# Pre-registered test plan and pass/fail criteria

Written **before** running the full-universe backtests (21-Oct-2026). Results must be judged against this
file as it stands in the commit that introduced it; later edits must be logged at the bottom.

## Honest disclosure: what has already been looked at
Earlier in this project (commit `2c2533b`) I already inspected, on Yahoo proxy data:
- Strategy A (hourly breakout) on GOLD, SILVER, CRUDEOIL, NATURALGAS, COPPER, ALUMINIUM, May-2024 → Oct-2026,
  split at 1-Oct-2025, plus 9 variants of it.
- Daily Donchian 20/10 (B), 55/20 + 200-day filter (C) and 3 other daily variants on GOLD, SILVER, CRUDEOIL,
  NATURALGAS, COPPER, 2005-2026, split at 1-Jan-2018, plus 15 parameter neighbours of C.

So **every commodity period is already "seen"**. Strategy C's parameters (55/20, 2 ATR) are the classic published
Turtle values, but I chose to promote C *after* seeing 2018-2026. Commodity results can therefore never reach
**PASS**; the best possible grade for any commodity result is **PAPER-CANDIDATE**.
Index futures (NSE) data had **not** been inspected before this plan. Variants inspected before this plan: **30**.

## Data grades
- **REAL**: NSE F&O bhavcopy (contract level, daily OHLC, volume, OI), Angel One contract candles.
- **PROXY**: Yahoo international futures for MCX commodities (continuous front month, *not* back-adjusted,
  roll dates unknown), Yahoo cash index for hourly index tests. Proxy results can at most be PAPER-CANDIDATE.

## Periods (chronological, fixed now)
| Universe | Train | Validation | Out-of-sample (OOS) |
|---|---|---|---|
| NSE index futures, daily (REAL) | 2011-01-01 → 2016-12-31 | 2017-01-01 → 2020-12-31 | 2021-01-01 → end |
| MCX commodities, daily (PROXY) | 2005-01-01 → 2012-12-31 | 2013-01-01 → 2017-12-31 | 2018-01-01 → end *(already seen)* |
| Hourly, all (PROXY, last ~730 days) | first 50% | next 25% | last 25% *(commodities already seen)* |
| MCX via Angel (REAL, only live contracts) | — | — | descriptive sanity check only (too short to grade) |

Walk-forward: anchored, yearly. For each test year Y, the parameter set with the best train expectancy among the
neighbour grid (data < Y) is applied to year Y. The stitched WF result is reported.

## Strategies (fixed list)
A hourly breakout (= live Engine C rules) · B Donchian 20/10, 2 ATR stop · C Donchian 55/20 + 200-day SMA filter,
2 ATR stop · D = C + RSI(14) block (no BUY if RSI > 70, no SELL if RSI < 30) · E = C + volume ≥ 1.5 × 20-day average
· F = C + rising open interest (total OI today > 5 days ago; REAL OI only = NSE indices) · G = C + regime filter
(ADX(14) ≥ 20 and ATR% within 10th-90th percentile of the past 252 days) · H1 = C+D+G · H2 = C+E+G ·
H3 = C+F+G (indices) · H4 = C+D+E · I (index-specific adaptation, tested separately) = C long-only.

Neighbour grid for stability: entry {40, 55, 70} × exit {15, 20, 25} × stop {1.5, 2.0, 2.5} ATR (27 sets, applied with
each strategy's own filters); for B: entry {15, 20, 25} × exit {7, 10, 13}; for A: breakout {3, 5, 8} × ADX {15, 20, 25}.

## Execution model
Signals use closed candles only. Daily: signal at close of day t → order at open of day t+1 on the actual front contract.
Stops are intraday on the held contract (gap through stop → fill at the open). Channel exits are decided at the close
and filled next open. Same bar stop and target → stop first. Rolls N trading days before expiry (NSE 3, MCX 5) at
the close, both legs costed. Costs = current statutory charges + brokerage ₹20/order + slippage (registry), applied
to all history. Hourly: signal at bar close → next bar open, square-off rules as in the live engine.

## Pass / fail criteria (OOS, after costs, group portfolio of the strategy)
Core:
1. Expectancy > **+0.10 R** per trade.
2. Bootstrap (5 000 resamples) **5th percentile** of mean R > 0.
3. At least **50 trades** in the group (20 per instrument to be named individually).
4. Profit factor ≥ **1.20**.
5. Still positive expectancy at **2× costs**.
Secondary:
6. Validation-period expectancy > 0 **and** ≥ 60% of OOS calendar years positive.
7. ≥ 70% of neighbour parameter sets have positive OOS expectancy.
8. Anchored walk-forward expectancy > 0.
9. Max drawdown ≤ 25 R.

Grades: **PASS** = REAL data, clean OOS, all 9 met. **PAPER-CANDIDATE** = all core met and at most one secondary
missed, or all met on proxy / already-seen data. **FAIL** = anything else. A positive total return alone never passes.

## Change log
- 21-Oct-2026, before any index or Angel results were looked at: Angel One turned out to serve a vendor-stitched
  **front-month** history on the nearest contract's token (checked against NSE bhavcopy: identical close to the front
  contract on 96% of days; it switches at expiry and is NOT back-adjusted). Added groups MCX_DAILY_REAL,
  MCX_HOURLY_REAL and INDEX_HOURLY_REAL from this series, graded **REAL-UNADJ** (real prices, but roll jumps remain
  in the series, so it cannot reach PASS). Their periods are proportional: first 50% train, next 25% validation,
  last 25% OOS. Hourly groups use the same proportional rule. Commodity markets stay "already seen".
  Added a bias check: strategy B/C on Angel's unadjusted NIFTY/BANKNIFTY vs the back-adjusted bhavcopy series.
- Proxy costs: charged as the MCX cost *fraction* at today's MCX-equivalent price (proxy price × USD/INR × unit
  conversion), because MCX point costs cannot be applied to USD prices.
