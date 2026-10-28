# STRATEGY-PROGRAM-001 – index / MCX futures breakouts (generated)

Win = trade closed with net R > 0 after costs. exp1/exp2 = mean net R per trade at 1×/2× costs. ci = 95 % month-block bootstrap. tgt/stop/gap = % of trades exiting at target / stop / gap through stop. invalid = signals cancelled before entry.


## angel · S1 · BUY

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train | 131 |        56 |  48.1 |    1.82 |   -1.07 |  0.32  |  0.251 | [+0.03,+0.57] | 1.58 |  9.1 |            6 |  42.7 |   50.4 |   5.3 |        |
| 2-valid |  91 |        33 |  41.8 |    1.69 |   -1.02 |  0.11  |  0.041 | [-0.23,+0.48] | 1.18 | 11.1 |           10 |  31.9 |   53.8 |   5.5 | n<100  |
| 3-test  | 123 |        89 |  52.8 |    1.62 |   -1.06 |  0.355 |  0.288 | [+0.09,+0.63] | 1.71 |  9.5 |            9 |  40.7 |   45.5 |   1.6 |        |
| ALL     | 345 |       178 |  48.1 |    1.71 |   -1.05 |  0.277 |  0.209 | [+0.10,+0.44] | 1.51 | 13.2 |           10 |  39.1 |   49.6 |   4.1 |        |

by year: 2022: n17 -0.04R w35%; 2023: n61 +0.36R w49%; 2024: n94 +0.25R w46%; 2025: n115 +0.30R w50%; 2026: n58 +0.29R w50%

by instrument: ALUMINIUM: n47 +0.02R; BANKNIFTY: n15 +0.21R; COPPER: n57 +0.23R; CRUDEOIL: n36 +0.12R; GOLD: n70 +0.58R; NIFTY: n15 -0.20R; SILVER: n62 +0.26R; ZINC: n43 +0.47R

by regime: range/hi-vol: n66 +0.13R w44%; range/lo-vol: n131 +0.35R w51%; trend/hi-vol: n86 +0.42R w52%; trend/lo-vol: n62 +0.07R w40%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict                     |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:----------------------------|
| A1 trend ADX≥25                                      |        70 |        47.1 |        0.251 |    -0.007 |        45 |        33.3 |       -0.22  |    -0.266 |       69 |       43.5 |       0.115 |   -0.186 | FAIL train                  |
| A2 high volatility                                   |        75 |        45.3 |        0.2   |    -0.054 |        34 |        35.3 |       -0.145 |    -0.202 |       60 |       51.7 |       0.226 |   -0.073 | FAIL train                  |
| A3 low volatility                                    |        69 |        46.4 |        0.174 |    -0.072 |        58 |        44.8 |        0.131 |     0.099 |       74 |       51.4 |       0.26  |   -0.02  | FAIL train                  |
| A4 vol expanding ATR14>ATR50                         |        83 |        43.4 |        0.136 |    -0.117 |        46 |        39.1 |       -0.022 |    -0.074 |       70 |       51.4 |       0.225 |   -0.069 | FAIL train                  |
| A5 not stretched ≤3 ATR from EMA200                  |        36 |        52.8 |        0.3   |     0.068 |        30 |        33.3 |       -0.172 |    -0.2   |       25 |       44   |      -0.104 |   -0.398 | pass train, FAIL valid      |
| A6 momentum ROC20 aligned                            |       131 |        48.1 |        0.251 |     0     |        91 |        41.8 |        0.041 |     0     |      123 |       52.8 |       0.288 |    0     | FAIL train                  |
| B1 extension ≤1 ATR                                  |       109 |        49.5 |        0.266 |     0.018 |        76 |        44.7 |        0.094 |     0.054 |      105 |       51.4 |       0.214 |   -0.071 | pass train+valid, FAIL test |
| B2 close near extreme (CLV)                          |       105 |        52.4 |        0.378 |     0.13  |        72 |        40.3 |       -0.004 |    -0.046 |       97 |       56.7 |       0.412 |    0.126 | pass train, FAIL valid      |
| B3 strong body ≥50%                                  |       102 |        52   |        0.332 |     0.085 |        75 |        42.7 |        0.072 |     0.033 |      100 |       54   |       0.322 |    0.036 | PASS all 3                  |
| B4 prior compression                                 |        57 |        49.1 |        0.255 |     0.005 |        35 |        45.7 |        0.075 |     0.043 |       49 |       55.1 |       0.334 |    0.061 | PASS all 3                  |
| B5 room ≥3 ATR to older level                        |       110 |        49.1 |        0.286 |     0.032 |        77 |        41.6 |       -0.011 |    -0.053 |       94 |       52.1 |       0.275 |   -0.015 | pass train, FAIL valid      |
| C1 volume ≥2×                                        |        97 |        48.5 |        0.291 |     0.041 |        60 |        36.7 |       -0.054 |    -0.096 |       86 |       48.8 |       0.232 |   -0.057 | pass train, FAIL valid      |
| C2 RSI not exhausted                                 |       102 |        51   |        0.326 |     0.079 |        81 |        44.4 |        0.106 |     0.065 |       95 |       51.6 |       0.232 |   -0.048 | pass train+valid, FAIL test |
| X1 stop 2 ATR · target 1R                            |       160 |        60   |        0.059 |    -0.193 |       102 |        55.9 |       -0.019 |    -0.059 |      146 |       63.7 |       0.128 |   -0.16  | FAIL train                  |
| X2 stop 2 ATR · target 0.75R                         |       167 |        62.9 |       -0.039 |    -0.291 |       109 |        61.5 |       -0.051 |    -0.091 |      155 |       67.7 |       0.052 |   -0.236 | FAIL train                  |
| X3 stop 2 ATR · target 0.5R                          |       183 |        72.7 |       -0.048 |    -0.301 |       119 |        69.7 |       -0.085 |    -0.127 |      165 |       73.3 |      -0.03  |   -0.32  | FAIL train                  |
| X4 stop 3 ATR · target 0.5R                          |       102 |        73.5 |       -0.004 |    -0.272 |        77 |        77.9 |        0.084 |     0.027 |      115 |       73.9 |       0.006 |   -0.298 | FAIL train                  |
| X5 stop 1.5 ATR · target 2R                          |       156 |        43.6 |        0.085 |    -0.141 |        97 |        42.3 |        0.053 |     0.035 |      154 |       44.8 |       0.106 |   -0.166 | FAIL train                  |
| X6 stop 2.5 ATR · target 3R                          |       101 |        47.5 |        0.362 |     0.102 |        74 |        41.9 |        0.074 |     0.021 |       93 |       47.3 |       0.168 |   -0.125 | pass train+valid, FAIL test |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |        51 |        47.1 |        0.087 |    -0.182 |        32 |        50   |        0.049 |    -0.015 |       49 |       53.1 |       0.167 |   -0.129 | FAIL train                  |


## angel · S1 · SELL

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train |  92 |        84 |  33.7 |    1.55 |   -1.04 | -0.169 | -0.271 | [-0.45,+0.08] | 0.75 | 16.1 |           10 |  23.9 |   60.9 |   5.4 | n<100  |
| 2-valid |  59 |        40 |  37.3 |    1.65 |   -1.09 | -0.069 | -0.139 | [-0.79,+0.46] | 0.9  | 20.1 |           13 |  30.5 |   59.3 |   5.1 | n<100  |
| 3-test  |  61 |        60 |  45.9 |    1.42 |   -1.13 |  0.04  | -0.019 | [-0.57,+0.45] | 1.07 | 13   |            5 |  29.5 |   52.5 |   9.8 | n<100  |
| ALL     | 212 |       184 |  38.2 |    1.53 |   -1.08 | -0.081 | -0.162 | [-0.35,+0.16] | 0.88 | 33.2 |           15 |  27.4 |   58   |   6.6 |        |

by year: 2022: n5 -0.70R w20%; 2023: n60 -0.08R w33%; 2024: n60 -0.29R w33%; 2025: n43 +0.01R w42%; 2026: n44 +0.18R w50%

by instrument: ALUMINIUM: n36 +0.18R; BANKNIFTY: n12 +0.15R; COPPER: n30 -0.00R; CRUDEOIL: n24 -0.60R; GOLD: n28 -0.13R; NIFTY: n17 -0.07R; SILVER: n35 -0.03R; ZINC: n30 -0.17R

by regime: range/hi-vol: n65 -0.23R w35%; range/lo-vol: n68 +0.04R w38%; trend/hi-vol: n48 -0.10R w38%; trend/lo-vol: n31 -0.01R w45%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict    |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:-----------|
| A1 trend ADX≥25                                      |        38 |        28.9 |       -0.442 |    -0.155 |        35 |        37.1 |       -0.066 |     0.067 |       31 |       54.8 |       0.231 |    0.246 | FAIL train |
| A2 high volatility                                   |        53 |        32.1 |       -0.37  |    -0.116 |        39 |        35.9 |       -0.144 |    -0.015 |       25 |       52   |       0.055 |    0.071 | FAIL train |
| A3 low volatility                                    |        49 |        34.7 |       -0.181 |     0.106 |        23 |        39.1 |       -0.166 |    -0.011 |       39 |       43.6 |       0.009 |    0.029 | FAIL train |
| A4 vol expanding ATR14>ATR50                         |        46 |        30.4 |       -0.439 |    -0.181 |        33 |        48.5 |        0.266 |     0.399 |       25 |       48   |      -0.015 |   -0.001 | FAIL train |
| A5 not stretched ≤3 ATR from EMA200                  |        57 |        36.8 |       -0.211 |     0.055 |        28 |        35.7 |       -0.167 |    -0.035 |       29 |       55.2 |       0.183 |    0.219 | FAIL train |
| A6 momentum ROC20 aligned                            |        92 |        33.7 |       -0.271 |     0     |        59 |        37.3 |       -0.139 |     0     |       61 |       45.9 |      -0.019 |    0     | FAIL train |
| B1 extension ≤1 ATR                                  |        79 |        35.4 |       -0.229 |     0.043 |        45 |        31.1 |       -0.361 |    -0.219 |       50 |       40   |      -0.203 |   -0.178 | FAIL train |
| B2 close near extreme (CLV)                          |        76 |        35.5 |       -0.198 |     0.067 |        51 |        33.3 |       -0.242 |    -0.104 |       42 |       47.6 |       0.056 |    0.07  | FAIL train |
| B3 strong body ≥50%                                  |        79 |        32.9 |       -0.273 |    -0.004 |        51 |        41.2 |       -0.03  |     0.112 |       46 |       47.8 |      -0.018 |   -0     | FAIL train |
| B4 prior compression                                 |        38 |        26.3 |       -0.417 |    -0.138 |        23 |        17.4 |       -0.745 |    -0.615 |       25 |       32   |      -0.386 |   -0.374 | FAIL train |
| B5 room ≥3 ATR to older level                        |        72 |        27.8 |       -0.389 |    -0.12  |        45 |        42.2 |        0.028 |     0.169 |       47 |       46.8 |       0.029 |    0.047 | FAIL train |
| C1 volume ≥2×                                        |        55 |        27.3 |       -0.359 |    -0.092 |        46 |        32.6 |       -0.212 |    -0.07  |       33 |       57.6 |       0.353 |    0.366 | FAIL train |
| C2 RSI not exhausted                                 |        81 |        35.8 |       -0.207 |     0.065 |        44 |        22.7 |       -0.504 |    -0.369 |       49 |       46.9 |      -0.012 |    0.006 | FAIL train |
| X1 stop 2 ATR · target 1R                            |       104 |        48.1 |       -0.27  |     0.002 |        67 |        49.3 |       -0.148 |    -0.008 |       70 |       54.3 |      -0.104 |   -0.086 | FAIL train |
| X2 stop 2 ATR · target 0.75R                         |       109 |        56.9 |       -0.223 |     0.048 |        70 |        57.1 |       -0.148 |    -0.007 |       76 |       60.5 |      -0.116 |   -0.099 | FAIL train |
| X3 stop 2 ATR · target 0.5R                          |       119 |        68.9 |       -0.168 |     0.103 |        75 |        64   |       -0.188 |    -0.047 |       78 |       62.8 |      -0.201 |   -0.184 | FAIL train |
| X4 stop 3 ATR · target 0.5R                          |        89 |        67.4 |       -0.141 |     0.104 |        34 |        70.6 |       -0.067 |     0.065 |       40 |       72.5 |      -0.05  |   -0.039 | FAIL train |
| X5 stop 1.5 ATR · target 2R                          |       117 |        34.2 |       -0.255 |     0.036 |        73 |        38.4 |       -0.022 |     0.132 |       76 |       36.8 |      -0.133 |   -0.099 | FAIL train |
| X6 stop 2.5 ATR · target 3R                          |        70 |        38.6 |       -0.164 |     0.094 |        39 |        35.9 |       -0.109 |     0.022 |       42 |       54.8 |       0.387 |    0.4   | FAIL train |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |        40 |        40   |       -0.171 |     0.075 |        12 |        33.3 |       -0.419 |    -0.295 |       15 |       46.7 |       0.02  |    0.028 | FAIL train |


## angel · S2 · BUY

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train |  17 |         6 |  64.7 |    2.76 |   -1.04 |  1.417 |  1.372 | [+0.55,+2.13] | 4.87 |  3.1 |            3 |  52.9 |   35.3 |   0   | n<30   |
| 2-valid |  23 |         9 |  34.8 |    1.47 |   -0.89 | -0.069 | -0.113 | [-0.71,+0.70] | 0.88 |  8.8 |           10 |   8.7 |   52.2 |   4.3 | n<30   |
| 3-test  |  32 |        30 |  56.2 |    2.27 |   -0.85 |  0.904 |  0.866 | [+0.27,+1.46] | 3.44 |  3.4 |            4 |  31.2 |   34.4 |   0   | n<100  |
| ALL     |  72 |        45 |  51.4 |    2.24 |   -0.9  |  0.714 |  0.673 | [+0.24,+1.15] | 2.63 |  9.5 |           10 |  29.2 |   40.3 |   1.4 | n<100  |

by year: 2023: n5 +0.94R w60%; 2024: n23 +0.81R w52%; 2025: n31 +0.62R w48%; 2026: n13 +0.69R w54%

by instrument: ALUMINIUM: n13 +0.30R; BANKNIFTY: n3 +1.03R; COPPER: n13 +0.86R; CRUDEOIL: n2 +0.34R; GOLD: n14 +0.98R; NIFTY: n6 +0.09R; SILVER: n12 +1.08R; ZINC: n9 +0.58R

by regime: range/hi-vol: n21 +0.39R w43%; range/lo-vol: n25 +0.63R w56%; trend/hi-vol: n16 +1.27R w62%; trend/lo-vol: n10 +0.73R w40%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict    |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:-----------|
| A1 trend ADX≥25                                      |        12 |        66.7 |        1.374 |     0.005 |         7 |        28.6 |       -0.021 |     0.091 |       15 |       46.7 |       0.757 |   -0.122 | FAIL train |
| A2 high volatility                                   |        12 |        58.3 |        1.163 |    -0.206 |        10 |        30   |       -0.027 |     0.074 |       16 |       62.5 |       1.022 |    0.148 | FAIL train |
| A3 low volatility                                    |         7 |        71.4 |        1.564 |     0.189 |        13 |        38.5 |       -0.18  |    -0.057 |       17 |       52.9 |       0.794 |   -0.066 | FAIL train |
| A4 vol expanding ATR14>ATR50                         |        14 |        71.4 |        1.532 |     0.162 |        12 |        33.3 |        0.005 |     0.106 |       19 |       73.7 |       1.238 |    0.376 | FAIL train |
| A5 not stretched ≤3 ATR from EMA200                  |         2 |       100   |        2.849 |     1.507 |         5 |        60   |       -0.106 |     0.036 |        1 |        0   |      -0.445 |   -1.259 | FAIL train |
| A6 momentum ROC20 aligned                            |        17 |        64.7 |        1.372 |     0     |        23 |        34.8 |       -0.113 |     0     |       32 |       56.2 |       0.866 |    0     | FAIL train |
| B1 extension ≤1 ATR                                  |        14 |        64.3 |        1.292 |    -0.084 |        19 |        36.8 |       -0.006 |     0.109 |       25 |       64   |       1.044 |    0.181 | FAIL train |
| B2 close near extreme (CLV)                          |        14 |        64.3 |        1.241 |    -0.127 |        21 |        33.3 |       -0.203 |    -0.088 |       27 |       59.3 |       0.992 |    0.125 | FAIL train |
| B3 strong body ≥50%                                  |        14 |        64.3 |        1.418 |     0.046 |        22 |        36.4 |       -0.07  |     0.044 |       24 |       62.5 |       1.088 |    0.218 | FAIL train |
| B4 prior compression                                 |         2 |        50   |        0.929 |    -0.453 |        16 |        31.2 |       -0.148 |    -0.036 |       13 |       38.5 |      -0.017 |   -0.881 | FAIL train |
| B5 room ≥3 ATR to older level                        |        15 |        66.7 |        1.271 |    -0.098 |        16 |        43.8 |        0.13  |     0.243 |       28 |       50   |       0.719 |   -0.147 | FAIL train |
| C1 volume ≥2×                                        |         9 |        77.8 |        1.652 |     0.284 |         8 |        37.5 |       -0.305 |    -0.198 |       19 |       52.6 |       0.665 |   -0.203 | FAIL train |
| C2 RSI not exhausted                                 |         9 |        55.6 |        0.983 |    -0.385 |        21 |        38.1 |       -0.022 |     0.092 |       25 |       56   |       0.762 |   -0.1   | FAIL train |
| X1 stop 2 ATR · target 1R                            |        18 |        83.3 |        0.593 |    -0.787 |        20 |        40   |       -0.271 |    -0.166 |       32 |       68.8 |       0.333 |   -0.544 | FAIL train |
| X2 stop 2 ATR · target 0.75R                         |        20 |        85   |        0.414 |    -0.966 |        20 |        45   |       -0.241 |    -0.136 |       36 |       75   |       0.285 |   -0.591 | FAIL train |
| X3 stop 2 ATR · target 0.5R                          |        22 |        86.4 |        0.22  |    -1.159 |        21 |        47.6 |       -0.302 |    -0.198 |       37 |       83.8 |       0.229 |   -0.648 | FAIL train |
| X4 stop 3 ATR · target 0.5R                          |        11 |        72.7 |        0.139 |    -1.255 |         6 |        66.7 |       -0.05  |     0.044 |       11 |       72.7 |       0.094 |   -0.783 | FAIL train |
| X5 stop 1.5 ATR · target 2R                          |        18 |        72.2 |        1.074 |    -0.297 |        23 |        34.8 |       -0.174 |    -0.061 |       35 |       51.4 |       0.458 |   -0.41  | FAIL train |
| X6 stop 2.5 ATR · target 3R                          |        13 |        76.9 |        1.11  |    -0.281 |        15 |        33.3 |       -0.266 |    -0.169 |       19 |       52.6 |       0.472 |   -0.407 | FAIL train |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |         2 |       100   |        1.447 |     0.061 |         2 |         0   |       -1.07  |    -0.966 |        2 |       50   |       0.51  |   -0.359 | FAIL train |


## angel · S2 · SELL

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train |  11 |         1 |  27.3 |    1.71 |   -1.07 | -0.314 | -0.383 | [-1.09,+0.59] | 0.6  |  7.5 |            7 |   0   |   72.7 |   0   | n<30   |
| 2-valid |   4 |        14 |  75   |    0.56 |   -0.24 |  0.358 |  0.303 | n/a           | 6.94 |  0.2 |            1 |   0   |    0   |   0   | n<30   |
| 3-test  |   8 |         4 |  62.5 |    1.12 |   -1.76 |  0.043 |  0.003 | [-1.32,+0.97] | 1.07 |  3.2 |            1 |  12.5 |   37.5 |  12.5 | n<30   |
| ALL     |  23 |        19 |  47.8 |    1.13 |   -1.18 | -0.073 | -0.13  | [-0.62,+0.46] | 0.88 |  8   |            7 |   4.3 |   47.8 |   4.3 | n<30   |

by year: 2023: n7 +0.11R w43%; 2024: n5 -0.58R w20%; 2025: n4 +0.34R w75%; 2026: n7 -0.13R w57%

by instrument: ALUMINIUM: n3 +0.08R; BANKNIFTY: n2 -0.49R; COPPER: n2 -0.48R; CRUDEOIL: n3 +0.09R; GOLD: n1 +2.52R; NIFTY: n5 -0.05R; SILVER: n2 -1.03R; ZINC: n5 -0.09R

by regime: range/hi-vol: n4 +1.09R w100%; range/lo-vol: n13 -0.33R w38%; trend/hi-vol: n4 -1.38R w0%; trend/lo-vol: n2 +1.89R w100%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict    |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:-----------|
| A1 trend ADX≥25                                      |         1 |       100   |        2.441 |     2.827 |         2 |         0   |       -0.699 |    -1.008 |        5 |       20   |      -1.043 |   -1.048 | FAIL train |
| A2 high volatility                                   |         1 |         0   |       -1.048 |    -0.71  |         4 |        50   |       -0.038 |    -0.344 |        5 |       40   |      -0.49  |   -0.495 | FAIL train |
| A3 low volatility                                    |        11 |        27.3 |       -0.383 |     0     |         1 |       100   |        0.247 |    -0.041 |        3 |      100   |       0.824 |    0.826 | FAIL train |
| A4 vol expanding ATR14>ATR50                         |         1 |         0   |       -1.057 |    -0.714 |         1 |         0   |       -1.118 |    -1.417 |        3 |       33.3 |      -0.45  |   -0.461 | FAIL train |
| A5 not stretched ≤3 ATR from EMA200                  |         7 |        28.6 |       -0.442 |    -0.07  |         3 |        66.7 |        0.409 |     0.116 |        3 |       66.7 |      -0.099 |   -0.1   | FAIL train |
| A6 momentum ROC20 aligned                            |        11 |        27.3 |       -0.383 |     0     |         4 |        75   |        0.303 |     0     |        8 |       62.5 |       0.003 |    0     | FAIL train |
| B1 extension ≤1 ATR                                  |         9 |        22.2 |       -0.627 |    -0.236 |         3 |        33.3 |       -0.47  |    -0.788 |        4 |       50   |      -0.044 |   -0.044 | FAIL train |
| B2 close near extreme (CLV)                          |         9 |        22.2 |       -0.344 |     0.039 |         3 |        66.7 |        0.409 |     0.116 |        7 |       57.1 |      -0.41  |   -0.415 | FAIL train |
| B3 strong body ≥50%                                  |        10 |        20   |       -0.425 |    -0.041 |         4 |        75   |        0.303 |     0     |        7 |       57.1 |      -0.41  |   -0.415 | FAIL train |
| B4 prior compression                                 |         6 |        33.3 |       -0.305 |     0.057 |         1 |         0   |       -0.279 |    -0.599 |        1 |      100   |       2.933 |    2.923 | FAIL train |
| B5 room ≥3 ATR to older level                        |         9 |        22.2 |       -0.614 |    -0.229 |         3 |        33.3 |       -0.046 |    -0.343 |        7 |       71.4 |       0.465 |    0.463 | FAIL train |
| C1 volume ≥2×                                        |         3 |         0   |       -1.103 |    -0.737 |         1 |       100   |       -0.013 |    -0.347 |        3 |       33.3 |      -1.025 |   -1.031 | FAIL train |
| C2 RSI not exhausted                                 |        11 |        27.3 |       -0.383 |     0     |         3 |        66.7 |       -0.015 |    -0.329 |        6 |       83.3 |       0.361 |    0.36  | FAIL train |
| X1 stop 2 ATR · target 1R                            |        10 |        50   |       -0.198 |     0.172 |         3 |        66.7 |        0.518 |     0.209 |        8 |       75   |       0.036 |    0.023 | FAIL train |
| X2 stop 2 ATR · target 0.75R                         |        10 |        70   |        0.115 |     0.484 |         3 |        66.7 |        0.352 |     0.042 |        8 |       87.5 |       0.214 |    0.201 | FAIL train |
| X3 stop 2 ATR · target 0.5R                          |        11 |        72.7 |       -0.029 |     0.345 |         3 |       100   |        0.402 |     0.093 |        8 |       87.5 |       0.026 |    0.013 | FAIL train |
| X4 stop 3 ATR · target 0.5R                          |         4 |        75   |        0.102 |     0.456 |         1 |         0   |       -0.14  |    -0.479 |        4 |       75   |      -0.18  |   -0.2   | FAIL train |
| X5 stop 1.5 ATR · target 2R                          |        11 |        27.3 |       -0.487 |    -0.103 |         4 |        75   |        0.848 |     0.545 |        9 |       55.6 |      -0.226 |   -0.23  | FAIL train |
| X6 stop 2.5 ATR · target 3R                          |         7 |        28.6 |       -0.567 |    -0.205 |         2 |        50   |        0.294 |    -0.027 |        5 |       60   |       0.255 |    0.238 | FAIL train |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |         3 |        66.7 |       -0.02  |     0.318 |         1 |         0   |       -0.143 |    -0.482 |        1 |      100   |       0.587 |    0.571 | FAIL train |


## angel · S3 · BUY

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train |  49 |         9 |  53.1 |    1.5  |   -0.87 |  0.388 |  0.348 | [+0.08,+0.77] | 1.95 |  4.6 |            4 |  28.6 |   34.7 |   6.1 | n<100  |
| 2-valid |  35 |        17 |  40   |    1.47 |   -0.86 |  0.072 |  0.034 | [-0.39,+0.53] | 1.14 |  6.6 |            5 |  25.7 |   42.9 |   2.9 | n<100  |
| 3-test  |  32 |        22 |  53.1 |    1.48 |   -0.95 |  0.338 |  0.293 | [-0.09,+0.75] | 1.76 |  3.2 |            3 |  34.4 |   40.6 |   6.2 | n<100  |
| ALL     | 116 |        48 |  49.1 |    1.49 |   -0.89 |  0.279 |  0.238 | [+0.04,+0.51] | 1.62 |  6.6 |            5 |  29.3 |   38.8 |   5.2 |        |

by year: 2022: n8 -0.06R w38%; 2023: n22 +0.40R w55%; 2024: n38 +0.20R w42%; 2025: n31 +0.35R w55%; 2026: n17 +0.31R w53%

by instrument: ALUMINIUM: n13 -0.33R; BANKNIFTY: n16 +0.34R; COPPER: n16 +0.44R; CRUDEOIL: n7 -0.09R; GOLD: n21 +0.95R; NIFTY: n23 -0.09R; SILVER: n12 +0.07R; ZINC: n8 +0.76R

by regime: range/hi-vol: n29 -0.16R w34%; range/lo-vol: n46 +0.18R w48%; trend/hi-vol: n16 +0.38R w50%; trend/lo-vol: n25 +0.90R w68%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict                     |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:----------------------------|
| A1 trend ADX≥25                                      |        24 |        62.5 |        0.688 |     0.338 |         8 |        50   |        0.642 |     0.599 |       10 |       60   |       0.436 |    0.141 | pass train, FAIL valid      |
| A2 high volatility                                   |        17 |        35.3 |       -0.134 |    -0.487 |        16 |        31.2 |       -0.088 |    -0.12  |       12 |       58.3 |       0.28  |   -0.02  | FAIL train                  |
| A3 low volatility                                    |        31 |        61.3 |        0.601 |     0.255 |        19 |        47.4 |        0.136 |     0.101 |       20 |       50   |       0.3   |    0.012 | PASS all 3                  |
| A4 vol expanding ATR14>ATR50                         |        24 |        54.2 |        0.444 |     0.09  |        18 |        33.3 |       -0.098 |    -0.131 |       10 |       60   |       0.216 |   -0.074 | pass train, FAIL valid      |
| A5 not stretched ≤3 ATR from EMA200                  |         6 |        66.7 |        0.834 |     0.478 |         4 |        50   |       -0.015 |    -0.055 |        1 |        0   |      -1.098 |   -1.387 | FAIL train                  |
| A6 momentum ROC20 aligned                            |        49 |        53.1 |        0.348 |     0     |        35 |        40   |        0.034 |     0     |       32 |       53.1 |       0.293 |    0     | FAIL train                  |
| B1 extension ≤1 ATR                                  |        47 |        53.2 |        0.361 |     0.014 |        34 |        38.2 |        0.005 |    -0.028 |       28 |       57.1 |       0.433 |    0.143 | pass train, FAIL valid      |
| B2 close near extreme (CLV)                          |        40 |        52.5 |        0.254 |    -0.094 |        31 |        45.2 |        0.103 |     0.07  |       26 |       57.7 |       0.426 |    0.132 | FAIL train                  |
| B3 strong body ≥50%                                  |        35 |        51.4 |        0.268 |    -0.081 |        29 |        44.8 |        0.127 |     0.093 |       25 |       56   |       0.305 |    0.01  | FAIL train                  |
| B4 prior compression                                 |        20 |        35   |       -0.089 |    -0.438 |        23 |        43.5 |        0.132 |     0.1   |       16 |       43.8 |       0.036 |   -0.257 | FAIL train                  |
| B5 room ≥3 ATR to older level                        |        40 |        60   |        0.568 |     0.219 |        18 |        44.4 |        0.173 |     0.137 |       24 |       54.2 |       0.242 |   -0.051 | pass train+valid, FAIL test |
| C1 volume ≥2×                                        |         2 |       100   |        1.928 |     1.577 |         2 |         0   |       -1.087 |    -1.115 |        7 |       28.6 |      -0.465 |   -0.765 | FAIL train                  |
| C2 RSI not exhausted                                 |        43 |        46.5 |        0.149 |    -0.198 |        34 |        38.2 |        0.005 |    -0.028 |       30 |       53.3 |       0.283 |   -0.009 | FAIL train                  |
| X1 stop 2 ATR · target 1R                            |        39 |        66.7 |        0.265 |    -0.091 |        31 |        51.6 |       -0.057 |    -0.101 |       29 |       62.1 |       0.207 |   -0.096 | FAIL train                  |
| X2 stop 2 ATR · target 0.75R                         |        40 |        65   |        0.117 |    -0.239 |        31 |        58.1 |       -0.057 |    -0.101 |       30 |       70   |       0.192 |   -0.111 | FAIL train                  |
| X3 stop 2 ATR · target 0.5R                          |        43 |        74.4 |        0.079 |    -0.278 |        33 |        60.6 |       -0.13  |    -0.175 |       30 |       73.3 |       0.116 |   -0.186 | FAIL train                  |
| X4 stop 3 ATR · target 0.5R                          |        27 |        59.3 |       -0.106 |    -0.471 |        16 |        68.8 |       -0.009 |    -0.065 |       14 |       64.3 |      -0.024 |   -0.336 | FAIL train                  |
| X5 stop 1.5 ATR · target 2R                          |        49 |        53.1 |        0.348 |     0     |        35 |        40   |        0.034 |     0     |       32 |       53.1 |       0.293 |    0     | FAIL train                  |
| X6 stop 2.5 ATR · target 3R                          |        31 |        58.1 |        0.105 |    -0.256 |        20 |        50   |        0.198 |     0.147 |       22 |       54.5 |       0.402 |    0.093 | FAIL train                  |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |        20 |        60   |        0.275 |    -0.089 |        12 |        66.7 |        0.208 |     0.162 |       12 |       50   |      -0.023 |   -0.334 | FAIL train                  |


## angel · S3 · SELL

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train |  15 |        17 |  60   |    1.08 |   -0.83 |  0.319 |  0.244 | [-0.32,+0.99] | 1.97 |  3.4 |            3 |  26.7 |   26.7 |     0 | n<30   |
| 2-valid |   5 |         6 |  40   |    0.56 |   -1.04 | -0.401 | -0.438 | n/a           | 0.36 |  3.1 |            3 |   0   |   60   |     0 | n<30   |
| 3-test  |   4 |         7 |  50   |    0.66 |   -1.04 | -0.188 | -0.223 | n/a           | 0.64 |  2.1 |            2 |   0   |   50   |     0 | n<30   |
| ALL     |  24 |        30 |  54.2 |    0.94 |   -0.92 |  0.085 |  0.024 | [-0.38,+0.59] | 1.2  |  5.2 |            3 |  16.7 |   37.5 |     0 | n<30   |

by year: 2022: n1 +0.44R w100%; 2023: n11 +0.31R w55%; 2024: n3 +0.32R w67%; 2025: n7 -0.10R w57%; 2026: n2 -1.04R w0%

by instrument: ALUMINIUM: n3 +0.10R; BANKNIFTY: n1 -1.04R; COPPER: n1 -0.19R; CRUDEOIL: n5 +0.02R; GOLD: n1 +0.10R; NIFTY: n5 -0.50R; ZINC: n8 +0.66R

by regime: range/hi-vol: n3 -0.21R w67%; range/lo-vol: n13 +0.03R w46%; trend/hi-vol: n2 -0.37R w50%; trend/lo-vol: n6 +0.51R w67%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict    |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:-----------|
| A1 trend ADX≥25                                      |         4 |       100   |        1.234 |     0.968 |         3 |        33.3 |       -0.634 |    -0.192 |        1 |        0   |      -1.093 |   -0.859 | FAIL train |
| A2 high volatility                                   |         2 |       100   |        0.135 |    -0.122 |         1 |       100   |        0.265 |     0.707 |        2 |        0   |      -1.081 |   -0.852 | FAIL train |
| A3 low volatility                                    |        12 |        50   |        0.25  |     0.01  |         4 |        25   |       -0.613 |    -0.177 |        2 |      100   |       0.636 |    0.852 | FAIL train |
| A4 vol expanding ATR14>ATR50                         |         2 |       100   |        0.135 |    -0.122 |         0 |       nan   |      nan     |   nan     |        1 |        0   |      -1.083 |   -0.853 | FAIL train |
| A5 not stretched ≤3 ATR from EMA200                  |         5 |        40   |       -0.166 |    -0.397 |         2 |        50   |       -0.142 |     0.288 |        0 |      nan   |     nan     |  nan     | FAIL train |
| A6 momentum ROC20 aligned                            |        15 |        60   |        0.244 |     0     |         5 |        40   |       -0.438 |     0     |        4 |       50   |      -0.223 |    0     | FAIL train |
| B1 extension ≤1 ATR                                  |        13 |        61.5 |        0.357 |     0.12  |         5 |        40   |       -0.438 |     0     |        3 |       33.3 |      -0.714 |   -0.489 | FAIL train |
| B2 close near extreme (CLV)                          |        11 |        72.7 |        0.515 |     0.261 |         3 |        66.7 |       -0.013 |     0.424 |        3 |       33.3 |      -0.302 |   -0.079 | FAIL train |
| B3 strong body ≥50%                                  |        10 |        70   |        0.451 |     0.203 |         3 |        33.3 |       -0.458 |    -0.023 |        3 |       66.7 |       0.061 |    0.283 | FAIL train |
| B4 prior compression                                 |         7 |        71.4 |        0.555 |     0.297 |         4 |        50   |       -0.275 |     0.161 |        1 |        0   |      -1.068 |   -0.846 | FAIL train |
| B5 room ≥3 ATR to older level                        |         8 |        50   |        0.004 |    -0.236 |         2 |        50   |       -0.412 |     0.032 |        3 |       33.3 |      -0.304 |   -0.08  | FAIL train |
| C1 volume ≥2×                                        |         1 |         0   |       -1.052 |    -1.345 |         0 |       nan   |      nan     |   nan     |        2 |       50   |       0.079 |    0.304 | FAIL train |
| C2 RSI not exhausted                                 |        14 |        57.1 |        0.257 |     0.016 |         4 |        50   |       -0.275 |     0.161 |        4 |       50   |      -0.22  |    0.001 | FAIL train |
| X1 stop 2 ATR · target 1R                            |        12 |        66.7 |        0.137 |    -0.12  |         3 |        33.3 |       -0.642 |    -0.21  |        2 |        0   |      -1.161 |   -0.943 | FAIL train |
| X2 stop 2 ATR · target 0.75R                         |        12 |        66.7 |        0.074 |    -0.182 |         3 |        33.3 |       -0.642 |    -0.21  |        3 |       33.3 |      -0.545 |   -0.327 | FAIL train |
| X3 stop 2 ATR · target 0.5R                          |        12 |        75   |        0.029 |    -0.227 |         3 |        33.3 |       -0.642 |    -0.21  |        3 |       33.3 |      -0.628 |   -0.41  | FAIL train |
| X4 stop 3 ATR · target 0.5R                          |         7 |        71.4 |        0.055 |    -0.22  |         3 |        33.3 |       -0.651 |    -0.229 |        3 |       33.3 |      -0.541 |   -0.332 | FAIL train |
| X5 stop 1.5 ATR · target 2R                          |        15 |        60   |        0.244 |     0     |         5 |        40   |       -0.438 |     0     |        4 |       50   |      -0.223 |    0     | FAIL train |
| X6 stop 2.5 ATR · target 3R                          |         8 |        50   |       -0.1   |    -0.366 |         3 |        33.3 |       -0.647 |    -0.221 |        2 |        0   |      -0.655 |   -0.443 | FAIL train |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |         4 |        50   |        0.072 |    -0.19  |         2 |         0   |       -1.06  |    -0.629 |        2 |       50   |       0.735 |    0.953 | FAIL train |


## nseidx · S2 · BUY

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train |  21 |         5 |  61.9 |    1.6  |   -0.65 |  0.746 |  0.697 | [+0.07,+1.41] | 4.02 |  3   |            5 |   9.5 |   14.3 |   4.8 | n<30   |
| 2-valid |   5 |         2 |  40   |    2.82 |   -0.97 |  0.548 |  0.515 | n/a           | 1.94 |  1.5 |            2 |  20   |   40   |  20   | n<30   |
| 3-test  |  11 |         3 |  36.4 |    1.88 |   -0.82 |  0.161 |  0.118 | [-0.88,+1.11] | 1.31 |  3.1 |            3 |   9.1 |   45.5 |   0   | n<30   |
| ALL     |  37 |        10 |  51.4 |    1.79 |   -0.77 |  0.545 |  0.5   | [-0.01,+1.08] | 2.46 |  3.1 |            5 |  10.8 |   27   |   5.4 | n<100  |

by year: 2012: n5 -0.61R w0%; 2014: n5 +1.63R w80%; 2015: n1 +2.39R w100%; 2016: n1 -1.03R w0%; 2017: n6 +1.03R w100%; 2018: n3 +1.02R w67%; 2019: n3 +0.38R w33%; 2021: n2 +0.79R w50%; 2022: n1 -1.03R w0%; 2023: n2 +2.46R w100%; 2024: n6 -0.26R w33%; 2025: n2 -0.28R w0%

by instrument: BANKNIFTY: n20 +0.73R; NIFTY: n17 +0.33R

by regime: range/hi-vol: n10 +0.22R w50%; range/lo-vol: n9 +0.41R w44%; trend/hi-vol: n3 +0.48R w33%; trend/lo-vol: n15 +0.86R w60%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict    |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:-----------|
| A1 trend ADX≥25                                      |        14 |        57.1 |        0.699 |     0.004 |         4 |        50   |        0.71  |     0.193 |        2 |       50   |       0.915 |    0.796 | FAIL train |
| A2 high volatility                                   |         7 |        57.1 |        0.408 |    -0.301 |         2 |         0   |       -0.789 |    -1.306 |        6 |       33.3 |       0.209 |    0.088 | FAIL train |
| A3 low volatility                                    |        16 |        56.2 |        0.698 |     0.004 |         3 |        66.7 |        1.385 |     0.871 |        6 |       33.3 |      -0.204 |   -0.316 | FAIL train |
| A4 vol expanding ATR14>ATR50                         |        10 |        70   |        0.938 |     0.234 |         4 |        50   |        1     |     0.484 |        5 |       40   |       0.466 |    0.346 | FAIL train |
| A5 not stretched ≤3 ATR from EMA200                  |         4 |        75   |        0.841 |     0.14  |         1 |         0   |       -0.5   |    -1.026 |        0 |      nan   |     nan     |  nan     | FAIL train |
| A6 momentum ROC20 aligned                            |        21 |        61.9 |        0.697 |     0     |         5 |        40   |        0.515 |     0     |       11 |       36.4 |       0.118 |    0     | FAIL train |
| B1 extension ≤1 ATR                                  |        14 |        57.1 |        0.571 |    -0.125 |         4 |        50   |        0.479 |    -0.034 |       10 |       30   |      -0.22  |   -0.339 | FAIL train |
| B2 close near extreme (CLV)                          |        17 |        52.9 |        0.391 |    -0.306 |         5 |        40   |        0.515 |     0     |        8 |       37.5 |       0.146 |    0.027 | FAIL train |
| B3 strong body ≥50%                                  |        14 |        64.3 |        0.707 |     0.008 |         4 |        50   |        0.769 |     0.256 |       10 |       40   |       0.236 |    0.119 | FAIL train |
| B4 prior compression                                 |         5 |       100   |        1.113 |     0.413 |         2 |        50   |        0.767 |     0.247 |        3 |       33.3 |      -0.374 |   -0.496 | FAIL train |
| B5 room ≥3 ATR to older level                        |        15 |        53.3 |        0.535 |    -0.16  |         4 |        50   |        0.769 |     0.256 |       10 |       30   |      -0.02  |   -0.138 | FAIL train |
| C1 volume ≥2×                                        |         7 |        57.1 |        0.71  |     0.007 |         1 |       100   |        2.958 |     2.431 |        1 |      100   |       1.009 |    0.898 | FAIL train |
| C2 RSI not exhausted                                 |        10 |        80   |        0.93  |     0.234 |         4 |        25   |       -0.011 |    -0.53  |        8 |       25   |      -0.305 |   -0.424 | FAIL train |
| X1 stop 2 ATR · target 1R                            |        18 |        66.7 |        0.261 |    -0.447 |         3 |        66.7 |       -0.004 |    -0.522 |       11 |       36.4 |      -0.204 |   -0.332 | FAIL train |
| X2 stop 2 ATR · target 0.75R                         |        19 |        68.4 |        0.178 |    -0.53  |         3 |        66.7 |       -0.087 |    -0.605 |       11 |       36.4 |      -0.279 |   -0.408 | FAIL train |
| X3 stop 2 ATR · target 0.5R                          |        19 |        68.4 |        0.058 |    -0.651 |         3 |        66.7 |       -0.066 |    -0.584 |       12 |       41.7 |      -0.305 |   -0.433 | FAIL train |
| X4 stop 3 ATR · target 0.5R                          |         8 |        62.5 |        0.054 |    -0.661 |         1 |       100   |        0.453 |    -0.072 |        8 |       50   |      -0.153 |   -0.291 | FAIL train |
| X5 stop 1.5 ATR · target 2R                          |        21 |        61.9 |        0.571 |    -0.126 |         5 |        40   |        0.172 |    -0.343 |       11 |       36.4 |       0.025 |   -0.093 | FAIL train |
| X6 stop 2.5 ATR · target 3R                          |        13 |        69.2 |        0.351 |    -0.362 |         3 |        66.7 |        0.421 |    -0.103 |       11 |       36.4 |      -0.092 |   -0.228 | FAIL train |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |         4 |        75   |        0.225 |    -0.491 |         0 |       nan   |      nan     |   nan     |        2 |        0   |      -0.574 |   -0.713 | FAIL train |


## nseidx · S2 · SELL

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |     pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-------:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train |  10 |         5 |  50   |    1.09 |   -0.77 |  0.159 |  0.123 | [-0.46,+0.74] |   1.41 |  3.2 |            3 |   0   |   30   |    10 | n<30   |
| 2-valid |   1 |         8 | 100   |    2.98 |    0    |  2.976 |  2.952 | n/a           | nan    |  0   |            0 | 100   |    0   |     0 | n<30   |
| 3-test  |   9 |         4 |  33.3 |    1.56 |   -0.72 |  0.037 |  0.001 | [-0.72,+0.60] |   1.08 |  2   |            2 |  11.1 |   44.4 |     0 | n<30   |
| ALL     |  20 |        17 |  45   |    1.45 |   -0.74 |  0.245 |  0.21  | [-0.24,+0.74] |   1.6  |  3.2 |            3 |  10   |   35   |     5 | n<30   |

by year: 2011: n1 -0.43R w0%; 2013: n3 +0.42R w67%; 2014: n1 +1.16R w100%; 2015: n2 -1.07R w0%; 2016: n1 -1.04R w0%; 2018: n2 +1.40R w100%; 2020: n1 +2.98R w100%; 2022: n2 -1.02R w0%; 2023: n1 +0.35R w100%; 2025: n1 -0.21R w0%; 2026: n5 +0.45R w40%

by instrument: BANKNIFTY: n8 -0.02R; NIFTY: n12 +0.42R

by regime: range/hi-vol: n7 +0.59R w57%; range/lo-vol: n2 -0.38R w50%; trend/hi-vol: n10 +0.02R w30%; trend/lo-vol: n1 +1.36R w100%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict    |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:-----------|
| A1 trend ADX≥25                                      |         6 |        33.3 |        0.028 |    -0.095 |         1 |         100 |        2.952 |         0 |        6 |       16.7 |      -0.531 |   -0.532 | FAIL train |
| A2 high volatility                                   |         9 |        55.6 |        0.265 |     0.141 |         1 |         100 |        2.952 |         0 |        7 |       14.3 |      -0.23  |   -0.234 | FAIL train |
| A3 low volatility                                    |         1 |         0   |       -1.148 |    -1.266 |         0 |         nan |      nan     |       nan |        2 |      100   |       0.808 |    0.818 | FAIL train |
| A4 vol expanding ATR14>ATR50                         |         7 |        57.1 |        0.333 |     0.209 |         1 |         100 |        2.952 |         0 |        4 |       50   |       0.288 |    0.281 | FAIL train |
| A5 not stretched ≤3 ATR from EMA200                  |         7 |        71.4 |        0.56  |     0.436 |         0 |         nan |      nan     |       nan |        4 |       50   |       0.489 |    0.485 | FAIL train |
| A6 momentum ROC20 aligned                            |        10 |        50   |        0.123 |     0     |         1 |         100 |        2.952 |         0 |        9 |       33.3 |       0.001 |    0     | FAIL train |
| B1 extension ≤1 ATR                                  |         9 |        33.3 |       -0.286 |    -0.41  |         0 |         nan |      nan     |       nan |        6 |       50   |       0.361 |    0.363 | FAIL train |
| B2 close near extreme (CLV)                          |         7 |        42.9 |       -0.054 |    -0.176 |         0 |         nan |      nan     |       nan |        7 |       28.6 |      -0.264 |   -0.265 | FAIL train |
| B3 strong body ≥50%                                  |         6 |        66.7 |        0.321 |     0.198 |         0 |         nan |      nan     |       nan |        7 |       42.9 |       0.307 |    0.307 | FAIL train |
| B4 prior compression                                 |         1 |       100   |        0.956 |     0.83  |         0 |         nan |      nan     |       nan |        3 |       33.3 |       0.544 |    0.54  | FAIL train |
| B5 room ≥3 ATR to older level                        |         6 |        33.3 |       -0.089 |    -0.214 |         1 |         100 |        2.952 |         0 |        8 |       25   |      -0.038 |   -0.039 | FAIL train |
| C1 volume ≥2×                                        |         2 |       100   |        0.775 |     0.652 |         1 |         100 |        2.952 |         0 |        0 |      nan   |     nan     |  nan     | FAIL train |
| C2 RSI not exhausted                                 |         8 |        50   |        0.151 |     0.028 |         0 |         nan |      nan     |       nan |        7 |       42.9 |       0.307 |    0.307 | FAIL train |
| X1 stop 2 ATR · target 1R                            |         5 |        60   |        0.144 |     0.013 |         0 |         nan |      nan     |       nan |        9 |       55.6 |       0.182 |    0.173 | FAIL train |
| X2 stop 2 ATR · target 0.75R                         |         5 |        60   |       -0.006 |    -0.137 |         0 |         nan |      nan     |       nan |        9 |       66.7 |       0.317 |    0.307 | FAIL train |
| X3 stop 2 ATR · target 0.5R                          |         5 |        60   |       -0.156 |    -0.287 |         0 |         nan |      nan     |       nan |        9 |       77.8 |       0.22  |    0.21  | FAIL train |
| X4 stop 3 ATR · target 0.5R                          |         0 |       nan   |      nan     |   nan     |         0 |         nan |      nan     |       nan |        6 |       66.7 |       0.279 |    0.263 | FAIL train |
| X5 stop 1.5 ATR · target 2R                          |        10 |        50   |        0.27  |     0.147 |         1 |         100 |        1.952 |        -1 |       10 |       30   |      -0.205 |   -0.207 | FAIL train |
| X6 stop 2.5 ATR · target 3R                          |         1 |       100   |        0.983 |     0.845 |         0 |         nan |      nan     |       nan |        6 |       50   |       0.511 |    0.499 | FAIL train |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |         0 |       nan   |      nan     |   nan     |         0 |         nan |      nan     |       nan |        2 |       50   |       0.253 |    0.239 | FAIL train |


## nseidx · S3 · BUY

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train |  88 |        10 |  39.8 |    1.25 |   -0.96 | -0.078 | -0.129 | [-0.40,+0.28] | 0.86 | 23   |            7 |  15.9 |   47.7 |   5.7 | n<100  |
| 2-valid |  33 |         2 |  54.5 |    1.15 |   -0.9  |  0.22  |  0.182 | [-0.14,+0.56] | 1.54 |  3.5 |            3 |  21.2 |   33.3 |   3   | n<100  |
| 3-test  |  44 |         5 |  45.5 |    1.26 |   -0.89 |  0.088 |  0.044 | [-0.33,+0.53] | 1.18 |  7.4 |            6 |  18.2 |   40.9 |   9.1 | n<100  |
| ALL     | 165 |        17 |  44.2 |    1.23 |   -0.93 |  0.026 | -0.021 | [-0.20,+0.25] | 1.05 | 23   |            7 |  17.6 |   43   |   6.1 |        |

by year: 2011: n7 -1.30R w0%; 2012: n12 -0.14R w33%; 2013: n9 -0.31R w33%; 2014: n19 -0.09R w42%; 2015: n5 -0.00R w40%; 2016: n9 -0.86R w11%; 2017: n18 +0.40R w56%; 2018: n9 +1.00R w78%; 2019: n13 -0.05R w46%; 2020: n7 +0.43R w57%; 2021: n13 +0.38R w62%; 2022: n10 +0.03R w40%; 2023: n9 +0.33R w56%; 2024: n13 -0.13R w31%; 2025: n10 +0.32R w60%; 2026: n2 -0.42R w50%

by instrument: BANKNIFTY: n78 +0.20R; NIFTY: n87 -0.13R

by regime: range/hi-vol: n36 +0.06R w44%; range/lo-vol: n64 +0.04R w48%; trend/hi-vol: n9 -0.37R w33%; trend/lo-vol: n56 +0.05R w41%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict                |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:-----------------------|
| A1 trend ADX≥25                                      |        45 |        37.8 |       -0.124 |     0.007 |        17 |        47.1 |        0.057 |    -0.126 |        9 |       33.3 |      -0.114 |   -0.155 | FAIL train             |
| A2 high volatility                                   |        17 |        47.1 |        0.144 |     0.265 |        11 |        54.5 |        0.008 |    -0.175 |       17 |       29.4 |      -0.322 |   -0.375 | FAIL train             |
| A3 low volatility                                    |        69 |        39.1 |       -0.169 |    -0.037 |        25 |        48   |        0.131 |    -0.049 |       27 |       55.6 |       0.274 |    0.236 | FAIL train             |
| A4 vol expanding ATR14>ATR50                         |        32 |        37.5 |       -0.243 |    -0.121 |        11 |        54.5 |        0.014 |    -0.172 |       16 |       37.5 |      -0.249 |   -0.3   | FAIL train             |
| A5 not stretched ≤3 ATR from EMA200                  |         7 |        42.9 |        0.139 |     0.261 |         2 |        50   |        0.104 |    -0.08  |        5 |       60   |       0.463 |    0.407 | FAIL train             |
| A6 momentum ROC20 aligned                            |        88 |        39.8 |       -0.129 |     0     |        33 |        54.5 |        0.182 |     0     |       44 |       45.5 |       0.044 |    0     | FAIL train             |
| B1 extension ≤1 ATR                                  |        82 |        37.8 |       -0.179 |    -0.05  |        33 |        54.5 |        0.182 |     0     |       44 |       45.5 |       0.044 |    0     | FAIL train             |
| B2 close near extreme (CLV)                          |        73 |        39.7 |       -0.076 |     0.053 |        30 |        53.3 |        0.143 |    -0.038 |       36 |       50   |       0.154 |    0.109 | FAIL train             |
| B3 strong body ≥50%                                  |        68 |        39.7 |       -0.201 |    -0.071 |        26 |        46.2 |        0.039 |    -0.141 |       29 |       41.4 |      -0.045 |   -0.089 | FAIL train             |
| B4 prior compression                                 |        44 |        34.1 |       -0.269 |    -0.139 |        21 |        47.6 |        0.087 |    -0.093 |       18 |       33.3 |      -0.279 |   -0.324 | FAIL train             |
| B5 room ≥3 ATR to older level                        |        72 |        34.7 |       -0.287 |    -0.157 |        25 |        52   |        0.124 |    -0.057 |       30 |       40   |      -0.111 |   -0.153 | FAIL train             |
| C1 volume ≥2×                                        |         2 |       100   |        1.465 |     1.594 |         1 |       100   |        1.958 |     1.759 |        0 |      nan   |     nan     |  nan     | FAIL train             |
| C2 RSI not exhausted                                 |        79 |        40.5 |       -0.112 |     0.016 |        32 |        50   |        0.113 |    -0.069 |       42 |       42.9 |      -0.054 |   -0.099 | FAIL train             |
| X1 stop 2 ATR · target 1R                            |        76 |        47.4 |       -0.16  |    -0.042 |        29 |        55.2 |       -0.054 |    -0.244 |       40 |       55   |       0.033 |   -0.021 | FAIL train             |
| X2 stop 2 ATR · target 0.75R                         |        76 |        51.3 |       -0.149 |    -0.031 |        30 |        66.7 |        0.048 |    -0.142 |       40 |       60   |       0.005 |   -0.049 | FAIL train             |
| X3 stop 2 ATR · target 0.5R                          |        80 |        60   |       -0.141 |    -0.024 |        33 |        69.7 |       -0     |    -0.19  |       42 |       64.3 |      -0.073 |   -0.127 | FAIL train             |
| X4 stop 3 ATR · target 0.5R                          |        39 |        66.7 |        0.016 |     0.125 |        14 |        50   |       -0.081 |    -0.277 |       31 |       54.8 |      -0.147 |   -0.21  | pass train, FAIL valid |
| X5 stop 1.5 ATR · target 2R                          |        88 |        39.8 |       -0.129 |     0     |        33 |        54.5 |        0.182 |     0     |       44 |       45.5 |       0.044 |    0     | FAIL train             |
| X6 stop 2.5 ATR · target 3R                          |        54 |        44.4 |       -0.105 |     0.008 |        24 |        54.2 |        0.171 |    -0.024 |       38 |       47.4 |      -0.15  |   -0.211 | FAIL train             |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |        33 |        54.5 |       -0.108 |     0.006 |        11 |        45.5 |        0.098 |    -0.094 |       20 |       55   |       0.016 |   -0.047 | FAIL train             |


## nseidx · S3 · SELL

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |     pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-------:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train |  21 |         8 |  42.9 |    1.3  |   -0.92 |  0.031 | -0.007 | [-0.61,+0.69] |   1.06 |  6.9 |            4 |  23.8 |   47.6 |   9.5 | n<30   |
| 2-valid |   2 |         2 | 100   |    1.08 |    0    |  1.079 |  1.046 | n/a           | nan    |  0   |            0 |  50   |    0   |   0   | n<30   |
| 3-test  |   9 |         0 |  33.3 |    0.15 |   -1.08 | -0.666 | -0.702 | [-0.96,-0.17] |   0.07 |  6   |            4 |   0   |   66.7 |  11.1 | n<30   |
| ALL     |  32 |        10 |  43.8 |    1.02 |   -0.97 | -0.099 | -0.136 | [-0.56,+0.44] |   0.82 |  7.1 |            4 |  18.8 |   50   |   9.4 | n<100  |

by year: 2011: n4 +0.84R w50%; 2013: n2 -0.03R w50%; 2015: n8 -0.78R w25%; 2016: n6 +0.77R w67%; 2018: n1 -1.03R w0%; 2019: n1 +0.19R w100%; 2020: n1 +1.97R w100%; 2022: n3 -0.74R w33%; 2023: n1 +0.35R w100%; 2025: n3 -0.68R w33%; 2026: n2 -1.04R w0%

by instrument: BANKNIFTY: n13 +0.10R; NIFTY: n19 -0.24R

by regime: range/hi-vol: n8 -0.35R w38%; range/lo-vol: n8 +0.75R w75%; trend/hi-vol: n12 -0.28R w33%; trend/lo-vol: n4 -0.77R w25%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict                |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:-----------------------|
| A1 trend ADX≥25                                      |        11 |        27.3 |       -0.51  |    -0.506 |         2 |         100 |        1.046 |     0     |        4 |       25   |      -0.813 |   -0.104 | FAIL train             |
| A2 high volatility                                   |        13 |        30.8 |       -0.338 |    -0.336 |         2 |         100 |        1.046 |     0     |        5 |       20   |      -0.894 |   -0.196 | FAIL train             |
| A3 low volatility                                    |         8 |        62.5 |        0.531 |     0.546 |         0 |         nan |      nan     |   nan     |        4 |       50   |      -0.461 |    0.245 | FAIL train             |
| A4 vol expanding ATR14>ATR50                         |        12 |        25   |       -0.366 |    -0.365 |         2 |         100 |        1.046 |     0     |        2 |       50   |      -0.385 |    0.321 | FAIL train             |
| A5 not stretched ≤3 ATR from EMA200                  |         7 |        42.9 |       -0.477 |    -0.473 |         2 |         100 |        1.046 |     0     |        1 |      100   |       0.313 |    1.018 | FAIL train             |
| A6 momentum ROC20 aligned                            |        21 |        42.9 |       -0.007 |     0     |         2 |         100 |        1.046 |     0     |        9 |       33.3 |      -0.702 |    0     | FAIL train             |
| B1 extension ≤1 ATR                                  |        20 |        45   |        0.046 |     0.053 |         2 |         100 |        1.046 |     0     |        9 |       33.3 |      -0.702 |    0     | pass train, FAIL valid |
| B2 close near extreme (CLV)                          |        14 |        28.6 |       -0.525 |    -0.519 |         2 |         100 |        1.046 |     0     |        7 |       42.9 |      -0.592 |    0.108 | FAIL train             |
| B3 strong body ≥50%                                  |        15 |        40   |       -0.279 |    -0.272 |         1 |         100 |        0.151 |    -0.892 |        5 |       20   |      -0.84  |   -0.139 | FAIL train             |
| B4 prior compression                                 |         7 |        71.4 |        0.64  |     0.651 |         1 |         100 |        0.217 |    -0.824 |        3 |       33.3 |      -0.707 |   -0.007 | FAIL train             |
| B5 room ≥3 ATR to older level                        |        14 |        42.9 |       -0.037 |    -0.031 |         1 |         100 |        1.941 |     0.892 |        4 |       25   |      -0.811 |   -0.103 | FAIL train             |
| C2 RSI not exhausted                                 |        21 |        42.9 |       -0.007 |     0     |         2 |         100 |        1.046 |     0     |        8 |       37.5 |      -0.653 |    0.048 | FAIL train             |
| X1 stop 2 ATR · target 1R                            |        11 |        63.6 |       -0.034 |    -0.032 |         2 |         100 |        0.951 |    -0.104 |        7 |       42.9 |      -0.464 |    0.231 | FAIL train             |
| X2 stop 2 ATR · target 0.75R                         |        11 |        63.6 |       -0.062 |    -0.06  |         2 |         100 |        0.701 |    -0.354 |        8 |       50   |      -0.294 |    0.401 | FAIL train             |
| X3 stop 2 ATR · target 0.5R                          |        13 |        69.2 |       -0.026 |    -0.025 |         2 |         100 |        0.451 |    -0.604 |        8 |       50   |      -0.388 |    0.308 | FAIL train             |
| X4 stop 3 ATR · target 0.5R                          |         3 |        33.3 |       -0.438 |    -0.444 |         0 |         nan |      nan     |   nan     |        7 |       42.9 |      -0.465 |    0.222 | FAIL train             |
| X5 stop 1.5 ATR · target 2R                          |        21 |        42.9 |       -0.007 |     0     |         2 |         100 |        1.046 |     0     |        9 |       33.3 |      -0.702 |    0     | FAIL train             |
| X6 stop 2.5 ATR · target 3R                          |         6 |        66.7 |        0.412 |     0.409 |         1 |         100 |        0.09  |    -0.967 |        6 |       33.3 |      -0.59  |    0.101 | FAIL train             |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |         3 |        66.7 |       -0.059 |    -0.061 |         1 |         100 |        0.098 |    -0.957 |        2 |        0   |      -0.836 |   -0.148 | FAIL train             |


## proxy · S2 · BUY

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train |  61 |        67 |  23   |    2.96 |   -1.07 | -0.145 | -0.182 | [-0.62,+0.39] | 0.82 | 20.2 |           11 |  23   |   75.4 |   9.8 | n<100  |
| 2-valid |  16 |        23 |  37.5 |    2.95 |   -1.03 |  0.462 |  0.425 | [-0.37,+1.36] | 1.72 |  3.1 |            3 |  37.5 |   62.5 |   0   | n<30   |
| 3-test  |  24 |        59 |  33.3 |    2.98 |   -1.07 |  0.277 |  0.246 | [-0.45,+1.10] | 1.39 |  6.4 |            5 |  33.3 |   66.7 |   8.3 | n<30   |
| ALL     | 101 |       149 |  27.7 |    2.97 |   -1.07 |  0.052 |  0.016 | [-0.31,+0.46] | 1.07 | 23.4 |           11 |  27.7 |   71.3 |   7.9 |        |

by year: 2005: n2 +2.96R w100%; 2006: n8 -0.03R w25%; 2007: n4 -0.06R w25%; 2008: n5 +0.57R w40%; 2009: n3 -1.02R w0%; 2010: n5 +1.23R w60%; 2011: n4 -1.03R w0%; 2012: n6 -1.07R w0%; 2013: n4 -0.05R w25%; 2014: n2 -1.06R w0%; 2016: n4 -0.27R w25%; 2017: n11 -0.35R w18%; 2018: n3 -0.85R w0%; 2019: n5 -0.24R w20%; 2020: n4 +1.97R w75%; 2021: n7 +0.10R w29%; 2022: n3 +0.22R w33%; 2023: n7 +0.12R w29%; 2024: n4 -0.05R w25%; 2025: n6 +0.97R w50%; 2026: n4 -0.12R w25%

by instrument: ALUMINIUM: n5 -0.60R; COPPER: n21 -0.13R; CRUDEOIL: n12 -0.31R; GOLD: n29 +0.36R; NATURALGAS: n4 -0.07R; SILVER: n30 +0.16R

by regime: range/hi-vol: n13 +0.21R w31%; range/lo-vol: n53 -0.10R w25%; trend/hi-vol: n7 +0.11R w29%; trend/lo-vol: n28 +0.25R w32%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict                |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:-----------------------|
| A1 trend ADX≥25                                      |        26 |        19.2 |       -0.298 |    -0.122 |         7 |        71.4 |        1.79  |     1.361 |       12 |       25   |      -0.057 |   -0.305 | FAIL train             |
| A2 high volatility                                   |         8 |        25   |        0.033 |     0.199 |         5 |        60   |        1.308 |     0.891 |        8 |       12.5 |      -0.629 |   -0.863 | FAIL train             |
| A3 low volatility                                    |        54 |        22.2 |       -0.23  |    -0.046 |        11 |        27.3 |        0.023 |    -0.405 |       17 |       41.2 |       0.583 |    0.33  | FAIL train             |
| A4 vol expanding ATR14>ATR50                         |        21 |        19   |       -0.293 |    -0.113 |         5 |        60   |        1.305 |     0.89  |       11 |       36.4 |       0.347 |    0.108 | FAIL train             |
| A5 not stretched ≤3 ATR from EMA200                  |        13 |         7.7 |       -0.878 |    -0.686 |         3 |         0   |       -1.051 |    -1.488 |        4 |        0   |      -1.047 |   -1.3   | FAIL train             |
| A6 momentum ROC20 aligned                            |        61 |        23   |       -0.182 |     0     |        16 |        37.5 |        0.425 |     0     |       24 |       33.3 |       0.246 |    0     | FAIL train             |
| B1 extension ≤1 ATR                                  |        48 |        16.7 |       -0.444 |    -0.263 |        13 |        38.5 |        0.475 |     0.044 |       20 |       30   |       0.127 |   -0.122 | FAIL train             |
| B2 close near extreme (CLV)                          |        40 |        12.5 |       -0.599 |    -0.417 |         9 |        44.4 |        0.721 |     0.287 |       20 |       35   |       0.306 |    0.061 | FAIL train             |
| B3 strong body ≥50%                                  |        43 |        11.6 |       -0.643 |    -0.458 |        10 |        40   |        0.544 |     0.11  |       19 |       31.6 |       0.166 |   -0.078 | FAIL train             |
| B4 prior compression                                 |        16 |         6.2 |       -0.828 |    -0.65  |         6 |        16.7 |       -0.415 |    -0.837 |        8 |       25   |      -0.045 |   -0.299 | FAIL train             |
| B5 room ≥3 ATR to older level                        |        52 |        21.2 |       -0.256 |    -0.075 |        14 |        42.9 |        0.637 |     0.213 |       15 |       26.7 |      -0.025 |   -0.268 | FAIL train             |
| C1 volume ≥2×                                        |        43 |        25.6 |       -0.081 |     0.101 |         8 |        37.5 |        0.42  |    -0.002 |       12 |       33.3 |       0.223 |   -0.013 | FAIL train             |
| C2 RSI not exhausted                                 |        50 |        24   |       -0.136 |     0.044 |        13 |        30.8 |        0.154 |    -0.27  |       21 |       38.1 |       0.441 |    0.191 | FAIL train             |
| X1 stop 2 ATR · target 1R                            |        48 |        56.2 |        0.056 |     0.229 |        16 |        68.8 |        0.304 |    -0.131 |       22 |       63.6 |       0.219 |   -0.034 | pass train, FAIL valid |
| X2 stop 2 ATR · target 0.75R                         |        51 |        66.7 |        0.102 |     0.276 |        16 |        75   |        0.241 |    -0.194 |       22 |       68.2 |       0.139 |   -0.114 | pass train, FAIL valid |
| X3 stop 2 ATR · target 0.5R                          |        53 |        66   |       -0.074 |     0.1   |        16 |        75   |        0.054 |    -0.381 |       23 |       69.6 |      -0.009 |   -0.263 | FAIL train             |
| X4 stop 3 ATR · target 0.5R                          |        31 |        77.4 |        0.103 |     0.269 |         9 |        88.9 |        0.287 |    -0.152 |        8 |       87.5 |       0.268 |    0.014 | pass train, FAIL valid |
| X5 stop 1.5 ATR · target 2R                          |        61 |        36.1 |       -0.028 |     0.154 |        16 |        50   |        0.425 |    -0     |       26 |       38.5 |       0.071 |   -0.176 | FAIL train             |
| X6 stop 2.5 ATR · target 3R                          |        36 |        33.3 |        0.281 |     0.45  |        14 |        35.7 |        0.213 |    -0.226 |       15 |       46.7 |       0.474 |    0.219 | pass train, FAIL valid |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |         5 |        60   |        0.778 |     0.933 |         2 |         0   |       -0.815 |    -1.263 |        1 |      100   |       1.983 |    1.715 | FAIL train             |


## proxy · S2 · SELL

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train |  41 |        59 |  36.6 |    2.83 |   -1.2  |  0.275 |  0.227 | [-0.40,+1.00] | 1.36 | 11   |            8 |  34.1 |   61   |  14.6 | n<100  |
| 2-valid |   8 |        19 |   0   |    0    |   -1.23 | -1.234 | -1.273 | [-1.49,-1.03] | 0    |  9.9 |            8 |   0   |  100   |  37.5 | n<30   |
| 3-test  |  14 |        39 |  35.7 |    2.05 |   -1.32 | -0.114 | -0.168 | [-1.02,+0.77] | 0.86 | 10.3 |            8 |  21.4 |   64.3 |  35.7 | n<30   |
| ALL     |  63 |       117 |  31.7 |    2.63 |   -1.23 | -0.003 | -0.051 | [-0.47,+0.51] | 1    | 13.8 |           10 |  27   |   66.7 |  22.2 | n<100  |

by year: 2006: n2 +0.70R w50%; 2007: n1 -1.03R w0%; 2012: n5 -0.23R w20%; 2013: n4 +1.16R w50%; 2014: n7 -0.47R w14%; 2015: n9 +1.10R w56%; 2016: n6 -1.00R w17%; 2017: n2 +0.96R w50%; 2018: n5 +0.97R w60%; 2019: n1 -1.07R w0%; 2020: n2 -1.41R w0%; 2021: n5 -1.20R w0%; 2022: n7 +0.86R w57%; 2023: n4 -1.40R w0%; 2024: n1 -1.04R w0%; 2025: n1 -1.26R w0%; 2026: n1 +0.24R w100%

by instrument: ALUMINIUM: n13 -0.71R; COPPER: n14 +0.07R; CRUDEOIL: n6 +0.43R; GOLD: n14 -0.20R; NATURALGAS: n1 -1.07R; SILVER: n15 +0.62R

by regime: range/hi-vol: n12 +0.82R w50%; range/lo-vol: n29 +0.02R w34%; trend/hi-vol: n12 -0.35R w25%; trend/lo-vol: n10 -0.64R w10%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict                |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:-----------------------|
| A1 trend ADX≥25                                      |        14 |        28.6 |        0.039 |    -0.196 |         5 |         0   |       -1.233 |     0.052 |        5 |       20   |      -1.026 |   -0.856 | FAIL train             |
| A2 high volatility                                   |        13 |        38.5 |        0.317 |     0.102 |         4 |         0   |       -1.256 |     0.024 |        8 |       50   |       0.556 |    0.712 | FAIL train             |
| A3 low volatility                                    |        29 |        34.5 |        0.151 |    -0.082 |         4 |         0   |       -1.289 |    -0.024 |        6 |       16.7 |      -1.134 |   -0.95  | FAIL train             |
| A4 vol expanding ATR14>ATR50                         |         7 |        42.9 |        0.511 |     0.282 |         4 |         0   |       -1.256 |     0.024 |        1 |        0   |      -1.354 |   -1.145 | FAIL train             |
| A5 not stretched ≤3 ATR from EMA200                  |        16 |        37.5 |        0.15  |    -0.08  |         4 |         0   |       -1.027 |     0.22  |        5 |       40   |       0.545 |    0.687 | FAIL train             |
| A6 momentum ROC20 aligned                            |        41 |        36.6 |        0.227 |     0     |         8 |         0   |       -1.273 |     0     |       14 |       35.7 |      -0.168 |    0     | FAIL train             |
| B1 extension ≤1 ATR                                  |        34 |        35.3 |        0.161 |    -0.065 |         6 |         0   |       -1.223 |     0.04  |       13 |       30.8 |      -0.289 |   -0.118 | FAIL train             |
| B2 close near extreme (CLV)                          |        27 |        37   |        0.304 |     0.06  |         7 |         0   |       -1.24  |     0.021 |        6 |       16.7 |      -0.556 |   -0.42  | pass train, FAIL valid |
| B3 strong body ≥50%                                  |        28 |        42.9 |        0.54  |     0.297 |         6 |         0   |       -1.181 |     0.089 |        7 |       14.3 |      -0.733 |   -0.583 | pass train, FAIL valid |
| B4 prior compression                                 |        14 |        42.9 |        0.498 |     0.261 |         2 |         0   |       -1.031 |     0.218 |        4 |       50   |       0.817 |    0.964 | FAIL train             |
| B5 room ≥3 ATR to older level                        |        26 |        30.8 |       -0.05  |    -0.276 |         7 |         0   |       -1.287 |    -0.015 |       11 |       27.3 |      -0.62  |   -0.444 | FAIL train             |
| C1 volume ≥2×                                        |        29 |        37.9 |        0.197 |    -0.025 |         3 |         0   |       -1.617 |    -0.321 |       10 |       40   |      -0.198 |   -0.024 | FAIL train             |
| C2 RSI not exhausted                                 |        41 |        36.6 |        0.227 |     0     |         6 |         0   |       -1.2   |     0.058 |       13 |       38.5 |      -0.077 |    0.088 | FAIL train             |
| X1 stop 2 ATR · target 1R                            |        36 |        50   |       -0.159 |    -0.396 |         6 |        66.7 |        0.277 |     1.539 |       14 |       71.4 |       0.238 |    0.392 | FAIL train             |
| X2 stop 2 ATR · target 0.75R                         |        36 |        66.7 |        0.078 |    -0.158 |         6 |        83.3 |        0.402 |     1.664 |       15 |       66.7 |      -0.036 |    0.121 | FAIL train             |
| X3 stop 2 ATR · target 0.5R                          |        37 |        64.9 |       -0.115 |    -0.351 |         6 |       100   |        0.443 |     1.705 |       15 |       80   |       0.062 |    0.219 | FAIL train             |
| X4 stop 3 ATR · target 0.5R                          |        22 |        77.3 |        0.095 |    -0.148 |         2 |       100   |        0.433 |     1.7   |        3 |       66.7 |      -0.259 |   -0.091 | FAIL train             |
| X5 stop 1.5 ATR · target 2R                          |        41 |        43.9 |        0.108 |    -0.118 |         8 |        25   |       -0.41  |     0.863 |       14 |       42.9 |      -0.142 |    0.026 | FAIL train             |
| X6 stop 2.5 ATR · target 3R                          |        31 |        41.9 |       -0.009 |    -0.253 |         4 |        25   |       -0.075 |     1.188 |        8 |       37.5 |      -0.191 |   -0.035 | FAIL train             |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |         5 |        40   |       -0.124 |    -0.386 |         0 |       nan   |      nan     |   nan     |        2 |       50   |       0.463 |    0.596 | FAIL train             |


## proxy · S3 · BUY

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train | 183 |       179 |  42.6 |    1.83 |   -1.26 |  0.058 | -0.172 | [-0.22,+0.33] | 1.08 | 31.7 |            8 |  40.4 |   53   |  10.9 |        |
| 2-valid |  40 |        63 |  37.5 |    1.95 |   -1.05 |  0.076 |  0.037 | [-0.41,+0.67] | 1.12 | 13.1 |            6 |  37.5 |   60   |  12.5 | n<100  |
| 3-test  |  71 |        68 |  49.3 |    1.77 |   -1.18 |  0.273 |  0.232 | [-0.10,+0.66] | 1.45 |  7   |            4 |  42.3 |   50.7 |  15.5 | n<100  |
| ALL     | 294 |       310 |  43.5 |    1.83 |   -1.21 |  0.112 | -0.046 | [-0.09,+0.31] | 1.16 | 32.7 |            7 |  40.5 |   53.4 |  12.2 |        |

by year: 2005: n15 +0.72R w60%; 2006: n18 +0.43R w50%; 2007: n16 +0.77R w62%; 2008: n9 +0.31R w44%; 2009: n17 +0.13R w41%; 2010: n26 +0.24R w50%; 2011: n12 -0.14R w33%; 2012: n13 -0.25R w31%; 2013: n5 +0.76R w60%; 2014: n6 -0.56R w17%; 2016: n6 +0.58R w50%; 2017: n25 -0.19R w32%; 2018: n15 -1.74R w20%; 2019: n11 +0.61R w55%; 2020: n17 +0.01R w35%; 2021: n12 -0.31R w25%; 2022: n11 +0.02R w45%; 2023: n13 +0.20R w46%; 2024: n13 +0.16R w46%; 2025: n24 +0.69R w62%; 2026: n10 -0.21R w30%

by instrument: ALUMINIUM: n28 -0.95R; COPPER: n71 -0.05R; CRUDEOIL: n38 +0.43R; GOLD: n90 +0.40R; NATURALGAS: n5 +0.11R; SILVER: n62 +0.16R

by regime: range/hi-vol: n57 +0.49R w56%; range/lo-vol: n135 +0.17R w44%; trend/hi-vol: n48 -0.07R w35%; trend/lo-vol: n54 -0.28R w37%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict                     |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:----------------------------|
| A1 trend ADX≥25                                      |        73 |        31.5 |       -0.932 |    -0.465 |        15 |        33.3 |       -0.049 |    -0.088 |       26 |       38.5 |      -0.015 |   -0.265 | FAIL train                  |
| A2 high volatility                                   |        56 |        48.2 |       -0.073 |     0.145 |        20 |        25   |       -0.347 |    -0.383 |       32 |       56.2 |       0.348 |    0.109 | FAIL train                  |
| A3 low volatility                                    |       129 |        40.3 |       -0.316 |    -0.111 |        21 |        47.6 |        0.32  |     0.28  |       42 |       42.9 |       0.12  |   -0.107 | FAIL train                  |
| A4 vol expanding ATR14>ATR50                         |        83 |        41   |       -0.048 |     0.014 |        22 |        27.3 |       -0.278 |    -0.314 |       44 |       47.7 |       0.16  |   -0.081 | FAIL train                  |
| A5 not stretched ≤3 ATR from EMA200                  |        21 |        52.4 |        0.388 |     0.367 |         2 |       100   |        1.926 |     1.887 |       12 |       41.7 |       0.177 |   -0.069 | pass train, FAIL valid      |
| A6 momentum ROC20 aligned                            |       182 |        42.9 |       -0.167 |     0.006 |        40 |        37.5 |        0.037 |     0     |       71 |       49.3 |       0.232 |    0     | FAIL train                  |
| B1 extension ≤1 ATR                                  |       161 |        42.2 |        0.11  |     0.085 |        31 |        38.7 |        0.097 |     0.053 |       59 |       47.5 |       0.185 |   -0.052 | pass train+valid, FAIL test |
| B2 close near extreme (CLV)                          |       136 |        43.4 |        0.142 |     0.114 |        28 |        35.7 |        0.023 |    -0.027 |       49 |       55.1 |       0.444 |    0.199 | pass train, FAIL valid      |
| B3 strong body ≥50%                                  |       133 |        45.9 |        0.221 |     0.193 |        24 |        37.5 |        0.078 |     0.028 |       46 |       58.7 |       0.523 |    0.277 | PASS all 3                  |
| B4 prior compression                                 |        78 |        43.6 |       -0.452 |    -0.096 |        19 |        47.4 |        0.37  |     0.337 |       38 |       50   |       0.273 |    0.032 | FAIL train                  |
| B5 room ≥3 ATR to older level                        |       147 |        42.2 |       -0.261 |    -0.04  |        36 |        33.3 |       -0.091 |    -0.127 |       49 |       57.1 |       0.462 |    0.228 | FAIL train                  |
| C1 volume ≥2×                                        |        13 |        46.2 |        0.255 |     0.237 |         1 |         0   |       -1.081 |    -1.116 |        2 |       50   |       0.463 |    0.209 | FAIL train                  |
| C2 RSI not exhausted                                 |       160 |        45   |        0.19  |     0.165 |        35 |        37.1 |        0.039 |    -0.001 |       68 |       48.5 |       0.209 |   -0.022 | pass train, FAIL valid      |
| X1 stop 2 ATR · target 1R                            |       130 |        46.9 |       -0.462 |    -0.286 |        27 |        59.3 |        0.113 |     0.068 |       55 |       61.8 |       0.142 |   -0.095 | FAIL train                  |
| X2 stop 2 ATR · target 0.75R                         |       130 |        54.6 |       -0.458 |    -0.282 |        28 |        64.3 |        0.059 |     0.013 |       57 |       64.9 |       0.048 |   -0.191 | FAIL train                  |
| X3 stop 2 ATR · target 0.5R                          |       135 |        63   |       -0.458 |    -0.29  |        30 |        70   |       -0.015 |    -0.061 |       60 |       76.7 |       0.066 |   -0.173 | FAIL train                  |
| X4 stop 3 ATR · target 0.5R                          |        63 |        60.3 |       -0.55  |    -0.302 |        13 |        76.9 |        0.078 |     0.03  |       16 |       68.8 |      -0.062 |   -0.3   | FAIL train                  |
| X5 stop 1.5 ATR · target 2R                          |       183 |        42.6 |       -0.172 |     0     |        40 |        37.5 |        0.037 |     0     |       71 |       49.3 |       0.232 |    0     | FAIL train                  |
| X6 stop 2.5 ATR · target 3R                          |        78 |        38.5 |       -0.184 |     0.059 |        17 |        58.8 |        0.83  |     0.779 |       27 |       55.6 |       0.556 |    0.318 | FAIL train                  |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |        43 |        34.9 |       -0.18  |    -0.103 |         9 |        66.7 |        0.677 |     0.624 |       11 |       81.8 |       0.934 |    0.702 | FAIL train                  |


## proxy · S3 · SELL

### Baseline (live rules)
| split   |   n |   invalid |   win |   avg_w |   avg_l |   exp1 |   exp2 | ci            |   pf |   dd |   max_losses |   tgt |   stop |   gap | warn   |
|:--------|----:|----------:|------:|--------:|--------:|-------:|-------:|:--------------|-----:|-----:|-------------:|------:|-------:|------:|:-------|
| 1-train | 101 |       163 |  40.6 |    1.76 |   -1.11 |  0.056 |  0.017 | [-0.25,+0.36] | 1.08 |  9.2 |            8 |  34.7 |   58.4 |  13.9 |        |
| 2-valid |  16 |        45 |  37.5 |    1.46 |   -1.32 | -0.276 | -0.355 | [-0.98,+0.48] | 0.67 |  9.4 |            4 |  25   |   62.5 |  25   | n<30   |
| 3-test  |  25 |        52 |  36   |    1.55 |   -1.1  | -0.141 | -0.184 | [-0.67,+0.40] | 0.8  | 11   |            5 |  28   |   64   |  24   | n<30   |
| ALL     | 142 |       260 |  39.4 |    1.7  |   -1.13 | -0.016 | -0.06  | [-0.27,+0.22] | 0.98 | 13.4 |            8 |  32.4 |   59.9 |  16.9 |        |

by year: 2005: n1 -1.03R w0%; 2007: n1 -1.02R w0%; 2008: n1 -1.01R w0%; 2012: n7 -0.50R w29%; 2013: n24 +0.19R w42%; 2014: n19 +0.28R w47%; 2015: n25 +0.12R w48%; 2016: n7 -0.67R w14%; 2017: n7 +0.69R w57%; 2018: n9 -0.06R w33%; 2019: n10 +0.21R w50%; 2020: n2 -1.22R w50%; 2021: n4 -1.02R w0%; 2022: n11 +0.57R w55%; 2023: n9 -0.78R w11%; 2024: n1 -1.04R w0%; 2025: n3 -0.61R w33%; 2026: n1 +0.04R w100%

by instrument: ALUMINIUM: n22 -0.35R; COPPER: n36 -0.27R; CRUDEOIL: n9 +0.30R; GOLD: n34 +0.16R; NATURALGAS: n1 +1.08R; SILVER: n40 +0.14R

by regime: range/hi-vol: n35 -0.18R w37%; range/lo-vol: n49 +0.23R w47%; trend/hi-vol: n34 -0.21R w32%; trend/lo-vol: n24 -0.01R w38%

### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)
| variant                                              |   train_n |   train_win |   train_exp2 |   train_d |   valid_n |   valid_win |   valid_exp2 |   valid_d |   test_n |   test_win |   test_exp2 |   test_d | verdict                |
|:-----------------------------------------------------|----------:|------------:|-------------:|----------:|----------:|------------:|-------------:|----------:|---------:|-----------:|------------:|---------:|:-----------------------|
| A1 trend ADX≥25                                      |        49 |        36.7 |       -0.041 |    -0.06  |         8 |        12.5 |       -1.248 |    -0.874 |        4 |       25   |      -0.436 |   -0.26  | FAIL train             |
| A2 high volatility                                   |        50 |        32   |       -0.263 |    -0.28  |         9 |        33.3 |       -0.791 |    -0.406 |       12 |       41.7 |       0.14  |    0.321 | FAIL train             |
| A3 low volatility                                    |        55 |        47.3 |        0.256 |     0.238 |         8 |        37.5 |        0.147 |     0.466 |       15 |       26.7 |      -0.56  |   -0.375 | pass train, FAIL valid |
| A4 vol expanding ATR14>ATR50                         |        36 |        36.1 |       -0.122 |    -0.143 |         9 |        33.3 |       -0.691 |    -0.308 |        3 |       66.7 |       0.9   |    1.09  | FAIL train             |
| A5 not stretched ≤3 ATR from EMA200                  |         9 |        44.4 |        0.122 |     0.098 |         1 |         0   |       -1.121 |    -0.784 |        4 |       75   |       0.284 |    0.446 | FAIL train             |
| A6 momentum ROC20 aligned                            |       101 |        40.6 |        0.017 |     0     |        16 |        37.5 |       -0.355 |     0     |       25 |       36   |      -0.184 |    0     | FAIL train             |
| B1 extension ≤1 ATR                                  |        82 |        40.2 |       -0.05  |    -0.067 |        12 |        41.7 |        0.012 |     0.347 |       21 |       38.1 |      -0.143 |    0.037 | FAIL train             |
| B2 close near extreme (CLV)                          |        70 |        41.4 |        0.1   |     0.075 |         7 |        42.9 |        0.074 |     0.395 |       14 |       21.4 |      -0.47  |   -0.304 | pass train, FAIL valid |
| B3 strong body ≥50%                                  |        76 |        39.5 |        0.038 |     0.013 |         8 |        37.5 |       -0.316 |     0.009 |       16 |       25   |      -0.541 |   -0.374 | pass train, FAIL valid |
| B4 prior compression                                 |        52 |        36.5 |       -0.102 |    -0.12  |         9 |        44.4 |        0.032 |     0.378 |       17 |       41.2 |      -0.123 |    0.069 | FAIL train             |
| B5 room ≥3 ATR to older level                        |        72 |        36.1 |       -0.112 |    -0.129 |        13 |        38.5 |       -0.351 |     0.012 |       13 |       30.8 |      -0.25  |   -0.05  | FAIL train             |
| C1 volume ≥2×                                        |        15 |        46.7 |        0.113 |     0.112 |         2 |       100   |        0.89  |     1.252 |        0 |      nan   |     nan     |  nan     | FAIL train             |
| C2 RSI not exhausted                                 |        97 |        41.2 |        0.015 |    -0.001 |        13 |        38.5 |       -0.191 |     0.153 |       23 |       34.8 |      -0.24  |   -0.054 | FAIL train             |
| X1 stop 2 ATR · target 1R                            |        82 |        47.6 |       -0.126 |    -0.151 |        14 |        42.9 |       -0.311 |     0.029 |       14 |       57.1 |      -0.022 |    0.158 | FAIL train             |
| X2 stop 2 ATR · target 0.75R                         |        87 |        52.9 |       -0.149 |    -0.173 |        15 |        46.7 |       -0.36  |    -0.022 |       14 |       57.1 |      -0.147 |    0.033 | FAIL train             |
| X3 stop 2 ATR · target 0.5R                          |        90 |        63.3 |       -0.119 |    -0.144 |        18 |        55.6 |       -0.337 |     0.001 |       14 |       64.3 |      -0.165 |    0.015 | FAIL train             |
| X4 stop 3 ATR · target 0.5R                          |        39 |        61.5 |       -0.102 |    -0.13  |        10 |        40   |       -0.549 |    -0.22  |        6 |       66.7 |      -0.139 |    0.037 | FAIL train             |
| X5 stop 1.5 ATR · target 2R                          |       101 |        40.6 |        0.017 |     0     |        16 |        37.5 |       -0.355 |     0     |       25 |       36   |      -0.184 |    0     | FAIL train             |
| X6 stop 2.5 ATR · target 3R                          |        57 |        42.1 |        0.044 |     0.017 |        10 |        30   |       -0.664 |    -0.331 |        9 |       44.4 |      -0.35  |   -0.172 | pass train, FAIL valid |
| X7 swing stop (10-bar extreme ± 0.5 ATR) · target 2R |        28 |        53.6 |        0.15  |     0.13  |         6 |        33.3 |       -0.518 |    -0.215 |        5 |       80   |       0.7   |    0.863 | pass train, FAIL valid |
