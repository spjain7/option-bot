"""Call ledger + end-of-day call report (one table image per segment: MCX, and Index + Stock).

Ledger rows (state["ledger"]) are written when a call is sent and closed when it exits. Option-SELL calls are read from
the option-selling engine's state file (state/state.json of the main branch). The report is sent once after the NSE
close (Index + Stock) and once after the MCX close. ALERTS ONLY – no orders.
"""
import json
import os
from pathlib import Path
import pandas as pd

MCX_RS_PER_POINT = {"CRUDEOIL": 100, "NATURALGAS": 1250, "GOLD": 100, "SILVER": 30, "COPPER": 2500, "ZINC": 5000, "ALUMINIUM": 5000}
OPT_STATE_CANDIDATES = [os.getenv("OPT_STATE_FILE", ""), "/tmp/opt/state/state.json",
                        str(Path(__file__).resolve().parents[1] / "state" / "state.json")]
# Option-buy cost model (same numbers as the option-buy research, research/search/obuy_month.py): half bid-ask spread paid
# on entry and on exit (the measured spread at the alert is used when known), exchange + tax ≈ 0.16 % of the sell value,
# ₹40 brokerage per lot round trip. Prices are LTP / quote based – NOT broker fills.
OPT_HALF_SPREAD = {"index": 0.003, "stock": 0.01, "mcx": 0.015}
OPT_FEES = 0.0016
OPT_BROKER_LOT = 40.0
PREMIUM_MAX_AGE_MIN = 30          # a recorded premium older than this is not used as the exit price
INDEX_NAMES = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"}
BASIS_QUOTE = "premium quote"
BASIS_EST = "estimated"
CALL_TYPE = {"3h": "Positional", "1d": "Positional", "1w": "Positional (weekly)", "1m": "Positional (monthly)"}


def mult_for(name, ex, lot):
    """₹ per 1 point per lot."""
    if ex == "MCX":
        return MCX_RS_PER_POINT.get(name, 1)
    return int(lot or 1)


def add(state, **row):
    row.setdefault("status", "OPEN")
    row.setdefault("date", str(pd.Timestamp(row.get("time")).date()))
    state.setdefault("ledger", []).append(row)
    state["ledger"] = state["ledger"][-500:]
    return row


def opt_kind(seg, name):
    return "mcx" if seg == "MCX" else "index" if name in INDEX_NAMES else "stock"


def option_pnl(entry, exitp, lot, kind, spread=None):
    """₹ per lot for an option BUY after spread, fees and brokerage. entry / exit are LTPs (mid-ish), not fills."""
    if entry is None or exitp is None or not lot:
        return None
    hs = spread / 2 if spread and spread > 0 else OPT_HALF_SPREAD[kind]
    buy, sell = float(entry) * (1 + hs), float(exitp) * (1 - hs)
    return round((sell - buy - OPT_FEES * sell) * float(lot) - OPT_BROKER_LOT)


def pnl_rs(r, mark=None):
    if r["status"] == "CLOSED" and str(r.get("note", "")).startswith("cancelled"):
        return 0                                           # call cancelled before entry – no trade
    px = r.get("exit") if r["status"] == "CLOSED" else mark
    if px is None:
        return None
    if r.get("cat") == "OPTION BUY":
        return option_pnl(r["entry"], px, r.get("lot"), r.get("kind") or opt_kind(r.get("seg"), r.get("name")), r.get("spread"))
    s = 1 if r["side"] in ("BUY",) else -1
    return round(s * (float(px) - float(r["entry"])) * float(r.get("mult") or 1))


def track_options(api, state, now, is_open):
    """Follow every open OPTION-BUY ledger row on its OWN premium (option token), not on the futures move.
    Uses only quotes that pass the exchange-timestamp checks. Premium SL / target hit -> row closed at the quoted level
    (stop at the worse of SL and LTP). Returns the number of rows closed."""
    from alerts import tradeplan as TP
    rows = [r for r in state.get("ledger", []) if r.get("cat") == "OPTION BUY" and r["status"] == "OPEN" and r.get("opt_token")]
    by_ex = {}
    for r in rows:
        if is_open(r.get("opt_ex") or ("MCX" if r["seg"] == "MCX" else "NFO"), now):
            by_ex.setdefault(r.get("opt_ex") or ("MCX" if r["seg"] == "MCX" else "NFO"), []).append(r)
    n = 0
    for ex, rr in by_ex.items():
        try:
            q = api.quotes({ex: sorted({r["opt_token"] for r in rr})}) or {}
        except Exception:
            continue
        for r in rr:
            x = q.get(r["opt_token"]) or {}
            ltp = float(x.get("ltp") or 0)
            if ltp <= 0 or TP.quote_check(x, now, require=True)[1]:
                continue
            r.update(last_prem=ltp, last_prem_time=str(now))
            if ltp <= float(r["sl"]):
                r.update(status="CLOSED", exit=round(min(ltp, float(r["sl"])), 2), note="SL hit (premium)", closed=str(now), basis=BASIS_QUOTE)
                n += 1
            elif r.get("target") and ltp >= float(r["target"]):
                r.update(status="CLOSED", exit=float(r["target"]), note="target hit (premium)", closed=str(now), basis=BASIS_QUOTE)
                n += 1
    return n


def option_exit_on_futures_close(L, fut_exit, now):
    """Exit premium for an option row whose futures call has just closed -> (price, basis).
    A premium quoted in the last PREMIUM_MAX_AGE_MIN minutes is used; otherwise the old estimate
    (entry premium + 0.5 × futures move) is used and labelled as estimated."""
    t = L.get("last_prem_time")
    if L.get("last_prem") and t and (pd.Timestamp(now) - pd.Timestamp(t)).total_seconds() <= PREMIUM_MAX_AGE_MIN * 60:
        return round(float(L["last_prem"]), 2), BASIS_QUOTE
    s = 1 if L.get("und_side") == "BUY" else -1
    if L.get("und_entry") is None:
        return None, "unverified – no premium and no futures reference"
    return round(max(0.05, float(L["entry"]) + 0.5 * s * (fut_exit - float(L["und_entry"]))), 2), BASIS_EST


def option_sells(today):
    """Option-SELL calls of today (open + closed) from the option-selling engine's state file."""
    for f in OPT_STATE_CANDIDATES:
        if f and Path(f).exists():
            try:
                st = json.loads(Path(f).read_text())
            except Exception:
                continue
            out = []
            for p, status in [(p, "OPEN") for p in st.get("positions", [])] + [(p, "CLOSED") for p in st.get("closed", [])]:
                if str(p.get("opened", ""))[:10] != today and status == "CLOSED":
                    continue
                leg = (p.get("legs") or [{}])[0]
                out.append(dict(seg="MCX" if p.get("exch") == "MCX" else "NSE", cat="OPTION SELL", name=p.get("name"),
                                symbol=leg.get("symbol", ""), type=("Intraday" if p.get("mode") == "intraday" else "Positional"),
                                side="SELL", entry=p.get("credit"), sl=p.get("sl_val"), target=p.get("target_val"),
                                lot=p.get("lot"), status=status, time=p.get("opened"),
                                pnl=p.get("pnl_rs_per_lot") if status == "CLOSED" else None, basis="engine (spread value)",
                                note=p.get("exit_reason", "") if status == "CLOSED" else ""))
            return out
    return []


OBUY_STATE = os.getenv("OBUY_STATE_FILE", "state/obuy/state.json")


def option_buys(today):
    """Intraday stock option-BUY calls (obuy engine) of today."""
    try:
        st = json.loads(Path(OBUY_STATE).read_text())
    except Exception:
        return []
    out = []
    for a, status in [(a, "OPEN") for a in st.get("open", [])] + [(a, "CLOSED") for a in st.get("closed", [])]:
        if str(a.get("opened", ""))[:10] != today:
            continue
        out.append(dict(seg="NSE", cat="OPTION BUY", name=a.get("name"), symbol=a.get("symbol"),
                        type="Intraday" if a.get("mode") == "intraday" else "Positional", side="BUY", entry=a.get("entry"),
                        sl=a.get("sl"), target=a.get("tg"), lot=a.get("lot"), status=status, time=a.get("opened"),
                        pnl=a.get("rs_lot") if status == "CLOSED" else None, note=a.get("why_exit", "") if status == "CLOSED" else "",
                        basis=BASIS_QUOTE))
    return out


def rows_for(state, seg, today, marks):
    out = []
    for r in state.get("ledger", []):
        if r["seg"] != seg or (r["date"] != today and r["status"] == "CLOSED"):
            continue
        mk = marks.get(r.get("mark_key"))
        basis = r.get("basis")
        if r["cat"] == "OPTION BUY" and r["status"] == "OPEN":
            if r.get("opt_token") and r.get("mark_key") == r.get("opt_token"):
                basis = BASIS_QUOTE                         # marked on the option's own premium
            elif mk is not None and r.get("und_entry") is not None:   # older rows: only the futures price is known
                mk = max(0.05, float(r["entry"]) + 0.5 * (1 if r["und_side"] == "BUY" else -1) * (mk - float(r["und_entry"])))
                basis = BASIS_EST
        elif r["cat"] == "OPTION BUY" and not basis:
            basis = BASIS_EST                               # rows closed before premium tracking existed
        out.append(dict(r, pnl=pnl_rs(r, mk), basis=basis))
    out += [x for x in option_sells(today) + option_buys(today) if x["seg"] == seg]
    return out


def _fmt(v):
    if v is None or v == "":
        return "-"
    try:
        v = float(v)
    except Exception:
        return str(v)
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"


def render(rows, title, path):
    """Table image (PNG). Returns path, or None when matplotlib is not available."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    head = ["Time", "Instrument", "Category", "Call type", "Side", "Entry", "SL", "Target", "Lot", "P&L ₹/lot", "Status"]
    body = []
    for r in rows:
        body.append([str(r.get("time", ""))[11:16], r.get("symbol") or r["name"], r["cat"], r["type"], r["side"], _fmt(r.get("entry")),
                     _fmt(r.get("sl")), _fmt(r.get("target")), str(int(r["lot"])) if r.get("lot") else "-",
                     _pnl_cell(r),
                     r["status"] + (f" ({r['note']})" if r.get("note") else "")])
    tot, est = totals(rows)
    fig_h = 0.9 + 0.36 * (max(1, len(body)) + 1)
    fig, ax = plt.subplots(figsize=(15, fig_h))
    ax.axis("off")
    ax.set_title(f"{title}   ·   Total P&L: {'+' if tot > 0 else ''}₹{tot:,.0f} per lot" + (f"  (≈ ₹{est:,.0f} of it estimated)" if est else ""),
                 fontsize=14, fontweight="bold", loc="left")
    if not body:
        body = [["-", "No calls today", "", "", "", "", "", "", "", "", ""]]
    t = ax.table(cellText=body, colLabels=head, loc="upper center", cellLoc="center",
                 colWidths=[0.05, 0.17, 0.08, 0.11, 0.05, 0.07, 0.07, 0.07, 0.05, 0.08, 0.14])
    t.auto_set_font_size(False)
    t.set_fontsize(9.5)
    t.scale(1, 1.5)
    for (i, j), cell in t.get_celld().items():
        if i == 0:
            cell.set_facecolor("#1f3b57"); cell.set_text_props(color="white", fontweight="bold")
        else:
            cell.set_facecolor("#f7f7f2" if i % 2 else "white")
            if j == 9 and body[i - 1][9] not in ("-", ""):
                cell.set_text_props(color="#0a7a2f" if "-" not in body[i - 1][9] else "#b3261e", fontweight="bold")
            if j == 4:
                cell.set_text_props(color="#0a7a2f" if body[i - 1][4] == "BUY" else "#b3261e")
    ax.text(0, 0, FOOTNOTE, transform=ax.transAxes, fontsize=8, va="top", color="#555")
    plt.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return str(path)


FOOTNOTE = ("P&L per lot from quoted prices (LTP / alert levels), not broker fills. Futures: before costs. Option buys: after "
            "spread, fees and ₹40 brokerage. ≈ = estimated from the futures move (no option premium available) – not a real result.")


def _pnl_cell(r):
    v = r.get("pnl")
    if v is None:
        return "-" if r.get("cat") != "OPTION BUY" or r.get("status") != "CLOSED" else "unverified"
    return ("≈" if r.get("basis") == BASIS_EST else "") + ("+" if v > 0 else "") + _fmt(v)


def totals(rows):
    tot = sum(float(r["pnl"]) for r in rows if r.get("pnl") is not None)
    est = sum(float(r["pnl"]) for r in rows if r.get("pnl") is not None and r.get("basis") == BASIS_EST)
    return tot, est


def text_table(rows, title):
    L = [title]
    for r in rows:
        L.append(f"• {r.get('symbol') or r['name']} · {r['cat']} · {r['type']} · {r['side']} {_fmt(r.get('entry'))} · SL {_fmt(r.get('sl'))} · "
                 f"T {_fmt(r.get('target'))} · lot {int(r['lot']) if r.get('lot') else '-'} · P&L {_pnl_cell(r)} · {r['status']}")
    if len(rows) == 0:
        L.append("No calls today.")
    tot, est = totals(rows)
    L.append(f"Total P&L: ₹{tot:,.0f} per lot" + (f" (≈ ₹{est:,.0f} of it estimated)" if est else ""))
    L.append(FOOTNOTE)
    return "\n".join(L)


def build(state, seg, now, marks, out_dir):
    today = str(now.date())
    rows = sorted(rows_for(state, seg, today, marks), key=lambda r: str(r.get("time")))
    title = f"{'MCX' if seg == 'MCX' else 'INDEX + STOCK'} CALLS – {now:%d %b %Y}"
    png = render(rows, title, Path(out_dir) / f"report_{seg}.png")
    txt = text_table(rows, "📊 " + title)
    return ([f"PHOTO::{png}::{title}"] if png else []) + [txt]
