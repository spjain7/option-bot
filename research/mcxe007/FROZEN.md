# MCXE-007 frozen candidate (committed BEFORE any MCXE-007 OOS computation)

**Experiments:** 202 register rows (101 experiments × BUY / SELL), DEV + VALID only, with OOS masked in `engine7.run`. Exactly one row met every pre-registered freeze test:
- sample size;
- 2× expectancy > 0 in DEV and in VALID;
- DEV + VALID CI lower bound > 0;
- top-5 removal ≥ 0;
- instrument share ≤ 50 %;
- beats the random-entry control and the market-direction control.

## SE_failed_oiup_h/L: stock futures, failed breakdown → BUY, OI rising on the reclaim day, beta-1 NIFTY hedge

**Market and data**
- Universe: NSE stock futures, point-in-time front month (all FUTSTK symbols with in-window data); daily bars.

**Entry**
- **Signal (close of day t):**
  - within the last 3 sessions the stock closed below its prior 20-day low (a breakdown);
  - today it closes back above that level, the first close back above it;
  - and the exchange OI of the same contract rose today versus yesterday.
- **Entry:** BUY the stock future at the next session's open.
- **Hedge:** at the same open, SELL an equal notional of NIFTY front-month futures (beta 1). The hedge is closed at the close of the day the stock position exits.

**Exit (stock leg)**
- Stop 2 × ATR(14) from entry; a gap through the stop fills at the open.
- 4 × ATR trailing stop on closes.
- Exit after 40 sessions, or before the contract roll.
- No trade spans a roll.

**Costs**
- Stock leg: fees + 0.05 % per side.
- Hedge: NIFTY fees + 1 index point per side.
- All results are also shown at 2×.

**DEV + VALID results**

| | DEV | VALID |
|---|---|---|
| Trades / dates | 140 / 31 | 65 / 25 |
| Win % | 51.4 | 53.8 |
| Avg win / loss (R) | +0.90 / −0.50 | +0.73 / −0.55 |
| Exp 1× / 2× (R) | +0.223 / +0.185 | +0.143 / +0.104 |
| Profit factor | 1.92 | 1.57 |
| Max DD (R) | 5.6 | 3.5 |

- **DEV + VALID combined:**
  - CI (1×) [+0.040, +0.356]; without the top 1 / 3 / 5 trades: +0.147 / +0.124 / +0.104 (2×).
  - Largest single stock: 9 % of net R. Largest single month: 45 % of net R (concentration flag).
- **Controls (DEV + VALID):**
  - random hedged entries (same stocks, counts, periods, exits): −0.057R (95th percentile +0.018R);
  - NIFTY on the same dates: −0.44R.
  - The strategy: +0.159R.

**Disclosed selection issues**
1. **The hedge was added after the unhedged version showed a stock-specific edge** (+0.3R above random longs). Under the expectancy keep/drop rule it is labelled DROP vs its unhedged parent, because the hedge removed VALID's rising-market drift.
   - It is frozen because the pre-registration requires rejecting edges explained by market exposure, and the hedge is the direct test of that.
2. **The OI-up filter was chosen over OI-down and no filter** (3 siblings).
3. **The NSE futures OOS regime is known** (MCXE-005: falling stocks). So the best possible outcome is PAPER_ONLY.
4. **Execution approximations:**
   - the hedge exit uses the NIFTY close of the stock's exit day, even when the stock stops intraday;
   - NIFTY lot granularity (about ₹16 lakh notional per lot) makes an exact 1:1 hedge impossible for most stock lots.

**OOS command, run once:** `python research/mcxe007/oos7.py`
