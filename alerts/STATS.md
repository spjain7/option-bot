# RSI-reversal alert rule – historical check (real Angel candles)

Entry at the next candle's open, SL checked first, half booked at T1 (SL to cost), rest at T2 or after 20 candles, costs ≈ 0.1R. Stitched front-month series (contract switches not removed – small distortion). Exploratory, not proof.

| Instrument | TF | Alerts | /year | T1 reached | Win % | Avg R | PF | Bootstrap p5 | BUY avg R | SELL avg R |
|---|---|---|---|---|---|---|---|---|---|---|
| CRUDEOIL | 15m | 962 | 160.0 | 49.0% | 50.9% | -0.077 | 0.85 | -0.133 | -0.097 | -0.055 |
| CRUDEOIL | 1h | 185 | 44.7 | 47.0% | 49.2% | -0.085 | 0.84 | -0.215 | -0.072 | -0.096 |
| CRUDEOIL | 3h | 38 | 9.7 | 50.0% | 50.0% | 0.035 | 1.07 | -0.273 | 0.375 | -0.186 |
| GOLD | 1h | 173 | 40.9 | 43.4% | 45.1% | -0.121 | 0.79 | -0.257 | 0.206 | -0.262 |
| GOLD | 3h | 84 | 22.0 | 47.6% | 48.8% | -0.039 | 0.93 | -0.235 | 0.463 | -0.139 |
| SILVER | 1h | 208 | 49.1 | 47.6% | 49.5% | -0.097 | 0.82 | -0.217 | -0.161 | -0.049 |
| SILVER | 3h | 61 | 14.7 | 45.9% | 47.5% | -0.159 | 0.72 | -0.378 | -0.105 | -0.188 |
| NATURALGAS | 1h | 223 | 52.8 | 50.2% | 50.7% | -0.079 | 0.85 | -0.197 | -0.094 | -0.067 |
| NATURALGAS | 3h | 64 | 15.6 | 50.0% | 51.6% | -0.039 | 0.92 | -0.251 | -0.007 | -0.061 |
| COPPER | 1h | 152 | 36.4 | 45.4% | 48.7% | -0.168 | 0.69 | -0.296 | -0.083 | -0.249 |
| COPPER | 3h | 51 | 12.5 | 39.2% | 39.2% | -0.261 | 0.59 | -0.492 | -0.265 | -0.259 |
| NIFTY | 1h | 128 | 30.7 | 46.1% | 46.9% | -0.168 | 0.71 | -0.322 | 0.059 | -0.319 |
| NIFTY | 3h | 17 | 5.0 | 58.8% | 58.8% | 0.226 | 1.5 | -0.247 | -0.157 | 0.567 |
| BANKNIFTY | 1h | 116 | 27.9 | 53.4% | 54.3% | -0.013 | 0.97 | -0.173 | 0.232 | -0.219 |
| BANKNIFTY | 3h | 22 | 5.4 | 45.5% | 45.5% | -0.261 | 0.56 | -0.6 | -0.108 | -0.306 |
