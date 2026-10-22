# STRAT-SEARCH-001 (registered 22-Oct-2026, before any result was seen)
Goal: find a rule that survives costs on data it was not chosen on. "Perfect" does not exist; the aim is *robust*.
- Universe: CRUDEOIL, NATURALGAS, GOLD, SILVER, COPPER, ZINC, ALUMINIUM, NIFTY, BANKNIFTY futures (Angel, front month).
- Timeframes: 1h, 3h, 1d (from 1h, Jul-2022 →), 15m (crude only, Oct-2020 →).
- Candidates (textbook parameters, no tuning): Donchian 20/10, EMA20/50+ADX, Supertrend 10/3, RSI(2) Connors,
  Bollinger mean-reversion with 200-EMA filter, MACD zero-cross with 200-EMA filter, trend-pullback RSI 40/60,
  inside-bar breakout with trend, opening-range breakout 30m (crude 15m), and the live RSI-reversal alert rule.
- Execution: next-candle open, ATR stops checked first, gap fills, full charges + slippage, no trade across a contract switch.
- Design period < 2024-07-01. Shortlist (pooled over instruments): ≥ 60 trades, ≥ +0.10R, PF ≥ 1.20, bootstrap p1 > 0,
  > 0 at 2× costs, positive in ≥ 60% of instruments (≥ 5 trades).
- Hold-out ≥ 2024-07-01, opened only for shortlisted rules. PASS: ≥ 40 trades, ≥ +0.05R, PF ≥ 1.10, > 0 at 2× costs.
- Caveat: parts of 2024-26 were viewed in earlier experiments for OTHER rules (crude intraday/RSI reversal).
- Nothing is deployed automatically.
