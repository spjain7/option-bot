# SR-001 (registered 27-Oct-2026, before running) – support / resistance levels (daily, weekly, monthly) for calls
User: 80-90% accuracy; use support/resistance for SL and target; use volume + OI in every decision; never miss weekly
and monthly breakouts / breakdowns.
Signals on DAILY closed candles (MCX 7 + NIFTY/BANKNIFTY futures; STOCKS 181 with daily OI), Jul-2022 → Oct-2026.
Levels known before the signal day: previous day (PDH/PDL), previous week (PWH/PWL), previous month (PMH/PML),
classic monthly pivot (P, R1, S1).
Setups (long; short = mirror):
 WB  weekly breakout   : first daily close above PWH
 MB  monthly breakout  : first daily close above PMH
 WS  weekly support    : low touches PWL (≤ 0.25 ATR beyond) and the day closes back above it (bounce)
 MS  monthly support   : same at PML
 PS  pivot support     : same at monthly S1
Filters: none / vol (> 1.5×) / mtf (weekly close above weekly EMA20 AND monthly close above monthly EMA10 – trend on
both higher timeframes) / vol+mtf / oi (stocks: day OI ≥ +2% with price up = long buildup) / oi+mtf.
Stops: LV = beyond the level (breakout: back below the broken level; bounce: below the tested level) − 0.3 ATR;
       A1.5 = 1.5 ATR.
Targets: NX = next level in the trade direction (e.g. PMH after a weekly breakout, PWH after a weekly-support bounce;
         ≥ 0.5R, else 1R) · R0.5 · R1 · R2.
One position per instrument, max 20 sessions, full costs, roll / rollover handled as before.
PASS: avg ₹/lot > 0 at 2× costs in BOTH periods (design < 2024-07-01, hold-out after), ≥ 40 trades per period,
≥ 60% of instruments positive in the hold-out. Win % reported – the goal is the highest win % among PASSING rules.

## RESULT (27-Oct-2026): 0 of 160 (MCX + index) and 0 of 240 (stocks) passed all rules
- Highest win rates: weekly / monthly support bounces and breakouts with a 0.5R target – 64-74% wins, but LOSING
  (e.g. stock monthly-support bounce + volume + trend: 67% / 64% wins, -₹138 / -₹4,045 per lot). No 80% setup exists.
- Near-pass (profitable in both periods at 2× costs, but only 5 of 9 instruments positive):
  MCX+index MONTHLY breakout + weekly & monthly trend, SL 1.5 ATR, T 2R: ₹6,030 / ₹24,459 · win 50% / 46%  → added live, labelled
  MCX+index WEEKLY-high breakout + trend, SL 1.5 ATR, T 2R: ₹2,719 / ₹24,708 · win 46% / 45% (the 20-week breakout is already live)
- S/R as SL (beyond the level) or as target (next level) did not beat ATR-based SL / R-multiple targets.
