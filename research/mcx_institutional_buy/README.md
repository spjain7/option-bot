# MCX Institutional BUY Research Engine – final report (12-Nov-2026)

Research only, on branch `research/mcx-institutional-buy`.
- No production file changes. The only edit outside this folder is one `.gitignore` line.
- No alerts, no orders.
- Backtested results are not a forecast of future profits.

Reproduce everything in this order:

```
python -m research.mcx_institutional_buy.data_quality.run
python -m research.mcx_institutional_buy.backtesting.stage1            # stage 1, all timeframes
python -m research.mcx_institutional_buy.strategy_combinations.run     # stages 2-4 + owner hypotheses A-J
python -m research.mcx_institutional_buy.strategy_combinations.mtf     # multi-timeframe configurations
python -m research.mcx_institutional_buy.strategy_combinations.score   # stage 5 score models
python -m research.mcx_institutional_buy.statistical_validation.run    # validation + labels
python -m research.mcx_institutional_buy.walk_forward.run
python -m research.mcx_institutional_buy.statistical_validation.modules
python -m research.mcx_institutional_buy.statistical_validation.commodity_specific
python -m research.mcx_institutional_buy.shadow_tracking.run 45        # research signal list, sends nothing
python -m pytest research/mcx_institutional_buy/tests -q               # 19 tests
```

Every experiment is appended to `reports/experiments.jsonl`. Each record holds the id, code version, feature hash, data version, split, configuration and counts.

## 1. Executive summary

**Scale:**
- 11,451 tests and 8.53 million simulated BUY trades.
- 7 commodities on 15m, 30m, 1h, 4h and 1d bars, plus Lead on daily. Nickel had no tradable history.
- Real MCX fees, and per-commodity slippage taken from the live MCX order book.

**Headline findings:**
- **No 60–70 % win-rate strategy survives as profitable on every test.** The best validated rules win 45–70 % of trades out-of-sample with +0.3 to +0.8R per trade. They are thin samples (53–107 OOS trades), and none clears the Deflated Sharpe Ratio test at 0.90 after about 2,000 trials per timeframe.
- **Eight rules are labelled OOS VALIDATED.** Each passed TRAIN 2022-07→2024-06, VALID 2024-07→2025-06 and OOS 2025-07→2026-10 with PF ≥ 1.2 in each. Each beat its matched random-entry baseline in all three periods, was BH-FDR significant on OOS, and had a bootstrap excess CI above zero.
  - Six are on 4h and two on 1h.
  - All are **trend / continuation or confirmed reversal inside an uptrend**: RSI crossing above 75, hidden bullish MACD divergence, and a previous-day-low sweep followed by a lower-high break and retest.
  - **None is an "early" countertrend reversal.**
- **The edge lives in metals (gold, silver, copper, zinc, aluminium) in uptrends.** Natural gas loses on 7 of 8 candidates, and crude is about flat.
- **Most "institutional" ideas did not beat the controls:**
  - Liquidity sweeps on their own, order-flow style volume proxies, OI states, candlestick patterns, support zones, global benchmark confirmation, and early RSI-25 reversals.
  - All ten pre-registered owner hypotheses (A–J): 0 of 227 tests pass.
  - Daily-chart sweep entries look strong (+0.36R OOS). A buy-stop above **any random bar's** high does about the same, so the sweep adds nothing.
- **15m and 30m fail because of costs.** The average round-trip cost is 0.42R per trade on 15m and 0.29R on 30m, against 0.09R on 4h.
- **Status:** none is promoted. 0 SHADOW CANDIDATE labels (DSR < 0.90 for all). Recommendation (section 20): shadow-track the top 3 on paper.

## 2. Data-quality audit (`reports/data_quality.json`)

| Source | Status | Span | Issues found |
|---|---|---|---|
| Angel 5-minute, 7 commodities | REAL | 2022-11 / 2023-xx → 2026-11-03 | 0 duplicates. 0–1 OHLC violations. Base metals have 2,120–13,521 in-session gaps (no-trade minutes, not printed). 43–212 short days per commodity. Zero-volume bars 0.02–2.7 %. |
| Angel 1-hour | REAL | 2022-07-15 → 2026-10-21 | 1 OHLC violation per file. 19–61 weekdays without bars (holidays + gaps). |
| Angel daily | REAL | 2006 → 2026-10-21 (NG from 2016) | Pre-2022 roll ratios INFERRED (open / previous close). |
| MCX bhavcopy, 9 symbols | REAL, end of day | 2022-07-01 → 2026-11-06, 1,118 days | Nickel: 781 zero-volume days, so untradable until mid-2025. Crude: 46 OI jumps over 50 % (roll days). Lead is thin (median 556 lots/day). |
| Contract rolls | 1h / intraday: 100 % exact from bhavcopy | | Natural gas roll gaps up to 54 % (contango). Trades never span a roll. |
| Best-5 depth, MCX | REAL, forward only | 11–12 Nov 2026, 6,439 snapshots | No history. Median spread: Gold 31 ticks, Silver 56, Copper 6, Zinc 4, Aluminium 4, Crude 2, NG 1. |
| International daily | REAL (Yahoo) | Gold, Silver, Crude, NG, Copper, Aluminium; USDINR | Not available: Zinc, Lead, Nickel, DXY, yields, Brent, EIA / LME inventories, weather, China data. |

Data-quality results that changed the design:
- **The live spreads are much wider than the old 1.5-tick assumption.** Slippage is now per commodity: max(1.5 ticks, live half-spread + 0.5 tick) per side. The resulting average cost per trade is in section 13.
- **Labels for real versus calculated data** are in `data_quality.json` under `real_vs_calculated`.
- **Not available, so those experiments are marked unavailable:**
  - Historical order book, trade aggressor side, volume delta, footprint.
  - Intraday OI history.
  - Lead and Nickel intraday data.

## 3–10. Module results (stage 1; matched-baseline excess = rule R minus the random-entry baseline with the same stop and exit)

Baselines on OOS with a 3R exit:

| Timeframe | Random entry, same stop | Random buy-stop above a bar high |
|---|---|---|
| 15m | −0.32R | −0.06R |
| 1h | −0.03R | +0.20R |
| 4h | +0.13R | +0.47R |
| 1d | +0.10R | +0.25R |

Buying strength (a buy-stop above a bar's high) is itself profitable on 4h and daily in this sample. Any rule must beat that.

| Module | Tests | Beat baseline in all 3 periods | Verdict |
|---|---|---|---|
| A Divergence (16 indicators × regular / hidden × pivot 2/3/5) | 96 rules per timeframe | 4h: 28 (mostly hidden and regular R2 divergences) | Multi-indicator divergence does **not** beat the TRAIN-best single indicator: better in VAL and OOS in only 3 of 20 cases (`mod_divergence_multi_vs_best.csv`). The pivot detection delay of 2/3/5 bars is in every signal. |
| B RSI oversold (< 25, cross, touch, 3-bar, < 30 + structure) | 300 | 0 | **Failed** on every timeframe. |
| B RSI ≥ 75 continuation BUY | 240 | 1d: 17, 4h: 5, 15m: 1 | **Strongest family.** Positive on 1d over 2006–2026 and on 4h. |
| B Candles (7 patterns, plain and buy-stop above the high) | 210 | 4h: 4 | No incremental value over the matched buy-stop baseline on 1d (median excess −0.11R). |
| C Liquidity sweeps (PDL / PWL / PML / swing / equal lows / double bottom / breakdown-reclaim / VWAP; 4 entries each) | 528 | 4h: 11, 1h: 1 | The sweep alone ≈ baseline. Only "sweep → **lower-high break → retest**" works (4h). Events are in `mod_sweep_events.csv`: median depth 0.2–1.5 ATR, reclaim 0.2–0.4 ATR, a later higher low in 20–55 %, MFE about 1R, MAE about −1.1R. Deeper sweeps (> 1 ATR) did better on 15m–1h but are still negative intraday. |
| D Volume / OI (6 hypotheses, climax, exhaustion, price-impact proxy) | 63 | 1d: 3, 4h: 1 | OI states are **not consistently predictive**: 0–1 of 6 positive in all periods per timeframe. Daily OI starts in Jul-2022, so on the daily split it has **no TRAIN data** (inconclusive). Relative volume ≥ 1.5 and volume percentile ≥ 90 improve pooled trades in all 3 periods on 4h, 15m and 30m, and partly on 1h. Labels are possible long liquidation / short build-up / covering / new longs, never "institutional buying". |
| E Absorption / order flow | — | — | **UNAVAILABLE historically.** Forward depth statistics only (`mod_absorption_forward_depth.csv`). `LOWIMPACT_PROXY` is a disclosed proxy, not observed absorption. |
| F Support / structure | 87 | 4h: 4 | Support zones (daily, weekly, monthly) do **not** beat mid-range except on 1d (daily support). Countertrend context never helps. **Uptrend context improves pooled trades in all 3 periods on every timeframe** (confirmed entries on 4 of 5 timeframes, early entries on 3 of 5). |
| G Global confirmation (previous completed international day) | 6 conditions | — | Positive in all 3 periods only sporadically: USDINR rising (1d), international above its 5-day average (1h early entries), previous international up day (30m early entries), gold/silver ratio falling (4h confirmed entries). Not robust. |
| H Timeframes and MTF (1,848 tests) | | 1h: 20, 30m: 4, 15m: 0 | Best higher-timeframe context: **4h uptrend** (improves 28 % of trigger and exit pairs in all 3 periods), then daily support (20 %) and daily uptrend (19 %). Exhaustion contexts: 0–3 %. |

## 11. Combinations (stages 2–5; `reports/combos_<tf>.csv`, `score.csv`)

- **Stages 2–4:** anchors and conditions were chosen on TRAIN only.
  - Combinations that beat the baseline in all periods (out of 2,408 combination tests): 4h 13, 1d 5, 1h 4, 15m 7, 30m 0.
  - Every one of them is a 2- or 3-condition combo. No 4-condition combo passed.
  - The best two (RSI 7 crossing 75 with volume percentile ≥ 90, 4h, 2R) are OOS-validated.
- **Owner hypotheses A–J:** 0 of 227 pass on any timeframe; most have too few trades.
- **Stage 5 score models (logistic regression and gradient-boosted trees):**
  - TRAIN win rates of 70–90 % collapse to 30–58 % in VALID. That is classic over-fitting.
  - Passes: 4h CONF logistic top 20 % (57.5 % wins, +0.66R OOS) and 1d EARLY gradient-boosted trees top 10–20 % (59–60 % wins OOS, 30–51 trades).
  - Inconclusive: samples are small, and the trades overlap across anchors.

## 12. Commodity-wise OOS R per trade (validated candidates)

| Candidate | AL | CU | CRUDE | GOLD | NG | SILVER | ZINC |
|---|---|---|---|---|---|---|---|
| 1h sweep-PDL→LH-break-retest @4h uptrend, 3R | +1.72 | +0.09 | +0.21 | +0.80 | −0.30 | +1.13 | +1.48 |
| 1h same @daily uptrend, 3R | +1.84 | +0.19 | +0.05 | +0.49 | −0.74 | +1.18 | +1.21 |
| 4h hidden MACD divergence R3, 3R | +0.08 | +0.86 | +0.19 | +1.38 | −0.32 | +1.10 | +0.54 |
| 4h hidden MACD divergence R5, partial 1R / 3R | +0.06 | −0.02 | +0.08 | +1.07 | +0.40 | +0.79 | +0.58 |
| 4h RSI 7 cross 75 & volume percentile ≥ 90, 2R | −0.16 | +0.68 | +0.47 | +1.11 | −0.88 | +1.27 | +1.15 |
| 4h RSI 7 cross 75 + RVOL & volume percentile ≥ 90, 2R | −0.08 | +0.68 | +0.25 | +1.23 | −0.88 | +1.27 | +1.15 |
| 4h RSI 9 cross 75, partial 1R / 3R | −0.20 | +0.35 | +0.07 | +0.54 | −0.17 | +0.67 | +0.61 |
| 4h sweep-PDL→LH-break-retest, 2R | +0.31 | +0.12 | +0.24 | +0.88 | −0.25 | +0.97 | +0.42 |

Commodities not in the table:
- **Lead (daily only, 2022+, 18,864 trades):** 97 % of rules are negative, and the random buy-stop baseline is −0.39R. **Failed.**
- **Nickel:** unavailable (no trading 2022 to mid-2025).

By group over the full sample:
- **Precious metals** are the strongest.
- **Base metals** are positive.
- **Energy** is about 0 or negative (`candidate_regimes.csv`).

Per-commodity tuned parameters beat a pooled choice in 12 of 18 cells, but not for the two validated families out-of-sample (`commodity_specific.csv`). Pooled parameters are kept.

## 13. Timeframe-wise (`mod_timeframes.csv`)

| Timeframe | Tests | OOS pass | Beat baseline in all 3 | Average cost per trade |
|---|---|---|---|---|
| 15m | 1,407 | 1 | 1 | 0.42R |
| 30m | 1,406 | 0 | 0 | 0.29R |
| 1h | 1,406 | 1 | 1 | 0.19R |
| 4h | 1,398 | 117 | 68 | 0.09R |
| 1d | 1,398 | 78 | 38 | 0.08R |

## 14. Early versus confirmed BUY

Rules that beat the baseline in all periods:
- **4h:** 39 EARLY out of 1,085 tests, and 26 CONFIRMED out of 271.
- **1d:** 10 EARLY out of 1,092, and 26 CONFIRMED out of 264.

After full validation, **all 8 survivors are confirmed or continuation entries.** The hidden-divergence rules are tagged EARLY in code but are trend-continuation entries.

Early countertrend reversals:
- RSI < 25: 0 passes.
- Sweep reclaim at the low: none survive validation.
- Regular divergence: none survive validation.

The shadow lister tags a confirmed signal that follows an early one within 5 days as the **same event**.

## 15. Out-of-sample results (validated, OOS 2025-07 → 2026-10)

| Timeframe | Rule | Exit | OOS trades | Win % | Net R | PF | 95 % CI | Excess over baseline (CI low) |
|---|---|---|---|---|---|---|---|---|
| 1h | sweep-PDL→LH-break-retest @4h uptrend | 3R | 62 | 59.7 | +0.82 | 2.88 | 0.40–1.27 | +0.85 (0.40) |
| 1h | same @daily uptrend | 3R | 74 | 54.1 | +0.68 | 2.42 | 0.27–1.11 | +0.71 (0.29) |
| 4h | hidden MACD divergence R3 | 3R | 101 | 44.6 | +0.58 | 2.10 | 0.23–0.95 | +0.45 (0.07) |
| 4h | hidden MACD divergence R5 | partial 1R / 3R | 79 | **69.6** | +0.41 | 2.38 | 0.17–0.65 | +0.36 (0.09) |
| 4h | RSI 9 cross 75 | partial 1R / 3R | 107 | **66.4** | +0.31 | 1.92 | 0.10–0.51 | +0.26 (0.03) |
| 4h | sweep-PDL→LH-break-retest | 2R | 94 | 52.1 | +0.37 | 1.94 | 0.12–0.63 | +0.32 (0.02) |
| 4h | RSI 7 cross 75 & volume percentile ≥ 90 | 2R | 57 | 57.9 | +0.57 | 2.44 | 0.23–0.93 | +0.52 (0.13) |
| 4h | RSI 7 cross 75 + RVOL & volume percentile ≥ 90 | 2R | 53 | 58.5 | +0.60 | 2.48 | 0.23–0.99 | +0.54 (0.14) |

TRAIN and VALID win rates for the same rules were 38–66 % and 38–59 %, with +0.10 to +0.65R per trade (`validation.csv`).

## 16. Statistical robustness

- **BH-FDR 10 %** on the OOS p-values of every rule that reached OOS. 8 rules are significant and also beat their baseline with an excess CI above 0.
- **Deflated Sharpe Ratio** with N of about 1,950–2,590 trials per timeframe: 0.00–0.80 for the 8. **None ≥ 0.90.**
- **PBO (CSCV, 10 blocks) per timeframe:** 1d 0.00, 4h 0.01, 1h 0.01, 30m 0.04, 15m 0.18. In-sample winners tend to stay above the median, which is consistent with persistent trend and drift effects.
- **Walk-forward of the selection process** (yearly top 5 by past R, `walk_forward_summary.csv`):

| Timeframe | Years where picks beat the baseline | Average R of picks | Average R of baseline |
|---|---|---|---|
| 15m | 93 % | +0.06 | −0.44 |
| 30m | 93 % | +0.29 | −0.15 |
| 1h | 80 % | +0.13 | −0.06 |
| 4h | 53 % | +0.30 | +0.27 |
| 1d | 33 % | −0.05 | +0.05 |

  Chasing the best past daily rules **fails**.
- **Parameter stability:** 80–100 % of neighbouring settings (pivot width, RSI length, exit) are also positive OOS for the 8 candidates.
- **Year-by-year:** 80–100 % of years are positive. The worst years are 2022 and 2023.
- **Concentration:** the best commodity holds 27–38 % of the profit.
- **Correlation:** the mean pairwise correlation of the candidates' daily R is 0.15.

## 17. Failed experiments (kept, not hidden)

**Failed outright:**
- RSI < 25 reversals (300 tests).
- Every 30m rule. All but one 15m rule.
- Lead.
- Owner hypotheses A–J.
- Multi-indicator divergence versus the best single indicator.
- Exhaustion and support contexts in multi-timeframe tests.
- Daily-chart sweep entries versus the matched baseline.
- The earlier institutional study (order block, FVG, VWAP 2σ, 80 % rule, US-open ORB; `research/inst` on the exp branch), 0 of 64.

**Other labels:**
- 168 FAILED and 1 INCONCLUSIVE in `validation.csv`.
- 153 PROMISING: they passed every period but were not significant after FDR, or their excess CI touched 0.

## 18. Best research candidates

1. **4h hidden MACD divergence R5, partial exit:** 70 % OOS wins, +0.41R, positive in every period and on 6 of 7 commodities.
2. **4h RSI 9 crossing 75, partial exit:** 66 % OOS wins, +0.31R, the largest sample (315 trades).
3. **1h sweep-PDL → lower-high break → retest, only when the 4h chart is in an uptrend, 3R:** the best excess (+0.85R), but only 41 / 34 / 62 trades.

All three should exclude natural gas, as an observation, not a tuned filter.

## 19. Data limitations

- **OOS window:** it covers a strong metals bull market. The matched baselines adjust for drift only partly.
- **OOS re-use:** earlier studies on other branches looked at 2025–26 MCX data. OOS here is untouched by *this engine's* selection, not by every past study.
- **Order flow:** no historical depth or trade aggressor side, so absorption and volume-delta claims cannot be tested.
- **OI:** daily only, from Jul-2022.
- **Missing commodities:** no Lead or Nickel intraday, and no international data for zinc or lead.
- **Contract specs:** Lead and Nickel lot sizes are assumed (flagged in `config.json`).
- **Spreads:** measured on 1.5 days of quotes only.

## 20. Shadow tracking recommendation (not done; needs owner approval)

**What exists:**
- `shadow_tracking/run.py` lists research signals with every field required in section 13 of the brief, including rule hash, evidence for and against, and data-quality grade.
- It found 73 signals in the last 45 days of data. It **sends nothing**.

**Suggested next step, if approved:** paper-track candidates 1–3 for at least 3 months, or 30 trades each, with frozen rules. Promote nothing before forward results and an independent review.
