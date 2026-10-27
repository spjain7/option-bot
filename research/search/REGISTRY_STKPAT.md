# STOCK-PAT-001 (registered 27-Oct-2026, before running) – 3h chart patterns + breakout on STOCK futures
Same detectors/exits as INST-PAT-001 (3h candles = 2 per NSE session; flag, head & shoulders, live 20-candle volume
breakout with EMA200; exits: stop 2 ATR, 50% at T1 + stop to entry, trail 3 ATR; conservative candle order).
Universe 181 stock futures (lot < 3000), stock costs, no trade across the rollover window.
PASS: ≥ 100 trades per period, avg ₹/lot > 0 at 2× costs in design (< 2024-07) AND hold-out, ≥ 55% of stocks positive in hold-out.

## RESULT (27-Oct-2026) – avg ₹/lot after costs (2× costs) design / hold-out, win %, share of stocks positive (hold-out)
 breakout  ₹769 / ₹5,145 · win 60% / 72% · 80%  PASS → live
 double    ₹2,780 / ₹6,048 · win 73% / 75% · 77%  PASS → live
 flag      ₹7,978 / ₹7,614 · win 67% / 72% · 71%  PASS → live
 hs        ₹2,699 / ₹5,317 · win 75% / 75% · 78%  PASS → live
 squeeze   ₹2,833 / ₹4,230 · win 65% / 68% · 70%  PASS (not used – lowest win rate)
