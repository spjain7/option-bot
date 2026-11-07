# MCXE-005 next research priorities (ordered)

1. **Fix the operational gaps around S4.** This is the highest expected value. It needs a separately approved production change, because MCXE-005 forbids one.
   - Run the scanner during market hours.
   - Make the clock-skew guard tolerant, or use the exchange timestamp.
   - Judge activation on the official open (or the first 09:15–09:20 bar) instead of whichever LTP the scan happens to see.
   - Three of the six recent S4 BUYs were cancelled for these reasons.
2. **Forward-log S4 as it is.** A one-year window cannot validate an EMA200 daily rule. Collect real forward outcomes, including the cancelled calls, for at least 30 trades on 20 dates before any judgement.
3. **Forward-log the closest MCXE-005 cells without alerting.**
   - The cells: fut_daily SELL `A_MACD_ZERO` and `A_EMA50_SLOPE` + ADX ≥ 20.
   - Their OOS was positive but the CI included 0.
   - New, untouched data is the only valid next test; re-tuning on this OOS is not.
   - Compare them against the all-SELL baseline to separate the edge from market drift.
4. **Use the same OI source in research and live.** Store Angel daily OI snapshots going forward, so research can replay what production actually saw (PETRONET: 1.88 % vs 2.42 %).
5. **Point-in-time F&O universe.** Rebuild the intraday stock lists from daily F&O membership to remove survivorship.
6. **Drop dead areas.**
   - Intraday price-pattern families on NSE cash, NSE futures and MCX showed no edge after costs: 0 BH-significant cells, and the median cell was below zero at 2× cost.
   - Deprioritise them unless there is a new information source (order flow, OI change intraday, options data).
7. **Regime awareness, as a hypothesis to pre-register.**
   - Daily breakout and trend rules were strong in DEV and negative in VALID.
   - A test of whether a simple market-level regime switch (for example, Nifty above or below its 50-day EMA) could separate the two must be pre-registered and tested on future data only.
8. **The two MCXE-004 PAPER_ONLY rules** (`RB_STK_3h_MACD0_SELL`, `RB_STK_3h_EMA921_SELL`): keep them in shadow logging and re-evaluate after 3 more months of forward data.
