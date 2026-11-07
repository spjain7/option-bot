# MCXE-005 data-quality audit

## Coverage actually used (trade dates per cell, from `results/trades_*.parquet`)

| Cell | Instruments | First trade | Last trade | Trades DEV / VALID / OOS |
|---|---|---|---|---|
| MCX intraday (15m, 30m) | 7 | 2025-11-05 | 2026-11-03 | 378,419 / 205,058 / 208,232 |
| MCX positional / overnight (1h, 4h, 1d) | 7 | 2025-11-10 | 2026-11-03 | 85,562 / 49,382 / 50,643 |
| NSE futures intraday (1h) | 179 | 2025-11-04 | 2026-10-22 | 862,091 / 493,678 / 508,468 |
| NSE futures daily | 209 | 2026-02-04 | 2026-11-05 | 136,961 / 137,773 / 138,658 |
| NSE cash daily | 612 | 2026-02-03 | 2026-11-04 | 167,920 / 180,783 / 183,555 |
| NSE cash intraday (15m, 1h) | 218 | 2025-11-11 | 2026-11-06 | 4,508,446 / 2,484,298 / 2,372,330 |

- Every cell ran with **0 errors** (`results/errors_*.txt` are empty).
- No data from before a market's window start was loaded. Data is clipped first, and indicators are computed after.

## Issues found (severity, what it affects, how it was handled)

1. **Warm-up eats DEV on daily cells (HIGH).**
   - The 60-bar warm-up means daily strategies cannot trade before Feb-2026. DEV is therefore about 3 months, not 6.
   - The production S4 rule (EMA200) cannot signal until about Sep-2026, so the exact rule has no DEV or VALID data at all.
   - Handling: reported. S4 was studied through a labelled EMA50 proxy. No older data was used, as the 1-year rule requires.
2. **OI source differs (HIGH for S4).**
   - PETRONET 2-Nov OI change: +1.88 % from NSE bhavcopy versus +2.42 % from Angel in production.
   - This one difference decides whether the signal fires (the threshold is 2 %).
   - Research uses bhavcopy OI of the same contract only (no change computed across a roll), so backtested S4 signal sets can differ from live ones.
3. **Survivorship in instrument lists (MEDIUM).**
   - NSE cash and futures universes come from today's symbol lists (Angel intraday) or from liquidity inside the window (bhavcopy daily).
   - Stocks removed from F&O during the year are partly missing from the intraday cells.
   - Effect: results lean slightly optimistic. Not corrected.
4. **Close semantics (LOW–MEDIUM).**
   - The bhavcopy close is the official close-auction price. Production daily bars are built from Angel 1-hour bars, whose last bar close can differ slightly.
   - The research fixtures reproduce production signals, so the effect on the three trades is nil. Small differences remain possible elsewhere.
5. **MCX 5-minute data ends 2026-11-03 (LOW).** MCX OOS ends there, matching the MCXE-004 window reference date.
6. **Rolls and back-adjustment (handled).**
   - Futures daily series are point-in-time front month and back-adjusted by the roll gap.
   - Positional trades are force-exited before a roll, and overnight trades never span one.
7. **Corporate actions (MEDIUM, not checked).**
   - Bhavcopy prices for NSE cash are not adjusted for splits or bonuses.
   - Split or bonus days were not screened out, so a few NSE cash daily trades may be distorted.
   - Futures are back-adjusted only for rolls.
   - The intraday Angel series are as delivered.
8. **Intraday timestamps (handled).** Bars are labelled by their start time. Signals act at the next bar's open. Session-end square-off is 15:15 for NSE intraday cells.
9. **Operational data quality in production (HIGH, out of scope to fix).**
   - The live loop logged "quote timestamp in the future (max skew 60s)" and postponed pending checks on 4-Nov.
   - The scanner did not run during market hours on 2-Nov and 3-Nov.
   - Covered in EXISTING_STRATEGY_ANALYSIS.md.

## Costs

- Costs come from `research/mcxe003/cost_model` (brokerage, STT/CTT, exchange, GST, stamp, plus slippage).
- Every result is also shown at 2× cost.
