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
