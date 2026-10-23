# EMA-X-001 (registered 23-Oct-2026, before running) – EMA crossover + volume + OI + false-trade filters
Universes: STOCKS first (181 futures, 1h), then INDEX (NIFTY, BANKNIFTY), MCX (7). 1-hour candles Jul-2022 → Oct-2026.
Signal: fast EMA crosses slow EMA on a closed 1h candle. Pairs: 5/13, 9/21, 20/50.
False-trade filters (flags at the signal candle, tested in all combinations of 0–3):
 vol      cross-candle volume > 1.5× same-hour average
 oi       yesterday's OI buildup in the trade direction (stocks only)
 trend    price on the trade side of EMA200 (1h)
 dtrend   yesterday's daily close on the trade side of daily EMA50
 adx      ADX(14, 1h) > 20 (avoid sideways chop – the main source of fake crosses)
 rsi      RSI(1h) 50–70 for buys / 30–50 for sells (momentum, not stretched)
 body     cross candle closes in the top (buy) / bottom (sell) 30% of its range
 confirm  the NEXT candle also closes beyond the cross-candle high (buy) / low (sell); entry after it
Entry next candle open. Exits: X1 same-day stop 1.5 ATR / target 2 ATR / day-close exit; X2 same-day stop 1 / target 1 ATR;
X3 (stocks) swing: stop 2 ATR, exit on the opposite cross, max 35 candles, never across an expiry.
Full costs. SHORTLIST (design < 2024-07-01): ≥ 100 trades, exp ≥ +0.05R, PF ≥ 1.1, p5 > 0, > 0 at 2× costs.
PASS (hold-out ≥ 2024-07-01): ≥ 60 trades, exp > 0 at 2× costs. Win rate reported.
