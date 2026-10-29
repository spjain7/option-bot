# Alert experiments (registered before running)

## ALERT-EXP-002 – extra filters against fake reversal calls (registered 22-Oct-2026)
Baseline: the LIVE alert rule (RSI extreme + reversal candle + quality layer), next-candle-open entry, half at T1, 0.1R costs.
Each filter is tested alone on top of the baseline: F1 daily-trend alignment, F2 RSI divergence, F3 next-candle break confirmation.
A filter is switched ON only if ALL hold: ≥ +0.05R improvement pooled; better in both halves (≤2023 / ≥2024);
better in ≥ 60% of instrument×timeframe groups (≥ 10 trades); bootstrap p5 of the improvement > 0; ≥ 100 trades remain.
Data 2020-26 already seen → exploratory. Code: `alerts/exp_filters.py`; results: `alerts/results/EXP-002/`.

### Result (706 baseline alerts, 2020-26): **no filter passes – none switched on**
| | Alerts kept | Avg R | Win % | PF | Improvement | Both halves | Groups better | Boot p5 | Losers removed / winners kept |
|---|---|---|---|---|---|---|---|---|---|
| Baseline (live rule) | 706 | −0.099 | 48.3 | 0.81 | – | – | – | – | – |
| F1 daily trend | 144 (20%) | −0.046 | 52.1 | 0.90 | +0.053 | no (+0.27 / −0.07) | 2/2 | −0.063 | 81% / 22% |
| F2 RSI divergence | 18 (3%) | −0.285 | 38.9 | 0.58 | −0.186 | no | – | −0.606 | 97% / 2% |
| F3 next-candle confirm | 469 (66%) | −0.060 | 49.9 | 0.88 | +0.039 | yes (+0.03 / +0.05) | 10/13 | −0.011 | 36% / 69% |
F3 is the most consistent (better in both halves and 10 of 13 groups) but misses the +0.05R and bootstrap thresholds;
all variants remain negative after costs.

## CANDLE-SETUPS – live from 29-Oct-2026 (owner approved: "do live not in log mode")
Code: `alerts/candle_setups.py`, tests `alerts/tests/test_candle_setups.py` (15 checks). Research: branch
`exp/strategy-program-001`, `research/program/REPORT.md` (DCP-001, EMAX-003, RR1, VERIFY-EXITS).

| Setup | Rule | Backtest 2022–26, after costs | Live code replayed over 2022–26 (before costs) |
|---|---|---|---|
| MCX daily hammer breakout BUY | hammer → BUY above its high within 3 sessions; SL 0.05 ATR below its low; target 2R; 20 sessions | +0.36R, 52% wins, 333 trades; every year and all 7 commodities positive | 352 trades, 52.3% wins, +0.44R; all 7 positive |
| Stock daily hanging-man breakdown SELL | hanging man while EMA20 > EMA50 → SELL below its low within 3 sessions; SL above its high; 2R; 20 sessions | +0.18R, 44% wins, 1,217 trades (flat 2023, 2025) | 40 stocks: 254 trades, 46.5% wins, +0.31R |
| MCX 3-hour EMA 13/48 BUY | EMA13 crosses above EMA48, ADX(14) ≥ 20 and rising → BUY next open; exit after opposite cross; safety SL 3 ATR | +0.67R, 48% wins, **79 trades (small sample, GOLD-heavy)** | 88 trades, 44% wins, +0.60R |

- **Message flow:** setup (with trigger, stop and target) → TRIGGERED → EXIT (target, stop, time or contract change), or
  CANCELLED (no breakout within 3 sessions, or the stop was touched first). Calls are written to the ledger used by the daily call reports.
- **Tracking:** MCX uses 15-minute candles; stocks use daily candles after the 15:30 close.
  - A gap through the target or stop fills at the open.
  - If one candle touches both, the stop is counted.
- **Review:** compare live results with the backtest after 4 weeks (owner review scheduled).
- **Rule kept for any future hourly pattern call:** skip pattern candles starting 14:15 and 15:15 (`hourly_pattern_allowed`).

## LIQUIDITY SWEEP – live from 29-Oct-2026 (owner approved; research SWEEP-001 / SWEEP-15 on exp/strategy-program-001)
- **STK_SWEEP3H (live).** Stock futures, 3-hour candles. A sweep candle goes above equal highs and closes back below them → SELL below its low within 3 candles. Stop 0.05 ATR above its high, target 1R, time exit after 20 candles.
  - **Sent only when volume and OI support the call:**
    - sweep-candle volume ≥ 1.5× average;
    - previous session was not a long buildup;
    - OI did not rise during the sweep candle (15-minute OI; skipped if unavailable).
  - **Backtest 2022–26 (volume + previous-day OI):** 387 trades, 58.4% wins, +0.15R after costs, every year positive.
  - **Live-code replay:** 411 trades, 57.7%, +0.17R before costs.
  - **The sweep-candle OI check is new:** it has 15-minute evidence only, as no historical intraday OI exists.
  - **Scans run after 12:15 and after the 15:30 close.** The 12:15 block now fetches 1-hour candles for the stock universe.
- **Sweep15 (29-Oct update: SELL + volume + OI falling now SENT, test phase; everything else logged).** Top-40 stock futures, 15-minute candles from the option-buy loop (no extra API calls).
  - Every sweep of the 20-candle or previous-day high/low is recorded, both sides, with volume and OI-falling flags, and tracked to the close at 1:1.
  - Exploratory evidence (Aug–Oct 2026): SELL with volume + OI falling, 48 trades, 75% wins, +0.28R. BUY sweeps were negative.
  - Review after about 100 trades.
- **Tests:** `alerts/tests/test_candle_setups.py`, 23 checks.
