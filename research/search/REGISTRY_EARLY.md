# EARLY-MOVE-001 (registered 23-Oct-2026, before running) – catch the stock BEFORE the 2-3% move (user request)
Signal only while the stock has NOT moved yet: |price vs today's open| < 1% at the signal candle's close.
Signal candles close at 10:15, 11:15, 12:15 or 13:15; first signal per stock per day per family.
Families (early signs):
 B1 quiet_spike   candle volume ≥ 2.5× normal for that hour, price still flat; direction = candle colour
 B2 coil_high/low close within 1% of the 20-day high (buy) / low (sell) and yesterday was NR7 or an inside day
 B3 level_break   first close above yesterday's high (buy) / below yesterday's low (sell), volume ≥ 1.5×
Filters (0–3): nifty (NIFTY up/down since open same way), oi (yesterday OI buildup same way), dtrend (daily EMA50 side),
 ema200, vwap (close on the trade side of VWAP), rsi (55–75 buy / 25–45 sell), strong (candle closes in top/bottom 25%).
Entry next candle open. Exits: X1 day close · X2 target +2% / stop -1% (price %), else day close · X3 target +3% / stop -1.5%.
Reported in plain terms: % per trade after costs, ₹ per lot after costs, win %, and % of trades that reached +2%.
SHORTLIST (design < 2024-07-01): ≥ 100 trades, net ≥ +0.10%, > 0 at 2× costs, p5 > 0.
PASS (hold-out ≥ 2024-07-01): ≥ 100 trades, net ≥ +0.05%, > 0 at 2× costs, ≥ 3 of 5 half-years positive.
