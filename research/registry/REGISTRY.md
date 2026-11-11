# Experiment registry – all markets (built 11-Nov-2026)

`registry.csv.gz` has 37,335 rows, one per tested variant, with failures included. It is rebuilt from each study's own result file by `python -m research.registry.build`, so nothing is typed by hand. A study whose file is missing is listed under `missing` in `registry_summary.json` (none at present).

Columns: strategy_id, study, market, timeframe, family, rule, context, side, target, result, status, rejection_reason, DEV / VALID / OOS n · win % · avg R · PF, all-period n and R, day-clustered t, multiple-testing flag, number of instruments and how many were positive, periods, cost model, script, trade file.

| Market | Study | Variants | PASS (own gate) | PASS + multiple-testing |
|---|---|---|---|---|
| MCX | MCX-HW 80-90 % win search (10-Nov) | 805 | 6 | 0 |
| MCX | MCX-RD RSI 75/25 + divergence, per commodity (10-Nov) | 14,535 | 3 | 0 |
| MCX | MCX-RD RSI 75/25 + divergence, pooled (10-Nov) | 2,325 | 15 | 0 |
| MCX | MCX-REV reversal candles (10-Nov) | 3,400 | 23 | 0 |
| NSE_CASH | CASHQ cash research engine (Nov-2026) | 2,409 | 10 | 10 |
| NSE_CASH | EQ-BTST cash buy-today-sell-tomorrow | 56 | 0 | 0 |
| NSE_CASH | RSIDIV-CM cash RSI + divergence + liquidity / RS / sector (11-Nov) | 2,805 | 29 | 11 |
| NSE_INDEX_FUT | RSIDIV-IX index futures RSI + divergence + OI (11-Nov) | 5,114 | 2 | 0 |
| NSE_STOCK_FUT | RSIDIV-SF stock futures RSI + divergence + OI + basis (11-Nov) | 5,886 | 50 | 4 |

Not listed row by row: the MCX 80–90 % win search tried 32,044 variants but saved only the 805 that passed its first test; the other 31,239 failed it. Several PASS + multiple-testing rows in the cash studies are neighbours of one effect (momentum or trend in cash), not independent discoveries.

## Status

| Status | Meaning | Count |
|---|---|---|
| research only | default | 37,333 |
| candidate for shadow testing | passed its gate, the multiple-testing control AND a separate stress test (placebo, neighbours, slippage, years, regime) | 2 |
| approved for production | none | 0 |

| ID | Market | TF | Rule | Side | Target | R by period DEV / VALID / OOS | Trades | t |
|---|---|---|---|---|---|---|---|---|
| S-8c4cd5ed71 | NSE_STOCK_FUT | 1d | break5:continuation · zone25 | SELL | 3.0R | +0.17 / +0.41 / +0.32 | 1019 | 4.04 |
| S-bc092ab892 | NSE_CASH | 1w | cross_in:continuation · zone75|liq_bottom | BUY | 1.0R | +0.17 / +0.10 / +0.15 | 709 | 4.09 |

**Stress-tested and NOT promoted:** MCX 3-hour hidden bullish divergence BUY (`research/mcxhw/results/hidden_check.json`).
- Its t of 3.3 is below the Bonferroni bar of 4.7 for the ~37,800 MCX variants tried.
- It fails with pivot K = 2.
- Energy makes about 0R; it works only in metals in a rising market.
- The divergence adds +0.14R over any higher low; 4 % of random higher-low subsets do as well.

**Live today as EXPERIMENTAL (production, already approved by the owner, not from this registry):** MCX daily hammer BUY, MCX gold/silver intraday day-trend, cash scored breakout, plus the existing PETRONET / GLENMARK / TITAN strategies.

Trade-level files: `research/rsidiv/results/*_trades.csv.gz`, `research/rsidiv/results/*_check_trades.csv.gz`, `research/mcxhw/results/hidden_check_trades.csv.gz`, and `research/cashq/results/ledger_*.csv`.
