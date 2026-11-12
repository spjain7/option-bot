# "Institutional" MCX setups (12-Nov-2026)

Research only.

**Data and rules:**
- 7 commodities, 5-minute data from 2023 to 3-Nov-2026.
- Real MCX costs, next-bar entry, stop checked first.
- BUY and SELL kept apart; win rate and net R both reported.

**Setups:**
- Order blocks and fair value gaps after a displacement.
- A sweep of the previous day's high or low that is then reclaimed.
- Reversion from 2 standard deviations away from VWAP.
- The volume-profile "80 % rule".
- An opening-range breakout at the US open (18:30 IST).
- A break and retest of the previous day's high or low.
- A benchmark of entry every 10th bar.

**Result:** 0 of 32 pass on 15-minute intraday, 0 of 32 on 1-hour positional. Every setup is negative after costs, and most are worse than the benchmark.

| Setup (15-min intraday) | Win % | Net R / trade | Setup (1-hour positional) | Win % | Net R / trade |
|---|---|---|---|---|---|
| Order block BUY 2R | 36 | −0.36 | Order block BUY 3R | 40 | −0.23 |
| FVG BUY 2R | 37 | −0.38 | FVG BUY 3R | 41 | −0.14 |
| PDH/PDL sweep BUY 2R | 36 | −0.23 | PDH/PDL sweep BUY 3R | 37 | −0.14 |
| VWAP 2σ BUY → VWAP | 36 | −0.42 | VWAP 2σ BUY 2R | 38 | −0.15 |
| Value-area 80 % rule BUY | 49 | −0.03 | Value-area 80 % rule BUY | 53 | −0.05 |
| US-open ORB BUY 3R | 43 | −0.06 | (not meaningful on hourly bars) | | |
| PDH retest BUY 3R | 31 | −0.35 | PDH retest BUY 3R | 34 | −0.22 |
| Benchmark (every 10th bar) 2R | 36 | −0.26 | Benchmark 2R | 39 | −0.11 |

**Why:**
- These setups use tight stops, so costs are a large share of the risk on 15-minute bars.
- The patterns themselves do not predict direction on MCX: win rates sit at or below the random benchmark.
- The "80 % rule" reaches the other side of the value area in only about half of cases on MCX, not 80 %.

**The only liquidity-grab ("institutional") idea that has held up on MCX** is the 1-hour stop-hunt with a structure shift, BUY with the trend, with a big target (`research/early_rev`). It made +0.43R per trade on untouched 2022–23 data.
