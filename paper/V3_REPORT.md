# Paper engine v3 – MCX daily trend (paper only) – delivery report, 21-Oct-2026

## 1. Verified problems (checked in source before changing anything – see `paper/PLAN.md`)
| # | Problem (v2 paper engine / workflow / runner) | Fix |
|---|---|---|
| 1 | Signals, fills, stops and exits used Angel's vendor-stitched front-month series; each contract switch is a price jump inside the breakout/ATR windows | `paper/contracts.py`: contract store (per contract symbol, token, expiry, daily candles), vendor-day → contract mapping, **exact** roll gaps only from recorded contracts; a bar whose 56-bar signal window holds an **unknown** switch can only be NO TRADE. Fills/stops/exits/rolls use the actual contract's candles |
| 2 | The front token returns stitched history – storing it as the front contract's own data would hide switches | front contract stores only days after what is already recorded (1 day on a new store); its earlier own history comes from when it was the "next" contract |
| 3 | Daily-loss lock was cleared by a re-run on the same day | per-trading-day open/close equity persisted; lock derived from stored values; processed days are skipped |
| 4 | Sizing used realised cash | size = 0.5% × marked-to-market equity ÷ (fill − stop) × ₹/point, main lot else mini |
| 5 | Risk / exposure / margin checked only at the signal | checked at the signal **and again at the simulated fill** (open risk, correlated group, margin cap and free equity) |
| 6 | Live run processed only the latest candle (a missed day misplaced fills) | every unprocessed trading day is replayed in order |
| 7 | No checks for duplicate candles / impossible OHLC | `validate()` drops and reports them; stale data and holes reported; any issue blocks a confirmation |
| 8 | Workflow masked failures (`|| true`, `|| echo`); new account vs failed restore not distinguished | missing branch → new account (notice); branch present but restore/state missing → stop; commit/push errors fail the run; `bash -euo pipefail` |
| 9 | Long-only was only a tuple in config | `sides()` derives it from `long_only`; the engine raises if a confirmed SELL is ever emitted; SELL setups are not evaluated at all |
| 10 | `runner.py mcxtrade`: with Engine C disabled, a manual run would **fall through into the option-selling engine** | explicit early return when `MCXT_ENABLED` is False |
| 11 | Dedup key lacked direction; alerts lacked paper id, generation time, slippage and the values used | stable key strategy │ instrument │ contract │ direction │ candle │ status │ stage; all fields added |

## 2. Files changed (since `9cabadc`)
- `paper/contracts.py` (new) – contract store, validation, roll mapping, signal series.
- `paper/mcx_daily.py` (rewritten, v3) – engine, providers (replay / Angel read-only), live runner, report.
- `paper/run_replay.py` – estimated vs strict roll replays at 0.25 / 0.5 / 1% risk.
- `paper/tests/test_paper.py` – 30 checks (below).
- `paper/PLAN.md`, `paper/V3_REPORT.md` (this file); `paper/workflows/paper-mcx-daily-schedule.yml` (prepared, **not active**).
- `.github/workflows/paper-mcx-daily.yml` – safe restore/save, manual only, Telegram off by default.
- `config.py` – **one line**: `MCXT_ENABLED = False` (hourly MCX buy/sell). Nothing else changed.
- `runner.py` – **two lines**: early return for manual `mcxtrade` mode when disabled.
- `research/paper_strategy_report.py` (new) + `research/output_v3/`; `paper/reports/` regenerated.
Option-selling, flow/big-move and RSI engines, their Telegram settings and `bot.yml` are untouched.

## 3. Test output (run in this session)
```
python -m research.audit_v2            OK
python -m research.run_v2              variants run: 924
python -m research.tests.test_research ALL 16 RESEARCH CHECKS PASSED
python -m paper.tests.test_paper       ALL 30 PAPER-ENGINE CHECKS PASSED
python tests/simulate.py               ALL SIMULATION CHECKS PASSED ✅
python tests/sim_mcx_trade.py          MCX BUY/SELL SIMULATION PASSED ✅
python -m paper.run_replay             6 replays written to paper/reports/
python -m research.paper_strategy_report  research/output_v3/paper_strategy_report.json
```
Paper checks include: long-only enforced (downtrend → no SELL of any status; emitting a confirmed SELL raises);
two runs on the same state → no repeated alert, no duplicate pending entry, one fill; missing/corrupt state stops;
daily lock persists across re-runs; duplicate/impossible/stale data cannot confirm; unknown roll → flagged window;
exact gap from recorded contracts applied only before the switch; front-token history not stored as contract data;
margin re-checked at fill; stop recalculated from the fill; chase rejected; gap through stop fills at the open; no order
API in `paper/`; workflow has no schedule and Telegram default off; hourly engine flag guards its only call site;
manual `mcxtrade` stops early; replay reproduces the research engine's long-only signals (95/97).

## 4. Sample messages
`paper/reports/SAMPLE_ALERTS.md` (WATCHLIST; CONFIRMED PAPER SIGNAL at signal and at paper fill; NO TRADE for RSI rule,
chase / open below breakout, data, 1 lot too big). Replay samples show the replay series name instead of a contract
because history has no per-day contract; live alerts carry the real symbol and expiry (tested with recorded data).

## 5. GitHub Actions – actually executed
- Run `39615681479` (manual, telegram 0): **success** – "No paper-state branch yet – creating a NEW paper account";
  processed 2026-10-20 (latest closed candle at 19:48 IST); 0 alerts; state saved to branch `paper-state`
  (14 contract files recorded).
- Run `39615862165` (manual, telegram 0): **success** – "Restored paper state from branch paper-state"; processed 0 days
  (already done); "State unchanged – nothing to save".
Telegram delivery was **not** tested (left off as required).

## 6. Strategy validation (exact paper configuration; all periods were inspected before – not untouched)
`research/output_v3/paper_strategy_report.json` – long-only, RSI rule, 0.5 ATR chase, estimated roll adjustment,
data holes excluded:
| OOS 08-Aug-2021 → 21-Oct-2026 | Value |
|---|---|
| Trades / win rate | 39 / 48.7% |
| Expectancy after costs (before) | +3.48R (+3.60R); PF 7.9; bootstrap 5th pct +1.28R |
| Cost stress 2× / 3× | +3.37R / +3.26R |
| Max drawdown | −6.3R; longest losing streak 4; avg MAE −0.78R, MFE +8.5R; 70 days avg hold |
| Concentration | top 5 trades = 87% of R; **without them +0.52R/trade** |
| Parameter stability / walk-forward | 27/27 neighbours positive; WF +4.6R |
| Account, 0.5% risk, MTM + margin + group + daily-loss limits | +18.1% (CAGR 3.3%), max DD −4.6%, worst month −2.0%; **17 of 39 signals skipped: 1 mini lot risked more than 0.5%** |
| **Grade (unchanged criteria)** | **FAIL** – fewer than 50 OOS trades; only 50% of OOS years positive |

Replay through the engine code (`paper/reports/replay_summary.csv`):
| Roll handling | Risk | Signals | Fills | Closed | Net ₹ | Return | Max DD |
|---|---|---|---|---|---|---|---|
| estimated (replay only) | 0.5% | 27 | 20 | 19 | +10.8 L | +46.7% | −9.0% |
| **strict (= live behaviour)** | 0.5% | **1** | 1 | 1 | +0.14 L | +0.6% | −0.3% |

Why the 0.5% results differ (+18% vs +47%): the Gold 2025-26 trade (+48R, ≈ ₹6 L, more than half the profit) needs
1 GOLDM lot risking ₹12,980 against a 0.5% budget of ≈ ₹12,500–13,100. The replay's equity was a few hundred rupees
higher on its entry day, so it took the trade; the research portfolio skipped it. **The rupee result depends on a
knife-edge sizing decision on one trade** – treat any single rupee figure as fragile.

## 7. Setup – paper alerts
1. GitHub → Actions → "Paper MCX daily trend (manual, research only)" → Run workflow → telegram `0` (default).
2. Read the run log: it prints every alert. State and history are on branch `paper-state`.
3. After approval only: run with telegram `1`, and/or copy `paper/workflows/paper-mcx-daily-schedule.yml` into
   `.github/workflows/` for 00:15 IST Mon-Fri nights.
4. Reset the paper account only deliberately: delete the `paper-state` branch.

## 8. Unresolved risks and missing data
- **Few signals at first**: monthly contracts have unknown roll gaps until the store has recorded both contracts around
  each roll; expect almost no confirmed signals for ~2-3 months (strict replay: 1 signal in 5 years).
- MCX historical contract data, OI history and expired contracts are not available from Angel; history uses estimates
  (replay only). Crude roll detection finds ~7 of ~12 rolls per year.
- Margin percentages are planning assumptions (verify with the broker); contract lot sizes are today's.
- Angel vendor series has a data hole Dec-2021 → Apr-2022; the engine refuses signals with a hole in the window.
- The strategy has not met the pass criteria; results are concentrated in a few trends (2026 especially).
- Paper fills assume the open is tradable with fixed slippage; MCX tender/delivery-period illiquidity is not modelled
  beyond rolling 5 trading days before expiry and the 20-lot minimum volume check.
- Telegram delivery and the scheduled run are untested by design.
