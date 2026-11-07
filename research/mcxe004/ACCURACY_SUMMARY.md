# MCXE-004 accuracy and profitability summary

- **Accuracy** = the share of trades with net R > 0 after realistic costs. It is always shown with the number of
  trades, the number of unique dates and the 95 % CI of expectancy (day-block bootstrap + cluster t, widest).
- In-sample (DEV), validation (VALID), out-of-sample (OOS) and forward live results are **never combined**.
- Scripts that only produce signals or statistics (no trade outcomes) are listed as SIGNAL-ONLY, with no accuracy.

## OOS (last 3 months of the window) – live / shadow rules with research code

| strategy | market | status | OOS trades | dates | wins | win % | expectancy R (1×) | expectancy R (2×) | PF | max DD R | 95% CI | DEV exp R (n) | VALID exp R (n) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RB_MCX_4h_EMA1348_BUY | MCX | INSUFFICIENT_DATA | 9 | 8 | 4 | 44.4 | 0.842 | 0.802 | 3.01 | 2.0 | [-0.853, 2.537] | -0.349 (8) | 0.820 (7) |
| RB_MCX_4h_MACD0_BUY | MCX | INSUFFICIENT_DATA | 14 | 10 | 6 | 42.9 | 0.148 | 0.074 | 1.27 | 3.1 | [-0.619, 0.934] | 0.506 (15) | -0.079 (15) |
| RB_MCX_2h_MOMO_BUY | MCX | REJECTED | 20 | 15 | 10 | 50.0 | 0.452 | 0.389 | 1.82 | 3.6 | [-0.504, 1.407] | 0.010 (22) | 0.584 (18) |
| RB_MCX_2h_EMA921_BUY | MCX | REJECTED | 22 | 17 | 8 | 36.4 | -0.041 | -0.084 | 0.93 | 8.3 | [-0.687, 0.605] | 0.328 (34) | -0.029 (23) |
| RB_MCX_1d_RETEST_BUY | MCX | INSUFFICIENT_DATA | 0 | 0 | 0 | — | — | — | — | — | — | — (0) | — (0) |
| RB_MCX_1h_MACD_BUY | MCX | REJECTED | 43 | 29 | 18 | 41.9 | 0.117 | 0.055 | 1.19 | 9.2 | [-0.41, 0.657] | 0.196 (71) | 0.031 (40) |
| RB_STK_3h_MACD0_SELL | NSE_FUT | PAPER_ONLY | 108 | 44 | 56 | 51.9 | 0.292 | 0.251 | 1.73 | 3.1 | [0.02, 0.598] | 0.337 (5) | -0.154 (129) |
| RB_STK_3h_EMA921_SELL | NSE_FUT | PAPER_ONLY | 133 | 51 | 75 | 56.4 | 0.274 | 0.244 | 1.88 | 4.3 | [0.07, 0.523] | -0.014 (13) | -0.195 (144) |
| RB_STK_1d_RSI80_BUY | NSE_FUT | INSUFFICIENT_DATA | 0 | 0 | 0 | — | — | — | — | — | — | — (0) | — (0) |
| BO_MCX_3h_BUY | MCX | REJECTED | 35 | 26 | 14 | 40.0 | 0.092 | 0.045 | 1.15 | 5.8 | [-0.367, 0.551] | 0.105 (45) | 0.729 (22) |
| FH_MCX_4h_BUY | MCX | REJECTED | 20 | 15 | 8 | 40.0 | 0.125 | 0.082 | 1.23 | 6.5 | [-0.538, 0.789] | 0.260 (22) | 0.730 (14) |
| BO_MCX_1d_BUY | MCX | INSUFFICIENT_DATA | 0 | 0 | 0 | — | — | — | — | — | — | — (0) | — (0) |
| FH_STK_3h_SELL | NSE_FUT | REJECTED | 253 | 47 | 131 | 51.8 | 0.250 | 0.210 | 1.85 | 5.5 | [-0.126, 0.695] | 0.836 (14) | -0.206 (113) |
| SHADOW_MCX_DTC_GOLD_SILVER | MCX | REJECTED | 48 | 20 | 24 | 50.0 | 0.297 | 0.278 | 2.18 | 2.9 | [-0.276, 0.87] | 0.100 (85) | 0.161 (25) |

## Not evaluable inside the window (BLOCKED – exact reasons)

- **cash-mom-1.2 monthly relative-strength portfolio (LIVE, BUY-only)** (NSE_EQ): the rule ranks stocks on 12-1 month returns and a 100-day market MA: its first signal needs 12 months of history, i.e. data older than the 1-year window -> cannot be evaluated without breaking the rule
- **S4 stock-futures OI breakout BUY / SELL (LIVE)** (NSE_FUT): no research-parity implementation of the live S4 rule exists in research code (it lives only in alerts/stocks.py); evaluating it needs a parity port first – NOT evaluated, not failed
- **S5 stock-futures bearish engulfing SELL (LIVE)** (NSE_FUT): same as S4: no research-parity code; NOT evaluated
- **candle setups: MCX daily hammer BUY / stock daily hanging-man SELL (LIVE)** (MCX+NSE_FUT): no research-parity code for the live candle_setups module; NOT evaluated
- **stock 4h SELL (Bollinger squeeze / MACD-zero, LIVE)** (NSE_FUT): research code (stk_anchor.py) uses day-anchored 4h candles from the same Angel 1h files; not yet wired to the window harness – NOT evaluated
- **index futures rules (NIFTY / BANKNIFTY daily, 3h; LIVE)** (INDEX): index futures are outside the MCXE-004 market list (MCX, NSE cash, NSE stock futures) – listed for visibility
- **option selling engine (LIVE)** (OPTIONS): no historical option premiums inside the window -> no backtest possible; only the live record exists
- **option buying engine (OFF since 4-Nov via config.OBUY_ENABLED)** (OPTIONS): engine disabled in config; one month of real premiums (Sep-Oct 2026) only
- **NSE cash intraday – any live strategy** (NSE_EQ): no live or shadow strategy exists for NSE cash intraday (owner rule: cash is BUY-only; research found nothing) -> nothing to evaluate
- **NSE futures BTST / STBT – any live strategy** (NSE_FUT): no live or shadow overnight (BTST/STBT) strategy exists -> nothing to evaluate
- **NSE cash BTST – any live strategy** (NSE_EQ): no live or shadow BTST strategy exists -> nothing to evaluate; STBT in cash is not permitted (no overnight cash short)

## Forward live record (alerts actually sent; `alerts-state` ledger, 28-Oct → 6-Nov-2026)

- Calls in the ledger: 24; closed: 16.
  - withdrawn or cancelled before an outcome: 10;
  - **with a real outcome: 6** (wins 2, losses 4,
    gross R sum -0.00, before costs).
- **INSUFFICIENT DATA:** 6 outcomes cannot support any accuracy statement.
- The live calls show *backtest* statistics from 2006-26 / 2022-26 (rulebook tier text). Under the 1-year rule those
  are **not current evidence**.

## SIGNAL-ONLY / statistics-only scripts (no trade-level accuracy is computed)

- MCXE-003 stage 1 (`run_discovery.py`, `daily.py`, `stage1.py`): event studies; information in ATR vs controls, not
  trades. Results are pre-window, so they are idea sources only.
- `research/program/` studies whose committed outputs are summaries only (see SCRIPT_INVENTORY.md, column "produces").

## Bottom line (computed from the records above)

- Status counts across 14 evaluated rules: REJECTED 7, INSUFFICIENT_DATA 5, PAPER_ONLY 2; plus 11 BLOCKED cells.
- 9 rules have enough OOS trades. 8 of them have a positive OOS point estimate, but only 2 also have a 95 % CI above zero.
- **VALIDATED_CANDIDATE: 0.**
- **PAPER_ONLY: RB_STK_3h_MACD0_SELL** – OOS 108 trades on 44 dates, 52 % profitable, expectancy +0.29R (2×: +0.25R), CI [0.02, 0.598].
  - Not independent evidence: the rule was selected on 2022-26 data that includes this window.
  - The stock universe is today's F&O list (survivorship).
  - So it is a forward paper-tracking candidate, not proof of an edge. It is already live.
- **PAPER_ONLY: RB_STK_3h_EMA921_SELL** – OOS 133 trades on 51 dates, 56 % profitable, expectancy +0.27R (2×: +0.24R), CI [0.07, 0.523].
  - Not independent evidence: the rule was selected on 2022-26 data that includes this window.
  - The stock universe is today's F&O list (survivorship).
  - So it is a forward paper-tracking candidate, not proof of an edge. It is already live.
- Daily rules: no OOS trades, because warm-up inside a 1-year window consumes the daily bars (INSUFFICIENT_DATA).