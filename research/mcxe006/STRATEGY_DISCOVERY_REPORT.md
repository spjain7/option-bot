# MCXE-006 strategy discovery report

Research only:
- `main` is unchanged at bc3153e6.
- The S4 logic behind PETRONET / GLENMARK / TITAN is unchanged; 6 of 6 preservation tests pass before and after.
- No alerts were sent, no orders were placed, and nothing was promoted.

## Answer in brief
- **New strategies developed:** 10 hypothesis families, 79 experiments, each recorded in `EXPERIMENT_REGISTER.csv` with its parent and the one component changed.
- **Best strategy: H1.12L, MCX 1-hour 20-bar breakout, BUY only, 2-ATR stop, 4-ATR trailing stop.**
  - Positive after 2× costs in all three independent periods:

    | Period | Trades | Expectancy at 2× cost |
    |---|---|---|
    | DEV | 157 | +0.58R |
    | VALID | 70 | +0.40R |
    | OOS | 79 | +0.31R |

  - It beat a random-entry control by +0.27R per trade.
- **OOS result (run once):**
  - 79 trades on 47 dates; win rate 41.8 %.
  - Average win +2.19R; average loss −0.95R.
  - Net expectancy +0.359R at 1× cost and +0.306R at 2× cost.
  - Profit factor 1.65; max drawdown 12.97R.
  - 95 % CI [−0.12, +0.86]R.
- **Survived validation? No.**
  - The pre-registered rule needs the OOS CI lower bound above 0. Status: **REJECTED** (BH q = 0.22).
  - OOS profit came almost entirely from August (+32.5R). September was flat and October negative (−4.9R).
  - Without its 5 best trades, OOS expectancy is −0.04R.
- **Forward paper testing:** recommended as the next step, as shadow logging only (no alerts), to collect independent evidence. Not as a validated strategy.
- **Accuracy:** no 80–90 % accuracy claim is supported. The best strategy wins about 42 % of trades; it is profitable only because its winners are more than twice the size of its losers.

## What was developed (one line per family; details in the register)

| Family | Hypothesis | Best version | DEV 2× | VALID 2× | Outcome |
|---|---|---|---|---|---|
| H1 MCX trend | Commodity trends persist; two-sided breakout with a wide trail | H1.11 4h (trail 4, cap 120); H1.12L 1h BUY | +0.45 / +0.58 | +0.47 / +0.40 | **Frozen**: OOS positive, CI includes 0 |
| H2 MCX intraday | Structural stops cut cost per R | H2.6 previous-day-high/low breakout with daily trend, before 11:00 | +0.06 | +0.14 | CI includes 0; not eligible |
| H3 Stock futures trend / pullback / breakout + OI | Trends continue; breadth chooses the side | none | < 0 | < 0 | Failed: both sides negative in VALID |
| H4 RSI(2) dip-buying (cash, futures) | Oversold dips in uptrends revert | H4.2 (4-ATR stop) | −0.12 | +0.00 | Failed: losses too large for small winners |
| H5 RSI reversal vs momentum (MCX, NSE) | Extremes revert / persist | H5.2L RSI > 75 momentum, BUY | +1.04 | +0.49 | **Frozen**: OOS +0.16R at 2×, CI includes 0. Reversal versions all failed. |
| H6 Candle at support / resistance, breakout + retest | Rejection at tested levels | H6.2 (with trend; 12 trades) | +0.30 | +0.29 | Too few trades; other versions failed VALID |
| H7 NSE cash and stock-futures intraday ORB / previous-day breakout | Opening drive continues | none | −0.19 | −0.22 | Failed: gross +0.02R vs cost 0.11R |
| H8 BTST / STBT close strength | Strong closes carry overnight | none | < 0 | ≈ 0 | Failed: gross ≈ 0 |
| H9 Hybrids (breakout + RSI confirmation) | Complementary confirmation | H9.1 / H9.2 | +0.53 / +0.19 | +0.29 / +0.40 | Did not beat the parent in VALID; dropped |
| H10 Cross-sectional long-short (stock futures) | Relative momentum / short-term reversal, market-neutral | none | ≈ 0 | ≈ 0 | Failed |

## Main findings
1. **The only consistent edge in the approved windows is MCX trend-following**, which makes money through exit design rather than prediction.
   - Win rates are 34–47 %, with average winners more than twice average losers.
   - Many neighbouring settings (trail 3 or 4 ATR, cap 60 or 120 bars, 1h or 4h) were positive in DEV and VALID. It is a stable region, not a fitted spike.
2. **In OOS the edge weakened, and its source shifted:**
   - Random entries with the same 4-ATR-trail exits earned +0.37R in OOS (more than H1.11's entries).
   - The 1-hour breakout entry (H1.12L) did add value over random entries (+0.36R vs +0.09R).
3. **NSE equities and stock futures have no edge in this window** under any tested logic: trend, pullback, breakout + OI, mean reversion, candles, overnight or cross-sectional.
   - Their daily DEV period is only about 3 months after warm-up, and the stock regime flipped between DEV and VALID.
4. **Intraday failures were mainly cost failures, and structural stops reduced the cost share.**
   - MCX intraday cost per trade fell from 0.13–0.20R (MCXE-005) to 0.04–0.08R.
   - But the remaining gross edge (+0.05 to +0.15R) is too small to be significant.

## Reproduce
```bash
git checkout exp/strategy-program-001                       # code at 31a25d8 (frozen list) + report commit
python research/mcxe005/tests/test_preservation.py          # 6 production regression tests
python research/mcxe006/diagnose.py                         # MCXE-005 failure diagnosis (DEV+VALID)
python research/mcxe006/lab.py fam H1 H2 H3 H4 H5 H6 H7 H8 H9 H10   # all 79 experiments, OOS masked (frames cached on first run)
python research/mcxe006/robustness.py H1.11 H1.12L H5.2L    # DEV+VALID robustness
python research/mcxe006/oos.py                              # OOS, once (refuses to run if results/oos_results.json exists)
```
The frames are cached in `research/mcxe006/cache/` (git-ignored). The first run builds them from the in-window data.
