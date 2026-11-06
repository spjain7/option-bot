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

## CHAN-001 – the Telegram channel's apparent pattern, last 2 months (29-Oct-2026, owner request)
40 stock futures, 15-min + OI, 20-Aug→22-Oct-2026 (37 sessions, 860 signals); option value modelled from the futures path with the
previous day's real ATM IV (NSE bhavcopy). Patterns 09:30-11:30: prev-day-high break CE, prev-day-low break PE, failed gap (PE/CE),
5-day high/low break; filters volume 1.5/2/3×, OI support, NIFTY direction; exits signal-bar stop 1R / 2R / hold to 15:15.
* Futures after costs: every pattern negative (−0.3 … −0.9R; signal-bar stops are tight). Option (modelled) ≈ 0 … +5 %, failed-gap PE
  best (+4.6 % at 1R, 65 % wins, 40 trades) but negative in the first month.
* Channel-like filter (vol ≥ 2×, OI supports, market same way): 14-31 trades per pattern, all negative.
* 306 combos: 0 positive in both months.
* "Made high": 26 % of ALL signals saw the ATM option rise ≥ 30 % at some point before 15:15 (median best +8…+14 %), while the average
  trade held to 15:15 lost 2.4 %. Posting only the moves that ran (and their peak) produces a "perfect" record from a coin-flip rule.

## BIGMOVE-001 – footprints before big moves (29-Oct-2026, owner: "every move leaves a footprint")
178 F&O stocks, NSE bhavcopy Jul-2022→Oct-2026, 137,771 stock-days. Big move next day = |return| ≥ 2× its 20-day average (13.4 % of days).
* Footprints exist for SIZE: IV ÷ HV20 > 1.64 -> 25 % big-move days (1.9×); IV rank > 0.7 1.4×; IV up > 22 % in 5 days 1.4×; volume > 1.9× 1.3×.
  Calm / cheap options (IV ÷ HV < 0.77, range compression ATR5/ATR20 < 0.74) -> 3-8 % (big moves rarer). OI buildup label: no effect.
* Walk-forward model (train 2022-24, test 2025-26): AUC 0.66; each day's top 5 stocks -> 30 % big moves vs 13.6 % (2.2×).
* NOT direction: big-move direction accuracy 53.5 % vs 51.7 % always-majority (AUC 0.56); confident subset 55.6 %.
* Trading it: ATM straddle close -> next close on the top-5 (real option prices, 3 % costs): median −6 %, 25 % wins; the +1.4 % average
  comes from the best 1 % (Q1-2025); without them −6 %. The option market already prices the coming move (that IS the footprint).

## MCX-OI-001 – commodity volume + OI on the official MCX bhavcopy (29-Oct-2026)
1,111 days (Jul-2022→Oct-2026), 13 contracts (big + mini), most-traded expiry per day, OI change within the same contract, 2× costs.
* Next-day direction after LB / SB / SC / LU: 52-53 % up for every label – the label alone tells nothing (all commodities pooled).
* Pooled "follow the buildup" (LB/SC buy, SB/LU sell) and "fade" lose in every period (−0.05…−0.3 ATR next day).
* Precious metals only – follow the buildup with volume ≥ 1.5× and OI change ≥ 2 %: positive in train, valid AND test:
  SILVER 1-day +0.04 / +0.29 / +0.20 ATR (3-day +0.11 / +0.46 / +0.23), 57 % wins, 111 signals;
  SILVERM +0.23 / +0.12 / +0.23 (93); GOLDM (OI ≥ 5 %) +0.10 / +0.15 / +0.20, 3-day +0.68 / +0.39 / +0.73 (73).
  Matches the earlier GOLD / SILVER 1h findings. Small samples, not FDR-tested – candidate for a tracked test only.
* CRUDEOIL, NATURALGAS, COPPER, ZINC, ALUMINIUM: no OI / volume rule positive in both train and valid.

## PREMOVE-002 / REV5-001 – every ≥ 1.5 % intraday move, 5-min futures + OI, 208 stocks, 27-Jul → 29-Oct-2026 (30-Oct)
* Before a move starts: 5-min volume ~1.1× its normal (other moments 0.6×), the last hour's range is already WIDER (0.45-0.50 of
  the day range vs 0.31) – no "quiet squeeze" before moves; a tight range makes a move LESS likely (0.4×).
* OI up ≥ 1 % in 30 min + volume ≥ 2×: a move follows 3.4 % of the time (4.2× normal) but up/down 48/52 – size, not direction.
* Direction hints are mean-reversion: day already −1.5 % + near the low + below VWAP + volume 2× -> of the moves that follow
  80 % are UP (mirror: 69 % DOWN); same in Aug, Sep, Oct.
* Traded (entry next 5-min open, stop beyond the day extreme, 1R / 2R, exit 15:15, real lots, 2× costs): 2,379 trades, win
  44-49 %, gross ≈ 0 (−0.05 / +0.02 R), after costs −0.5R; −₹30 lakh total per lot over 3 months. Wider stops (≥ 0.6 %): still negative.
  Reason: even with the hint, 97-98 % of the time no 1.5 % move comes, and the costs on a tight intraday stop are ~0.45R.

## MCX-LOOKBACK-001 – breakout lookback 3 / 5 / 10 / 15 / 20 candles (30-Oct-2026, owner)
Live MCX rule otherwise unchanged (vol > 1.5×, EMA200 side, 3h stop 2 ATR 2R · daily 1.5 ATR 3R), 6 commodities (NATURALGAS not in
the Angel set), Jul-2022→Oct-2026, 2× costs.
* Daily BUY: N=5 +0.78R/trade, 94 trades, +0.96 / +0.59 / +0.80 (train/valid/test) vs N=20 +0.73R, 63 trades, +1.61 / −0.15 / +0.87
  -> shorter lookback = 50 % more trades, same average, positive in every period.
* 3h BUY: N=20 +0.24R (315), N=10 +0.22R (374), N=5 +0.20R (434, +0.09 / +0.14 / +0.36) – similar; more trades with shorter N.
* SELL (3h and daily): negative at EVERY lookback (3h −0.14…−0.17R; daily −0.04…−0.19R) – the lookback does not fix SELL.
* Best per commodity (3h BUY): GOLD +0.44…+0.60R at all N, ZINC/SILVER/COPPER +0.13…+0.36R, ALUMINIUM negative.

## PARAM-SWEEP-001 – one-at-a-time sensitivity of the live futures rules (30-Oct-2026, owner: "do this yourself")
MCX (6) and NIFTY/BANKNIFTY, 3h + daily, both sides; lookback, volume, EMA, stop ATR, target R, max hold; "better" = beats live
in train AND valid AND test, positive in all three, ≥ 60 % of the trades.
* MCX 3h BUY (live +0.23 / +0.13 / +0.28R, 374 trades): stop 3 ATR (+0.28 / +0.19 / +0.33, 236), target 3R (+0.26 / +0.13 / +0.35, 344),
  target 4R pass. Combination stop 2.5 ATR + 2.5R: +0.29 / +0.23 / +0.32R, 290 trades – better in every period.
* MCX daily BUY (5-day lookback, +0.96 / +0.59 / +0.80): no change beats it everywhere.
* MCX 3h SELL: negative at every setting tried. Daily SELL: 14-27 trades in 4 years – too few to tune.
* INDEX: 7-30 trades per rule in 4 years – too few to tune anything.

## TF5H-001 – 5-hour candles (30-Oct-2026, owner idea)
MCX 5h = 09-14 / 14-19 / 19-close blocks; NSE 5h = every 5 consecutive 1h bars. Live breakout family, 18 variants, 2× costs.
* MCX 5h BUY: 13 of 18 variants positive in train, valid AND test. Best: lookback 5, vol > 1.5×, stop 2.5 ATR, 2.5R ->
  +0.42R/trade (+0.34 / +0.60 / +0.40), 148 trades, every commodity positive (GOLD +0.63, SILVER +0.54, ZINC +0.43, COPPER +0.25,
  ALUMINIUM +0.10); 2023 −0.08, other years positive. Live 3h BUY ≈ +0.22R. 69 % of 5h trades have a 3h BUY within ±1 day.
* STOCKS 5h SELL (breakdown, vol ≥ 2×, stop 2.5 ATR, 2.5R): +0.18R, 63 % wins, 152 trades in 66 stocks, positive every year 2023-26
  (+0.26 / +0.34 / +0.10 / +0.25). Stocks 5h BUY and 3h BUY lose.
* MCX SELL and all INDEX settings: no robust result (index has 8-30 trades).
Selection caveat: 18 variants per timeframe/side, not FDR-corrected; MCX 5h BUY is robust across most variants.

## TFNH-001 – 2h / 4h / 5h / 6h candles (30-Oct-2026, owner: "same setting for 4 hours?")
Same 18 variants (lookback 5/10/20 · volume 1.5/2 · stop/target 2/2, 2.5/2.5, 1.5/3). Variants positive in all 3 periods:
* MCX BUY: 2h 4/18 · 4h 17/18 (median +0.31R) · 5h 13/18 (+0.34R) · 6h 16/18 (+0.38R). Best 4h: lookback 10, vol > 2×, stop 1.5 ATR,
  3R -> +0.50R (+0.53 / +0.27 / +0.64), 246 trades. Proposed 5h setting on 4h: +0.26R, 257 trades.
* STOCK SELL: 2h 4/18 · 4h 6/18 (median +0.13R) · 5h 7/18 · 6h 1/18. Best 4h: lookback 5, vol > 2×, 2 ATR / 2R -> +0.17R
  (+0.11 / +0.04 / +0.23), 892 trades. MCX SELL and stock BUY: negative on every candle size.

## TF2H-VOL – 2-hour candles with volume 2 / 2.5 / 3× (30-Oct-2026, owner)
* Higher volume helps on 2h: MCX BUY median +0.09R (2×) -> +0.16R (3×); stock SELL +0.05R -> +0.11R, 7 of 9 variants positive in all
  periods at 3×. Best MCX BUY 3×: lookback 10, 2.5 ATR / 2.5R +0.25R (+0.15 / +0.14 / +0.46), 228 trades.
  Best stock SELL 3×: lookback 10, 2.5 ATR / 2.5R +0.14R, 51 % wins, 1,022 trades (+0.11 / +0.01 / +0.20).
* Still below 4h (MCX BUY best +0.50R, 17/18 robust; stock SELL +0.17R). MCX SELL and stock BUY negative at every volume level.

## TF1H-VOL – 1-hour candles with volume 3 / 4 / 5× (30-Oct-2026, owner)
No variant positive in all three periods at any volume level. MCX BUY at 5×: −0.24…−0.45R in 2022-24, +0.07…+0.30R after (median
−0.07R overall); stock SELL 5×: +0.03…+0.08R, mixed by period; MCX SELL and stock BUY negative. 3-month log (22 Jul – 21 Oct):
MCX 1h BUY 5× 10 calls +₹4.26 lakh/lot (3 wins), stock 1h SELL 5× 212 calls 47 % wins +₹3.61 lakh, 82 stop hits – both behind the
4-hour rules (+₹10.83 lakh, +₹7.97 lakh).

## TOUCH-001 (30-Oct-2026) – enter on the touch vs wait for the candle close
Script `research/program/touch.py`, results `results/touch_summary.csv`. Live rules, 1-hour bar resolution, 2x costs, one trade at a time.
| Rule | CLOSE (today) n / R / all 3 periods | TOUCH at level n / R / all 3 | TOUCH, alert within the hour | TOUCH + volume pace |
|---|---|---|---|---|
| MCX 3h BUY | 441 / +0.16 / no | 830 / +0.15 / **yes** (total +121R vs +70R) | 719 / +0.08 | 464 / +0.14 / yes |
| MCX 4h BUY | 277 / **+0.39 / yes** | 745 / +0.21 / no | 655 / +0.10 | 324 / +0.11 |
| STK 3h SELL | 1,889 / +0.08 / no | 4,435 / +0.00 | 3,464 / −0.03 | 2,086 / −0.05 |
| STK 4h SELL | 913 / **+0.17 / yes** | 3,564 / +0.07 | 2,866 / +0.07 | 1,139 / +0.06 |
Waiting for the close enters ~0.8–1.0 ATR later, but the touch catches 2–4x more false breaks. Cutting a false break at the close
(TOUCH+cut) is worse everywhere. Only MCX 3h BUY gains from the touch, and only with an order resting AT the level (a pre-placed
stop-buy); an alert sent up to an hour later halves the edge. Verdict: keep close-based entries; candidate = MCX 3h BUY pending
stop-buy level alerts (needs owner approval).

## DELTA-001 (1-Nov-2026) – how option delta helps the live stock SELL calls
Script `research/program/delta.py`. Real NSE option closes → IV per strike; puts priced (Black-76) at the futures entry/exit, 2 % spread cost.
Trades on split-adjusted names (futures history ≠ option strikes, 8 %) skipped.
4h SELL, ₹ per lot per trade (futures: +₹3,325, all 3 periods positive):
| put delta | win | ₹/lot | premium ₹/lot | train / valid / test |
|---|---|---|---|---|
| 0.25 (OTM) | 38 % | +240 | 6,150 | +227 / −1,024 / +487 |
| 0.50 (ATM) | 46 % | +1,054 | 15,870 | +538 / −274 / +1,539 |
| 0.75 (ITM) | 52 % | +2,293 | 31,950 | +810 / +179 / +3,344 |
| 0.90 (deep ITM) | 57 % | +3,779 | 46,380 | +2,153 / +1,254 / +4,896 |
3h SELL: every delta below 0.9 loses before mid-2024 to mid-2025; futures +₹1,387. Net delta of option OI (level or 1-day change) as a
filter: no bucket better in all 3 periods – no help. Verdict: for a futures call, the option should be ITM (delta ≥ 0.75); OTM keeps almost
nothing of the move. Caveat: deep-ITM stock options trade thinly – real spreads may exceed 2 %.

## ALLPAT-001 (1-Nov-2026) – all 20 patterns of the "Price Action RoadMap" reel
Script `research/program/allpat.py`, summary `results/allpat_summary.csv`. Daily candles, trend context, entry on the break of the
pattern candle within 3 days, stop beyond the pattern, 1R / 2R, 20 days, normal costs. Success = target before stop.
Stocks (biggest sample): 17 of 20 patterns lose or are flat; success at 1:1 is 24–54 % (break-even ≈ 52 %).
Positive in all 3 periods at 2R: Hanging Man (stocks +0.18R / 1,238; NSE index 2011-26 +0.21R) – already live; Gravestone Doji
(stocks +0.10R / 218) – new, small edge; NSE index 2011-26 Evening Star (+0.29R, 37), Three Outside Down (+0.33R, 61), Tweezer Top
(+0.11R, 77); MCX Piercing Line (13 trades – too few). MCX Hammer +0.31R (live). Worst: Three Outside Up (stocks −0.20R), Bullish
Engulfing (−0.14R), Evening Doji Star (−0.17R).

## IMPROVE-001 (1-Nov-2026) – confluence, trade management, regime filter on the core breakout calls
Script `research/program/improve4.py`, summary `results/improve4_summary.csv`. 2x costs, 1-hour exits, previous-day daily values only.
| Rule | Base n / win / R | + daily trend (D) | + daily ADX ≥ 20 | D + ADX | Half at 1R + stop to entry | Stop to entry at 1R |
|---|---|---|---|---|---|---|
| MCX 3h BUY | 442 / 45 % / +0.16 (valid −0.03) | 304 / 47 % / +0.25 ✓ | 241 / 49 % / +0.30 ✓ | 198 / 48 % / +0.31 ✓ | 59 % / +0.08 | 33 % / +0.08 |
| MCX 4h BUY | 277 / 41 % / +0.40 ✓ | 186 / 42 % / +0.47 ✓ | 147 / 46 % / +0.66 ✓ | 119 / 46 % / +0.66 ✓ | 55 % / +0.07 | 27 % / +0.17 |
| STK 4h SELL | 913 / 56 % / +0.17 ✓ | 596 / 60 % / +0.21 ✓ | 468 / 59 % / +0.20 ✓ | 365 / 61 % / +0.21 ✓ | 58 % / +0.14 | 53 % / +0.16 |
✓ = positive in all 3 periods. Half-booking / breakeven raise the win rate but cut the profit (they stop the big winners) – rejected.
Daily ATR above median: no help. Stock OI label (daily-based): worse. NIFTY trend for stock SELL: +0.21R, D + NIFTY fails 2024-25.
Recommendation: daily ADX ≥ 20 + daily trend agreeing on all three core rules (about half the calls, higher R per call).

## WALLS-001 (1-Nov-2026) – option-OI walls (largest call / put OI strike) on 183 stock futures, daily, 2022-26
Script `research/program/walls.py`, summary `results/walls_summary.csv`. Walls from the previous day's real option OI. 2x costs.
| Setup | BUY n / win / R | SELL n / win / R |
|---|---|---|
| Close through the wall, vol ≥ 2x (2R) | 1,494 / 42 % / −0.07 | 1,221 / 52 % / +0.05 |
| + futures OI up (2R) | 702 / 40 % / −0.11 | 464 / 58 % / **+0.16** (2022-24 −0.02, 2024-25 +0.09, 2025-26 +0.35) |
| Stop-hunt beyond the wall, close back (2R) | 571 / 41 % / −0.11 | 617 / 47 % / +0.10 (2022-25 ≤ 0) |
| ZYDUSLIFE sequence (stop-hunt, then wall break ≤ 5 days) | 51 / 47 % / +0.01 | 55 / 47 % / −0.05 |
| ZYDUSLIFE sequence + OI up | 11 trades | 19 / 74 % / +0.30 (too few) |
Verdict: the ZYDUSLIFE sequence is not a repeatable BUY edge. Put-wall breakdown + OI up (SELL) works since mid-2024 only – watch, not live.

## LIQTL-001 (3-Nov-2026) – "Liquidity Trendline With Signals [StratifyTrade]" (owner's Pine script)
Script `research/program/liqtl.py` (faithful port: pivots 5/5, shared 'broken' flag, padding 2), summary `results/liqtl_summary.csv`.
212 stock futures, 5-min 27-Jul → 29-Oct-2026; 10/15/30 min built from 5-min; 3-min not testable (no 1-min history).
Entry next bar open, intraday (flat 15:20), costs 0.08 % round trip. Stop 1 ATR14 (the signal-bar stop is far worse: risk too small vs costs).
| TF | BUY win / R (1R) | SELL win / R (1R) | best net | gross R (before costs) BUY / SELL |
|---|---|---|---|---|
| 5 min | 47 % / −0.46 | 51 % / −0.39 | −0.32 (SELL 3R) | −0.06 / +0.02 |
| 10 min | 46 % / −0.32 | 52 % / −0.21 | −0.17 (SELL 3R) | −0.06 / +0.06 |
| 15 min | 44 % / −0.31 | 52 % / −0.17 | −0.12 (SELL 3R) | −0.10 / +0.05 |
| 30 min | 47 % / −0.23 | 52 % / −0.06 | ≈ 0 (SELL 2-3R) | −0.08 / +0.09 |
Verdict: BUY breakouts lose even before costs; SELL breakdowns have a small gross edge that costs remove. Not tradeable as is.

## LIQTL-002 (3-Nov-2026) – the same trendline indicator on MCX
Script `research/program/liqtl_mcx.py`. 7 commodities, 1-hour candles Jul-2022 → Oct-2026, stop 1 ATR, next-bar-open entry.
Intraday (flat 23:20), 2R: BUY 999 trades 36 % win, gross +0.07R, net (2x costs) −0.49R; SELL 1,077, 31 %, gross −0.03R.
Swing 3R best gross: BUY +0.17R, net −0.40R. Every period negative after costs. SILVER 2R intraday: BUY 148, 37 % win, gross +0.09R,
net −0.21R; SELL 166, 33 %, −0.30R. Per commodity gross BUY: COPPER +0.30R, GOLD +0.13R, SILVER +0.09R; all negative after costs.
SILVER 3/5/10/15/30-min on the ~2.5 days of 1-minute stream: 11 trades in all, 2 wins, net −3,375 points (too few to judge).

## LIQTL-003 (3-Nov-2026) – trendline signals held until the opposite signal (how the owner trades it)
Script `research/program/liqtl_rev.py`, summary `results/liqtl_rev_summary.csv`.
Stocks 5/10/15/30-min, intraday, no stop: BUY −0.67 / −0.49 / −0.38 / −0.23R; SELL −0.17 / −0.07 / −0.09 / 0.00R – still no edge.
MCX 1-hour held overnight, no stop, reverse on the opposite signal: BUY 859 trades 43 % win +0.19R net, but 2022-24 −0.45R,
2024-25 +0.36R, 2025-26 +1.03R (the metals bull run: GOLD +2.29R, SILVER +0.33R, COPPER/ZINC +0.49R; CRUDE −0.18, NATGAS −0.59,
ALUMINIUM −1.18). SELL −0.85R. Verdict: a trend-following BUY that pays only in a strong trend – not robust.
Why the owner's chart differs: every chart signal on 2/3-Nov fell in hours with no stream data (loop not running); the chart
triangle is drawn one candle early (plotshape offset −1); fixed 1:2 exits cap a 5-min silver win at ≈ 800 points.

## LIQTL-004 (4-Nov-2026) – trendline indicator on 3 years of MCX 3/5/10/15/30-min (Angel front-month, 7 commodities)
Script `research/program/liqtl_mcx5.py`; summary `results/liqtl_mcx5_summary.csv`, per name `results/liqtl_mcx5_by_name.csv`.
Port verified against the owner's TradingView screenshots (2/3-Nov signals match; his chart is in UTC).
No filter: every TF / exit loses after costs (5-min −2.3R, 30-min −0.6R; gross only +0.0…+0.27R). 3/5-min: cost ≥ 1R on most metals.
Choppy filter that works: previous-day daily trend up (EMA20 > EMA50, close > EMA50) + signal-candle volume ≥ 1.5x (DT+VOL).
SILVER+GOLD+CRUDE 15-min DT+VOL BUY, hold to opposite signal: 234 trades, 51 % win, +0.52R (2x costs), all 3 periods positive.
SILVER 15-min DT+VOL BUY, 3-ATR trailing stop: 90 trades (2.7/month), 52 % win, +0.84R, avg +598 pts (win +1,886 / loss −811),
periods +0.55 / +0.29 / +1.29R. GOLD same: 97, 39 %, +0.32R (2023-24 −0.09). SELL side: no robust version.
Baseline without the trendline (daily up + volume + up candle, same exit): −0.10…−0.24R – the trendline adds the edge.
Not usable: ALUMINIUM, ZINC, NATURALGAS, COPPER (costs 1-6R on intraday ATR). Caveat: 2023-26 was a metals bull market.

## STRETCH-001 (6-Nov-2026) – why the live GOLD calls failed; stretch / RSI / trend filters on the MCX breakout rules
Script `research/program/stretch.py`. 7 commodities, 4 years, live rules, 2x costs.
MCX BUY breakouts work: 1d BUY 61 trades 59 % +0.94R; 3h BUY 383, 48 %, +0.22R (+0.28R with the daily trend). Stretched BUYs
(> 3 ATR above daily EMA20 or RSI > 70) do BEST (+0.58…+1.86R) – momentum, so no stretch filter.
MCX SELL breakouts lose: 3h SELL 182 trades 37 % −0.15R (with the daily downtrend −0.40R); 1d SELL 8 trades −0.27R. No filter fixes it.
GOLD: BUY 99 trades +0.66R, SELL 29 trades −0.07R. Live GOLD SELLs on 30-Oct came after a −2.8 % day (RSI 28.7) and reversed;
the 5-Nov 3h EMA BUY was against the daily downtrend (EMA20 < EMA50) after a +4.5 % bounce.

## SEARCH-ALL-001 (6-Nov-2026) – 6,108 combinations, 5.1 M trades, walk-forward + BH-FDR (q < 0.10)
Script `research/program/search_all.py`; `results/search_all_summary.csv`, `results/search_all_robust.csv`. 118 robust, all one-sided:
MCX BUY (100): best daily BO N20/N55 + ADX ≥ 25, 1.5 ATR / 2R: 83 / 72 trades, 58-60 % win, +0.56 / +0.60R, 6-7 of 7 commodities
positive; 4h BO N10 vol ≥ 1.5x + daily trend, 2 ATR / 3R: 259 trades, 44 %, +0.42R, 7/7; 3h/4h EMA20 pull-back in daily uptrend +0.27R.
STOCKS SELL in a daily downtrend (17): 3h BO N5 vol ≥ 2x 1.5ATR/2R 1,335 trades +0.13R; 4h NR7 breakdown 2,341 +0.125R; 4h EMA20/50
pull-back SELL 3,101 +0.11R. NSE index daily N5 breakdown in downtrend SELL 98 trades +0.29R (q 0.098).
Not robust anywhere: MCX SELL, stock BUY (stock daily BO BUY −0.07…+0.04R), RSI2, Bollinger squeeze, liquidity trendline, stop-hunt.
Caveat: 2022-26 was a metals bull market – MCX BUY results partly reflect it.

## WKMO-001 (6-Nov-2026) – weekly and monthly breakouts on 20 years (MCX 2006-26, NIFTY/BANKNIFTY futures 2011-26)
Script `research/program/wkmo.py`, `results/wkmo_summary.csv`. 2x costs; periods 2006-12 / 2013-19 / 2020-26.
MCX weekly 20-week BUY, 2 ATR / 3R: 146 trades (7.6 a year, all 7 commodities), 49 % win, +0.64R (+0.70 / +0.24 / +0.85).
MCX monthly (close above last month's high) BUY 2 ATR / 3R: 104 trades, 62 %, +0.68R, 7/7 commodities positive.
MCX weekly 52-week BUY 2 ATR / 3R: 106 trades, 55 %, +0.75R. Live weekly rule (20-week, 3 ATR / 2R): BUY 137, 59 %, +0.52R ✓;
SELL 92, 35 %, −0.23R ✗. Index: monthly BUY 2ATR/3R 29 trades +0.45R; weekly 4/10-week BUY +0.38…+0.45R; live-style monthly-level
BUY (daily close above last month's high) 175 trades +0.37R. Every SELL version loses over 20 years (MCX and index).

## SEARCH-V2 (6-Nov-2026) – 14 new families × 15m-1d × regime split (5,292 combinations, 4.28 M trades, BH-FDR)
Script `research/program/search_v2.py`; `results/search_v2_summary.csv` / `_robust.csv` (64 robust). Robust only on:
MCX BUY with the daily trend (1h, 2h, 3h, 4h, 1d), stock SELL with the daily trend (2h, 3h, 4h) and stock daily RSI>80 BUY.
Nothing robust: MCX 15m / 30m (costs ≥ edge), index futures (too few trades per rule), every RSI-reversal threshold
(30/70 … 15/85), RSI divergence, pin bar, failed breakout, ORB, Supertrend.
Promoted to the live rulebook (alerts/rulebook.py, parity with this code 24/24):
MCX 4h EMA13/48 (112, 52 %, +0.62R) · 4h MACD zero (163, 53 %, +0.44R) · 2h momentum candle (309, 42 %, +0.36R) · 2h EMA9/21
(357, 45 %, +0.31R) · daily breakout retest (121, 55 %, +0.47R) · 1h MACD signal (742, 42 %, +0.21R) · stock 3h MACD zero SELL
(1,036, 49 %, +0.17R) · stock 3h EMA9/21 SELL (1,274, 49 %, +0.15R) · stock daily RSI>80 BUY (234, 55 %, +0.27R).
Stock 2h/4h rules not promoted: research candles were not day-anchored, live candles would differ.

## PORTFOLIO-001 + LONG20-001 (6-Nov-2026)
PORTFOLIO-001 (`portfolio.py`): 13 live rules with research code re-simulated trade by trade 2022-26 (2x costs).
| Overlap policy | calls/day | exp R | PF | total R | max DD R | losing streak |
|---|---|---|---|---|---|---|
| one call per instrument + side (was live) | 3.3 | +0.149 | 1.30 | +497 | 90.5 | 20 |
| one per instrument + side + timeframe (now live) | 4.6 | +0.217 | 1.42 | +1,013 | 89.7 | 23 |
| every rule independent | 6.4 | +0.220 | 1.44 | +1,430 | 119.4 | 32 |
Years (now-live policy): 2022 +0.18 · 2023 +0.05 · 2024 +0.28 · 2025 +0.26 · 2026 +0.24R.
LONG20-001 (`long20.py`): 1,604 combinations on 20 years of daily candles. MCX BUY: 60 robust incl. the 2013-19 bear years ->
the BUY edge is not only the 2022-26 bull market. MCX SELL: none robust, none positive in 2013-19 beyond +0.26R (n 95). Index
(2011-26): 8 robust BUY (EMA 20/50 cross, RSI>70, 5/10/20-day breakouts); no SELL. Live MCX daily 20-day+ADX rule: 20 years
only +0.15R (2006-12 −0.02, 2013-19 +0.02) -> tier B; 55-day vol 2x breakout +0.49R in every era -> promoted.

## STK-ANCHOR-001 (6-Nov-2026) – stock 2h / 4h on day-anchored candles (live-reproducible)
`stk_anchor.py`, `results/stk_anchor_summary.csv`. 1,712 combinations, 24 robust – all SELL in a daily downtrend.
Best: 2h Bollinger squeeze breakdown 2ATR/3R 1,014 trades +0.27R (+0.23/+0.31/+0.28); 4h MACD zero 1.5ATR/2R 1,034 +0.19R;
4h EMA9/21 +0.16R; 2h EMA20/50 +0.19R. No stock BUY passed on 2h / 4h. Promoted: 2h SQZ SELL, 4h MACD-zero SELL (parity 8/8).

---
## RSIX-001 — RSI extreme reversal + reversal-candle breakout (6-Nov-2026)

**Question (owner):** does "RSI touches 75/25 → reversal candle → break of that candle's high/low" work on MCX?

**Grid.** 7 MCX commodities × 15m/30m/1h/2h/4h/1d. Extremes: touch / cross back / stay 3 candles / divergence;
levels 20/25/30 (70/75/80); candles none / bull-bear / hammer-star / engulfing / any; entries market next open /
**buy-stop above candle high (3 candles)** / close-confirmed break / retest; stops candle low / 1.5 ATR; exits 1/2/3R,
3-ATR trail, half at 1R. Stage 2 added RSI 7/21, daily-trend with/against, ADX<20 / >25, volume ≥1.5×.
Stage 1: 25,835 pooled combinations; stage 2: 215,988. 2× costs, completed candles, chronological splits
(intraday 2023-24 / 24-25 / 25-26; daily 2006-12 / 2013-19 / 2020-26).

**Verdict: the RSI extreme reversal does NOT work intraday on MCX.**
| tf | mean R of all variants | share positive in all 3 periods |
|---|---|---|
| 15m | −0.70 … −1.09 | 0 % |
| 30m | −0.47 … −0.79 | 0 % |
| 1h | −0.30 … −0.56 | 0 % |
| 2h | −0.21 … −0.41 | ≤ 1 % |
| 4h | −0.11 … −0.47 | ≤ 2 % |
| 1d BUY | −0.04 … −0.26 | 2–7 % |
Walk-forward (rank on train, keep valid > 0, read test): per-commodity survivors positive in test 19 / 43 = chance.
SELL side negative on every timeframe (consistent with all earlier MCX SELL work).

**One pocket survives — daily BUY, intrabar trigger:** RSI(7) touched ≤ 30 in the last 3 days, bullish candle
(close > open, close in upper half), ADX(14) < 20; BUY-STOP at that candle's high for 3 sessions (cancel if its low
breaks first); SL 1.5 ATR.
| exit | trades | win % | R | PF | 2006-12 | 2013-19 | 2020-26 | commodities positive |
|---|---|---|---|---|---|---|---|---|
| 3-ATR trail | 271 | 42.4 | +0.25 | 1.45 | +0.27 | +0.26 | +0.23 | 7 / 7 |
| 3R target (implemented) | 264 | 45.8 | +0.19 | 1.33 | +0.19 | +0.12 | +0.26 | — |
Avg win +1.91R / avg loss −0.97R (trail); max DD 16R over 20 y; ≈ 0.16 calls per commodity per month (~1.1 / month MCX).
Close-confirmed break (BRKC) of the same setup: +0.07R — **the intrabar break of the candle high is what carries the edge.**
Caveat: selected from >200k variants; the evidence is stability (3 periods, 7/7 commodities, neighbours L25/L30 and
bull/any all positive), not significance after full multiple-testing correction. Tier B.

Implemented on main 8a75fb6 as `RB_MCX_1d_RSIX_BUY` (pending stop-entry call, activated/cancelled/expired in
four_hour.track). Parity: live mask == research mask on all 7 commodities (20-year daily).
Files: rsix.py, rsix_select.py, rsix_final.py, results/rsix_pooled.csv, rsix_selected.csv, rsix_per_commodity.csv,
rsix2_breadth.csv, rsix2_top500.csv, rsix_final_trades.csv.

---
## MISSED-001 — big MCX moves the engine called / missed (6-Nov-2026)

Big move = daily zig-zag swing ≥ 6 ATR(14), 2022-08 … 2026-10, 7 commodities → 89 moves (44 UP avg +50 %, 45 DOWN avg −22 %).
Live rules evaluated with the production rulebook code; "caught" = signal before half the move was done.
| | moves | caught early | why missed |
|---|---|---|---|
| UP | 44 | 31 (70 %) | 13 — all started with the daily trend NOT up (V-reversals; trend-filtered rules wait) |
| DOWN | 45 | 0 | no live MCX SELL rule |
First rule to catch: 4h EMA13/48 (12 moves, +0.38R realistic trade), 2h MOMO (5, +1.75R), 4h MACD0 (4, −0.46R),
**1d RSIX (4, +0.88R — the new rule catches part of the reversal blind spot)**.

**Blind spot 1 — down moves.** Every SELL family signalled 80–98 % of the down moves early, but on ALL their signals
each one loses (−0.03 … −0.69R after 2× costs). Catching the down moves this way would add net-losing calls → not fixed.
**Blind spot 2 — V-reversal up moves.** Daily RSI cross-back above 30 looked excellent in 2022-26 (+0.82R, 62 % win)
but over 20 years it is −0.02R (−0.21 / −0.04 / +0.33 by period) — a 2020-26 commodity-bull artefact. Only the RSIX form
(reversal candle + ADX < 20 + stop above the candle high) holds in all three 20-year periods.
Files: missed.py, results/missed_moves.csv, results/missed_alternatives.csv.

## RSIX-001 NSE transfer (finalist unchanged)
| market | side | n | R (3R exit) | periods | verdict |
|---|---|---|---|---|---|
| NIFTY 2011-26 | BUY | 30 | −0.11 | −0.34 / +0.16 / −0.11 | no |
| BANKNIFTY 2011-26 | SELL | 33 | +0.26 | +0.63 / +0.28 / +0.07 | too few trades |
| Stocks 2022-26 | BUY | 910 | −0.05 | +0.27 / +0.17 / −0.24 | unstable, no |
| Stocks 2022-26 | SELL | 1,103 | +0.05 | −0.33 / −0.01 / +0.31 | unstable, no |
RSIX stays MCX-daily-BUY only. File: rsix_nse.py.

---
## STRUCTX-001 / ROLLCHECK-001 / MISSED-002 (6-Nov-2026, owner directive "Stop endless testing")

Pre-registered hypotheses and promotion bar are in the header of `structx.py` (BH q < 0.10 over all 1,920 combinations,
positive in all 3 periods, n ≥ 60, ≥ 4/7 commodities, 2× costs, never chase > 0.5 ATR past a trigger).
**Result: 0 / 1,920 pass.**

| hypothesis | result | failure mechanism |
|---|---|---|
| H1 stop-entry above the signal candle vs next open (same signals) | +0.09R better in 80 % of matched cells, but only +0.01R in the latest period. On the 4 LIVE 2h/4h rules with exact parameters: next open 1,016 trades +0.35R, stop-entry 779 trades +0.34R (worse on both 4h rules) | the stop mainly filters out signals that never follow through; the live rules are already filtered by the daily trend, so little is left to remove. **Production entries unchanged.** |
| H2 V-reversal = market-structure shift (break of the last lower high after a ≥ 4 ATR fall) | 2h/4h/1d mean −0.15…−0.01R; caught 2 / 13 missed V-moves | the "higher low" forms again and again inside down-legs (13 failed MSS setups in the 45 days before the 13 V-moves) |
| H3–H6 MCX SELL (failed recovery, support retest, momentum breakdown, pull-back continuation) | every setup × tf negative on average (−0.35…+0.05R); best 2h momentum breakdown q = 0.89 | see MISSED-002 below |

**MISSED-002 (45 missed down moves, 4h).** At least one structure SELL gave an early entry on 40/45 moves, and on those moves
it looks great (pull-back continuation +0.97R on 38 moves). On ALL its 711 signals it is −0.17R: 98 identical setups failed
in the 45 days before those moves. Down moves are visible in hindsight; at the time they are indistinguishable from the
many failed sell setups in a market with upward drift. Same for the 13 V-reversals: 4h EMA9/21 without trend filter fires
early on 13/13 (+1.23R on those) but counter-trend 2h/4h BUY variants average −0.05…−0.28R.

**ROLLCHECK-001 — data integrity finding.** The 20-year daily MCX file is an *unadjusted* front-month stitch with no contract
labels (verified: equals the 1h front-month closes; gaps on roll days are 2–6× normal). Earlier daily/weekly/monthly
validations held trades through roll gaps. Roll calendar inferred per commodity from the flagged 1h data; every live rule
re-validated (results/rollcheck.csv):
| rule | before | roll-adjusted (realistic) | periods 06-12/13-19/20-26 | verdict |
|---|---|---|---|---|
| 1M monthly close > prev high | +0.61 | **+0.89** (n 93) | +0.82/+0.39/+1.32 | keep |
| 1w 20-week breakout | +0.40 | +0.29 (n 218) | +0.35/+0.04/+0.43 | keep |
| 1d BO55 vol 2× | +0.47 | +0.32 (n 145) | +0.24/+0.49/+0.35 | keep |
| 1d RETEST | +0.27 | +0.23 (n 672) | +0.14/+0.12/+0.40 | keep |
| 1d RSIX (3R) | +0.20 | +0.16 (n 250) | +0.08/+0.05/+0.36 | keep, evidence re-stated (trailing exit +0.19, +0.21/+0.18/+0.17) |
| 1d BO 20d + ADX ≥ 25 (engine) | +0.16 | **+0.02** (n 541) | −0.09/−0.10/+0.25 | **fails – recommend demote to logged-only** |
rsix.daily_long now flags rolls (and > 25 % glitches) for all research that uses it.

**Production (main 64d267b):** signal lifecycle – EARLY WARNING (info only) → CONFIRMED SETUP (pending stop) → ACTIONABLE
(triggered) → INVALIDATED; funnel statistics split trend BUY / reversal BUY / SELL / early / setup / actionable.

---
## EQ – NSE cash equity (6-Nov-2026). BUY only. Source: official NSE cash bhavcopies 2005-26 (no futures, no OI)

**Data (eq_data_check.json):** 5,393 sessions, 2005-01-03 … 2026-11-05; 306 weekdays without a file = exchange holidays
(10-19/yr); no duplicates / non-positive prices; corporate actions via NSE's adjusted PREVCLOSE (35,010 factors) + fix for
the UDiFF format (from Jul-2024 PREVCLOSE is unadjusted: bonuses/splits/demergers detected by >40 % open gaps – price bands
cap normal moves at 20 %); ISIN carried back before mid-2011 (one continuous history per company); 539 ETF / fund units
excluded (ISIN INF…); point-in-time liquid universe (60-day median turnover ≥ ₹25 cr, price ≥ ₹50, ≥ 250 sessions);
3,029 securities that later stopped trading are included → no survivorship bias. Costs: Angel One schedule (delivery
0.393 % round trip incl. 0.05 %/side slippage; intraday 0.163 %).

| family | result (after costs) | verdict |
|---|---|---|
| Delivery swing ≤ 20 sessions (A–G: PDH, 20/55-day breakout, retest, EMA pull-back, momentum consolidation, RSI reversal, RS+sector), 288 combinations | gross ≈ 0 (−0.01…+0.05R), costs ≈ 0.07R → 0/288 pass | rejected: moves too small vs costs |
| H-B 26/52-week closing-high breakout, EMA50 trend exit | per trade +0.22R, PF 1.49, t 6.7, all 4 blocks positive; edge in the top 2 % of trades (96 stocks, 15 years, half in 2020/2023); daily mark-to-market portfolio 2016-26 only 4.5-8.5 % CAGR, DD −37…−50 % | rejected as a portfolio (worse than the equal-weight universe) |
| **H-A monthly relative-strength portfolio** (12-1 month return / 126-day vol, top 10, market filter) | chosen on 2006-15: CAGR 11.0 % vs 5.6 % EW; **2016-26 OOS: CAGR 16.9 %, Sharpe 0.91, maxDD −31 %** vs EW 12.5 % / −44 % and Nifty ~11.8 % incl. dividends / −38 %; 7 of 12 filtered variants beat EW OOS; bad years 2008 −35 %, 2018 −30 % | **implemented** (main `cashstock/`, live-monitoring candidate) |
| Intraday cash (57 sessions of 5-min, ORB 5/15/30, retest, pull-back, VWAP, RVOL, PDH, trend, failed-breakout) | all negative; ORB gross +0.04R vs cost 0.16R, 67 % false breaks | rejected on this sample; 2-year 5-min data downloading |
Production/research parity of the ranking: 10/10 names identical in 6 of 7 test months (the 7th differs only by a company rename).

### EQ-MOM-002 robustness of the monthly relative-strength portfolio (rules fixed on 2006-15, nothing re-tuned)
| check (2016-26 OOS unless noted) | CAGR | Sharpe | maxDD | note |
|---|---|---|---|---|
| base | 16.9 % | 0.91 | −31 % | beta 0.41, alpha +12.2 %/yr vs EW universe (11.5 %, DD −44 %) |
| 2006-15 | 11.0 % | 0.62 | −37 % | EW 5.6 % (DD −72 %), alpha +9.1 %/yr |
| costs ×2 / ×3 | 15.2 % / 13.6 % | 0.84 / 0.76 | −32 / −34 % | still above EW |
| rebalance day 5 / day 10 | 19.0 % / 16.3 % | 0.95 / 0.76 | −41 / −42 % | return robust to timing, drawdown not |
| ≤ 2 names per correlation cluster | 17.7 % | 0.95 | −31 % | holdings' avg correlation 0.24 → concentration not a problem |
Regimes (month start): bull +2.33 %/month vs EW +1.04 %; bear −0.03 % vs +0.98 %; sideways −0.13 % vs +0.80 % – the edge
is a bull-market edge; the market filter avoids crashes but misses rebounds. Beat EW in 12 / 21 years. Turnover 3.8 names
per month, cost drag ≈ 1.3 %/yr. Sector-index filter pending the NSE industry map (Angel equity job tonight).
