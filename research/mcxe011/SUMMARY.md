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

## MCXE-011b: volume / OI / ADX / VWAP confirmation filters (`filtered_bo.py`, `FILTERED_RESULTS.csv`; exploratory)
- **Filters** (all known at the signal close):
  - volume ≥ 1.5× its 20-bar average;
  - close beyond the session VWAP;
  - ADX(14) ≥ 20 with the DI aligned to the side;
  - the previous session's exchange OI build-up in the trade direction. Intraday OI history does not exist, so this uses the last known daily OI.
- **Tested on:** MCX 1h (BUY = the live H1.12L entry), MCX 15m Donchian-80 and stock futures 1h, each side separately.
- **Only ADX ≥ 20 + DI alignment improved MCX 1h BUY in both periods:** DEV +0.49 → +0.53R, VALID +0.25 → +0.38R (2×), VALID win rate 36.8 → 42.6 %, with 22 % fewer trades.
  - Like the unfiltered rule, it does **not** beat the 95th percentile of random MCX long entries with the same exits (2025-26 metals uptrend).
  - It is a forward hypothesis, not a validated improvement.
- **Volume and VWAP** raised DEV but lowered VALID.
- **OI** flipped hard: VALID −0.28R.
- **All four together** cut trades to 24 in VALID and lost (−0.76R): over-filtering.
- **MCX 15m and stock 1h:** no filter changed the sign. Both stay failed.
