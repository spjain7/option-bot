# H1.12L shadow-tracking protocol (FROZEN 2026-11-07, before any forward data was collected)

**Scope:** research-only forward logging.
- No alerts, no Telegram, no orders, no production or shadow deployment, nothing written outside `research/mcxe007/shadow/`.
- No H1.12L tracker existed before this one (checked: `research/`, `alerts/`, `crude/` and the `*-state` branches have no H1.12L / MCXE-006 reference).

## Frozen specification (identical to MCXE-006 commit 31a25d8, `research/mcxe006/experiments.py` id `H1.12L`)

**Data and bars**
- **Data:** Angel MCX front-month stitched 5-minute candles (`research/data/angel/manifest.csv`, `front_stitched=True`), loaded by `research/program/liqtl_mcx5.load`. Duplicate timestamps are dropped by that loader, and the contract-switch days come from `research/search/strategy_search.switch_days`.
- **Bars:** 60-minute bars anchored at 09:00 IST, built by `research/mcxe005/frames.mcx_positional(name, 60)` from 5-minute data starting at the MCX window start, 2025-11-04. Timestamps are bar-start IST.
- **ATR:** `crude.indicators.atr(f, 14)` on these 1-hour bars (the MCXE-005 `B._finish` definition).

**Rules**
- **Signal:** `research/mcxe006/strategies.donchian(n=20, k=2.0)` BUY side only. The 1-hour close crosses above the highest high of the previous 20 bars (`high.shift(1).rolling(20).max()`). Only the first close above the level counts.
- **Eligibility:**
  - bar index ≥ 40 (warm-up);
  - ATR finite and > 0;
  - not a contract-switch day (`sig_ok`);
  - not the last bar;
  - the exit cap (`iend_positional`, 240 bars or the bar before the next switch day) is after the signal;
  - no open position in that commodity.
- **Frozen quirk, preserved deliberately:**
  - MCXE-006 simulated H1.12L as the two-sided Donchian rule (one position slot per commodity) and kept only the BUY trades afterwards (`side_only=1` is applied after `engine.run`).
  - So a BUY signal is skipped while the rule's own SELL leg (never traded, never counted) would still be open.
  - The tracker reproduces this exactly. SELL legs are logged as `sell_leg_blocking` / `sell_leg_open` so the blocking is visible.
  - A "pure long-only" version would be a *different* strategy. It is not tracked.
- **Entry:** the open of the next 1-hour bar. The entry is rejected if that open is already at or below the stop (R ≤ 0).

**Exits**
- **Initial stop:** entry − 2 × ATR at the signal bar.
- **Trailing stop:** the highest close since entry − 4 × ATR at the signal bar. It only rises and is checked from the next bar onwards.
- **Exit order inside a bar:**
  1. a gap through the stop fills at the open;
  2. otherwise, a touch of the stop fills at the stop;
  3. otherwise, the trail is updated at the close.
- **Time exit:** at the close of bar `iend` (240 bars, or the bar before the next contract switch).

**Costs**
- `research/program/mcx_disc.real_cost` (MCXE-003 MCX model):
  - brokerage ₹20 per order;
  - exchange 0.0021 %;
  - SEBI ₹10 per crore;
  - GST 18 % on (brokerage + exchange + SEBI);
  - CTT 0.01 % on the sell side;
  - stamp duty 0.002 % on the buy side;
  - slippage and spread of 1.5 ticks per side.
- Costs are recorded per lot in rupees and in R. The 2× stress doubles the whole cost.

**Engine:** `research/mcxe006/engine._run` / `_sim`, imported unchanged. The tracker adds logging only.

## Forward period and counting
- **Forward period:** signals whose signal bar starts on or after **2026-11-04 09:00 IST**, the first session after the MCXE-006 OOS window. At freeze time no MCX data after 2026-11-03 existed in the research store.
- **Carry-over:** positions opened before the forward period are logged as `carry_over` and **not counted**.
- **Checkpoint 1** is preliminary and is not validation. It requires all of:
  - ≥ 30 closed forward trades on ≥ 20 distinct signal dates;
  - expectancy at 2× cost > 0;
  - a day-block bootstrap 95 % CI lower bound > 0.
  Logging continues after the checkpoint whatever its result.
- **Parameters are never changed.** A defect fix to logging is allowed only if it does not change any trade, and it must be proven by the replay test.

## Logged per signal (`shadow/ledger_h112l.csv`)
- **Identification:**
  - signal time, commodity, contract (the front-stitched symbol whose file supplied the bar), forward / pre-forward flag.
- **Signal values:**
  - signal close, 20-bar level, ATR.
- **Status:**
  - `trade` / `sell_leg_blocking` / `sell_leg_open` / `rejected_switch_day` / `rejected_warmup` / `rejected_position_open` / `rejected_roll_cap` / `rejected_gap_below_stop` / `rejected_no_next_bar` / `open`.
- **Entry:**
  - entry time and next-bar open; initial stop; R in points.
- **Exit:**
  - final trailing stop; exit time, price and reason (stop / trail / gap / time / open);
  - hold in bars and hours; MAE and MFE in R.
- **Results:**
  - gross R and net R at 1× and 2× cost;
  - cost per lot in rupees, split into brokerage, exchange, SEBI, GST, CTT, stamp and slippage/spread;
  - net rupees per lot.

**Data issues** go to `shadow/data_issues.csv`: missing 1-hour bars inside a session, sessions with unusually few bars, duplicate timestamps dropped by the loader, weekday gaps, and stale data (last bar more than one weekday old).

## How it runs
- `python research/mcxe007/shadow/h112l_tracker.py`
  - It reads whatever stitched 5-minute files the manifest points to.
  - It rewrites the ledger and STATUS.md deterministically.
- **Data dependency:** forward bars must be appended to the research store with the same pipeline that produced the window data. That pipeline is the Angel candle download, which needs broker API credentials that this research environment does not have. **Until the store is refreshed, forward trades = 0.** This is a blocked step and is not hidden.
- **Replay test:** `research/mcxe007/tests/test_shadow_tracker.py`. On data up to 2026-11-03 the tracker must reproduce every MCXE-006 H1.12L trade (DEV, VALID and OOS) exactly.
