# STOCK-1H-002 (registered 23-Oct-2026, before running) – stock futures, 1-hour data, new idea families
Why earlier tests failed: same-day moves of one stock on 1-hour candles are small vs costs (≈0.1% + slippage per round trip).
New families use effects documented in market research (cross-sectional strength, overnight drift, short-term reversal):
 R1 rel_strength   at the first-hour close, rank stocks by first-hour return MINUS NIFTY's; when NIFTY's first hour is up,
                   buy the top N; when down, sell the bottom N. Exit: day close (R1a) or next day close (R1b).
 R2 late_momentum  rank by return prev-close → 14:15; buy top N / sell bottom N at 14:15, exit at the close.
 R3 overnight      strong day (close in top 20% of the day range, day volume > 1.5× avg, above daily EMA50) → buy at 15:15,
                   exit next day 10:15 close (R3a) or next day close (R3b). Shorts mirror.
 R4 rsi2_dip       daily RSI(2) < 10 above daily EMA200 → buy next open; exit on a daily close above the 5-day average or
                   after 5 days (R4a: no stop, R4b: 3-ATR stop). Shorts mirror (RSI(2) > 90, below EMA200).
 R5 rsi2_dip + OI  R4 only when yesterday was NOT short buildup (long) / NOT long buildup (short).
 R6 rsi2_dip + 1h hammer: R4 entry only after a 1-hour hammer / bullish engulfing on the next day (enter next candle).
N ∈ {3, 5} for R1/R2. No trade may span an NFO expiry (rollover window skipped). Full costs on the real price.
SHORTLIST (design < 2024-07-01): ≥ 100 trades, mean net > +0.05% per trade, > 0 at 2× costs, bootstrap p5 > 0.
PASS (hold-out ≥ 2024-07-01): ≥ 100 trades, mean net > 0 at 2× costs. Win rate reported (goal 80%), never the only test.
