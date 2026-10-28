# LIVE-AUDIT-001 (28-Oct-2026) – live futures rules, in R, 1×/2× costs

Script: `research/search/live_audit.py` · trades: `results_live_audit/trades.csv.gz` · full breakdown: `results_live_audit/summary.txt`
Fills: next-candle open, stop checked before target, gap through stop fills at open. Design < 2024-07-01 ≤ hold-out.

| Rule (with live stop cap) | Trades | Win % | Exp 1× | Exp 2× | PF | Max DD (R) |
|---|---|---|---|---|---|---|
| S1 3h breakout | 562 | ~43 | +0.123 | +0.05 | ~1.2 | — |
| S2 daily breakout | 105 | 49.5 | +0.512 | +0.467 | 1.99 | 12.9 |
| S3 monthly breakout | 166 | ~50 | +0.245 | +0.201 | ~1.5 | 8.1 |
| S4 stock OI breakout | 681 | ~45 | +0.024 | +0.004 | ~1.05 | — |
| S5 stock bear engulf | 127 | ~61 | +0.158 | ~+0.13 | ~1.5 | — |

By side (hold-out, exp 1×): S1 BUY +0.24 / SELL −0.08 · S2 BUY +0.52 / SELL +0.12 (n16) · S3 BUY +0.26 / SELL −0.30 (n9) · S4 BUY −0.16 / SELL +0.31 · S5 SELL +0.23.

Limits: S1–S3 exit settings were picked with the hold-out visible (PAT-002/SR-001) → hold-out not clean. S2/S3 SELL samples tiny. S4 BUY decays to negative after 2024. S5 hold-out was a falling market. No rule reaches 80–90 % wins; none should be judged on win rate alone.
