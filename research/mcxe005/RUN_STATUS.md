# MCXE-005 script-wise run status

All scripts ran on branch `exp/strategy-program-001`. "Errors" counts the exceptions logged in `results/errors_<cell>.txt`.

| Script | Run | Status | Output |
|---|---|---|---|
| `tests/test_preservation.py` | before the research and again before the final commit | PASS 6/6 | production unchanged; S4 reproduces all 3 trades |
| `run.py mcx_intraday` | once | COMPLETED, 0 errors | 791,709 trades (7 commodities × 15m/30m) |
| `run.py mcx_positional` | once | COMPLETED, 0 errors | 185,587 trades (1h/4h/1d + overnight) |
| `run.py fut_intraday` | once | COMPLETED, 0 errors | 1,864,237 trades (179 stock futures, 1h) |
| `run.py fut_daily` | once | COMPLETED, 0 errors | 413,392 trades (209 stock futures, daily + overnight) |
| `run.py eq_daily` | once | COMPLETED, 0 errors | 532,258 trades (612 stocks, BUY only, BTST/positional) |
| `run.py eq_intraday` | once | COMPLETED, 0 errors | 9,365,074 trades (218 stocks × 15m/1h) |
| `select_eval.py freeze` | once (DEV + VALID only) | COMPLETED | 6,306 register rows; 4 frozen; 314 of 4,476 filter ablations "help" |
| `s4_study.py` | once | COMPLETED | 7 S4 baseline/variant rows; none validated |
| `select_eval.py oos` | once (1st attempt crashed on JSON output before printing; re-run of the same frozen list) | COMPLETED | 4 cells evaluated, all REJECTED |
| `summarise.py` | once | COMPLETED | ACCURACY_COMPARISON, FAILED_STRATEGIES, WINNING_STRATEGIES |

**Run times:** wall-clock times were not recorded. Every run used a pool of 2 worker processes.

**Final status by cell (register)**

| Status | Count |
|---|---|
| VALIDATED_CANDIDATE | 0 |
| PAPER_ONLY | 0 |
| REJECTED at OOS | 4 |
| FAILED_VALID | 25 |
| FAILED_DEV | 4,113 |
| INSUFFICIENT_DATA | 2,164 |

**Execution register:** `research/mcxe004/register/executions.jsonl` has 11 MCXE005 records (7 s4_study, 4 select_eval-oos).
