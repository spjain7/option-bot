# STOCK-CHECK-001 – live volume-breakout rule on NSE stock futures (lot < 3000) → FAIL, stock alerts switched off
Real Angel 1-hour history, Jul-2022 → Oct-2026, 181 stock futures. The rule is unchanged from the live alerts, so this
is a true out-of-sample test. Costs: brokerage, STT, exchange charges, stamp duty, GST and 0.03% slippage per side.
| Timeframe | Trades | Stocks | Avg R | 2× costs | Win % | PF | Bootstrap p5 | Halves (≤Jun-24 / ≥Jul-24) | Max DD |
|---|---|---|---|---|---|---|---|---|---|
| Daily | 2,298 | 163 | +0.030 | +0.011 | 46 | 1.08 | −0.011 | +0.056 / +0.015 | −79R |
| 3-hour | 4,964 | 175 | +0.013 | −0.016 | 41 | 1.03 | −0.017 | +0.005 / +0.018 | −139R |
- The result is roughly break-even: about half of the stocks are positive and half negative.
- Picking only the "best" stocks (LODHA, RELIANCE, …) would be curve-fitting, so it was not done.
- Stock alerts are disabled in `alerts/stocks.py` (`ENABLED = False`). Commodities and NIFTY/BANKNIFTY keep running.
