# CASHQ – NSE cash-equity research leaderboard

Variants: **2001** · completed trades (all splits, all variants): **25,213,246**

Status counts: NOT_SELECTED 1994, PASS 5, FAIL_OOS 2

Protocol: SELECTED only if DEV and VALID both positive after costs (VALID PF ≥ 1.1, n ≥ 50 each); the OOS then decides (PASS = OOS n ≥ 100, mean R > 0 with day-block bootstrap 95 % lower bound > 0, PF ≥ 1.30, top-5 stocks < 50 % of profit, BH-FDR q < 0.10 among the selected). Sorted by VALID (never by OOS).

## 1. Best intraday (1680 variants; selected 0, PASS 0)

_no variant was positive in both DEV and VALID_

## 2. Best positional / swing (daily + weekly) (288 variants; selected 6, PASS 5)

| exp_id                                | status   |   n_all |   DEV_n |   DEV_avgR |   VALID_n |   VALID_avgR |   VALID_PF |   OOS_n |   OOS_win |   OOS_avgR |   OOS_grossR |   OOS_costR |   OOS_PF |   OOS_lo95 |   OOS_maxDD_R |   OOS_max_consec_loss |   OOS_hold |   OOS_per_day |   OOS_top5_share |   OOS_q |
|:--------------------------------------|:---------|--------:|--------:|-----------:|----------:|-------------:|-----------:|--------:|----------:|-----------:|-------------:|------------:|---------:|-----------:|--------------:|----------------------:|-----------:|--------------:|-----------------:|--------:|
| CQD-POSITIONAL-F2_RS_BO50_trail50-0R  | PASS     |    1544 |     299 |      0.312 |       313 |        0.128 |      1.240 |     932 |    34.100 |      0.242 |        0.276 |       0.034 |    1.450 |      0.078 |       104.700 |                    24 |     35.600 |         1.470 |            0.230 |   0.003 |
| CQD-POSITIONAL-F1_52wHigh_trail50-3R  | PASS     |    2843 |     408 |      0.217 |       533 |        0.093 |      1.190 |    1902 |    36.700 |      0.180 |        0.223 |       0.042 |    1.370 |      0.107 |       104.400 |                    29 |     27.700 |         2.030 |            0.090 |   0.000 |
| CQD-POSITIONAL-F1_52wHigh_trail50-0R  | PASS     |    2785 |     404 |      0.306 |       525 |        0.078 |      1.160 |    1856 |    36.600 |      0.340 |        0.382 |       0.043 |    1.710 |      0.226 |       111.300 |                    26 |     36.600 |         2.010 |            0.130 |   0.000 |
| CQD-POSITIONAL-F2_RS_BO50_trail50-3R  | FAIL_OOS |    1691 |     327 |      0.201 |       343 |        0.073 |      1.130 |    1021 |    34.100 |      0.071 |        0.105 |       0.034 |    1.130 |     -0.026 |        90.500 |                    23 |     27.600 |         1.520 |            0.110 |   0.049 |
| CQW-POSITIONAL-W1_donchian10_trend-0R | PASS     |    4436 |     838 |      0.208 |       857 |        0.045 |      1.120 |    2741 |    37.100 |      0.245 |        0.277 |       0.032 |    1.640 |      0.142 |       145.200 |                    38 |      9.800 |         8.260 |            0.080 |   0.000 |
| CQW-POSITIONAL-W5_pullback_EMA10-0R   | PASS     |    8945 |    1664 |      0.122 |      1726 |        0.029 |      1.110 |    5555 |    30.000 |      0.135 |        0.165 |       0.029 |    1.480 |      0.071 |       275.500 |                    41 |      7.000 |        15.740 |            0.080 |   0.000 |

## 3. Best divergence (228 variants; selected 0, PASS 0)

_no variant was positive in both DEV and VALID_

## 4. Best RSI reversal (302 variants; selected 0, PASS 0)

_no variant was positive in both DEV and VALID_

## 5. Best volume (30 variants; selected 0, PASS 0)

_no variant was positive in both DEV and VALID_

## 6. Best price action (638 variants; selected 0, PASS 0)

_no variant was positive in both DEV and VALID_

## 7. Best combined / confluence (742 variants; selected 0, PASS 0)

_no variant was positive in both DEV and VALID_

## 7b. Positional trend (28 variants; selected 6, PASS 5)

| exp_id                                | status   |   n_all |   DEV_n |   DEV_avgR |   VALID_n |   VALID_avgR |   VALID_PF |   OOS_n |   OOS_win |   OOS_avgR |   OOS_grossR |   OOS_costR |   OOS_PF |   OOS_lo95 |   OOS_maxDD_R |   OOS_max_consec_loss |   OOS_hold |   OOS_per_day |   OOS_top5_share |   OOS_q |
|:--------------------------------------|:---------|--------:|--------:|-----------:|----------:|-------------:|-----------:|--------:|----------:|-----------:|-------------:|------------:|---------:|-----------:|--------------:|----------------------:|-----------:|--------------:|-----------------:|--------:|
| CQD-POSITIONAL-F2_RS_BO50_trail50-0R  | PASS     |    1544 |     299 |      0.312 |       313 |        0.128 |      1.240 |     932 |    34.100 |      0.242 |        0.276 |       0.034 |    1.450 |      0.078 |       104.700 |                    24 |     35.600 |         1.470 |            0.230 |   0.003 |
| CQD-POSITIONAL-F1_52wHigh_trail50-3R  | PASS     |    2843 |     408 |      0.217 |       533 |        0.093 |      1.190 |    1902 |    36.700 |      0.180 |        0.223 |       0.042 |    1.370 |      0.107 |       104.400 |                    29 |     27.700 |         2.030 |            0.090 |   0.000 |
| CQD-POSITIONAL-F1_52wHigh_trail50-0R  | PASS     |    2785 |     404 |      0.306 |       525 |        0.078 |      1.160 |    1856 |    36.600 |      0.340 |        0.382 |       0.043 |    1.710 |      0.226 |       111.300 |                    26 |     36.600 |         2.010 |            0.130 |   0.000 |
| CQD-POSITIONAL-F2_RS_BO50_trail50-3R  | FAIL_OOS |    1691 |     327 |      0.201 |       343 |        0.073 |      1.130 |    1021 |    34.100 |      0.071 |        0.105 |       0.034 |    1.130 |     -0.026 |        90.500 |                    23 |     27.600 |         1.520 |            0.110 |   0.049 |
| CQW-POSITIONAL-W1_donchian10_trend-0R | PASS     |    4436 |     838 |      0.208 |       857 |        0.045 |      1.120 |    2741 |    37.100 |      0.245 |        0.277 |       0.032 |    1.640 |      0.142 |       145.200 |                    38 |      9.800 |         8.260 |            0.080 |   0.000 |
| CQW-POSITIONAL-W5_pullback_EMA10-0R   | PASS     |    8945 |    1664 |      0.122 |      1726 |        0.029 |      1.110 |    5555 |    30.000 |      0.135 |        0.165 |       0.029 |    1.480 |      0.071 |       275.500 |                    41 |      7.000 |        15.740 |            0.080 |   0.000 |

## 7c. F&O open interest (33 variants; selected 1, PASS 0)

| exp_id                                     | status   |   n_all |   DEV_n |   DEV_avgR |   VALID_n |   VALID_avgR |   VALID_PF |   OOS_n |   OOS_win |   OOS_avgR |   OOS_grossR |   OOS_costR |   OOS_PF |   OOS_lo95 |   OOS_maxDD_R |   OOS_max_consec_loss |   OOS_hold |   OOS_per_day |   OOS_top5_share |   OOS_q |
|:-------------------------------------------|:---------|--------:|--------:|-----------:|----------:|-------------:|-----------:|--------:|----------:|-----------:|-------------:|------------:|---------:|-----------:|--------------:|----------------------:|-----------:|--------------:|-----------------:|--------:|
| CQD-OPEN_INTEREST-OI_div_high_OIfalling-3R | FAIL_OOS |    7346 |    2576 |      0.005 |      1941 |        0.102 |      1.150 |    2829 |    30.200 |     -0.236 |       -0.132 |       0.104 |    0.700 |     -0.327 |       747.600 |                    53 |     10.300 |         6.990 |            0.200 |   1.000 |

## 8. Failed strategies – reasons

| engine                   | family        | status       |   variants |   mean_DEV_R |   mean_gross_R |   mean_cost_R |
|:-------------------------|:--------------|:-------------|-----------:|-------------:|---------------:|--------------:|
| F&O OI (daily)           | OPEN_INTEREST | FAIL_OOS     |          1 |        0.005 |          0.094 |         0.089 |
| F&O OI (daily)           | OPEN_INTEREST | NOT_SELECTED |         32 |       -0.052 |          0.030 |         0.082 |
| intraday                 | COMBINED      | NOT_SELECTED |        672 |       -0.164 |          0.038 |         0.203 |
| intraday                 | DIVERGENCE    | NOT_SELECTED |        168 |       -0.222 |          0.012 |         0.235 |
| intraday                 | PRICE_ACTION  | NOT_SELECTED |        588 |       -0.177 |          0.036 |         0.213 |
| intraday                 | RSI           | NOT_SELECTED |        252 |       -0.194 |          0.012 |         0.207 |
| positional (weekly)      | POSITIONAL    | NOT_SELECTED |         16 |        0.127 |          0.152 |         0.025 |
| positional (weekly)      | POSITIONAL    | PASS         |          2 |        0.165 |          0.193 |         0.028 |
| positional/swing (daily) | COMBINED      | NOT_SELECTED |         70 |       -0.077 |         -0.005 |         0.072 |
| positional/swing (daily) | DIVERGENCE    | NOT_SELECTED |         60 |        0.011 |          0.062 |         0.051 |
| positional/swing (daily) | POSITIONAL    | FAIL_OOS     |          1 |        0.201 |          0.237 |         0.035 |
| positional/swing (daily) | POSITIONAL    | NOT_SELECTED |          6 |        0.239 |          0.272 |         0.034 |
| positional/swing (daily) | POSITIONAL    | PASS         |          3 |        0.278 |          0.317 |         0.038 |
| positional/swing (daily) | PRICE_ACTION  | NOT_SELECTED |         50 |       -0.098 |         -0.021 |         0.076 |
| positional/swing (daily) | RSI           | NOT_SELECTED |         50 |       -0.100 |         -0.040 |         0.060 |
| positional/swing (daily) | VOLUME        | NOT_SELECTED |         30 |       -0.129 |         -0.055 |         0.074 |
