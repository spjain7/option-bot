# STRAT-SEARCH-001 – result
No rule met the pre-registered shortlist bar (design < Jul-2024: ≥ +0.10R AND bootstrap p1 > 0 AND …), so formally nothing passes.

Design-period expectancy per trade, pooled over instruments, after costs:
- **Best:** EMA20/50+ADX on 3-hour candles +0.158R (127 trades, PF 1.30, p5 −0.08); Donchian 20/10 on 3-hour candles +0.06R (601 trades, PF 1.11).
- **Everything on 15m/1h is negative:** mean-reversion (RSI-2, Bollinger), opening-range breakout, inside bar, MACD, and the live RSI-reversal rule (−0.11 to −0.18R).

Hold-out (Jul-2024 → Oct-2026), opened as INFORMATION ONLY for the two best 3h trend rules:
| Rule | Trades | Exp. 1× costs | PF | Exp. 2× costs |
|---|---|---|---|---|
| EMA20/50+ADX, 3h | 199 | +0.137R | 1.25 | +0.085R |
| Donchian 20/10, 3h | 779 | +0.201R | 1.38 | +0.139R |

These rules are positive in both periods, but they don't qualify:
- They failed the strict design test.
- 2024-26 was a strong commodity trend period.
- EMA 3h depends heavily on GOLD (design +1.43R), and is negative on NATURALGAS and NIFTY.

Status: **PAPER-CANDIDATE (trend-following on 3-hour candles)**, not proven. Next step is forward paper alerts only.
