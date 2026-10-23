# OPT-BUY-001 – can option BUYING win? (registered before running)

Research only. Nothing here changes the live selling bot.

**Question:** which entry signals and exit rules make buying an at-the-money option profitable after costs, on real
MCX (crude, natural gas, gold, silver, copper, zinc, aluminium) and NIFTY / BANKNIFTY hourly data, Jul-2022 → Oct-2026?

**Option model (no free option-price history exists):** Black-76 ATM option on the futures price.
- IV = 20-day realised volatility (daily closes, before the signal day) × 1.15, floor 10%; kept constant during the trade.
  Sensitivity: × 1.0 and × 1.3, and an "IV crush" case where the exit IV is 10% lower than the entry IV.
- Days to expiry at entry: 7 and 20 (both reported). A trade is closed before expiry.
- Costs per round trip, as a share of the premium: 2 × bid-ask half-spread (index 0.5%, MCX 2% each side) + 0.5% brokerage and taxes.
  Stress test at 2× costs.

**Entries** (textbook settings, not tuned; signal on a completed candle, entry at the next candle's open; long = buy CE,
short = buy PE; no signal on a contract-roll day; trades closed before a roll):
1. Volume breakout: close beyond the previous 20-candle high/low and volume > 1.5× its 20-candle average.
2. Donchian breakout: the same without the volume condition.
3. Squeeze breakout: Bollinger(20, 2) width at its lowest of 120 candles within the last 5 candles, then a close outside the band.
4. Momentum candle: range > 2 × ATR(14) and close in the outer 25% of the candle.
5. Control: random entries (same number as entry 1, random direction, fixed seed).

Timeframes: 1-hour, 3-hour, daily.

**Exits:**
- X1 underlying: 2 ATR stop, 3 ATR trailing stop, maximum hold of 40 / 30 / 15 candles.
- X2 premium: −40% stop, +100% target, time stop after 10 / 6 / 5 candles.
- X3 fast-or-out: −35% stop; exit if not up at least 20% after 3 candles; once up 50%, exit if it falls back to +20%;
  time stop as in X2.

**Pass rule (fixed now):**
- At least 60 trades in each half (before / after 1 Jul 2024).
- Average return per trade positive at 2× costs in **both** halves.
- Bootstrap 5th percentile of the average above 0.
- Better than the random control in both halves.
- Still positive without its 10 best trades.

A pass makes a PAPER-CANDIDATE only. It must then be tracked with real option prices before any live alert.
