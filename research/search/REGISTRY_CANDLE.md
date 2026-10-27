# CANDLE-001 (registered 27-Oct-2026, before running) – classic reversal candles + volume + OI, stock & index futures
Patterns (on closed candles): hammer, hanging man, bullish engulfing, bearish engulfing, morning star, evening star.
Definitions: body = |close-open|, range = high-low; hammer / hanging man = lower wick ≥ 2× body, upper wick ≤ 0.3× range;
engulfing = body fully covers the previous opposite-colour body; stars = big candle, small-body candle (≤ 0.3× range),
then a candle closing beyond the middle of the first.
Context (required – a reversal needs something to reverse): bullish patterns (hammer, bullish engulfing, morning star)
only after a decline (close < EMA20 and 5-candle return < 0); bearish (hanging man, bearish engulfing, evening star) only
after a rise (close > EMA20 and 5-candle return > 0).
Filters: none / vol (pattern candle volume > 1.5×) / sr (bullish within 0.5 ATR of the 20-candle low, bearish of the high)
/ conf (the NEXT candle closes beyond the pattern high/low; entry after it) / oi (stocks, daily: pattern-day OI change
≥ +2% = fresh positions in the reversal direction is not knowable, so used as: bullish needs OI falling on the decline =
long unwinding exhaustion (OI ≤ -1%); bearish needs OI falling on the rise = short covering (OI ≤ -1%)) and pairs.
Timeframes: DAILY (stocks 181, NIFTY/BANKNIFTY) and 1-HOUR (same instruments, max 10 candles).
Stop: PT = beyond the pattern low/high + 0.1 ATR; A1.5 = 1.5 ATR. Target: R0.5, R1, R2.
PASS: avg ₹/lot > 0 at 2× costs in design (< 2024-07) AND hold-out, ≥ 40 trades per period, ≥ 55% of instruments
positive. Win % reported.
