"""Live call scorecard (4-Nov-2026): measured results per strategy from the ledger – LIVE calls, SHADOW calls and PAPER
trades kept apart, never mixed. Used in the end-of-day message and the run log.

Per group: closed calls, first-target hit rate, profitable rate, expectancy (avg R), profit factor, avg MFE / MAE (R).
R = (exit − entry) × side ÷ initial risk |entry − SL| (gross of costs for live calls; paper trades are net of costs).
"""
import math


def _r(row):
    try:
        e, sl, x = float(row["entry"]), float(row["sl"]), float(row["exit"])
    except (TypeError, ValueError, KeyError):
        return None
    s = 1 if row.get("side") == "BUY" else -1
    risk = s * (e - sl)
    return s * (x - e) / risk if risk > 0 else None


def strategy_of(row):
    """Registry id of a ledger row, from its key (alerts/strategies.py ids)."""
    k = str(row.get("key") or "")
    side = row.get("side") or "?"
    parts = k.split("|")
    if parts[0] in ("MCX_HAMMER", "MCX_EMA1348", "STK_HANGMAN", "STK_SWEEP3H"):
        return parts[0]
    if parts[0] == "4H":
        return "FH_MCX_BUY" if row.get("seg") == "MCX" else "FH_STK_SELL"
    if len(parts) > 1 and parts[1] == "1dSTK":
        return "STK_ENGULF_SELL" if "ENGULF" in k.upper() else f"STK_OI_{side}"
    if len(parts) > 1 and parts[1] in ("3h", "1d", "1m", "1w"):
        return f"BO_{parts[1]}_{side}"
    return row.get("type") or "?"


def _stats(rs, t1=None, mfe=None, mae=None):
    rs = [r for r in rs if r is not None and math.isfinite(r)]
    if not rs:
        return None
    w, l = [r for r in rs if r > 0], [r for r in rs if r <= 0]
    avg = lambda x: sum(x) / len(x) if x else None
    return dict(n=len(rs), profitable=len(w) / len(rs), exp_R=avg(rs),
                pf=(sum(w) / -sum(l)) if l and sum(l) < 0 else None,
                t1_hit=avg([1.0 if x else 0.0 for x in t1]) if t1 else None,
                mfe=avg([x for x in (mfe or []) if x is not None]), mae=avg([x for x in (mae or []) if x is not None]))


def build(state):
    """-> dict(group -> {strategy -> stats})."""
    out = {"LIVE": {}, "SHADOW": {}, "PAPER": {}}
    groups = {}
    for r in state.get("ledger", []):
        note = str(r.get("note", "")).lower()
        if r.get("cat") != "FUTURES" or r.get("status") != "CLOSED" or "cancel" in note or "withdrawn" in note:
            continue
        groups.setdefault(strategy_of(r), []).append(r)
    for k, rows in groups.items():
        st = _stats([_r(x) for x in rows], [x.get("t1_hit") for x in rows if "t1_hit" in x],
                    [x.get("mfe_R") for x in rows], [x.get("mae_R") for x in rows])
        if st:
            out["LIVE"][k] = st
    sh = {}
    for x in state.get("shadow_bo", []):
        sh.setdefault(str(x.get("label", "?")).split(" (")[0], []).append(x.get("r") if x.get("r") is not None else x.get("R"))
    for x in state.get("shadow_calls", []):
        sh.setdefault(x.get("strategy", "?"), []).append(x.get("R"))
    for k, rs in sh.items():
        st = _stats(rs)
        if st:
            out["SHADOW"][k] = st
    for sid, b in (state.get("paper") or {}).items():
        cl = [x for x in b.get("closed", []) if x.get("status") == "CLOSED"]
        st = _stats([x.get("net_R") for x in cl], [x.get("t1_hit") for x in cl], [x.get("mfe_R") for x in cl],
                    [x.get("mae_R") for x in cl])
        if st:
            out["PAPER"][sid] = st
    return out


def text(state, max_rows=8):
    """Compact scorecard lines for Telegram (empty string when nothing has closed yet)."""
    sc = build(state)
    lines = []
    for grp, title in (("LIVE", "Live calls (sent)"), ("SHADOW", "Shadow calls (logged, not sent)"), ("PAPER", "Paper trades (not sent)")):
        if not sc[grp]:
            continue
        lines.append(f"{title}:")
        for k, s in sorted(sc[grp].items(), key=lambda kv: -kv[1]["n"])[:max_rows]:
            pf = f" · PF {s['pf']:.2f}" if s["pf"] is not None else ""
            t1 = f" · T1 {s['t1_hit']:.0%}" if s["t1_hit"] is not None else ""
            ex = f" · MFE {s['mfe']:+.2f}R / MAE {s['mae']:+.2f}R" if s["mfe"] is not None and s["mae"] is not None else ""
            lines.append(f"• {k}: {s['n']} closed · {s['profitable']:.0%} profitable · avg {s['exp_R']:+.2f}R{pf}{t1}{ex}")
    if not lines:
        return ""
    return "📊 SCORECARD (measured, since tracking began)\n" + "\n".join(lines) + "\nSmall samples – not yet evidence."
