# INTRA-WIN-002 (registered 23-Oct-2026, before running) – INTRA-WIN-001 + filter layers (trial & error)
INTRA-WIN-001 result: no combo reached 80% wins AND profit (best: stocks gap_fade S3/T0.25 = 80% wins, -0.04R).
Same universes, entries (8), exits (16 stop/target pairs), costs and same-day rules as INTRA-WIN-001.
Filter flags (all known at the signal candle, no look-ahead):
 adx      daily ADX(14) of yesterday > 25 (strong trend day context)
 with     trade side = yesterday's daily trend (close vs EMA50)
 ema200   trade side agrees with yesterday's close vs daily EMA200
 room     RSI(1h) not stretched in trade direction (long < 70, short > 30)
 snap     RSI(1h) stretched against the trade (long < 35, short > 65) – mean-reversion helper
 vol      signal-candle volume > 1.5× same-hour average
 oi       yesterday OI buildup in trade direction (stocks only)
 early    signal candle starts before 12:00
 calm     ATR(1h)% below its own 200-candle median (quiet market)
Every entry × exit × combination of 0–3 flags is tested (~50k tests) → many false positives expected.
SHORTLIST (design < 2024-07-01): win ≥ 80%, trades ≥ 100, exp ≥ +0.05R, PF ≥ 1.15, bootstrap p5 > 0, > 0 at 2× costs.
PASS (hold-out ≥ 2024-07-01, untouched): win ≥ 75%, trades ≥ 50, exp > 0, > 0 at 2× costs.
Only PASS rules may become alerts (as an "experimental intraday" label, alerts only). Existing live rules are not changed.
