# MCXE-006 production regression results

**Production check:** `origin/main` = bc3153e6b30bb8477a3d81042b96a5f93c5f8444 (verified on 2026-11-07 before starting). The `main` worktree is clean.

**Command:** `python research/mcxe005/tests/test_preservation.py`

| Run | Result |
|---|---|
| Before MCXE-006 work | 6 / 6 passed |
| After OOS, before final commit | 6 / 6 passed |

**What the tests cover**
1. The S4 signal-path files on `main` are byte-identical to the baseline.
2. Production `evaluate` (run from a pristine archive of bc3153e6) still emits BUY for PETRONET (2-Nov), GLENMARK (4-Nov) and TITAN (4-Nov).
3. Negative controls produce no signal.
4. The research copy matches production.
5. No send, notify, order or POST code exists in the research packages. This check covers `research/mcxe004` and `research/mcxe005`; `research/mcxe006` imports neither Telegram nor broker modules (checked with grep below).
6. The production alert suite passes (71 checks).

**Grep check for `research/mcxe006`:** `grep -rniE "telegram|send_message|place_order|requests\.post|notify" research/mcxe006/*.py` returns nothing.

**Not changed:** production code, configuration, alerts, Telegram, broker, shadow settings and the `main` branch.
