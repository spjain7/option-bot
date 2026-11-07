# MCXE-007 regression and safety tests (run 2026-11-07, after OOS and before the final commit)

| Suite | Command | Result |
|---|---|---|
| Production preservation (PETRONET / GLENMARK / TITAN, S4 hashes, negative controls, research parity, production alert suite with 71 checks) | `python research/mcxe005/tests/test_preservation.py` | **6 / 6 passed** |
| H1.12L shadow tracker (replay of all 306 MCXE-006 trades, cost breakdown, no side effects, signal statuses) | `python research/mcxe007/tests/test_shadow_tracker.py` | **4 / 4 passed** |
| Research isolation (no network / alert / Telegram / broker / order code or production imports in mcxe006 + mcxe007; origin/main unchanged) | `python research/mcxe007/tests/test_research_isolation.py` | **2 / 2 passed** |

**Production commit:** `origin/main` = bc3153e6b30bb8477a3d81042b96a5f93c5f8444. The `main` worktree is clean (0 changed files).

**What protects the three production calls:** `test_production_reproduces_three_signals`.
- It runs production `evaluate` from a pristine `git archive` of bc3153e6 on the recorded bars.
- It asserts BUY for PETRONET (2-Nov), GLENMARK (4-Nov) and TITAN (4-Nov).
- `test_negative_controls` asserts that no signal fires when OI, volume, breakout, expiry window or EMA200 conditions fail.

**Not changed:** production code, configuration, alerts, Telegram, broker / Angel execution, risk management, scanner behaviour, shadow settings and the `main` branch.
