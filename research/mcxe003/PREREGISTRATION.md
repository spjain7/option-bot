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
