# STRAT-SEARCH-002 – combination search with walk-forward selection (registered 22-Oct-2026, before running)
Question: if we keep picking the best COMBINATION of entry × filter × exit × stop × timeframe on past data, does the
pick make money on the NEXT, unseen period? (This measures the search process itself, so data-mining is paid for.)
- Universe: CRUDEOIL, NATURALGAS, GOLD, SILVER, COPPER, ZINC, ALUMINIUM, NIFTY, BANKNIFTY futures; one rule for all.
- Grid (540 combos): entry {Donchian 20/40/55 breakout, EMA 20/50 cross, EMA 10/30 cross, Supertrend 10/3}
  × filter {none, ADX>20, 200-EMA side, daily-trend agree, high-volatility regime}
  × exit {opposite signal, 3×ATR trailing, fixed 2R} × initial stop {2, 3 ATR} × timeframe {1h, 3h, 1d}.
- Fills next-candle open, stop first, gap fills, full costs + slippage, no trade across contract switches, max 60 candles.
- Walk-forward: train = previous 18 months, test = next 6 months; test windows 2024-H1 … 2026 (to Oct).
  Pick (a) the single best combo and (b) the top-5 combos (equal weight) by train expectancy (≥ 40 trades, PF ≥ 1.1).
- PASS (for the selection process, pooled over all test windows): ≥ 100 trades, ≥ +0.10R, PF ≥ 1.20, bootstrap p5 > 0,
  > 0 at 2× costs, positive in ≥ 3 of 5 test windows.
- If PASS, the combos picked in the LATEST window go to paper Telegram alerts – never to real orders.
