# Audit of existing scripts (21-Oct-2026)

| Script | What it is | Historical profitability validation? |
|---|---|---|
| `mcx_trade.py` | **Live signal generator** (Engine C, MCX buy/sell + option-buy ideas) and paper-tracker of its own calls | None before this project. Its rules were written without a backtest. |
| `strategy.py` | **Live signal generator** for option selling (strike choice by delta, spreads, naked sells) | **None.** No historical option-chain data exists in the repo; never backtested. |
| `market.py` | Data + indicator helpers for the live engines (chain, IV/Greeks, PCR, OI walls, EMA/ADX trend, pivots) | Not a strategy; not validated. |
| `flow.py` | **Live alert generator** (OI/volume buildup, big-move alerts) and fast-track trigger for option calls | **None.** |
| `rsi_alert.py` | **Live informational alerts** (RSI < 20 / > 80). Shows past-90-day forward-return stats in the message | Descriptive stats only; not a strategy backtest. |
| `positions.py` | Paper-tracking of live option calls (targets, stops, P&L tally, weekly expectancy) | Records **live paper results** going forward; not a historical backtest. |
| `tests/simulate.py` | **Unit/integration simulation** with a fake Angel API and synthetic Black-Scholes prices | Checks code paths only. **Not** a profitability test. |
| `tests/sim_mcx_trade.py` | **Unit simulation** of Engine C on synthetic candles | Checks code paths only. **Not** a profitability test. |
| `backtest/bt.py` | **Historical backtest** of Engine C rules on Yahoo hourly futures (proxy), 2024-26 | Yes, but proxy data; Yahoo series not back-adjusted (roll jumps); bars start at :30 IST (MCX bars start at :00); flat 0.03%/side cost; no contract-level execution; exit 22:30. Signal logic verified identical to `mcx_trade.signal` on 100 sampled bars. |
| `backtest/variants.py` | 10 parameter variants of `bt.py`, split at 1-Oct-2025 | Yes (proxy), but both halves were inspected → no untouched holdout remains. |
| `backtest/daily.py` | **Historical backtest** of daily Donchian / RSI(2) systems on Yahoo daily futures (proxy) 2005-26 | Yes (proxy). Unadjusted continuous series (roll gaps cause false breakouts/stops, worst for NATURALGAS); channel exits filled at the **same** close that triggered them (slightly optimistic); flat 0.05%/side costs; 2018-26 holdout was inspected and used to choose C. |
| `backtest/fetch_data.py` | Yahoo downloader for the above | — |

## Findings
1. Before this project, **no live engine had any historical profitability validation**: option selling (Engine A),
   flow alerts and MCX buy/sell (Engine C) were all rule-based without backtests. RSI alerts are informational.
2. The only backtests (`backtest/`) use proxy data, unadjusted continuous series and simplified costs; their holdouts
   are no longer untouched (disclosed in `CRITERIA.md`).
3. MCX historical data: MCX's own bhavcopy blocks automated access. Angel One serves a vendor-stitched front-month
   history (daily from 2006, hourly from Jul-2022) on the nearest contract's token, but it is not back-adjusted and has
   no MCX OI history.
4. NSE index futures have complete REAL end-of-day contract data (bhavcopy, with volume and OI) back to 2011.
