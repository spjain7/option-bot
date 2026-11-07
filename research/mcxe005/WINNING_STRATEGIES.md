# MCXE-005 winning strategies

**None.** No strategy met the pre-registered OOS acceptance bar inside the approved one-year windows.

Closest results (OOS read once; all REJECTED because the conservative 95 % CI includes 0):

### A_MACD_ZERO SELL + adx20 · exit X2 · NSE stock futures · daily · positional

- **Logic:** daily close on point-in-time front-month futures; the MACD(12,26) crosses below 0 and ADX(14) ≥ 20 → SELL.
- **Entry and exit:** entry at the next open. Stop 1.5 ATR; 2.5-ATR trailing stop; max 20 sessions. No holding across a roll.
- **OOS:** 51 trades on 28 dates · win 62.7% · expectancy +0.401R (2×: +0.359R) ·
  PF 2.425 · max DD 3.43R · CI [-0.1, 0.915].
- **Matched all-signal SELL baseline:** +0.216R.
- **Status: REJECTED.** OOS 95% CI lower bound -0.1 not > 0
- **Limitations:** 3-month OOS; a falling-market period for stocks; 51 trades on fewer than 30 dates.
- **Eligible for paper testing?** Not under the pre-registered rule. At most a watch-list item for forward
  logging.

### A_MACD_ZERO SELL + adx20 · exit X1 · NSE stock futures · daily · positional

- **Logic:** daily close on point-in-time front-month futures; the MACD(12,26) crosses below 0 and ADX(14) ≥ 20 → SELL.
- **Entry and exit:** entry at the next open. Stop 2 ATR; target 3R; max 20 sessions. No holding across a roll.
- **OOS:** 51 trades on 28 dates · win 70.6% · expectancy +0.344R (2×: +0.313R) ·
  PF 2.815 · max DD 2.06R · CI [-0.025, 0.669].
- **Matched all-signal SELL baseline:** +0.229R.
- **Status: REJECTED.** OOS 95% CI lower bound -0.025 not > 0
- **Limitations:** 3-month OOS; a falling-market period for stocks; 51 trades on fewer than 30 dates.
- **Eligible for paper testing?** Not under the pre-registered rule. At most a watch-list item for forward
  logging.

### A_EMA50_SLOPE SELL + adx20 · exit X2 · NSE stock futures · daily · positional

- **Logic:** daily close on point-in-time front-month futures; the EMA50 slope (EMA50 − EMA50 five bars ago) crosses below 0 and ADX(14) ≥ 20 → SELL.
- **Entry and exit:** entry at the next open. Stop 1.5 ATR; 2.5-ATR trailing stop; max 20 sessions. No holding across a roll.
- **OOS:** 51 trades on 27 dates · win 49.0% · expectancy +0.171R (2×: +0.129R) ·
  PF 1.455 · max DD 5.59R · CI [-0.16, 0.502].
- **Matched all-signal SELL baseline:** +0.316R.
- **Status: REJECTED.** OOS 95% CI lower bound -0.16 not > 0
- **Limitations:** 3-month OOS; a falling-market period for stocks; 51 trades on fewer than 30 dates.
- **Eligible for paper testing?** Not under the pre-registered rule. At most a watch-list item for forward
  logging.

### A_EMA50_SLOPE SELL + adx20 · exit X1 · NSE stock futures · daily · positional

- **Logic:** daily close on point-in-time front-month futures; the EMA50 slope (EMA50 − EMA50 five bars ago) crosses below 0 and ADX(14) ≥ 20 → SELL.
- **Entry and exit:** entry at the next open. Stop 2 ATR; target 3R; max 20 sessions. No holding across a roll.
- **OOS:** 51 trades on 27 dates · win 52.9% · expectancy +0.145R (2×: +0.114R) ·
  PF 1.477 · max DD 5.21R · CI [-0.104, 0.394].
- **Matched all-signal SELL baseline:** +0.317R.
- **Status: REJECTED.** OOS 95% CI lower bound -0.104 not > 0
- **Limitations:** 3-month OOS; a falling-market period for stocks; 51 trades on fewer than 30 dates.
- **Eligible for paper testing?** Not under the pre-registered rule. At most a watch-list item for forward
  logging.

**Not advertised:** no accuracy figure in this research supports claims like "80–90 % accurate". The highest OOS
win % among the evaluated cells (≈ 71 %) comes with a CI that includes 0 expectancy, on 51 trades.