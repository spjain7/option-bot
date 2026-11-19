# Shadow test – SF-CONT-SELL-v1 and CM-CONT-BUY-v1 (started 11-Nov-2026)

SHADOW ONLY. No Telegram message, no order, nothing on `main` and nothing read by production. Neither strategy is promoted.

| Version | Label | Market | Rule (fixed; see `rules.py`) |
|---|---|---|---|
| SF-CONT-SELL-v1 | **CONTINUATION SELL** (not an RSI reversal) | NSE stock futures, daily | RSI(14) ≤ 25 on any of the last 10 sessions and the close above the prior 5-session high: sell the bounce. Next open, stop 5-session high + 0.1 ATR, 3R target, 15 sessions |
| CM-CONT-BUY-v1 | **CONTINUATION BUY** (momentum, not a reversal) | NSE cash, weekly | Weekly RSI(14) crosses to ≥ 75 in the least-liquid third of eligible stocks. Next week's open, stop 5-week low − 0.1 ATR, 1R target, 10 weeks |

## How it runs
- **Schedule:** every weekday at 21:47 IST, as a scheduled cloud task (`nightly.sh`). It reads official NSE end-of-day files (cash and F&O bhavcopy, F&O ban list, today's price bands) and the Best-5 depth that production records.
- **Storage:** ledgers and reports go to branch `shadow-state`.
- **Ledger (`signals_<id>.csv`):** append-only, one row per qualifying signal, never filtered. The same signal on a later run is not added again.
- **Trades (`trades_<id>.csv`):** rebuilt from the ledger and official prices on every run. Statuses: PENDING ENTRY · ACTIVE · TARGET HIT · STOP HIT (including gap through stop) · TIME EXIT · NOT EXECUTABLE (reason) · OVERLAP (one open trade per stock, as in research). A signal found after its entry open is flagged LATE.
- **Execution basis:** stock futures use the actual contract (next month on expiry day), roll at expiry with an extra round trip, 0.03 % slippage per side, the date-based STT, and the F&O ban list (no new positions). Cash uses the next open plus 0.05 % slippage, a ₹5 lakh order's share of the day's turnover, locked-circuit checks and the price band. Each trade records MFE, MAE, sessions held, net R, net %, ₹ per lot or per 100 shares, market regime and sector.
- **Research basis:** each trade also gets the back-test outcome on adjusted cash prices. The gap between the two shows how much real execution costs.
- **Best-5 depth:** when the entry instrument is in the recorded set, the first snapshot of the entry day gives the measured spread and imbalance. No historical depth exists.
- **Immutability:** `meta.json` stores a hash of the rules. A changed rule cannot continue a ledger; it needs a new version id and a new ledger.
- **Reports:** a daily reconciliation report (data dates, new signals, a fresh re-detection compared with the ledger, late detections, open, not executed, closed) and a weekly performance report on Fridays (results on both bases, against the research expectation, by regime and sector).

## Rule verification (requirement 1, `parity.py`)
The shadow rules replay the research trades exactly:
- SF: 1019 of 1019 trades, R difference 0.0, same exit dates.
- CM: 814 of 814, same result.
- Signals inside an open trade of the same stock (not taken in research, now recorded as OVERLAP): 443 for SF and 184 for CM.

## SF – why 2026 is negative, and falling markets (requirement 7, `results/investigate_sf.json`)
- **2026 has not worked even before costs:** gross +0.007R, net -0.064R over 161 trades. 70 % hit the stop and 23 % the target, against 58 % and 40 % in good years. The average MFE fell to 1.44R. So the signal itself weakened; costs alone do not explain it.
- **Costs matter:** STT on futures went to 0.05 % from Apr-2026. The cost per trade rose from about 0.05R (2018–24) to 0.08R; in the 0.05 % STT period, net is +0.043R over 94 trades.
- **2026 losses came from crowded days:** on days with 5 or more signals (a market-wide bounce) 2026 made -0.191R over 102 trades. Isolated signals made +0.155R over 59. Feb and Apr 2026 were the worst months.
- **Falling markets – depends on the market measure:**
  - Against the top-100 equal-weight market and its EMA200: up +0.274R, down +0.295R, so no weakness over 2018–26.
  - The earlier weakness used an F&O-stock market measure.
  - In 2026 the down-market trades lost -0.241R over 28 trades.
  - By the market's 20-day return: a −5 % to −2 % market is the best bucket (+0.722R); a flat 0 to +2 % market is the worst (-0.036R).
- **Real futures execution instead of the cash proxy** (same engine as the forward test, F&O ban lists for all 532 entry days):
  - Not executable: 85 of 1020 entries; 20 because of the F&O ban and 65 because there was no contract on the entry day.
  - The executed trades make **+0.199R** on futures against +0.284R on the research basis (-0.085R per trade, from the basis move, slippage and rolls).
  - 2026 on futures: -0.084R over 154 trades.

## CM – execution and overlap with the momentum portfolio (requirement 8, `results/investigate_cm.json`)
- **Liquidity is not the problem at ₹5 lakh:** the median order is 0.079 % of the entry day's turnover, and 0.0 % of trades exceed 2 %. 749 of the 814 trades could be matched to the raw files; the rest changed symbol.
- **Circuits:** 0 entries were locked at the upper circuit. 1 stop day was locked at the lower circuit. 5 entries were in trade-for-trade (BE) series.
- **Gap risk:** 3 trades gapped through the stop (average -1.311R). Entries that gapped up 2–5 % did better (+0.277R).
- **Overlap with the live monthly momentum rule** (B0, 10 stocks, 2006–26):
  - Only 9.3 % of CM trades were in the momentum portfolio at the time. Those made +0.390R; the other 738 made +0.117R.
  - When the momentum rule's market filter had it in cash, CM lost money (-0.103R over 96 trades), against +0.176R otherwise.
  - Monthly correlation with the momentum portfolio's returns: 0.324.
  - So CM mostly holds different stocks, but depends on the same market condition.

Tests: `tests/test_shadow.py`, 22 checks (signal detection, duplicate prevention, immutability guard, price tracking, gaps, rolls, costs, F&O ban, overlap, circuit lock, fills, participation).
