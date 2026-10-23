# INTRA-CLUE-001 (registered 23-Oct-2026, before running) – "what clues come before an intraday move?"
Idea (user): every move leaves clues before it starts. Study every 1-hour candle and ask which conditions at its close
came before a winning same-day trade in the next hours, then trade only when the clues line up.
Universes: STOCKS (181 futures), INDEX (NIFTY, BANKNIFTY), MCX (7). 1-hour candles, Jul-2022 → Oct-2026.
Clues (all known at the candle close, ~45): trend (daily EMA50/EMA200, ADX), position vs VWAP / day range / previous
day high-low / open, gap, volume vs same-hour normal, day volume so far, RSI + slope, 1h EMA20/50, range compression
(NR4, inside bar, small candle), 1h candlestick patterns (engulfing, hammer, shooting star, doji, marubozu,
morning/evening star, piercing/dark cloud), yesterday's daily pattern (engulfing, hammer/star, inside, NR7),
OI change yesterday (stocks), hour of day, weekday.
Trade: entry next candle open, same-day exit; exits A = stop 1 ATR / target 1.5 ATR, B = stop 1.5 ATR / target 0.75 ATR.
Steps:
 1 Clue table (design < 2024-01-01): win % and R for each clue vs the base rate.
 2 Model: gradient-boosted trees learn the clue combinations on design (< 2024-01-01); the probability threshold is
   picked on validation (Jan–Jun 2024; top 2/5/10% of candles); max 1 trade per instrument per day.
 3 Hold-out (≥ 2024-07-01, untouched): PASS = ≥ 100 trades, exp > 0 after costs and > 0 at 2× costs.
   Win rate is reported (goal 80%+), but a rule that loses money is not deployed.
 4 A depth-3 decision tree is printed as readable rules.
