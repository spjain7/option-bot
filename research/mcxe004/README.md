# MCXE-004: script-wise research visibility and alert audit (7-Nov-2026)

Research only. No production, broker, Telegram, alert or shadow setting was changed.
- Data: only the approved 1-year windows (`PROTOCOL.md`, `windows.json`) with their DEV / VALID / OOS split.
- Results reproduce at code commit **147f71c**; every register record carries its commit.

## The four questions
**1. Which scripts ran?** See `SCRIPT_INVENTORY.md` (227 files; generated from evidence, not from file existence).
- **Research branch:** 78 executed (output committed); 56 defined only (no committed output, schedule or log evidence);
  38 libraries; 6 scheduled data adapters.
- **Live code on `main`:** 10 seen running in the 6-Nov market-loop log; 31 live-loop components; 2 scheduled; 3 defined
  only.
- **This work:** `eval_live_rules.py` (E1) and `blocked_cells.py` produced 25 register records (`EXECUTION_REGISTER.md`).

**2. What did each find?**
- `RESULTS_BY_SCRIPT.md` gives per rule: DEV / VALID / OOS at 1× and 2× costs, per instrument, BUY / SELL, holding period
  and timeframe.
- `ACCURACY_SUMMARY.md` gives the OOS table.
- `register/historical_backfill.jsonl` lists the 79 earlier research runs. They are RESEARCH_ONLY and not current evidence.

**3. Which strategies have credible accuracy and profitability evidence? None that qualifies as VALIDATED_CANDIDATE.**

| Status | Rules | Detail |
|---|---|---|
| PAPER_ONLY | 2 (both already live) | **Stock 3h MACD-zero SELL:** OOS 108 trades / 44 dates, 52 % profitable, +0.29R (2×: +0.25R), CI +0.02 … +0.60.<br>**Stock 3h EMA 9/21 SELL:** OOS 133 / 51 dates, 56 %, +0.27R (2×: +0.24R), CI +0.07 … +0.52.<br>Both were selected on 2022-26 data that includes this window, and the universe is today's F&O list. Their VALID period was negative (−0.15R, −0.19R), so they are forward paper-tracking candidates only. |
| REJECTED | 7 | OOS CI includes 0, e.g. MCX day-trend shadow: OOS 48 trades, +0.30R, CI −0.28 … +0.87 |
| INSUFFICIENT_DATA | 5 | Daily rules lose their bars to warm-up inside a 1-year window; two MCX 4h rules have fewer than 20 OOS trades |
| BLOCKED | 11 | Exact reasons in the register:<br>– cash momentum needs 12 months of history;<br>– no research-parity code for S4 / S5 / candle setups / stock 4h;<br>– no option premium history;<br>– no live strategy for cash intraday, cash BTST or futures BTST/STBT. |

Forward live record: 6 calls with real outcomes since 28-Oct (2 target, 4 stop). INSUFFICIENT DATA.

**4. Why are alerts not arriving?** See `ROOT_CAUSE_ALERTS.md` and `ALERT_PIPELINE_AUDIT.md`.
- Alerts *are* delivered: 20 Telegram messages on 6-Nov with 0 real failures, including 3 BUY calls, 1 SELL setup and 1 exit.
- "Accuracy-level" alerts do not exist, for these reasons:
  1. No rule has credible current-window accuracy.
  2. Live calls print old multi-year backtest stats, not window OOS results with CI.
  3. There is no accuracy gate in the pipeline.
  4. 15 of 18 signals on 6-Nov were rejected by entry / risk rules, with logged reasons.
  5. Angel data failures: 22 of 60 scans RATE_LIMITED, 1 FAILED, 162 stock data failures.
  6. Shadow / research strategies are never sent, by design.

## Files
| Deliverable | File |
|---|---|
| 1 Script inventory | `SCRIPT_INVENTORY.md`, `script_inventory.csv` (`inventory.py`) |
| 2 Execution register | `register/executions.jsonl` (+ `.csv`), `EXECUTION_REGISTER.md` (`register.py`) |
| 3 Script-wise results | `RESULTS_BY_SCRIPT.md`, `results/e1_records.json`, `results/e1_trades.csv.gz`, `results/e1_signals.csv` |
| 4 Accuracy / profitability summary | `ACCURACY_SUMMARY.md` |
| 5 Alert pipeline audit | `ALERT_PIPELINE_AUDIT.md`, `evidence/live_funnel_by_day.csv`, `evidence/live_ledger_6nov.csv` |
| 6 Root cause | `ROOT_CAUSE_ALERTS.md` |
| 7 Changes and tests | `CHANGES_AND_TESTS.md`, `tests/test_mcxe004.py` (11 pass) |
| 8–9 Not executed / failing / blocked | `SCRIPT_STATUS_LISTS.md` |
| 10 Next priorities | `NEXT_PRIORITIES.md` |
| Alert status + transparent card | `register.py` (`classify`, `alert_card`), `ALERT_CARD_EXAMPLES.md` |

Superseded register files (kept for audit, **not** results):
- `register/executions_devrun_7nov.jsonl`: metrics index bug, all runs FAILED.
- `register/executions_superseded_period_bug.jsonl`: DEV / VALID / OOS mislabelled.
- `register/executions_precommit_7nov.jsonl`: identical code, run before it was committed.

## Reproduce
```
python research/mcxe004/windows.py            # 1-year windows (already approved; re-run only after a data refresh)
python research/mcxe004/eval_live_rules.py    # E1 (about 2 min)
python research/mcxe004/blocked_cells.py
python research/mcxe004/inventory.py          # needs a checkout of main at /home/claude/ob-main for the live-code part
python research/mcxe004/report.py
python research/mcxe004/alert_examples.py
python research/mcxe004/tests/test_mcxe004.py
```
