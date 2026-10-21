# EXP-001 – regime filter vs baseline vs long-only (intraday). Verdict: **FAIL (all variants)**

**Exploratory only:** the 12-Oct-2020 → 21-Oct-2026 period was already examined when the subgroup was found, so nothing here is independent evidence. Reproduce with `python -m crude.research.exp001`; `manifest.json` holds the code revision, data hash, config and costs.

## Audit
- **Baseline reproduction:** the original backtest reproduced exactly (324 trades, −0.194R, −₹47,399; tolerance 0.001R / ₹1).
- **Look-ahead 1 – regime label:** the regime's volatility measure divided ATR by the *back-adjusted* close. That level depends on roll gaps estimated later, so it leaked future information. The fix divides by the real close; this relabelled 104 of 1,448 sessions. With the old labels, B showed 54 trades at +0.17R, so part of the earlier promise came from this leak.
- **Look-ahead 2 – contract-switch days:** the roll-gap estimate needs that day's close. The fix blocks entries on switch days for all variants, which removed 20 trades. Baseline A moved from −0.19R to −0.16R.
- **Regime timing:** the regime of session d uses only sessions ≤ d−1. A test proves this.

## Results (corrected implementation, 1× costs)
| | A baseline | B uptrend/high-vol | C long-only |
|---|---|---|---|
| Trades / time in market | 304 / 3.5% | 60 / 0.6% | 167 / 2.1% |
| Win rate | 31.6% | 43.3% | 31.7% |
| Avg win / avg loss | ₹1,232 / −₹738 | ₹1,225 / −₹721 | ₹1,160 / −₹752 |
| Expectancy | −0.155R (−₹116) | **+0.136R (+₹123)** | −0.176R (−₹145) |
| Profit factor / net P&L | 0.77 / −₹35,193 | 1.30 / +₹7,353 | 0.72 / −₹24,255 |
| Max drawdown | −₹45,809 (−9.2%, −59.7R) | −₹4,576 (−0.9%, −6.1R) | −₹32,735 (−6.5%, −40.4R) |
| Worst losing streak | 17 | 4 | 12 |
| Bootstrap 95% CI (p5) | −0.30…−0.02 (−0.27) | **−0.18…+0.47 (−0.13)** | −0.36…+0.01 (−0.33) |
| Costs 1× / 2× / 3× | −0.16 / −0.37 / −0.59 | 0.14 / **−0.07** / −0.24 | −0.18 / −0.38 / −0.65 |
| Slippage 0 / 2 / 4 / 6 ticks | −0.08 / −0.16 / −0.27 / −0.40 | 0.24 / 0.14 / 0.02 / −0.06 | −0.10 / −0.18 / −0.28 / −0.44 |
| 10% missed fills (3 seeds) | −0.16 | 0.17 | −0.17 |
| Anchored walk-forward (pooled, positive years) | −0.15 (2/6) | +0.04 (1/4) | −0.18 (1/6) |
| Criteria | FAIL | **FAIL** (bootstrap p5 < 0; negative at 2× costs) | FAIL |

- **B by year:** 2021 +0.51 (12 trades), 2022 −0.31 (13), 2023 −0.50 (2), 2025 −0.05 (9), 2026 +0.31 (24).
- **B neighbours** (stability check only): SMA80 +0.19, SMA120 +0.19, median200 +0.15, median300 +0.10. This is stable in sign, but every neighbour shares the same seen-data problem.

## Where B's difference comes from
- **Not long bias.** C (BUY only) is −0.18R. Inside B, BUYs are −0.02R (31 trades) and SELLs are +0.30R (29 trades).
- **Mostly 2026.** Without 2026, B has 36 trades at **+0.02R**.
- **Not luck of fewer trades alone.** B beats 97.4% of random 60-trade subsets of A, but the subset was chosen after seeing these results.
- **Not lower costs.** Charges are 0.088R per trade for B vs 0.098R for A, which explains only ~0.01R.

## Conclusion
No variant passes. B is not even a PAPER-CANDIDATE: it fails bootstrap p5 > 0 and 2× costs on data that is already non-independent. Nothing is deployed; the live paper engine stays on its original rules.
