# RSIREV – RSI REVERSAL separated from RSI CONTINUATION (11-Nov-2026)

Research only. There are 10 pre-defined strategies with BUY and SELL kept apart, each run separately for MCX, stock futures, index futures and cash (cash is BUY only). Each is tested on a full grid of entry (next open / price confirmation) × stop (structure / 1.5 ATR / signal candle) × target (1–3R) × regime at the decision bar (all / trend up / trend down / range). That gives 6,480 cells, all kept in `results/<market>_grid.csv` and the registry. Costs and execution are the same as in `research/rsidiv`.

The two shadow candidates are **not** part of this study and are not mixed with it. SF-CONT-SELL-v1 (CONTINUATION SELL) and CM-CONT-BUY-v1 (CONTINUATION BUY) keep their own fixed rules and shadow ledgers (`research/shadow`).

## Base setting per strategy
Base setting: next-open entry, structure stop, 2R target, all regimes. Each cell shows net R per trade and the number of trades.

| Strategy | Label | MCX 1h | MCX 3h | MCX 1d | STOCK fut 1d | STOCK fut 1w | INDEX fut 1d | INDEX fut 1h | CASH 1d | CASH 1w |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 RSI enters ≤ 25 (extreme only) | **REVERSAL BUY** | -0.28R (547) | -0.09R (152) | n<30 | +0.01R (1761) | +0.04R (179) | +0.07R (33) | -0.24R (198) | -0.14R (3562) | +0.13R (366) |
| S2 RSI enters ≥ 75 (extreme only) | **REVERSAL SELL** | -0.35R (765) | -0.21R (278) | -0.41R (71) | -0.04R (2849) | -0.17R (800) | -0.56R (50) | -0.44R (189) | not shortable | not shortable |
| S3 RSI crosses back above 25 | **REVERSAL BUY** | -0.16R (576) | -0.03R (153) | n<30 | -0.07R (1752) | +0.07R (181) | -0.26R (31) | -0.16R (208) | -0.07R (3581) | +0.11R (369) |
| S4 RSI crosses back below 75 | **REVERSAL SELL** | -0.21R (808) | -0.13R (285) | -0.21R (71) | -0.14R (2968) | -0.22R (827) | -0.31R (52) | -0.39R (195) | not shortable | not shortable |
| S5 bullish RSI divergence near 25 | **REVERSAL BUY** | +0.09R (258) | +0.04R (77) | n<30 | +0.04R (892) | +0.03R (75) | n<30 | -0.07R (82) | -0.05R (1780) | -0.11R (161) |
| S6 bearish RSI divergence near 75 | **REVERSAL SELL** | -0.01R (385) | -0.13R (120) | n<30 | -0.04R (1535) | -0.13R (368) | n<30 | -0.27R (116) | not shortable | not shortable |
| S7 ≤ 25 + bullish candle + volume | **REVERSAL BUY** | -0.03R (94) | n<30 | n<30 | +0.10R (272) | n<30 | n<30 | -0.03R (38) | -0.01R (583) | +0.09R (57) |
| S8 ≥ 75 + bearish candle + volume | **REVERSAL SELL** | -0.07R (160) | -0.15R (75) | n<30 | -0.05R (390) | -0.20R (129) | n<30 | -0.53R (48) | not shortable | not shortable |
| S9 ≤ 25 then breakdown | **CONTINUATION SELL** | +0.10R (396) | +0.06R (115) | n<30 | -0.08R (1362) | -0.24R (156) | n<30 | -0.06R (150) | not shortable | not shortable |
| S10 ≥ 75 + strong trend + breakout | **CONTINUATION BUY** | +0.10R (485) | +0.25R (175) | +0.33R (50) | +0.04R (1812) | +0.17R (563) | +0.28R (34) | +0.32R (126) | +0.00R (4243) | +0.15R (1943) |

## All cells with ≥ 30 trades, by label

| Market | Label | Cells | Median R | Cells with profit | PASS |
|---|---|---|---|---|---|
| MCX | CONTINUATION BUY | 108 | +0.180 | 85% | 3 |
| MCX | CONTINUATION SELL | 78 | +0.068 | 74% | 7 |
| MCX | REVERSAL BUY | 252 | -0.110 | 34% | 0 |
| MCX | REVERSAL SELL | 345 | -0.152 | 11% | 0 |
| NSE_CASH | CONTINUATION BUY | 83 | -0.003 | 46% | 0 |
| NSE_CASH | REVERSAL BUY | 378 | -0.089 | 29% | 6 |
| NSE_INDEX_FUT | CONTINUATION BUY | 61 | +0.144 | 85% | 0 |
| NSE_INDEX_FUT | CONTINUATION SELL | 42 | -0.075 | 17% | 0 |
| NSE_INDEX_FUT | REVERSAL BUY | 117 | -0.135 | 19% | 0 |
| NSE_INDEX_FUT | REVERSAL SELL | 135 | -0.350 | 5% | 0 |
| NSE_STOCK_FUT | CONTINUATION BUY | 81 | +0.050 | 72% | 0 |
| NSE_STOCK_FUT | CONTINUATION SELL | 90 | -0.193 | 6% | 0 |
| NSE_STOCK_FUT | REVERSAL BUY | 297 | -0.024 | 43% | 2 |
| NSE_STOCK_FUT | REVERSAL SELL | 360 | -0.136 | 6% | 0 |

## Cells that passed the period gate (none survives the multiple-testing control)

| Market / TF | Strategy | Entry · stop · regime · target | R DEV / VALID / OOS | Trades | t |
|---|---|---|---|---|---|
| NSE_STOCK_FUT 1d | S7 **REVERSAL BUY** | next_open · structure · trend_down · 2R | +0.29 / +0.11 / +0.34 | 181 | 2.69 |
| MCX 3h | S10 **CONTINUATION BUY** | next_open · structure · all · 2R | +0.26 / +0.28 / +0.19 | 175 | 2.59 |
| NSE_CASH 1w | S1 **REVERSAL BUY** | next_open · atr · trend_down · 2R | +0.15 / +0.10 / +0.47 | 172 | 2.31 |
| NSE_CASH 1w | S1 **REVERSAL BUY** | next_open · atr · trend_down · 3R | +0.20 / +0.11 / +0.46 | 172 | 2.26 |
| NSE_STOCK_FUT 1d | S7 **REVERSAL BUY** | next_open · candle · trend_down · 2R | +0.27 / +0.11 / +0.21 | 181 | 2.08 |
| MCX 1h | S9 **CONTINUATION SELL** | next_open · structure · trend_down · 3R | +0.25 / +0.44 / +0.29 | 242 | 2.04 |
| MCX 1h | S10 **CONTINUATION BUY** | confirm · structure · all · 2R | +0.13 / +0.25 / +0.19 | 300 | 1.96 |
| MCX 1h | S9 **CONTINUATION SELL** | confirm · structure · trend_down · 3R | +0.26 / +0.66 / +0.23 | 156 | 1.95 |
| MCX 3h | S10 **CONTINUATION BUY** | next_open · atr · trend_up · 3R | +0.24 / +0.17 / +0.35 | 173 | 1.93 |
| NSE_CASH 1w | S1 **REVERSAL BUY** | next_open · atr · trend_down · 1R | +0.08 / +0.18 / +0.24 | 172 | 1.9 |
| NSE_CASH 1w | S1 **REVERSAL BUY** | next_open · atr · all · 2R | +0.19 / +0.08 / +0.42 | 338 | 1.85 |
| NSE_CASH 1w | S1 **REVERSAL BUY** | next_open · atr · all · 3R | +0.22 / +0.09 / +0.38 | 338 | 1.72 |
| MCX 1h | S9 **CONTINUATION SELL** | next_open · atr · trend_down · 3R | +0.25 / +0.29 / +0.32 | 307 | 1.7 |
| MCX 1h | S9 **CONTINUATION SELL** | confirm · atr · trend_down · 3R | +0.30 / +0.46 / +0.34 | 179 | 1.67 |
| NSE_CASH 1w | S1 **REVERSAL BUY** | next_open · atr · all · 1R | +0.14 / +0.11 / +0.28 | 338 | 1.54 |
| MCX 1h | S9 **CONTINUATION SELL** | confirm · structure · trend_down · 2R | +0.18 / +0.35 / +0.21 | 169 | 1.43 |
| MCX 1h | S9 **CONTINUATION SELL** | next_open · candle · trend_down · 3R | +0.33 / +0.17 / +0.28 | 320 | 1.37 |
| MCX 1h | S9 **CONTINUATION SELL** | next_open · candle · trend_down · 2R | +0.15 / +0.31 / +0.15 | 363 | 0.53 |

## What this says
- **An RSI extreme is not a signal.**
  - S2 (sell when RSI enters ≥ 75) loses money in every market.
  - S1 (buy when RSI enters ≤ 25) loses on MCX, index hourly and daily cash, and is about flat on stock futures (+0.01R / +0.04R).
  - Exceptions: index daily (+0.07R, only 33 trades) and **weekly cash (+0.13R, 366 trades; DEV +0.21 / VALID −0.14 / OOS +0.25, so it fails the gate)**.
- **Waiting for confirmation does not fix it.** RSI crossing back over 25 or 75 (S3, S4), price confirmation, and a reversal candle with volume (S7, S8) reduce the loss but almost never make a reversal profitable across periods.
- **REVERSAL SELL is the worst label:** 5–11 % of cells are profitable outside cash.
- **Regime:** a REVERSAL BUY in a trend-up or range market is worse than in a downtrend.
- **CONTINUATION BUY is the only label that is mostly profitable:** 72–85 % of cells on MCX, stock futures and indices, especially MCX 3h/1h and index 1h. It still passes no multiple-testing control.
- **MCX 1h continuation sell:** S9 (sell a breakdown after RSI ≤ 25) passes the period gate only in down-trending MCX (t ≤ 2.0).
- **The stock-futures shadow candidate is a different trade from S9.** SF-CONT-SELL-v1 sells the BOUNCE after oversold. S9, which sells the breakdown, loses on stock futures (−0.08R daily, −0.24R weekly at the base setting).
- **Factor effects** (mean over cells): confirmation entry ≈ next open; structure and ATR stops beat the candle stop; wider targets help CONTINUATION BUY (+0.03R at 1R → +0.17R at 3R).

Nothing here is promoted or shadow-tested. The best continuation-buy rows would need a separate stress test (placebo, neighbours, years) before any shadow version.
