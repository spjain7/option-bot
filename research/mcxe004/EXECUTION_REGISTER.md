# MCXE-004 research execution register

- Source: `register/executions.jsonl`, append-only, one JSON line per execution, with every required field.
- CSV copy: `register/executions.csv`.
- **win_rate / expectancy / profit factor are OOS values** (the last 3 months of the window). Per-period values are in
  `results/e1_records.json` and in RESULTS_BY_SCRIPT.md.
- Missing values are blank (null), never estimated.
- Records: 25, of which the latest per strategy: 25.
- Earlier failed development runs (an index bug in `metrics`, caught by the register as FAILED/ERROR) are kept in
  `register/executions_devrun_7nov.jsonl`.
- Historical (pre-register) research executions: `register/historical_backfill.jsonl`. They are COMPLETED with
  RESEARCH_ONLY status and null metrics, because they were never recorded at the time.

| experiment_id | script_id | strategy_name | market | timeframe | data_start_date | data_end_date | status | validation_status | total_signals | executed_backtest_trades | rejected_signals | win_rate | net_expectancy_R | profit_factor | code_commit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MCXE004-E1-5459c02d | MCXE004-E1 | RB_MCX_4h_EMA1348_BUY | MCX | 4h | 2025-11-04 | 2026-10-21 | INSUFFICIENT_DATA | INSUFFICIENT_DATA | 35.000 | 24.000 | 11.000 | 44.400 | 0.842 | 3.012 | 147f71c |
| MCXE004-E1-fa0b949a | MCXE004-E1 | RB_MCX_4h_MACD0_BUY | MCX | 4h | 2025-11-04 | 2026-10-21 | INSUFFICIENT_DATA | INSUFFICIENT_DATA | 48.000 | 44.000 | 4.000 | 42.900 | 0.148 | 1.267 | 147f71c |
| MCXE004-E1-3ff1e184 | MCXE004-E1 | RB_MCX_2h_MOMO_BUY | MCX | 2h | 2025-11-04 | 2026-10-21 | COMPLETED | REJECTED | 77.000 | 60.000 | 17.000 | 50.000 | 0.452 | 1.819 | 147f71c |
| MCXE004-E1-b4d67e62 | MCXE004-E1 | RB_MCX_2h_EMA921_BUY | MCX | 2h | 2025-11-04 | 2026-10-21 | COMPLETED | REJECTED | 133.000 | 79.000 | 54.000 | 36.400 | -0.041 | 0.932 | 147f71c |
| MCXE004-E1-6d27725e | MCXE004-E1 | RB_MCX_1d_RETEST_BUY | MCX | 1d | 2025-11-04 | 2026-11-03 | INSUFFICIENT_DATA | INSUFFICIENT_DATA | 0.000 | 0.000 | 0.000 | — | — | — | 147f71c |
| MCXE004-E1-0315c17f | MCXE004-E1 | RB_MCX_1h_MACD_BUY | MCX | 1h | 2025-11-04 | 2026-10-21 | COMPLETED | REJECTED | 302.000 | 154.000 | 148.000 | 41.900 | 0.117 | 1.192 | 147f71c |
| MCXE004-E1-a855a0e4 | MCXE004-E1 | RB_STK_3h_MACD0_SELL | NSE_FUT | 3h | 2025-10-23 | 2026-10-22 | COMPLETED | PAPER_ONLY | 296.000 | 242.000 | 54.000 | 51.900 | 0.292 | 1.726 | 147f71c |
| MCXE004-E1-e2f7a468 | MCXE004-E1 | RB_STK_3h_EMA921_SELL | NSE_FUT | 3h | 2025-10-23 | 2026-10-22 | COMPLETED | PAPER_ONLY | 379.000 | 290.000 | 89.000 | 56.400 | 0.274 | 1.883 | 147f71c |
| MCXE004-E1-34bb2964 | MCXE004-E1 | RB_STK_1d_RSI80_BUY | NSE_FUT | 1d | 2025-10-23 | 2026-10-22 | INSUFFICIENT_DATA | INSUFFICIENT_DATA | 0.000 | 0.000 | 0.000 | — | — | — | 147f71c |
| MCXE004-E1-ff685670 | MCXE004-E1 | BO_MCX_3h_BUY | MCX | 3h | 2025-11-04 | 2026-10-21 | COMPLETED | REJECTED | 243.000 | 102.000 | 141.000 | 40.000 | 0.092 | 1.153 | 147f71c |
| MCXE004-E1-5696ff18 | MCXE004-E1 | FH_MCX_4h_BUY | MCX | 4h | 2025-11-04 | 2026-10-21 | COMPLETED | REJECTED | 145.000 | 56.000 | 89.000 | 40.000 | 0.125 | 1.228 | 147f71c |
| MCXE004-E1-736e40ff | MCXE004-E1 | BO_MCX_1d_BUY | MCX | 1d | 2025-11-04 | 2026-11-03 | INSUFFICIENT_DATA | INSUFFICIENT_DATA | 0.000 | 0.000 | 0.000 | — | — | — | 147f71c |
| MCXE004-E1-7b988eb1 | MCXE004-E1 | FH_STK_3h_SELL | NSE_FUT | 3h | 2025-10-23 | 2026-10-22 | COMPLETED | REJECTED | 586.000 | 380.000 | 206.000 | 51.800 | 0.250 | 1.851 | 147f71c |
| MCXE004-E1-b12d4167 | MCXE004-E1 | SHADOW_MCX_DTC_GOLD_SILVER | MCX | 15m checkpoints 13:00/17:00 | 2025-11-04 | 2026-11-03 | COMPLETED | REJECTED | 158.000 | 158.000 | 0.000 | 50.000 | 0.297 | 2.176 | 147f71c |
| M-cashstock.run-b0c7359e | M-cashstock.run | cash-mom-1.2 monthly relative-strength portfolio (LIVE, BUY-only) | NSE_EQ | monthly | 2025-11-06 | 2026-11-05 | BLOCKED | BLOCKED | — | — | — | — | — | — | 147f71c |
| M-alerts.stocks-053d3a0a | M-alerts.stocks | S4 stock-futures OI breakout BUY / SELL (LIVE) | NSE_FUT | 1d | 2025-11-07 | 2026-11-06 | BLOCKED | BLOCKED | — | — | — | — | — | — | 147f71c |
| M-alerts.stocks-858da15d | M-alerts.stocks | S5 stock-futures bearish engulfing SELL (LIVE) | NSE_FUT | 1d | 2025-11-07 | 2026-11-06 | BLOCKED | BLOCKED | — | — | — | — | — | — | 147f71c |
| M-alerts.candle_setups-fc66cff4 | M-alerts.candle_setups | candle setups: MCX daily hammer BUY / stock daily hanging-man SELL (LIVE) | MCX+NSE_FUT | 1d | 2025-11-04 | 2026-11-03 | BLOCKED | BLOCKED | — | — | — | — | — | — | 147f71c |
| M-alerts.four_hour-118340d0 | M-alerts.four_hour | stock 4h SELL (Bollinger squeeze / MACD-zero, LIVE) | NSE_FUT | 4h | 2025-10-23 | 2026-10-22 | BLOCKED | BLOCKED | — | — | — | — | — | — | 147f71c |
| M-alerts.engine-8326d3b4 | M-alerts.engine | index futures rules (NIFTY / BANKNIFTY daily, 3h; LIVE) | INDEX | 3h/1d | 2025-11-07 | 2026-11-06 | BLOCKED | BLOCKED | — | — | — | — | — | — | 147f71c |
| M-runner-04a7c06c | M-runner | option selling engine (LIVE) | OPTIONS | intraday/positional | 2025-11-07 | 2026-11-06 | BLOCKED | BLOCKED | — | — | — | — | — | — | 147f71c |
| M-obuy.run-0f780536 | M-obuy.run | option buying engine (OFF since 4-Nov via config.OBUY_ENABLED) | OPTIONS | intraday | 2025-11-07 | 2026-11-06 | BLOCKED | BLOCKED | — | — | — | — | — | — | 147f71c |
| R-mcxe004-28e0b73b | R-mcxe004 | NSE cash intraday – any live strategy | NSE_EQ | 5m-60m | 2025-11-07 | 2026-11-06 | BLOCKED | BLOCKED | — | — | — | — | — | — | 147f71c |
| R-mcxe004-64f952f2 | R-mcxe004 | NSE futures BTST / STBT – any live strategy | NSE_FUT | overnight | 2025-11-07 | 2026-11-06 | BLOCKED | BLOCKED | — | — | — | — | — | — | 147f71c |
| R-mcxe004-8c6c8892 | R-mcxe004 | NSE cash BTST – any live strategy | NSE_EQ | overnight | 2025-11-06 | 2026-11-05 | BLOCKED | BLOCKED | — | — | — | — | — | — | 147f71c |

## Conclusions / reasons (latest record per strategy)

- **RB_MCX_4h_EMA1348_BUY** (MCXE004-E1) – INSUFFICIENT_DATA / INSUFFICIENT_DATA: OOS 9 trades / 8 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
  - rejected signals: skipped: position already open / switch day / warm-up edge: 8; next open beyond the 0.5-ATR entry zone: 3
- **RB_MCX_4h_MACD0_BUY** (MCXE004-E1) – INSUFFICIENT_DATA / INSUFFICIENT_DATA: OOS 14 trades / 10 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
  - rejected signals: skipped: position already open / switch day / warm-up edge: 1; next open beyond the 0.5-ATR entry zone: 3
- **RB_MCX_2h_MOMO_BUY** (MCXE004-E1) – COMPLETED / REJECTED: OOS 95% CI lower bound -0.504 not > 0 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
  - rejected signals: skipped: position already open / switch day / warm-up edge: 16; next open beyond the 0.5-ATR entry zone: 1
- **RB_MCX_2h_EMA921_BUY** (MCXE004-E1) – COMPLETED / REJECTED: OOS expectancy <= 0 at 1x cost; OOS expectancy <= 0 at 2x cost; OOS 95% CI lower bound -0.687 not > 0 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
  - rejected signals: next open beyond the 0.5-ATR entry zone: 6; skipped: position already open / switch day / warm-up edge: 48
- **RB_MCX_1d_RETEST_BUY** (MCXE004-E1) – INSUFFICIENT_DATA / INSUFFICIENT_DATA: OOS 0 trades / 0 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
- **RB_MCX_1h_MACD_BUY** (MCXE004-E1) – COMPLETED / REJECTED: OOS 95% CI lower bound -0.41 not > 0 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
  - rejected signals: skipped: position already open / switch day / warm-up edge: 142; next open beyond the 0.5-ATR entry zone: 6
- **RB_STK_3h_MACD0_SELL** (MCXE004-E1) – COMPLETED / PAPER_ONLY: passes OOS checks, but the rule was selected on data that includes this window – forward paper test only | stock universe = today's F&O list (survivorship)
  - rejected signals: skipped: position already open / switch day / warm-up edge: 24; next open beyond the 0.5-ATR entry zone: 30
- **RB_STK_3h_EMA921_SELL** (MCXE004-E1) – COMPLETED / PAPER_ONLY: passes OOS checks, but the rule was selected on data that includes this window – forward paper test only | stock universe = today's F&O list (survivorship)
  - rejected signals: skipped: position already open / switch day / warm-up edge: 48; next open beyond the 0.5-ATR entry zone: 41
- **RB_STK_1d_RSI80_BUY** (MCXE004-E1) – INSUFFICIENT_DATA / INSUFFICIENT_DATA: OOS 0 trades / 0 dates < required 20 / 15 | stock universe = today's F&O list (survivorship)
- **BO_MCX_3h_BUY** (MCXE004-E1) – COMPLETED / REJECTED: OOS 95% CI lower bound -0.367 not > 0 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
  - rejected signals: skipped: position already open / switch day / warm-up edge: 135; next open beyond the 0.5-ATR entry zone: 6
- **FH_MCX_4h_BUY** (MCXE004-E1) – COMPLETED / REJECTED: OOS 95% CI lower bound -0.538 not > 0 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
  - rejected signals: skipped: position already open / switch day / warm-up edge: 87; next open beyond the 0.5-ATR entry zone: 2
- **BO_MCX_1d_BUY** (MCXE004-E1) – INSUFFICIENT_DATA / INSUFFICIENT_DATA: OOS 0 trades / 0 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
- **FH_STK_3h_SELL** (MCXE004-E1) – COMPLETED / REJECTED: OOS 95% CI lower bound -0.126 not > 0 | stock universe = today's F&O list (survivorship)
  - rejected signals: skipped: position already open / switch day / warm-up edge: 187; next open beyond the 0.5-ATR entry zone: 19
- **SHADOW_MCX_DTC_GOLD_SILVER** (MCXE004-E1) – COMPLETED / REJECTED: OOS 95% CI lower bound -0.276 not > 0 | shadow rule (never sent); window info {"GOLD": {"sessions": 257, "first": "2025-11-04", "last": "2026-11-03", "warmup_until": "2025-11-25"}, "SILVER": {"sessions": 258, "first": "2025-11-04", "last": "2026-11-03", "warmup_until": "2025-11-25"}}; signal = trade (no entry filters in this rule)
- **cash-mom-1.2 monthly relative-strength portfolio (LIVE, BUY-only)** (M-cashstock.run) – BLOCKED / BLOCKED: the rule ranks stocks on 12-1 month returns and a 100-day market MA: its first signal needs 12 months of history, i.e. data older than the 1-year window -> cannot be evaluated without breaking the rule
- **S4 stock-futures OI breakout BUY / SELL (LIVE)** (M-alerts.stocks) – BLOCKED / BLOCKED: no research-parity implementation of the live S4 rule exists in research code (it lives only in alerts/stocks.py); evaluating it needs a parity port first – NOT evaluated, not failed
- **S5 stock-futures bearish engulfing SELL (LIVE)** (M-alerts.stocks) – BLOCKED / BLOCKED: same as S4: no research-parity code; NOT evaluated
- **candle setups: MCX daily hammer BUY / stock daily hanging-man SELL (LIVE)** (M-alerts.candle_setups) – BLOCKED / BLOCKED: no research-parity code for the live candle_setups module; NOT evaluated
- **stock 4h SELL (Bollinger squeeze / MACD-zero, LIVE)** (M-alerts.four_hour) – BLOCKED / BLOCKED: research code (stk_anchor.py) uses day-anchored 4h candles from the same Angel 1h files; not yet wired to the window harness – NOT evaluated
- **index futures rules (NIFTY / BANKNIFTY daily, 3h; LIVE)** (M-alerts.engine) – BLOCKED / BLOCKED: index futures are outside the MCXE-004 market list (MCX, NSE cash, NSE stock futures) – listed for visibility
- **option selling engine (LIVE)** (M-runner) – BLOCKED / BLOCKED: no historical option premiums inside the window -> no backtest possible; only the live record exists
- **option buying engine (OFF since 4-Nov via config.OBUY_ENABLED)** (M-obuy.run) – BLOCKED / BLOCKED: engine disabled in config; one month of real premiums (Sep-Oct 2026) only
- **NSE cash intraday – any live strategy** (R-mcxe004) – BLOCKED / BLOCKED: no live or shadow strategy exists for NSE cash intraday (owner rule: cash is BUY-only; research found nothing) -> nothing to evaluate
- **NSE futures BTST / STBT – any live strategy** (R-mcxe004) – BLOCKED / BLOCKED: no live or shadow overnight (BTST/STBT) strategy exists -> nothing to evaluate
- **NSE cash BTST – any live strategy** (R-mcxe004) – BLOCKED / BLOCKED: no live or shadow BTST strategy exists -> nothing to evaluate; STBT in cash is not permitted (no overnight cash short)