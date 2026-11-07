# MCXE-005 failed strategies (every cell is kept in STRATEGY_EXPERIMENT_REGISTER.csv)

## Failure reasons by market cell

| cell | outcome | cells |
|---|---|---|
| NSE cash BTST / positional | FAILED_DEV | 424 |
| NSE cash BTST / positional | INSUFFICIENT_DATA | 120 |
| NSE cash intraday | FAILED_DEV | 1086 |
| NSE cash intraday | INSUFFICIENT_DATA | 18 |
| NSE futures BTST / STBT / positional | FAILED_DEV | 570 |
| NSE futures BTST / STBT / positional | FAILED_VALID | 25 |
| NSE futures BTST / STBT / positional | FROZEN_FOR_OOS | 4 |
| NSE futures BTST / STBT / positional | INSUFFICIENT_DATA | 481 |
| NSE futures intraday | FAILED_DEV | 532 |
| NSE futures intraday | INSUFFICIENT_DATA | 20 |
| MCX intraday | FAILED_DEV | 983 |
| MCX intraday | INSUFFICIENT_DATA | 121 |
| MCX positional / overnight | FAILED_DEV | 518 |
| MCX positional / overnight | INSUFFICIENT_DATA | 1404 |

## Why they failed (measured)

- **MCX intraday**:
  - 983 testable cells; 14 % positive in DEV at 2× cost;
  - 0 significant after BH;
  - of the DEV-positive cells, 86 % turned ≤ 0 in VALID (regime flip / noise);
  - positive in both: 2 %; median DEV 2× expectancy -0.203R.
- **MCX positional / overnight**:
  - 518 testable cells; 51 % positive in DEV at 2× cost;
  - 0 significant after BH;
  - of the DEV-positive cells, 45 % turned ≤ 0 in VALID (regime flip / noise);
  - positive in both: 28 %; median DEV 2× expectancy +0.015R.
- **NSE cash intraday**:
  - 1086 testable cells; 0 % positive in DEV at 2× cost;
  - 0 significant after BH;
  - of the DEV-positive cells, 0 % turned ≤ 0 in VALID (regime flip / noise);
  - positive in both: 0 %; median DEV 2× expectancy -0.403R.
- **NSE cash BTST / positional**:
  - 424 testable cells; 29 % positive in DEV at 2× cost;
  - 0 significant after BH;
  - of the DEV-positive cells, 62 % turned ≤ 0 in VALID (regime flip / noise);
  - positive in both: 11 %; median DEV 2× expectancy -0.148R.
- **NSE futures intraday**:
  - 532 testable cells; 0 % positive in DEV at 2× cost;
  - 0 significant after BH;
  - of the DEV-positive cells, 100 % turned ≤ 0 in VALID (regime flip / noise);
  - positive in both: 0 %; median DEV 2× expectancy -0.269R.
- **NSE futures BTST / STBT / positional**:
  - 599 testable cells; 37 % positive in DEV at 2× cost;
  - 29 significant after BH;
  - of the DEV-positive cells, 94 % turned ≤ 0 in VALID (regime flip / noise);
  - positive in both: 2 %; median DEV 2× expectancy -0.054R.

**Patterns seen:**
- **No information after costs on intraday horizons.**
  - MCX, NSE cash and NSE futures intraday: the median cell is below zero at 2× cost.
  - The few positive DEV cells do not survive BH, or flip in VALID. This matches MCXE-003, where intraday pattern
    information was absent or below costs.
- **Regime dependence on daily horizons.**
  - Strong DEV results (Nov-2025 – May-2026) often turn negative in VALID (May – Aug 2026).
  - Example: the S4 proxy, +0.72R DEV → −0.14R VALID → −0.11R OOS.
- **SELL-side survivors and market drift.**
  - The surviving cells are stock-futures SELL rules (trend down + ADX ≥ 20).
  - In OOS the plain all-signal SELL baseline earned +0.22 to +0.32R, so much of their OOS profit is a falling-market
    effect, not the pattern.
- **Filters raise win % more often than expectancy.** See the ablation table in ACCURACY_COMPARISON.md: most filters
  cut trades heavily without a CI-backed gain.

## The 4 OOS-evaluated cells – rejection reasons

| fam | side | filt | exit | status | reason | oos_trades | oos_exp1 | oos_ci | control_exp1 |
|---|---|---|---|---|---|---|---|---|---|
| A_EMA50_SLOPE | -1 | adx20 | X1 | REJECTED | OOS 95% CI lower bound -0.104 not > 0 | 51 | 0.145 | [-0.104, 0.394] | 0.317 |
| A_EMA50_SLOPE | -1 | adx20 | X2 | REJECTED | OOS 95% CI lower bound -0.16 not > 0 | 51 | 0.171 | [-0.16, 0.502] | 0.316 |
| A_MACD_ZERO | -1 | adx20 | X1 | REJECTED | OOS 95% CI lower bound -0.025 not > 0 | 51 | 0.344 | [-0.025, 0.669] | 0.229 |
| A_MACD_ZERO | -1 | adx20 | X2 | REJECTED | OOS 95% CI lower bound -0.1 not > 0 | 51 | 0.401 | [-0.1, 0.915] | 0.216 |
