# CASHQ data-quality and coverage report (10-Nov-2026)

| source | coverage | used for | quality checks | known limits |
|---|---|---|---|---|
| NSE cash bhavcopy (official, `research/data/nse_cm`, raw kept as downloaded) | 2005-01-03 … 2026-11-05, 5,393 sessions, 5,742 securities | daily / weekly positional, BTST, OI trades (cash prices) | no duplicates, no non-positive prices; 306 weekdays without a file = holidays; 35,010 corporate-action factors from NSE's adjusted PREVCLOSE (2,456 split / bonus-like); UDiFF (Jul-2024+) unadjusted PREVCLOSE fixed by > 40 % open gaps; 29 unexplained gaps > 40 %; ISIN continuity across symbol changes; 539 ETF / fund units removed | **3,029 delisted / suspended securities included → no survivorship bias**; no delivery quantity / delivery % in the files we hold (→ delivery strategies BLOCKED); circuit limits not in the file (proxy: next session high = low → no fill) |
| Point-in-time universe | each day: 60-session median turnover (to t−1) ≥ ₹25 cr, close ≥ ₹50, ≥ 250 sessions of history → 997 securities ever eligible | all daily tests | rank / RS computed only within that day's eligible set | turnover threshold is nominal ₹ (fewer stocks before ~2010) |
| NSE futures bhavcopy (`research/data/nse_fut/days`) | 2011-01-03 … 2026-10-19, 3,895 sessions, every expiry with OI and change in OI | F&O OI family (exact near contract, roll week excluded) | matched to cash by (date, symbol) | F&O list changes over time (handled: only days with a futures contract) |
| Angel NSE cash 5-minute (`research/data/angel/NSE_EQ`) | 218 stocks, 2024-10-14 … 2026-11-06 (≈ 513 sessions, 75 bars/day) | intraday 5 / 15 / 30 / 60 min (resampled, complete bars only) | 0 duplicates, 0 invalid OHLC, 2 short days (Muhurat) and ~12 off-session rows per stock removed; split / bonus jumps adjusted (eq_data.adjust_splits, logged) | **survivorship / selection bias: today's liquid stocks only** (results biased upward); only ~2 years → DEV 12 m / VALID 6 m / OOS 7 m |
| Market index | equal-weight index of the 100 most-traded stocks (PIT, from the bhavcopy) | regime filter, RS | – | NIFTY index history not in the files; the proxy is used |
| Sector classification | **not available** (Angel master has none; historical NSE sector map not stored) | – | – | sector-strength / sector-leadership tests **BLOCKED** |

Timestamps: IST, bar start; a signal is known at the bar's close; entries at the next bar's open. Raw files are never modified;
adjusted series exist only in memory / `nse_cm/_adjusted.pkl`.
