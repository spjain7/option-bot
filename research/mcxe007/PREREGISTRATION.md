# MCXE-007 pre-registration (2026-11-07, written before any MCXE-007 result)

Base: research branch `exp/strategy-program-001` at d08d607. Production `main` = bc3153e6, untouched.

## Workstream A: H1.12L shadow tracking
See SHADOW_TRACKING_PROTOCOL.md (frozen separately).

## Workstream B: daily breakout / breakdown research

### Universe and data (approved MCXE-004 windows only; nothing older, no window widening)

| Market | Window (DEV / VALID / OOS) | Source | Instruments |
|---|---|---|---|
| MCX daily | 2025-11-04 → 05-04 / 08-04 / 11-03 | Angel front-month stitched 5-minute bars → daily bars (09:00 anchor). Positions are force-exited before a contract switch. | The 7 commodities of the approved pipeline |
| NSE stock futures daily | 2025-11-07 → 2026-05-07 / 08-07 / 11-06 | NSE F&O bhavcopy, point-in-time. All FUTSTK rows, including expired contracts. Front month with the roll 2 sessions before expiry; ratio back-adjusted; no trade spans a roll. | Every symbol that traded inside the window (no current-constituent list) |
| NSE index futures daily | same as stock futures (NSE_FUT key) | the same bhavcopy, FUTIDX rows | NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50 (whichever have in-window data) |

**Warm-up:** each strategy's longest lookback + 15 bars, counted from the window start. EMA100 and EMA200 cannot be warmed up inside the window, so they are marked INSUFFICIENT and not tested.

### Execution and costs
- **Signal timing:** a close-confirmed signal is evaluated at the daily close. Entry is at the next session's open. Fills at the signal close are not allowed.
- **Intraday-breach variant:** a stop order at the level, valid for the next session only.
  - Fill = open if the session opens through the level (gap-through), otherwise the level.
  - If the stop is also inside that session's range, the trade is assumed stopped (worst case).
- **Stops:** the stop is checked before the target. A gap through the stop fills at the open. One position per instrument per strategy.
- **Costs:**
  - MCX: statutory fees plus 1.5 ticks of slippage per side (MCXE-003 model).
  - Stock futures: fees plus 0.05 % per side.
  - Index futures: `research/instruments.cost_points` (fees plus the index slippage points).
  - All results are also shown at 2× costs.
- **Rupees:**
  - MCX: R points × contract multiplier, per 1 lot (raw stitched prices).
  - Stock and index futures: R × risk % × 1-lot notional, using the raw front-contract bhavcopy close. Lot sizes come from the current Angel scrip master (approximate for past dates; disclosed).

### Families (one change at a time from a baseline; small, economically motivated sets only)
- **A Classic:**
  - Donchian close breakout / breakdown with N ∈ {5, 10, 20, 30, 50};
  - close-confirmed vs intraday breach (stop order);
  - 0.25-ATR buffer.
  - Default exit X0 = 2-ATR stop, 4-ATR trailing stop, 40-session cap (carried over from MCXE-006).
- **B Trend filter:**
  - EMA20 > EMA50 alignment;
  - ADX ≥ 20;
  - HH/HL structure (last swing high and low rising);
  - market trend (NIFTY futures EMA20 vs EMA50, stocks only);
  - relative strength vs NIFTY (20-day).
- **C Volatility:**
  - NR4 / NR7 or inside-day breakout (stop order at the range);
  - ATR(5) / ATR(20) < 0.75, then breakout.
- **D Volume / OI:**
  - volume > 1.5 × its 20-day average;
  - OI up (build-up) vs OI down (covering) on the signal day, using exchange OI;
  - an explicit exchange vs Angel OI comparison in the data audit.
- **E Retest / failed breakout:**
  - breakout, then a retest within 5 sessions, then a close back beyond the level;
  - failed breakout (close back inside within 3 sessions), then fade.
- **F Gap handling:** skip if the next open is beyond the level by more than 1 ATR (no chasing), vs taking every gap.
- **G Exits:**
  - X0 as above;
  - X1 = 2-ATR stop + 2R target, 10 sessions;
  - X2 = swing stop (lowest low of the last 5 sessions) + 4-ATR trail;
  - X3 = time exit after 5 sessions, with 2-ATR stop;
  - X4 = partial 50 % at 1.5R, rest trailing at 4 ATR (only to test the win-rate vs expectancy trade-off).
- Long and short are always measured separately. Every experiment is recorded in EXPERIMENT_REGISTER.csv.

### Staged selection (DEV and VALID only; OOS is masked in code during development)
- **Stage 1:** baselines per market. A change is KEPT if it raises DEV 2× expectancy and does not lower VALID 2× expectancy (the MCXE-006 rule).
- **Freeze bar** (per market and side):
  - DEV and VALID each ≥ 20 trades on ≥ 15 dates;
  - 2× expectancy > 0 in both;
  - DEV + VALID day-block bootstrap CI (1×) lower bound > 0;
  - beats a random-entry control (same instruments, sides, counts and exits) in DEV + VALID;
  - beats the market-direction control (always long or always short at the same frequency);
  - removing the top 5 trades still leaves DEV + VALID expectancy ≥ 0;
  - no single instrument provides more than 50 % of net R.
- **At most 6 frozen candidates** in total (at most 3 per market). The list is committed before OOS.
- **Index futures:** with 5 instruments, daily breakouts are expected to give fewer than 20 trades per period. They are reported, and marked INSUFFICIENT_DATA where the bar is not met. They are not pooled with stocks.

### OOS (once per frozen candidate)
- `research/mcxe004/register.classify` with `selection_overlaps_window=True` for every market, because:
  - MCX OOS was used in MCXE-006 (including a random-entry control showing a trending OOS);
  - stock-futures OOS was used in MCXE-005, which revealed a falling-stock regime;
  - the index futures OOS regime is therefore partly known as well.
- So the **best possible outcome is PAPER_ONLY**. Nothing can become a validated candidate from this window.
- Also reported: BH across the frozen list, top-1/3/5 removal, random-entry and market-direction controls, and breakdowns by instrument, month and regime.

## Overlap with earlier work (disclosed)
- **MCXE-005:** `B_BO20`, `B_BO20_VOL`, `B_FAIL_BO`, `B_COMPRESS_BRK`, `D_INSIDE_BRK` and `D_NR7_BRK` on stock-futures and MCX daily bars with 60-bar warm-up and X1/X2 exits. All failed. The S4 study (breakout + volume + OI + EMA200) failed.
- **MCXE-006:** H1.0d (MCX daily Donchian 20); H3.5 / H3.6 (stock-futures Donchian, with breadth); H3.0b (breakout + volume + OI). All failed or had too few trades.
- **New in MCXE-007:**
  - shorter warm-up, which gives more DEV;
  - index futures;
  - intraday-breach entries, buffers and gap handling;
  - HH/HL structure, relative strength and market trend;
  - OI build-up vs covering split by side;
  - swing stops and time stops;
  - controls and concentration tests built into the freeze rule.
