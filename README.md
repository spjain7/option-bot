# Option-Selling Bot + Independent RSI Alerts (cloud, no install)

Two **separate engines** run free on GitHub Actions and send alerts to Telegram (and optionally WhatsApp).
The bot sends **alerts only**; it never places orders. Data comes from the free Angel One SmartAPI.

| | Engine A: Option Selling | Engine B: RSI Extreme Alerts |
|---|---|---|
| Markets | NIFTY, BANKNIFTY, F&O stocks | NIFTY, BANKNIFTY, FINNIFTY + MCX (Gold, Silver, Crude, NG, Copper, Zinc, Aluminium…) |
| Output | Naked single CE / PE sell calls (index, stock, MCX) with sell price, target, stop-loss, price-stop and exit time; then book / stop / exit alerts | "RSI < 20" or "RSI > 80" on 1-hour candles, information only |
| Module | `strategy.py` `market.py` `positions.py` | `rsi_alert.py` |
| Switch | `OPTION_ENGINE_ENABLED` | `RSI_ENGINE_ENABLED` |

RSI **never** touches the option engine: no score, no direction, no strike, no entry.
The two modules don't import each other; they share only market data and Telegram. This is tested in `tests/simulate.py`.

## Engine A: when a call is sent (default: NAKED single-leg sells)
- Confidence score must be **≥ 70/100** (trend, futures OI, PCR, rich premium, strike beyond the OI wall, gamma).
- **Intraday:** the same direction must show on **2 hourly checks in a row**, so there's never an instant call.
- **Reward ≥ risk:** intraday target −35% / SL +35%; weekly and monthly −50% / +50%.
- An extra **price stop** triggers if the underlying moves half-way to your sold strike.
- Lot suggestion is capped by 2% risk **and** by estimated margin (≤ 50% of capital).

## Engine A: how a sell call is made (details)
1. **Regime / direction:**
   - trend from EMA (1-hour for intraday, daily for positional), with **ADX < 18 treated as RANGE**
   - futures **OI buildup**
   - option-chain **PCR**

   The result is BULLISH, BEARISH or NEUTRAL.
2. **Structure**, with `SELL_STYLE` in config:
   - **HEDGED** (default): Bull Put Spread / Bear Call Spread / Iron Condor
   - **NAKED**: Single PE Sell / Single CE Sell / Short Strangle
3. **Strike by delta**, using IV and Greeks the bot calculates itself (Black-76). The short strike needs OI of at least 500 and a bid-ask spread under 8%.
4. **No-trade filters.** No call is sent when any of these apply:

   | Filter | Blocks a call when |
   |---|---|
   | IV vs realised volatility | Options are **CHEAP** (IV < 0.9 × RV) |
   | Gamma risk | **EXTREME** (expiry day with the short strike inside the expected move) |
   | India VIX | Up more than 8% today. Condors are also blocked when VIX is very low |
   | Event dates | The event day. Weekly and monthly calls are also blocked the day before. You add the dates in config |
   | Data | Quote is stale or missing |
   | Risk limits | Maximum open positions reached, or daily loss limit hit |
   | Kill switch | Option engine turned off in config |

5. **Every alert shows:**
   - legs, credit and costs
   - max loss (hedged) or UNLIMITED (naked)
   - risk and reward to SL/target, and R:R
   - breakeven and probability of profit (delta-based estimate)
   - **expected move** and how far the short strike sits from it
   - **gamma risk** and **IV vs RV label**
   - **IV skew**
   - position Greeks and suggested lots
   - an **invalidation level**
6. **Management (every 15 min):**
   - book profit at 50–60%
   - stop-loss when the value reaches 2× the credit
   - adjust alert when the short-leg delta reaches 0.35–0.40
   - time exits
7. **Friday report:** win rate, average win and loss, profit factor, expectancy and longest losing streak.
   This is the *real* measure of the strategy, built from its own tracked calls.

## Engine B: RSI alerts
- RSI(14) on **closed** 1-hour candles.
- Alerts when RSI < 20 or > 80.
- Mode is `entry_and_continuation` (default), `entry` or `every_hour`.
- Each alert adds past statistics (average and median return 3h and 6h after similar extremes, and % of cases up), clearly marked "stats only".
- Runs for MCX in the evening too (hourly until 11 PM).

## Setup
See **SETUP_GUIDE.md**. It needs only a browser, takes about 30 minutes, and runs on GitHub's free tier (about 1,300 of the 2,000 free minutes a month).

Not investment advice. All numbers are estimates. Paper-trade for 3–4 weeks first, and keep stop-loss orders at your broker.

## Engine C: MCX Buy / Sell alerts (futures + option buying)
Module `mcx_trade.py`, switch `MCXT_ENABLED`, state `state/mcx_trades.json`. Alerts only.
- **Markets:** GOLD, SILVER, CRUDEOIL, NATURALGAS (mini contract lots shown too), COPPER, ZINC, ALUMINIUM.
- **BUY:** price > EMA20 > EMA50 and above EMA200 (1H), ADX ≥ 20, close breaks the last 5-hour high, RSI 55–75, volume ≥ 1.2×. **SELL** is the mirror.
- **Plan:** entry at live price, SL beyond the 5-hour swing (1–2 ATR), T1 = 1R (book half, SL to cost), T2 = 2R, exit all by 23:00.
- **Option idea:** buy ~ATM CE (BUY) / PE (SELL) on the nearest liquid expiry; exits follow the future, plus a 40% premium stop.
- Lots sized to risk 1% of capital. Daily summary after 23:00.
- Manual scan now: Actions → Run workflow → mode `mcxtrade`. Telegram check: mode `chatid`.
- Test offline: `python tests/sim_mcx_trade.py`

## 👀 Pre-move watch (early warning, information only)
Before a move, price often stays unusually quiet while open interest and volume keep rising (positions being built).
Every 15 min the bot checks the last hour of futures snapshots: price range ≤ 0.15% (index) / 0.4% (stock) / 0.3% (MCX),
OI up ≥ 1% / 2% / 1.5%, volume ≥ 1.3× the day's pace. Near the day high/low the alert says which break to watch.
It is **not a call** and cannot predict direction. Each alert is tracked for 2 hours against a random script of the
same kind (control); the daily report shows both hit rates. Settings: `PREMOVE_*` in `config.py`; tests: `tests/test_premove.py`.

## 🟢 Option-BUY alerts (TEST PHASE, Engine E)
Separate from the selling bot (`obuy/`, state on branch `obuy-state`). Only the two setups that did best on real option
prices last month (`research/search/obuy_month.py`):
- **Intraday (stocks):** VWAP cross + RSI ≥ 60 / ≤ 40 + OI and price rising/falling over the last hour, 9:30–14:30. SL −30%, target +60%, exit 15:15.
- **Positional (stocks + indices):** yesterday's close beyond the 20-day high/low with 1.5× volume and OI up. SL −35%, target +80%, exit on the 3rd session.

ATM option, nearest monthly expiry with ≥ 3 days left; skipped if not traded today or spread > 3%. Every alert is tracked
with real option prices (SL / target / time exit) and a scorecard is sent after 15:30. The edge is small and unproven live:
use 1 lot or paper-track. Tests: `python -m obuy.tests.test_obuy`.
