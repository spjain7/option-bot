# Research cycle 3 (11-Nov-2026)

Research only. Nothing is promoted. Both shadow candidates run unchanged.

## 1 · Relative volume ≥ 2× on CONTINUATION BUY (separate version CONT-BUY-B1-RVOL2-v1) – `rvol.py`

| Market / TF (2R) | Base OOS R | Version OOS R | OOS kept vs dropped | Years better | Instruments better | Dose 1.5× / 2× / 2.5× / 3× (all-period R) |
|---|---|---|---|---|---|---|
| MCX 1h | +0.21 | +0.36 | +0.44 vs +0.06 (t 1.53) | 4/5 | 5/7 | +0.18 / +0.22 / +0.24 / +0.18 |
| MCX 3h | +0.06 | +0.27 | +0.35 vs −0.08 (t 1.03) | 3/4 | 6/7 | +0.34 / +0.40 / +0.79 / +0.76 |
| Stock futures 1d | −0.01 | +0.03 | −0.06 vs +0.02 | 5/9 | 79/136 | flat |
| Stock futures 1w | +0.06 | +0.23 | +0.22 vs +0.04 (t 1.15) | 4/9 | 1/4 | flat |
| Index 1h | +0.39 | +0.57 | +0.29 vs +0.44 | 3/5 | 2/3 | rising, 131 trades |
| Cash 1d / 1w | +0.03 / +0.20 | +0.05 / +0.21 | about equal | 14/21 / 6/21 | about half | flat |

- **It does not pass any multiple-testing check:** 0 of 18 cells pass Holm or BH.
- **Pooled across all markets, it adds nothing:** OOS kept-minus-dropped is −0.014R, with a permutation p of 0.53.
- **The only consistent effect is on MCX 1h and 3h:** it is better in most years and most commodities, with a rising dose response at 3h. In falling markets the 3h gain is smaller (+0.11R vs +0.37R), and below the instrument's own EMA200 the 1h version loses.
- **No forward evidence exists.** A forward test would need an intraday MCX shadow ledger, built from the 1-minute bars production already saves to `ws-bars`. That ledger is not built yet.

## 2 · Stock futures: the 0.085R execution gap of SF-CONT-SELL-v1 (v1 unchanged) – `sf_gap.py`
Every executed trade was rebuilt on the actual contract, with raw and adjusted cash prices and basis at entry, close and the stop-day high. Daily bars only; no intraday futures history or historical depth exists.
- **Where the gap is:**
  - 658 of 930 trades exit on the same day on both bases; the gap there is +0.003R.
  - The 272 trades with different exits carry all of it (−0.30R each).
  - In 119 of them the futures stopped out first, costing −130R in total.
  - In 80 the cash stopped out first, adding +65R back.
- **Causes of the 119 futures-first stops:**

| Cause | Trades | Total R | Median basis rise to the stop-day high |
|---|---|---|---|
| The premium widened (futures basis rose, at the close as well) | 83 | −83.7R | +0.67 % |
| Expiry / roll inside the trade | 24 | −42.5R | +0.68 % |
| Corporate action inside the trade | 6 | −3.9R | |
| Futures-only intraday spike | 3 | −0.4R | |
| Tiny noise | 3 | +0.1R | |

- **Mechanism:** the strategy SELLS after a fall, often when the future trades at a discount to cash. When the discount closes, the future rises about 0.7 % more than cash. With a median stop of only 1.76 %, that is enough to hit the futures stop while cash stays 0.36 % below it.
- **The gap depends on the basis at entry:** about −0.53R when the future starts at a discount below −0.5 %, and about +0.76R when it starts at a premium above +1 %.
- **Decision-time basis** (futures close vs raw cash close on the signal day):

| Basis at signal | Trades | Futures R | Gap |
|---|---|---|---|
| ≤ −0.3 % | 79 | −0.07R | −0.24R |
| −0.3 % to 0 | 177 | +0.28R | −0.12R |
| 0 to +0.3 % | 386 | +0.27R | −0.10R |

  A "skip if discount ≤ −0.3 %" filter (SF-CONT-SELL-v2c) is a hypothesis only: the sample is small (79), and it would need its own version and a forward test.
- **Known limitation:** the shadow engine's `basis_pct` field uses the adjusted cash close. That is correct for forward days, but would be wrong for past days after a later corporate action. Research above uses raw prices.

## 3 · MCX 3-hour CONTINUATION BUY: gold, silver, zinc, benchmarks, untouched data – `mcx_metals.py`
The untouched window is Jul-2022 to the start of each commodity's 5-minute data (Nov-2022 to Sep-2023). It uses Angel hourly bars; on overlapping dates, 3-hour bars built from hourly match those built from 5-minute exactly.

| 2R, all trends | DEV | VALID | OOS | UNTOUCHED | All |
|---|---|---|---|---|---|
| B1 metals | +0.35 (64) | +0.31 (56) | +0.24 (36) | **−0.01 (28)** | +0.31 (156) |
| B1 energy | −0.26 | −0.15 | −0.33 | +0.66 (11) | −0.25 (42) |
| B1 gold / silver / zinc | +0.74 / +1.10 / −0.49 | +0.70 / +0.55 / −0.34 | +0.19 / +0.06 / +0.70 | −0.19 / −0.10 / +1.56 | +0.62 / +0.67 / −0.04 |
| Benchmark: 20-bar breakout, metals | +0.24 | +0.39 | +0.17 | **+0.31 (83)** | +0.27 (478) |
| Benchmark: higher low, metals | +0.15 | +0.49 | +0.14 | −0.08 | +0.25 (689) |
| Benchmark: EMA20/50 cross, metals | +0.22 | +0.68 | +0.25 | +0.37 | +0.36 (190) |
| Drift (every 8th bar), metals | −0.04 | +0.24 | +0.08 | −0.10 | +0.06 |

- **The RSI rule adds nothing over a plain trend-following entry in metals:** a 20-bar breakout or an EMA cross does as well or better, and holds up in the untouched window where B1 does not.
- **The effect is "metals trended upward in 2023–26", not RSI.**
- **Per-commodity samples are 28–42 trades, too small to tune.** Gold and silver were strong before 2026, weak in OOS and negative in the untouched window. Zinc is the opposite.
- **Energy is negative.**

## 4 · Index futures 1h: more data
- **Why it is short:** Angel's front-month hourly index history was fetched with a self-imposed 4-page limit (about 4.3 years, from Jul-2022).
- **The fix:** a page-limit override was added on the research branch, together with the quiet-hours guard.
- **When it runs:** the fetch is scheduled for tonight 00:40 IST, outside live hours.
- **How the result will be used:** if older data comes back, it will be used only as an untouched window. No threshold changes and no lower standards.

## 5 · Cash
No further work on CM-CONT-BUY-v1. Its shadow log is unchanged.

## 6 · Depth
`research/cycle2/depth_check.py` is extended with:
- a per-instrument data-quality score (0–100), made of coverage of session minutes, both sides present, five levels, not stale, receive lag ≤ 5 s, and ordered / monotonic books;
- median spread by hour;
- the distribution of top-5 imbalance.

It runs once the first `ws-depth` file is saved (when the morning job ends, around 14:50 IST). It was smoke-tested on synthetic recorder output.

## 9 · New strategy families (`research/families/run.py`) – 124 tests, **0 pass, 0 survive FDR**
- **MCX 15-minute intraday:** every family loses after costs (−0.06 to −0.32R). The drift benchmark is −0.25R, because costs are large relative to 15-minute ranges.
- **MCX 1-hour:**
  - VWAP reclaim BUY: −0.02 / +0.17 / +0.18R.
  - Sweep + structure-shift BUY: −0.01 / +0.08 / +0.11R.
  - Both fail in DEV.
- **Index 1-hour:** all negative or about 0.
- **Stock futures and cash daily:** all about 0 or negative. Support/resistance retests are worst in cash (−0.24R).
- **RS / sector rotation (cash, monthly):** CAGR 10.4 % / −0.9 % / 27.3 % (DEV / VALID / OOS). The live momentum rule made 21.0 % / 1.7 % / 37.4 % over the same periods; correlation 0.62. Worse in every period.

## 8 · Registry
- 44,776 rows, each with an `evidence_stage` column: BACKTEST (DEV/VALID in-sample, OOS held-out), BACKTEST with an untouched window, or FORWARD SHADOW (live).
- The forward rows come straight from the `shadow-state` ledgers: 0 forward signals so far, because the first nightly run is 11-Nov at 21:47 IST.
- The configuration register is updated; there are still no per-instrument parameters.
