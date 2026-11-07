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
- **All filters at once (owner request), compared with no filter, VALID at 2×:**

  | Market / side | No filter | All four filters | Vol + VWAP + ADX (no OI) |
  |---|---|---|---|
  | MCX 1h BUY | +0.25R | −0.76R | +0.14R |
  | MCX 1h SELL | +0.34R | −0.18R | +0.43R (DEV −0.31R) |
  | MCX 15m BUY | −0.06R | −0.34R | −0.09R |
  | MCX 15m SELL | +0.19R | +0.15R | +0.26R (DEV −0.10R) |
  | Stock 1h BUY | −0.31R | −0.33R | −0.29R |
  | Stock 1h SELL | −0.37R | −0.39R | −0.37R |

  - Nothing qualifies.
  - Stacking filters cuts trades 50–85 % and does not improve the rules. On MCX 1h BUY it makes them worse.

## MCXE-011c: RSI crossing its 14-SMA + VWAP (owner idea; `rsi_ma_vwap.py`, `RSI_MA_VWAP_RESULTS.csv`; exploratory)
- **Tested:** 48 runs = 4 markets (MCX 15m, MCX 1h, stock futures 1h, index futures 1h) × BUY / SELL × 3 filter sets (base / +VWAP / +VWAP + RSI zone) × 2 exits (short 1.5 ATR / 2R / ~1 session; trend 2 ATR + 4 ATR trail).
- **No candidate is good enough.**
  - **Short exits:** negative everywhere after costs (−0.01 to −0.50R in VALID).
  - **Stock and index futures:** negative in both periods.
- **Best row:** MCX 1h BUY, trend exit, + VWAP + RSI > 50.
  - DEV +0.70R (171 trades), **VALID only +0.05R** (91 trades, 29.7 % won).
  - It technically passes the freeze bar and beats the random p95, but its VALID edge is about zero, and it is weaker than H1.12L (VALID +0.25R in the same engine).
- **VWAP:** it did nudge the RSI-cross rule upwards on MCX (VALID −0.04 → +0.01 → +0.05R), unlike on breakouts, but not enough to matter.
