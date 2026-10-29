# STRATEGY-PROGRAM-001: complete strategy-improvement report (28-Oct-2026)

Branch `exp/strategy-program-001` (research only; nothing here is merged or live).
Live code inspected: `main` at c86deb4 / 8845e03.

**Win definition:** a completed trade with net R > 0 after costs. R is the stop distance from the executable entry.
**Expectancy:** average net R per trade at 1× and 2× costs (costs include slippage).
**Uncertainty:** 95 % month-block bootstrap. Warnings mark n < 30 and n < 100.

## 1. Inventory: active strategies on `main` (checked in code)

| Segment | Strategy | Live rule | Data for research |
|---|---|---|---|
| Index + MCX futures | S1 3-hour breakout BUY / SELL | Close beyond the 20-bar high/low, volume > 1.5×, EMA200 side, OI label must agree; SL 2 ATR (≤ 2.5 %), target 2R, 40 bars; entry only if price is within 0.5 ATR of the signal close | Angel 1-hour bars, 2022–26, 9 instruments (no MCX OI history) |
| | S2 daily breakout BUY / SELL | Same entry on daily bars; SL 1.5 ATR (≤ 4 %), target 3R, 40 days | As above, plus **NSE bhavcopy NIFTY / BANKNIFTY 2011–26** and **international proxies 2005–26** |
| | S3 monthly breakout BUY / SELL | First daily close beyond last month's high/low, with weekly and monthly trend; SL 1.5 ATR, 2R, 20 days | As above |
| Stock futures | S4 OI breakout BUY / SELL | 20-day breakout, volume > 1.5×, OI ≥ +2 % (validated), EMA200; SL 2 ATR, 3-ATR trail, expiry-day exit, next-open entry check; corporate-action and OI safeguards | Angel 2022–26; OI only from Nov-2023 |
| | S5 bearish engulfing SELL | Engulfing after a rise, volume > 1.5×; SL 1.5 ATR, 1R, 10 days | Angel 2022–26 |
| | +2–4 % OI label | Shadow only | Live forward record from 29-Oct |
| Option buy | Options from futures calls; intraday stock option-buy engine (VWAP + RSI + OI) | Premium SL / target %; filters on IV, spread and VIX | **Real premiums for one month only** (research-obuy, Sep–Oct 2026) |
| Option sell | `runner.try_open` → `strategy.build_trade`, naked CE/PE sells (intraday, weekly, monthly, MCX positional); RSI-80/25 rule; 28-Oct rules (expiry window, flip OI check, S/R buffer, SL checked between scans) | Premium SL / target, spot stop, time exits | **No historical option premiums.** Live record only: 221 archived calls (21-Sep to 27-Oct) and 4 since |
| Off | Weekly breakout, 3h stock calls, chart patterns, RSI-reversal engine, old calls engine, MCX trade engine, positional option buys | — | — |

## 2. Verified baselines (live rules, live entry check, conservative execution)
Execution model:
- entry at the next bar's open;
- **stop checked before target inside a bar** (if both are hit, it counts as a loss);
- a gap through the stop fills at the open;
- exit before a contract switch;
- costs at 1× and 2×.

Splits:
- **Angel and stock data:** train < Jul-24 ≤ validation < Jul-25 ≤ test.
- **NSE and proxy data:** train < 2019 ≤ validation < 2022 ≤ test.

| Dataset · strategy | Side | Trades (invalid*) | Win % | Avg win / loss R | Exp 1× (2×) | PF | Max DD R | Losing streak | Train / valid / test exp |
|---|---|---|---|---|---|---|---|---|---|
| Angel S1 3h | BUY | 345 (178) | 48.1 | +1.71 / −1.05 | **+0.28 (+0.21)** [+0.10, +0.44] | 1.51 | 13.2 | 10 | +0.32 / +0.11 / +0.36 |
| Angel S1 3h | SELL | 212 (184) | 38.2 | | **−0.08 (−0.16)** | 0.88 | 33.2 | 15 | −0.17 / −0.07 / +0.04 |
| Angel S2 daily | BUY | 72 (45) | 51.4 | | **+0.71 (+0.67)** [+0.24, +1.15] | 2.63 | 9.5 | 10 | +1.42 / −0.07 / +0.90 |
| Angel S2 daily | SELL | 23 | 47.8 | | −0.07 | 0.88 | 8.0 | 7 | n<30 |
| Angel S3 monthly | BUY | 116 (48) | 49.1 | | **+0.28 (+0.24)** [+0.04, +0.51] | 1.62 | 6.6 | 5 | +0.39 / +0.07 / +0.34 |
| Angel S3 monthly | SELL | 24 | 54.2 | | +0.09 | 1.20 | 5.2 | 3 | n<30 |
| NSE NIFTY/BANKNIFTY 2011–26 S2 | BUY | 37 | 51.4 | | **+0.55 (+0.50)** | 2.46 | 3.1 | 5 | +0.75 / +0.55 / +0.16 |
| NSE S2 | SELL | 20 | 45.0 | | +0.25 | 1.60 | 3.2 | 3 | n<30 |
| NSE S3 | BUY | 165 | 44.2 | | +0.03 (−0.02) | 1.05 | 23.0 | 7 | −0.08 / +0.22 / +0.09 |
| NSE S3 | SELL | 32 | 43.8 | | −0.10 | 0.82 | 7.1 | 4 | |
| Proxy (international) S2 | BUY / SELL | 101 / 63 | 28 / 32 | | +0.05 / −0.00 | 1.07 / 1.00 | | | not MCX – reference only |
| Proxy S3 | BUY / SELL | 294 / 142 | 44 / 39 | | +0.11 (−0.05) / −0.02 | | | | reference only |
| Stocks S4 OI breakout | BUY | 623 (65) | 44.9 | +1.15 / −0.80 | +0.08 (+0.06) | 1.17 | 36.1 | 15 | **+0.27 / +0.01 / −0.07** (2023 +0.58 → 2026 −0.06) |
| Stocks S4 | SELL | 220 (46) | 56.8 | | **+0.23 (+0.21)** [+0.02, +0.40] | 1.76 | 12.6 | 14 | +0.05 / +0.09 / +0.32 |
| Stocks S5 bear engulf | SELL | 120 (13) | 59.2 | | **+0.20 (+0.18)** [+0.03, +0.38] | 1.65 | 8.4 | 5 | +0.06 / +0.22 / +0.35 |

\* Invalid = signals cancelled before entry: the next open was more than 0.5 ATR from the signal close, or the stop was wider than the cap. Live does not send these.

**Reconciliation with earlier reports:**
- These baselines include the live entry-zone check and the live stock exit (expiry-day close). Earlier reports used a different exit for stocks.
- S4 BUY is **flat-to-negative in recent periods, not strongly negative**, as already corrected in REPORT_STOCK_OI_BUY.md.

**Options:**
- **Option buy:** one month of real premiums (20 sessions; the engine's VWAP-RSI-OI setup): 138 trades, 45 % wins, +1.6 % per trade, PF 1.15. That is far too short to judge.
- **Option sell:** there is no historical premium data, so the strategy cannot be backtested honestly. The live record is in §3, item 3.

## 3. Ranked causes of poor signal quality
1. **SELL breakouts on index/MCX futures:** S1 SELL −0.16R at 2× costs, 15-trade losing streak, 33R drawdown. Monthly and daily SELL samples are too small to rescue.
2. **Today's 7-day expiry limit on intraday option sells (my change, approved by you today) blocks the most profitable live segment:**
   - **MCX intraday sells on options 8+ days from expiry:** 100 calls, 59–76 % wins, +₹3.07 lakh per lot (archived record).
   - **Stock-option intraday sells on 16+ day expiries:** lost (34 calls, 41 % wins, −₹16k), so the limit is right for stocks.
   - **→ revert the limit for MCX** (§7).
3. **Option-sell tracking was optimistic until today:** stops touched between 15-minute scans were missed (fixed today). So the archived 66 % win rate and PF 3.3 are **upper bounds**, not facts.
4. **Stock OI BUY is decaying:** +0.58R (2023) → −0.06R (2026), in every variant tested.
5. **Late or gapped entries:** 30–50 % of futures signals fail the 0.5-ATR entry zone. They are correctly not sent, but each one is a missed or stale signal (worst for 3h SELL).
6. **Low trade counts:** daily/monthly SELL and option buy cannot be judged.
7. **ALUMINIUM / ZINC mega contracts** have zero volume: no calls possible (now shown in the morning message).

## 4. Experiments: all results, including failures
- **A–C: 13 pre-declared entry filters** (regime, momentum, extension, candle quality, compression, room to level, volume, RSI):
  - **Futures:** 182 tests; 4 pass train + validation + test with Δ > 0 and exp at 2× costs > 0. That is **no better than chance** (multiple comparisons).
  - **Stocks:** 39 tests; 3 pass (S4 SELL + close near the low; S4 SELL + RSI not exhausted; S5 + volatility expanding), each by only +0.01 to +0.09R.
  - **Verdict:** no filter is a reliable improvement → **REJECT** as live rules; at most **SHADOW**.
- **D: exits:**
  - **2R targets:** the stop/target alternatives (1.5 ATR · 2R; 2.5 ATR · 3R; swing stop · 2R) do not beat the live exits consistently.
  - **Small targets:** these raise win rate to 70–87 % but **cut expectancy to about zero in most cases**.
- **High-accuracy search:** 390 futures and 24 stock variants. The gate is ≥ 75 % wins, exp at 2× costs > 0 and PF ≥ 1.2 in **each** of train, validation and test. **2 pass:**

| Candidate HA-1 (3h BUY only) | Trades | Win % (train / valid / test) | Exp 1× (2×) | PF | Max DD R | Losing streak |
|---|---|---|---|---|---|---|
| Live 3h BUY baseline | 345 | 48 / 42 / 53 | +0.28 (+0.21) | 1.51 | 13.2 | 10 |
| SL 3 ATR (≤ 2.5 %), target 0.5R, RSI < 75 | 212 | 77 / 80 / 77 | +0.11 (+0.05) [+0.01, +0.20] | 1.47 | 4.4 | 4 |
| SL 3 ATR (≤ 2.5 %), target 0.5R, prior compression | 98 | 82 / 77 / 82 | +0.15 (+0.09) [+0.01, +0.28] | 1.71 | 4.6 | 3 |

  - **Sensitivity:** nearby stop/target settings (3–3.5 ATR, 0.5–0.6R) stay positive.
  - **The result depends on the 2.5 % stop cap,** which keeps only calm setups. Without the cap, expectancy is about 0.
  - **By instrument:** strong on GOLD and ALUMINIUM, about zero on SILVER, COPPER and ZINC.
  - **Trade-off:** about 78–80 % wins, but **about ½ to ⅓ of the profit per trade** of the live rule, with a much smaller drawdown.
  - **Stocks:** the high-win exits fail (most signals are cancelled by the 6 % cap, many trades end at expiry before the target).

## 5. Recommendations by segment and side
| Strategy | BUY | SELL |
|---|---|---|
| S1 3h breakout | KEEP BASELINE; HA-1 → **PAPER TEST** (shadow log) | **READY FOR MY REVIEW**: switch to shadow-only (negative in train and validation, 15-loss streak) |
| S2 daily breakout | KEEP BASELINE (best expectancy; NIFTY/BANKNIFTY 2011–26 agrees) | KEEP / SHADOW (n < 30) |
| S3 monthly breakout | KEEP BASELINE | SHADOW TEST (n < 30, mixed) |
| S4 stock OI breakout | KEEP BASELINE + +2–4 % shadow (unchanged); decay → **REVIEW** in 4 weeks | KEEP BASELINE; RSI / close-location filters → SHADOW |
| S5 bear engulfing | — | KEEP BASELINE |
| Entry filters A–C | REJECT CANDIDATE | REJECT CANDIDATE |
| Option buy | KEEP BASELINE (insufficient data) | — |
| Option sell | KEEP BASELINE and the between-scan SL check; **READY FOR MY REVIEW**: remove the 7-day intraday limit for MCX, keep it for stock options | |

## 6. Data limitations
- **No historical option premiums** for option selling, and one month for option buying. Option strategies cannot reach 75–90 % with evidence; their live record is the only test.
- **Stock futures:** 3 years only (OI from Nov-2023). The universe is today's F&O list, so survivorship bias inflates results.
- **No MCX OI history,** so the live OI-agreement rule for MCX calls could not be backtested.
- **International proxies are not MCX** (USD, other hours, roll jumps). They are used for reference only.
- **Contaminated test periods:** the Angel 2024–26 periods were seen in earlier studies (baseline rules only; the new filters and exits were chosen on train). The NSE 2011–2021 data was never used before, but it has few daily signals.
- **About 430 variants tested:** expect a few false passes, so every passing candidate still needs paper testing.

## 7. Recommended configuration (needs your approval)
1. **Option sell:** set the intraday expiry limit for MCX back to "any expiry ≥ 3 days". Keep ≤ 7 days for stock options and the 3-day MCX minimum. Keep the flip-OI check, the S/R buffer and the between-scan SL check (all are measured live from now).
2. **S1 3h SELL:** shadow-only (logged, not sent), or keep sending with a "lower-quality" label. Your choice.
3. **HA-1:** add as a shadow log beside every 3h BUY call. It is not sent.

## 8. Files on the research branch
- `research/program/harness.py`, `run_futures.py`, `run_highacc.py`, `run_stocks.py`, `REPORT.md`
- `results/*.md|csv`
- `tests/test_program_harness.py` (10 checks)

## 9. Commands
- **Tests:** `python -m tests.test_program_harness`
- **Experiments:** `python research/program/run_futures.py`, `run_highacc.py`, `run_stocks.py`

## 10. Paper-test plan and promotion conditions
Forward data from 29-Oct-2026 only. Thresholds are fixed now and are not tuned on this data.

| Candidate | Promote if, after ≥ 40 closed shadow trades | Reject if |
|---|---|---|
| HA-1 (3h BUY high-accuracy) | win ≥ 75 % **and** exp at 2× costs > 0 **and** PF ≥ 1.2 | win < 70 % or exp ≤ 0 |
| S1 SELL shadow | exp at 2× costs > +0.1R | exp ≤ 0 → stays off |
| +2–4 % OI label (S4 BUY) | label exp at 2× costs > 0 and > all calls | otherwise |
| Option-sell 28-Oct rules | blocked calls' tracked outcome worse than the calls sent | blocked calls would have won more → remove the rule |

## Addendum: SEARCH-80 (owner's 80 % goal), 28-Oct-2026 evening
Script `research/program/search80.py`; tables in `results/search80_tables.md` and `results/search80_variants.csv`.

**What was tested:**
- **24 BUY setups:** trend breakouts (EMA cross, MACD, Supertrend, Donchian, ADX, Bollinger squeeze, inside bar, NR7); uptrend pullbacks (RSI(2), 3 lower closes, lower Bollinger, Williams %R, Stochastic, EMA20 pull-back, 10-day low, gap-down reversal); candle patterns (bullish engulfing, hammer, morning star, piercing); volume/OI dips.
- **7 exits:** small targets with wide stops; close above SMA5; first profitable close; close above the previous high.
- **2 regime settings.**
- **7 datasets:** MCX daily and 3h, index daily and 3h, NIFTY/BANKNIFTY daily 2011–26, international proxies 2005–26, 181 stock futures.
- **2,380 variants in total.**

**Results:**
- **≥ 80 % wins in train, validation and test (sample-size minimum met):** 0 variants, even ignoring profit.
- **Gate ≥ 80 % (or ≥ 75 %) wins plus exp at 2× costs > 0 and PF ≥ 1.2 in every period:** 0 variants.
- **Gate at ≥ 70 % wins:** 1 variant. Stocks: morning star with NIFTY above EMA200, exit at the first profitable close. Wins 76 / 81 / 74 %, +0.04 / +0.03 / +0.05R per trade at 2× costs, 73 % of stocks positive in the test period. That is a small edge.
- **Best earlier result:** HA-1 (3h BUY, stop 3 ATR capped at 2.5 %, target 0.5R, RSI < 75 or compression), 77–82 % wins. It is already logged live beside every 3h BUY since 28-Oct.

**Conclusion:** on this data, 80 % winning trades with positive profit after costs is not achievable reliably in any segment. Win rates of about 75–80 % are possible only with small targets, and the profit per trade then falls to +0.03–0.15R.

## Addendum: REV-001, RSI-reversal futures calls with every confirmation (owner's request), 28-Oct-2026
Script `research/program/reversal.py`; tables in `results/rev_tables.md` and `results/rev_variants.csv`.

**Setup tested:**
- **Base signal:** BUY when RSI(14) < 25 (also < 20); SELL when RSI(14) > 75 (also > 80).
- **Confirmations, in all 64 on/off combinations:** reversal candle (hammer, hanging man, shooting star, engulfing, morning/evening star, piercing, dark cloud); volume ≥ 1.5× plus relative volume by time of day ≥ 1.5×; ADX < 25; OI positioning (short buildup before a BUY, long buildup before a SELL); price ≥ 1 ATR away from VWAP; EMA200 trend side.
- **Exits:** 4 options (0.5R or 1R targets, or back to VWAP/EMA20).
- **Data:** 1-hour candles 2022–26 (MCX, NIFTY/BANKNIFTY, 181 stocks) and 15-minute candles with intraday OI for 2 months (Aug–Oct 2026; 4 indices, 40 stocks, 4 MCX).
- **3,164 variants in total.**

**Results:**
- **80 %, 75 % and 70 % win gates** (with exp at 2× costs > 0 and PF ≥ 1.2 in every period): **0 variants** pass any of them.
- **Base RSI 75/25 reversal:** 56–64 % wins, but −0.2 to −0.5R per trade after costs in every segment.
- **Before costs:** only 57 of 778 adequately sampled variants (7 %) are positive in every period, about what chance gives. The best ones are 15-minute stock variants with only 2 months of data.
- **Costs on intraday candles** take 0.07–0.21R per trade because intraday stops are small.

**Conclusion:** RSI-extreme reversal entries for futures, with any mix of candle, volume, ADX, OI, VWAP and EMA confirmation, do not reach 70 % wins with a profit on 1-hour or 15-minute candles. The RSI-80/25 rule stays where it is live today: as an option-SELL trigger. That is a different trade (premium decay) and cannot be backtested without option-price history.

## Addendum: EMAX-002, EMA crossover with volume and OI (owner's request), 28-Oct-2026
Script `research/program/emax.py`; tables in `results/emax_tables.md` and `results/emax_variants.csv`. 1,527 variants were tested:
- **EMA pairs:** 9/21, 20/50, 50/200 (+ 5/13 on 15m and 1h).
- **Confirmations:** volume, OI and EMA200 in all combinations.
- **Exits:** 3 (opposite cross, 2-ATR stop with 2R target, 3-ATR trailing stop).
- **Timeframes:** 15m, 1h, 3h, daily.
- **Markets:** MCX, index, stocks, NSE 2011–26, international proxies 2005–26.

40 variants are profitable at 2× costs (PF ≥ 1.2) in every period. They cluster in **MCX BUY on 3-hour candles**:

| Candidate | Trades | Win % | Exp 1× (2×) | PF | Max DD R | By instrument | By year |
|---|---|---|---|---|---|---|---|
| MCX 3h EMA9/21 BUY above EMA200, exit on opposite cross (3-ATR safety stop) | 400 | 39 | +0.32 (+0.27) | 1.98 | 9.6 | 6 of 7 positive (GOLD +0.82, CRUDE +0.54, SILVER +0.29; COPPER −0.07) | 2022 ≈ 0, 2023 −0.04, 2024 +0.51, 2025 +0.38, 2026 +0.27 |
| Same, plus volume ≥ 1.5× | 101 | 41 | +0.30 (+0.26) | 2.03 | 4.1 | mixed (n small) | |
| Same, no EMA200 filter | 658 | 37 | +0.22 (+0.17) | 1.67 | 12.3 | 5 of 7 | |
| MCX 3h EMA9/21 SELL (comparison) | 654 | 33 | −0.02 (−0.07) | 0.96 | 39.6 | 1 of 7 | negative |
| Proxy (international) daily 20/50 BUY, 2005–26 | 276 | 32 | +0.28 (+0.26) | 1.51 | 30.1 | 5 of 6 | long losing years (2013–15, 2018) |
| Stocks 3h EMA50/200 SELL, exit on opposite cross | 715 | 54 | +0.15 (+0.13) | 1.52 | 18.5 | broad | positive every year |
| Stocks 3h EMA9/21 BUY + OI long buildup | 852 | 37 | −0.04 (−0.06) | 0.88 | 64 | — | negative (OI confirmation does not help) |
| Index 3h EMA9/21 BUY | 80 | 33 | +0.01 (−0.02) | 1.03 | | | no edge |

**Conclusions:**
- **The EMA crossover is a trend-following edge for MCX BUY:** a low win rate (about 40 %), but winners average +1.6R and losers −0.5R.
- **Not 80 % accuracy.**
- **Volume adds little; OI cannot be tested for MCX** (no history) and **does not help for stocks.**
- **MCX 3h EMA BUY overlaps with the live 3h breakout BUY** (both are trend-following on the same instruments).
- **The stocks 3h 50/200 SELL is a new, broad, modest candidate.**
- **Recommendation:** shadow-log both before any live use.

## Addendum: EMAX-003, many EMA pairs, trend-only (no choppy market), 28-Oct-2026
Script `research/program/emax3.py`; results in `results/emax3_variants.csv`.
- **Pairs tested (14):** 5/13 to 100/200.
- **Trend filters, measured on the crossover candle:**
  - ADX ≥ 20;
  - ADX ≥ 25;
  - ADX ≥ 20 and rising (A20R);
  - Choppiness Index < 50 or < 45;
  - ADX ≥ 20 and price on the trade side of EMA200;
  - each with and without volume.
- **Scale:** 14,832 variants; 338 pass in every period (2.3%, so many will be luck).

**Findings:**
- **On MCX 3h BUY, slower pairs beat 9/21.**
  - Plain crossover, opposite-cross exit, expectancy at 2× costs: 9/21 +0.17R, 13/48 +0.25R, 21/55 +0.23R.
  - 21/55 passes under all 7 filters.
- **"ADX ≥ 20 and rising" is the trend filter that lifts these slower pairs most.**
  - It removes about 70–75% of trades.

  | Variant | Trades | Win % | Exp 2× | PF | Max DD |
  |---|---|---|---|---|---|
  | 13/48 + A20R | 79 | 48 | +0.67R | 2.97 | 6.6R |
  | 20/50 + A20R | 99 | 48 | +0.42R | 2.13 | 8.4R |
  | 21/55 + A20R | 98 | 45 | +0.41R | 2.10 | 6.6R |

  - All three lost in 2022 (n 7–8) and were positive in 2023–26.
  - GOLD is the largest contributor; CRUDE and COPPER are flat or negative.
- **The Choppiness filter does not help MCX BUY**, but it does help INDEX 1h 12/26 SELL (CH < 45): n 120, 45% wins, +0.32R, PF 1.93, mostly NIFTY.
- **Elsewhere, trend filters show no consistent gain.** Medians across pairs are mixed for stocks, MCX SELL and MCX 1h.
- **Win rates stay at 40–50%**; the edge comes from winners about 2–3× the size of losers.

## Addendum: HAM-001, 1-hour hammer BUY after a downtrend / hanging man SELL after an uptrend, 28-Oct-2026
Script `research/program/hammer.py`; results in `results/ham_variants.csv`.
- **Rules:**
  - stop 0.05 ATR beyond the candle's low (hammer) or high (hanging man);
  - target 1R, 2R or 3R; maximum 20 candles.
- **Variants:**
  - 3 trend definitions: EMA20/50, 20-bar swing extreme after a 5-bar move, or both;
  - entry at the next open, or on a break of the candle's high/low (confirmation);
  - with and without volume ≥ 1.5×, and candle range ≥ 1 ATR.
- **Scale:** 432 variants; 2 pass, both INDEX hammer with volume.

**Results (both trend definitions together, 2R target, net at 2× costs):**

| Setup | Market | Trades | Win % | Result |
|---|---|---|---|---|
| Hammer BUY | Stocks | 7,882 | 34 | −0.44R (gross −0.09R) |
| Hammer BUY | MCX | 924 | 34 | −0.88R (gross −0.03R) |
| Hammer BUY | Index | 110 | 50 | −0.27R |
| Hanging man SELL, next-open entry | all markets | — | 21–29 | −1.3R to −3.1R |
| Hammer BUY, best filters (confirmation entry, volume, candle ≥ 1 ATR) | Stocks / MCX | — | 40–43 | −0.13R to −0.20R |
| Index hammer + volume, both trend definitions, next-open entry | Index | 46 | 70 | +0.55R |

- **Hanging man:** the candle closes near its high, so the stop is only about 0.25–0.4 ATR away. Normal noise hits it, and costs are large relative to that small risk. With confirmation entry it is about −0.03 to −0.7R.
- **Index hammer + volume:** small sample. The EMA-only trend version (n 70) gives +0.19R and lost in 2023 and 2026. Treat it as a watch item, not an edge.
- **Conclusion:** no tradable edge on stocks or MCX. Index hammer + volume is too small to trust.
- **HAM-001 follow-up (confirmation-close entry E3).** A candle within 3 bars must close beyond the pattern's high/low; entry at the next open; stop unchanged. Both trend definitions, 2R target, net at 2× costs:

  | Setup | Market | Breakout entry (E2) | Close entry (E3) |
  |---|---|---|---|
  | Hammer BUY | Stocks | −0.20R | −0.22R |
  | Hammer BUY | MCX | −0.46R | −0.43R |
  | Hammer BUY | Index | −0.12R | −0.03R |
  | Hanging man SELL | Stocks | −0.20R | −0.25R |
  | Hanging man SELL | MCX | −0.69R | −0.62R |

  - Before costs, all are about zero. The candle has no directional edge, even after confirmation.
  - Index hammer + volume with breakout entry: 35 trades, 66–80% wins, +0.34 to +0.39R. This is the only positive case and is too small to rely on.

## Addendum: exit cross-check (owner found 360ONE 22-Sep wrongly booked as a stop), 28-Oct-2026
- **Bug:** the hammer simulator checked the stop before a candle that OPENED beyond the target. For 360ONE on 23-Sep 09:15, the candle opened at 1090.5, above the 1086.91 target, and its low was below the stop. The trade was booked as a stop.
- **Fix:** a gap through the target now fills at the open (hammer.py, hammer_log.py, daily_candles.py).
- **Impact:** 109 of 32,246 hourly calls changed from stop to target (3 in the last month: 360ONE ×2, SBIN). Averages moved by about 0.01–0.04R; conclusions are unchanged.
- **`verify_exits.py` independently re-walks all 32,246 hourly and 7,367 daily calls from the raw candles:**
  - 0 real logic errors. 31 flags were price touching a level to within 0.01 because of rounding in the log.
  - 568 hourly calls (1.8%) and 8 daily calls had one candle touch both the stop and the target. The order inside such a candle is unknown, so they are booked as stops.
  - If all of those were targets instead, the hourly averages would move to: stocks BUY −0.02R, stocks SELL −0.01R, MCX −0.12/−0.18R. Still not positive.
  - 15-minute data (Aug–Oct 2026 only) resolved 4 of them, all stop first.
- **The same stop-before-gap-target order exists in harness.py, reversal.py, emax.py (Y2) and stock_oi_buy.py.** It makes those results slightly cautious; they are not yet re-run.

## Addendum: DCP-001, daily hammer / hanging man / engulfing, breakout entry, 28-Oct-2026
- **Script:** `research/program/daily_candles.py`.
- **Rules:** EMA20/50 trend before the pattern; entry on a break of the pattern day's high/low within 3 days; stop beyond the pattern; 2R target; 20 days maximum.
- **Results after normal costs, 2022–26:**

  | Pattern | Market | Trades | Win % | Result | Notes |
  |---|---|---|---|---|---|
  | **Hammer BUY** | MCX | 102 | 53 | **+0.31R** | |
  | Hammer BUY, any trend | MCX | 333 | — | **+0.36R** | every year 2022–26 positive; all 7 commodities positive; passes all periods |
  | Bullish engulfing BUY | MCX | 60 | — | +0.15R | without the trend filter: 165 trades, +0.35R, passes |
  | **Hanging man SELL** | Stocks | 1,217 | 44 | **+0.18R** | flat in 2023 and 2025 |
  | **Hanging man SELL** | NSE index 2011–26 | 111 | — | **+0.21R** | |
  | Hanging man SELL | MCX | — | — | about 0 | |
  | Bearish engulfing SELL | all markets | — | — | about 0 to −0.3R | |
  | Bullish engulfing BUY | Stocks / index | — | — | negative | |
  | Hammer BUY | Stocks | — | — | about −0.05R | |

- **Next-day-open entry (no breakout wait) is much worse** for all patterns. Waiting for the breakout is what makes these work.

## Addendum: RR1-001, the four candle patterns with a 1:1 target, 28-Oct-2026
- **Script:** `research/program/rr1.py`; trades in `results/rr1_trades.csv.gz`.
- **Windows:** 1h and 3h, last 2 months (pattern from 22-Aug-2026); daily, last 1 year (from 22-Oct-2025). Full 2022–26 history is shown for comparison.
- **Rules:** EMA20/50 trend; breakout entry; stop beyond the pattern; target 1R; net of normal costs.

**Break-even win rate.** At 1:1, the win rate needed to break even is above 50% by the cost share of R:

| Timeframe and market | Cost per trade | Win rate needed |
|---|---|---|
| 1h MCX | ~0.3R | ~60% |
| 1h stocks | ~0.15R | ~55% |
| Daily | ~0.05R | ~52–53% |

**Findings:**
- **Recent window:**
  - Stock SELL patterns were strong (hanging man and bearish engulfing, 59–68% wins on 1h, 3h and daily).
  - Stock BUY patterns were weak (34–48% wins). This matches a falling stock market in Aug–Oct 2026.
  - MCX 1h/3h BUY hammer: 63% and 70% wins.
- **Full history (2022–26), win rates are mostly 50–60%. Positive after costs:**
  - MCX daily hammer: 63%, +0.15R;
  - MCX daily bullish engulfing: 62%, +0.19R;
  - stocks daily hanging man: 58%, +0.14R;
  - index daily hanging man: 74%, +0.44R (n = 19).
- **Full history, negative after costs:** most 1h patterns. They win 51–56%, but costs take 0.15–0.3R of each trade.
- **Ambiguous candles:** few. Up to 4% of 1h stock trades touched the stop and the target in the same candle; the "best case" win rate moves by 1–4 points.

## Addendum: RR1-RSI, RSI and volume filters on the 1:1 candle-pattern trades, 28-Oct-2026
- **Scripts:** `rr1_rsi.py` and `rr1_rsi_analyse.py`; variants in `results/rr1_rsi_variants.csv`.
- **Method:** every pattern signal is simulated once (273k trades); the filters are then applied to the same trades.
- **Filters:**
  - RSI(14) extreme in the pattern candle or the 2 before (BUY ≤ 30 or ≤ 25; SELL ≥ 70 or ≥ 75);
  - pattern-candle volume ≥ 1.5× or 2×, or the previous candle's volume ≥ 1.5× (climax);
  - EMA20/50 trend, or any.
- **Scale:** 790 variants; 30 are positive in all three periods (3.8%, about what chance would give).
- **Pooled across markets and patterns (trend version), RSI and volume do not raise the win rate:**

  | Candles | No filter | Best filter combination | RSI and volume extremes |
  |---|---|---|---|
  | 1h | 51.8%, −0.10R | RSI 25/75 + volume 2×: 54.7%, +0.03R | — |
  | 3h | 51.3%, −0.02R | — | lower: 38–49% |
  | Daily | 50.2%, −0.02R | — | lower: 34–48% |

  On 3h and daily candles, a stretched RSI with a volume spike more often means the trend continues than that it reverses.
- **Pockets that held in every period** (small samples):

  | Setup | Trades | Win % | Result |
  |---|---|---|---|
  | 1h INDEX hammer + volume ≥ 1.5× (downtrend) | 51 | 75 | +0.56R |
  | 3h MCX hanging man + RSI ≥ 70 | 85 | 66 | +0.22R |
  | 1h STOCKS hanging man + RSI ≥ 70 + volume ≥ 2× | 135 | 61 | +0.16R |
  | Daily MCX hammer | 408 | 59 | +0.13R |
  | Daily MCX hammer + previous-day volume ≥ 1.5× | 74 | 64 | +0.24R |
  | Daily STOCKS hanging man (no RSI needed) | 2,808 | 58 | +0.12R |

- **Not established:** no 80% setup.

## Addendum: RR1, 1-hour patterns without the 15:15 candle (owner's request), 28-Oct-2026
- **The NSE 15:15 hourly candle is only 15 minutes long** (15:15–15:30), and its breakout comes after the overnight gap.
- **Stocks, trend as asked, 2022–26, win rate by pattern-candle time:**

  | Candle | Win % |
  |---|---|
  | 15:15 | 44–48 (hammer 43.8, hanging man 44.8) |
  | 14:15 | 47 |
  | 09:15–13:15 | 51–55 |

- **Results with those candles skipped:**

  | Data | All candles | Skip 15:15 | Skip 14:15 and 15:15 |
  |---|---|---|---|
  | 2022–26, pooled | 51.6% win, −0.093R | 52.1%, −0.078R | 53.3%, −0.053R |
  | Last 2 months | 49.9%, −0.14R | 50.0%, −0.14R | 51.4%, −0.11R |

- **Best rows after skipping 14:15 and 15:15:**
  - 2022–26: index hammer, 60.1% win, +0.04R.
  - Last 2 months: stocks hanging man, 64.6% win, +0.25R.
- **Verdict:** skipping late candles helps by 1–2 points of win rate, but 1-hour patterns stay slightly negative after costs over 2022–26.

## Addendum: STKFUT-CMP-001, 8 GitHub repositories vs the existing stock-futures alerts at a fixed 1:1, 29-Oct-2026
- **Scripts:** `stkfut_cmp.py`, `stkfut_cmp_analyse.py`, `stkfut_cmp_15m.py`, `stkfut_vbt_export.py`, `stkfut_vbt_xcheck.py`.
- **Execution and costs:** identical for every setup. STT is date-based: 0.0125% until 30-Sep-2024, 0.02% until 31-Mar-2026, 0.05% from 1-Apr-2026.
- **Verdict:** no repository setup has an edge at 1:1.
  - Setups tested: ORB, VWAP pullback, IB failure and gap-and-go; 119 intraday variants with 7 filters.
  - Before costs: about 0. After costs: −0.04 to −0.13R.
  - Positive in all 3 periods: 1 variant. Significant after Benjamini–Hochberg: 0.
- **Only PASS:** the bot's own daily hanging-man SELL, with 1,062 trades, 58.9% wins, +0.16R after costs and PF 1.39. Its periods were +0.06, +0.21 and +0.21R, with p < 0.001. It was selected on this data, so live results are the true out-of-sample test.
- **OI-breakout SELL:** +0.15R over 169 trades, but only 26 in training.
- **OI-breakout BUY:** negative at 1:1 (−0.08R); keep its 2-ATR stop with trailing exit.
- **NIFTY regime (nse-trading-lab `assess_tape`):** useful as a report label, but failed as a filter out of sample.
- **vectorbt 0.28.1 cross-check:** 2,786 of 2,787 comparable trades identical.
- **Cost model:** the stock cost model still uses 0.02% STT; it should move to the date-based rate (proposal; needs approval).
- **HA-1 re-run after the gap-through-target fix:** still PASS all 3 (test +0.097 → +0.111R).
- **PAT-002 live 3h breakout rule after the fix:** ₹1,565 / ₹11,386 per lot, 42.9% wins in both periods, 67% of instruments positive (before the fix: ₹1,407 / ₹10,605).

## OBUY-REAL-001 – option buying on REAL NSE option prices (29-Oct-2026)
Data: NSE F&O bhavcopy Jul-2022 → Oct-2026 (1,064 days, options ±12 % of futures, 2 nearest expiries). Signals on daily bars;
option bought at the real open next day (expiry ≥ 15 days), exit when the futures call exits (daily-close based), 1 % slippage/side + costs.
4,394 option trades priced (928 skipped: strike not traded at entry; 221 no exit price).

Avg ₹ per lot (option | option + 60-min-style time stop | futures, same timing):
| setup | ATM | ITM | OTM | futures |
|---|---|---|---|---|
| HANGMAN SELL (537) | −551 | −929 (−192 TS) | −517 | +358 |
| BEARENG SELL (167) | −342 | −1,232 | −740 | +897 |
| OIBRK BUY/SELL (778) | −3,414 | −2,855 | −3,176 | −2,040 |

* Options lost money in every setup × strike; median premium return −8 % to −33 %. Win rate 33–40 % vs futures 46–52 %.
* On stops the option loses ~45 % of the futures loss, but on targets it earns only ~55 % of the futures gain → net worse.
* IV ≤ 1.5×HV + normal-move filters did NOT help (HANGMAN −881 filtered vs −666 all). Time stop reduces losses, never turns positive.
* Test split HANGMAN ITM ≈ −50/lot (break-even) vs futures +861.
Verdict: no option-buying edge on these signals; trade the futures leg. Live option IDEA messages remain informational only.

## BO1H-001/002 – hourly futures breakout calls (29-Oct-2026, owner request)
Rule family of the live 3h call on 1h bars (MCX 7, NIFTY/BANKNIFTY, ~180 stock futures, Jul-2022→Oct-2026, 2× costs).
* BO1H-001 base (20-bar breakout, vol >1.5×, EMA200, stop 2 ATR, 2R): stocks BUY −0.11R (11,429 trades), SELL −0.07R; MCX BUY −0.07R,
  SELL −0.21R; index BUY −0.20R, SELL −0.09R. OI confirm / no-resistance / no-14:15-15:15 filters do not make it positive.
* BO1H-002 grid (owner: ADX/ADR, EMA 20/50/100/200, volume 1.5/2/2.5×, OI, room, exits 1R / 2R / S-R stop and target):
  9,491 combos · 126 positive in train AND valid · 0 survive BH-FDR 10 % · of the 126, 22 positive in test (median −0.10R).
  Best train/valid combos (stocks BUY, vol 2.5×, ADX ≥25 rising, ADR used ≤0.8, OI long buildup) fall to ≈0 / negative in test.
Verdict: no hourly breakout call is supported; not deployed.

## MCX-TIGHT-001 – per-commodity tight filters, 1h / 3h / daily (29-Oct-2026, owner request)
10,626 combos (EMA side, volume 1.5/2/2.5×, ADX, ADR room, room to older level, 5 exits) per commodity × timeframe × side, 2× costs.
770 positive in train AND valid; 0 survive BH-FDR 10 % (samples per commodity are small: 20–80 trades per period).
Consistent across train / valid / test (not proven):
* GOLD 1h BUY (breakout, vol ≥2×, room, stop 2 ATR, 2R): +0.38 / +0.59 / +0.32R (59 / 30 / 52 trades); 311 of 327 passing combos
  positive in test – but 2026 ≈ −0.02R and the gold BULL market (2022-25) drives it; GOLD SELL loses (−0.25R).
* SILVER 1h SELL (below EMA100, vol ≥2×, ADX ≥20, room, stop 1.5 ATR, 1R): +0.19 / +0.31 / +0.43R, 72 % wins in test (58/32/36 trades).
* SILVER 1h/3h BUY, COPPER 1h BUY (vol ≥2.5×, S/R stop, 1R): positive in all periods on 15-50 trades each – thin.
* CRUDEOIL, NATURALGAS, ZINC, ALUMINIUM: negative in every period (ALUMINIUM −0.6R: costs vs a small range).
Today (29-Oct): no MCX breakout at all (prices inside their 20-candle range); SILVER 3h broke below 191,401 on 1.1× volume (< 1.5×).

## MCX-MULTI-001 – RSI reversal / divergence, candle & chart patterns, intraday ORB / ADR momentum (29-Oct-2026, owner)
7 MCX futures, 1h / 3h / daily 2022-26 (+15-min Aug-Oct 2026, 4 commodities), filters volume / ADX / trend / ADR, 3 exits, 2× costs.
MCX OI history is not available from Angel -> OI rules not testable (live only).
* GROSS edge before costs ≈ 0 for every hourly intraday idea (RSI 25/30/35 reversal −0.02…0.00R, ORB +0.02R, ADR momentum +0.05R,
  engulfing / pin / NR7 ≈ 0); costs ≈ 0.14R per trade -> all lose (exp1 −0.10…−0.21R). 15-min (2 months): all negative.
* RSI reversals lose on 3h and daily too (gross −0.23…+0.05R).
* 4,556 pooled combos: 6 positive in train AND valid, 0 survive FDR. Best: daily NR7 breakout BUY (stop 1.5 ATR, 1.5R)
  +0.11 / +0.18 / +0.35R (56 / 50 / 55 trades, 4 of 6 commodities positive in test); 3h double-bottom BUY with EMA200, ADX < 20
  +0.02 / +0.36 / +0.31R (62 / 32 / 51). Daily double bottom / engulfing gross +0.11…+0.15R (small samples).
Verdict: no RSI-reversal or intraday commodity call is supported; nothing deployed.
