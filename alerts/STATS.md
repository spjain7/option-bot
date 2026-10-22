# RSI-reversal alert rule – historical check (real Angel candles)

Entry at the next candle's open, SL checked first, half booked at T1 (SL to cost), rest at T2 or after 20 candles, costs ≈ 0.1R. Stitched front-month series (contract switches not removed – small distortion). Exploratory, not proof.

| Instrument | TF | Alerts (after quality filter) | /year | T1 reached | Win % | Avg R | PF | Bootstrap p5 | BUY avg R | SELL avg R |
|---|---|---|---|---|---|---|---|---|---|---|
| CRUDEOIL | 15m | ALL candidates (no quality filter) | 1318 | | | | -0.064 | 0.87 | -0.11 | | |
| CRUDEOIL | 15m | **filtered** 214 | 35.8 | 44.9% | 48.6% | -0.075 | 0.85 | -0.188 | -0.099 | -0.035 |
| CRUDEOIL | 1h | ALL candidates (no quality filter) | 243 | | | | -0.046 | 0.91 | -0.152 | | |
| CRUDEOIL | 1h | **filtered** 50 | 12.4 | 42.0% | 46.0% | -0.176 | 0.68 | -0.407 | -0.552 | 0.343 |
| CRUDEOIL | 3h | ALL candidates (no quality filter) | 57 | | | | 0.041 | 1.08 | -0.198 | | |
| CRUDEOIL | 3h | **filtered** 19 | 5.2 | 68.4% | 68.4% | 0.396 | 2.27 | 0.012 | 0.678 | 0.142 |
| GOLD | 1h | ALL candidates (no quality filter) | 252 | | | | -0.114 | 0.8 | -0.224 | | |
| GOLD | 1h | **filtered** 51 | 13.4 | 35.3% | 37.3% | -0.271 | 0.57 | -0.506 | -0.024 | -0.34 |
| GOLD | 3h | ALL candidates (no quality filter) | 114 | | | | -0.053 | 0.9 | -0.22 | | |
| GOLD | 3h | **filtered** 32 | 8.8 | 53.1% | 56.2% | 0.044 | 1.1 | -0.251 | 0.665 | 0.003 |
| SILVER | 1h | ALL candidates (no quality filter) | 284 | | | | -0.123 | 0.78 | -0.231 | | |
| SILVER | 1h | **filtered** 50 | 12.7 | 50.0% | 54.0% | 0.083 | 1.18 | -0.166 | 0.186 | -0.013 |
| SILVER | 3h | ALL candidates (no quality filter) | 98 | | | | -0.134 | 0.75 | -0.293 | | |
| SILVER | 3h | **filtered** 34 | 10.0 | 38.2% | 41.2% | -0.198 | 0.66 | -0.487 | -0.221 | -0.188 |
| NATURALGAS | 1h | ALL candidates (no quality filter) | 308 | | | | -0.088 | 0.84 | -0.186 | | |
| NATURALGAS | 1h | **filtered** 63 | 16.4 | 42.9% | 44.4% | -0.206 | 0.65 | -0.425 | -0.2 | -0.21 |
| NATURALGAS | 3h | ALL candidates (no quality filter) | 84 | | | | -0.058 | 0.88 | -0.244 | | |
| NATURALGAS | 3h | **filtered** 22 | 5.9 | 31.8% | 36.4% | -0.344 | 0.42 | -0.642 | -0.2 | -0.387 |
| COPPER | 1h | ALL candidates (no quality filter) | 230 | | | | -0.15 | 0.72 | -0.251 | | |
| COPPER | 1h | **filtered** 46 | 11.0 | 45.7% | 50.0% | -0.068 | 0.86 | -0.316 | -0.07 | -0.066 |
| COPPER | 3h | ALL candidates (no quality filter) | 72 | | | | -0.207 | 0.65 | -0.409 | | |
| COPPER | 3h | **filtered** 23 | 5.6 | 47.8% | 47.8% | -0.086 | 0.84 | -0.451 | -0.5 | 0.001 |
| NIFTY | 1h | ALL candidates (no quality filter) | 183 | | | | -0.099 | 0.82 | -0.225 | | |
| NIFTY | 1h | **filtered** 52 | 12.6 | 36.5% | 40.4% | -0.274 | 0.56 | -0.503 | -0.147 | -0.411 |
| NIFTY | 3h | ALL candidates (no quality filter) | 29 | | | | 0.084 | 1.17 | -0.269 | | |
| NIFTY | 3h | **filtered** 8 | 2.1 | 37.5% | 37.5% | -0.413 | 0.4 | -0.913 | -0.475 | -0.35 |
| BANKNIFTY | 1h | ALL candidates (no quality filter) | 167 | | | | -0.095 | 0.82 | -0.222 | | |
| BANKNIFTY | 1h | **filtered** 33 | 8.7 | 48.5% | 57.6% | 0.132 | 1.31 | -0.164 | 0.224 | 0.034 |
| BANKNIFTY | 3h | ALL candidates (no quality filter) | 32 | | | | -0.257 | 0.58 | -0.541 | | |
| BANKNIFTY | 3h | **filtered** 11 | 2.8 | 45.5% | 45.5% | -0.329 | 0.45 | -0.78 | 0.063 | -0.8 |
