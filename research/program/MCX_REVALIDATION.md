# MCX revalidation record (ROLLCHECK-001, 6-Nov-2026)

**Adjustment method.** The 20-year MCX daily file is an unadjusted front-month stitch without contract labels. Roll days are inferred per commodity from the flagged 2022-26 hourly data (roll months + usual day of month; exact 1h switch days where known; >25 % open gaps treated as glitches). *Adjusted* = ratio back-adjustment at each roll (prices before a roll × prev close / roll-day open), trades held through rolls as a trader who rolls would. *Roll-exit* = conservative alternative, every trade closed at the last close before a roll. Entry next open (RSIX: buy-stop), stop first, 2× costs. Periods 2006-12 / 2013-19 / 2020-26; **out of sample = 2020-26** (all rules were designed on 2022-26 or earlier data, so 2006-19 is also out of sample for most).

| rule | original R (n) | corrected R adjusted (n) | win % | PF | max DD R | 2006-12 | 2013-19 | 2020-26 (OOS) | roll-exit R | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| BO_1d (20d high, ADX>=25) | +0.16 (507) | +0.02 (541) | 43 | 1.03 | 65.7 | -0.09 | -0.10 | +0.25 | +0.09 | fails – prepared logged-only (branch prep/bo1d-mcx-logged-only, needs approval) |
| RB_MCX_1d_BO55_BUY | +0.47 (141) | +0.32 (145) | 48 | 1.55 | 8.4 | +0.24 | +0.49 | +0.35 | +0.41 | holds |
| RB_MCX_1d_RETEST_BUY | +0.27 (638) | +0.23 (672) | 45 | 1.38 | 17.2 | +0.14 | +0.12 | +0.40 | +0.15 | holds |
| RB_MCX_1d_RSIX_BUY | +0.20 (262) | +0.16 (250) | 45 | 1.24 | 22.6 | +0.08 | +0.05 | +0.36 | +0.07 | holds |
| BO_1w (20-week high) | +0.40 (183) | +0.29 (218) | 52 | 1.64 | 14.2 | +0.35 | +0.04 | +0.43 | +0.10 | holds |
| BO_1M (month close > prev high) | +0.61 (85) | +0.89 (93) | 62 | 4.07 | 9.0 | +0.82 | +0.39 | +1.32 | +0.14 | holds |

RSIX exit (RSIX-TRAIL-001, independent simulator): 3R target n 251, 43.8 % win, +0.12R, PF 1.17, DD 28R · 3-ATR trail n 255, 39.6 %, +0.19R, PF 1.29, DD 34R. Paired difference +0.10R, 90 % CI [−0.004, +0.21]; trail better in 9 / 21 years and worse in 2020-26 → **not promoted**; 3R stays.
