# INST-PAT-001 (registered 27-Oct-2026, before running) – "how institutions see it": levels + chart patterns
Universes: MCX 7 + NIFTY/BANKNIFTY futures (3h and daily candles), 2022-07 → 2026-10. Option-chain OI walls and order
flow have NO history in our data, so they cannot be backtested (stated, not faked).
Entries (long; short = mirror), all on closed candles, pivots confirmed 3 candles later (no look-ahead):
 P1 double_bottom    two swing lows within 0.5 ATR, ≥ 5 candles apart → close above the neckline (swing high between)
 P2 inv_head_shoulders three swing lows, middle lowest, shoulders within 1 ATR → close above the neckline
 P3 flag             impulse ≥ 3 ATR in ≤ 5 candles, then 3–8 candle pause of ≤ 1.5 ATR range → close above the pause
 P4 squeeze          10-candle range ≤ 2.5 ATR → close above it with volume > 1.5×
 L1 week_level       (daily only) close above last week's high with volume > 1.5×
 L2 pivot_reject     touch of classic floor pivot S1 (long) / R1 (short) and close back beyond it (reversal)
Each with and without the EMA200 side filter (12 rules × 2 timeframes), and LIVE breakout + pattern confirmation
(breakout only when a P1–P4 pattern completed in the last 10 candles).
Exits = live exits (3h: stop 2 ATR, 50% at 1R + stop to entry, trail 3; daily: stop 1.5 ATR, trail 3, EMA20 trend exit).
Full costs, roll days skipped. Measured in ₹ per lot.
PASS: ≥ 40 trades in each period, avg ₹/lot > 0 at 2× costs in design (< 2024-07) AND hold-out,
and ≥ 6 of 9 instruments positive in the hold-out. Win rate reported; 80-90% is the user's goal, not a pass condition.
