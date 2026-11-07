# MCXE-012: OI 1-hour rule – data check, SL / target design, conflict protection (7-Nov)

**Angel OI:**
- The live 1-minute WebSocket bars have OI on 100 % of minutes for the 7 MCX futures and NIFTY / BANKNIFTY. It changes on 30–97 % of minutes.
- Historical intraday OI exists via Angel `getOIData` (`angel.py oi_history`), but this research environment has no credentials. **Blocker:** a real OI backtest needs a research-data workflow run that fetches OI.

**SL / target test** (`sl_target.py`, MCX 1h, DEV / VALID, signals without OI):

| Plan | DEV 2× | VALID 2× | DEV win | Stop-outs |
|---|---|---|---|---|
| SL 1 ATR, target 3R (v1) | +0.27R (35) | −0.08R (11) | 37 % | 63 / 73 % |
| **SL 1.5 ATR, S/R-capped 3-ATR target, R:R ≥ 1.2 (v2, deployed)** | **+0.34R (36)** | **+0.01R (13)** | 53 % | 47 / 62 % |
| Swing-low stop (5 candles) | too few valid trades | — | — | — |
| Breakout-candle stop | −0.05R (22) | +0.16R (7) | 36 % | 64 % |

- Index 1h: 0 wins in 25 DEV trades across all plans. Weak, and still EXPERIMENTAL.
- **Deployed: PR #53** (`main` c2225f7).
- **PR #51 not merged.** It would revive 8 rules with these one-year verdicts: 1 PAPER_ONLY, 2 REJECTED, 1 insufficient, 4 never evaluated. It would also change call priority.
