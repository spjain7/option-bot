# DATA-AUDIT-001 — MCX research data checked against the official MCX bhavcopy (4-Nov-2026)

The directive was to get the data right before searching for more strategies. Here, the Angel One vendor-stitched MCX front-month series are compared, day by day, with the MCX bhavcopy, the exchange's official daily file for each contract. The bhavcopy has 1,115 sessions, from 1-Jul-2022 to 3-Nov-2026.

Re-run with `python -m research.data_audit` and then `python -m research.dq_retest`. The audit writes `manifest.json`, `rolls_true.csv` and `match_*.csv.gz`.

## Observed (measured)

| Commodity | Status | O/H/L match | Missing sessions | Volume ratio | Illiquid-contract days | Rolls | True roll gap, median | Sessions Angel stays on old contract after OI roll | Angel daily-close definition change | 1h days off > 0.5 % |
|---|---|---|---|---|---|---|---|---|---|---|
| GOLD | DEGRADED | 99.7% | 43 (hole Aug–Oct 2022) | 1.00 | 9.9% | 25 | 0.85% (max 2.3%) | 11 | Feb–Mar 2024* | 5 |
| SILVER | DEGRADED | 99.2% | 2 | 1.00 | 8.3% | 22 | 1.69% (max 3.3%) | 7.5 | 27-Feb-2024 | 13 |
| CRUDEOIL | ACCEPTABLE | 98.7% | 3 | 1.00 | 1.9% | 52 | 0.68% (max 3.9%) | 3 | 27-Feb-2024 | 20 |
| NATURALGAS | ACCEPTABLE | 99.1% | 4 | 1.00 | 4.2% | 51 | **5.2%** (max 41%) | 4 | 4-Mar-2024 | 25 |
| COPPER | DEGRADED | 99.5% | 7 | 1.00 | 17.4% | 51 | 0.57% (max 3.2%) | 8 | 28-Feb-2024 | 7 |
| ZINC | DEGRADED | 99.7% | 10 | 1.00 | 17.5% | 51 | 1.14% (max 6.5%) | 7 | 27-Feb-2024 | 6 |
| ALUMINIUM | DEGRADED | 99.2% | 17 | 1.00 | 15.6% | 51 | 1.23% (max 5.8%) | 7 | 1-Mar-2024 | 12 |

\* The GOLD detector is noisier (it reports 7-Jan-2025). The month-by-month match shows the change in March 2024.

1. **Prices are correct; the construction is the problem.**
   - Angel's open, high and low equal the official values on 98.7–99.7% of days.
   - Volume equals the contract's official volume in lots (median ratio 1.00).
   - Angel holds no open-interest history for MCX; the bhavcopy is the only OI source.
2. **Angel's series stays on the expiring contract too long.**
   - It always uses the nearest expiry, up to the expiry day.
   - It stays there for 3–11 sessions after the market's open interest has moved to the next contract.
   - For gold and base metals, 8–18% of all days are priced from a contract with less than 20% of the day's volume (tender or delivery days).
3. **Every roll leaves a raw price jump.**
   - Median jump per roll: 0.6–1.7%. NATURALGAS: 5.2%.
   - The research gap estimator (`research/roll_adjust.py`) cannot be checked properly here, because its proxy files are not in this environment and it falls back to the raw jump. The exact gaps are now available, so the estimator is no longer needed from Jul-2022 onward.
4. **Angel changed what its daily "close" means around 27-Feb-2024.**
   - Before that date it is the last trade, the same as the last 1-hour close.
   - After it, it is MCX's official closing price, which differs from the last trade by about 0.1–0.3%.
   - Daily-close rules backtested on Angel data before 2024 therefore used a different close from the one live calls use now.
5. **The 1-hour files cover most of each day but not all of it.**
   - Daily high and low rebuilt from 1-hour bars match the daily file on 91–98% of days.
   - The differences are mostly 1–3 ticks, but 6–25 days per commodity are off by more than 0.5%. For example, CRUDEOIL on 11-Sep-2026 has a first-hour open about 7% away.
   - The 1-hour last close equals the daily close only before Feb-2024 (see 4).
6. **Before Jul-2022 nothing can be checked independently.**
   - There is a data hole from Dec-2021 to Apr-2022.
   - ZINC and ALUMINIUM 2020 have flat bars and volume of 1 or less.

## What this changes (measured re-test, same rules, same period)

The MCX_HAMMER rules (frozen, live) were run on two series:

- **Angel raw:** Angel's stitched data, raw.
- **Verified:** the bhavcopy series. It follows the open-interest leader, uses the exact roll gaps and is back-adjusted.

| | Trades | Win % | Avg R after costs | PF |
|---|---|---|---|---|
| Angel raw | 423 | 44.7% | +0.29 | 1.51 |
| **Verified** | **413** | **41.2%** | **+0.20** | **1.33** |

- **By year (Verified):**
  - 2022: −0.10R
  - 2023: −0.05R
  - 2024: +0.38R
  - 2025: +0.37R
  - 2026: +0.29R
  - From 2024 onward the two series give almost the same result, because the close definitions are the same.
- **By commodity (Verified):** SILVER −0.08R and NATURALGAS −0.13R. Both were positive on raw data.
- **Angel raw trades that had a roll inside the trade:** +0.56R, against +0.23R for the rest. Upward roll jumps (contango) flatter BUY results.
- **My rebuild versus the registry:** my rebuild of the rules gives 423 trades on Angel data, not the registry's 333. The comparison above is like-for-like, but the original study's exact trade list was not reproduced.

**Registry changes:**

- MCX_HAMMER stays LIVE, because it still meets the rule: more than 70 trades, positive after costs, and positive in the latest period.
- Its tier drops from A to B.
- Its evidence text now gives the verified figures.
- The claim "every year and all 7 commodities positive" was false, and has been removed from the call message.
- No commodity was excluded. Dropping SILVER or NATURALGAS on about 60 trades each would be fitting to the sample.

## Statuses and the gate

`research/dq_gate.py` reads `manifest.json`. `research/search/strategy_search.load` now:

- labels every dataset with its status;
- refuses INVALID data.

| Data | Status |
|---|---|
| Bhavcopy continuous daily from 2022-07 (`research/continuous_verified.py`) | VERIFIED |
| Angel daily, CRUDEOIL and NATURALGAS | ACCEPTABLE |
| Angel daily, others | DEGRADED |
| Angel intraday | DEGRADED (only checked through its daily totals; rolls uncorrected) |
| Anything before Jul-2022 | DEGRADED |
| NSE index and stocks | DEGRADED (NSE bhavcopy audit still to do) |

A positive result found on DEGRADED data needs a VERIFIED re-test before it can affect a status.

## Live system (assumption, not yet changed)

- Live MCX calls move to the next contract when 4 or fewer trading days remain.
- At 5 days left, the expiring gold or base-metal contract still has 43–51% of the volume (median) but only 11–28% of the open interest.
- Rolling one day earlier for GOLD, SILVER and the base metals would put calls on the contract that carries most of the volume. This is borderline, so it is a proposal only.

## Next

1. Re-test the other LIVE MCX daily rules on the verified series: BO_1d_BUY and BO_1m_BUY.
2. Back-adjust the Angel 1h, 3h and 4h series with the exact gaps on Angel's own switch days, and flag illiquid days. Then re-test FH_MCX_BUY, MCX_EMA1348 and E_BUY_v1.
3. Audit NSE index and stock futures against the NSE bhavcopy.
