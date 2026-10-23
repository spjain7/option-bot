# INTRA-WIN-001 (registered 23-Oct-2026, before running) – intraday combos with 80-90% win rate that STILL make money
Universes: STOCKS (181 stock futures, 1h), INDEX (NIFTY, BANKNIFTY futures, 1h), MCX (7 commodities, 1h).
Same-day trades only; entry = next candle open; stop checked before target inside a candle (worst case);
unfilled at the close → exit at the last close. Full costs + slippage. Max one trade per instrument per entry family per day.
Entries (8; both sides; "trend" = yesterday's close vs daily EMA50):
 E1 orb_trend   E2 pdh_break   E3 vwap_pullback   E4 oi_orb (stocks)   — as in INTRADAY-001
 E5 gap_fade      gap ≥ 1% AGAINST the trend, first hour moves back toward the previous close → trade toward it
 E6 vwap_stretch  1h close > 2 ATR away from VWAP after 11:15 → fade back toward VWAP
 E7 rsi_snap      daily trend up and 1h RSI < 25 (down: RSI > 75) → trade with the trend
 E8 fh_reversal   first hour against the trend by > 1 ATR, second hour closes back above the first-hour mid → with the trend
Exits (grid): stop ∈ {1, 1.5, 2, 3} × ATR(1h); target ∈ {0.25, 0.5, 0.75, 1} × ATR(1h)  → 16 per entry.
SHORTLIST (design < 2024-07-01): win ≥ 80%, trades ≥ 100, exp > +0.03R, PF ≥ 1.10, bootstrap p5 > 0, > 0 at 2× costs.
PASS (hold-out ≥ 2024-07-01): win ≥ 75%, trades ≥ 60, exp > 0, > 0 at 2× costs.
Warning written in advance: with ~400 combos tested, some will look good by chance – only the hold-out decides.
