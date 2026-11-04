# E_BUY_v1 – compression breakout BUY (MCX, 1-hour) – FROZEN 4-Nov-2026

Status: **PAPER_ONLY** (recorded in `alerts-state` → `state["paper"]["E_BUY_v1"]`, never sent; every Telegram sender
refuses text with the `PAPER_ONLY` marker – `paperguard.py`). Code: `alerts/paper.py`. Rules below are the code's rules;
any change creates `E_BUY_v2`, this version is never edited.

## Rules
- Universe: MCX CRUDEOIL, NATURALGAS, GOLD, SILVER, COPPER, ZINC, ALUMINIUM front month; completed 1-hour candles,
  roll-adjusted; contract-switch day skipped; contracts without valid volume skipped (never assumed zero).
- Signal on candle i: ATR14 < 0.8 × its 100-candle median on each of candles i-4…i; close[i] > highest high of the 20
  candles before i; volume[i] ≥ 1.5 × the 20-candle average before i; RSI14[i] ≥ 60.
- Entry: open of candle i+1. Stop: close[i] − 1.5 × ATR14[i]. R = entry − stop, valid only if 0 < R ≤ 6 ATR.
- Exit: half at T1 = entry + 1R (stop → entry), rest at T2 = entry + 2R; time stop 30 candles at the close; a candle that
  touches the stop and a target counts as stop. Costs 0.04 % of entry per round trip. One open trade per commodity.
- MFE / MAE: from 1-hour candle highs / lows after entry (not tick data).

## Evidence so far (research RSIFAM-001, branch exp/icss-backtest) – NOT independent
| Period | Trades | T1 hit | Profitable | Expectancy | PF |
|---|---|---|---|---|---|
| Jul-2022 – Dec-2024 | 72 | 58 % | 58 % | +0.10R (95 % CI −0.15…+0.36) | 1.21 |
| Jan-2025 – Oct-2026 | 102 | 63 % | 62 % | +0.29R (95 % CI +0.07…+0.50) | 1.74 |

Limitations: the BUY/SELL split was chosen after seeing pooled results; 2025-26 RSI behaviour had been examined in
earlier studies (RSIREV-001, RSIPAT-001); 2025-26 was a strong metals up-trend; ALUMINIUM was negative in both periods.

## Periods already examined (cannot be used as untouched evidence)
MCX 1-hour data Jul-2022 → 21-Oct-2026 (all of it). **Untouched evidence = prospective paper trades from 5-Nov-2026.**

## VAL-EBUY-001 – prospective validation (pre-registered 4-Nov-2026)
- Sample: first 30 closed paper trades (or 6 months, whichever first). Overlap: one trade per commodity at a time.
- Measure: mean net R after costs (stop-first, as above); also median R, T1 hit, profitable %, PF, max drawdown in R,
  longest losing streak, share of total R from the best 3 trades, results by commodity.
- Pass (all): mean net R > 0; PF ≥ 1.2; no single commodity > 40 % of trades; total R still > 0 without the best 3 trades;
  max drawdown ≤ 6R.
- Pass → propose live alerts in a reviewed PR (graded, with the risk warning). Fail → REJECTED, recorded here; no retuning
  of v1 on the same trades.
