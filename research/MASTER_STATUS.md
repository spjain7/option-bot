# Master instruction (10-Nov-2026) – where each section stands

Received: sections 1–26 (16–25 on 11-Nov).
Nothing here changes production. Research only, on `exp/cash-equity-engine`.

| § | Topic | Status | Where |
|---|---|---|---|
| 2 | Repository | `spjain7/option-bot` (only repo visible) | – |
| 3 | Coverage | MCX 7 commodities (no 5-min history loaded for LEAD / NICKEL), stock futures, NSE cash 2005–26 incl. delisted; index-only strategies not yet researched separately | `research/program`, `research/cashq/data.py` |
| 4 | Angel audit | Candles, volume, OI, WebSocket, limits done. Depth: 20-level deprecated by Angel (Apr-2025); best-5 recorded live from 11-Nov (PR #68), live verification pending | `research/DEPTH_AUDIT.md`, `research/mcxe013/DATA_AUDIT.md` |
| 5 | Data quality | Live checks in production (WS-vs-REST hourly verify, stale feed, OI jump cap, feed-health notice). No per-instrument quality score; no exchange holiday calendar | `wsbars.py`, `alerts/engine.py` |
| 6 | Indicators / structure | Tested: candles, chart patterns, trendlines, breakouts, VWAP, EMA, volume (MCX); momentum, breakout score, screeners (cash) | `research/mcxhw`, `research/cashq` |
| 7 | Divergence | MCX, stock futures (incl. OI divergence), index futures, cash done (10-11 Nov) | `research/mcxhw/rsi_div.py`, `research/rsidiv/` |
| 8 | RSI 75 / 25 | all four markets done (10 events, reversal and continuation, BUY / SELL apart) | `research/rsidiv/README.md` |
| 9 | Volume + OI + price | Stock futures daily OI done (0 / 33 pass). MCX has no historical OI from Angel | `research/cashq/oi_run.py` |
| 10 | Multi-timeframe | Only as a trend filter so far | – |
| 11 | Experiment registry | One registry for all markets, 37,335 rows incl. failures, rebuilt from result files | `research/registry/REGISTRY.md` |
| 12–13 | Backtest rules / gates | Costs, next-bar entry, chronological periods, FDR in place | `research/mcxhw`, `research/cashq/validate.py` |
| 14 | Trade construction | Live card has entry / SL / target / lot / expiry / WHY; no confidence or data-quality score | `alerts/candle_setups.py` |
| 15 | Regimes | Not built | – |
| 26 | Per-instrument config | Results are stored per commodity; no config hierarchy or dashboard yet | `rsi_div_by_commodity.csv` |

## MCX-RD result (10-Nov) – RSI 75 / 25 and divergence, 2,325 pooled variants, 14,535 per-commodity
DEV to 2024 · VALID 2025 · OOS 2026. PASS = profit and PF >= 1.2 in all three.
- 15 pooled variants pass; none survives the multiple-testing correction (best t = 3.6).
- RSI 75 / 25 as a REVERSAL signal loses on every timeframe (median −0.15R to −0.31R). Continuation is about flat.
- Regular divergence (the classic kind): 0 passes, any indicator, any timeframe, either side.
- All SELL variants: 0 passes. All 15-minute variants: 0 passes.
- What passes: HIDDEN bullish divergence BUY on 3-hour bars (10) and daily bars (3) – i.e. buy a higher low in an up-move.
  Best: MACD hidden BUY 3R: DEV +0.32R / VALID +0.25R / OOS +0.56R, 315 trades, 41 % wins, positive in 7 of 7 commodities.
- Baseline on the same bars, stop and target: buy every 8th bar +0.01R; any pivot low +0.10R; any higher low +0.23R;
  MACD / OBV hidden divergence +0.36R. So about two thirds of the edge is "buy higher lows in a rising market"
  (2023–26 was a rising market for metals); the indicator adds roughly +0.13R on top.
- Per commodity: only 3 of 14,535 pass (SILVER 1h MFI hidden BUY, COPPER 1h MACD hidden BUY, COPPER 1h volume hidden
  BUY) – no more than chance. There is not enough data per commodity to justify separate tuned parameters yet.

## 11-Nov update
- RSI 75/25 + divergence on stock futures, index futures and cash: `research/rsidiv/README.md`. Two shadow candidates (stock-futures SELL of the first bounce after RSI ≤ 25; cash weekly RSI ≥ 75 BUY in less-liquid stocks). Index futures: nothing.
- MCX 3-hour hidden divergence stress test: not promoted (`research/mcxhw/hidden_check.py`).
- Engine defect found by the new tests: RSI returned NaN while a series had no falling bar yet; fixed (it only affected warm-up bars, before any signal date).

## 11-Nov update (2)
- Shadow test built and scheduled (weekdays 21:47 IST, branch shadow-state): SF-CONT-SELL-v1 (CONTINUATION SELL) and CM-CONT-BUY-v1 (CONTINUATION BUY). Rules verified trade for trade against research (1,019 / 1,019 and 814 / 814). `research/shadow/README.md`.
- Investigations: SF 2026 weakness is mostly the signal itself (gross ≈ 0), plus the 0.05 % STT; on real futures prices the edge is about 0.085R lower. CM is not liquidity-limited at ₹5 lakh, overlaps the momentum portfolio only 9 %, but depends on the same market condition.
- RSI REVERSAL vs CONTINUATION study across 4 markets (6,480 cells): reversals do not survive in any market; CONTINUATION BUY is the only mostly profitable label (none passes multiple testing). `research/rsirev/README.md`.
- Registry: 43,095 rows, every RSI / divergence row labelled REVERSAL / CONTINUATION BUY / SELL.
