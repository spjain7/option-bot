# STOCK-OI-001 – volume + OI + support/resistance + trend + RSI on stock futures → 1 rule PASSES
60 pre-registered combinations, 16 shortlisted on the design period (Jul-2022 → Jun-2024), and 1 passed the unseen hold-out (Jul-2024 → Oct-2026).

**PASS: OI breakout, both directions (daily candles)**
- **BUY:** close above the 20-day high (resistance broken), volume > 1.5× the 20-day average, price up with OI up ≥ 2% (long buildup), above EMA200.
- **SELL:** close below the 20-day low (support broken), volume > 1.5×, price down with OI up ≥ 2% (short buildup), below EMA200.
- **Risk:** stop 2 ATR, then a 3-ATR trailing stop; exit by expiry; OI ignored around rollover days.

| Period | Trades | Avg R | 2× costs | Win % | PF | Bootstrap p5 |
|---|---|---|---|---|---|---|
| Design | 275 | +0.195 | +0.175 | 48 | 1.47 | +0.056 |
| Hold-out | 638 | +0.085 | +0.066 | 47 | 1.20 | +0.002 |

- **By year:** 2023 +0.52 · 2024 +0.08 · 2025 +0.00 · 2026 +0.16.
- **Breadth and frequency:** 156 stocks, about 25 alerts per month, max drawdown −28.5R.
- **Longs and shorts take turns.** Longs earned in the 2023-24 bull market (+0.24R) and lost in the hold-out (−0.06R). Shorts lost in design (−0.22R, 29 trades) and earned +0.34R in the 2024-26 weakness. Use BOTH sides.

**Caveats:**
- Only 1 of 16 shortlisted rules passed, and its hold-out p5 is barely above 0, so the edge is modest and could partly be luck.
- The higher-scoring design rules (OI trend, OI pullback) failed or had too few trades.
