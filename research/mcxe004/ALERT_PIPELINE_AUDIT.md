# MCXE-004 alert pipeline audit (live code on `main` at bc3153e; evidence from the 6-Nov-2026 run and the `alerts-state` branch)

Evidence sources (all read-only):
- Code: `alerts/*.py`, `scripts/market_loop.sh`, `.github/workflows/market-loop.yml` on `main`.
- The full log of market-loop run **42154958592** (6-Nov-2026, 03:11–18:47 UTC).
- The `alerts-state` branch: `alerts/state.json` (funnel, ledger, status), `scan.json` and `delivery.json`.
  - Extracted to `evidence/live_funnel_by_day.csv` and `evidence/live_ledger_6nov.csv`.

## Pipeline, stage by stage
| # | Stage | Where (code) | What happens | Logged? | Evidence 6-Nov-2026 |
|---|---|---|---|---|---|
| 1 | Schedule | `market-loop.yml` → `scripts/market_loop.sh` (scan every 15 min, 08:55–00:20 IST) | Fresh worktree of the latest `main`; restore state from `alerts-state`; `python -m alerts.run scan`; save state; `alerts.run flush` | yes (`alerts outcome:` line + step summary) | **60 alert scans: 35 SUCCESS, 22 RATE_LIMITED, 1 BUDGET_EXHAUSTED, 1 FAILED** |
| 2 | Data | `angel.py` (REST candles / quotes, pacing, rate-limit fail-fast, time budget `ANGEL_DEADLINE`), `wsfeed.py` / `wsbars.py` (live ticks) | Candles per instrument and timeframe; stock futures 1-hour for the 3h / 4h / daily stock scans | yes: funnel stage `data`, `scan.json` api counters | **163 data failures** in the funnel (162 stock futures, 1 MCX). The FAILED scan: "Angel login / instrument list failed: DataException", so no alerts that slot. BUDGET_EXHAUSTED 14:02–14:19 IST: 35 of 67 calls refused, 186 skipped. The 15:30 stock 4h scan needed 6 cycles to cover 207 stocks (37 → 63 → 110 → 141 → 179 → 207) |
| 3 | Indicators + conditions | `alerts/engine.py` (breakout S1–S3, index / MCX), `alerts/rulebook.py` (RB rules, signal code copied from `search_v2.py`), `alerts/stocks.py` (S4 / S5 stock futures), `alerts/four_hour.py` (stock 4h SELL), `alerts/candle_setups.py`, `alerts/mcx_dtc.py` (shadow), `alerts/watch1h.py` | Completed candles only | yes: per-instrument `[GOLD] …` lines with every rule's result; `status` in state | `[stocks]` / rulebook / `bo_3h` / `bo_1d` lines present all day (inventory: live log evidence column) |
| 4 | Signal | same modules → `alerts/funnel.note(…, "signal")` | One record per rule × instrument × candle | yes (funnel, since 6-Nov) | **18 signals** |
| 5 | Risk checks / validation filters | `alerts/tradeplan.py` (stop-loss % cap, R:R), entry zone (no chase > 0.5 ATR past the signal), live-quote staleness, `alerts/strategies.conflict` (one call per instrument + direction, duplicates), daily-trend filter (rulebook `DT`), grade | Rejects with an exact reason | **yes:** funnel `rejected{reason: n}` + `[rejected]` / `[conflict]` log lines + rulebook dict | **15 of 18 rejected**:<br>– price already ran 0.98 / 1.22 ATR past the signal: 4<br>– duplicate of an open call: 4<br>– daily trend not up: 3<br>– already in an open call: 2<br>– stop-loss too wide (4.6 %, 7.7 %): 2<br>– R:R 1.00 below 1.0: 1 |
| 6 | Alert eligibility | rulebook `status` LIVE / SHADOW; `mcx_dtc.LIVE = False`; HA-1 log-only (`engine.py:713`); `paperguard.blocked()` (PAPER_ONLY / SHADOW_ONLY markers never sent) | Only LIVE rules reach the outbox | shadow: funnel `shadow` + `shadow_log` | shadow 0 sent (by design). The DTC shadow was deployed 6-Nov 17:11 IST, after both 13:00 / 17:00 checkpoints, so **0 DTC records so far**; log shows "dtc: not a checkpoint candle" ×56. `paperguard` blocked 0 |
| 7 | Delivery | `alerts/run.py flush`: after the state save; pending queue; calls older than 30 min dropped as stale; Telegram via `crude.run.telegram`; counts in `delivery.json` | yes: `sent: ok \| …` / `TELEGRAM FAILED` lines; funnel `sent` | **20 real Telegram messages sent: ok, 0 real failures.** The 3 `TELEGRAM FAILED: HTTP 429` lines are the offline test (`alerts/tests/test_alerts.py:395`, mocked). Calls delivered: NIFTY BUY (daily EMA 20/50), BANKNIFTY BUY (daily RSI > 70), ICICIBANK BUY (daily RSI > 80), JSWSTEEL SELL setup (hanging man), GOLD EXIT. Stale drops 0 |
| 8 | Outcome tracking | ledger + `alerts/scorecard.py` (closed-call stats in the end-of-day message) | Live results per call | yes (ledger) | 24 calls 28-Oct → 6-Nov:<br>– 16 closed: 3 withdrawn, 7 cancelled on a gap;<br>– **6 with a real outcome:** 2 target, 4 stop, gross 0.0R |

## What the alerts claim as "accuracy" today
- Rulebook calls carry a fixed line: *"Strength: tier A – N backtest trades, X % won, +Y R avg after 2× costs, periods …
  (backtest, not a guarantee)"* (`alerts/rulebook.py:369-370, 443-444`).
- These numbers come from the 2006-26 / 2022-26 searches. They are **not** out-of-sample results inside the approved
  1-year window. They carry no confidence interval, no unique-date count and no validation status.
- There is **no accuracy gate** anywhere in the pipeline: alerts are not filtered by any measured accuracy. They are
  filtered only by the entry / risk rules in stage 5.

## Visibility gaps found
1. **Funnel history** starts on 6-Nov-2026. It was introduced that day and keeps 10 days. Rejections before 6-Nov exist only
   in Actions logs.
2. **`delivery.json`** holds only the current day (latest file: `{"2026-11-07": {"sent": 0, …}}`). The history of
   delivered and failed messages exists only in Actions logs.
3. **Research results never reach the live pipeline.** No research script on `exp/strategy-program-001` produces live
   signals, and no research status (PAPER_ONLY etc.) is attached to live calls. The two pipelines are disconnected by
   design: research-only.
4. **No per-signal validation status in alerts.** The live call shows the static backtest tier. The status system and
   alert card are implemented in research (`register.alert_card`, examples in `ALERT_CARD_EXAMPLES.md`), but are **not
   wired into production**. That needs owner approval.
