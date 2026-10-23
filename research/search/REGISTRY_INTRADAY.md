# INTRADAY-001 (registered 23-Oct-2026, before running) – fewer but accurate INTRADAY calls
Universes:
- STOCKS: 181 NSE stock futures (lot < 3000), 1-hour candles Jul-2022 → Oct-2026, plus daily OI.
- MCX: crude, natural gas, gold, silver, copper, zinc, aluminium, 1-hour candles.
Every trade is entered and exited the SAME day: next 1-hour candle open, stop checked first, exit at the target or the
session close. Full costs + slippage (stocks: brokerage/STT/exchange/stamp/GST + 0.03%/side; MCX: research/instruments).
Families (long version; short = mirror), fixed parameters:
 D1 orb_trend      first-hour range breakout after the first hour, close beyond it, volume > 1.5× same-hour average,
                   daily trend agrees (prev close vs daily EMA50); stop = other side of the first-hour range
 D2 gap_hold       gap ≥ 1% in the daily-trend direction and the first hour closes beyond the open; stop = first-hour low
 D3 pdh_break      1-hour close beyond yesterday's high, volume > 1.5× same-hour average, daily trend agrees; stop 1 ATR(1h)
 D4 vwap_pullback  daily uptrend, price above VWAP, a candle touches VWAP after 11:15 and closes back above; stop 1 ATR(1h)
 D5 oi_orb         D1 + yesterday was an OI long-buildup day (stocks only; short: short buildup)
 D6 dip_buy        daily uptrend, first-hour fall > 1.5 ATR(1h) and RSI(1h) < 30 → long, target = previous close
Targets for D1–D5: 1R and 1.5R. Selectivity is built in (one trade per instrument per day, filters above).
SHORTLIST on design (< 2024-07-01): ≥ 60 trades, ≥ +0.10R, PF ≥ 1.20, bootstrap p5 > 0, > 0 at 2× costs.
PASS on hold-out (≥ 2024-07-01, opened only for shortlisted): ≥ 60 trades, ≥ +0.05R, PF ≥ 1.10, > 0 at 2× costs.
Win rate is reported but is not a pass condition by itself.
