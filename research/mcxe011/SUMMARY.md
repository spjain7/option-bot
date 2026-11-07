# MCXE-011: 15-minute / 1-hour breakout-breakdown screen (exploratory; DEV + VALID only)

**Result: no candidate.** 10 rules were screened (`RESULTS.csv`); none met the freeze bar.

| Market / rule | DEV 2× | VALID 2× | Why it fails |
|---|---|---|---|
| MCX 15m Donchian-20 / 40 / 80 BUY, 4-ATR trail | +0.16 / +0.23 / +0.31R | −0.19 / −0.17 / −0.06R | Sign flips: commodity regime, not the rule |
| MCX 15m Donchian-20 / 40 / 80 SELL | −0.22 / −0.19 / −0.10R | +0.17 / +0.26 / +0.19R | Mirror flip |
| Stock futures 1h Donchian-20 / 40 BUY | −0.23 / −0.09R | −0.31 / −0.34R | Breakouts fail in this window |
| Stock futures 1h Donchian-20 / 40 SELL | −0.25 / −0.25R | −0.38 / −0.43R | Breakdowns fail too |

**Earlier tests of 15m / 1h breakouts, all failed:**
- MCXE-005: same-day Donchian, ATR breakouts and NR7 on MCX 15m / 30m, NSE cash 15m / 1h and stock futures 1h;
- MCXE-006: MCX 15m opening-range breakout, previous-day high/low and VWAP pullback;
- MCXE-007: NSE cash opening-range breakout;
- MCXE-008: index futures 1h trend.

**The only 1h breakout that held up is H1.12L** (MCX 1h, BUY only), which is already live as EXPERIMENTAL.

**Run:** `python research/mcxe011/intraday_bo.py`
