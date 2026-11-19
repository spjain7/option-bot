# Research cycle 2 (11-Nov-2026)

Research only. Both shadow candidates run unchanged. Nothing is promoted, changed or merged into production.

The labels used are REVERSAL BUY, REVERSAL SELL, CONTINUATION BUY and CONTINUATION SELL.

## 1 · CONTINUATION BUY: why it is the strongest RSI family, and which filters add edge (`cont_buy.py`)

**Base events and exits:**
- B1: RSI crosses to ≥ 75. B2: the S10 rule (RSI ≥ 75, ADX ≥ 25, close above EMA50, 20-bar breakout).
- Next-open entry, structure stop, 2R target (3R also reported), real costs.

**Protocol:**
- 18 pre-registered filters, each added one at a time to the base (no stacking).
- A filter is "selected" if it beats the base in both DEV and VALID.
- Out-of-sample evidence: OOS result of the filtered set compared with both the base and the trades the filter removed.
- Walk-forward by year, and BH-FDR across all 516 tests.

**Why the family is the strongest.** The base beats the "enter every 10th bar" drift benchmark in most markets:

| Market / TF | Base B1, DEV / VALID / OOS | Drift benchmark, DEV / VALID / OOS |
|---|---|---|
| MCX 1h | +0.01 / +0.10 / +0.21 | −0.08 / +0.04 / −0.01 |
| MCX 3h | +0.25 / +0.22 / +0.06 | +0.03 / +0.20 / −0.02 |
| Index 1h | +0.25 / +0.56 / +0.39 (131 trades) | +0.02 / −0.24 / −0.38 |
| Stock futures 1d | −0.01 / +0.13 / −0.01 | +0.03 / +0.04 / −0.09 |
| Stock futures 1w | +0.05 / +0.56 / +0.06 | +0.19 / +0.23 / +0.00 |
| Cash 1w | +0.12 / −0.02 / +0.20 | +0.11 / −0.01 / +0.12 |

- Momentum persistence after a strong push is real on MCX (especially metals) and index 1h.
- On stock futures and weekly cash, most of the result is market drift.
- REVERSAL strategies trade against this same persistence, which is why they lose (see the RSIREV study).

**Filters:**
- **No filter passes the multiple-testing control** (0 of 516).
- 111 tests were selected on DEV and VALID; 58 of those also improved OOS. That is about what chance gives when a filter is mildly informative.
- The most consistent filters:
  - **Relative volume ≥ 2×:** OOS better than the base in 14 of 18 cells, +0.10R on average; walk-forward better in 10 of 18. MCX 1h B1: +0.11 / +0.23 / +0.36 against base +0.01 / +0.10 / +0.21.
  - **Market above EMA200:** a small improvement in 12 of 12 cells.
  - **MCX breadth** (≥ 4 of 7 commodities above their daily EMA50): helps MCX 1h.
- Do not help on average: higher-timeframe alignment, EMA stack, stock relative strength (top 30 %), and the confirmation entry (fewer trades, same R).

## 2 · Stock-futures CONTINUATION SELL (SF-CONT-SELL-v1 unchanged; variants are separate versions) (`sf_crowd.py`)

R per trade on two bases: research (adjusted cash prices) and real futures prices.

| Version | Research basis: all / DEV / VALID / OOS / 2026 | Futures basis: all / OOS / 2026 |
|---|---|---|
| v1 (shadow) | +0.29 / +0.17 / +0.41 / +0.32 / **−0.06** (1,019) | +0.20 / +0.21 / **−0.08** |
| v2a-3 skip days with ≥ 3 signals | +0.33 / +0.43 / +0.27 / +0.27 / +0.27 (379) | +0.28 / +0.24 / +0.23 |
| v2a-5 skip days with ≥ 5 signals | +0.29 / +0.18 / +0.39 / +0.33 / +0.10 (573) | +0.17 / +0.20 / −0.02 |
| v2a-8 skip days with ≥ 8 signals | +0.20 / +0.03 / +0.27 / +0.30 / +0.03 (752) | +0.10 / +0.10 / −0.13 |
| v2b-cap4 at most 4 a day, most liquid | +0.30 / +0.17 / +0.39 / +0.36 / +0.24 (785) | +0.19 / +0.23 / +0.21 |

**Crowding is not monotonic.** R by number of signals that day (research / futures basis):

| Signals that day | Research | Futures |
|---|---|---|
| 1–2 | +0.40 | +0.34 |
| 3–4 | +0.12 | −0.18 |
| 5–7 | −0.03 | −0.07 |
| 8+ (market-wide bounce days) | +0.45 | +0.42 |

- Days with 5+ signals lost in 2020, 2021, 2023 and 2026, but won in 2018, 2022, 2024 and 2025.
- **The pre-registered ≥ 5 congestion filter does not help on real futures prices** (+0.17R vs +0.20R).
- The cap-4 and skip-≥3 versions look better, but they were motivated by the 2026 losses. That makes them hypotheses for a later forward test, not evidence.

**2026:**
- It is unusual: only 0.3 % of bootstrap years drawn from 2018–25 trades are as bad.
- The market-move mix of 2026 would have predicted +0.30R, so the regime does not explain it.
- 63 % of 2026 trades came from crowded days, against 47 % in 2018–25.
- Gross R in 2026 is about 0, so the signal itself stopped working, and the higher STT adds about 0.03R of cost per trade.

**Futures execution gap (−0.085R per trade):**
- On 71 % of trades the futures and cash exits fall on the same day, and the gap is about 0.
- On the other 29 % the gap averages −0.30R: the futures price touches the stop when cash does not, because of basis noise and different highs and lows.
- Fees (0.02R) and slippage (0.035R) are already in the research cost, so they are not the gap.

## 3 · Cash CONTINUATION BUY (CM-CONT-BUY-v1 unchanged) (`cash_cm.py`)

| Condition at the signal | Inside: R, OOS R | Outside: R, OOS R | OOS t |
|---|---|---|---|
| Momentum rule's MA100 market filter on | +0.17 (740), +0.18 | −0.10 (74), **−0.41** | **4.28** |
| Market above EMA200 | +0.16 (764), +0.16 | −0.06 (50), −0.30 | 1.97 |
| Breadth > 50 % | +0.16 (727), +0.17 | +0.02 (87), −0.09 | 2.17 |
| Sector above its EMA50 | +0.24 (510), +0.27 | +0.08 (25), +0.02 | 1.26 |
| Sector RS top half / stock RS top 30 % | about equal inside and outside | | n.s. |

- **It depends on the bullish market filter.** Outside the MA100 filter it loses (−0.41R OOS, t 4.3).
- **No independent portfolio value against the live monthly momentum rule:**
  - Correlation 0.37; alpha +0.12 % a month (t 0.85) in 2016–26.
  - An equal-volatility blend has a Sharpe of 1.17, against 1.23 for momentum alone.
  - Restricting CM to the MA100 filter (separate version CM-v2a) raises the alpha to t 1.18, and the blend only matches momentum alone (Sharpe 1.23).
- **Capacity:** up to 31 open positions; 20 at the 95th percentile, which is ₹1 crore at ₹5 lakh each.

## 4 · MCX: continuation by objective daily trend, metals vs energy (`mcx_trend.py`)
Trend is taken from the previous completed day: down = close < EMA50 and EMA50 falling over 10 sessions. The results below exclude the last 3 sessions before a contract switch and use real costs.
- **CONTINUATION BUY on 3h works in metals in an uptrend, not in energy:**
  - B1, metals, uptrend: +0.67 / +0.35 / +0.32R over 114 trades, t 3.35. Gold +0.53R, silver +0.70R, zinc +0.56R.
  - Energy: crude −0.02R, natural gas +0.02R.
  - It passes FDR within this study but not a Bonferroni bar for the ~40,000 MCX variants tried (t 4.7 needed).
  - In a downtrend, CONTINUATION BUY loses on 3h.
- **1h CONTINUATION SELL (S9) in a downtrend:**
  - +0.27 / +0.30 / +0.29R over 142 trades; it passes the period gate, but t is only 1.57.
  - Metals +0.32R (92 trades); energy +0.17R in DEV but −0.21R OOS (6 trades).
  - It holds with no late entries (+0.36R OOS).
  - Too small to act on.

## 5 · Depth
Validation runs on the first saved file of 11-Nov (`depth_check.py`); results are in `results/depth_check.json`. No strategy uses depth.

## 7 · Statistical control
- All tests are in the registry (44,134 rows), failures included.
- Each study applies BH-FDR. Stock-futures and cash tests use t-statistics on the mean R per entry day, because trades on the same day are not independent. Walk-forward is used for filters, and every result is compared with a drift benchmark.

## 8 · Configuration
`research/config/strategy_configs.json` lists every market × strategy × timeframe configuration. All use shared defaults; no instrument-level override has enough evidence.
