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
CALL_TYPE = {"3h": "Positional (3-hour)", "1d": "Positional (daily)"}


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


def rows_for(state, seg, today, marks):
    out = []
    for r in state.get("ledger", []):
        if r["seg"] != seg or (r["date"] != today and r["status"] == "CLOSED"):
            continue
        mk = marks.get(r.get("mark_key"))
        if r["cat"] == "OPTION BUY" and mk is not None and r.get("und_entry") is not None:
            mk = max(0.05, float(r["entry"]) + 0.5 * (1 if r["und_side"] == "BUY" else -1) * (mk - float(r["und_entry"])))
        out.append(dict(r, pnl=pnl_rs(r, mk)))
    out += [x for x in option_sells(today) if x["seg"] == seg]
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
                     ("+" if (r.get("pnl") or 0) > 0 else "") + _fmt(r.get("pnl")),
                     r["status"] + (f" ({r['note']})" if r.get("note") else "")])
    tot = sum(float(r["pnl"]) for r in rows if r.get("pnl") is not None)
    fig_h = 0.9 + 0.36 * (max(1, len(body)) + 1)
    fig, ax = plt.subplots(figsize=(15, fig_h))
    ax.axis("off")
    ax.set_title(f"{title}   ·   Total P&L: {'+' if tot > 0 else ''}₹{tot:,.0f} per lot", fontsize=14, fontweight="bold", loc="left")
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
                cell.set_text_props(color="#0a7a2f" if not body[i - 1][9].startswith("-") else "#b3261e", fontweight="bold")
            if j == 4:
                cell.set_text_props(color="#0a7a2f" if body[i - 1][4] == "BUY" else "#b3261e")
    plt.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def text_table(rows, title):
    L = [title]
    for r in rows:
        L.append(f"• {r.get('symbol') or r['name']} · {r['cat']} · {r['type']} · {r['side']} {_fmt(r.get('entry'))} · SL {_fmt(r.get('sl'))} · "
                 f"T {_fmt(r.get('target'))} · lot {int(r['lot']) if r.get('lot') else '-'} · P&L {_fmt(r.get('pnl'))} · {r['status']}")
    if len(rows) == 0:
        L.append("No calls today.")
    tot = sum(float(r["pnl"]) for r in rows if r.get("pnl") is not None)
    L.append(f"Total P&L: ₹{tot:,.0f} per lot (open calls marked at the last price; option-buy P&L ≈ 0.5 × futures move)")
    return "\n".join(L)


def build(state, seg, now, marks, out_dir):
    today = str(now.date())
    rows = sorted(rows_for(state, seg, today, marks), key=lambda r: str(r.get("time")))
    title = f"{'MCX' if seg == 'MCX' else 'INDEX + STOCK'} CALLS – {now:%d %b %Y}"
    png = render(rows, title, Path(out_dir) / f"report_{seg}.png")
    txt = text_table(rows, "📊 " + title)
    return ([f"PHOTO::{png}::{title}"] if png else []) + [txt]
