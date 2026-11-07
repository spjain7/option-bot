# MCXE-004 implemented changes and tests

All changes are on the research branch, under `research/mcxe004/`. **No live code on `main` was changed.** No strategy
logic was changed: E1 calls the existing research-parity functions (`portfolio.LIVE`, `search_v2` / `search_all` signal
sets, `harness.simulate`, `mcx_dtc.trades`) unchanged, on window-clipped data.

| File | What it does |
|---|---|
| `register.py` | Append-only execution register with the 30 required fields; enforced lifecycle (PENDING → RUNNING → COMPLETED / FAILED / BLOCKED / INSUFFICIENT_DATA); enforced validation vocabulary (RESEARCH_ONLY · PAPER_ONLY · VALIDATED_CANDIDATE · REJECTED · INSUFFICIENT_DATA · BLOCKED · ERROR). Exceptions and missing `finish()` are recorded as FAILED / ERROR, never silent. `metrics()` computes trade-level accuracy and profitability. `classify()` applies the pre-registered decision. `alert_card()` produces the transparent alert text |
| `window.py` | 1-year window enforcement (`clip`, `period`). **Fixed 7-Nov:** `period()` aligned on the caller's index and mislabelled periods. Caught by the new leakage test; all evaluations re-run |
| `eval_live_rules.py` | E1: the live / shadow rules with research parity, re-simulated only inside the windows, with indicator warm-up inside the window. One register record per rule; DEV / VALID / OOS at 1× and 2× costs; per-signal rejection reasons |
| `blocked_cells.py` | Registers every strategy or market cell that cannot be evaluated, with the exact reason |
| `inventory.py` | Evidence-based inventory of 227 scripts: committed outputs (git dates), live-loop log evidence, import graph from the scheduled entry points, workflow schedules |
| `report.py`, `alert_examples.py` | Generate every Markdown deliverable from the result files. The "bottom line" is computed, not typed |
| `tests/test_mcxe004.py` | 11 tests (below) |

## Tests: `python research/mcxe004/tests/test_mcxe004.py` → **11 tests passed**, run at commit 147f71c
| Test | Checks |
|---|---|
| test_registration_fields | Every required field is present; ids unique by script; start / end times set; unknown metrics stay null, not fabricated |
| test_status_transitions | Illegal transition (PENDING → COMPLETED) raises; INSUFFICIENT_DATA is recorded; unknown validation status → ERROR |
| test_failed_script_visibility | An exception and a missing `finish()` are both recorded as FAILED with error details |
| test_trade_counts_and_win_rate | Hand-computed example: trades, wins (net R > 0 only; 0.0 is not a win), win %, avg win / loss, expectancy, PF, net R, max drawdown, dates |
| test_missing_data_handling | Empty input → n = 0 and null metrics → INSUFFICIENT_DATA; NaN outcomes are not counted as trades |
| test_classify_never_promotes_on_win_rate | A 90 %-win, negative-expectancy series is REJECTED; good results on a contaminated window or without controls → PAPER_ONLY only |
| test_window_no_leakage | Windows ordered, at most 1 year; pre-window dates raise; every E1 trade lies inside its window, and its period label matches its date (**this test found the `period()` bug**) |
| test_cost_calculation | For every E1 trade, r1 − r2 equals exactly one cost (2× stress); costs > 0; futures cost fraction consistent |
| test_rejection_reasons_logged | For every rule × instrument: trades + Σ rejection reasons = signals |
| test_no_false_accuracy_claims | No card contains "x % accurate" or "probability of success"; a win rate appears only with wins / trades, dates and CI; INSUFFICIENT_DATA is shown explicitly |
| test_report_from_actual_results | Every OOS trade count in ACCURACY_SUMMARY.md equals the register record |

The existing test suites still pass: MCXE-003 (7 tests) and the `main` alert suite (`python -m alerts.tests.test_alerts`: 71 checks passed), which was not touched.
