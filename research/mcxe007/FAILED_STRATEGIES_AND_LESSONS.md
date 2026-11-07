# MCXE-007 failed strategies and lessons

**Register:** 202 rows in `EXPERIMENT_REGISTER.csv`, each with its parent, the one change made, DEV / VALID metrics at 1× and 2× cost, CI, top-1 / 3 / 5 removal, concentration and the decision.

## By family

| Family | Markets | What happened | Main reason for failure |
|---|---|---|---|
| A Classic Donchian (N 5–50, breach vs close, buffer, gap rule) | All | Stock BUYs negative in both periods for every variant. Stock SELLs and index SELLs positive in DEV, negative in VALID. MCX tiny samples. | Regime dependence; in stocks, breakouts failed (gross −0.2R) |
| B Trend filters (EMA20/50, ADX, HH/HL, market trend, relative strength) | All | No filter turned a negative baseline positive in both periods. Market-trend filtering left too few dates (STK BUY: 5 DEV dates). | Filters cut trades without changing the sign |
| C Compression (NR7, NR4, inside day, ATR squeeze) | All | MCX and index versions were positive in both periods only with structural stops, and were fat-tailed. Stock versions were negative or zero. | Market exposure (MCX); top-5 dependence; insufficient sample |
| D Volume / OI | STK, IDX | OI-down (unwinding) breakdown SELLs: +0.33R DEV, +0.05R VALID, but n = 19 in VALID, and they lost to NIFTY shorts on the same dates. OI-up breakouts were negative. | Market-direction control; sample |
| E Retest | All | Negative or zero. | No continuation after retests in this window |
| E Failed breakout / breakdown | STK | **BUY side beat random entries by about +0.3R in DEV/VALID** and passed the freeze bar when hedged. SELL side: +0.48R DEV, −0.09R VALID. | OOS sell-off: the hedged BUY lost −0.21R at 2× |
| G Exits (2R target, 5-day time stop, partial 1.5R, swing stop) | All | Changed expectancy by ±0.1R at most and never flipped a sign. A partial exit raises win % slightly and lowers expectancy (as in MCXE-006). | Exits cannot rescue an entry with no edge |

## Lessons
1. **The one-year window gives about 30–60 independent dates per period on daily data.**
   - Daily cross-sectional signals cluster on market-wide days (e.g. 203 trades on 42 dates).
   - Day-clustered CIs are therefore wide, unless the market factor is removed (the hedge tightened the CI from [−0.33, +0.54] to [−0.03, +0.33]).
2. **Controls matter more than in-sample expectancy.**
   - MCX daily breakouts looked strong (+0.6 to +0.9R DEV), but random MCX longs made +0.3 to +0.4R.
   - Stock failed-breakdown BUYs looked weak (+0.08R), but random longs made −0.20R.
3. **A relative edge is not an absolute profit.**
   - In OOS the failed-breakdown BUY still beat random hedged entries (−0.21R vs −0.28R) but lost money.
   - Stocks underperformed NIFTY in OOS, so the hedge lost too.
4. **Win rate:** no daily construction reached even 60 % in VALID at a positive expectancy. The 80–90 % accuracy target has no support in this data.
5. **Index futures and MCX daily cannot be judged inside one year** without widening the window. That is not allowed, so they stay INSUFFICIENT DATA.
