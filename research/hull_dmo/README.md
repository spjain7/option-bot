# Hull Trend + DMO on MCX intraday (12-Nov-2026)

Research only; nothing is live. Both indicators are coded exactly as in the owner's Pine scripts (`run.py`).

The grid covers 3,456 tests:
- 5-min, 15-min, 30-min and 1-hour candles.
- Hull length 12, 16, 20, 24, 30, 36, 40, 48 and 60.
- DMO 14, 14 smoothed, 10 and 20.
- 6 Hull + DMO combinations.
- 2 exits: the opposite Hull cross, or a stop with a 2R target.
- BUY and SELL kept apart.

Every trade is intraday and flat by 23:30. Costs are real MCX fees plus slippage. Periods: DEV 2023–24, VALID 2025, OOS 2026.

**Result: 0 of 3,456 pass the gate** (profit and PF ≥ 1.2 in every period). 0 survive multiple testing, and only 15 are positive in all three periods.

| Timeframe | Average R per trade over all tests | Best test |
|---|---|---|
| 5 min | −0.25 | −0.16 |
| 15 min | −0.10 | −0.01 |
| 30 min | −0.06 | +0.05 |
| 1 hour | −0.02 | +0.09 |

## The owner's setting (Hull 30, DMO 14, 1 hour)

| Rule (Hull 30, DMO 14, opposite-cross exit) | Trades | Win % | Net R per trade | DEV / VALID / OOS |
|---|---|---|---|---|
| Hull BUY cross alone | 2,816 | 45.7 | +0.00 | −0.04 / +0.02 / +0.05 |
| **Hull BUY cross + DMO > 0** | 1,102 | 46.9 | **+0.05** | +0.02 / +0.05 / +0.11 (PF 1.08 / 1.16 / 1.46, t 1.6) |
| Hull SELL cross + DMO < 0 | 941 | 46.4 | +0.06 | +0.10 / −0.04 / +0.10 |
| Same rules on 5 min | 12,187 | 31.7 | −0.20 | all periods negative |

- **Hull length 30 is the best length on 1 hour.** 24–36 are slightly positive; 12–20 and 48–60 are not. The best is still only +0.05R per trade.
- **DMO > 0 as confirmation removes about 60 % of the Hull crosses and adds about +0.05R.** That is not enough to pass the gate.
- **Shorter timeframes lose more,** because costs and noise grow relative to the move.
- **Metals and energy behave alike** (+0.06R vs +0.04R for the best rule).

This is not a validated strategy. At best, the 1-hour Hull 30 + DMO > 0 rule could be watched as a shadow test.
