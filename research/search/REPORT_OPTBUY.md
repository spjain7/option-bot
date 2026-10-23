# OPT-BUY-001 result – can option BUYING win? (rules in REGISTRY_OPTBUY.md, fixed before the run)

Model estimate on real MCX + NIFTY/BANKNIFTY hourly futures data, Jul-2022 → Oct-2026. ATM options priced with Black-76 at
20-day realised volatility × 1.15. Returns are per trade, as a share of the premium paid, after costs (shown at 2× costs).
No free option-price history exists, so this is a model, not real fills.

**Pass (all on the 7-days-to-expiry assumption): daily volume breakout** — close beyond the 20-day high/low with volume
> 1.5× average, buy the ATM option at the next open:

| Exit | Trades | Win % | Avg per trade, 2× costs (before / after Jul-2024) | Without top 10 | IV × 1.3 | IV crush 10% |
|---|---|---|---|---|---|---|
| X2: −40% stop, +100% target, 5 days max | 221 | 41% | +18% / +18% | +8% | +9% | +13% |
| X1: 2 ATR stop, 3 ATR trail | 202 | 41% | +24% / +24% | +1% | +11% | +22% |
| X3: fast-or-out | 214 | 35% | +15% / +27% | +1% | +12% | +17% |

**But it does not survive realistic expiries.** MCX options are monthly, so a buyer usually pays for 10–30 days of
time value. With each trade's real days-to-expiry, the same rule makes +1–7% before Jul-2024 and +4–17% after: it fails
the rule. The edge depends on cheap, near-expiry options.

- **Hourly and 3-hour buying loses or is flat everywhere.** Time decay and spread eat the small moves.
- **Squeeze and momentum-candle entries fail.**
- **Random entries lose** (−3% to −14% per trade), as expected for option buying.
- **By instrument, the daily rule at 7 days to expiry:** silver, copper and gold carry it; natural gas loses in both halves;
  NIFTY and BANKNIFTY have too few trades (about 30).

**Status: hypothesis only, not a PASS for live use.** Next step:
1. Shadow-track daily volume-breakout option buys with **real option prices**, buying only when the nearest expiry is
   7–10 days away (a new rule, so it must be tested on new data).
2. Accept only if it stays positive after 30+ real trades.
