# BIG-MOVE-001 (registered 23-Oct-2026, before running) – catch the stocks that make big intraday moves
Exploratory finding that motivated this test (seen on ALL data, so not proof): when a stock's first hour (9:15–10:15)
moves ≥ 3% on > 2× normal volume, following it to the close earned +0.22%/trade after costs (+0.47% in 2022-24,
+0.08% in 2024-26). This test tries to make it stronger and decides on the untouched period only.
Universe: 181 stock futures (lot < 3000), 1-hour candles. Rollover window skipped. Full costs on the real price.
Base: |first-hour return vs open| ≥ M (1.5 / 2 / 3 %) and first-hour volume ≥ V × normal (1.5 / 2 / 3).
Filters (0–3 combined): nifty (NIFTY first hour same direction), oi (yesterday OI buildup same direction),
 dtrend (yesterday close vs daily EMA50 same side), ema200 (vs daily EMA200), gap (opening gap ≥ 0.5% same direction),
 nr7 (yesterday = narrowest range of 7 days), pdh (first-hour close beyond yesterday's high/low),
 strong (first-hour close in the top/bottom 25% of its range), rsi_ok (1h RSI not > 85 for buys / < 15 for sells).
Entries: E1 10:15 open · E2 break of the first-hour high/low later the same day (stop order, fill at worse of open/level)
 · E3 pull-back to the first-hour midpoint before 13:15 (limit).
Exits: X1 day close · X2 stop at the other side of the first hour + day close · X3 X2 + trailing stop 1 ATR(1h) from best
 close · X4 X2 + target 2× risk.
SHORTLIST (design < 2024-07-01): ≥ 100 trades, net ≥ +0.10%/trade, > 0 at 2× costs, bootstrap p5 > 0.
PASS (hold-out ≥ 2024-07-01): ≥ 100 trades, net ≥ +0.05%/trade and > 0 at 2× costs.
Many combinations are tested → some design winners will be luck; only PASS rules are candidates for alerts.
