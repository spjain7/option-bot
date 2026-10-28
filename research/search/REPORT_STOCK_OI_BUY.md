# STOCK-OI-BUY-001 – improving the stock-futures OI BUY rule (28-Oct-2026)

Code: `research/search/stock_oi_buy.py` (candidate logic) · `stock_oi_buy_run.py` (run) · tests
`tests/test_stock_oi_buy_research.py` (29 checks) · full tables `results_stock_oi_buy/tables.md` · trades `results_stock_oi_buy/trades.csv.gz`.
Live rules, flags and workflows are **not changed**.

**Status: EXPLORATORY.** All dates (Nov-2023 → Oct-2026; OI history starts Nov-2023) were examined before. Nothing below
is independent validation. Prospective evidence = forward paper calls from 29-Oct-2026, judged on rules fixed today.

## Set-up
- **Baseline:** the exact live rule and the live execution:
  - signal: close above the previous 20-day high, volume > 1.5× average, price up, OI ≥ +2 %, close above EMA200;
  - no signal inside the rollover window;
  - entry at the next open, stop 2 ATR, trailing 3 ATR (moved only when it gains > 0.25 ATR);
  - exit at the expiry-day close, or after 40 sessions; one open call per stock;
  - a gap through the stop fills at the open.
- **Costs:** taxes, brokerage and 3 bp slippage per side (≈ 0.02R per trade), at 1× and 2×.
- **Uncertainty:** 95 % month-block bootstrap; candidate − baseline differences use the same resampled months.
- **Sample warnings:** n < 30 and n < 100 are flagged in the tables.

## Data checks (deliverable: verify OI alignment / roll / invalid data)
| Check | Finding | Handling |
|---|---|---|
| OI ↔ candle alignment | daily OI date = completed daily candle date for all 107,959 sessions; no OI day without a price day | OI(t) = end of day t; the signal is known after the close; entry is the next open (no look-ahead) |
| Contract roll | stitched prices switch contract on the **first session after expiry** (avg gap +0.62 % vs ≈0.1 % on other days); OI jumps up to +1,700 % inside the rollover window | rollover-window exclusion kept; exit at the expiry-day close uses the old contract (valid) |
| Bad OI ticks | 1,538 sessions **outside** the rollover window have isolated bad OI values (e.g. −99 % then +7,000 %, Feb-2024) | an OI change is valid only if both days are > 0 and within ×0.5–×2 of the previous 5-session median (past data only); invalid = no confirmation |
| Corporate actions | **28 unadjusted splits / bonus issues / demergers** in the stored prices (e.g. DRREDDY 28-Oct-24 ×0.2, RELIANCE ×0.5, BAJFINANCE ×0.1) | back-adjusted prices, volume and OI; the OI change on the ex-date is invalid |
| Missing / zero OI | 66 missing, 115 zero | rejected |

The data fixes change the baseline only a little: B0 +0.058R → B1 +0.066R per trade.

The same defects exist in **live** data, which has no OI-tick check and no split adjustment. That is a live-data risk to fix
separately (needs your approval).

## Baseline vs candidates (BUY; all periods; per-trade R after costs)
| Variant | Trades | Removed | Win % | Exp 1× | Exp 2× | 95 % CI | PF | Max DD R | Δ vs B1 [95 % CI] | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| **B1 baseline (live rule, corrected data)** | 675 | – | 44.3 | +0.066 | +0.046 | [−0.08, +0.22] | 1.15 | 39.7 | – | baseline |
| B1 + live open-zone check (±0.5 ATR) | 623 (65 cancelled) | – | 44.9 | +0.075 | +0.055 | [−0.08, +0.23] | 1.17 | 36.1 | +0.01 [−0.02, +0.03] | neutral (already live) |
| E1 OI 2–3 % | 126 | 549 | 42.1 | +0.129 | +0.110 | [−0.14, +0.45] | 1.31 | 8.7 | +0.06 [−0.15, +0.35] | not proven (thin) |
| **E1 OI 2–4 %** | 236 | 439 | 46.2 | **+0.167** | **+0.148** | [−0.05, +0.39] | 1.41 | 12.9 | **+0.10 [−0.04, +0.25]** | **best; not proven** |
| E1 OI 2–5 % | 317 | 358 | 45.1 | +0.105 | +0.086 | [−0.07, +0.28] | 1.24 | 18.1 | +0.04 [−0.06, +0.13] | small, not proven |
| E2 extension ≤ 0.25 ATR | 152 | 523 | 43.4 | +0.093 | +0.075 | [−0.10, +0.29] | 1.21 | 12.7 | +0.03 [−0.13, +0.20] | fail (noise) |
| E2 extension ≤ 0.5 | 273 | 402 | 45.1 | +0.051 | +0.032 | [−0.11, +0.19] | 1.12 | 19.0 | −0.02 | fail |
| E2 extension ≤ 0.75 | 395 | 280 | 43.3 | +0.047 | +0.027 | [−0.12, +0.20] | 1.10 | 28.1 | −0.02 | fail |
| E2 extension ≤ 1.0 | 495 | 180 | 44.8 | +0.078 | +0.059 | [−0.08, +0.23] | 1.18 | 26.7 | +0.01 | fail (no effect) |
| E3 confirmation buy-stop | 475 (223 missed) | – | 44.2 | +0.033 | +0.013 | [−0.12, +0.21] | 1.07 | 24.7 | −0.03 [−0.10, +0.05] | fail |
| SELL baseline (reference only) | 257 | – | 58.0 | +0.235 | +0.218 | [+0.01, +0.44] | 1.77 | 14.8 | – | not in scope |

By period, per-trade exp 1×:

| Variant | Nov-23 – Jun-24 | Jul-24 – Jun-25 | Jul-25 – Oct-26 |
|---|---|---|---|
| B1 | +0.26 | −0.01 | −0.07 |
| E1 2–4 % | +0.40 | +0.06 | +0.06 |
| E1 2–5 % | +0.35 | +0.01 | −0.02 |
| E1 2–3 % | +0.31 | +0.09 (n27) | +0.04 |
| E2 ≤0.25 | +0.42 | −0.03 | −0.13 |
| E3 | +0.17 | −0.05 | −0.05 |

- **By year (B1):** 2023 +0.54 (n79), 2024 +0.03, 2025 +0.03, 2026 −0.08.
- **E1 2–4 % by year:** +0.72 (n27), +0.10, +0.06, +0.13. E1 2–3 % and 2–4 % are the only candidates positive in every period and every year; 2–4 % has nearly twice the trades.
- **By stock:** B1 is positive on 66 of 145 stocks; E1 2–4 % on 61 of 116.
- **By market regime:** NIFTY above/below its EMA200 does not separate results for B1 (+0.07 vs +0.05).

## Root-cause hypotheses (deliverable 1)
| # | Hypothesis | Data | Verdict |
|---|---|---|---|
| H1 | The earlier "negative expectancy" (OOS-VALIDATE-001: −0.19R / −0.17R) partly came from the **simulation**: it exited 3 sessions before expiry, while live holds to the expiry-day close | same signals, early exit: −0.046R vs +0.066R; Δ −0.11 [−0.21, −0.02] | **Supported.** With live exits the rule is about break-even recently (−0.01, −0.07), not clearly negative |
| H2 | The edge has **decayed over time** | +0.54 (2023) → +0.03 (2024/25) → −0.08 (2026), in every variant; not explained by NIFTY regime | **Supported** as an observation; the cause is unknown |
| H3 | **Large OI jumps** are worse | OI 2–3 %: +0.12 · 3–4 %: +0.23 · 4–5 %: −0.03 · 5–8 %: +0.14 · > 8 %: −0.06 | **Weak.** Only > 8 % is negative, and the pattern is not monotonic. Bands help a little, not proven |
| H4 | **Extended breakouts** fail | ext 0–0.25: +0.08 · 0.25–0.5: −0.09 · 0.75–1.0: +0.28 · > 1.5: −0.02 | **Not supported** |
| H5 | **Entry timing / gaps** hurt | open against the signal by > 0.5 ATR: −0.16 (n25); live zone check adds +0.01; confirmation entry −0.03 | **Not supported** as a main cause |
| H6 | **Data defects** (splits, bad OI) | B0 vs B1 +0.008R | real defects, small effect on results |

Outcomes are driven by the exit: 403 expiry exits average +0.77R, while 272 stop-outs average −0.98R. Trades held 5
sessions or less (mostly stop-outs) are 30 % of all trades.

## Recommendations (deliverable 6)
| Candidate | Recommendation | Reason |
|---|---|---|
| E1 OI 2–4 % | **Paper-test** (shadow log only; live alerts unchanged) | best Δ and positive in all periods, but the CI includes 0 and it was chosen on examined data |
| E1 2–3 %, 2–5 % | Reject as separate options; keep as shadow columns only | thin sample (2–3 %) or small effect (2–5 %) |
| E2 extension caps (all four) | **Reject** | no consistent improvement; no monotonic pattern |
| E3 confirmation entry | **Reject** | lower expectancy; 32 % of signals missed |
| Exit model correction | **Retain for research**: the OOS-VALIDATE-001 S4 numbers should be read with live exits | modelling fix, no live change |
| OI-tick validity check and split adjustment in live data | **Needs your approval** (code-correctness fix to live inputs, not a strategy change) | live currently treats a bad OI tick as confirmation |

**Pre-registered forward test (from 29-Oct-2026, fixed now):**
- Log every live S4 BUY signal with its OI change and extension. Live calls are unchanged; the band is a shadow label only.
- Compare baseline vs the E1 2–4 % subset after at least 40 subset trades.
- Pass only if the subset's net expectancy at 2× costs is > 0 and above the baseline.
- These forward observations are not used to adjust the thresholds.

## Limits / data not available
- **Survivorship:** the universe is today's 181 F&O stocks; stocks dropped from F&O are missing, which biases results upward.
- **Execution:** there is no bid/ask history for stock futures, so slippage is a fixed 3 bp per side. Intraday order inside
  an hourly bar is unknown, so the confirmation entry is resolved conservatively.
- **Corporate actions:** adjustments were inferred from price gaps. For the two demergers (SIEMENS, VEDL) the exact NSE
  adjustment factors would need NSE corporate-action data.
- **OI history** only goes back to Nov-2023: about 3 years and fewer than 700 baseline trades. Every subset is small.
