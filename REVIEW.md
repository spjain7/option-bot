# Review of the "Master Development Prompt"

The core idea is sound: two separate engines, alerts first, and a proper no-trade engine.
But about 60% of the spec needs data or infrastructure that a free, no-install setup can't provide reliably.
Below is what was **built**, **simplified**, or **dropped**, and why.

## ✅ Built as specified
| Spec part | Where |
|---|---|
| Two fully independent engines (RSI never affects option calls) | `rsi_alert.py` vs `strategy.py` / `market.py`; each has its own on/off switch; separation is tested |
| RSI(14) 1H, <20 / >80, entry / continuation / every-hour modes, no duplicates | `rsi_alert.py` |
| RSI instruments: NIFTY, BANKNIFTY, FINNIFTY + MCX Gold, Silver, Crude, NG, Copper, Zinc, Aluminium | `config.RSI_NSE`, `config.RSI_MCX` |
| RSI statistics (forward returns after extremes), informational only | `history_stats()` |
| No hard-coded expiry, lot size, strike step or token | Angel instrument master, downloaded daily |
| Option chain: LTP, bid/ask, OI, volume, IV, delta, gamma, theta, vega | `market.build_chain` |
| IV vs realised vol → CHEAP / NORMAL / EXPENSIVE / EXTREMELY EXPENSIVE (CHEAP = no trade) | `market.iv_label` |
| IV skew (25-delta put IV minus call IV) | shown in each alert |
| Expected move (1 SD to expiry) and strike distance vs expected move | shown in each alert |
| Gamma risk LOW / MEDIUM / HIGH / EXTREME, with EXTREME blocked | `strategy.gamma_risk` |
| Liquidity: bid-ask %, minimum OI at the short strike | `strategy._liquid` |
| Single CE / PE sell, short strangle, spreads, iron condor | `SELL_STYLE` = NAKED / HEDGED |
| Entry, SL, T1/T2, risk, reward, R:R, costs, return on risk, invalidation | entry alert |
| Regime: trend / range using EMA + ADX + futures OI | `market.trend_score` |
| No-trade engine: event day, stale data, max positions, daily loss, kill switch, VIX spike | `runner.blocked` + filters |
| Alert-only mode (no execution) | the bot has no order code at all |
| Signal database + separate RSI log | `state/state.json`, `state/rsi_state.json` |
| "Never say guaranteed", uncertainty stated | every alert says "estimate" |

## 🟡 Simplified (the full version wasn't worth the complexity)
| Spec part | Simple version used | Why |
|---|---|---|
| Event-risk engine with live economic calendar | You list dates in `EVENT_DATES` | Free calendar APIs are unreliable; about 10 dates a year are easy to type in |
| 100-point weighted score (11 components) | Bias score (trend + OI + PCR) + hard pass/fail filters | Weights with no backtest are guesses dressed up as precision; pass/fail rules are clearer |
| Top-3 CE / PE strike ranking | Best strike by target delta + liquidity + OI | A delta target already captures distance, probability and expected move |
| Expected value from historical probability | R:R + delta-based probability labelled "estimate" + **real expectancy from tracked calls** (Friday report) | Probabilities without option-chain history would be made up, which the spec itself forbids |
| 5-timeframe hierarchy | 1H (intraday) + Daily (positional) | More timeframes = more conflicts and fewer signals, with little benefit |
| Dashboard | Daily Telegram report | No server needed |
| Backtest engine | Paper-tracking of every call + weekly stats | Historical NSE option-chain data isn't free |

## ❌ Dropped
| Spec part | Why |
|---|---|
| True Volume Delta / CVD (5m–daily), absorption, exhaustion | Needs tick-by-tick trade-side data. Angel's free API doesn't provide it, and the spec itself says not to fake it |
| MCX **option selling** | MCX options are thin and have different expiry and session rules. MCX is covered by the RSI engine; option selling can be added later if you want it |
| LIVE auto-execution | Needs a registered static IP (SEBI rule) and adds risk. Deliberately left out |
| Margin API / exact margin | Angel margin API needs extra permissions; max loss is shown for hedged trades instead |

## Suggested next steps (only after 3–4 weeks of paper results)
1. Tune `DELTA` / `RULES` using the Friday stats.
2. Add MCX option selling for CRUDEOIL only, if the RSI and market data look reliable.
3. Consider a small VPS (₹300–500/month) if GitHub delays of 5–15 minutes matter to you.
