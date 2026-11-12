# Early-stage reversals: low risk, high reward (12-Nov-2026)

Research only; nothing is live.

**The test:**
- 8 early-reversal triggers: spring, sweep + structure shift, failed breakdown, divergence + break, volume climax, key reversal, RSI reclaim, double bottom.
- Tight stop just beyond the reversal extreme (0.3–2 ATR).
- Targets 3R, 5R, 8R, or a trailing exit.
- Context: any trend, counter-trend, or with the 200-EMA trend.
- Markets: MCX 1h / 3h / 1d, stock futures 1d, index futures 1h, cash 1d. BUY and SELL apart.
- 1,056 tests, all after real costs (`run.py`).

**Overall result:**
- 9 pass the period gate, 0 survive multiple testing.
- Almost every SELL setup and every non-MCX market is flat or negative.
- Larger targets help: median −0.05R at 3R, −0.02R at 8R.

**The passes, checked on Angel hourly data from Jul-2022 to the start of 2023 (never used by any study), against random entries with the same stop (`check.py`):**

| MCX BUY setup | DEV / VALID / OOS (R per trade) | Untouched 2022–23 | Random entry, same stop | Verdict |
|---|---|---|---|---|
| **1h sweep + structure shift, with trend, 8R** | **+0.32 / +0.12 / +0.63** (628 trades, 28 % wins, average win 4.0R) | **+0.43R (159 trades, PF 1.55)** | +0.02 / +0.21 / +0.01; untouched +0.09 | **best candidate** |
| 1h RSI reclaim, with trend, 8R | +0.44 / +0.26 / +1.06 | +0.54R (only 33 trades) | as above | too few trades |
| 1h double bottom, with trend, 8R | +0.43 / +0.85 / +0.20 | **−0.19R** (75 trades) | | fails |
| 3h sweep + structure shift, 8R | +0.22 / +0.41 / +0.31 | +0.03R | +0.07 / +0.56 / +0.15 | no better than random |
| 1d sweep + structure shift, 8R | +0.25 / +0.25 / +0.21 | (no data) | +0.26 / +0.83 / +0.16 | no better than random |

**The best candidate (MCX 1-hour, BUY only):**
- **Conditions:** the price is above its 200-EMA (uptrend). A candle's low breaks below the lowest low of the previous 20 candles (a stop-run). Within the next 3 candles, a candle closes above that sweep candle's high.
- **Entry:** buy at the next candle's open.
- **Stop:** the lowest low from the sweep to the signal, minus 0.1 ATR (0.3–2 ATR).
- **Target:** 8R (5R gives +0.29R per trade). Maximum 90 candles.

**Strengths:**
- Profitable in every period, including the untouched one.
- Profitable in metals (+0.30R) and energy (+0.37R).
- 5R and 3R targets are also positive.

**Against it:**
- The VALID period is weak (+0.12R, PF 1.15, below the 1.2 gate).
- It was picked from 1,056 tests and does not survive the multiple-testing correction.
- Copper loses (−0.23R).
- It wins only about 28 % of the time: long losing streaks are normal (about 1 in 3 chance of 10 losses in a row in 100 trades).
- The SELL mirror loses.

**Status:** a hypothesis that should be tested forward in shadow, not sent as calls.
