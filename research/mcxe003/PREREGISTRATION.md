# MCXE-003 pre-registration (written and committed BEFORE any MCXE-003 result was computed, 7-Nov-2026)

## Stage 1: information (event study)
- **Unit (cell):** market × instrument × timeframe × detector event × side × swing method (where the detector uses swings).
- **Event time:** the close of the bar on which the pattern became knowable, using only data up to and including that bar.
- **Measures, in ATR(14) of the signal timeframe, gross of costs:**
  - fwd_entry(h): from the next bar's open to the close h bars later. **Primary horizon h = 6 bars** for intraday and BTST
    (next session for daily); 5 sessions for positional.
  - fwd_detect(h): from the signal close. Used only to detect information that is already spent before entry.
  - MFE / MAE over 12 bars. Descriptive only.
- **Matched control:** up to 20 non-event bars of the same instrument, timeframe, bar time-of-day (intraday) and calendar
  quarter, with the same side sign. excess = event − control mean.
- **Statistics:** excess is averaged per day (intraday) or per date (daily), and a t-test is run across days. Effective n = days.
  BH-FDR is applied over *all* cells of a market × horizon. A family-level max-statistic (5,000 day-block sign flips) is
  added for the family verdict.
- **Periods:**
  - MCX intraday: DEV < 2025-04-01 ≤ VALID < 2026-01-01 ≤ OOS (to 2026-11-03).
  - NSE cash intraday: DEV < 2025-07-01 ≤ VALID < 2026-01-01 ≤ OOS.
  - Daily / overnight / positional: DEV < 2023-01-01 ≤ VALID < 2025-01-01 ≤ OOS. Where data starts in 2022 (MCX bhavcopy):
    DEV < 2024-01-01 ≤ VALID < 2025-07-01 ≤ OOS.
  - **OOS is not read until the stage-2 choices are frozen.**
- **Stage-1 pass (to stage 2):**
  1. n_days(DEV) ≥ 40;
  2. DEV excess > 0 with BH q < 0.10;
  3. VALID excess > 0;
  4. raw gross fwd_entry(DEV + VALID) ≥ 2 × the realistic round-trip cost in ATR (feasibility at stress cost).
- **Failure labels:** TOO_FEW · NO_INFO (DEV excess t < 1) · WRONG_SIGN (DEV excess t < −2) · NOT_SIGNIFICANT (q ≥ 0.10) ·
  UNSTABLE (VALID ≤ 0) · TOO_SMALL_VS_COST (fails 4) · INFO_SPENT_BEFORE_ENTRY (fwd_detect excess t ≥ 2 but fwd_entry
  excess t < 1, a diagnostic label).

## Stage 2: execution (survivors only)
- **Menu, fixed:**
  - entry {next open, stop order at the trigger within 3 bars, cancelled if the invalidation trades first};
  - stop {pattern invalidation ± 0.1 ATR (clamped 0.3–3 ATR), 1.5 ATR};
  - exit {2R, end of session / time stop of 12 bars, 2-ATR trailing}.
- **Execution rules:**
  - stop is checked before the target within a bar;
  - a gap through the stop fills at the open;
  - one position at a time per stream;
  - intraday square-off at the session's last bar; MCX: no entries after 22:00; NSE cash: no entries after 14:45, square-off 15:15.
- **Costs:** realistic (MCX: fees + 1.5 ticks/side; NSE cash intraday: 0.163 % round trip; delivery 0.393 %; NSE futures: fees +
  0.05 % slippage/side), and 2× stress.
- **Matched control trades:** the same execution at control bars, with stop distance set to the event's median stop distance in ATR.
- **Selection:** on DEV + VALID combined, choose the execution with the best mean net R at 2× cost (n ≥ 30). Freeze, then run OOS once.
- **Accept as "potentially promising, unvalidated":**
  - OOS net R at 1× cost > 0 and at 2× cost > 0;
  - OOS beats the matched control trades;
  - bootstrap (day-block) 95 % CI of OOS net R at 1× cost above 0;
  - adjusted for selection with a max-statistic over all stage-2 survivors.

Nothing that passes goes beyond shadow / log-only. No production change, no Telegram, no orders.

## Addendum A (7-Nov-2026, before any result)
- **NSE stock-futures 1-hour periods:** the Angel 1-hour data runs 2022-07 → 2026-10 for most names, so the periods are
  DEV < 2024-07-01 ≤ VALID < 2025-07-01 ≤ OOS. This matches the earlier Angel splits. Earlier work used this data for
  breakout / EMA / MACD families, so those families are marked contaminated.
- **Swing methods:** MCX uses f2, f3, f5, z15 and z3. NSE uses f3 and z3, for compute reasons. A cell includes its swing
  method, so every method counts in the BH-FDR denominator.

## Addendum B (7-Nov-2026): estimator fix, made before any stage-2 decision and without reading OOS
The first stage-1 run averaged per-day means. That gives a day with one event the same weight as a day with 30 events,
which changes the quantity being estimated. A trader who takes every signal earns the event-weighted mean.
- **Example:** MCX 30-minute 20-bar breakout BUY earned +0.05 ATR per event, but its mean of daily means was −0.29.
- **Fix:** use the event-weighted mean with a day-clustered (cluster-robust) standard error. Effective n is still the number of days.
- All stage-1 tables were recomputed with this estimator.

## Addendum C (7-Nov-2026): control fix, before any stage-2 decision and without reading OOS
The first matched control used a calendar-quarter window: the same minute of day within the same quarter, and for MCX daily
the same quarter. A quarter's realised drift comes partly from bars **after** the event, and it is correlated with the
pattern's own context: falling channels form in falling quarters. That inflated counter-trend patterns.
- **Example:** the MCX daily "channel exhaustion BUY" showed +0.28 ATR excess at 5 sessions, but its raw move was only
  +0.05, because the quarter control was −0.23 there.
- **Fix:** match the control over the whole research period instead (DEV, VALID or OOS separately). Intraday uses
  minute of day × period; MCX daily uses commodity × period.
- **Unchanged:** NSE daily keeps the cross-sectional same-day control, which has no time-series drift problem.
- All events and stage-1 tables were recomputed with the fixed control.
