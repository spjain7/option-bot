"""Strategy registry (call quality, 4-Nov-2026): every call type the alert engine can produce, its status and the
evidence behind it. One place decides what is SENT (LIVE), what is only logged with tracked outcomes (SHADOW) and what is
paper-traded (PAPER). Evidence = conservative backtest of the LIVE rules (next-open entry, stop first, costs) from
research STRATEGY-PROGRAM-001 / TFNH-001 / candle-setup studies (branch exp/strategy-program-001) – backtest, NOT live
results; live results are measured by alerts/scorecard.py from the ledger.

Status rules (owner directive 4-Nov: fewer, better calls; unvalidated = shadow):
  LIVE    positive expectancy after costs with >= 70 trades, and positive in the most recent test period
  SHADOW  negative or decaying, or fewer than 30 trades – logged and tracked, never sent
  PAPER   frozen candidate under a pre-registered prospective test (alerts/paper.py)
Tier (shown on LIVE calls): A = robust (all periods positive, >= 200 trades) · B = positive but smaller sample or uneven.
"""

S = {
    # id: (status, tier, label, trades, win %, avg R after costs, PF, note)
    "BO_3h_BUY":     ("LIVE",   "A", "3-hour breakout BUY", 345, 48, 0.28, 1.51, "train/valid/test +0.32/+0.11/+0.36"),
    "BO_3h_SELL":    ("SHADOW", "-", "3-hour breakout SELL", 212, 38, -0.08, 0.88, "negative in train and validation, 15-loss streak"),
    "BO_1d_BUY":     ("LIVE",   "B", "daily breakout BUY", 72, 51, 0.71, 2.63, "validation period -0.07; NIFTY/BANKNIFTY 2011-26 +0.55"),
    "BO_1d_SELL":    ("SHADOW", "-", "daily breakout SELL", 23, 48, -0.07, 0.88, "fewer than 30 trades"),
    "BO_1m_BUY":     ("LIVE",   "B", "monthly breakout BUY", 116, 49, 0.28, 1.62, "valid +0.07, test +0.34"),
    "BO_1m_SELL":    ("SHADOW", "-", "monthly breakout SELL", 24, 54, 0.09, 1.20, "fewer than 30 trades"),
    "FH_MCX_BUY":    ("LIVE",   "A", "MCX 4-hour breakout BUY", 277, 41, 0.39, None, "positive in all 3 periods (TFNH-001)"),
    "FH_STK_SELL":   ("LIVE",   "A", "stock 4-hour breakdown SELL", 913, 56, 0.17, None, "positive in all 3 periods (TFNH-001)"),
    "STK_OI_BUY":    ("SHADOW", "-", "stock OI breakout BUY", 623, 45, 0.08, 1.17, "decaying: train +0.27 / valid +0.01 / test -0.07"),
    "STK_OI_SELL":   ("LIVE",   "B", "stock OI breakdown SELL", 220, 57, 0.23, 1.76, "train/valid/test +0.05/+0.09/+0.32"),
    "STK_ENGULF_SELL": ("LIVE", "B", "stock bearish engulfing SELL", 120, 59, 0.20, 1.65, "train/valid/test +0.06/+0.22/+0.35"),
    "MCX_HAMMER":    ("LIVE",   "B", "MCX daily hammer breakout BUY", 413, 41, 0.20, 1.33,
                      "VERIFIED bhavcopy re-test (DATA-AUDIT-001): 2024-26 positive, 2022-23 and SILVER/NATURALGAS negative"),
    "MCX_EMA1348":   ("LIVE",   "B", "MCX 3-hour EMA 13/48 BUY", 79, 48, 0.67, None, "small sample, GOLD-heavy"),
    "STK_HANGMAN":   ("LIVE",   "B", "stock hanging-man breakdown SELL", 1217, 44, 0.18, None, "flat in 2023 and 2025"),
    "STK_SWEEP3H":   ("LIVE",   "B", "stock 3-hour sweep SELL", 387, 58, 0.15, None, "every year positive"),
    "E_BUY_v1":      ("PAPER",  "-", "MCX 1-hour compression breakout BUY", 174, 60, 0.21, None, "prospective test VAL-EBUY-001"),
}


def status(sid):
    return S.get(sid, ("LIVE", "-", sid, None, None, None, None, ""))[0]


def is_live(sid):
    return status(sid) == "LIVE"


def bo_id(tf, side):
    return f"BO_{tf}_{side}"


def evidence_line(sid):
    """One line for the WHY message of a LIVE call: what the backtest of these exact rules showed (not a promise)."""
    st, tier, label, n, w, r, pf, note = S.get(sid, (None,) * 8)
    if st != "LIVE" or n is None:
        return ""
    pf_ = f" · PF {pf:.2f}" if pf else ""
    return (f"• Record  : tier {tier} – {label}: {n} backtest trades 2022-26, {w}% won, {r:+.2f}R avg after costs{pf_} "
            f"(backtest, not a guarantee)")


def shadow_bo():
    """(tf, side) pairs of breakout calls that are logged only."""
    out = set()
    for sid, v in S.items():
        if sid.startswith("BO_") and v[0] != "LIVE":
            _, tf, side = sid.split("_")
            out.add((tf, side))
    return out


def conflict(state, name, side):
    """Reason string if a new call on `name` would contradict or duplicate an OPEN live futures call, else None.
    Opposite side open -> contradictory; same side open -> redundant (one live call per instrument and direction)."""
    for r in state.get("ledger", []):
        if r.get("status") == "OPEN" and r.get("cat") == "FUTURES" and r.get("name") == name:
            if r.get("side") != side:
                return f"contradicts the open {r.get('side')} call ({r.get('type')}, {str(r.get('time'))[:16]})"
            return f"duplicate of the open {side} call ({r.get('type')}, {str(r.get('time'))[:16]})"
    return None


SHADOW_MARK = "SHADOW_ONLY"          # messages of shadow calls carry this; alerts/run.py logs them instead of sending


def mark(text, shadow):
    return f"{SHADOW_MARK} {text}" if shadow else text
