# MCXE-004 protocol: strict rolling 1-year window (owner rule, 7-Nov-2026)

This protocol is binding for every MCXE-004 script. It is written **before** any MCXE-004 result.
Research only: production, broker, Telegram, alert and shadow settings are not changed.

## 1. Rule
- Only data from the last year is used: the window starts exactly one calendar year before the market's reference date.
  The reference date is the last complete session of the market's primary dataset.
- Nothing older is used for any purpose: samples, tuning, instrument choice, regimes, indicator warm-up, or "historical
  context". The first 60 bars inside the window are warm-up and produce no signals.
- Enforcement: every MCXE-004 loader goes through `research/mcxe004/window.py`. `clip()` drops older rows, and
  `period()` raises an error on any earlier date.
- The window is split chronologically: **DEV first 6 months · VALID next 3 months · OOS last 3 months**.
  OOS is not read before the strategy and execution choices are frozen and committed.
- Too few observations → the strategy is marked **INSUFFICIENT DATA**. The window is never widened.
- Evidence from existing strategies before the cutoff, including MCXE-001…003, the production backtests and the MCXD
  day-trend studies, **is not evidence of profitability**. Their rules may be re-tested as candidate logic inside the window.

## 2. Windows and data (measured by `windows.py`; full table in `windows.csv`)
| Market / use | Dataset | Reference (last complete session) | Start | VALID from | OOS from | Sessions DEV / VALID / OOS | Instruments |
|---|---|---|---|---|---|---|---|
| MCX intraday + daily (daily bars built from 5-min) | Angel front-month 5-min | 2026-11-03 | 2025-11-04 | 2026-05-04 | 2026-08-04 | 127 / 66 / 65 | 7 (LEAD, NICKEL: none) |
| NSE cash BTST / positional | official cash bhavcopy (point-in-time) | 2026-11-05 | 2025-11-06 | 2026-05-06 | 2026-08-06 | 120 / 64 / 63 | 3,090 securities traded (liquid-universe filter applied per day) |
| NSE cash intraday | Angel 5-min, today's 218 liquid names (survivorship) | 2026-11-06 | 2025-11-07 | 2026-05-07 | 2026-08-07 | 121 / 64 / 63 | 218 |
| NSE futures BTST / STBT / positional | official F&O bhavcopy (point-in-time) | 2026-11-06 | 2025-11-07 | 2026-05-07 | 2026-08-07 | 120 / 64 / 63 | 237 stock futures |
| NSE futures intraday | Angel 1-hour, today's list (survivorship) | 2026-10-22 | 2025-10-23 | 2026-04-23 | 2026-07-23 | 122 / 62 / 63 | 181 |

Data notes:
- The Angel MCX 1-hour and daily files end 2026-10-21. They are **not** used: MCX daily and hourly bars are rebuilt
  from the 5-min data (reference 2026-11-03).
- The NSE futures 1-hour data ends 2026-10-22, about two weeks before the bhavcopy. This is kept as its own window and
  is not stretched.
- **No other data needs refreshing to run MCXE-004.** A refresh would only move the reference date. It would be done
  with the research-data workflow outside market hours, and then `windows.py` would be re-run before any result.

## 3. Minimum sample (decided now; failing any rule → INSUFFICIENT DATA)
| Horizon | DEV | VALID | OOS |
|---|---|---|---|
| Intraday (per tested strategy, after one-position-at-a-time) | ≥ 60 trades and ≥ 40 trade dates | ≥ 25 trades | **≥ 30 trades and ≥ 20 trade dates** |
| BTST / STBT (one-night holds) | ≥ 60 trades, ≥ 40 dates | ≥ 25 trades | **≥ 30 trades, ≥ 20 dates** |
| Positional (5-session hold) | ≥ 40 trades, ≥ 25 dates | ≥ 15 trades | **≥ 20 trades, ≥ 15 entry dates**; non-overlapping per instrument |

Feasibility check for positional MCX:
- OOS = 65 sessions × 7 commodities allows at most about 13 non-overlapping 5-session trades per commodity.
- **A single-commodity positional strategy can never reach the OOS minimum.** Single-commodity MCX positional cells are
  marked INSUFFICIENT DATA in advance. Only pooled multi-commodity rules, declared before testing, can be evaluated.

## 4. Statistics and promotion bar (reuses the validated MCXE-003 machinery)
- **Matched controls:** same instrument, same time-of-day (intraday), same period, same exit rule and stop distance.
- **Confidence intervals:** the day-block bootstrap in `research/mcxe003/bootstrap.py`. Decisions use
  `ci95_conservative`, the widest of the block-bootstrap intervals (L = 1, 2, 3, 5 and default) and the cluster t-interval.
- **Selection:** choices are made on DEV + VALID only, BH-FDR over all cells, and a family max-statistic. OOS is run once.
- **Costs:** realistic and 2× stress, with MCX costs at raw contract prices.
- **"Potentially promising, unvalidated" requires all of:**
  - OOS net R > 0 at both 1× and 2× cost;
  - OOS beats the matched controls;
  - OOS `ci95_conservative` lower bound > 0;
  - the minimum sample sizes are met.

  Even then the status is only *paper / shadow candidate*. **Nothing is promoted on this research alone.**

## 5. Contamination statement (honest status of the window)
- MCXE-003 already looked at data inside this window:
  - MCX intraday: its VALID (to 2025-12-31) and OOS (2026) periods, including the diagnostic OOS results for 6 MCX and
    4 NSE-futures families;
  - NSE cash intraday and NSE futures 1h: their VALID and OOS periods.
- So **MCXE-003 detectors and families are not untouched inside this window.** If MCXE-004 re-tests them, the report
  must say so.
- The **truly untouched** evidence for any MCXE-004 choice is forward data after the reference dates. That is the
  paper / shadow period.
- No MCXE-003 or earlier result may be cited as evidence in MCXE-004. They may only be cited as the origin of a hypothesis.

## 6. First candidate questions (from the validation, §E; not yet run)
Pattern-as-overlay on an existing base strategy, inside the window only:
- Base: the Gold/Silver day-trend continuation rule, re-simulated inside the window, with no pre-cutoff evidence.
- Overlay: same-direction pattern events used for selection or entry timing.
- Comparison: paired, on identical days, judged on expectancy after costs, MAE and drawdown.

Expected power is low. The base rule produced about 150 trades a year in 2023-26. Every result will be reported with its
sample size, or marked INSUFFICIENT DATA.
