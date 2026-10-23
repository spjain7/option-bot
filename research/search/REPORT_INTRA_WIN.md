# INTRA-WIN-001/002 result (23-Oct-2026) – NO 80-90% intraday rule survived. Nothing deployed.
001 (8 entries × 16 exits): best 80% win combos all lose after costs (stocks gap_fade S3/T0.25: 80% win, -0.04R).
002 (+ trend/ADX/EMA200/RSI/volume/OI/time/volatility filters, ~50k tests):
 INDEX 0 shortlisted · MCX 0 shortlisted · STOCKS 12 shortlisted, 0 passed.
 All 12 = vwap_stretch fade (with trend / EMA200 + before 12:00), stop 3 ATR, target 0.5-1 ATR:
   design 80-91% win, +0.06…+0.16R  →  hold-out 54-68% win, -0.04…-0.06R (loses).
 Classic curve-fit: the high win rate came from luck in the design period and vanished on new data.
Conclusion: on 1-hour data with real costs, no intraday stock/index/MCX rule gives 80-90% wins with profit.

# INTRA-MONTH-001 (Oct-2026 pick → Jul–Sep 2026 + full-history check): 667 October winners, 0 kept
- STOCKS 643 Oct winners. Best: rsi_snap + ADX>25, stop 2 ATR, target 0.25 ATR → Oct 91% win (+0.01R), Jul–Sep 90% (+0.01R),
  but full 2022-26: 76% win, -0.07R (loses). vwap_pullback + OI: Oct 84-88% → Jul–Sep 67-70% → full 52-55%, losing.
- MCX 24 Oct winners, none held up. INDEX: too few trades in one month (2 instruments).

# INTRA-CLUE-001 (clues before a move + candlestick patterns, ML model) – 0 of 12 passed
Model picks (top 2–10% of candles) on the data it learned from: 65–98% wins. On unseen data (Jan-2024 → Oct-2026):
 INDEX 40–59% wins, -0.05…-0.17R · MCX 35–63% wins, -0.10…-0.39R · STOCKS 43–57% wins, -0.05…-0.11R. All lose.
Single clues (candlestick patterns, inside/NR days, etc.) shift the win rate by only 1–7 points – not enough after costs.

# STOCK-1H-002 (relative strength, late momentum, overnight, RSI(2) dip ± OI ± 1h hammer) – 0 passed
- R1 relative strength / R2 late momentum: ≈ break-even or losing after costs.
- R3 overnight: first run "passed" but had look-ahead (used the full-day close while entering at 15:15). Fixed run:
  design +0.20%/trade, hold-out +0.07% but -0.02% at 2× costs → FAIL. Win ≈ 48-49%.
- R4/R5/R6 RSI(2) dip: design 62-66% win, +0.2…+0.4%/trade → hold-out 59-60% win but LOSING (-0.03…-0.21%).

# EMA-X-001 (EMA 5/13, 9/21, 20/50 crossover + vol/OI/trend/ADX/RSI/body/confirm filters) – 0 shortlisted, 0 passed
STOCKS 668 tests: best = 5/13 swing exit + OI + daily trend + strong candle: +0.20R but only 106 trades, 29% win,
  bootstrap p5 < 0 (could be luck) → not shortlisted. Same-day exits all lose.
INDEX 52 tests: all losing (best -0.08R). MCX 320 tests: all losing (best -0.03R, 52% win).

# BIG-MOVE-001 (first hour) – 130 passed, but FRAGILE
Best: first hour ≥ 3% on ≥ 2× volume + gap same way (+ beyond yesterday's high/low) + RSI not extreme, 10:15 entry,
exit at close: design +0.75%/trade → hold-out +0.22%, 56% win, 2× costs +0.13%, ~11 trades/month.
But: profit mostly SELL side; 2024-H2 and 2025-H1 lost; 2026 strong.
# BIG-MOVE-002 (any hour until 14:15) – 1 passed (incl. stability rule)
Move from open ≥ 3% + that candle's volume ≥ 2× + gap same way + beyond yesterday's high/low + RSI not extreme,
exit at close: design +0.30% → hold-out +0.12%/trade, 53% win, 2× costs +0.02%, 3/5 half-years positive,
buys +0.08% / sells +0.18%, ~23 trades/month. Thin edge – same pattern found in both tests.

# EARLY-MOVE-001 (signal BEFORE the move: volume spike while flat, coil near 20-day high/low, early level break) – 0 shortlisted
Base: 15,136 signals, 41-45% win, -0.07…-0.12%/trade, -₹470…-₹916 per lot after costs; only 6-10% reached +2% later.
No filter combination reached the shortlist.
