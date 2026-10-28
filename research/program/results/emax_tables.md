# EMAX-002 – EMA crossover + volume + OI (generated)

variants 1527 · PASS (profitable at 2× costs, PF ≥ 1.2 in every period): 40

| seg                  | pair   | side   | conf   | exit              |   train_n |   train_win |   train_exp2 |   valid_n |   valid_win |   valid_exp2 |   test_n |   test_win |   test_exp2 |   test_pf |
|:---------------------|:-------|:-------|:-------|:------------------|----------:|------------:|-------------:|----------:|------------:|-------------:|---------:|-----------:|------------:|----------:|
| INDEX 15m            | 5/13   | SELL   | V      | Y3 trail 3ATR     |        16 |      62.5   |        0.623 |       nan |     nan     |      nan     |       20 |     50     |       0.18  |     1.82  |
| INDEX 15m            | 9/21   | SELL   | T      | Y3 trail 3ATR     |        27 |      51.852 |        0.507 |       nan |     nan     |      nan     |       28 |     39.286 |       0.034 |     1.276 |
| INDEX 15m            | 5/13   | SELL   | V      | Y2 2ATR stop / 2R |        15 |      66.667 |        0.59  |       nan |     nan     |      nan     |       20 |     45     |       0.031 |     1.298 |
| INDEX 1h             | 20/50  | SELL   | T      | Y2 2ATR stop / 2R |        30 |      50     |        0.072 |        16 |      50     |        0.329 |       27 |     51.852 |       0.116 |     1.314 |
| INDEX 1h             | 9/21   | SELL   | V      | Y3 trail 3ATR     |        56 |      35.714 |        0.071 |        22 |      31.818 |        0.115 |       39 |     46.154 |       0.038 |     1.259 |
| INDEX 1h             | 20/50  | SELL   | none   | Y3 trail 3ATR     |        56 |      44.643 |        0.072 |        30 |      40     |        0.072 |       47 |     46.809 |       0.032 |     1.246 |
| MCX 15m              | 9/21   | BUY    | V+T    | Y2 2ATR stop / 2R |        19 |      57.895 |        0.33  |       nan |     nan     |      nan     |       17 |     47.059 |       0.049 |     1.351 |
| MCX 1d               | 9/21   | BUY    | none   | Y1 opposite cross |        44 |      43.182 |        0.138 |        40 |      50     |        0.124 |       32 |     50     |       0.084 |     1.557 |
| MCX 1d               | 9/21   | BUY    | none   | Y3 trail 3ATR     |        40 |      50     |        0.149 |        40 |      50     |        0.151 |       30 |     53.333 |       0.072 |     1.401 |
| MCX 1h               | 20/50  | BUY    | V+T    | Y1 opposite cross |        81 |      30.864 |        0.015 |        44 |      43.182 |        0.278 |       51 |     37.255 |       0.451 |     2.147 |
| MCX 1h               | 50/200 | BUY    | none   | Y1 opposite cross |       140 |      36.429 |        0.236 |        73 |      35.616 |        0.121 |       97 |     36.082 |       0.252 |     1.504 |
| MCX 1h               | 9/21   | BUY    | V      | Y1 opposite cross |       249 |      31.325 |        0.109 |       139 |      39.568 |        0.075 |      190 |     36.842 |       0.061 |     1.313 |
| MCX 3h               | 9/21   | BUY    | V+T    | Y3 trail 3ATR     |        39 |      33.333 |        0.131 |        23 |      43.478 |        0.169 |       35 |     45.714 |       0.493 |     4.055 |
| MCX 3h               | 9/21   | BUY    | T      | Y1 opposite cross |       159 |      33.962 |        0.137 |        95 |      42.105 |        0.201 |      146 |     42.466 |       0.451 |     2.933 |
| MCX 3h               | 9/21   | BUY    | T      | Y3 trail 3ATR     |       141 |      36.879 |        0.046 |        88 |      44.318 |        0.074 |      137 |     45.255 |       0.417 |     2.49  |
| MCX 3h               | 9/21   | BUY    | none   | Y1 opposite cross |       287 |      33.101 |        0.077 |       169 |      41.42  |        0.137 |      202 |     40.099 |       0.333 |     2.297 |
| MCX 3h               | 9/21   | BUY    | V+T    | Y1 opposite cross |        40 |      35     |        0.161 |        24 |      41.667 |        0.299 |       37 |     45.946 |       0.329 |     2.609 |
| MCX 3h               | 20/50  | BUY    | T      | Y3 trail 3ATR     |        87 |      39.08  |        0.211 |        52 |      42.308 |        0.122 |       74 |     50     |       0.308 |     2.09  |
| MCX 3h               | 9/21   | BUY    | V+T    | Y2 2ATR stop / 2R |        37 |      45.946 |        0.162 |        23 |      43.478 |        0.175 |       36 |     52.778 |       0.306 |     1.74  |
| MCX 3h               | 9/21   | BUY    | V      | Y3 trail 3ATR     |        71 |      35.211 |        0.159 |        45 |      44.444 |        0.076 |       46 |     41.304 |       0.299 |     2.523 |
| MCX 3h               | 9/21   | BUY    | V      | Y1 opposite cross |        76 |      27.632 |        0.069 |        49 |      36.735 |        0.129 |       48 |     41.667 |       0.295 |     2.398 |
| MCX 3h               | 20/50  | BUY    | T      | Y1 opposite cross |        88 |      39.773 |        0.296 |        53 |      47.17  |        0.45  |       79 |     40.506 |       0.265 |     1.663 |
| MCX 3h               | 9/21   | BUY    | none   | Y3 trail 3ATR     |       253 |      38.34  |        0.048 |       157 |      48.408 |        0.088 |      191 |     43.455 |       0.263 |     1.922 |
| MCX 3h               | 20/50  | BUY    | none   | Y3 trail 3ATR     |       129 |      41.86  |        0.179 |        76 |      42.105 |        0.08  |       95 |     49.474 |       0.24  |     1.818 |
| MCX 3h               | 20/50  | BUY    | none   | Y1 opposite cross |       137 |      37.956 |        0.149 |        79 |      45.57  |        0.331 |      100 |     39     |       0.2   |     1.515 |
| MCX 3h               | 9/21   | SELL   | V+T    | Y1 opposite cross |        37 |      32.432 |        0.036 |        23 |      47.826 |        0.457 |       19 |     42.105 |       0.051 |     1.233 |
| MCX proxy 1d 2005-26 | 20/50  | BUY    | none   | Y1 opposite cross |       170 |      29.412 |        0.222 |        44 |      34.091 |        0.397 |       62 |     35.484 |       0.274 |     1.532 |
| MCX proxy 1d 2005-26 | 20/50  | BUY    | none   | Y2 2ATR stop / 2R |       161 |      40.994 |        0.139 |        40 |      47.5   |        0.33  |       62 |     45.161 |       0.27  |     1.505 |
| MCX proxy 1d 2005-26 | 20/50  | BUY    | none   | Y3 trail 3ATR     |       164 |      39.024 |        0.135 |        41 |      36.585 |        0.182 |       63 |     41.27  |       0.238 |     1.642 |
| MCX proxy 1d 2005-26 | 20/50  | BUY    | T      | Y3 trail 3ATR     |       111 |      36.036 |        0.126 |        27 |      29.63  |        0.213 |       45 |     35.556 |       0.111 |     1.275 |
| MCX proxy 1d 2005-26 | 9/21   | BUY    | T      | Y1 opposite cross |       213 |      35.211 |        0.409 |        51 |      49.02  |        0.704 |      103 |     32.039 |       0.108 |     1.292 |
| MCX proxy 1d 2005-26 | 9/21   | BUY    | T      | Y3 trail 3ATR     |       189 |      42.857 |        0.32  |        50 |      46     |        0.396 |       92 |     35.87  |       0.084 |     1.246 |
| MCX proxy 1d 2005-26 | 9/21   | BUY    | none   | Y3 trail 3ATR     |       321 |      41.121 |        0.182 |        79 |      45.57  |        0.322 |      145 |     36.552 |       0.07  |     1.217 |
| STOCKS 15m           | 50/200 | SELL   | O      | Y1 opposite cross |        21 |      42.857 |        0.752 |       nan |     nan     |      nan     |       20 |     50     |       0.363 |     1.84  |
| STOCKS 15m           | 9/21   | SELL   | V      | Y2 2ATR stop / 2R |       109 |      49.541 |        0.062 |       nan |     nan     |      nan     |       76 |     50     |       0.19  |     1.587 |
| STOCKS 15m           | 50/200 | SELL   | none   | Y2 2ATR stop / 2R |        49 |      53.061 |        0.171 |       nan |     nan     |      nan     |       48 |     47.917 |       0.177 |     1.52  |
| STOCKS 15m           | 50/200 | SELL   | O      | Y3 trail 3ATR     |        21 |      42.857 |        0.223 |       nan |     nan     |      nan     |       26 |     53.846 |       0.091 |     1.444 |
| STOCKS 15m           | 50/200 | SELL   | O      | Y2 2ATR stop / 2R |        21 |      61.905 |        0.389 |       nan |     nan     |      nan     |       29 |     44.828 |       0.077 |     1.337 |
| STOCKS 15m           | 50/200 | SELL   | none   | Y3 trail 3ATR     |        49 |      36.735 |        0.013 |       nan |     nan     |      nan     |       44 |     52.273 |       0.028 |     1.288 |
| STOCKS 3h            | 50/200 | SELL   | none   | Y1 opposite cross |       186 |      54.839 |        0.095 |       170 |      43.529 |        0.064 |      359 |     58.496 |       0.178 |     1.757 |

## Plain crossover (no confirmation) – all periods pooled

| seg                  | pair   | side   | exit              |     n |   win |   exp2 |
|:---------------------|:-------|:-------|:------------------|------:|------:|-------:|
| INDEX 15m            | 20/50  | BUY    | Y1 opposite cross |    31 |   6.5 | -1.015 |
| INDEX 15m            | 20/50  | BUY    | Y2 2ATR stop / 2R |    31 |   9.7 | -1.171 |
| INDEX 15m            | 20/50  | BUY    | Y3 trail 3ATR     |    30 |  23.3 | -0.639 |
| INDEX 15m            | 20/50  | SELL   | Y1 opposite cross |    31 |  38.7 |  0.191 |
| INDEX 15m            | 20/50  | SELL   | Y2 2ATR stop / 2R |    33 |  39.4 | -0.233 |
| INDEX 15m            | 20/50  | SELL   | Y3 trail 3ATR     |    32 |  40.6 |  0.118 |
| INDEX 15m            | 5/13   | BUY    | Y1 opposite cross |   114 |  24.6 | -0.482 |
| INDEX 15m            | 5/13   | BUY    | Y2 2ATR stop / 2R |    70 |  32.9 | -0.523 |
| INDEX 15m            | 5/13   | BUY    | Y3 trail 3ATR     |    79 |  32.9 | -0.536 |
| INDEX 15m            | 5/13   | SELL   | Y1 opposite cross |   113 |  31   | -0.137 |
| INDEX 15m            | 5/13   | SELL   | Y2 2ATR stop / 2R |    89 |  42.7 | -0.147 |
| INDEX 15m            | 5/13   | SELL   | Y3 trail 3ATR     |    91 |  38.5 |  0.051 |
| INDEX 15m            | 50/200 | BUY    | Y1 opposite cross |     9 |  11.1 | -1.043 |
| INDEX 15m            | 50/200 | BUY    | Y2 2ATR stop / 2R |     9 |  11.1 | -1.093 |
| INDEX 15m            | 50/200 | BUY    | Y3 trail 3ATR     |     9 |  33.3 | -0.703 |
| INDEX 15m            | 50/200 | SELL   | Y1 opposite cross |     7 |  28.6 | -0.125 |
| INDEX 15m            | 50/200 | SELL   | Y2 2ATR stop / 2R |    10 |  30   | -0.476 |
| INDEX 15m            | 50/200 | SELL   | Y3 trail 3ATR     |     9 |  33.3 | -0.329 |
| INDEX 15m            | 9/21   | BUY    | Y1 opposite cross |    67 |  13.4 | -0.671 |
| INDEX 15m            | 9/21   | BUY    | Y2 2ATR stop / 2R |    54 |  27.8 | -0.704 |
| INDEX 15m            | 9/21   | BUY    | Y3 trail 3ATR     |    61 |  24.6 | -0.636 |
| INDEX 15m            | 9/21   | SELL   | Y1 opposite cross |    68 |  33.8 | -0.022 |
| INDEX 15m            | 9/21   | SELL   | Y2 2ATR stop / 2R |    66 |  45.5 | -0.038 |
| INDEX 15m            | 9/21   | SELL   | Y3 trail 3ATR     |    66 |  45.5 |  0.213 |
| INDEX 1d             | 20/50  | BUY    | Y1 opposite cross |    14 |  42.9 | -0.07  |
| INDEX 1d             | 20/50  | BUY    | Y2 2ATR stop / 2R |    14 |  42.9 | -0.074 |
| INDEX 1d             | 20/50  | BUY    | Y3 trail 3ATR     |    14 |  42.9 |  0.002 |
| INDEX 1d             | 20/50  | SELL   | Y1 opposite cross |    15 |  66.7 |  0.449 |
| INDEX 1d             | 20/50  | SELL   | Y2 2ATR stop / 2R |    14 |  64.3 |  0.597 |
| INDEX 1d             | 20/50  | SELL   | Y3 trail 3ATR     |    14 |  64.3 |  0.465 |
| INDEX 1d             | 50/200 | BUY    | Y1 opposite cross |     4 |  50   |  0.159 |
| INDEX 1d             | 50/200 | BUY    | Y2 2ATR stop / 2R |     4 |  50   |  0.051 |
| INDEX 1d             | 50/200 | BUY    | Y3 trail 3ATR     |     4 |  50   | -0.087 |
| INDEX 1d             | 50/200 | SELL   | Y1 opposite cross |     4 |  75   |  0.484 |
| INDEX 1d             | 50/200 | SELL   | Y2 2ATR stop / 2R |     3 | 100   |  1.054 |
| INDEX 1d             | 50/200 | SELL   | Y3 trail 3ATR     |     3 | 100   |  0.702 |
| INDEX 1d             | 9/21   | BUY    | Y1 opposite cross |    34 |  32.4 | -0.136 |
| INDEX 1d             | 9/21   | BUY    | Y2 2ATR stop / 2R |    33 |  36.4 | -0.138 |
| INDEX 1d             | 9/21   | BUY    | Y3 trail 3ATR     |    32 |  34.4 | -0.12  |
| INDEX 1d             | 9/21   | SELL   | Y1 opposite cross |    41 |  43.9 |  0.069 |
| INDEX 1d             | 9/21   | SELL   | Y2 2ATR stop / 2R |    40 |  50   | -0.004 |
| INDEX 1d             | 9/21   | SELL   | Y3 trail 3ATR     |    40 |  50   |  0.064 |
| INDEX 1d NSE 2011-26 | 20/50  | BUY    | Y1 opposite cross |    49 |  61.2 |  0.073 |
| INDEX 1d NSE 2011-26 | 20/50  | BUY    | Y2 2ATR stop / 2R |    49 |  61.2 |  0.134 |
| INDEX 1d NSE 2011-26 | 20/50  | BUY    | Y3 trail 3ATR     |    48 |  58.3 |  0.052 |
| INDEX 1d NSE 2011-26 | 20/50  | SELL   | Y1 opposite cross |    48 |  64.6 |  0.322 |
| INDEX 1d NSE 2011-26 | 20/50  | SELL   | Y2 2ATR stop / 2R |    47 |  63.8 |  0.365 |
| INDEX 1d NSE 2011-26 | 20/50  | SELL   | Y3 trail 3ATR     |    47 |  66   |  0.331 |
| INDEX 1d NSE 2011-26 | 50/200 | BUY    | Y1 opposite cross |    22 |  59.1 |  0.131 |
| INDEX 1d NSE 2011-26 | 50/200 | BUY    | Y2 2ATR stop / 2R |    22 |  54.5 |  0.159 |
| INDEX 1d NSE 2011-26 | 50/200 | BUY    | Y3 trail 3ATR     |    22 |  50   |  0.002 |
| INDEX 1d NSE 2011-26 | 50/200 | SELL   | Y1 opposite cross |    21 |  38.1 | -0.083 |
| INDEX 1d NSE 2011-26 | 50/200 | SELL   | Y2 2ATR stop / 2R |    21 |  38.1 | -0.151 |
| INDEX 1d NSE 2011-26 | 50/200 | SELL   | Y3 trail 3ATR     |    21 |  38.1 | -0.083 |
| INDEX 1d NSE 2011-26 | 9/21   | BUY    | Y1 opposite cross |   130 |  48.5 |  0.053 |
| INDEX 1d NSE 2011-26 | 9/21   | BUY    | Y2 2ATR stop / 2R |   130 |  50.8 |  0.077 |
| INDEX 1d NSE 2011-26 | 9/21   | BUY    | Y3 trail 3ATR     |   128 |  52.3 |  0.064 |
| INDEX 1d NSE 2011-26 | 9/21   | SELL   | Y1 opposite cross |   140 |  52.1 |  0.112 |
| INDEX 1d NSE 2011-26 | 9/21   | SELL   | Y2 2ATR stop / 2R |   137 |  52.6 |  0.099 |
| INDEX 1d NSE 2011-26 | 9/21   | SELL   | Y3 trail 3ATR     |   134 |  53.7 |  0.111 |
| INDEX 1h             | 20/50  | BUY    | Y1 opposite cross |   135 |  33.3 | -0.127 |
| INDEX 1h             | 20/50  | BUY    | Y2 2ATR stop / 2R |   133 |  33.8 | -0.267 |
| INDEX 1h             | 20/50  | BUY    | Y3 trail 3ATR     |   132 |  37.9 | -0.023 |
| INDEX 1h             | 20/50  | SELL   | Y1 opposite cross |   139 |  36.7 |  0.111 |
| INDEX 1h             | 20/50  | SELL   | Y2 2ATR stop / 2R |   131 |  45.8 |  0.025 |
| INDEX 1h             | 20/50  | SELL   | Y3 trail 3ATR     |   133 |  44.4 |  0.058 |
| INDEX 1h             | 5/13   | BUY    | Y1 opposite cross |   447 |  28   | -0.145 |
| INDEX 1h             | 5/13   | BUY    | Y2 2ATR stop / 2R |   330 |  31.5 | -0.32  |
| INDEX 1h             | 5/13   | BUY    | Y3 trail 3ATR     |   349 |  34.1 | -0.14  |
| INDEX 1h             | 5/13   | SELL   | Y1 opposite cross |   462 |  31.4 | -0.035 |
| INDEX 1h             | 5/13   | SELL   | Y2 2ATR stop / 2R |   370 |  40   | -0.073 |
| INDEX 1h             | 5/13   | SELL   | Y3 trail 3ATR     |   381 |  38.1 | -0.003 |
| INDEX 1h             | 50/200 | BUY    | Y1 opposite cross |    44 |  38.6 |  0.033 |
| INDEX 1h             | 50/200 | BUY    | Y2 2ATR stop / 2R |    44 |  52.3 |  0.233 |
| INDEX 1h             | 50/200 | BUY    | Y3 trail 3ATR     |    44 |  50   |  0.13  |
| INDEX 1h             | 50/200 | SELL   | Y1 opposite cross |    47 |  36.2 |  0.18  |
| INDEX 1h             | 50/200 | SELL   | Y2 2ATR stop / 2R |    47 |  34   | -0.304 |
| INDEX 1h             | 50/200 | SELL   | Y3 trail 3ATR     |    47 |  36.2 | -0.161 |
| INDEX 1h             | 9/21   | BUY    | Y1 opposite cross |   275 |  30.2 | -0.116 |
| INDEX 1h             | 9/21   | BUY    | Y2 2ATR stop / 2R |   238 |  33.6 | -0.264 |
| INDEX 1h             | 9/21   | BUY    | Y3 trail 3ATR     |   249 |  36.9 | -0.097 |
| INDEX 1h             | 9/21   | SELL   | Y1 opposite cross |   286 |  35.3 |  0.084 |
| INDEX 1h             | 9/21   | SELL   | Y2 2ATR stop / 2R |   265 |  43   | -0.019 |
| INDEX 1h             | 9/21   | SELL   | Y3 trail 3ATR     |   269 |  41.3 |  0.052 |
| INDEX 3h             | 20/50  | BUY    | Y1 opposite cross |    39 |  33.3 | -0.134 |
| INDEX 3h             | 20/50  | BUY    | Y2 2ATR stop / 2R |    39 |  35.9 | -0.103 |
| INDEX 3h             | 20/50  | BUY    | Y3 trail 3ATR     |    39 |  43.6 | -0.044 |
| INDEX 3h             | 20/50  | SELL   | Y1 opposite cross |    43 |  44.2 |  0.258 |
| INDEX 3h             | 20/50  | SELL   | Y2 2ATR stop / 2R |    42 |  42.9 | -0.08  |
| INDEX 3h             | 20/50  | SELL   | Y3 trail 3ATR     |    42 |  52.4 |  0.198 |
| INDEX 3h             | 50/200 | BUY    | Y1 opposite cross |    10 |  40   | -0.265 |
| INDEX 3h             | 50/200 | BUY    | Y2 2ATR stop / 2R |    10 |  40   | -0.314 |
| INDEX 3h             | 50/200 | BUY    | Y3 trail 3ATR     |    10 |  30   | -0.44  |
| INDEX 3h             | 50/200 | SELL   | Y1 opposite cross |    11 |  72.7 |  0.833 |
| INDEX 3h             | 50/200 | SELL   | Y2 2ATR stop / 2R |    11 |  63.6 |  0.013 |
| INDEX 3h             | 50/200 | SELL   | Y3 trail 3ATR     |    11 |  63.6 |  0.437 |
| INDEX 3h             | 9/21   | BUY    | Y1 opposite cross |    80 |  32.5 | -0.022 |
| INDEX 3h             | 9/21   | BUY    | Y2 2ATR stop / 2R |    73 |  37   | -0.016 |
| INDEX 3h             | 9/21   | BUY    | Y3 trail 3ATR     |    73 |  38.4 |  0.025 |
| INDEX 3h             | 9/21   | SELL   | Y1 opposite cross |    85 |  40   |  0.052 |
| INDEX 3h             | 9/21   | SELL   | Y2 2ATR stop / 2R |    73 |  49.3 |  0.073 |
| INDEX 3h             | 9/21   | SELL   | Y3 trail 3ATR     |    73 |  47.9 |  0.066 |
| MCX 15m              | 20/50  | BUY    | Y1 opposite cross |    79 |  26.6 | -0.282 |
| MCX 15m              | 20/50  | BUY    | Y2 2ATR stop / 2R |    79 |  34.2 | -0.316 |
| MCX 15m              | 20/50  | BUY    | Y3 trail 3ATR     |    79 |  34.2 | -0.191 |
| MCX 15m              | 20/50  | SELL   | Y1 opposite cross |    78 |  28.2 | -0.156 |
| MCX 15m              | 20/50  | SELL   | Y2 2ATR stop / 2R |    79 |  35.4 | -0.38  |
| MCX 15m              | 20/50  | SELL   | Y3 trail 3ATR     |    79 |  30.4 | -0.185 |
| MCX 15m              | 5/13   | BUY    | Y1 opposite cross |   288 |  29.2 | -0.141 |
| MCX 15m              | 5/13   | BUY    | Y2 2ATR stop / 2R |   209 |  37.8 | -0.244 |
| MCX 15m              | 5/13   | BUY    | Y3 trail 3ATR     |   221 |  34.4 | -0.236 |
| MCX 15m              | 5/13   | SELL   | Y1 opposite cross |   282 |  25.5 | -0.163 |
| MCX 15m              | 5/13   | SELL   | Y2 2ATR stop / 2R |   199 |  35.2 | -0.321 |
| MCX 15m              | 5/13   | SELL   | Y3 trail 3ATR     |   211 |  30.8 | -0.238 |
| MCX 15m              | 50/200 | BUY    | Y1 opposite cross |    34 |  26.5 | -0.226 |
| MCX 15m              | 50/200 | BUY    | Y2 2ATR stop / 2R |    34 |  32.4 | -0.404 |
| MCX 15m              | 50/200 | BUY    | Y3 trail 3ATR     |    33 |  33.3 | -0.283 |
| MCX 15m              | 50/200 | SELL   | Y1 opposite cross |    34 |  29.4 | -0.11  |
| MCX 15m              | 50/200 | SELL   | Y2 2ATR stop / 2R |    33 |  36.4 | -0.226 |
| MCX 15m              | 50/200 | SELL   | Y3 trail 3ATR     |    33 |  30.3 |  0.065 |
| MCX 15m              | 9/21   | BUY    | Y1 opposite cross |   175 |  27.4 | -0.237 |
| MCX 15m              | 9/21   | BUY    | Y2 2ATR stop / 2R |   156 |  41   | -0.166 |
| MCX 15m              | 9/21   | BUY    | Y3 trail 3ATR     |   159 |  36.5 | -0.18  |
| MCX 15m              | 9/21   | SELL   | Y1 opposite cross |   175 |  25.1 | -0.292 |
| MCX 15m              | 9/21   | SELL   | Y2 2ATR stop / 2R |   147 |  32   | -0.462 |
| MCX 15m              | 9/21   | SELL   | Y3 trail 3ATR     |   160 |  26.2 | -0.331 |
| MCX 1d               | 20/50  | BUY    | Y1 opposite cross |    59 |  50.8 |  0.09  |
| MCX 1d               | 20/50  | BUY    | Y2 2ATR stop / 2R |    58 |  55.2 |  0.265 |
| MCX 1d               | 20/50  | BUY    | Y3 trail 3ATR     |    57 |  57.9 |  0.135 |
| MCX 1d               | 20/50  | SELL   | Y1 opposite cross |    54 |  53.7 |  0.003 |
| MCX 1d               | 20/50  | SELL   | Y2 2ATR stop / 2R |    54 |  53.7 |  0.093 |
| MCX 1d               | 20/50  | SELL   | Y3 trail 3ATR     |    52 |  53.8 |  0.032 |
| MCX 1d               | 50/200 | BUY    | Y1 opposite cross |    13 |  61.5 |  0.063 |
| MCX 1d               | 50/200 | BUY    | Y2 2ATR stop / 2R |    13 |  53.8 |  0.043 |
| MCX 1d               | 50/200 | BUY    | Y3 trail 3ATR     |    12 |  66.7 |  0.117 |
| MCX 1d               | 50/200 | SELL   | Y1 opposite cross |    13 |  53.8 |  0.07  |
| MCX 1d               | 50/200 | SELL   | Y2 2ATR stop / 2R |    13 |  38.5 | -0.143 |
| MCX 1d               | 50/200 | SELL   | Y3 trail 3ATR     |    13 |  53.8 |  0.068 |
| MCX 1d               | 9/21   | BUY    | Y1 opposite cross |   116 |  47.4 |  0.118 |
| MCX 1d               | 9/21   | BUY    | Y2 2ATR stop / 2R |   113 |  46.9 |  0.088 |
| MCX 1d               | 9/21   | BUY    | Y3 trail 3ATR     |   110 |  50.9 |  0.129 |
| MCX 1d               | 9/21   | SELL   | Y1 opposite cross |   124 |  33.1 | -0.187 |
| MCX 1d               | 9/21   | SELL   | Y2 2ATR stop / 2R |   117 |  38.5 | -0.235 |
| MCX 1d               | 9/21   | SELL   | Y3 trail 3ATR     |   118 |  36.4 | -0.229 |
| MCX 1h               | 20/50  | BUY    | Y1 opposite cross |   949 |  33.2 |  0.124 |
| MCX 1h               | 20/50  | BUY    | Y2 2ATR stop / 2R |   926 |  39.6 | -0.128 |
| MCX 1h               | 20/50  | BUY    | Y3 trail 3ATR     |   931 |  38.2 | -0.018 |
| MCX 1h               | 20/50  | SELL   | Y1 opposite cross |   968 |  28   | -0.137 |
| MCX 1h               | 20/50  | SELL   | Y2 2ATR stop / 2R |   930 |  35.8 | -0.25  |
| MCX 1h               | 20/50  | SELL   | Y3 trail 3ATR     |   942 |  35.1 | -0.173 |
| MCX 1h               | 5/13   | BUY    | Y1 opposite cross |  3337 |  30.7 | -0.065 |
| MCX 1h               | 5/13   | BUY    | Y2 2ATR stop / 2R |  2454 |  37.9 | -0.165 |
| MCX 1h               | 5/13   | BUY    | Y3 trail 3ATR     |  2589 |  38.5 | -0.027 |
| MCX 1h               | 5/13   | SELL   | Y1 opposite cross |  3372 |  28.6 | -0.159 |
| MCX 1h               | 5/13   | SELL   | Y2 2ATR stop / 2R |  2513 |  33.9 | -0.288 |
| MCX 1h               | 5/13   | SELL   | Y3 trail 3ATR     |  2592 |  34.5 | -0.151 |
| MCX 1h               | 50/200 | BUY    | Y1 opposite cross |   310 |  36.1 |  0.214 |
| MCX 1h               | 50/200 | BUY    | Y2 2ATR stop / 2R |   310 |  41   | -0.051 |
| MCX 1h               | 50/200 | BUY    | Y3 trail 3ATR     |   307 |  38.8 | -0.01  |
| MCX 1h               | 50/200 | SELL   | Y1 opposite cross |   317 |  29.3 | -0.145 |
| MCX 1h               | 50/200 | SELL   | Y2 2ATR stop / 2R |   318 |  35.8 | -0.255 |
| MCX 1h               | 50/200 | SELL   | Y3 trail 3ATR     |   316 |  34.2 | -0.121 |
| MCX 1h               | 9/21   | BUY    | Y1 opposite cross |  2040 |  31.9 | -0.009 |
| MCX 1h               | 9/21   | BUY    | Y2 2ATR stop / 2R |  1761 |  39.1 | -0.137 |
| MCX 1h               | 9/21   | BUY    | Y3 trail 3ATR     |  1868 |  37.9 | -0.025 |
| MCX 1h               | 9/21   | SELL   | Y1 opposite cross |  2034 |  28.4 | -0.145 |
| MCX 1h               | 9/21   | SELL   | Y2 2ATR stop / 2R |  1755 |  34.3 | -0.274 |
| MCX 1h               | 9/21   | SELL   | Y3 trail 3ATR     |  1860 |  34.9 | -0.141 |
| MCX 3h               | 20/50  | BUY    | Y1 opposite cross |   316 |  40.2 |  0.211 |
| MCX 3h               | 20/50  | BUY    | Y2 2ATR stop / 2R |   303 |  45.5 |  0.148 |
| MCX 3h               | 20/50  | BUY    | Y3 trail 3ATR     |   300 |  44.3 |  0.173 |
| MCX 3h               | 20/50  | SELL   | Y1 opposite cross |   308 |  29.5 | -0.18  |
| MCX 3h               | 20/50  | SELL   | Y2 2ATR stop / 2R |   299 |  34.8 | -0.168 |
| MCX 3h               | 20/50  | SELL   | Y3 trail 3ATR     |   293 |  37.5 | -0.043 |
| MCX 3h               | 50/200 | BUY    | Y1 opposite cross |   111 |  36   |  0.331 |
| MCX 3h               | 50/200 | BUY    | Y2 2ATR stop / 2R |   110 |  40.9 |  0.077 |
| MCX 3h               | 50/200 | BUY    | Y3 trail 3ATR     |   110 |  36.4 |  0.052 |
| MCX 3h               | 50/200 | SELL   | Y1 opposite cross |   108 |  26.9 | -0.382 |
| MCX 3h               | 50/200 | SELL   | Y2 2ATR stop / 2R |   108 |  29.6 | -0.319 |
| MCX 3h               | 50/200 | SELL   | Y3 trail 3ATR     |   106 |  29.2 | -0.307 |
| MCX 3h               | 9/21   | BUY    | Y1 opposite cross |   658 |  37.4 |  0.171 |
| MCX 3h               | 9/21   | BUY    | Y2 2ATR stop / 2R |   573 |  44.3 |  0.083 |
| MCX 3h               | 9/21   | BUY    | Y3 trail 3ATR     |   601 |  42.6 |  0.127 |
| MCX 3h               | 9/21   | SELL   | Y1 opposite cross |   654 |  33   | -0.066 |
| MCX 3h               | 9/21   | SELL   | Y2 2ATR stop / 2R |   566 |  35.7 | -0.143 |
| MCX 3h               | 9/21   | SELL   | Y3 trail 3ATR     |   609 |  36.1 | -0.075 |
| MCX proxy 1d 2005-26 | 20/50  | BUY    | Y1 opposite cross |   276 |  31.5 |  0.262 |
| MCX proxy 1d 2005-26 | 20/50  | BUY    | Y2 2ATR stop / 2R |   263 |  43   |  0.199 |
| MCX proxy 1d 2005-26 | 20/50  | BUY    | Y3 trail 3ATR     |   268 |  39.2 |  0.167 |
| MCX proxy 1d 2005-26 | 20/50  | SELL   | Y1 opposite cross |   270 |  23.3 | -0.054 |
| MCX proxy 1d 2005-26 | 20/50  | SELL   | Y2 2ATR stop / 2R |   263 |  30.8 | -0.168 |
| MCX proxy 1d 2005-26 | 20/50  | SELL   | Y3 trail 3ATR     |   268 |  31.7 | -0.042 |
| MCX proxy 1d 2005-26 | 50/200 | BUY    | Y1 opposite cross |    84 |  29.8 |  0.294 |
| MCX proxy 1d 2005-26 | 50/200 | BUY    | Y2 2ATR stop / 2R |    84 |  36.9 |  0.033 |
| MCX proxy 1d 2005-26 | 50/200 | BUY    | Y3 trail 3ATR     |    84 |  36.9 |  0.144 |
| MCX proxy 1d 2005-26 | 50/200 | SELL   | Y1 opposite cross |    85 |  27.1 |  0.234 |
| MCX proxy 1d 2005-26 | 50/200 | SELL   | Y2 2ATR stop / 2R |    86 |  32.6 | -0.198 |
| MCX proxy 1d 2005-26 | 50/200 | SELL   | Y3 trail 3ATR     |    85 |  31.8 |  0.389 |
| MCX proxy 1d 2005-26 | 9/21   | BUY    | Y1 opposite cross |   623 |  33.5 |  0.193 |
| MCX proxy 1d 2005-26 | 9/21   | BUY    | Y2 2ATR stop / 2R |   536 |  39.7 |  0.094 |
| MCX proxy 1d 2005-26 | 9/21   | BUY    | Y3 trail 3ATR     |   545 |  40.6 |  0.173 |
| MCX proxy 1d 2005-26 | 9/21   | SELL   | Y1 opposite cross |   619 |  27.9 | -0.068 |
| MCX proxy 1d 2005-26 | 9/21   | SELL   | Y2 2ATR stop / 2R |   510 |  29.2 | -0.24  |
| MCX proxy 1d 2005-26 | 9/21   | SELL   | Y3 trail 3ATR     |   560 |  31.6 | -0.112 |
| STOCKS 15m           | 20/50  | BUY    | Y1 opposite cross |   324 |  17.6 | -0.544 |
| STOCKS 15m           | 20/50  | BUY    | Y2 2ATR stop / 2R |   310 |  27.7 | -0.528 |
| STOCKS 15m           | 20/50  | BUY    | Y3 trail 3ATR     |   315 |  26   | -0.434 |
| STOCKS 15m           | 20/50  | SELL   | Y1 opposite cross |   307 |  28.7 | -0.032 |
| STOCKS 15m           | 20/50  | SELL   | Y2 2ATR stop / 2R |   314 |  41.4 | -0.123 |
| STOCKS 15m           | 20/50  | SELL   | Y3 trail 3ATR     |   321 |  34   | -0.103 |
| STOCKS 15m           | 5/13   | BUY    | Y1 opposite cross |  1141 |  21.4 | -0.316 |
| STOCKS 15m           | 5/13   | BUY    | Y2 2ATR stop / 2R |   815 |  26.5 | -0.571 |
| STOCKS 15m           | 5/13   | BUY    | Y3 trail 3ATR     |   833 |  25   | -0.393 |
| STOCKS 15m           | 5/13   | SELL   | Y1 opposite cross |  1123 |  32.2 | -0.121 |
| STOCKS 15m           | 5/13   | SELL   | Y2 2ATR stop / 2R |   790 |  40.6 | -0.155 |
| STOCKS 15m           | 5/13   | SELL   | Y3 trail 3ATR     |   829 |  36.9 | -0.062 |
| STOCKS 15m           | 50/200 | BUY    | Y1 opposite cross |    97 |  17.5 | -0.58  |
| STOCKS 15m           | 50/200 | BUY    | Y2 2ATR stop / 2R |    97 |  23.7 | -0.666 |
| STOCKS 15m           | 50/200 | BUY    | Y3 trail 3ATR     |    97 |  18.6 | -0.518 |
| STOCKS 15m           | 50/200 | SELL   | Y1 opposite cross |    80 |  41.2 |  0.402 |
| STOCKS 15m           | 50/200 | SELL   | Y2 2ATR stop / 2R |    97 |  50.5 |  0.174 |
| STOCKS 15m           | 50/200 | SELL   | Y3 trail 3ATR     |    93 |  44.1 |  0.02  |
| STOCKS 15m           | 9/21   | BUY    | Y1 opposite cross |   663 |  23.1 | -0.347 |
| STOCKS 15m           | 9/21   | BUY    | Y2 2ATR stop / 2R |   594 |  27.1 | -0.559 |
| STOCKS 15m           | 9/21   | BUY    | Y3 trail 3ATR     |   611 |  25.4 | -0.386 |
| STOCKS 15m           | 9/21   | SELL   | Y1 opposite cross |   666 |  34.2 | -0.043 |
| STOCKS 15m           | 9/21   | SELL   | Y2 2ATR stop / 2R |   546 |  45.4 |  0.003 |
| STOCKS 15m           | 9/21   | SELL   | Y3 trail 3ATR     |   599 |  39.4 | -0.001 |
| STOCKS 1d            | 20/50  | BUY    | Y1 opposite cross |   828 |  46.7 |  0.042 |
| STOCKS 1d            | 20/50  | BUY    | Y2 2ATR stop / 2R |   822 |  44.9 |  0.006 |
| STOCKS 1d            | 20/50  | BUY    | Y3 trail 3ATR     |   811 |  46.5 |  0.016 |
| STOCKS 1d            | 20/50  | SELL   | Y1 opposite cross |   902 |  53.5 |  0.074 |
| STOCKS 1d            | 20/50  | SELL   | Y2 2ATR stop / 2R |   900 |  52.9 |  0.094 |
| STOCKS 1d            | 20/50  | SELL   | Y3 trail 3ATR     |   887 |  54.3 |  0.077 |
| STOCKS 1d            | 50/200 | BUY    | Y1 opposite cross |   268 |  51.9 |  0.04  |
| STOCKS 1d            | 50/200 | BUY    | Y2 2ATR stop / 2R |   268 |  50   |  0.051 |
| STOCKS 1d            | 50/200 | BUY    | Y3 trail 3ATR     |   267 |  50.6 |  0.027 |
| STOCKS 1d            | 50/200 | SELL   | Y1 opposite cross |   280 |  56.1 |  0.067 |
| STOCKS 1d            | 50/200 | SELL   | Y2 2ATR stop / 2R |   281 |  54.8 |  0.077 |
| STOCKS 1d            | 50/200 | SELL   | Y3 trail 3ATR     |   278 |  56.1 |  0.062 |
| STOCKS 1d            | 9/21   | BUY    | Y1 opposite cross |  2000 |  43   | -0.017 |
| STOCKS 1d            | 9/21   | BUY    | Y2 2ATR stop / 2R |  1924 |  45.3 | -0.042 |
| STOCKS 1d            | 9/21   | BUY    | Y3 trail 3ATR     |  1895 |  45.6 | -0.033 |
| STOCKS 1d            | 9/21   | SELL   | Y1 opposite cross |  2138 |  46.5 |  0.041 |
| STOCKS 1d            | 9/21   | SELL   | Y2 2ATR stop / 2R |  2054 |  49.1 |  0.047 |
| STOCKS 1d            | 9/21   | SELL   | Y3 trail 3ATR     |  2011 |  49.8 |  0.039 |
| STOCKS 1h            | 20/50  | BUY    | Y1 opposite cross |  8912 |  31.3 | -0.084 |
| STOCKS 1h            | 20/50  | BUY    | Y2 2ATR stop / 2R |  8725 |  36.3 | -0.123 |
| STOCKS 1h            | 20/50  | BUY    | Y3 trail 3ATR     |  8722 |  36.8 | -0.074 |
| STOCKS 1h            | 20/50  | SELL   | Y1 opposite cross |  9004 |  34.8 | -0.01  |
| STOCKS 1h            | 20/50  | SELL   | Y2 2ATR stop / 2R |  8887 |  38.8 | -0.048 |
| STOCKS 1h            | 20/50  | SELL   | Y3 trail 3ATR     |  8796 |  37.4 | -0.06  |
| STOCKS 1h            | 5/13   | BUY    | Y1 opposite cross | 30902 |  30.5 | -0.063 |
| STOCKS 1h            | 5/13   | BUY    | Y2 2ATR stop / 2R | 23144 |  35.5 | -0.154 |
| STOCKS 1h            | 5/13   | BUY    | Y3 trail 3ATR     | 23890 |  36.1 | -0.085 |
| STOCKS 1h            | 5/13   | SELL   | Y1 opposite cross | 31832 |  31.6 | -0.055 |
| STOCKS 1h            | 5/13   | SELL   | Y2 2ATR stop / 2R | 24151 |  38.2 | -0.05  |
| STOCKS 1h            | 5/13   | SELL   | Y3 trail 3ATR     | 24735 |  37.2 | -0.053 |
| STOCKS 1h            | 50/200 | BUY    | Y1 opposite cross |  2812 |  35.3 | -0.025 |
| STOCKS 1h            | 50/200 | BUY    | Y2 2ATR stop / 2R |  2821 |  37.4 | -0.085 |
| STOCKS 1h            | 50/200 | BUY    | Y3 trail 3ATR     |  2799 |  37.3 | -0.053 |
| STOCKS 1h            | 50/200 | SELL   | Y1 opposite cross |  2896 |  38.2 |  0.044 |
| STOCKS 1h            | 50/200 | SELL   | Y2 2ATR stop / 2R |  2895 |  38.2 | -0.073 |
| STOCKS 1h            | 50/200 | SELL   | Y3 trail 3ATR     |  2882 |  37.5 | -0.065 |
| STOCKS 1h            | 9/21   | BUY    | Y1 opposite cross | 19258 |  31.1 | -0.065 |
| STOCKS 1h            | 9/21   | BUY    | Y2 2ATR stop / 2R | 16864 |  35.7 | -0.143 |
| STOCKS 1h            | 9/21   | BUY    | Y3 trail 3ATR     | 17559 |  36.3 | -0.083 |
| STOCKS 1h            | 9/21   | SELL   | Y1 opposite cross | 19776 |  32.5 | -0.043 |
| STOCKS 1h            | 9/21   | SELL   | Y2 2ATR stop / 2R | 17480 |  39   | -0.033 |
| STOCKS 1h            | 9/21   | SELL   | Y3 trail 3ATR     | 17993 |  37.9 | -0.044 |
| STOCKS 3h            | 20/50  | BUY    | Y1 opposite cross |  2193 |  41.5 | -0.031 |
| STOCKS 3h            | 20/50  | BUY    | Y2 2ATR stop / 2R |  2168 |  40   | -0.082 |
| STOCKS 3h            | 20/50  | BUY    | Y3 trail 3ATR     |  2136 |  39.9 | -0.057 |
| STOCKS 3h            | 20/50  | SELL   | Y1 opposite cross |  2282 |  47.2 |  0.075 |
| STOCKS 3h            | 20/50  | SELL   | Y2 2ATR stop / 2R |  2248 |  46.2 |  0.034 |
| STOCKS 3h            | 20/50  | SELL   | Y3 trail 3ATR     |  2209 |  45.7 |  0.042 |
| STOCKS 3h            | 50/200 | BUY    | Y1 opposite cross |   670 |  49.7 |  0.064 |
| STOCKS 3h            | 50/200 | BUY    | Y2 2ATR stop / 2R |   666 |  46.1 |  0.04  |
| STOCKS 3h            | 50/200 | BUY    | Y3 trail 3ATR     |   659 |  46.9 |  0.019 |
| STOCKS 3h            | 50/200 | SELL   | Y1 opposite cross |   715 |  54   |  0.129 |
| STOCKS 3h            | 50/200 | SELL   | Y2 2ATR stop / 2R |   722 |  47.9 |  0.077 |
| STOCKS 3h            | 50/200 | SELL   | Y3 trail 3ATR     |   713 |  47.4 |  0.064 |
| STOCKS 3h            | 9/21   | BUY    | Y1 opposite cross |  4932 |  36.2 | -0.04  |
| STOCKS 3h            | 9/21   | BUY    | Y2 2ATR stop / 2R |  4626 |  39.9 | -0.088 |
| STOCKS 3h            | 9/21   | BUY    | Y3 trail 3ATR     |  4536 |  40.5 | -0.058 |
| STOCKS 3h            | 9/21   | SELL   | Y1 opposite cross |  5129 |  39.6 |  0.003 |
| STOCKS 3h            | 9/21   | SELL   | Y2 2ATR stop / 2R |  4779 |  43.5 | -0.018 |
| STOCKS 3h            | 9/21   | SELL   | Y3 trail 3ATR     |  4700 |  43.8 | -0.006 |