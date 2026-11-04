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

## OPTION-BUY IMPROVEMENTS – live from 29-Oct-2026 (owner: "do all improvement required")
Code: `obuy/improve.py`, `obuy/engine.py`; tests: `obuy/tests/test_improve.py` (19 checks).
These are pricing-based guards, **not backtested**: no option-price history exists to test them, so the live scorecard is the test.

| Rule | What it does |
|---|---|
| Strike | Compare ATM with 1 strike in-the-money; ITM is used when its gain on a normal move is ≥ 90% of ATM's (less time decay); otherwise ATM |
| Normal move | Skip when a normal move cannot lift the premium by the 30% stop. Intraday normal move = daily ATR × √(minutes left / 375); positional = 1 ATR; time decay included |
| OI wall | Skip when a strike before that move has ≥ 2× the bought strike's OI |
| F&O ban | Skip stocks in today's NSE ban list. If the list cannot be fetched, the check is skipped and that is reported |
| Time | Intraday: no new buys after 13:30, and the option must be ≥ 4 days from expiry |
| Exits (intraday) | Besides −30% / +60%: exit when the premium is not +10% after 60 min, or when a 15-min futures candle closes back across VWAP |
| Option ideas | When a stock hanging-man or sweep SELL triggers, a PE (or CE) idea is attached, judged on the futures stop and target with 3 days of decay. It is sent only if the gain at the target ≥ the loss at the stop and IV ≤ 1.5× realised. Exit when the futures call exits |

Not added: a company-results calendar (no reliable free feed); the IV ≤ 1.5× realised check catches inflated pre-event premiums.

## 1H BIG MOVE WATCH (owner request, live 29-Oct-2026 – watch 2-3 days)
Information alert, NOT a trade call (no entry / SL / target): a completed 1-hour futures candle closes beyond the 20-hour
high/low with volume ≥ 2× and OI supporting the move. MCX + NIFTY/BANKNIFTY (alerts engine) and the option-buy stock list
(hourly from the 15-min candles already fetched, no extra API calls). Tracked (best / worst / last) with an end-of-day
summary. Hourly breakout CALLS were rejected by research BO1H-001/002 (9,491 combos, none survive). Code: alerts/watch1h.py.

## 4-HOUR CALLS (owner approved 30-Oct-2026, live)
MCX 4h BUY (10-candle high, vol > 2×, EMA200, stop 1.5 ATR, 3R) and STOCK 4h SELL (NSE day blocks 09:15-13:15 / 13:15-15:30,
5-candle low, vol > 2×, below EMA200, stop 2 ATR, 2R). Sent only when OI over the signal candle (live 1-minute OI) supports the
side and no resistance (BUY) / support (SELL) lies within 0.5R of the entry. Tracked on the live price; in the daily report.
Code: alerts/four_hour.py · research TFNH-001 / TFLOG-002 (branch exp/strategy-program-001).
Also 30-Oct: the 1H BIG MOVE watch and MCX OI now read OI over the candle from the live 1-minute stream (OI "n/a" had blocked
CRUDEOIL / GOLD hourly breakouts on 30-Oct).

## 4-NOV-2026 – FUTURES ONLY + MCX NEWS (owner)
- **Option SELL and option BUY switched off** (config `OPTION_ENGINE_ENABLED`, `OBUY_ENABLED`, `OPTION_IDEAS_ENABLED`); open sells are still managed to exit; all history kept.
- **ICSS-001** (branch `exp/icss-backtest`): the owner's TradingView "BTC ICSS" (Conservative, default inputs) ported bar-by-bar on daily futures.
  4,455 signals: 10-day direction right 49–54% vs random 46–56%; +1R before a 2-ATR stop 42–55% vs random 42–49%. **No edge over random entries** → not used.
- **MCX news** (`alerts/news.py`, tests `alerts/tests/test_news.py`): each MCX futures call gets up to 3 headlines from the last 24h (Google News RSS),
  a keyword tone tag (not a forecast) and any scheduled US event in the next 24h with its measured 1-hour move. Separate alerts: event heads-up 45–120 min before
  events that measurably move MCX (NG storage Thu 1.7×, US jobs first Fri: SILVER 1.8×, GOLD 1.4×, COPPER 1.6×; CPI, FOMC), and high-impact headlines (max 4/day).
  EIA crude Wednesday hour is only 1.1× a normal hour → shown on calls, no separate alert. CPI/FOMC dates are a list in `alerts/news.py` (DATED).

## INTEL-001 – pre-registered 4-Nov-2026 (shadow grade on live futures calls)
- **Hypothesis:** live futures calls graded A or B by `alerts/intel.py` (regime fit, daily bias, structure, volume, OI, VWAP,
  reward:risk, room to the next level) end with a better result than calls graded C or NO TRADE.
- **Coverage (grade_v intel-1.0):** futures breakout calls (3h / daily / monthly), MCX 4-hour calls, stock-futures daily
  calls, MCX candle setups (hammer, EMA 13/48) and stock 3-hour sweeps / hanging-man (graded when the setup is recorded,
  copied to the ledger at entry). Not graded: 15-min sweeps (log-only inside the option-buy engine, which is off).
- **Data:** only calls sent live after this date (`alerts-state` ledger, fields `grade`, `regime`, `why_for`, `why_against`).
  Backtests and data already inspected are not evidence for this test. Grade rules are frozen while the test runs.
- **Costs:** ledger P&L with 0.04 % (MCX/index) / 0.06 % (stocks) round trip, stop-first when a candle touches both levels.
- **Sample:** at least 30 closed calls in A+B and 30 in C+NO TRADE; overlapping calls on the same instrument count once.
- **Measure:** realised R per closed call from the ledger (exit vs entry ÷ initial risk, after costs). Primary statistic:
  difference of MEAN R (A+B minus C+NO TRADE); median R and win rate reported beside it. Grades of one `grade_v` only.
- **Fairness checks (all must hold):** the difference has the same sign in MCX and in NSE separately, and in BUY and SELL
  separately; no single instrument contributes more than 25 % of either group; a one-sided bootstrap (10,000 resamples)
  of the mean difference has p < 0.10.
- **NO TRADE while in shadow:** nothing is blocked, so NO-TRADE calls are real sent calls with real outcomes. Once
  `INTEL_BLOCK` is on, blocked calls are tracked as hypothetical trades (same entry / SL / target rules) in a separate
  shadow list and never mixed with sent calls.
- **Pass:** average R of A+B ≥ average R of C+NO TRADE + 0.3 R, and A+B average R > 0 after costs, plus the fairness checks.
- **If pass:** `INTEL_IN_MESSAGE = True` (grade shown). A second, separate pass is needed before `INTEL_BLOCK = True`.
- **If fail:** grade stays log-only; the rules are revised as INTEL-002 and tested on new calls only.

## E_BUY_v1 – PAPER ONLY from 4-Nov-2026
Compression breakout BUY on MCX 1-hour candles (RSIFAM-001 family E, BUY side). Frozen rules and the pre-registered
prospective test VAL-EBUY-001: `docs/strategies/E_BUY_v1.md`. Recorded in `state["paper"]`, separate from the live ledger;
never sent (hard guard `paperguard.py` in every Telegram sender). Tests: `alerts/tests/test_paper.py`.

## CALL-QUALITY-001 – strategy registry, shadow demotions, conflict guard, live scorecard (4-Nov-2026, owner: fewer, better calls)
Registry `alerts/strategies.py` decides per call type: LIVE (sent) · SHADOW (logged with tracked outcome, never sent) · PAPER.
Rule: LIVE needs ≥ 70 backtest trades with positive expectancy after costs and a positive recent period; < 30 trades or
negative / decaying → SHADOW. Evidence = STRATEGY-PROGRAM-001, TFNH-001, candle-setup studies (backtests of the live rules).

| Call type | Trades | Win % | Avg R | PF | Status | Change today |
|---|---|---|---|---|---|---|
| MCX daily hammer BUY | 333 | 52 | +0.36 | – | LIVE A | – |
| MCX 4h breakout BUY | 277 | 41 | +0.39 | – | LIVE A | – |
| Index/MCX 3h breakout BUY | 345 | 48 | +0.28 | 1.51 | LIVE A | – |
| Stock 4h breakdown SELL | 913 | 56 | +0.17 | – | LIVE A | – |
| Daily breakout BUY | 72 | 51 | +0.71 | 2.63 | LIVE B | – |
| Monthly breakout BUY | 116 | 49 | +0.28 | 1.62 | LIVE B | – |
| MCX 3h EMA 13/48 BUY | 79 | 48 | +0.67 | – | LIVE B | – |
| Stock OI breakdown SELL | 220 | 57 | +0.23 | 1.76 | LIVE B | – |
| Stock bearish engulfing SELL | 120 | 59 | +0.20 | 1.65 | LIVE B | – |
| Stock hanging-man SELL | 1217 | 44 | +0.18 | – | LIVE B | – |
| Stock 3h sweep SELL | 387 | 58 | +0.15 | – | LIVE B | – |
| 3h breakout SELL | 212 | 38 | −0.08 | 0.88 | **SHADOW** | was sent since 30-Oct |
| Daily / monthly breakout SELL | 23 / 24 | – | −0.07 / +0.09 | – | **SHADOW** | were sent (n < 30) |
| Stock OI breakout BUY | 623 | 45 | +0.08 (test −0.07) | 1.17 | **SHADOW** | was the most frequent live call |
| MCX 1h compression BUY (E_BUY_v1) | 174 | 60 | +0.21 | – | PAPER | – |

Also: a new call on an instrument that already has an OPEN live futures call is not sent (opposite side = contradiction,
same side = duplicate) – logged with its outcome. LIVE WHY messages carry one "Record" line with the backtest evidence.
The end-of-day message carries a measured scorecard (live / shadow / paper separately; T1 hit, profitable %, avg R, PF,
MFE / MAE). Live ledger 28-Oct → 4-Nov (before this change): 5 closed calls – 3h SELL 2 target / 1 stop, daily SELL 1 stop,
hammer 1 stop; stock OI BUY 4 of 7 cancelled at the open gap.
