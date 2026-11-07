# MCXE-007 strategy discovery report: daily breakouts / breakdowns + H1.12L shadow tracking

**Branch:** `exp/strategy-program-001`.
- Freeze commit: aca7411. Report commit: see the final push.
- Production `main` = bc3153e6, unchanged.
- Research only: no alerts, no orders, nothing deployed.

## 1. H1.12L shadow setup status
- **Built and tested; collecting is blocked on data.**
  - The research-only tracker `shadow/h112l_tracker.py` uses the frozen MCXE-006 code unchanged.
  - Its replay reproduces **all 306** MCXE-006 H1.12L trades. R, MAE and MFE are identical for the 236 DEV + OOS trades.
  - Tests: `tests/test_shadow_tracker.py`, 4 of 4 passed.
- **A frozen detail was preserved, not "fixed":** H1.12L was simulated as the two-sided rule with SELL legs discarded afterwards. A BUY is therefore skipped while the rule's own untraded SELL leg would still be open. The tracker logs those legs as `sell_leg_blocking`.
- **Forward trades so far: 0.**
  - Forward data begins 2026-11-04, and the research MCX store ends 2026-11-03 23:00.
  - Refreshing it needs the Angel candle download, which needs broker API credentials that this research environment does not have. **This is blocked; see section 7.**
  - Checkpoint 1 (≥ 30 trades on ≥ 20 dates) has not been reached.

## 2. Daily MCX results (7 commodities, 56 experiment rows)
- **Samples are the binding limit.** 47 of 56 rows have fewer than 20 trades in DEV or in VALID.
- **BUY side:** the median 2× expectancy was +0.56R in DEV and −0.18R in VALID.
- **SELL side:** the mirror image, −0.29R in DEV and +0.18R in VALID.
- So results follow the commodity regime, not the rule.
- **Best-looking rows:** NR4 / NR7 / inside-day breakouts with a structural stop (MC_nr4s/L: DEV +0.93R, VALID +0.13R, 48 / 39 trades).
  - Random MCX long entries with the same exits earned +0.38R, and the strategy did not clear the random-control 95th percentile. This is market exposure.
  - Without the top 5 trades the result is negative. **Rejected.**

## 3. Stock futures results (209 point-in-time symbols, 88 rows)
- **Classic breakouts fail in this window.**
  - BUY breakouts lost in DEV and VALID for every lookback (5–50 days), buffer, intraday-breach entry, gap rule, filter (EMA, ADX, HH/HL, market trend, relative strength), volume / OI filter and exit (X0–X4, swing stop). Median 2× expectancy: −0.23R DEV, −0.18R VALID.
  - SELL breakdowns: +0.07R DEV → −0.23R VALID (regime flip).
- **The one stock-specific effect: failed breakdown → BUY.**
  - Random long entries in the same stocks and periods: −0.20R. Failed-breakdown BUYs: +0.08 to +0.14R.
  - That is about +0.3R of entry value. It is not market exposure: NIFTY traded on the same dates lost −0.44R.
  - With a beta-1 NIFTY hedge and OI rising on the reclaim day (SE_failed_oiup_h/L), it passed every pre-registered freeze test. **It then failed OOS** (section 5).

## 4. Index futures results (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50; 58 rows)
- **INSUFFICIENT DATA.** 54 of 58 rows have fewer than 20 trades in DEV or VALID (5 instruments × about 120 sessions per period).
- SELL rows looked good in DEV (median +0.53R) and failed in VALID (−0.26R).
- No index candidate could be frozen without widening the window, which is not allowed.

## 5. Best daily candidate: SE_failed_oiup_h/L (frozen, OOS once, REJECTED)

**Rule**
- In stock futures, a close back above the prior 20-day low within 3 sessions of breaking below it, with OI of the same contract rising that day.
- Entry: BUY at the next open, plus a short of equal notional NIFTY futures.
- Exit: 2-ATR stop, 4-ATR trail, 40 sessions.

**Results**

| | Trades / dates | Win % | Avg win / loss | Exp 1× | Exp 2× | PF | Max DD | 95 % CI (1×) |
|---|---|---|---|---|---|---|---|---|
| DEV | 140 / 31 | 51.4 | +0.90 / −0.50 | +0.223 | +0.185 | 1.92 | 5.6R | DEV + VALID [+0.04, +0.36] |
| VALID | 65 / 25 | 53.8 | +0.73 / −0.55 | +0.143 | +0.104 | 1.57 | 3.5R | |
| **OOS** | **178 / 37** | **33.7** | **+0.68 / −0.59** | **−0.162** | **−0.206** | **0.59** | **37.0R** | **[−0.38, +0.03]** |

**OOS detail**
- Rupees (stock leg, 1 lot): about −₹5,590 per trade; −₹9.9 lakh across 178 trades.
- Exposure: about 16 open positions on average. Turnover: about 59 trades per month.
- Without the top 1 / 3 / 5 trades: −0.22 / −0.25 / −0.28R.
- Random hedged entries: −0.28R (95th percentile −0.20R). The strategy kept a small relative edge (+0.07R) but lost money in absolute terms.
- Every OOS month was negative, and October lost −23R on 105 trades.

**Why it failed**
- The OOS period was a broad sell-off in stocks, which generated nearly 3× the VALID signal count.
- Reclaimed breakdowns kept failing.
- Stocks also underperformed NIFTY, so the hedge lost as well (hedge leg −0.08R per trade).

## 6. Rejected candidates and why
See FAILED_STRATEGIES_AND_LESSONS.md and EXPERIMENT_REGISTER.csv (202 rows: 30 KEEP, 130 DROP, 42 baselines).

## 7. Data gaps and blocked research
See DATA_QUALITY_AUDIT.md. The main items:
- **Blocked:**
  - forward MCX data for the shadow tracker (needs broker API credentials);
  - Angel OI history (the research store has no OI column), so exchange vs broker OI can be compared only on the three recorded production values.
- **Insufficient inside the approved window:**
  - index futures and MCX daily samples;
  - EMA100 / EMA200 filters, which cannot be warmed up.
- **Defect found:** the front-month rule rolls early in the last 3 sessions of the dataset (it counts the remaining trading days from the dataset itself). This affects only 4–6 Nov 2026 (OOS end) and is documented.

## 8. Production changes that would help (recommendations only, NOT implemented)
1. **Persist the MCX 5-minute candles the live bot already downloads to a research-readable store** (read-only export). Without this, H1.12L shadow tracking cannot collect forward trades.
2. **Log the Angel OI value used for every S4 decision next to the exchange bhavcopy OI.** PETRONET 2-Nov passed the 2 % rule on Angel (+2.42 %) but not on the bhavcopy (+1.88 %).
3. **Earlier MCXE-005 recommendations still apply:**
   - run the scanner in market hours;
   - make the clock-skew guard tolerant;
   - judge S4 activation on the official open.

## Conclusion
- **Validated: none. Profitable after costs, out-of-sample: none. "80–90 % accurate": not supported.** The best in-sample daily candidate won 51–54 % in DEV/VALID and 34 % in OOS.
- **The approved one-year window is now exhausted for daily breakout research:**
  - its OOS period has been used by MCXE-005, MCXE-006 and MCXE-007;
  - MCX and index daily samples are too small.
- Further progress needs **forward data**:
  - H1.12L shadow tracking (once the data refresh exists);
  - a new, untouched period for a pre-registered retest of the failed-breakdown idea, which was the only daily effect that beat random entries in all three periods.

## Reproduce
```bash
git checkout exp/strategy-program-001
python research/mcxe005/tests/test_preservation.py           # production regression (6 tests)
python research/mcxe007/tests/test_shadow_tracker.py          # shadow tracker replay + safety (4 tests)
python research/mcxe007/shadow/h112l_tracker.py               # rebuild ledger_h112l.csv / STATUS.md / data_issues.csv
python research/mcxe007/lab7.py fam A B C D E G               # 202 DEV/VALID rows (OOS masked); frames cached on first run
python research/mcxe007/lab7.py run SE_failed_oiup SE_failed_h SE_failed_oiup_h SE_failed_X1h SE_failed_w5h SE_failed_volh   # stage 3 + hedge
python research/mcxe007/lab7.py controls SE_failed_oiup_h/L   # random-entry + market-direction controls
python research/mcxe007/oos7.py                               # OOS – refuses to run again (results/oos7_results.json exists)
```
Note: `lab7.py fam E` also runs every stage-3 E-family row. `fam D` and `fam C` include the stage-3 D and C rows.
