# Why "accuracy-level" alerts are not arriving – root cause (evidence-based)

**Short answer.**
- Alerts **are** being generated and delivered: on 6-Nov-2026, 20 Telegram messages went out with 0 real failures,
  including 3 BUY calls, 1 SELL setup and 1 exit. The ledger holds 24 calls between 28-Oct and 6-Nov.
- What does not arrive are **alerts backed by credible, current accuracy evidence**. There are three reasons: no such
  strategy exists in the system, most signals are filtered out before delivery, and data failures cut the scan coverage.

| # | Root cause | Evidence | Effect |
|---|---|---|---|
| 1 | **No strategy has credible accuracy evidence inside the approved 1-year window** | E1 re-ran 14 live / shadow rules inside the window (`ACCURACY_SUMMARY.md`): 0 VALIDATED_CANDIDATE, 2 PAPER_ONLY, 7 REJECTED (OOS CI includes 0), 5 INSUFFICIENT_DATA; 11 more BLOCKED. The 2 PAPER_ONLY rules (stock 3h MACD-zero SELL, stock 3h EMA 9/21 SELL) were selected on data that includes this window, so they are not independent | There is nothing that could honestly be labelled "high accuracy" |
| 2 | **The "accuracy" printed on live calls is old backtest text, not window OOS** | `alerts/rulebook.py:369-370, 443-444`: "N backtest trades, X % won … (backtest, not a guarantee)", from 2006-26 / 2022-26 searches; win rates 42–55 % in the RULES table; no CI, no dates, no status | Alerts arrive, but without the transparent accuracy the owner expects |
| 3 | **There is no accuracy gate in the pipeline** | No code path compares a signal against measured OOS accuracy; filters are entry / risk rules only (stage 5 of `ALERT_PIPELINE_AUDIT.md`) | An "accuracy-level" alert class does not exist to be sent |
| 4 | **Most generated signals are rejected before delivery (correctly logged)** | Funnel 6-Nov: 18 signals → 3 sent, 15 rejected. Reasons: chase > 0.5 ATR 4, duplicate 4, daily trend 3, already open 2, stop too wide 2, R:R 1. Plus 8 `[rejected]` log lines in other slots (stale quotes, price moved against) | Few calls per day by design; every rejection has its reason |
| 5 | **Data failures reduce coverage** | 6-Nov: 22 / 60 scans RATE_LIMITED, 1 BUDGET_EXHAUSTED, 1 FAILED (Angel DataException → no alerts that slot); 162 stock-futures data failures; the 15:30 stock 4h scan took 6 cycles. OPS-RATE: Angel refused 47 % of candle requests during NSE hours | Some signals are never evaluated, or are evaluated late (stale → rejected) |
| 6 | **Shadow / research strategies are never sent, by design** | `alerts/mcx_dtc.py` LIVE = False (deployed 6-Nov 17:11 IST, after both checkpoints → 0 records yet); HA-1 log-only; research branch not connected to delivery | The day-trend strategy cannot produce alerts. Its window result is also REJECTED (OOS 48 trades, CI −0.28 … +0.87) |
| 7 | **Forward live record is too small to state accuracy** | 6 calls with real outcomes since 28-Oct (2 target, 4 stop, gross 0.0R); 10 withdrawn / cancelled | INSUFFICIENT DATA for any live accuracy claim |

**Not a cause (checked):**
- Telegram delivery: 0 real failures; the 429 lines are mocked tests.
- `paperguard` blocking: 0 blocks on 6-Nov.
- Stale-call drops: 0.
- Silent exceptions: the `[scorecard]` failure path prints, and no scorecard errors appear in the log.

**What would make accuracy-qualified alerts possible (owner approval needed; not done):**
1. Attach each rule's window evaluation (status, OOS n / dates / CI) to its live call via `register.alert_card`, and
   stop showing the multi-year backtest tier as if it were current.
2. Fix Angel data coverage during NSE hours (OPS-RATE proposal: bars from the live feed, history pre-fetched before 09:00).
3. Accumulate forward paper evidence for the two PAPER_ONLY stock SELL rules before any "accuracy" label.
