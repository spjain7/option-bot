# MCXE-006 frozen candidates (committed BEFORE any OOS computation)

**Selection basis:**
- PREREGISTRATION.md freeze rule, applied to DEV + VALID only.
- In every MCXE-006 run so far, `engine.run(oos=False)` dropped OOS signals and capped exits before OOS.
- At most 2 candidates per family.
- Only the last KEPT version of each chain is frozen. Dropped siblings are not frozen, even when eligible.

**Rules common to all three candidates:**
- Universe: the 7 approved MCX commodities, front-month stitched 5-minute data resampled to bars starting 09:00 IST.
- Execution:
  - signal at the bar close, entry at the next bar's open;
  - stop checked first; a gap through the stop fills at the open;
  - one position per commodity per strategy; forced exit before a contract roll.
- Costs: MCXE-003 MCX cost model (statutory fees + 1.5 ticks slippage per side), at 1× and 2×.

| ID | Market / TF | Side | Entry | Stop | Exit | DEV 2× | VALID 2× | DEV + VALID CI (1×) |
|---|---|---|---|---|---|---|---|---|
| H1.11 | MCX 4h | BUY + SELL | close crosses above the prior 20-bar high (BUY) / below the prior 20-bar low (SELL) | 2 × ATR(14) from entry | 4 × ATR trailing stop on closes; time cap 120 bars | +0.453R (n 90) | +0.467R (n 45) | [+0.108, +0.860] |
| H1.12L | MCX 1h | BUY only | close crosses above the prior 20-bar high | 2 × ATR(14) | 4 × ATR trail; cap 240 bars | +0.578R (n 157) | +0.400R (n 70) | [+0.149, +1.069] |
| H5.2L | MCX 1h | BUY only | RSI(14) crosses above 75 (momentum: RSI stays extreme) | 2 × ATR(14) | 4 × ATR trail; cap 120 bars | +1.042R (n 73) | +0.486R (n 27) | [+0.311, +1.715] |

**Why the SELL sides of H1.12 and H5.2 were dropped:** both were negative in DEV (−0.31R, −0.40R). The pre-registered side rule therefore keeps only their BUY sides.

**Known before OOS (disclosed):**
- MCXE-004 evaluated two MCX 4h rules and the MCX day-trend shadow rule on this OOS period. Aggregate MCX positional results for OOS have not been seen.
- The two BUY-only candidates were selected in a period with strong metals rallies. Their DEV + VALID results in the "down" regime are negative.

**OOS command, run once:** `python research/mcxe006/oos.py`
