# RSIFAM-001 – RSI 75/25 strategy family (registered and run 4-Nov-2026)

Script `research/search/rsi_family_mcx.py` (rules fixed in its docstring before the run). MCX 7, 1-hour, Jul-2022 → Oct-2026,
roll-adjusted. Half at T1 → stop to entry → rest at T2 / stop / time. Stop-first. Costs 0.04 % per round trip (in R).
Disclosure: 2025-26 is not untouched for RSI-reversal ideas (RSIREV-001 / RSIPAT-001 looked at it earlier).

| Family | Period | n | T1 hit | T2 hit | Stop hit | Profitable | Avg win R | Avg loss R | Expectancy R | PF | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A range MR (ADX<20) | 22-24 / 25-26 | 3 / 6 | – | – | – | – | – | – | −1.06 / −0.25 | – | **REJECT** – almost never fires |
| B trend pullback | 22-24 / 25-26 | 113 / 95 | 38 / 53 % | 15 / 21 % | 50 / 39 % | 47 / 57 % | 0.77 / 0.84 | −1.17 / −1.08 | −0.26 / +0.01 | 0.58 / 1.03 | **REJECT** |
| C sweep reversal | 22-24 / 25-26 | 1005 / 808 | 44 / 45 % | 21 / 24 % | 56 / 55 % | 43 / 44 % | 0.83 / 0.89 | −1.25 / −1.27 | −0.36 / −0.33 | 0.49 / 0.54 | **REJECT** (worse than random) |
| D divergence | 22-24 / 25-26 | 275 / 207 | 46 / 52 % | 19 / 25 % | 43 / 36 % | 48 / 56 % | 0.93 / 0.94 | −0.99 / −0.97 | −0.06 / +0.10 | 0.88 / 1.23 | **REJECT** – not consistent (BUY 25-26 +0.22R, CI −0.02…0.45; 22-24 −0.11R) |
| E compression breakout | 22-24 / 25-26 | 139 / 152 | 57 / 57 % | 35 / 34 % | 43 / 43 % | 57 / 56 % | 1.01 / 1.02 | −1.25 / −1.08 | +0.04 / +0.09 | 1.07 / 1.20 | **CONTINUE (BUY only) → PAPER** |
| – E BUY only | 22-24 / 25-26 | 72 / 102 | 58 / 63 % | 33 / 42 % | 42 / 36 % | 58 / 62 % | 0.96 / 1.10 | −1.11 / −1.03 | +0.10 / +0.29 | 1.21 / 1.74 | 95 % CI −0.15…0.36 / +0.07…0.50; side split chosen after the run |
| F small target (T1 0.5R) | 22-24 / 25-26 | 670 / 544 | 58 / 58 % | 27 / 29 % | 32 / 31 % | 58 / 58 % | 0.43 / 0.45 | −0.93 / −0.92 | −0.14 / −0.12 | 0.64 / 0.68 | **REJECT** – high T1 hit, negative expectancy |
| Random baseline | 22-24 / 25-26 | 2315 / 1860 | 49 / 49 % | 24 / 24 % | 48 / 49 % | 50 / 49 % | 0.93 / 0.96 | −1.13 / −1.08 | −0.10 / −0.07 | 0.83 / 0.86 | reference (cost drag ≈ −0.08R) |

Lesson confirmed: a 58 % first-target hit rate (F) still loses after costs because winners are half the size of losers.
Next: E BUY (compression breakout with volume) goes to PAPER as a log-only shadow signal; promote only if 30+ paper trades
show expectancy > 0 after costs with the same rules.
