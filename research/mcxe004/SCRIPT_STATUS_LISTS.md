# Scripts not executed, failing or blocked

## Not executed (no committed output, schedule or log evidence) – 61

Some may have been run locally; this is not claimed.

| script_id | file | last_code_commit | summary |
|---|---|---|---|
| R-research.adapters.nse_bhavcopy | research/adapters/nse_bhavcopy.py | 2026-10-21 | NSE F&O end-of-day bhavcopy adapter (REAL exchange data, contract level). Downloads the official dai |
| R-research.adapters.nse_options | research/adapters/nse_options.py | 2026-10-29 | NSE F&O end-of-day bhavcopy -> OPTION prices (REAL exchange data, contract level) for option-buy bac |
| R-research.adapters.nse_stkfut_pit | research/adapters/nse_stkfut_pit.py | 2026-11-07 | MCXE-003: POINT-IN-TIME NSE stock + index futures, contract level, from the official F&O bhavcopy ar |
| R-research.angel_check | research/angel_check.py | 2026-10-21 | REAL MCX sanity check with Angel One contract candles (descriptive only - too short to grade). 1. Pr |
| R-research.audit_v2 | research/audit_v2.py | 2026-10-21 | Phase 1 audit of the v1 MCX_DAILY_REAL results (C and G). Does not modify v1 outputs. python -m rese |
| R-research.mcxe003.daily | research/mcxe003/daily.py | 2026-11-07 | MCXE-003 – daily-bar horizons: BTST / STBT (overnight) and positional, three markets, same detectors |
| R-research.mcxe003.run_discovery | research/mcxe003/run_discovery.py | 2026-11-07 | MCXE-003 stage 1 – event study over all families, intraday markets (pre-registered in PREREGISTRATIO |
| R-research.mcxe004.alert_examples | research/mcxe004/alert_examples.py | 2026-11-07 | Transparent alert cards (register.alert_card) for REAL signals the live bot sent on 5/6-Nov-2026 (al |
| R-research.mcxe004.blocked_cells | research/mcxe004/blocked_cells.py | 2026-11-07 | MCXE-004 – register every live / shadow strategy and every requested market cell that could NOT be e |
| R-research.mcxe004.inventory | research/mcxe004/inventory.py | 2026-11-07 | MCXE-004 script inventory (automatic, evidence-based). For every Python file under research/ (resear |
| R-research.mcxe004.report | research/mcxe004/report.py | 2026-11-07 | MCXE-004 report generator – every table is computed from the actual result files (register, e1_trade |
| R-research.mcxe004.windows | research/mcxe004/windows.py | 2026-11-07 | MCXE-004 – strict rolling 1-YEAR data windows (owner rule, 7-Nov-2026). Read-only. For every market  |
| R-research.program.bigmove_straddle | research/program/bigmove_straddle.py | 2026-10-29 |  |
| R-research.program.crude_v1 | research/program/crude_v1.py | 2026-11-03 | CRUDE-V1 (1-Nov-2026, owner: ChatGPT's "Crude Oil Research Model V1" – CVD/order flow, realized semi |
| R-research.program.eq_data | research/program/eq_data.py | 2026-11-06 | NSE cash-equity research data layer (6-Nov-2026, owner workstream "cash equity, 4-5 quality stocks a |
| R-research.program.mcx_dtc_controls | research/program/mcx_dtc_controls.py | 2026-11-06 | MCXD-005 – matched controls for the Gold/Silver day-trend continuation (shadow strategy), same stand |
| R-research.program.mcx_engine_trades | research/program/mcx_engine_trades.py | 2026-11-06 | Trade-level extraction for chosen MCXE configurations + matched RANDOM-entry control (same commodity |
| R-research.program.mcx_engine_v1 | research/program/mcx_engine_v1.py | 2026-11-06 | MCXE – MCX intraday STRATEGY ENGINE (research). One framework, many families (owner directive 6-Nov: |
| R-research.program.param_sweep | research/program/param_sweep.py | 2026-10-30 | PARAM-SWEEP-001 (30-Oct-2026, owner: "do this type of analysis yourself and find a way"): one-at-a-t |
| R-research.program.rollcheck | research/program/rollcheck.py | 2026-11-06 | ROLLCHECK-001 (6-Nov-2026): the 20-year MCX daily file is an UNADJUSTED front-month stitch with no c |
| R-research.program.rr1_rsi_analyse | research/program/rr1_rsi_analyse.py | 2026-10-28 |  |
| R-research.program.rsi75_mcx | research/program/rsi75_mcx.py | 2026-10-28 | RSI75-MCX (28-Oct-2026): owner's question – after RSI(14) rises above 75 (SELL idea), with volume su |
| R-research.program.rsix_final | research/program/rsix_final.py | 2026-11-06 | RSIX-001 finalist – trade-level report (daily BUY: RSI(7) touch <= L, bullish candle, ADX(14) < 20,  |
| R-research.program.rsix_nse | research/program/rsix_nse.py | 2026-11-06 | RSIX-001 transfer test to NSE – the MCX finalist applied UNCHANGED (no re-optimisation): RSI(7) touc |
| R-research.program.rsix_trail | research/program/rsix_trail.py | 2026-11-06 | RSIX-TRAIL-001 – independent check (plain-Python simulator written separately from rsix.sim) of the  |
| R-research.program.stkfut_cmp_15m | research/program/stkfut_cmp_15m.py | 2026-10-28 | STKFUT-CMP-001 – 15-minute check of the intraday setups at their native resolution (exploratory: onl |
| R-research.program.structx_live | research/program/structx_live.py | 2026-11-06 | STRUCTX-001 H1 on the LIVE rules with their exact parameters: next-open entry (production) vs stop a |
| R-research.program.tf1h_vol | research/program/tf1h_vol.py | 2026-10-30 | TF1H-VOL (30-Oct-2026, owner: "1-hour with volume 5×"): breakout family on 1h candles, volume > 3 /  |
| R-research.program.tf2h_vol | research/program/tf2h_vol.py | 2026-10-30 | TF2H-VOL (30-Oct-2026, owner: "2-hour candles with volume 3×"): breakout family on 2h candles, volum |
| R-research.program.tf5h | research/program/tf5h.py | 2026-10-30 | TF5H-001 (30-Oct-2026, owner: "5-hour candles – nobody uses them, try"). 5-hour futures candles from |
| R-research.program.tf5h_log | research/program/tf5h_log.py | 2026-10-30 | TF5H-LOG (30-Oct-2026): trade-by-trade log, last 3 months of data, for the owner's review page. Rule |
| R-research.program.tf_log2 | research/program/tf_log2.py | 2026-10-30 | TFLOG-002 (30-Oct-2026): 3-month trade logs for the proposed 4-hour rules vs the 5-hour rules and th |
| R-research.program.tf_log3 | research/program/tf_log3.py | 2026-10-30 | TFLOG-003 (30-Oct-2026): 3-month trade logs – 2-hour volume-3× rules vs the 4-hour rules and the liv |
| R-research.program.tf_log4 | research/program/tf_log4.py | 2026-10-30 | TFLOG-004 (30-Oct-2026): 3-month trade logs – 1-hour volume-5× rules vs the 4-hour rules and the liv |
| R-research.program.tf_nh | research/program/tf_nh.py | 2026-10-30 | TFNH-001 (30-Oct-2026, owner: "same settings for 4 hours?"): the TF5H-001 test on 2h / 4h / 5h / 6h  |
| R-research.program.touch | research/program/touch.py | 2026-11-01 | TOUCH-001 (30-Oct-2026, owner: "a 3h candle breaks out mid-candle and we only call at the close – we |
| R-research.search.candle_rev | research/search/candle_rev.py | 2026-10-28 | CANDLE-001 – see REGISTRY_CANDLE.md. python -m research.search.candle_rev |
| R-research.search.combo_search | research/search/combo_search.py | 2026-10-22 | STRAT-SEARCH-002 – combination grid + walk-forward selection (see REGISTRY_002.md). python -m resear |
| R-research.search.exit_test | research/search/exit_test.py | 2026-10-27 | EXIT-001 – see REGISTRY_EXIT.md. python -m research.search.exit_test |
| R-research.search.indicator_search | research/search/indicator_search.py | 2026-10-22 | STRAT-SEARCH-004 – volume & other indicator families (pre-registered in the docstring; research only |
| R-research.search.inst_patterns | research/search/inst_patterns.py | 2026-10-27 | INST-PAT-001 – see REGISTRY_INST.md. python -m research.search.inst_patterns |
| R-research.search.live_audit | research/search/live_audit.py | 2026-10-28 | LIVE-AUDIT-001 (28-Oct-2026): performance audit of every LIVE futures rule, in R, with the live exit |
| R-research.search.oos_validate | research/search/oos_validate.py | 2026-10-28 | OOS-VALIDATE-001 (28-Oct-2026): independent chronological validation of the LIVE futures rules. Why  |
| R-research.search.option_buy_search | research/search/option_buy_search.py | 2026-10-23 | OPT-BUY-001: can option BUYING win? Registered in REGISTRY_OPTBUY.md before running. Research only.  |
| R-research.search.pat2 | research/search/pat2.py | 2026-10-28 | PAT-002 – see REGISTRY_PAT2.md. python -m research.search.pat2 [MCXIDX/STOCKS] |
| R-research.search.rsi_sell | research/search/rsi_sell.py | 2026-10-27 | RSI-SELL-001 – see REGISTRY_RSISELL.md. python -m research.search.rsi_sell |
| R-research.search.single_target | research/search/single_target.py | 2026-10-27 | ONE-TARGET-001: one stop + one target (full exit), no trailing, vs the current live exits. Measured  |
| R-research.search.sr_levels | research/search/sr_levels.py | 2026-10-28 | SR-001 – see REGISTRY_SR.md. python -m research.search.sr_levels [MCXIDX/STOCKS] |
| R-research.search.stock_check | research/search/stock_check.py | 2026-10-22 | STOCK-CHECK-001 – the LIVE volume-breakout rule (alerts/breakout.py, unchanged) on NSE stock futures |
| R-research.search.stock_highwin | research/search/stock_highwin.py | 2026-10-22 | STOCK-HIGHWIN-001 – trial-and-error for 80-90% accuracy on stock futures (lot < 3000), daily candles |
| R-research.search.stock_oi_buy_run | research/search/stock_oi_buy_run.py | 2026-10-28 | Runs STOCK-OI-BUY-001 (see stock_oi_buy.py for the pre-declared candidates). python research/search/ |
| R-research.search.stock_oi_search | research/search/stock_oi_search.py | 2026-10-22 | STOCK-OI-001 – stock futures with VOLUME + OI + support/resistance + trend + RSI (pre-registered her |
| R-research.search.stock_patterns | research/search/stock_patterns.py | 2026-10-27 | STOCK-PAT-001 – see REGISTRY_STKPAT.md. |
| R-research.search.stock_search | research/search/stock_search.py | 2026-10-22 | STOCK-SEARCH-001 – see REGISTRY_STOCKS.md. python -m research.search.stock_search |
| R-research.search.strategy_search | research/search/strategy_search.py | 2026-10-22 | STRAT-SEARCH-001 – disciplined search for a strategy that survives costs and an untouched hold-out.  |
| R-research.search.trend_exit | research/search/trend_exit.py | 2026-10-27 | TREND-EXIT-001 – see REGISTRY_TREXIT.md. |
| R-research.search.vb_tune | research/search/vb_tune.py | 2026-10-22 | STRAT-SEARCH-005 – robustness / improvement grid around the volume breakout (3h + daily). Grid: chan |
| R-research.search.winrate_search | research/search/winrate_search.py | 2026-10-22 | STRAT-SEARCH-003 – can a combination reach 70-80% win rate AND still make money after costs on unsee |
| M-alerts.exp_filters | alerts/exp_filters.py | 2026-10-22 | ALERT-EXP-002 – which extra filter cuts fake RSI-reversal alerts? (research only) python -m alerts.e |
| M-crude.backtest | crude/backtest.py | 2026-10-21 | Backtest of the Crude Oil engines on REAL Angel One candles (research/data/angel, branch research-da |
| M-crude.probe | crude/probe.py | 2026-10-21 | Inspect what Angel One SmartAPI ACTUALLY returns for MCX Crude Oil futures (read-only market data).  |

## Failing (register FAILED / ERROR)

- 25 records superseded on 7-Nov: `window.period()` mislabelled DEV / VALID / OOS when the trade table had a non-0..n-1 index (caught by test_window_no_leakage; fixed; all strategies re-run). Kept in `register/executions_superseded_period_bug.jsonl`; **those OOS numbers must not be used**.
- 11 development-run failures on 7-Nov (all `KeyError` in `register.metrics` index alignment; fixed; every affected strategy re-ran COMPLETED). Records kept in `register/executions_devrun_7nov.jsonl`.
- Current failing executions: 0
- Live loop, 6-Nov run 42154958592 (alerts scans):
  - **1 FAILED** scan (exit 2; Angel login / instrument-list DataException at 14:20 IST; no alerts in that slot);
  - **1 BUDGET_EXHAUSTED** (14:02–14:19 IST: 35 of 67 API calls refused, 186 skipped);
  - **22 RATE_LIMITED** of 60 scans.

## Blocked / insufficient data (register)

- INSUFFICIENT_DATA: **RB_MCX_4h_EMA1348_BUY** – OOS 9 trades / 8 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
- INSUFFICIENT_DATA: **RB_MCX_4h_MACD0_BUY** – OOS 14 trades / 10 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
- INSUFFICIENT_DATA: **RB_MCX_1d_RETEST_BUY** – OOS 0 trades / 0 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
- INSUFFICIENT_DATA: **RB_STK_1d_RSI80_BUY** – OOS 0 trades / 0 dates < required 20 / 15 | stock universe = today's F&O list (survivorship)
- INSUFFICIENT_DATA: **BO_MCX_1d_BUY** – OOS 0 trades / 0 dates < required 20 / 15 | MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)
- BLOCKED: **cash-mom-1.2 monthly relative-strength portfolio (LIVE, BUY-only)** – the rule ranks stocks on 12-1 month returns and a 100-day market MA: its first signal needs 12 months of history, i.e. data older than the 1-year window -> cannot be evaluated without breaking the rule
- BLOCKED: **S4 stock-futures OI breakout BUY / SELL (LIVE)** – no research-parity implementation of the live S4 rule exists in research code (it lives only in alerts/stocks.py); evaluating it needs a parity port first – NOT evaluated, not failed
- BLOCKED: **S5 stock-futures bearish engulfing SELL (LIVE)** – same as S4: no research-parity code; NOT evaluated
- BLOCKED: **candle setups: MCX daily hammer BUY / stock daily hanging-man SELL (LIVE)** – no research-parity code for the live candle_setups module; NOT evaluated
- BLOCKED: **stock 4h SELL (Bollinger squeeze / MACD-zero, LIVE)** – research code (stk_anchor.py) uses day-anchored 4h candles from the same Angel 1h files; not yet wired to the window harness – NOT evaluated
- BLOCKED: **index futures rules (NIFTY / BANKNIFTY daily, 3h; LIVE)** – index futures are outside the MCXE-004 market list (MCX, NSE cash, NSE stock futures) – listed for visibility
- BLOCKED: **option selling engine (LIVE)** – no historical option premiums inside the window -> no backtest possible; only the live record exists
- BLOCKED: **option buying engine (OFF since 4-Nov via config.OBUY_ENABLED)** – engine disabled in config; one month of real premiums (Sep-Oct 2026) only
- BLOCKED: **NSE cash intraday – any live strategy** – no live or shadow strategy exists for NSE cash intraday (owner rule: cash is BUY-only; research found nothing) -> nothing to evaluate
- BLOCKED: **NSE futures BTST / STBT – any live strategy** – no live or shadow overnight (BTST/STBT) strategy exists -> nothing to evaluate
- BLOCKED: **NSE cash BTST – any live strategy** – no live or shadow BTST strategy exists -> nothing to evaluate; STBT in cash is not permitted (no overnight cash short)