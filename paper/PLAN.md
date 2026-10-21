# Paper engine v3 – audit findings and implementation plan (written before code changes, 21-Oct-2026)

## Entry points (verified in source)
| Engine | Entry point | Switch | Paths checked |
|---|---|---|---|
| Option selling (Engine A, NSE + MCX options) | `runner.main()` → `Bot.monitor / intraday_scan / positional_scan / mcx_*_scan` | `OPTION_ENGINE_ENABLED` (inside `Bot`), `MCX_OPTIONS_ENABLED` | `bot.yml` schedule + manual modes auto/test/report/mcx/view |
| OI / volume flow + big-move alerts | `runner.main()` → `flow.run` | `FLOW_ENABLED`, `BIGMOVE_ENABLED` | same |
| RSI extreme alerts (Engine B) | `runner.main()` → `rsi_alert.run` (mode `auto` only) | `RSI_ENGINE_ENABLED` | same |
| Hourly MCX buy/sell (Engine C) | `runner.main()` → `mcx_trade.run` (modes `auto` and `mcxtrade`) – **the only call site** (grep: `runner.py:746`) | `MCXT_ENABLED` checked right before that call for both modes | `bot.yml`; `tests/sim_mcx_trade.py` imports it directly (test only) |
| Daily MCX paper engine | `python -m paper.mcx_daily` via `.github/workflows/paper-mcx-daily.yml` (manual) | separate workflow; never imported by `runner.py` | – |

Hourly engine state `state/mcx_trades.json`: 0 open and 0 closed calls, so disabling it leaves nothing unmanaged.

## Verified problems in the current paper engine (`paper/mcx_daily.py`, commit 9cabadc)
1. **Signals and fills on the vendor-stitched front-month series.** Angel's nearest-token history switches contract at
   expiry (verified on NIFTY vs NSE bhavcopy: same close as the front contract on 96% of days; MCX volume collapses to
   11-100 lots in the last days, then jumps). Each switch is an artificial price jump inside breakout and ATR windows.
   Paper fills, stops and exits were also taken from that series, not from a real contract.
2. **Daily-loss lock resets on a re-run**: `end_of_day()` compares equity with `last_equity`, which the same run just
   overwrote; a second run on the same day computes 0% change and clears the lock.
3. **Sizing uses realised cash**, not marked-to-market equity.
4. **Risk, margin and exposure are only checked at the signal**, not again at the simulated fill.
5. **Only the latest candle is processed live**: if a run is missed, a pending entry fills at the wrong day's open.
6. **No checks for duplicate candles or impossible OHLC**; holes and staleness only partly checked.
7. **Workflow hides failures**: state restore ends with `|| true`, the push with `|| echo`, and a missing branch is not
   distinguished from a failed restore.
8. Dedup key lacks the direction; alerts lack a paper id / generation time and the slippage assumption.
9. Long-only is a config tuple only – no guard against a misconfigured value.

## Plan (small, testable steps)
1. `paper/contracts.py`: contract store (per-contract daily candles with token + expiry, persisted), data validation,
   vendor-day → contract mapping, **exact roll gaps where both contracts were recorded on the same day**, unknown gaps
   otherwise; signal series back-adjusted only by exact gaps; signals suppressed (NO TRADE) when the 56-bar
   breakout/ATR window contains a switch with an unknown gap.
2. Engine: positions held in a real contract (fills, stops, exits on that contract's candles); explicit roll policy
   (roll at the close when ≤ 5 trading days to expiry, both legs costed, stop moved by the exact gap); size from MTM
   equity and actual fill-to-stop distance; all limits re-checked at fill; chase / back-below-breakout rejection;
   persistent per-day locks keyed by trading date; catch-up over every unprocessed candle; long-only enforced.
3. Workflow: explicit new-account vs restore-failure logic, fail on restore/commit/push errors, manual only,
   Telegram off by default; a separate daily schedule file prepared but kept outside `.github/workflows/`.
4. Tests: long-only cannot confirm a short; two runs on the same state create no duplicate alerts or fills; lock persists
   across re-runs; invalid/stale/duplicate data cannot confirm; roll gap exactness; risk at fill.
5. Disable hourly Engine C only via `MCXT_ENABLED = False` (single verified call site); nothing else in `config.py`.
6. Re-run research + replay; write the strategy report with the requested metrics.
