# MCXE-006 failed strategies and lessons

**Register:** all 79 experiments are in `EXPERIMENT_REGISTER.csv`:

| Classification | Experiments |
|---|---|
| FAILED_DEV_VALID | 60 |
| ELIGIBLE_BUT_DROPPED (lost to their parent) | 9 |
| ELIGIBLE_NOT_FROZEN (superseded by a kept descendant) | 7 |
| REJECTED at OOS | 3 |

## Why MCXE-005 failed, and what changed in response (diagnosis on DEV + VALID only: `results/diagnosis_mcxe005.txt`)

| Cause | Evidence | Response in MCXE-006 | Result |
|---|---|---|---|
| **Costs vs stop size** (main cause intraday) | Intraday gross edge +0.01 to +0.15R, but costs 0.12–0.32R per trade because the stops were 1–1.5 bar-ATR | Structural stops (opening range, 0.5 daily ATR); fewer trades | MCX cost fell to 0.04–0.08R; the remaining edge was still too small to be significant |
| **Too-small cells** (selection power) | Each family × side × filter was judged alone; 1,404 MCX positional cells had insufficient data | Treat a strategy as a portfolio across the 7 commodities and both sides | MCX trend became significant in DEV + VALID |
| **Regime change** (daily stocks) | Stock-futures daily rules: DEV positive, VALID negative | Market-breadth side filter; market-neutral long-short | Did not help: both sides lost in VALID |
| **Short DEV for daily data** | The 60-bar warm-up leaves about 3 months of daily DEV | Shorter-lookback rules (RSI2, 5-day reversal) | No edge found anyway |
| **Excessive filtering** | MCXE-005 ablations: filters raised win % more often than expectancy | One change at a time, kept only if VALID did not fall | Most filters (ADX, EMA alignment, vol regime) lowered VALID on H1 |
| **Selection bias** | 6,306 MCXE-005 cells | MCXE-006 froze 3 candidates and reported BH across them | 0 of 3 survive |

## Strategy-level lessons
1. **RSI reversals lose; RSI persistence wins (on MCX).**
   - Fading RSI 75/25 or 80/20 lost in VALID. Exiting at RSI 50 was worse.
   - Buying RSI > 75 (H5.2) was the best DEV result of the program.
   - Trend-aware reversals almost never trigger on 1-hour bars.
2. **Partial profit-taking and tighter trails hurt trend strategies.**
   - Taking 50 % at 1R and moving the stop to breakeven: H1.6 raised win % from 47 to 54 %, but cut VALID expectancy from +0.37R to +0.24R.
   - Trail 2 ATR: VALID +0.12R vs +0.37R.
   - This is the clearest example in the program of "higher accuracy, lower profit".
3. **Candle patterns at support and resistance:** the edge in DEV did not hold in VALID (H6.0: +0.01 → −0.28R). Confirmation bars cut trades without fixing the sign.
4. **Dip-buying in stocks (RSI2):** a 61–68 % win rate, but negative expectancy.
   - Average winner +0.25R; stops −1.05R.
   - A wider stop only moved it to about zero.
5. **NSE intraday (ORB, previous-day high/low):** the gross edge is about +0.02R. Costs of 0.10–0.13R make it unworkable at any filter.
6. **Overnight (BTST / STBT):** the close-strength carry is about 0R gross on stock futures. MCX had too few signals.
7. **Cross-sectional stock momentum and reversal (weekly):** about 0R. Only about 18 rebalance dates fit in DEV.
8. **Trend-following was the only lasting effect, and it is fat-tailed.**
   - OOS profit depended on August.
   - The random-entry control showed that exits did most of the work for the 4-hour rule.

## What did not cause the failures
- **Data errors:** 0 run errors. The S4 fixtures reproduce production. Frames are clipped to the window before indicators.
- **Execution optimism:** next-bar entry, stop first, gap fills at the open, 2× costs shown.
