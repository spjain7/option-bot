# MCXE-005 regression and safety tests

**Command:** `python research/mcxe005/tests/test_preservation.py` (no pytest needed)

**Last run:** 2026-11-07, final check before commit. Result: **6 of 6 passed** (75 s).

| # | Test | What it proves |
|---|---|---|
| 1 | `test_production_unchanged` | `main` is still at bc3153e6, and the S4 signal-path files are byte-identical to the recorded hashes. |
| 2 | `test_production_reproduces_three_signals` | Production `evaluate` reproduces BUY for PETRONET 2-Nov, GLENMARK 4-Nov and TITAN 4-Nov. It is run from a pristine `git archive` of the baseline commit, in a separate process, on the recorded fixtures plus the production OI values. |
| 3 | `test_negative_controls` | The same bars produce no signal when OI is +1.9 %, volume is 1.4×, the breakout is removed, the date is in the expiry window, or the close is below EMA200. The rule has not drifted into firing on everything. |
| 4 | `test_research_copy_parity` | The research copy (`s4_research.py`) gives identical decisions to production on all fixtures and controls. |
| 5 | `test_research_cannot_send_or_trade` | No Telegram, notify, order-placement or HTTP POST code exists in `research/mcxe004` or `research/mcxe005`. |
| 6 | `test_production_alert_suite_passes` | The existing production alert test suite (71 checks) still passes on the baseline. |

**Also confirmed in the `main` worktree**
- `git rev-parse HEAD` = bc3153e6b30bb8477a3d81042b96a5f93c5f8444.
- The working tree is clean (0 changed files).

**Not touched by this work:** strategy rules, entry, exit, stop and target logic, alert eligibility, production config, the broker, Telegram, and shadow settings.
