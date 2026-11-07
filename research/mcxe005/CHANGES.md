# MCXE-005 summary of changes

**Branch:** `exp/strategy-program-001`. Only research files changed.

**Not changed**
- `main` is unchanged at bc3153e6b30bb8477a3d81042b96a5f93c5f8444.
- No production, broker, Telegram, alert or shadow file was touched.
- No real orders were placed and no alerts were sent.

**Commits, in order**

| Commit | Content |
|---|---|
| 85b584d | Pre-registration (families, filters, exits, selection rules), written before any result |
| cb10010 | Research copy of S4, recorded PETRONET/GLENMARK/TITAN fixtures, 6 preservation tests |
| 1304d4a | Engine (frames, signals, run), S4 study, DEV/VALID selection, 4 survivors frozen before OOS |
| 6de0161 | OOS evaluated once: all 4 REJECTED |
| dcdff66 | Reports: EXISTING_STRATEGY_ANALYSIS, ACCURACY_COMPARISON, WINNING_STRATEGIES, FAILED_STRATEGIES, DATA_QUALITY_AUDIT, REGRESSION_TESTS, NEXT_RESEARCH_PRIORITIES, RUN_STATUS, register `oos_status` column, summarise.py |

**Rollback:** every change is in `research/mcxe005/` plus appended records in `research/mcxe004/register/executions.jsonl`. Reverting these commits on the research branch removes all of it. Production is unaffected either way.

**Large files:** the per-trade parquet files in `results/` are git-ignored. They can be regenerated with `run.py <cell>`.
