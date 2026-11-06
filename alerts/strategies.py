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
    "BO_1d_BUY":     ("LIVE",   "A", "daily breakout BUY", 83, 58, 0.56, None,
                      "6-Nov MCX rule 20-day high + ADX>=25, 2R: +0.80/+0.02/+0.63 (SEARCH-ALL-001); index 2011-26 +0.55"),
    "BO_1d_SELL":    ("SHADOW", "-", "daily breakout SELL", 23, 48, -0.07, 0.88, "fewer than 30 trades"),
    "BO_1m_BUY":     ("LIVE",   "B", "monthly breakout BUY", 116, 49, 0.28, 1.62, "valid +0.07, test +0.34"),
    "BO_1m_SELL":    ("SHADOW", "-", "monthly breakout SELL", 24, 54, 0.09, 1.20, "fewer than 30 trades"),
    "BO_1w_BUY":     ("LIVE",   "A", "weekly 20-week breakout BUY", 146, 49, 0.64, None,
                      "6-Nov WKMO-001, 20 years MCX: 2006-12 +0.70 / 2013-19 +0.24 / 2020-26 +0.85; index weekly BUY +0.31"),
    "BO_1w_SELL":    ("SHADOW", "-", "weekly 20-week breakdown SELL", 92, 35, -0.23, None, "negative in every 20-year period"),
    "BO_1M_BUY":     ("LIVE",   "A", "monthly-candle breakout BUY", 104, 62, 0.68, None,
                      "6-Nov WKMO-001, MCX 2006-26: +0.76 / +0.26 / +0.96, all 7 commodities positive"),
    "BO_1M_SELL":    ("SHADOW", "-", "monthly-candle breakdown SELL", 103, 28, -0.49, None, "negative in every 20-year period"),
    "FH_MCX_BUY":    ("LIVE",   "A", "MCX 4-hour breakout BUY", 259, 44, 0.42, None,
                      "6-Nov rule vol 1.5x + daily trend, 2 ATR / 3R: +0.48/+0.09/+0.55, 7/7 commodities (SEARCH-ALL-001)"),
    "FH_STK3H_SELL": ("LIVE",   "A", "stock 3-hour breakdown SELL (daily downtrend)", 1335, 50, 0.13, None,
                      "6-Nov SEARCH-ALL-001: 5-candle low, vol>=2x, daily trend down, 1.5 ATR / 2R: +0.08/+0.01/+0.19"),
    "FH_STK_SELL":   ("LIVE",   "A", "stock 4-hour breakdown SELL", 913, 56, 0.17, None, "positive in all 3 periods (TFNH-001)"),
    "STK_OI_BUY":    ("LIVE",   "B", "stock OI breakout BUY", 623, 45, 0.08, 1.17,
                      "owner 6-Nov: keep sending (GLENMARK / TITAN type); backtest decaying train +0.27 / valid +0.01 / test -0.07"),
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


def tf_of(row):
    """Timeframe of a ledger row from its key (None when unknown -> treated as the same timeframe, conservative)."""
    k = str(row.get("key") or "")
    p = k.split("|")
    if k.startswith("RB|") and len(p) > 1:
        for tf in ("15m", "30m", "1h", "2h", "3h", "4h", "1d"):
            if f"_{tf}_" in p[1]:
                return tf
    if k.startswith("4H|"):
        return "4h"
    if k.startswith("3H|"):
        return "3h"
    if len(p) > 1 and p[1] in ("3h", "1d", "1w", "1m", "1M"):
        return p[1]
    if len(p) > 1 and p[1] == "1dSTK":
        return "1d"
    return {"MCX_HAMMER": "1d", "STK_HANGMAN": "1d", "STK_ENGULF": "1d", "MCX_EMA1348": "3h", "STK_SWEEP3H": "3h",
            "STK_SWEEP15": "15m"}.get(p[0])


def conflict(state, name, side, tf=None):
    """Reason string if a new call on `name` would contradict or duplicate an OPEN live futures call, else None.
    Opposite side open -> contradictory (always blocked).
    Same side open -> duplicate only on the SAME timeframe (6-Nov, PORTFOLIO-001: one call per instrument + direction +
    timeframe: 4.6 calls/day, +0.22R, PF 1.42, max DD 90R vs one per instrument + direction: 3.3/day, +0.15R, PF 1.30, 90R).
    tf=None keeps the old rule (any open same-side call blocks)."""
    for r in state.get("ledger", []):
        if r.get("status") == "OPEN" and r.get("cat") == "FUTURES" and r.get("name") == name:
            if r.get("side") != side:
                return f"contradicts the open {r.get('side')} call ({r.get('type')}, {str(r.get('time'))[:16]})"
            rtf = tf_of(r)
            if tf is not None and rtf is not None and rtf != tf:
                continue                                  # independent opportunity on another timeframe
            return f"duplicate of the open {side} call ({r.get('type')}, {str(r.get('time'))[:16]})"
    return None


SHADOW_MARK = "SHADOW_ONLY"          # messages of shadow calls carry this; alerts/run.py logs them instead of sending


def mark(text, shadow):
    return f"{SHADOW_MARK} {text}" if shadow else text
