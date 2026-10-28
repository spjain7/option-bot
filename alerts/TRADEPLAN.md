# Trade-plan validation (28-Oct-2026)

Every futures, stock-futures and option-buy call is built through `alerts/tradeplan.py` before anything is sent.
The same numbers are used for the Telegram call, the open-call tracker (`state["bo_active"]`, `state["stk"]["active"]`)
and the report ledger (`state["ledger"]`), so what you read is exactly what is tracked.

| Check | Rule | Where |
|---|---|---|
| Data | signal close, ATR and live price finite and > 0; missing live price during market hours = no call | `futures_plan` |
| Quote timestamp (market hours) | live entry needs the quote's exchange time (`exchFeedTime`, else `exchTradeTime`); missing or malformed = no call | `quote_check` |
| Quote age | older than 5 min = no call | `MAX_QUOTE_AGE_MIN` |
| Quote in the future | more than 60 s ahead of our clock = no call (env `QUOTE_CLOCK_SKEW_SEC`) | `MAX_CLOCK_SKEW_SEC` |
| Time zones | all times compared as naive Asia/Kolkata; tz-aware values converted first | `to_ist` |
| Stock calls | sent after the close without a live quote; at the next open the quote must pass the same timestamp checks, otherwise the call keeps waiting (never activated or cancelled on an unverified price) | `stocks.validate_pending` |
| Logging | every rejected signal prints `[rejected] <name> <tf> <side>: <reason>` in the run log | `engine._breakouts`, `run.py` |
| Slippage | live price ≤ 0.5 ATR past the signal (no chasing) and ≤ 0.5 ATR against it (setup still valid) | `MAX_CHASE_ATR`, `MAX_AGAINST_ATR` |
| Tick | entry, SL, target rounded to the contract tick from the instrument master (`tick_size`); SL rounded away from entry, target towards it; risk / reward recomputed | `tick_round` |
| Sides | BUY: SL < entry < target · SELL: SL > entry > target | |
| Stop width | ≤ 2.5% (3h), 4% (daily, monthly), 6% (stock futures); the stop is never widened to fit | `MAX_SL_PCT` |
| Reward/risk | ≥ the strategy's minimum (1.0) after rounding | `min_rr` |
| S/R | a resistance (BUY) / support (SELL) in the first half of the way to the target is shown as a WHY note – not a rejection (no research support) | `levels` |
| Option buy | levels on the PREMIUM (−30%/+60% 3h, −35%/+80% daily/monthly), tick-rounded, never derived from the futures stop; no call if premium missing, illiquid, spread too wide, IV expensive or VIX jumping | `option_plan`, `optfilter.py` |
| Stock futures | sent after the close with entry = close; at the next session (09:16+) the call becomes ACTIVE only if the price is inside the 0.5-ATR entry zone and not beyond the SL, otherwise CANCELLED | `stocks.validate_pending` |
| Option sell | SL / target rounded to the option tick; naked sells keep reward ≥ risk after rounding | `runner.try_open` |
| Telegram | futures / option-buy: retry on 429 + `pending.json`; option-sell: retry on 429 + `state/telegram_pending.json`, re-sent next run | `alerts/run.py`, `notify.py` |

Strategy rules (ATR multiple, target in R, entries) are unchanged by this layer.
Tests: `python -m alerts.tests.test_tradeplan` (45 checks) and `python -m alerts.tests.test_alerts`.
