# Crude Oil experiment registry

Every experiment is recorded here BEFORE it runs, failed ones included. Results go to `crude/research/results/<id>/`
(manifest.json with code revision, data hash, config and costs; results.json; trade lists) – never to the paper ledger.

| ID | Registered | Question | Data | Status | Verdict |
|---|---|---|---|---|---|
| EXP-000 | 21-Oct-2026 | Original intraday (15m+1h) and positional (3h) rules, fixed parameters | Angel CRUDEOIL 15m, 12-Oct-2020 → 21-Oct-2026 | done (`crude/BACKTEST.md`) | FAIL (−0.19R intraday; positional 1 trade) |
| EXP-001 | 21-Oct-2026 | Does a pre-entry regime filter improve intraday out of sample? | same as EXP-000 (**already examined → exploratory only**) | registered | – |

## EXP-001 – frozen definitions (do not edit after the run)
- **A baseline**: intraday engine exactly as in `crude/config.py` 1.0.0.
- **B regime filter**: new entries only if the regime of the signal session is `uptrend/high-vol`.
- **C long-only control**: BUY entries only, no volatility restriction.
- Regime of session d (computed only from sessions ≤ d−1):
  trend = adjusted daily close > SMA100 of adjusted daily closes (≥ 60 obs) → uptrend, else downtrend;
  volatility = Wilder ATR20 of adjusted daily bars ÷ **real** daily close; high-vol if above its rolling 250-session median (≥ 100 obs).
- Research correction applied to all variants: no entries on a contract-switch day (that day's roll-gap estimate needs its close).
- Identical data, fills (next open + 2 ticks), stops, targets, sizing (0.25% of ₹5 L on CRUDEOILM), costs, expiry policy.
- Reported: 1×/2×/3× costs, 0/2/4/6 ticks slippage, 10% missed fills (3 seeds), year/regime/side splits,
  anchored walk-forward (frozen params, yearly steps), rolling 12-month windows, bootstrap CI (5,000 resamples, seed 7),
  neighbour stability for B (SMA 80/120, median 200/300) – stability only, never used to choose.
- Acceptance (research/CRITERIA.md): ≥ 50 trades, expectancy > +0.10R, bootstrap p5 > 0, PF ≥ 1.20, positive at 2× costs,
  positive anchored walk-forward. B was found by looking at this same history → at best **PAPER-CANDIDATE**, never PASS.
- Not deployed automatically, whatever the result.
