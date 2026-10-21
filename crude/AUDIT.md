# Crude Oil engine – audit (21-Oct-2026)

## What already works (kept unchanged)
- `runner.py` auto mode on `bot.yml` (every 15 min): Engine A option selling, Engine B RSI alerts, Engine D Telegram calls (`calls/`, `CALLS_ENABLED=True`). Engine C (`mcx_trade.py`) stays disabled (`MCXT_ENABLED=False`).
- `angel.py` read-only client: `getCandleData`, FULL quotes, scrip master. No order code.
- `paper/mcx_daily.py` v3 paper engine (manual only), `research/` backtest framework and cost model.
- Telegram delivery via `notify.py`. State committed to `main` by `bot.yml`.

## What Angel actually returns for CRUDEOIL (probe run 21-Oct-2026 21:14 IST)
| Item | Result |
|---|---|
| 15-min candles | Served directly (`FIFTEEN_MINUTE`). History back to Oct-2020 on the front token. |
| 1-hour candles | Served directly. Bars start at 09:00, 10:00, … 23:00. |
| 3-hour candles | **Not served.** Built from completed 1-hour candles in fixed blocks: 09–12, 12–15, 15–18, 18–21, 21–close. |
| Forming candle | The last candle returned is **still forming**. Only closed candles are used (end time + 60 s). |
| Volume | Present on 100% of candles. There is no buy/sell split, so volume is never labelled as buying or selling. |
| Historical OI | **Unavailable.** `getOIData` for MCX returns AB1012 "Invalid Bad Request" (front and next contract, hourly and daily). |
| Current OI | FULL quote `opnInterest` (e.g. 1,420,700). `tradeVolume` is today's volume. There is no OI-change field. |
| Front-token history | **Vendor-stitched.** Older bars belong to the previous, expired contract. The jump at the switch was 293 pts on 22-Sep and 345 pts on 20-Oct-2026, measured from the overlap with the next contract. |
| Holidays | Half-day sessions (Dussehra 20-Oct and Ganesh Chaturthi 14-Sep-2026: evening only) appear as missing morning candles. |
| Lot / tick | CRUDEOIL lot 100 (₹100/pt) and CRUDEOILM lot 10 (₹10/pt), tick ₹1, match the scrip master. |

## What was missing
- Any 15-min logic, any 3-hour logic, OI handling that is honest about missing data, and roll continuity on the stitched token.
- A 0.25%-risk paper book with lot/tick checks, persisted state, failure-aware reporting and a health check.

## Reused
- `angel.Angel` and `load_master`.
- `research.roll_adjust.expected_return`, used to estimate historical roll gaps in the backtest.
- The cost-model structure from `research/instruments`.
- The state-branch pattern from the paper-engine workflow.
- The `research-data` workflow, now with `FIFTEEN_MINUTE` support.

## Files changed or added
- **New:**
  - `crude/` (config, data, indicators, rules, paper, engine, report, run, probe, backtest, tests, reports).
  - `.github/workflows/crude-paper.yml`.
- **Small, backward-compatible edits:**
  - `research/adapters/angel_hist.py` (15-min interval, `RESEARCH_INTERVALS`).
  - `.github/workflows/research-data.yml` (intervals input).
  - `.gitignore` (`state/crude/`).
- **Not touched:** `runner.py`, `config.py`, `bot.yml`, `calls/`, `mcx_trade.py`, `notify.py`, `angel.py`.

## Tests that prove it
`python -m crude.tests.test_crude` (86 checks) covers:
- RSI 25/75 boundaries.
- Closed-candle-only evaluation and 1-hour no-look-ahead.
- 3-hour construction.
- OI/volume missing or stale.
- Trend conflict.
- Duplicates.
- SL/target/gap fills.
- Costs and sizing.
- Session, expiry and roll.
- State restore and failed saves.
- Telegram flush failures.
- Workflow ordering.
- A 12-hour replay on real candles.

The existing suites still pass: research 16, paper 30, calls 18, plus both simulations.
