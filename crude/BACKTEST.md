# Crude Oil engine – backtest (real Angel candles, 12-Oct-2020 → 21-Oct-2026)

Reproduce with `python -m crude.backtest`. Raw output is in `crude/reports/` (`backtest.json`, trade lists, `rolls.csv`).

## Data and method
- **Source.** Angel CRUDEOIL front-month 15-min candles: 82,561 bars over 1,448 sessions, 92% of weekdays.
  - Holes are reported, not filled: 9→16-Apr-2021 and 17-Dec-2021→2-May-2022.
  - Volume is present on 99.96% of bars.
  - **OI coverage is 0%.** Angel serves no historical MCX OI, so every trade ran under the "OI unavailable → fallback" policy.
- **Candle construction.** 1-hour candles are built from the 15-min ones and match Angel's own 1-hour closes on 99.99% of 15,980 bars. 3-hour candles use the live `three_hour()` code.
- **Rolls.** There were 68 contract switches, placed by the expiry rule. A volume jump confirms 53 of them.
  - The roll gap is estimated as the MCX move not explained by WTI × USD/INR. The median gap is 0.7% and the largest is 4.8%.
  - Indicators run on the back-adjusted series. Fills, P&L and charges use real prices.
  - No trade spans a switch.
  - No entries are taken in the 4 trading days before expiry: live trading uses the next contract then, and its history isn't available.
- **Fills and sizing.**
  - Entries fill at the next candle's open plus 2 ticks.
  - A gap through the stop fills at the open. When stop and target fall in the same candle, the stop is assumed to hit first.
  - Full MCX charges are included.
  - Sizing is 0.25% of ₹5,00,000 on CRUDEOILM (₹10/pt).
- **No tuning.** The parameters are the fixed values in `crude/config.py` and nothing was optimised. Both halves are reported; neither was used for fitting.

## Results at real paper sizing (cost ×1)
| Engine | Trades | Win % | Avg win | Avg loss | Expectancy | PF | Max DD | Worst losing streak |
|---|---|---|---|---|---|---|---|---|
| **New intraday** (15m + 1h) | 324 | 30.2 | ₹1,242 | −₹748 | **−₹146 / −0.19R** | 0.72 | −₹55,742 (−11.1%) | 18 |
| **New positional** (3h) | 1 | 0 | – | −₹1,164 | −1.07R | – | – | 1 |
| Baseline: Engine D intraday (1h) | 149 | 47.0 | ₹436 | −₹559 | −₹91 / −0.11R | 0.69 | −₹17,804 (−3.6%) | 6 |

- **Cost sensitivity, new intraday:** −0.19R at 1× costs, −0.42R at 2× and −0.64R at 3×.
- **Halves** (the out-of-sample check; nothing was fitted on either half): −0.11R for 2020-10…2023 (151 trades) and −0.27R for 2024…2026-10 (173 trades).
- **By year:** 2021 −0.13 · 2022 −0.08 · 2023 −0.08 · 2024 −0.42 · 2025 −0.40 · 2026 +0.12 (47 trades).
- **Walk-forward:** rolling 12-month windows stepped 6 months, with no re-fitting. 2 of 14 windows are positive.
- **By regime** (yesterday's trend and volatility): only uptrend/high-vol is positive, at +0.09R on 61 trades. Every other regime is negative.
- **Positional:**
  - 46 signals in 6 years; 35 of them could not be sized, because 1 mini lot with a 1.5–3.5×ATR(3h) stop risks more than ₹1,250.
  - At 1 mini lot for every signal, the diagnostic gives 25 trades, −0.26R and PF 0.46.
  - The sample is too small for any conclusion.

## Verdict
**FAIL** on the pre-registered criteria (`research/CRITERIA.md`). Expectancy is below 0.10R, the bootstrap p5 is below 0, PF is below 1.2 and the result is negative at 2× costs.
- The new intraday rules lose more than the existing 1-hour baseline per trade in R terms (−0.19 vs −0.11).
- The new rules are less bad in 2026 only.
- The main loss driver is the stop-loss: 164 of 324 exits average −1.17R, against a 30% win rate on 2R targets.
- Paper mode is therefore an **observation stage**, not evidence of an edge. Do not trade these signals with real money.
