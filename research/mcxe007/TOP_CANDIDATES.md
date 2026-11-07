# MCXE-007 top candidates

**No candidate is validated or profitable out-of-sample.**

| Rank | ID | Market / side | DEV 2× | VALID 2× | DEV + VALID CI | Controls | OOS | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | SE_failed_oiup_h/L | Stock futures, failed breakdown → BUY, OI up, NIFTY-hedged | +0.185R (140 trades / 31 dates) | +0.104R (65 / 25) | [+0.04, +0.36] | beats random hedged (−0.06R, p95 +0.02R) and NIFTY on the same dates (−0.44R) | **−0.206R at 2×, 178 trades, CI [−0.38, +0.03]** | **REJECTED** |
| — | SE_failed_volh/L | same family, reclaim on volume > 1.5×, hedged | +0.159R (47 / 20) | +0.349R (27 / **12 dates**) | [+0.06, +0.48] | not run | not evaluated | INSUFFICIENT DATA (VALID dates < 15) |
| — | SE_failed_h/L | failed breakdown, hedged, no OI filter | +0.149R (312 / 44) | +0.049R (184 / 40) | [−0.03, +0.33] | beats random hedged (−0.08R) | not evaluated | not eligible (CI includes 0) |
| — | MC_nr4s/L | MCX NR4 breakout BUY, structural stop | +0.933R (48 / 34) | +0.126R (39 / 26) | [−0.33, +1.76] | random MCX longs +0.38R; below the random 95th percentile | not evaluated | REJECTED: market exposure, top-5 dependent |
| — | IC_nr4s/S | Index NR4 breakdown SELL, structural stop | +0.977R (39 / 22) | +0.123R (29 / 20) | [−0.70, +2.57] | random +0.36R | not evaluated | REJECTED: CI includes 0, top-5 dependent |

**Full specification of rank 1:** see FROZEN.md. Its OOS details are in `results/oos7_results.json`, and its trades in `TRADE_LEVEL_ANALYSIS.csv` (experiment `SE_failed_oiup_h/L`).

**Further forward paper testing:**
- **H1.12L (MCXE-006) remains the only candidate in forward shadow tracking.** It is blocked on data.
- **The failed-breakdown idea is worth a pre-registered retest on a new period**, because it beat random entries in DEV, VALID and OOS. In OOS it was not profitable in absolute terms, so it is not a paper-trading candidate as it stands.
