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

## RESULT (27-Oct-2026): 8 of 1,518 passed – all BEARISH, all stock futures, daily
Why the patterns "don't work": on their own every pattern LOSES after costs (stocks daily 37-54% wins, -₹450…-₹6,500 per
lot; index and all 1-hour versions lose too). A single candle is common and usually just noise.
What works: BEARISH ENGULFING on a stock future after a rise, with volume > 1.5×: SL 1.5 ATR, target 1R →
win 55% / 68%, ₹2,065 / ₹7,208 per lot at 2× costs, 66% of stocks positive (58 + 75 trades). + near 20-day high: 54% / 69%.
Hanging man + OI falling (short covering on the rally) passed only thinly (₹315 / ₹2,798).
Bullish patterns (hammer, bullish engulfing, morning star) failed with every filter, incl. volume and OI.
Index futures: too few daily patterns (4-34 per period); hourly versions all lose.
Caution: the hold-out (Jul-2024 → Oct-2026) contained a long market decline, which favours bearish signals.
