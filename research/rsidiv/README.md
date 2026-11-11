# RSIDIV – RSI 75 / 25 and divergence on NSE stock futures, index futures and cash (11-Nov-2026)

Research only. Nothing here sends an alert or changes production.

The engine (`engine.py`) uses the same signal definitions as the MCX study (`research/mcxhw/rsi_div.py`), so results can be compared across markets. Parameters are the same everywhere and are not tuned per instrument.

- **RSI(14) events at 75, mirrored at 25:** cross in, stay 5 bars, cross out, cross 70/30, reversal candle, volume exhaustion, near the 50-bar level, 5-bar break, EMA20 cross, RSI divergence. Each event is traded both as a reversal and as a continuation.
- **Divergence:** 12 indicators plus OI where verified OI exists, regular and hidden, plus 3 or 5 indicators at once. Pivots need K bars on each side (K = 3, or 2 on weekly bars), so a divergence is known only K bars after the swing. It is traded at the next open; the delay is recorded in the registry.
- **Trades:** stop beyond the 5-bar extreme plus 0.1 ATR, targets 1R / 2R / 3R, stop checked first, gaps fill at the open, one trade at a time per instrument. A futures trade held over an expiry pays one extra round trip.
- **Costs:** futures STT on the sell side by date (0.0125 % → 0.02 % from Oct-2024 → 0.05 % from 1-Apr-2026), exchange fees, stamp duty, GST, brokerage, and slippage of 0.03 % per side for stocks and 0.01 % for indices. Cash delivery costs 0.393 % per round trip.
- **Gate (PASS):** profit and PF ≥ 1.2 in each of the three periods, at least 30 trades in each and 100 in total.
- **Multiple testing:** t-statistic on the mean R per entry day (trades on the same day are not independent), with BH-FDR 10 % and Holm 5 % within each market study.
- **Benchmark per market:** entry every 10th bar with the same stop and target, which shows what market drift alone gives.

## Results

| Market (data) | Variants | PASS | PASS + FDR | Verdict |
|---|---|---|---|---|
| Stock futures, daily + weekly 2018–26 (351 stocks, verified bhavcopy OI, basis) | 5,874 | 50 | 4 (1 also Holm) | **1 shadow candidate** (below) |
| Index futures NIFTY / BANKNIFTY / FINNIFTY / MIDCPNIFTY, daily 2018–26 (OI) + 1h / 3h 2022–26 (no OI) | 5,096 | 2 | 0 | nothing |
| Cash, daily + weekly 2005–26 (984 stocks incl. delisted, BUY only) | 2,799 | 29 | 11 (1 also Holm) | **1 shadow candidate** (below); daily: 1 / 1,455 pass |

- **Stock futures:** classic RSI 75/25 reversals lose money. Divergence SELL loses money. OI divergence passes 0 of 72 daily tests and 3 of 72 weekly tests, all weak. The OI-up/OI-down and basis contexts do not lift results on their own (the median variant is negative with every context).
- **Index futures:** nothing survives. Daily and hourly results are close to the drift benchmark. Basis cannot be tested because index spot history is not stored.
- **Weekly BUY:** most passes are market drift. The weekly BUY benchmark alone makes +0.19R (stock futures) and +0.14R (cash) at 2R.

### Shadow candidate 1 – stock futures SELL, "short the first bounce after an oversold fall"
Rule: daily RSI(14) ≤ 25 at some point in the last 10 sessions, and today's close is above the prior 5-session high. SELL the future at the next open. Stop 0.1 ATR above the 5-session high, target 3R, at most 15 sessions.

Stress test (`sf_check.py`, `results/sf_check.json`):
- 1,019 trades, 34 % wins, +0.29R per trade (+0.43 % per trade), PF 1.40, day-clustered t 4.0.
- Periods: DEV +0.17R, VALID +0.41R, OOS +0.32R.
- Placebo: none of 300 random-entry draws reached it (their mean is −0.01R).
- Concentration: the top 10 stocks give 12 % of the profit.
- Slippage: +0.26R at 0.05 % per side, +0.20R at 0.10 % per side.
- Neighbours: RSI 25 with a 10–15-session look-back and a 5-session break is positive in every period; RSI 20 and RSI 30 are weaker.
- **Against it:** losing years 2019, 2020, 2023 and **2026 so far (−0.06R, 161 trades)**. Much weaker when the market is below its EMA200 (+0.15R, t 0.8). It does not clear a Bonferroni bar for everything tried across all markets.

### Shadow candidate 2 – cash BUY, weekly RSI ≥ 75 in less-liquid eligible stocks
Rule: the weekly RSI(14) crosses above 75, and the stock is in the bottom third of that week's eligible stocks by turnover (still ≥ ₹25 cr a day). BUY at Monday's open. Stop 0.1 ATR below the 5-week low, target 1R, at most 10 weeks.

Stress test (`cash_check.py`, `results/cash_check.json`):
- 814 trades, 57 % wins, +0.14R per trade (+2.6 % per trade), PF 1.48, t 4.1.
- Periods: DEV +0.16R, VALID +0.10R, OOS +0.15R.
- Placebo: 0 of 300 draws reached it.
- Slippage: survives 0.3 % per side (+0.11R).
- Neighbours: RSI 70 / 75 / 80 and any liquidity cut stay positive in most cells.
- **Against it:** it only works when the market is above its 40-week EMA (+0.16R over 765 trades, versus −0.08R over 49 trades below it). Losing years: 2022 (−0.30R), 2025, 2018, 2008. It is the same momentum effect as the live monthly momentum portfolio, so it adds little that is new.

Neither candidate is promoted. "Shadow" means recording signals internally against real prices without sending them, which needs the owner's approval to build.

Files: `results/*_variants.csv` (every variant, including failures), `results/*_trades.csv.gz` (trade by trade for the passes and the 25 best by t), `results/*_check.json`, `results/*_check_trades.csv.gz`.

**Data notes:**
- Stock-futures price indicators use the adjusted cash series, because futures history has unadjusted split jumps.
- OI is the sum over live expiries divided by the cumulative corporate-action factor.
- Basis is the near future close divided by the unadjusted cash close, minus 1; its median is +0.22 %.
- Index daily series are ratio back-adjusted at each roll. Untraded rows (open = 0) were dropped. FINNIFTY starts in Jul-2021 and MIDCPNIFTY in Jul-2023 because earlier contracts were too thin.
- Sector for cash uses today's NIFTY 500 industry list, so 529 of 997 stocks have a sector; delisted stocks have none.
