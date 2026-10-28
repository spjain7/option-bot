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
