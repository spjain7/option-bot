# STRAT-SEARCH-002 – combination search (540 combos × 9 instruments, Jul-2022 → Oct-2026, real Angel candles)

## 1. "Pick the best combo from the past" does NOT work → FAIL
Each 6-month window, the best combination over the previous 18 months was traded next:
| | OOS trades | Avg R | PF | Positive windows |
|---|---|---|---|---|
| Single best combo | 192 | 0.00 | 1.00 | 2/5 |
| Top-5 combos | 1,133 | +0.09 | 1.18 | 2/5 |
The past winner changes every window, so chasing "the best" is curve-fitting.

## 2. A whole FAMILY is robust: trend breakouts on daily / 3-hour candles
- 199 of 318 combos with enough trades are positive in BOTH halves (before / after Jul-2024).
- Families that were positive at 2× costs in the design half (daily Donchian 20/40/55, daily EMA20/50, 3h Donchian20,
  3h EMA10/30 and 20/50) stayed positive in the hold-out: **+0.12R per trade (1× costs), +0.08R (2×), PF 1.26**,
  8 of 10 quarters positive.
- Every 15-min / 1-hour rule is negative at 2× costs. Supertrend 10/3 is negative or ~0 on all timeframes.
  (A NaN bug had silently produced zero Supertrend trades in STRAT-SEARCH-001; it is fixed and re-tested here.)

## 3. Best simple, stable rules (exploratory – the families were chosen with both halves visible)
| Rule | Trades | Avg R | At 2× costs | Win % | PF | Bootstrap p5 | Max DD | Per year |
|---|---|---|---|---|---|---|---|---|
| Daily Donchian 55 breakout, 2 ATR stop, exit on 27-day opposite channel | 194 | +0.27 | +0.23 | 44 | 1.58 | +0.07 | −14R | 23 +0.25 · 24 +0.07 · 25 +0.67 · 26 −0.04 |
| Daily Donchian 55, 3 ATR trailing | 197 | +0.24 | +0.20 | 44 | 1.54 | +0.04 | −15R | 23 +0.19 · 24 +0.06 · 25 +0.68 · 26 −0.13 |
| Daily Donchian 40, 3 ATR trailing | 228 | +0.23 | +0.20 | 45 | 1.51 | +0.05 | −13R | 23 +0.15 · 24 +0.12 · 25 +0.65 · 26 −0.13 |
| 3-hour Donchian 20, 3 ATR trailing | 1,284 | +0.14 | +0.07 | 39 | 1.27 | +0.07 | −24R | 22 −0.17 · 23 +0.08 · 24 +0.20 · 25 +0.20 · 26 +0.17 |

- **Neighbouring settings agree** (channels 40/55, stop 2/3 ATR, either exit), so this is not a single lucky setting.
- **Strong on:** gold, silver, aluminium, copper, zinc, BANKNIFTY.
- **Weak or negative on:** natural gas, NIFTY, crude (daily).
- **Weakest period:** 2026 has been flat or negative.

## Verdict
Nothing qualifies as PASS. Daily / 3-hour channel breakout is a **PAPER-CANDIDATE**: the most robust evidence found so far, but not proven.
Expect a ~40% win rate, many small losses and a few big winners, and drawdowns of ~15R.
