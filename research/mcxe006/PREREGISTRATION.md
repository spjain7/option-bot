# MCXE-006 pre-registration (written 2026-11-07, before any MCXE-006 result)

## Data, windows and safety
- Only the approved MCXE-004 one-year windows (`research/mcxe004/windows.json`): DEV 6 months, VALID 3 months, OOS 3 months per market.
- Indicators are computed on clipped data only. A strategy's warm-up is its longest lookback + 10 bars.
- **OOS masking:**
  - During development, `engine.py` drops every signal in the OOS period before simulation, so OOS trades are never computed.
  - OOS is computed only by `oos.py` on the frozen list, and only once.
- Research only. Production (`main` bc3153e6, S4 logic for PETRONET / GLENMARK / TITAN) is untouched. The preservation tests are re-run before and after.

## What MCXE-005 taught (DEV + VALID trade-level diagnosis, `diagnose.py`)
1. **Intraday cells have small positive gross edges but lose to costs.**
   - Gross edge: MCX intraday +0.04 to +0.15R; stock futures and NSE cash +0.01 to +0.04R.
   - Costs: 0.12–0.32R per trade, because the stops (1–1.5 × bar ATR on 15–60-minute bars) are small relative to fixed costs.
   - Main lever: wider, structure-based stops (daily-ATR or opening-range) and fewer, longer trades. Not more filters.
2. **MCX positional trend-following is net positive in both DEV and VALID when both sides are traded.**
   - Longs earned in DEV, shorts in VALID.
   - MCXE-005 judged each family, side and setting as a separate small cell, so the significance tests had no power.
   - Lever: a two-sided commodity trend portfolio.
3. **Stock-futures daily rules flipped sign between DEV and VALID** (market regime).
   - Lever: market-level breadth to choose the side (do not buy in a falling market or sell in a rising one).
4. **NSE cash daily BUY-only positional was positive in DEV and VALID** (long drift).
   - Lever: buy pullbacks inside uptrends (mean reversion in trend) to improve entry timing.

## Hypotheses (families) and baselines
- **H1 MCX trend portfolio** (1h / 4h / 1d; 7 commodities; long and short):
  - Baseline: 20-bar Donchian close breakout, 2-ATR stop, 3-ATR trailing stop, time cap.
- **H2 MCX intraday, cost-aware** (15m / 30m):
  - Baseline: opening-range breakout (first 60 minutes) with the stop at the other side of the range and exit at session end.
  - Variants: previous-day high/low breakout; daily-trend alignment; VWAP-pullback continuation.
- **H3 NSE stock futures positional, regime-aware:**
  - Baseline: pullback to EMA20 inside an EMA20 > EMA50 trend with ADX ≥ 20, both sides.
  - Variants: market breadth filter for the side; breakout + volume + OI build-up.
- **H4 NSE cash daily pullback-in-uptrend (BUY):**
  - Baseline: RSI(2) < 10 while close > EMA50; exit when close > EMA5 or after 10 days; 2.5-ATR stop.
- **H5 RSI reversal** (MCX 1h / 4h, NSE futures daily, NSE cash daily):
  - Baseline: RSI(14) crosses back inside 75/25.
  - Variants: 80/20; reversal-candle confirmation; range-regime only (ADX < 20); trend-aware (only with the higher trend).
- **H6 Candle at support / resistance:**
  - Baseline: hammer or bullish engulfing within 0.5 ATR of the 20-bar low (mirror for SELL).
  - Variant: confirmation, i.e. a break of the pattern high on the next bar.
- **H7 NSE cash intraday ORB** (15m) with the opening-range stop and session exit; variants for volume and trend.
- **H8 Overnight (BTST / STBT) on stock futures:**
  - Baseline: close in the top or bottom 10 % of the day's range on volume > 1.5×, exit at the next open.
- **H9 Hybrids** of the components that survive the steps above.

Long and short sides are always reported separately. A two-sided strategy is frozen as two-sided only if each side is ≥ 0 at 2× cost in DEV and in VALID; otherwise only the surviving side is frozen.

## Iteration rule
1. Every experiment is appended to `EXPERIMENT_REGISTER.csv` with its parent experiment, the one component changed, DEV and VALID metrics at 1× and 2× cost, and the decision.
2. A change is **kept** only if it raises DEV 2× expectancy **and** does not lower VALID 2× expectancy.
3. A change is also kept if it leaves both about the same but cuts drawdown or the cost share.
4. Parameter values come from small, economically motivated sets (for example, trail 2 / 3 / 4 ATR). No fine grids.

## Freeze rule (before OOS)
- Required:
  - DEV and VALID each have ≥ 30 trades on ≥ 20 dates (intraday or overnight) or ≥ 20 trades on ≥ 15 dates (positional);
  - expectancy at 2× cost > 0 in both;
  - the combined DEV + VALID day-clustered conservative 95 % CI lower bound is > 0.
- At most **8** candidates are frozen. If more qualify, the 8 with the highest combined t-statistic are taken. At most 2 per family.
- The frozen list (rules, parameters, code commit) is committed before OOS is run.

## OOS decision (run once)
- `research/mcxe004/register.classify`: minimum OOS sample, expectancy > 0 at 1× and 2×, and CI lower bound > 0.
- A BH adjustment across the frozen candidates is reported alongside.
- **Contamination disclosures:**
  - **NSE stock futures and NSE cash daily OOS:** MCXE-005 already revealed the falling-stock regime of the NSE futures OOS period. Candidates from these markets are flagged `selection_overlaps_window=True`, so PAPER_ONLY at best.
  - **MCX:** MCXE-004 evaluated two MCX 4h rules and the MCX day-trend shadow rule on MCX OOS. Aggregate MCX positional and intraday OOS results have not been seen.
- **Outcomes:**
  - A candidate that passes is eligible for **forward paper tracking only**.
  - Nothing is promoted to production without the owner's explicit approval.
