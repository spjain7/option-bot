# v2 – Evidence-first redesign of the MCX daily alerts (research / paper only)

Nothing live was changed: `runner.py`, `mcx_trade.py`, `config.py`, `notify.py` and `bot.yml` are untouched, and the
existing hourly MCX engine still sends its alerts. The v1 results (`research/output/`) and `CRITERIA.md` are unchanged.

## Phase 1 – Audit of the unusually profitable v1 results (`output_v2/audit/`)
| Check | Finding |
|---|---|
| R and entry maths | R = 2 × ATR(20) at the signal close recomputed for all 514 C trades: **all correct**; every entry is the next day's open; ₹/lot = net R × R × ₹/point: **correct**. |
| Trades > 10R (C: 10, G: 6) | Big winners are **genuine moves**: MCX change matches international price × USD/INR within a few % (e.g. Gold +86.7% vs +75.1%, Crude +46.8% vs +48.9%). Silver 2025-26 is +128% on MCX vs +89% on the proxy, so part of that trade is **not** confirmed by the proxy. |
| 2026 | C made **128 of its 171 total R** on trades closing in 2026 (best month Mar-2026: +94R); the top 5 trades = **87%** of all R (G: 91%). The edge is a few large trends, not steady. |
| Data holes | Angel has **no MCX data Dec-2021 → Apr-2022** (59-136 days per commodity), plus Gold Aug-Oct 2022 and short 2020 gaps for Aluminium/Zinc. 4 C trades spanned a hole; the **Natural Gas short −5.9R** is an artefact (MCX +108% across the hole vs proxy +12%). |
| Contract rolls | Angel holds the expiring contract until expiry – including tender/delivery days with volume as low as 11 lots – then switches; each switch is a price jump. Estimated cumulative drift: Silver +123%, Natural Gas +204%, Gold +48% over the history. Estimator validated on NIFTY/BANKNIFTY against true NSE roll gaps: correlation 0.71, captures 80% of the cumulative gap. Rolls detected per year: Gold 5.8/6, Silver 5.0/5, Crude only 6.8/12. |
| Contract / expiry | The vendor series does not say which contract each day came from; actual contract & expiry cannot be reconstructed per day. Lot sizes are today's contract specs. |
| ₹ reconciliation | v1 headline +124.8% (C, OOS) used fixed ₹25 L sizing and closed-trade equity. Same trades, mark-to-market, fixed sizing: +136.4% (DD −42%). Sizing on **current** equity: **+65.7%** (DD −47%) – because losses before the 2026 rally shrank position sizes. With margin, group and daily-loss limits: +63.9% (DD −50%). **The ₹ headline was path-dependent and overstated.** |

## Corrected comparison (MCX daily, OOS from 08-Aug-2021, after costs) – `output_v2/corrected_comparison_mcx_daily.csv`
| Strategy | v1 (unadjusted) | holes fixed | holes fixed + roll-adjusted | Grade (adj) |
|---|---|---|---|---|
| B 20/10 | +0.089R | +0.086R | +0.171R | FAIL |
| C 55/20 + 200d | +0.747R | +0.884R | +1.024R | FAIL (validation/years, DD) |
| D = C + RSI rule | +1.132R | +1.393R | +1.505R | PAPER-CANDIDATE |
| E = C + volume | +0.854R | +0.983R | +1.098R | PAPER-CANDIDATE |
| G = C + regime | +1.115R | +1.206R | +1.119R | FAIL |
| H1/H2/H4 | | | +1.1 to +1.6R | FAIL (< 50 trades) |

Index futures daily (real NSE data) and every hourly result stay as in v1: **all FAIL**. The hourly MCX engine is
marked **unvalidated** here (−0.04R/trade on real data); its live alerts are untouched pending your approval.
Index strategies stay disabled for trade-ready use.

## Ranked improvements, one at a time (selected on train + validation only) – `output_v2/improvements_ranked.csv`
| Rank | Change | Sides | Val. Δ vs base | OOS trades | OOS R/trade | Boot p5 | Top-5 share | Grade |
|---|---|---|---|---|---|---|---|---|
| 1 | + lagged volume ≥ 1.5× | L/S | +0.82 | 53 | +1.16 | +0.24 | 99% | PAPER-CANDIDATE |
| 2 | combo RSI + volume + 10d exit + chase | L/S | +0.71 | **14** | +0.82 | −0.22 | – | FAIL (too few) |
| 3 | + lagged volume | long-only | +0.70 | 34 | +2.18 | +0.79 | 82% | FAIL (< 50 trades) |
| 4 | + RSI rule | long-only | +0.22 | 40 | +3.37 | +1.16 | 88% | FAIL (< 50 trades) |
| 5 | + regime | long-only | +0.17 | 51 | +2.40 | +0.86 | 84% | PAPER-CANDIDATE |
| 6 | + RSI rule | L/S | +0.16 | 78 | +1.51 | +0.33 | 101% | PAPER-CANDIDATE |
| 8 | exit: 3 ATR trailing | long-only | +0.11 | 86 | +1.00 | +0.47 | **64%** | PAPER-CANDIDATE (only proxy/seen missed) |
| 10 | + chase limit 0.5 ATR | long-only | +0.06 | 59 | +2.46 | +0.93 | 83% | PAPER-CANDIDATE |
| 13 | base C | long-only | 0 | 61 | +2.37 | +0.92 | 83% | PAPER-CANDIDATE |
| 14 | base C | L/S | 0 | 113 | +1.02 | +0.18 | 104% | FAIL |
| 15 | exit: 10-day channel | long-only | −0.10 | 79 | +1.17 | +0.59 | 57% | PAPER-CANDIDATE |
| 16 | combo of all long-only winners | long-only | −0.11 | **3** | – | – | – | FAIL |
| – | + OI confirmation | – | – | – | – | – | – | **NOT TESTED – MCX OI history unavailable (missing ≠ negative)** |

Shorts lose in every variant (OOS short R/trade −0.36 to −0.74). Combinations cut trades below the 50-trade minimum
and failed. No variant can reach PASS: the commodity period was already inspected (CRITERIA.md). 924 variants run in v2.

## Risk levels – portfolio, mark-to-market, margin, correlated groups, 3% daily-loss stop (`output_v2/risk_levels_portfolio.csv`)
| Base C, OOS 2021-26 | 0.25% / trade | 0.5% / trade | 1% / trade |
|---|---|---|---|
| Long/short: return, max DD | +1.1%, −2.7% (84 trades skipped: 1 lot too big) | +8.0%, −10.3% | +78.6%, −25.8% |
| Long-only: return, max DD | +3.4%, −2.3% | +54.2%, −8.9% | +145.8%, −23.7% |

## Paper engine (`paper/mcx_daily.py`) and replay (`paper/reports/`)
Separate engine, own state (`state/paper_mcx_daily.json`), own JSONL event log, dedup by
strategy | instrument | contract | candle | state, alerts only on state change. Three states: WATCHLIST,
CONFIRMED PAPER SIGNAL, NO TRADE (RSI rule – never reversed –, chase, stale data, data hole, 1 lot too big,
stop too wide, exposure / group / margin / daily-loss limits). Samples: `paper/reports/SAMPLE_ALERTS.md`.

Historical **replay** through the same code (unadjusted series, as live would see it), 08-Aug-2021 → 21-Oct-2026,
₹25 L, includes costs, stop slippage and chase cancels. This is a replay, not forward paper trading:
| Variant | Risk | Trades | Net ₹ | Return | Max DD | Win % | Long ₹ | Short ₹ |
|---|---|---|---|---|---|---|---|---|
| Long/short | 0.5% | 37 | +2.71 L | +12.5% | −10.5% | 32% | +4.33 L | −1.62 L |
| Long-only | 0.5% | 19 | +4.20 L | +18.2% | −7.5% | 63% | +4.20 L | 0 |
| Long-only | 1% | 25 | +18.1 L | +76.8% | −31.4% | 48% | +18.1 L | 0 |
The replay is weaker than the research portfolio because it also applies the RSI rule, the chase rule, blocks entries
for 260 days after the 2022 data hole, and trades the unadjusted series.

## Commands
```bash
python -m research.tests.test_research   # 16 research checks
python -m paper.tests.test_paper         # 9 paper-engine checks
python tests/simulate.py && python tests/sim_mcx_trade.py   # live-engine simulations (unchanged)
python -m research.audit_v2              # Phase 1 audit        -> research/output_v2/audit/
python -m research.run_v2                # Phases 3 & 6         -> research/output_v2/
python -m paper.run_replay               # paper replay         -> paper/reports/
# live paper (manual, Telegram off by default): GitHub Actions -> "Paper MCX daily trend" -> Run workflow
```
