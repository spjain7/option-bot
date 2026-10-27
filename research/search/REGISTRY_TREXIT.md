# TREND-EXIT-001 (registered 27-Oct-2026, before running) – exit on trend change instead of waiting for the stop
User: "update if trend changes in any script instead of waiting for stop loss".
Base = the live exits after EXIT-001: 3h = stop 2 ATR, 50% at T1 + stop to entry, trail 3 ATR; daily = stop 1.5 ATR, trail 3.
Added exit (on a closed candle of the same timeframe, exit at that close):
 e20  close crosses EMA20 against the trade      e50  close crosses EMA50 against the trade
 ch10 close beyond the opposite 10-candle extreme (long: below the 10-candle low)
Accept a trend exit only if it beats the base on avg ₹/lot at 2× costs in BOTH design (< 2024-07) and hold-out.

## RESULT (27-Oct-2026), avg ₹/lot at 2× costs design / hold-out
daily base 31,778 / 67,524 · e20 32,890 / 72,257 (worst loss -7.4L → -5.0L) · ch10 33,217 / 71,344 · e50 31,885 / 69,993
3h    base 5,390 / 22,119 · e20 5,210 / 20,410 · e50 5,338 / 22,583 · ch10 5,173 / 21,779
→ daily: e20 PASSES (better in both, smaller worst loss; design only 32 trades) → adopted.
→ 3h: no trend exit passes in both periods → not used (T1 half-booking + stop-to-entry already protects).
