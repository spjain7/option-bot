"""Call ledger + end-of-day call report (one table image per segment: MCX, and Index + Stock).
30-Oct (owner): every OPEN call of any day + every call CLOSED today, with the high / low reached after the call, the current
price (or exit), best / worst ₹ per lot and P&L per lot.

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


def pnl_rs(r, mark=None):
    px = r.get("exit") if r["status"] == "CLOSED" else mark
    if px is None:
        return None
    s = 1 if r["side"] in ("BUY",) else -1
    return round(s * (float(px) - float(r["entry"])) * float(r.get("mult") or 1))


def _ltp(q):
    if q is None:
        return None
    if isinstance(q, dict):
        v = float(q.get("ltp") or 0)
        return v if v > 0 else None
    return float(q) if q else None


def track(state, quotes, now):
    """Every scan: high / low of the price since the call for every OPEN ledger row (30-Oct, owner: daily report with the high /
    low after each call). Futures rows track the futures; option-buy rows track their underlying (option ≈ 0.5 × move).
    A row opened before today also takes today's full day high / low from the quote (all of it is after the call)."""
    today = now.normalize()
    for r in state.get("ledger", []):
        if r.get("status") != "OPEN":
            continue
        q = quotes.get(r.get("mark_key")) if r.get("mark_key") else None
        p = _ltp(q)
        if p is None:
            continue
        base = float(r["und_entry"]) if r.get("cat") == "OPTION BUY" and r.get("und_entry") is not None else float(r["entry"])
        hi, lo = max(r.get("uhi", base), p), min(r.get("ulo", base), p)
        if isinstance(q, dict) and pd.Timestamp(r.get("time")).normalize() < today:
            dh, dl = float(q.get("high") or 0), float(q.get("low") or 0)
            if dh > 0:
                hi = max(hi, dh)
            if dl > 0:
                lo = min(lo, dl)
        r["uhi"], r["ulo"], r["ulast"], r["uat"] = round(hi, 2), round(lo, 2), round(p, 2), str(now)


def _opt_est(r, und_px):
    s = 1 if r.get("und_side") == "BUY" else -1
    return max(0.05, float(r["entry"]) + 0.5 * s * (und_px - float(r["und_entry"])))


def _hilo(r):
    """(high, low) of the CALLED instrument after the call, or (None, None)."""
    if r.get("uhi") is None:
        return r.get("hi"), r.get("lo")
    if r.get("cat") == "OPTION BUY" and r.get("und_entry") is not None:
        a, b = _opt_est(r, r["uhi"]), _opt_est(r, r["ulo"])
        return max(a, b), min(a, b)
    return r["uhi"], r["ulo"]


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
                                pnl=p.get("pnl_rs_per_lot") if status == "CLOSED" else None,
                                note=p.get("exit_reason", "") if status == "CLOSED" else ""))
            return out
    return []


OBUY_STATE = os.getenv("OBUY_STATE_FILE", "state/obuy/state.json")


def option_buys(today):
    """Stock option-BUY calls (obuy engine): every open one + those closed today, with the premium high / low after the call."""
    try:
        st = json.loads(Path(OBUY_STATE).read_text())
    except Exception:
        return []
    out = []
    for a, status in [(a, "OPEN") for a in st.get("open", [])] + [(a, "CLOSED") for a in st.get("closed", [])]:
        if status == "CLOSED" and str(a.get("closed", a.get("opened", "")))[:10] != today:
            continue
        lot = a.get("lot")
        cmp_ = a.get("exit") if status == "CLOSED" else a.get("last")
        pnl = a.get("rs_lot") if status == "CLOSED" else (round((float(cmp_) - float(a["entry"])) * float(lot)) if cmp_ and lot else None)
        out.append(dict(seg="NSE", cat="OPTION BUY", name=a.get("name"), symbol=a.get("symbol"),
                        type="Intraday" if a.get("mode") == "intraday" else "Positional", side="BUY", entry=a.get("entry"),
                        sl=a.get("sl"), target=a.get("tg"), lot=lot, mult=lot, status=status, time=a.get("opened"),
                        hi=a.get("hi"), lo=a.get("lo"), cmp=cmp_, pnl=pnl,
                        note=a.get("why_exit", "") if status == "CLOSED" else ""))
    for r in (st.get("sweep15") or {}).get("open", []) + (st.get("sweep15") or {}).get("closed", []):
        if not r.get("send") or r.get("entry") is None:
            continue
        status = "CLOSED" if r.get("status") == "closed" else "OPEN"
        if status == "CLOSED" and str(r.get("closed", ""))[:10] != today:
            continue
        lot = r.get("lot") or 1
        sd = 1 if r.get("side") == "BUY" else -1
        pnl = round(sd * (float(r["exit"]) - float(r["entry"])) * float(lot)) if status == "CLOSED" and r.get("exit") is not None else None
        out.append(dict(seg="NSE", cat="FUTURES", name=r.get("name"), symbol=r.get("contract") or r.get("name"), type="Intraday (15-min sweep)",
                        side=r.get("side"), entry=r.get("entry"), sl=r.get("stop"), target=r.get("target"), lot=lot, mult=lot,
                        status=status, time=r.get("entry_time") or r.get("sweep_time"), hi=r.get("hi"), lo=r.get("lo"),
                        cmp=r.get("exit"), pnl=pnl, note=r.get("exit_reason", "") if status == "CLOSED" else ""))
    return out


def rows_for(state, seg, today, marks):
    """Every OPEN call (any day) + every call CLOSED today, with high / low after the call, CMP (or exit) and P&L per lot."""
    out = []
    for r in state.get("ledger", []):
        if r["seg"] != seg or (r["status"] == "CLOSED" and str(r.get("closed", r["date"]))[:10] != today):
            continue
        mk = _ltp(marks.get(r.get("mark_key"))) if r["status"] == "OPEN" else None
        if mk is None and r["status"] == "OPEN":
            mk = r.get("ulast")
        if r["cat"] == "OPTION BUY" and mk is not None and r.get("und_entry") is not None:
            mk = _opt_est(r, mk)
        hi, lo = _hilo(r)
        cmp_ = r.get("exit") if r["status"] == "CLOSED" else mk
        out.append(dict(r, pnl=pnl_rs(r, mk), hi=hi, lo=lo, cmp=cmp_))
    out += [x for x in option_sells(today) + option_buys(today) if x["seg"] == seg]
    for x in out:                                         # best / worst ₹ per lot reached after the call
        m, s_ = float(x.get("mult") or x.get("lot") or 1), 1 if x.get("side") == "BUY" else -1
        if x.get("hi") is not None and x.get("lo") is not None and x.get("entry") is not None and x.get("cat") != "OPTION SELL":
            e = float(x["entry"])
            fav, adv = (float(x["hi"]), float(x["lo"])) if s_ > 0 else (float(x["lo"]), float(x["hi"]))
            x["best"], x["worst"] = round(s_ * (fav - e) * m), round(s_ * (adv - e) * m)
    return out


def _fmt(v):
    if v is None or v == "":
        return "-"
    try:
        v = float(v)
    except Exception:
        return str(v)
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"


HEAD = ["Called", "Instrument", "Category", "Call type", "Side", "Entry", "SL", "Target", "Lot", "High after", "Low after",
        "CMP / Exit", "Best ₹", "Worst ₹", "P&L ₹/lot", "Status"]


def _cells(r):
    t = pd.Timestamp(r.get("time")) if r.get("time") else None
    pn = r.get("pnl")
    return [f"{t:%d-%b %H:%M}" if t is not None else "-", r.get("symbol") or r["name"], r["cat"], r["type"], r["side"],
            _fmt(r.get("entry")), _fmt(r.get("sl")), _fmt(r.get("target")), str(int(r["lot"])) if r.get("lot") else "-",
            _fmt(r.get("hi")), _fmt(r.get("lo")), _fmt(r.get("cmp")),
            _fmt(r.get("best")), _fmt(r.get("worst")), ("+" if (pn or 0) > 0 else "") + _fmt(pn),
            r["status"] + (f" ({r['note']})" if r.get("note") else "")]


def render(rows, title, path):
    """Table image (PNG). Returns path, or None when matplotlib is not available."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    body = [_cells(r) for r in rows]
    tot = sum(float(r["pnl"]) for r in rows if r.get("pnl") is not None)
    n_open = sum(r["status"] == "OPEN" for r in rows)
    fig_h = 1.0 + 0.36 * (max(1, len(body)) + 1)
    fig, ax = plt.subplots(figsize=(21, fig_h))
    ax.axis("off")
    ax.set_title(f"{title}   ·   open {n_open} · closed today {len(rows) - n_open}   ·   P&L (closed + open at CMP): "
                 f"{'+' if tot > 0 else ''}₹{tot:,.0f} per lot", fontsize=14, fontweight="bold", loc="left")
    if not body:
        body = [["-", "No open calls and none closed today"] + [""] * (len(HEAD) - 2)]
    t = ax.table(cellText=body, colLabels=HEAD, loc="upper center", cellLoc="center",
                 colWidths=[0.055, 0.13, 0.06, 0.09, 0.035, 0.05, 0.05, 0.05, 0.035, 0.055, 0.055, 0.055, 0.05, 0.05, 0.055, 0.12])
    t.auto_set_font_size(False)
    t.set_fontsize(9)
    t.scale(1, 1.5)
    for (i, j), cell in t.get_celld().items():
        if i == 0:
            cell.set_facecolor("#1f3b57"); cell.set_text_props(color="white", fontweight="bold")
        else:
            row = body[i - 1]
            cell.set_facecolor("#f7f7f2" if i % 2 else "white")
            if j in (12, 13, 14) and row[j] not in ("-", ""):
                cell.set_text_props(color="#0a7a2f" if not row[j].startswith("-") else "#b3261e", fontweight="bold" if j == 14 else "normal")
            if j == 4:
                cell.set_text_props(color="#0a7a2f" if row[4] == "BUY" else "#b3261e")
    plt.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def text_table(rows, title):
    L = [title]
    for r in rows:
        c = _cells(r)
        L.append(f"• {c[0]} {c[1]} · {r['cat']} · {r['type']} · {r['side']} {c[5]} · SL {c[6]} · T {c[7]} · lot {c[8]}\n"
                 f"   high {c[9]} · low {c[10]} · {'exit' if r['status'] == 'CLOSED' else 'CMP'} {c[11]} · best {c[12]} · worst {c[13]} · "
                 f"P&L {c[14]} · {c[15]}")
    if len(rows) == 0:
        L.append("No open calls and none closed today.")
    tot = sum(float(r["pnl"]) for r in rows if r.get("pnl") is not None)
    L.append(f"Total P&L: ₹{tot:,.0f} per lot (closed at exit, open at the current price; ₹ per lot = 1 lot; "
             "option-buy rows on futures calls ≈ 0.5 × futures move)")
    return "\n".join(L)


def build(state, seg, now, marks, out_dir):
    today = str(now.date())
    rows = sorted(rows_for(state, seg, today, marks), key=lambda r: (r["status"] != "OPEN", str(r.get("time"))))
    title = f"{'MCX' if seg == 'MCX' else 'INDEX + STOCK'} CALLS – {now:%d %b %Y} (all open + closed today)"
    png = render(rows, title, Path(out_dir) / f"report_{seg}.png")
    txt = text_table(rows, "📊 " + title)
    return ([f"PHOTO::{png}::{title}"] if png else []) + [txt]
