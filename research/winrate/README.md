# 70–80 % win-rate search with learned weights (12-Nov-2026)

Research only. Every closed candle (MCX 1-hour and 3-hour; stock futures daily with OI) was scored on all features at once, about 70 of them:
- candlestick patterns and trendline slope;
- support / resistance distances and demand / supply (swing) zones;
- breakouts and EMA trend;
- RSI, MACD, stochastic, CCI, MFI, DMO and Hull;
- 16 divergence flags;
- relative volume, OBV and OI build-up / unwinding;
- higher-timeframe trend.

**How the weights were found:**
- Two models learned the weights on DEV only: logistic regression and gradient-boosted trees.
- The score cut-off giving ≥ 70 % or ≥ 80 % wins was chosen on VALID only.
- OOS was looked at once, after costs, both as single signals and as real one-at-a-time calls.

Each trade enters at the next open with a 1-ATR stop and a target of 0.5, 1 or 1.5 ATR. BUY and SELL use separate models. That gives 72 model runs.

**Results:**
- **80 % wins: never reached,** in any market, side, target or model, even on VALID.
- **70 % wins: reached only with a target half the size of the stop** (0.5 ATR target, 1 ATR stop):

| Setup | Every candle, no model (win % / net R) | Model calls in OOS, one at a time (win % / net R per call) |
|---|---|---|
| MCX 3h BUY | 64.6 % / −0.07R | 70.6 % / +0.03R (235 calls) |
| MCX 1h BUY | 63.8 % / −0.12R | 67.1 % / −0.07R (277) |
| Stock futures BUY | 63.1 % / −0.09R | 66.4 % / −0.04R (2,653) |
| Stock futures SELL | 67.5 % / −0.02R | 70.1 % / +0.01R (3,523) |

- **Targets of 1 or 1.5 ATR never reached 70 %** for any model.

**Why:** with a target half the stop, even random entries win about 65 %, and a 70 % win rate is exactly break-even before costs. The features raise the win rate by 3–6 points, which only covers costs. A setup that wins 70–80 % *and* makes money is not in this data, with any weighting of these indicators.

## 60–70 % with profit: full registry check (12-Nov)
- **Registry scan:** across every tested setup, only one family wins ≥ 60 % with profit in DEV, VALID and OOS (≥ 30 trades each): index futures 1h, RSI(14) crosses to ≥ 75, BUY next open, structure stop, **1R target**.
- **Untouched 2018 – Jun-2022 index hourly data:** all indices 55 % wins / +0.02R (145 trades); BANKNIFTY 46 % / −0.09R.
- **NIFTY futures alone:**

| Period | Trades | Wins | R per trade |
|---|---|---|---|
| Untouched 2018 – Jun-2022 | 67 | 64 % | +0.15 |
| DEV Jul-2022 – Jun-2024 | 30 | 60 % | +0.13 |
| VALID | 9 | 67 % | +0.27 |
| OOS | 13 | 62 % | +0.16 |

- **About 119 trades** in 8 years (about 13 a year).
- **Caveats:** NIFTY was singled out after BANKNIFTY failed (a per-instrument choice), the sample is small, and t is about 1.6. Shadow test only.
