# MCXE-004 script-wise results – E1: live / shadow rules inside the 1-year window

- Script `eval_live_rules.py` (`MCXE004-E1`), run at code commit bb036bb.
- Trades: `results/e1_trades.csv.gz`. Signals and rejection reasons: `results/e1_signals.csv`.
- **Units:** net R per trade after realistic costs (1×). The 2× stress value is shown separately. Rupee P&L is
  not modelled, because lot sizing is not part of the rules.
- **Periods:** DEV, VALID and OOS of the approved window. MCX is 2025-11-04 → 2026-11-03, but its frames end on
  2026-10-21 (Angel 1-hour). Stocks are 2025-10-23 → 2026-10-22.
- **Contamination:** every one of these rules was **selected on 2022-26 data that includes this window**. So the
  window is not independent evidence for them; their best possible status is PAPER_ONLY.

## RB_MCX_4h_EMA1348_BUY — INSUFFICIENT_DATA

OOS 9 trades / 8 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)

signals 35 · executed trades 24 · rejected 11 · reasons: {"skipped: position already open / switch day / warm-up edge": 8, "next open beyond the 0.5-ATR entry zone": 3}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 8 | 2 | 6 | 25.000 | 1.352 | -0.916 | -0.349 | 0.492 | -2.790 | 3.780 | 8 | [-1.356, 0.658] |
| DEV | 2× | 8 | 2 | 6 | 25.000 | 1.306 | -0.935 | -0.374 | 0.466 | -3.000 | 3.870 | 8 | [-1.363, 0.614] |
| VALID | 1× | 7 | 5 | 2 | 71.400 | 1.572 | -1.062 | 0.820 | 3.701 | 5.740 | 2.120 | 7 | [-0.892, 2.531] |
| VALID | 2× | 7 | 5 | 2 | 71.400 | 1.524 | -1.124 | 0.767 | 3.389 | 5.370 | 2.250 | 7 | [-0.97, 2.504] |
| OOS | 1× | 9 | 4 | 5 | 44.400 | 2.835 | -0.753 | 0.842 | 3.012 | 7.580 | 2.030 | 8 | [-0.853, 2.537] |
| OOS | 2× | 9 | 4 | 5 | 44.400 | 2.796 | -0.793 | 0.802 | 2.822 | 7.220 | 2.060 | 8 | [-0.89, 2.495] |

By instrument (net R 1×; n / mean):

| inst | size_DEV | size_OOS | size_VALID | mean_DEV | mean_OOS | mean_VALID |
|---|---|---|---|---|---|---|
| ALUMINIUM | 1.000 | — | 1.000 | -0.721 | — | 2.132 |
| COPPER | 1.000 | 2.000 | 1.000 | -1.016 | 0.948 | -1.042 |
| CRUDEOIL | 3.000 | 2.000 | 1.000 | -1.018 | 2.731 | 1.110 |
| GOLD | 1.000 | — | 1.000 | 0.276 | — | 2.984 |
| NATURALGAS | — | — | 1.000 | — | — | 0.711 |
| SILVER | 1.000 | 2.000 | — | -0.704 | -1.015 | — |
| ZINC | 1.000 | 3.000 | 2.000 | 2.429 | 0.749 | -0.079 |

## RB_MCX_4h_MACD0_BUY — INSUFFICIENT_DATA

OOS 14 trades / 10 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)

signals 48 · executed trades 44 · rejected 4 · reasons: {"skipped: position already open / switch day / warm-up edge": 1, "next open beyond the 0.5-ATR entry zone": 3}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 15 | 8 | 7 | 53.300 | 1.782 | -0.953 | 0.506 | 2.138 | 7.590 | 2.030 | 13 | [-0.394, 1.398] |
| DEV | 2× | 15 | 8 | 7 | 53.300 | 1.727 | -1.003 | 0.453 | 1.968 | 6.800 | 2.060 | 13 | [-0.443, 1.338] |
| VALID | 1× | 15 | 6 | 9 | 40.000 | 1.411 | -1.072 | -0.079 | 0.878 | -1.180 | 5.210 | 13 | [-0.823, 0.666] |
| VALID | 2× | 15 | 6 | 9 | 40.000 | 1.338 | -1.144 | -0.151 | 0.780 | -2.270 | 5.640 | 13 | [-0.897, 0.594] |
| OOS | 1× | 14 | 6 | 8 | 42.900 | 1.641 | -0.972 | 0.148 | 1.267 | 2.070 | 3.110 | 10 | [-0.619, 0.934] |
| OOS | 2× | 14 | 6 | 8 | 42.900 | 1.572 | -1.050 | 0.074 | 1.123 | 1.030 | 3.210 | 10 | [-0.692, 0.867] |

By instrument (net R 1×; n / mean):

| inst | size_DEV | size_OOS | size_VALID | mean_DEV | mean_OOS | mean_VALID |
|---|---|---|---|---|---|---|
| ALUMINIUM | 3.000 | 2.000 | 2.000 | 0.170 | -1.144 | 0.394 |
| COPPER | 1.000 | 4.000 | 3.000 | -1.022 | 0.745 | -0.659 |
| CRUDEOIL | 3.000 | 2.000 | 2.000 | 1.498 | 0.475 | 0.231 |
| GOLD | 3.000 | 1.000 | — | -0.011 | -1.019 | — |
| NATURALGAS | — | 1.000 | 4.000 | — | 1.911 | 0.217 |
| SILVER | 2.000 | 1.000 | 1.000 | 0.492 | -1.019 | -1.015 |
| ZINC | 3.000 | 3.000 | 3.000 | 0.885 | 0.186 | -0.102 |

## RB_MCX_2h_MOMO_BUY — REJECTED

OOS 95% CI lower bound -0.504 not > 0 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)

signals 77 · executed trades 60 · rejected 17 · reasons: {"skipped: position already open / switch day / warm-up edge": 16, "next open beyond the 0.5-ATR entry zone": 1}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 22 | 6 | 16 | 27.300 | 2.957 | -1.095 | 0.010 | 1.013 | 0.220 | 8.360 | 19 | [-0.861, 0.881] |
| DEV | 2× | 22 | 6 | 16 | 27.300 | 2.914 | -1.139 | -0.034 | 0.959 | -0.740 | 8.910 | 19 | [-0.905, 0.837] |
| VALID | 1× | 18 | 9 | 9 | 50.000 | 2.092 | -0.925 | 0.584 | 2.262 | 10.500 | 3.180 | 15 | [-0.447, 1.654] |
| VALID | 2× | 18 | 9 | 9 | 50.000 | 2.029 | -1.010 | 0.510 | 2.009 | 9.170 | 3.650 | 15 | [-0.533, 1.597] |
| OOS | 1× | 20 | 10 | 10 | 50.000 | 2.007 | -1.103 | 0.452 | 1.819 | 9.030 | 3.560 | 15 | [-0.504, 1.407] |
| OOS | 2× | 20 | 10 | 10 | 50.000 | 1.932 | -1.153 | 0.389 | 1.676 | 7.790 | 3.860 | 15 | [-0.56, 1.339] |

By instrument (net R 1×; n / mean):

| inst | size_DEV | size_OOS | size_VALID | mean_DEV | mean_OOS | mean_VALID |
|---|---|---|---|---|---|---|
| ALUMINIUM | 5.000 | — | 2.000 | -1.266 | — | -1.118 |
| COPPER | 2.000 | 3.000 | 1.000 | -1.042 | 0.743 | 2.926 |
| CRUDEOIL | 4.000 | 5.000 | 3.000 | 0.977 | 0.193 | 0.378 |
| GOLD | 7.000 | 2.000 | 2.000 | 0.127 | 0.843 | 0.977 |
| NATURALGAS | — | 2.000 | 5.000 | — | 0.429 | 0.317 |
| SILVER | 3.000 | 2.000 | 1.000 | 0.327 | -1.021 | 2.987 |
| ZINC | 1.000 | 6.000 | 4.000 | 2.857 | 0.889 | 0.538 |

## RB_MCX_2h_EMA921_BUY — REJECTED

OOS expectancy <= 0 at 1x cost; OOS expectancy <= 0 at 2x cost; OOS 95% CI lower bound -0.687 not > 0 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)

signals 133 · executed trades 79 · rejected 54 · reasons: {"next open beyond the 0.5-ATR entry zone": 6, "skipped: position already open / switch day / warm-up edge": 48}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 34 | 12 | 22 | 35.300 | 2.520 | -0.867 | 0.328 | 1.585 | 11.160 | 7.420 | 25 | [-0.343, 0.999] |
| DEV | 2× | 34 | 12 | 22 | 35.300 | 2.473 | -0.906 | 0.287 | 1.489 | 9.740 | 7.550 | 25 | [-0.381, 0.955] |
| VALID | 1× | 23 | 9 | 14 | 39.100 | 1.293 | -0.878 | -0.029 | 0.947 | -0.650 | 5.120 | 19 | [-0.648, 0.592] |
| VALID | 2× | 23 | 9 | 14 | 39.100 | 1.225 | -0.924 | -0.083 | 0.852 | -1.920 | 5.230 | 19 | [-0.699, 0.533] |
| OOS | 1× | 22 | 8 | 14 | 36.400 | 1.532 | -0.940 | -0.041 | 0.932 | -0.900 | 8.260 | 17 | [-0.687, 0.605] |
| OOS | 2× | 22 | 8 | 14 | 36.400 | 1.480 | -0.979 | -0.084 | 0.864 | -1.860 | 8.540 | 17 | [-0.731, 0.563] |

By instrument (net R 1×; n / mean):

| inst | size_DEV | size_OOS | size_VALID | mean_DEV | mean_OOS | mean_VALID |
|---|---|---|---|---|---|---|
| ALUMINIUM | 9 | 1 | 3 | -0.229 | -1.143 | 0.338 |
| COPPER | 3 | 5 | 3 | -0.852 | -0.486 | -0.592 |
| CRUDEOIL | 9 | 4 | 2 | 1.572 | 0.163 | 0.180 |
| GOLD | 3 | 3 | 1 | 0.122 | 0.422 | -1.016 |
| NATURALGAS | 1 | 1 | 5 | -1.011 | 1.828 | -0.482 |
| SILVER | 4 | 3 | 2 | -1.005 | -0.808 | -1.011 |
| ZINC | 5 | 5 | 7 | 1.260 | 0.271 | 0.742 |

## RB_MCX_1d_RETEST_BUY — INSUFFICIENT_DATA

OOS 0 trades / 0 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)

signals 0 · executed trades 0 · rejected 0 · reasons: {}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| DEV | 2× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| VALID | 1× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| VALID | 2× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| OOS | 1× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| OOS | 2× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |

## RB_MCX_1h_MACD_BUY — REJECTED

OOS 95% CI lower bound -0.41 not > 0 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)

signals 302 · executed trades 154 · rejected 148 · reasons: {"skipped: position already open / switch day / warm-up edge": 142, "next open beyond the 0.5-ATR entry zone": 6}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 71 | 26 | 45 | 36.600 | 2.292 | -1.016 | 0.196 | 1.304 | 13.880 | 14.600 | 44 | [-0.282, 0.683] |
| DEV | 2× | 71 | 26 | 45 | 36.600 | 2.245 | -1.078 | 0.139 | 1.204 | 9.870 | 16.310 | 44 | [-0.339, 0.629] |
| VALID | 1× | 40 | 15 | 25 | 37.500 | 1.592 | -0.906 | 0.031 | 1.054 | 1.230 | 5.010 | 26 | [-0.549, 0.776] |
| VALID | 2× | 40 | 15 | 25 | 37.500 | 1.507 | -0.977 | -0.045 | 0.926 | -1.820 | 7.220 | 26 | [-0.628, 0.701] |
| OOS | 1× | 43 | 18 | 25 | 41.900 | 1.733 | -1.046 | 0.117 | 1.192 | 5.030 | 9.220 | 29 | [-0.41, 0.657] |
| OOS | 2× | 43 | 18 | 25 | 41.900 | 1.673 | -1.109 | 0.055 | 1.086 | 2.380 | 10.290 | 29 | [-0.471, 0.593] |

By instrument (net R 1×; n / mean):

| inst | size_DEV | size_OOS | size_VALID | mean_DEV | mean_OOS | mean_VALID |
|---|---|---|---|---|---|---|
| ALUMINIUM | 15.000 | 1.000 | 6.000 | -0.270 | -1.144 | -0.427 |
| COPPER | 7.000 | 11.000 | 7.000 | -0.352 | -0.344 | -0.023 |
| CRUDEOIL | 16.000 | 8.000 | 3.000 | 1.082 | 0.838 | -0.137 |
| GOLD | 14.000 | 4.000 | 4.000 | 0.301 | 0.273 | 0.183 |
| NATURALGAS | — | 5.000 | 4.000 | — | 0.189 | -0.282 |
| SILVER | 6.000 | 4.000 | 4.000 | -0.366 | -0.846 | -0.415 |
| ZINC | 13.000 | 10.000 | 12.000 | 0.082 | 0.460 | 0.535 |

## RB_STK_3h_MACD0_SELL — PAPER_ONLY

passes OOS checks, but the rule was selected on data that includes this window – forward paper test only | stock universe = today's F&O list (survivorship)

signals 296 · executed trades 242 · rejected 54 · reasons: {"skipped: position already open / switch day / warm-up edge": 24, "next open beyond the 0.5-ATR entry zone": 30}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 5 | 4 | 1 | 80.000 | 0.679 | -1.030 | 0.337 | 2.635 | 1.690 | 1.030 | 5 | [-0.722, 1.396] |
| DEV | 2× | 5 | 4 | 1 | 80.000 | 0.650 | -1.061 | 0.308 | 2.452 | 1.540 | 1.060 | 5 | [-0.754, 1.37] |
| VALID | 1× | 129 | 52 | 77 | 40.300 | 1.005 | -0.937 | -0.154 | 0.724 | -19.880 | 27.940 | 42 | [-0.382, 0.08] |
| VALID | 2× | 129 | 49 | 80 | 38.000 | 1.030 | -0.935 | -0.189 | 0.674 | -24.360 | 31.790 | 42 | [-0.416, 0.044] |
| OOS | 1× | 108 | 56 | 52 | 51.900 | 1.339 | -0.835 | 0.292 | 1.726 | 31.520 | 3.090 | 44 | [0.02, 0.598] |
| OOS | 2× | 108 | 54 | 54 | 50.000 | 1.346 | -0.844 | 0.251 | 1.594 | 27.090 | 3.180 | 44 | [-0.021, 0.556] |

By instrument (net R 1×; n / mean):

| inst | size_DEV | size_OOS | size_VALID | mean_DEV | mean_OOS | mean_VALID |
|---|---|---|---|---|---|---|
| 360ONE | — | 1.000 | — | — | -0.125 | — |
| ADANIGREEN | — | 1.000 | — | — | 0.566 | — |
| ADANIPORTS | — | 1.000 | — | — | -1.177 | — |
| ALKEM | — | 2.000 | 1.000 | — | 0.459 | -0.264 |
| AMBER | — | 1.000 | — | — | 1.962 | — |
| AMBUJACEM | — | 2.000 | 2.000 | — | 0.460 | -0.214 |
| ANGELONE | — | 2.000 | — | — | 0.358 | — |
| APLAPOLLO | — | — | 2.000 | — | — | -0.492 |
| ASTRAL | — | 1.000 | 3.000 | — | -0.593 | 1.321 |
| AXISBANK | — | 1.000 | 1.000 | — | -0.174 | -1.041 |
| BAJAJFINSV | — | — | 2.000 | — | — | 0.460 |
| BANKBARODA | — | 2.000 | 2.000 | — | -0.101 | -0.459 |
| BEL | — | 1.000 | 2.000 | — | 1.944 | 0.659 |
| BHARATFORG | — | 1.000 | — | — | 0.107 | — |
| BHARTIARTL | — | — | 3.000 | — | — | -0.714 |
| BLUESTARCO | — | 2.000 | — | — | -1.027 | — |
| BPCL | — | 1.000 | 3.000 | — | 1.210 | -0.031 |
| BRITANNIA | — | — | 1.000 | — | — | -0.388 |
| BSE | — | 1.000 | — | — | -1.028 | — |
| CAMS | — | 1.000 | — | — | 0.160 | — |
| CDSL | — | — | 1.000 | — | — | -1.032 |
| CGPOWER | — | 1.000 | — | — | -0.578 | — |
| COFORGE | — | — | 1.000 | — | — | -1.022 |
| COLPAL | — | 1.000 | 1.000 | — | 0.408 | -1.048 |
| CROMPTON | — | 1.000 | — | — | -1.029 | — |
| DABUR | — | 3.000 | 2.000 | — | 0.081 | 0.206 |
| DELHIVERY | — | 1.000 | — | — | -1.043 | — |
| DLF | — | — | 1.000 | — | — | -1.282 |
| DMART | — | 2.000 | — | — | 0.463 | — |
| DRREDDY | — | 2.000 | — | — | 0.725 | — |
| EICHERMOT | — | 1.000 | 2.000 | — | -0.068 | -1.035 |
| ETERNAL | — | — | 2.000 | — | — | -1.231 |
| FORCEMOT | — | 2.000 | — | — | 0.329 | — |
| FORTIS | — | 1.000 | — | — | 1.960 | — |
| GODREJCP | — | — | 2.000 | — | — | -1.178 |
| HAVELLS | — | — | 3.000 | — | — | -0.396 |
| HCLTECH | 2.000 | — | — | 0.093 | — | — |
| HDFCAMC | — | 1.000 | — | — | 1.956 | — |
| HDFCBANK | — | 1.000 | 1.000 | — | 0.584 | 0.386 |
| HDFCLIFE | — | 3.000 | 1.000 | — | -0.101 | 0.530 |
| HEROMOTOCO | 1.000 | 1.000 | 2.000 | 0.853 | -1.033 | 0.180 |
| HINDPETRO | — | 1.000 | 1.000 | — | 0.255 | -1.021 |
| HINDUNILVR | — | — | 2.000 | — | — | -0.534 |
| ICICIBANK | — | — | 1.000 | — | — | -1.047 |
| ICICIGI | — | — | 3.000 | — | — | -0.753 |
| ICICIPRULI | — | 3.000 | 4.000 | — | 0.800 | -0.269 |
| INDIANB | — | — | 1.000 | — | — | 0.034 |
| INDUSTOWER | 1.000 | 4.000 | 1.000 | 0.314 | -0.291 | 1.254 |
| INFY | — | 1.000 | 1.000 | — | -1.508 | 2.833 |
| ITC | — | 2.000 | 3.000 | — | 0.437 | 0.463 |
| JIOFIN | — | — | 4.000 | — | — | -0.559 |
| JUBLFOOD | — | — | 3.000 | — | — | 0.523 |
| KALYANKJIL | — | — | 1.000 | — | — | 1.976 |
| KAYNES | — | 2.000 | — | — | 0.265 | — |
| KEI | — | 1.000 | — | — | 2.810 | — |
| KFINTECH | — | 2.000 | 2.000 | — | -0.551 | -1.308 |
| KOTAKBANK | — | — | 2.000 | — | — | -1.038 |
| KPITTECH | — | 1.000 | 2.000 | — | 0.136 | -1.021 |
| LICI | — | 1.000 | — | — | 1.955 | — |
| LODHA | — | — | 1.000 | — | — | -1.023 |
| LUPIN | — | — | 1.000 | — | — | -1.050 |
| M&M | — | — | 2.000 | — | — | -0.240 |
| MARICO | — | 1.000 | — | — | 0.724 | — |
| MARUTI | — | — | 3.000 | — | — | -0.308 |
| MCX | — | — | 2.000 | — | — | 0.107 |
| MFSL | — | 1.000 | 1.000 | — | -1.041 | -1.030 |
| MPHASIS | — | — | 1.000 | — | — | -1.023 |
| MUTHOOTFIN | — | 1.000 | 1.000 | — | -1.033 | -1.028 |
| NATIONALUM | — | — | 1.000 | — | — | -1.028 |
| NAUKRI | — | — | 2.000 | — | — | -0.027 |
| NESTLEIND | — | 1.000 | — | — | 1.973 | — |
| NTPC | — | 1.000 | — | — | 0.972 | — |
| ONGC | — | 2.000 | — | — | 0.227 | — |
| PATANJALI | — | — | 1.000 | — | — | 1.963 |
| PAYTM | — | — | 2.000 | — | — | -1.085 |
| PERSISTENT | — | — | 3.000 | — | — | 0.734 |
| PETRONET | — | — | 2.000 | — | — | -1.032 |
| PFC | — | 2.000 | 1.000 | — | 0.988 | 0.087 |
| PGEL | — | — | 2.000 | — | — | 0.477 |
| PHOENIXLTD | — | 2.000 | — | — | -1.038 | — |
| PIIND | — | 2.000 | 1.000 | — | 1.109 | 1.961 |
| POLYCAB | — | 2.000 | — | — | 0.471 | — |
| POWERGRID | — | 3.000 | 1.000 | — | 0.533 | 0.083 |
| POWERINDIA | — | 1.000 | — | — | -1.032 | — |
| PREMIERENE | — | 1.000 | — | — | 0.607 | — |
| PRESTIGE | — | 1.000 | — | — | 0.018 | — |
| RECLTD | — | 1.000 | — | — | -0.315 | — |
| RELIANCE | 1.000 | 4.000 | 4.000 | 0.333 | 0.055 | -0.248 |
| RVNL | — | 2.000 | 1.000 | — | 0.459 | 0.452 |
| SBICARD | — | — | 1.000 | — | — | 0.383 |
| SBILIFE | — | 1.000 | 4.000 | — | -1.042 | 0.316 |
| SHREECEM | — | — | 2.000 | — | — | -1.032 |
| SHRIRAMFIN | — | — | 1.000 | — | — | -0.089 |
| SRF | — | 1.000 | — | — | 1.953 | — |
| SUPREMEIND | — | 1.000 | 2.000 | — | -1.035 | 0.466 |
| SWIGGY | — | — | 1.000 | — | — | 1.164 |
| TATACONSUM | — | 1.000 | 1.000 | — | 0.901 | 1.043 |
| TATAELXSI | — | — | 2.000 | — | — | 1.224 |
| TATAPOWER | — | 3.000 | — | — | 0.486 | — |
| TATASTEEL | — | 4.000 | — | — | 0.066 | — |
| TCS | — | — | 1.000 | — | — | -1.034 |
| TECHM | — | — | 2.000 | — | — | -0.848 |
| TIINDIA | — | 1.000 | — | — | 1.965 | — |
| TITAN | — | — | 1.000 | — | — | -1.298 |
| TMPV | — | 1.000 | — | — | 1.968 | — |
| TVSMOTOR | — | — | 1.000 | — | — | -1.029 |
| UNITDSPR | — | 1.000 | 2.000 | — | 1.955 | 0.459 |
| UPL | — | 3.000 | 1.000 | — | 0.217 | -1.027 |
| VBL | — | 1.000 | — | — | 1.963 | — |
| VEDL | — | 2.000 | — | — | 0.464 | — |
| VOLTAS | — | — | 1.000 | — | — | 0.410 |
| WAAREEENER | — | — | 1.000 | — | — | 1.962 |

## RB_STK_3h_EMA921_SELL — PAPER_ONLY

passes OOS checks, but the rule was selected on data that includes this window – forward paper test only | stock universe = today's F&O list (survivorship)

signals 379 · executed trades 290 · rejected 89 · reasons: {"skipped: position already open / switch day / warm-up edge": 48, "next open beyond the 0.5-ATR entry zone": 41}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 13 | 8 | 5 | 61.500 | 0.682 | -1.127 | -0.014 | 0.968 | -0.180 | 2.560 | 7 | [-1.07, 1.042] |
| DEV | 2× | 13 | 8 | 5 | 61.500 | 0.662 | -1.146 | -0.034 | 0.924 | -0.440 | 2.590 | 7 | [-1.089, 1.022] |
| VALID | 1× | 144 | 55 | 89 | 38.200 | 0.805 | -0.812 | -0.195 | 0.612 | -28.000 | 33.870 | 44 | [-0.424, 0.075] |
| VALID | 2× | 144 | 53 | 91 | 36.800 | 0.808 | -0.820 | -0.221 | 0.573 | -31.850 | 37.020 | 44 | [-0.45, 0.047] |
| OOS | 1× | 133 | 75 | 58 | 56.400 | 1.038 | -0.713 | 0.274 | 1.883 | 36.500 | 4.280 | 51 | [0.07, 0.523] |
| OOS | 2× | 133 | 72 | 61 | 54.100 | 1.050 | -0.708 | 0.244 | 1.751 | 32.430 | 4.510 | 51 | [0.04, 0.493] |

By instrument (net R 1×; n / mean):

| inst | size_DEV | size_OOS | size_VALID | mean_DEV | mean_OOS | mean_VALID |
|---|---|---|---|---|---|---|
| 360ONE | — | — | 2.000 | — | — | -0.519 |
| ADANIGREEN | — | 2.000 | — | — | -0.136 | — |
| ADANIPORTS | — | 1.000 | — | — | -1.034 | — |
| ALKEM | — | 2.000 | — | — | 0.390 | — |
| AMBER | — | 1.000 | — | — | 2.972 | — |
| AMBUJACEM | — | 1.000 | 2.000 | — | 0.162 | -0.286 |
| ANGELONE | — | 2.000 | — | — | -0.556 | — |
| APLAPOLLO | — | — | 2.000 | — | — | -0.325 |
| ASTRAL | — | 2.000 | 1.000 | — | -1.102 | -0.400 |
| AXISBANK | — | 3.000 | 1.000 | — | 0.552 | -1.031 |
| BAJAJFINSV | — | — | 3.000 | — | — | -0.691 |
| BANKBARODA | — | 2.000 | 2.000 | — | -0.201 | -1.027 |
| BDL | — | 1.000 | — | — | 0.730 | — |
| BEL | — | 1.000 | 2.000 | — | -1.046 | 0.743 |
| BHARATFORG | — | 1.000 | — | — | 0.080 | — |
| BHARTIARTL | — | 1.000 | 3.000 | — | -1.037 | -0.725 |
| BIOCON | — | — | 1.000 | — | — | -1.027 |
| BLUESTARCO | — | 1.000 | — | — | -0.066 | — |
| BPCL | — | 1.000 | 3.000 | — | 0.908 | -0.698 |
| BRITANNIA | — | — | 2.000 | — | — | -0.665 |
| BSE | — | 3.000 | — | — | 0.084 | — |
| CAMS | — | 2.000 | — | — | 1.221 | — |
| CDSL | — | 1.000 | 1.000 | — | 1.010 | -1.079 |
| CHOLAFIN | — | — | 1.000 | — | — | -1.361 |
| COALINDIA | — | 1.000 | — | — | -1.037 | — |
| COFORGE | — | — | 1.000 | — | — | -0.761 |
| COLPAL | — | 1.000 | 2.000 | — | 0.306 | -0.340 |
| CROMPTON | — | 1.000 | — | — | 0.574 | — |
| DABUR | — | 3.000 | 1.000 | — | -0.065 | 0.213 |
| DMART | — | 4.000 | — | — | 0.545 | — |
| DRREDDY | — | 2.000 | — | — | -0.673 | — |
| EICHERMOT | — | — | 1.000 | — | — | -1.023 |
| ETERNAL | 1.000 | — | 1.000 | -1.533 | — | -1.021 |
| FORCEMOT | — | 3.000 | — | — | -0.091 | — |
| FORTIS | — | 2.000 | — | — | 1.591 | — |
| GODREJCP | — | 1.000 | 3.000 | — | -0.071 | -1.200 |
| HAVELLS | — | — | 3.000 | — | — | -0.569 |
| HCLTECH | 2.000 | — | — | -0.056 | — | — |
| HDFCAMC | — | 2.000 | — | — | 1.695 | — |
| HDFCBANK | — | 1.000 | 2.000 | — | 0.252 | -0.120 |
| HDFCLIFE | — | 3.000 | 2.000 | — | -0.023 | -0.315 |
| HEROMOTOCO | — | — | 3.000 | — | — | 0.239 |
| HINDALCO | — | — | 1.000 | — | — | 0.787 |
| HINDPETRO | — | 1.000 | 1.000 | — | 0.291 | -1.392 |
| HINDUNILVR | — | 1.000 | 2.000 | — | 0.733 | 1.150 |
| HINDZINC | — | 1.000 | — | — | 0.077 | — |
| ICICIBANK | — | — | 2.000 | — | — | -0.392 |
| ICICIGI | — | 1.000 | 3.000 | — | 0.598 | -0.326 |
| ICICIPRULI | — | 2.000 | 3.000 | — | 0.038 | -0.064 |
| INDIANB | — | 1.000 | 2.000 | — | -0.457 | -0.023 |
| INDIGO | — | 2.000 | — | — | 1.324 | — |
| INDUSTOWER | 1.000 | 3.000 | 1.000 | 0.235 | -0.490 | 0.941 |
| INFY | 1.000 | — | — | 2.202 | — | — |
| ITC | — | 3.000 | 2.000 | — | 0.883 | -0.478 |
| JIOFIN | 1.000 | — | 3.000 | -1.023 | — | -0.361 |
| JSWSTEEL | — | 1.000 | 1.000 | — | -0.412 | -1.033 |
| JUBLFOOD | — | — | 3.000 | — | — | 0.521 |
| KALYANKJIL | 1.000 | — | 1.000 | 0.183 | — | -1.017 |
| KAYNES | — | 1.000 | 2.000 | — | 0.469 | -0.412 |
| KEI | — | 2.000 | — | — | 0.977 | — |
| KFINTECH | 1.000 | 2.000 | 2.000 | -1.016 | -0.538 | -1.107 |
| KOTAKBANK | — | — | 3.000 | — | — | -1.029 |
| KPITTECH | — | 1.000 | 2.000 | — | 0.246 | 0.505 |
| LICI | — | 2.000 | 1.000 | — | 0.253 | -1.031 |
| LODHA | — | — | 1.000 | — | — | -0.498 |
| LUPIN | — | — | 2.000 | — | — | -1.097 |
| M&M | — | 1.000 | 3.000 | — | 0.003 | -0.279 |
| MARUTI | — | — | 3.000 | — | — | -0.349 |
| MAXHEALTH | — | 1.000 | — | — | 0.551 | — |
| MAZDOCK | — | 1.000 | — | — | 2.972 | — |
| MCX | — | — | 1.000 | — | — | 0.429 |
| MFSL | — | — | 4.000 | — | — | -0.093 |
| MPHASIS | — | — | 1.000 | — | — | -1.112 |
| MUTHOOTFIN | — | — | 2.000 | — | — | 0.334 |
| NATIONALUM | — | — | 1.000 | — | — | 0.234 |
| NAUKRI | — | 1.000 | — | — | -0.133 | — |
| NESTLEIND | — | 1.000 | — | — | 1.602 | — |
| NTPC | — | 2.000 | 1.000 | — | 0.435 | 0.162 |
| OBEROIRLTY | 1.000 | — | — | 0.327 | — | — |
| OIL | — | 1.000 | — | — | -1.028 | — |
| ONGC | — | 2.000 | — | — | 0.156 | — |
| PAGEIND | — | 1.000 | — | — | 2.319 | — |
| PATANJALI | — | 2.000 | 1.000 | — | 0.274 | -0.318 |
| PAYTM | 1.000 | — | 1.000 | 0.953 | — | -1.021 |
| PERSISTENT | — | — | 2.000 | — | — | 0.981 |
| PETRONET | — | — | 2.000 | — | — | -1.184 |
| PFC | — | 2.000 | — | — | 1.486 | — |
| PGEL | — | — | 2.000 | — | — | 0.656 |
| PHOENIXLTD | — | 2.000 | — | — | -0.935 | — |
| PIDILITIND | — | — | 1.000 | — | — | -1.030 |
| PIIND | — | — | 1.000 | — | — | 2.458 |
| PNBHOUSING | 1.000 | — | — | 0.394 | — | — |
| POLYCAB | — | 1.000 | — | — | 1.540 | — |
| POWERGRID | — | 1.000 | 2.000 | — | 0.387 | 0.213 |
| POWERINDIA | — | 1.000 | — | — | -1.024 | — |
| PREMIERENE | — | 1.000 | — | — | 0.157 | — |
| RECLTD | — | 1.000 | — | — | -0.387 | — |
| RELIANCE | 1.000 | 1.000 | 4.000 | 0.250 | -0.023 | -0.311 |
| RVNL | — | 3.000 | 1.000 | — | 0.933 | 0.319 |
| SBICARD | — | — | 2.000 | — | — | 0.223 |
| SBILIFE | — | 1.000 | 2.000 | — | -0.708 | 0.969 |
| SHRIRAMFIN | — | — | 1.000 | — | — | -0.067 |
| SRF | 1.000 | 3.000 | — | -1.040 | 1.246 | — |
| SUPREMEIND | — | 2.000 | 2.000 | — | -1.025 | 0.849 |
| SWIGGY | — | — | 1.000 | — | — | 0.873 |
| TATACONSUM | — | 2.000 | 1.000 | — | 0.482 | 0.498 |
| TATAELXSI | — | — | 3.000 | — | — | 0.576 |
| TATAPOWER | — | 4.000 | 1.000 | — | -0.094 | 0.581 |
| TATASTEEL | — | 5.000 | — | — | -0.337 | — |
| TCS | — | — | 2.000 | — | — | 0.727 |
| TECHM | — | — | 1.000 | — | — | -0.661 |
| TIINDIA | — | 2.000 | — | — | 1.011 | — |
| TITAN | — | — | 1.000 | — | — | -1.028 |
| TRENT | — | 1.000 | — | — | 0.083 | — |
| TVSMOTOR | — | 1.000 | 1.000 | — | -0.208 | 0.404 |
| ULTRACEMCO | — | 2.000 | 1.000 | — | -0.008 | 0.424 |
| UNITDSPR | — | 1.000 | 2.000 | — | 0.367 | -0.483 |
| UNOMINDA | — | — | 1.000 | — | — | -1.021 |
| UPL | — | 3.000 | 4.000 | — | 0.644 | 0.180 |
| VBL | — | 1.000 | — | — | 1.878 | — |
| VEDL | — | 2.000 | — | — | 0.120 | — |
| VOLTAS | — | — | 1.000 | — | — | 0.374 |
| WAAREEENER | — | 1.000 | 1.000 | — | 0.200 | 0.836 |

## RB_STK_1d_RSI80_BUY — INSUFFICIENT_DATA

OOS 0 trades / 0 dates < required 20 / 15 | stock universe = today's F&O list (survivorship)

signals 0 · executed trades 0 · rejected 0 · reasons: {}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| DEV | 2× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| VALID | 1× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| VALID | 2× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| OOS | 1× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| OOS | 2× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |

## BO_MCX_3h_BUY — REJECTED

OOS 95% CI lower bound -0.367 not > 0 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)

signals 243 · executed trades 102 · rejected 141 · reasons: {"skipped: position already open / switch day / warm-up edge": 135, "next open beyond the 0.5-ATR entry zone": 6}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 45 | 19 | 26 | 42.200 | 1.595 | -0.983 | 0.105 | 1.186 | 4.740 | 5.680 | 36 | [-0.372, 0.583] |
| DEV | 2× | 45 | 18 | 27 | 40.000 | 1.640 | -0.984 | 0.066 | 1.111 | 2.950 | 5.950 | 36 | [-0.412, 0.543] |
| VALID | 1× | 22 | 14 | 8 | 63.600 | 1.754 | -1.064 | 0.729 | 2.884 | 16.040 | 2.100 | 15 | [0.003, 1.389] |
| VALID | 2× | 22 | 14 | 8 | 63.600 | 1.694 | -1.128 | 0.668 | 2.628 | 14.690 | 2.200 | 15 | [-0.063, 1.334] |
| OOS | 1× | 35 | 14 | 21 | 40.000 | 1.739 | -1.006 | 0.092 | 1.153 | 3.220 | 5.750 | 26 | [-0.367, 0.551] |
| OOS | 2× | 35 | 14 | 21 | 40.000 | 1.686 | -1.049 | 0.045 | 1.072 | 1.580 | 6.260 | 26 | [-0.414, 0.504] |

By instrument (net R 1×; n / mean):

| inst | size_DEV | size_OOS | size_VALID | mean_DEV | mean_OOS | mean_VALID |
|---|---|---|---|---|---|---|
| ALUMINIUM | 6 | 4 | 4 | 0.017 | -0.744 | 0.068 |
| COPPER | 4 | 7 | 5 | 0.018 | -0.055 | 0.748 |
| CRUDEOIL | 12 | 7 | 1 | 0.346 | 0.266 | -1.019 |
| GOLD | 8 | 5 | 1 | 0.354 | 0.241 | 1.983 |
| NATURALGAS | 3 | 2 | 5 | -1.032 | 1.920 | 0.490 |
| SILVER | 6 | 5 | 2 | 0.020 | -0.462 | 1.990 |
| ZINC | 6 | 5 | 4 | 0.092 | 0.398 | 1.158 |

## FH_MCX_4h_BUY — REJECTED

OOS 95% CI lower bound -0.538 not > 0 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)

signals 145 · executed trades 56 · rejected 89 · reasons: {"skipped: position already open / switch day / warm-up edge": 87, "next open beyond the 0.5-ATR entry zone": 2}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 22 | 9 | 13 | 40.900 | 2.133 | -1.038 | 0.260 | 1.423 | 5.710 | 5.100 | 17 | [-0.491, 1.01] |
| DEV | 2× | 22 | 9 | 13 | 40.900 | 2.103 | -1.075 | 0.225 | 1.354 | 4.950 | 5.210 | 17 | [-0.529, 0.979] |
| VALID | 1× | 14 | 8 | 6 | 57.100 | 2.027 | -0.999 | 0.730 | 2.704 | 10.220 | 3.130 | 11 | [-0.552, 2.032] |
| VALID | 2× | 14 | 8 | 6 | 57.100 | 1.963 | -1.050 | 0.672 | 2.493 | 9.400 | 3.270 | 11 | [-0.608, 1.978] |
| OOS | 1× | 20 | 8 | 12 | 40.000 | 1.686 | -0.915 | 0.125 | 1.228 | 2.510 | 6.480 | 15 | [-0.538, 0.789] |
| OOS | 2× | 20 | 8 | 12 | 40.000 | 1.631 | -0.952 | 0.082 | 1.143 | 1.630 | 6.800 | 15 | [-0.579, 0.742] |

By instrument (net R 1×; n / mean):

| inst | size_DEV | size_OOS | size_VALID | mean_DEV | mean_OOS | mean_VALID |
|---|---|---|---|---|---|---|
| ALUMINIUM | 4.000 | — | 2.000 | -0.747 | — | 0.525 |
| COPPER | — | 5.000 | 4.000 | — | -0.462 | -0.047 |
| CRUDEOIL | 9.000 | 4.000 | — | 0.995 | 0.662 | — |
| GOLD | 4.000 | 2.000 | 1.000 | 0.289 | -1.070 | 2.984 |
| NATURALGAS | — | 1.000 | 2.000 | — | -0.426 | 0.699 |
| SILVER | 2.000 | 2.000 | 1.000 | -1.007 | -1.014 | -1.123 |
| ZINC | 3.000 | 6.000 | 4.000 | 0.200 | 1.127 | 1.524 |

## BO_MCX_1d_BUY — INSUFFICIENT_DATA

OOS 0 trades / 0 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)

signals 0 · executed trades 0 · rejected 0 · reasons: {}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| DEV | 2× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| VALID | 1× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| VALID | 2× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| OOS | 1× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |
| OOS | 2× | 0 | 0 | 0 | — | — | — | — | — | — | — | 0 | — |

## FH_STK_3h_SELL — REJECTED

OOS 95% CI lower bound -0.126 not > 0 | stock universe = today's F&O list (survivorship)

signals 586 · executed trades 380 · rejected 206 · reasons: {"skipped: position already open / switch day / warm-up edge": 187, "next open beyond the 0.5-ATR entry zone": 19}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 14 | 12 | 2 | 85.700 | 1.146 | -1.025 | 0.836 | 6.710 | 11.700 | 1.030 | 9 | [0.084, 1.44] |
| DEV | 2× | 14 | 12 | 2 | 85.700 | 1.120 | -1.049 | 0.810 | 6.405 | 11.340 | 1.060 | 9 | [0.056, 1.413] |
| VALID | 1× | 113 | 50 | 63 | 44.200 | 0.663 | -0.896 | -0.206 | 0.588 | -23.270 | 30.190 | 28 | [-0.516, 0.049] |
| VALID | 2× | 113 | 45 | 68 | 39.800 | 0.699 | -0.861 | -0.239 | 0.538 | -27.060 | 33.660 | 28 | [-0.547, 0.014] |
| OOS | 1× | 253 | 131 | 122 | 51.800 | 1.052 | -0.611 | 0.250 | 1.851 | 63.350 | 5.510 | 47 | [-0.126, 0.695] |
| OOS | 2× | 253 | 125 | 128 | 49.400 | 1.060 | -0.620 | 0.210 | 1.670 | 53.180 | 5.790 | 47 | [-0.166, 0.653] |

By instrument (net R 1×; n / mean):

| inst | size_DEV | size_OOS | size_VALID | mean_DEV | mean_OOS | mean_VALID |
|---|---|---|---|---|---|---|
| 360ONE | — | 1.000 | — | — | 0.121 | — |
| ABB | — | 2.000 | — | — | 0.551 | — |
| ADANIENSOL | — | 2.000 | — | — | 1.303 | — |
| ADANIENT | 1.000 | 3.000 | — | 0.610 | -0.319 | — |
| ADANIGREEN | — | 3.000 | — | — | -0.424 | — |
| ALKEM | — | 1.000 | — | — | -0.266 | — |
| AMBER | — | 2.000 | — | — | -0.338 | — |
| AMBUJACEM | — | 3.000 | 2.000 | — | 0.372 | -1.034 |
| ANGELONE | — | 1.000 | — | — | 1.748 | — |
| APLAPOLLO | — | — | 2.000 | — | — | 0.113 |
| ASIANPAINT | — | 2.000 | — | — | -0.109 | — |
| ASTRAL | — | 2.000 | 2.000 | — | -0.202 | 0.480 |
| AXISBANK | — | 1.000 | — | — | -1.047 | — |
| BAJAJFINSV | — | 2.000 | 1.000 | — | 0.235 | 0.231 |
| BAJFINANCE | — | 2.000 | — | — | 0.116 | — |
| BANKBARODA | 1.000 | 4.000 | 1.000 | 1.274 | -0.074 | 0.745 |
| BDL | — | 2.000 | 1.000 | — | 0.916 | -1.020 |
| BEL | — | 4.000 | 2.000 | — | 0.583 | -0.248 |
| BHARATFORG | — | 2.000 | — | — | -0.084 | — |
| BHARTIARTL | — | 1.000 | — | — | 0.773 | — |
| BIOCON | — | 2.000 | 1.000 | — | 0.742 | -1.036 |
| BLUESTARCO | — | 3.000 | — | — | -0.397 | — |
| BPCL | — | — | 1.000 | — | — | -1.424 |
| BRITANNIA | — | 2.000 | 2.000 | — | 0.575 | -0.152 |
| BSE | — | 3.000 | — | — | -1.029 | — |
| CAMS | — | 2.000 | — | — | 1.054 | — |
| CDSL | — | 1.000 | — | — | 0.259 | — |
| CHOLAFIN | — | — | 1.000 | — | — | 0.128 |
| CIPLA | — | 1.000 | — | — | -0.705 | — |
| COALINDIA | — | 3.000 | 1.000 | — | 0.134 | -1.043 |
| COCHINSHIP | — | 1.000 | — | — | -0.106 | — |
| COFORGE | — | — | 1.000 | — | — | -1.021 |
| COLPAL | — | 3.000 | 1.000 | — | 0.881 | -1.042 |
| CONCOR | — | 2.000 | — | — | 1.050 | — |
| CROMPTON | — | 2.000 | 1.000 | — | 0.820 | 0.494 |
| CUMMINSIND | — | 3.000 | — | — | 0.868 | — |
| DABUR | — | 3.000 | — | — | 0.028 | — |
| DELHIVERY | — | 2.000 | — | — | 0.462 | — |
| DIXON | — | 1.000 | — | — | 1.965 | — |
| DMART | — | 4.000 | — | — | 0.728 | — |
| DRREDDY | — | 1.000 | — | — | 0.513 | — |
| EICHERMOT | — | 3.000 | 1.000 | — | 0.216 | -1.031 |
| FEDERALBNK | — | 1.000 | — | — | 0.176 | — |
| FORCEMOT | — | 1.000 | — | — | -0.242 | — |
| FORTIS | — | 2.000 | — | — | 0.465 | — |
| GLENMARK | — | — | 1.000 | — | — | -1.035 |
| GODFRYPHLP | — | 2.000 | — | — | 0.539 | — |
| GODREJCP | — | 1.000 | 1.000 | — | 0.776 | 0.221 |
| GODREJPROP | — | 1.000 | — | — | 1.346 | — |
| HAL | 1.000 | — | — | 1.045 | — | — |
| HAVELLS | — | 1.000 | 1.000 | — | 1.494 | 1.957 |
| HCLTECH | 1.000 | — | 2.000 | 1.216 | — | 0.076 |
| HDFCAMC | — | 2.000 | — | — | 1.137 | — |
| HDFCBANK | — | 2.000 | 1.000 | — | -0.244 | 0.230 |
| HDFCLIFE | 1.000 | 2.000 | — | 1.084 | -0.422 | — |
| HEROMOTOCO | — | 2.000 | 3.000 | — | 0.465 | -0.334 |
| HINDALCO | — | 1.000 | — | — | 0.347 | — |
| HINDPETRO | — | 2.000 | 1.000 | — | 0.459 | -1.336 |
| HINDUNILVR | — | 3.000 | 2.000 | — | 0.652 | 0.452 |
| HINDZINC | — | 3.000 | 1.000 | — | -0.659 | 0.851 |
| ICICIBANK | — | 1.000 | 1.000 | — | 1.934 | -1.045 |
| ICICIGI | — | 2.000 | 2.000 | — | -0.509 | -0.468 |
| ICICIPRULI | 1.000 | 3.000 | 2.000 | 1.449 | 0.573 | -0.048 |
| INDHOTEL | — | — | 1.000 | — | — | -1.033 |
| INDIANB | — | 1.000 | 1.000 | — | 1.954 | 0.034 |
| INDIGO | — | 2.000 | — | — | 0.697 | — |
| INDUSINDBK | — | 2.000 | — | — | 0.169 | — |
| INDUSTOWER | 1.000 | 2.000 | 2.000 | 1.972 | 0.444 | -0.096 |
| INFY | 1.000 | 3.000 | 2.000 | 1.967 | -0.794 | 0.592 |
| ITC | — | 3.000 | 3.000 | — | -0.346 | 0.115 |
| JINDALSTEL | — | 1.000 | — | — | -1.041 | — |
| JIOFIN | — | 2.000 | — | — | 1.063 | — |
| JSWENERGY | — | 1.000 | — | — | 1.955 | — |
| JSWSTEEL | — | 1.000 | — | — | -0.357 | — |
| JUBLFOOD | 1.000 | 2.000 | 2.000 | -1.018 | 0.470 | 0.132 |
| KALYANKJIL | — | — | 2.000 | — | — | -0.507 |
| KAYNES | — | 1.000 | — | — | -0.535 | — |
| KEI | — | 2.000 | — | — | 0.146 | — |
| KFINTECH | — | 1.000 | 1.000 | — | -1.033 | -1.028 |
| KOTAKBANK | — | — | 2.000 | — | — | -1.036 |
| KPITTECH | — | 3.000 | 4.000 | — | -0.265 | -0.450 |
| LICHSGFIN | — | 2.000 | — | — | 0.917 | — |
| LICI | — | 1.000 | — | — | -0.156 | — |
| LODHA | — | 1.000 | — | — | -0.284 | — |
| LT | — | 2.000 | — | — | 0.444 | — |
| LTF | — | 1.000 | — | — | 1.258 | — |
| LUPIN | — | 2.000 | — | — | 0.267 | — |
| M&M | — | 1.000 | 2.000 | — | 1.220 | 0.855 |
| MARICO | — | 2.000 | — | — | 0.221 | — |
| MARUTI | — | 4.000 | 1.000 | — | 0.229 | 0.779 |
| MAXHEALTH | — | 1.000 | — | — | -0.107 | — |
| MAZDOCK | 1.000 | 1.000 | 1.000 | 0.672 | -0.024 | -0.392 |
| MCX | — | 2.000 | 1.000 | — | -0.417 | -1.020 |
| MFSL | — | 4.000 | 2.000 | — | -0.518 | -0.806 |
| MPHASIS | — | — | 1.000 | — | — | -1.023 |
| MUTHOOTFIN | — | 3.000 | 3.000 | — | -0.526 | -0.499 |
| NAM-INDIA | — | 1.000 | — | — | 0.823 | — |
| NATIONALUM | — | 1.000 | 1.000 | — | 0.077 | 0.094 |
| NAUKRI | — | — | 1.000 | — | — | 0.525 |
| NESTLEIND | — | 2.000 | — | — | 1.438 | — |
| NTPC | — | 3.000 | 1.000 | — | -0.520 | 0.393 |
| OBEROIRLTY | — | 1.000 | — | — | 0.008 | — |
| OFSS | — | 1.000 | — | — | 1.036 | — |
| OIL | — | — | 1.000 | — | — | -0.704 |
| ONGC | — | 1.000 | 1.000 | — | 0.596 | 1.950 |
| PAGEIND | — | 2.000 | — | — | -0.527 | — |
| PATANJALI | — | 1.000 | 3.000 | — | -0.295 | -0.398 |
| PERSISTENT | — | — | 3.000 | — | — | -0.600 |
| PFC | — | 4.000 | — | — | 0.979 | — |
| PGEL | — | 2.000 | 1.000 | — | 0.301 | -1.020 |
| PIDILITIND | — | 1.000 | — | — | 2.133 | — |
| PIIND | — | 3.000 | 2.000 | — | 0.446 | 1.087 |
| POLICYBZR | — | 1.000 | — | — | -1.033 | — |
| POLYCAB | — | 1.000 | — | — | 0.726 | — |
| POWERGRID | — | 1.000 | 1.000 | — | -1.046 | 0.083 |
| POWERINDIA | — | 3.000 | — | — | 0.196 | — |
| PREMIERENE | — | 2.000 | — | — | 0.504 | — |
| PRESTIGE | 1.000 | 1.000 | — | 0.830 | -0.128 | — |
| RECLTD | — | 2.000 | — | — | -0.366 | — |
| RELIANCE | — | 3.000 | 1.000 | — | 0.690 | -1.046 |
| RVNL | — | 2.000 | 1.000 | — | 1.348 | 0.458 |
| SBICARD | 1.000 | 1.000 | — | 1.223 | 1.526 | — |
| SBILIFE | — | 1.000 | 2.000 | — | -0.156 | 0.063 |
| SBIN | — | 1.000 | 1.000 | — | 1.939 | -0.055 |
| SHREECEM | — | 1.000 | — | — | -0.386 | — |
| SHRIRAMFIN | — | 1.000 | — | — | 0.789 | — |
| SIEMENS | — | 1.000 | — | — | 0.325 | — |
| SRF | — | 4.000 | — | — | 0.676 | — |
| SUNPHARMA | — | 1.000 | 1.000 | — | -0.471 | -1.035 |
| SUPREMEIND | — | — | 1.000 | — | — | 1.969 |
| SWIGGY | — | 1.000 | 1.000 | — | 0.039 | 0.385 |
| TATACONSUM | — | 3.000 | 1.000 | — | -0.280 | -1.046 |
| TATAELXSI | — | 1.000 | 3.000 | — | 1.184 | -0.509 |
| TATAPOWER | — | 3.000 | 1.000 | — | -0.344 | 0.478 |
| TATASTEEL | — | 2.000 | 1.000 | — | -0.126 | 0.936 |
| TCS | 1.000 | 1.000 | 2.000 | -1.031 | 1.137 | -1.032 |
| TECHM | — | 1.000 | 1.000 | — | -1.031 | -0.800 |
| TIINDIA | — | 4.000 | — | — | 0.141 | — |
| TITAN | — | 1.000 | — | — | -1.038 | — |
| TMPV | 1.000 | 4.000 | — | 0.409 | 0.559 | — |
| TRENT | — | 2.000 | — | — | 1.033 | — |
| TVSMOTOR | — | — | 2.000 | — | — | -0.564 |
| UNITDSPR | — | 1.000 | 1.000 | — | 0.490 | -0.652 |
| UNOMINDA | — | 1.000 | 1.000 | — | -1.033 | -1.021 |
| UPL | — | 2.000 | 3.000 | — | 0.754 | -0.212 |
| VBL | — | 2.000 | — | — | -0.681 | — |
| VEDL | — | 2.000 | 1.000 | — | 0.263 | -1.036 |
| VOLTAS | — | 1.000 | 1.000 | — | -1.039 | 0.204 |
| WAAREEENER | — | 3.000 | 2.000 | — | 0.292 | 0.464 |

## SHADOW_MCX_DTC_GOLD_SILVER — REJECTED

OOS 95% CI lower bound -0.276 not > 0 | shadow rule (never sent); window info {"GOLD": {"sessions": 257, "first": "2025-11-04", "last": "2026-11-03", "warmup_until": "2025-11-25"}, "SILVER": {"sessions": 258, "first": "2025-11-04", "last": "2026-11-03", "warmup_until": "2025-11-25"}}; signal = trade (no entry filters in this rule)

signals 158 · executed trades 158 · rejected 0 · reasons: {}

| period | cost | trades | wins | losses | win % | avg win R | avg loss R | expectancy R | PF | net R | max DD R | dates | 95% CI (cons.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV | 1× | 85 | 42 | 43 | 49.400 | 0.987 | -0.766 | 0.100 | 1.259 | 8.520 | 5.040 | 37 | [-0.261, 0.462] |
| DEV | 2× | 85 | 42 | 43 | 49.400 | 0.970 | -0.781 | 0.084 | 1.214 | 7.170 | 5.240 | 37 | [-0.277, 0.446] |
| VALID | 1× | 25 | 15 | 10 | 60.000 | 0.535 | -0.400 | 0.161 | 2.008 | 4.030 | 1.020 | 15 | [-0.135, 0.457] |
| VALID | 2× | 25 | 15 | 10 | 60.000 | 0.519 | -0.413 | 0.146 | 1.884 | 3.650 | 1.050 | 15 | [-0.15, 0.442] |
| OOS | 1× | 48 | 24 | 24 | 50.000 | 1.100 | -0.506 | 0.297 | 2.176 | 14.270 | 2.880 | 20 | [-0.276, 0.87] |
| OOS | 2× | 48 | 24 | 24 | 50.000 | 1.079 | -0.523 | 0.278 | 2.063 | 13.350 | 3.060 | 20 | [-0.294, 0.851] |

By instrument (net R 1×; n / mean):

| inst | size_DEV | size_OOS | size_VALID | mean_DEV | mean_OOS | mean_VALID |
|---|---|---|---|---|---|---|
| GOLD | 37 | 20 | 9 | 0.215 | 0.308 | 0.277 |
| SILVER | 48 | 28 | 16 | 0.012 | 0.290 | 0.096 |

## Breakdowns across all E1 trades (1× cost)

### by mkt × period

| mkt | period | trades | win_pct | expectancy_R | net_R |
|---|---|---|---|---|---|
| MCX | DEV | 302 | 41.100 | 0.162 | 49.038 |
| MCX | OOS | 211 | 43.600 | 0.203 | 42.812 |
| MCX | VALID | 164 | 49.400 | 0.280 | 45.923 |
| STOCKS | DEV | 32 | 75.000 | 0.413 | 13.207 |
| STOCKS | OOS | 494 | 53.000 | 0.266 | 131.375 |
| STOCKS | VALID | 386 | 40.700 | -0.184 | -71.150 |

### by side_txt × period

| side_txt | period | trades | win_pct | expectancy_R | net_R |
|---|---|---|---|---|---|
| BUY | DEV | 276 | 39.900 | 0.162 | 44.707 |
| BUY | OOS | 181 | 42.500 | 0.160 | 29.007 |
| BUY | VALID | 146 | 47.900 | 0.288 | 42.033 |
| SELL | DEV | 58 | 65.500 | 0.302 | 17.538 |
| SELL | OOS | 524 | 52.900 | 0.277 | 145.181 |
| SELL | VALID | 404 | 41.600 | -0.166 | -67.260 |

### by holding × period

| holding | period | trades | win_pct | expectancy_R | net_R |
|---|---|---|---|---|---|
| 1-5 days | DEV | 123 | 33.300 | -0.016 | -1.955 |
| 1-5 days | OOS | 342 | 45.000 | 0.039 | 13.457 |
| 1-5 days | VALID | 233 | 29.600 | -0.326 | -75.998 |
| < 1 day | DEV | 38 | 23.700 | -0.543 | -20.627 |
| < 1 day | OOS | 97 | 23.700 | -0.229 | -22.191 |
| < 1 day | VALID | 38 | 34.200 | -0.412 | -15.655 |
| > 5 days | DEV | 88 | 63.600 | 0.867 | 76.303 |
| > 5 days | OOS | 218 | 70.200 | 0.774 | 168.653 |
| > 5 days | VALID | 254 | 55.500 | 0.246 | 62.398 |
| intraday (same session) | DEV | 85 | 49.400 | 0.100 | 8.523 |
| intraday (same session) | OOS | 48 | 50.000 | 0.297 | 14.269 |
| intraday (same session) | VALID | 25 | 60.000 | 0.161 | 4.029 |

### by tf × period

| tf | period | trades | win_pct | expectancy_R | net_R |
|---|---|---|---|---|---|
| 15m checkpoint | DEV | 85 | 49.400 | 0.100 | 8.523 |
| 15m checkpoint | OOS | 48 | 50.000 | 0.297 | 14.269 |
| 15m checkpoint | VALID | 25 | 60.000 | 0.161 | 4.029 |
| 1h | DEV | 71 | 36.600 | 0.195 | 13.879 |
| 1h | OOS | 43 | 41.900 | 0.117 | 5.030 |
| 1h | VALID | 40 | 37.500 | 0.031 | 1.230 |
| 2h | DEV | 56 | 32.100 | 0.203 | 11.386 |
| 2h | OOS | 42 | 42.900 | 0.194 | 8.137 |
| 2h | VALID | 41 | 43.900 | 0.240 | 9.849 |
| 3h | DEV | 77 | 55.800 | 0.233 | 17.949 |
| 3h | OOS | 529 | 52.200 | 0.254 | 134.597 |
| 3h | VALID | 408 | 41.900 | -0.135 | -55.110 |
| 4h | DEV | 45 | 42.200 | 0.234 | 10.508 |
| 4h | OOS | 43 | 41.900 | 0.283 | 12.155 |
| 4h | VALID | 36 | 52.800 | 0.410 | 14.776 |
