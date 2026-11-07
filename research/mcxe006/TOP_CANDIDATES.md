# MCXE-006 top candidates

**None is validated.** All three were frozen before OOS and tested on OOS once (`results/oos_results.json`). All three have positive OOS expectancy after 2× costs, but the 95 % CI includes 0.

**Common execution for all three:**
- Universe: the 7 MCX commodities (ALUMINIUM, COPPER, CRUDEOIL, GOLD, NATURALGAS, SILVER, ZINC), front-month stitched data.
- Signal at the bar close; entry at the next bar's open.
- The initial stop is checked first; a gap through the stop fills at the open.
- One position per commodity per strategy; forced exit before a contract roll.
- Costs: statutory fees + 1.5 ticks slippage per side; also shown at 2×.

## 1. H1.12L: MCX 1-hour breakout, BUY only (best)

**Rules**
- **Entry:** the 1-hour close crosses above the highest high of the previous 20 bars → BUY at the next bar's open.
- **Stop:** entry − 2 × ATR(14).
- **Trailing stop:** 4 × ATR (ATR at signal) below the highest close since entry. It only tightens.
- **Time exit:** after 240 bars, or before a contract roll.
- **Target:** none. It is a trend capture.

**Results**

| Period | Trades / dates | Win % | Avg win / loss | Exp 1× | Exp 2× | PF | Max DD | 95 % CI (1×) |
|---|---|---|---|---|---|---|---|---|
| DEV (Nov-25 – May-26) | 157 / 84 | 37.6 | — | +0.629 | +0.578 | 2.00 | — | DEV + VALID [+0.15, +1.07] |
| VALID (May – Aug-26) | 70 / — | 38.6 | — | +0.453 | +0.400 | 1.78 | — | |
| **OOS (Aug – Nov-26)** | **79 / 47** | **41.8** | **+2.19 / −0.95** | **+0.359** | **+0.306** | **1.65** | **12.97R** | **[−0.12, +0.86]** |

**OOS detail**
- Random-entry control with the same exits: +0.090R. Day-clustered p = 0.073; BH q = 0.22.
- By commodity:

  | Commodity | Trades | Avg R |
  |---|---|---|
  | ZINC | 12 | +1.52 |
  | COPPER | 9 | +0.84 |
  | GOLD | 10 | +0.47 |
  | SILVER | 7 | +0.30 |
  | CRUDEOIL | 18 | −0.03 |
  | NATURALGAS | 12 | −0.05 |
  | ALUMINIUM | 11 | −0.28 |

- By month: Aug +32.5R, Sep +0.7R, Oct −4.9R.

**Limitations**
- BUY only, and selected during a metals rally. In DEV + VALID its "down" regime trades lost (−0.85R, 10 trades).
- Profits come from a few large trends: without the best 5 OOS trades, expectancy is −0.04R.
- The strategy is cumulative, with drawdowns of about 13R.

**Status:** REJECTED under the pre-registered rule. **Eligible only for forward paper (shadow) tracking.**
- Suggested bar before any review: ≥ 30 new trades on ≥ 20 dates.
- Expectancy at 2× cost > 0, with a CI lower bound > 0.

## 2. H1.11: MCX 4-hour two-sided breakout

**Rules**
- **Entry:** close crosses above the prior 20-bar high → BUY, or below the prior 20-bar low → SELL.
- **Stop:** 2 × ATR.
- **Exit:** 4-ATR trailing stop; cap of 120 bars (about 30 sessions).

**Results**
- DEV: 90 trades, +0.453R at 2×.
- VALID: 45 trades, +0.467R at 2×. Both sides were positive in both periods.
- OOS:
  - 53 trades on 34 dates; win 34 %.
  - Expectancy +0.138R (2×: +0.113R); PF 1.24; max DD 12.3R; CI [−0.43, +0.75].
  - SELL +0.32R (23 trades); BUY +0.00R (30 trades).
- **The random-entry control earned +0.37R**: the entry signal added nothing in OOS, and the profit came from the trailing exit in trending markets.

**Status:** REJECTED. Not recommended for paper tracking ahead of H1.12L.

## 3. H5.2L: MCX 1-hour RSI momentum, BUY only

**Rules**
- **Entry:** RSI(14) crosses above 75 (strength persists) → BUY at the next open.
- **Stop:** 2 × ATR.
- **Exit:** 4-ATR trail; cap of 120 bars.

**Results**
- DEV: 73 trades, +1.04R at 2×.
- VALID: 27 trades, +0.49R at 2×.
- OOS:
  - 31 trades on 22 dates; win 35.5 %.
  - Expectancy +0.223R (2×: +0.165R); PF 1.38; max DD 9.1R; CI [−0.47, +1.01].
  - Control +0.22R. By month: Aug +15.0R, Sep −2.7R, Oct −5.4R.

**Status:** REJECTED. It overlaps heavily with H1.12L (both are long 1-hour strength entries). Not tracked separately.

## The RSI reversal, candle and stock strategies the brief asked about
- None reached the freeze bar. Their numbers are in FAILED_STRATEGIES_AND_LESSONS.md and the register.
- **RSI 75/25 and 80/20 reversal on MCX 1h:** −0.11 and −0.15R in VALID.
- **Trend-aware RSI reversal:** fewer than 5 trades. RSI rarely reaches 25 inside an uptrend on 1-hour bars.
