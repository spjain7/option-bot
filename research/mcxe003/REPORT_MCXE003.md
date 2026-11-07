# MCXE-003 — pattern-edge discovery across MCX, NSE cash and NSE stock futures (7-Nov-2026)

Research only. No production, Telegram, broker or risk setting was touched. Backtests are not promises of future profit.

Related documents: [RESEARCH_AUDIT.md](RESEARCH_AUDIT.md) · [DATA_AUDIT.md](DATA_AUDIT.md) ·
[PREREGISTRATION.md](PREREGISTRATION.md) (written before any result; addenda A–C record every later methodology change).

## 1. What was done
1. **Audit** of all earlier research (60+ studies) and of every dataset.
2. **New point-in-time NSE futures dataset.** The earlier stock-futures files contained only today's F&O names. A new
   adapter downloads the official NSE F&O bhavcopy with every stock that ever traded (2018-01 → 2026-11, 2,183 sessions).
3. **Modular causal engine** in `research/mcxe003/`. Every detector uses only bars up to the signal close.
   - Ten families: A trendlines/channels, B 20 candlestick patterns, C market structure, D liquidity sweeps,
     E support/resistance, F chart patterns, G failed breakouts (generated from every breakout type), H pull-backs,
     I volatility/regime transitions, J session/time-of-day.
   - Five swing definitions: fractal 2/3/5 and ATR zig-zag 1.5/3.
   - Six tests pass, including **no look-ahead** (prefix data reproduces exactly the full-data events), with two
     instruments, every swing method and three cut points.
4. **Event study first (stage 1).** Does a pattern predict the next move better than a random entry at the same time of
   day? This is measured before any trade rules or costs, so we can see *why* a pattern fails.
5. **Execution (stage 2).** Pre-registered to run only on stage-1 survivors. Plus a labelled diagnostic run of the
   execution menu on the strongest families, to answer "are stops/entries the problem?".
6. **Selection-aware statistics.**
   - BH-FDR over all testable cells.
   - Family-level max-statistic (5,000 day sign-flips applied jointly to all families).
   - Day-clustered errors (effective n = days).
   - Untouched OOS.

## 2. Headline result
**No new pattern strategy passed, in any market or horizon. Nothing is recommended for shadow or production.**
- 18.3 million causal pattern events were tested: 9.9 M NSE cash intraday, 3.2 M MCX intraday, 3.1 M NSE futures
  intraday, and 2.1 M on daily bars.
- **Intraday (3 markets):** 0 of 37,073 testable cells passed stage 1. No family survives the selection-aware
  max-statistic.
- **Daily (overnight / positional):** 2 single-instrument cells passed stage 1. Both failed the pre-registered stage 2.
- The number of "good-looking" cells is what chance alone would produce: 16–18 % of cells with t ≥ 1 (chance 15.9 %).
  Earlier "winners" were this noise.

## 3. Coverage matrix (every market × horizon cell)
DEV/VALID/OOS = development / validation / untouched out-of-sample periods. "Families" = the 10 families A–J
(intraday: all 10; daily: J excluded).

| Market | Intraday | BTST (overnight long) | STBT (overnight short) | Positional (5 sessions) |
|---|---|---|---|---|
| **MCX futures** (7 commodities; LEAD/NICKEL: no intraday data, illiquid) | 15/30/60 min, 2023-26 · 3.2 M events · 7,194 testable cells · **0 pass** · best family max-stat p 0.10 | daily 2005-26, roll-adjusted · 548 cells · **0 pass** · best p 0.08 | same run, SELL side · included above · **0 pass** | 490 cells · **1 pass at stage 1** (COPPER 20-day breakout BUY) → **failed stage 2** |
| **NSE stock futures** | 1 h, 2022-26 (today's list: survivorship noted) · 3.1 M events · 9,493 cells · **0 pass** · best p 0.18 | point-in-time F&O bhavcopy 2018-26 · 2,428 cells · **0 pass** · best p 0.15 | same run, SELL side · **0 pass** | 1,296 cells · **1 pass at stage 1** (ZEEL NR7 breakdown SELL) → **failed stage 2** (no OOS trades, VALID −0.14R) |
| **NSE cash** | 15/60 min, Oct-2024 → Nov-2026, 218 liquid stocks · 9.9 M events · 20,386 cells · **0 pass** · best p 0.36 | point-in-time bhavcopy 2005-26, liquid universe, BUY · 3,876 cells · **0 pass** — trendline-break BUY has **real but tiny** information (family max-stat p 0.005, +0.02 ATR) that is about 5× smaller than the 0.12 ATR delivery cost | **Blocked:** no overnight cash short for retail (intraday-only shorts; SLB not modelled) | BUY · 3,817 cells · **0 pass** · best p 0.71 |

Cells marked TOO_FEW (fewer than 40 DEV days for one instrument) are not tested individually. They count in the
family-level tests, which pool instruments.

## 4. Why the patterns fail (measured, not assumed)
| Question | Evidence | Answer |
|---|---|---|
| Is there any information? | Share of cells with t ≥ 1 is 15.6–18.1 % vs 15.9 % by chance; t ≤ −2 is 2.0–2.3 % vs 2.3 %. Excess over random time-matched entries: median \|0.03–0.06\| ATR at 6 bars | **Essentially none.** Pattern events are statistically indistinguishable from random entries at the same time of day. |
| Are costs destroying a real edge? | Round-trip cost (ATR of the signal timeframe): MCX 0.30 (15m) / 0.20 (30m) / 0.14 (60m); NSE cash 0.31 / 0.16; NSE futures 1h 0.21. Typical gross move after a pattern: 0.04–0.06 ATR | Costs are **3–6× larger** than any gross move. Where real information exists (NSE futures 1h strongest families, NSE cash BTST trendline breaks), it is smaller than costs. The futures 1h families beat random entries in 98 % of executions out of sample, but **0 %** are profitable after costs. |
| Are entries too late? | Information from the signal close vs from the next open (x_fd − x_fe): median −0.02 … +0.02 ATR | **No.** Nothing is lost between the signal and the executable entry. |
| Are stops / exits unsuitable? | 12-bar MFE vs MAE medians are symmetric: MCX +1.36 / −1.32 ATR, NSE cash +0.87 / −0.92, futures 1h +0.64 / −0.64, daily +1.3 / −1.3. The diagnostic run of 12 entry × stop × exit combinations on the strongest families gives out-of-sample mean ≈ 0 (MCX +0.01R) | **No.** With symmetric excursions, no stop/target design can create expectancy. |
| Wrong timeframe? | Gross excess grows only slightly with timeframe (MCX \|x\| 0.04 → 0.05 → 0.06 ATR at 15 → 30 → 60 min) while cost falls from 0.30 to 0.14 ATR. Daily bars: cost 0.02–0.12 ATR, information still ≈ 0 | Higher timeframes reduce the cost problem but do not add information. |
| Wrong context? | Pooled over families, the excess is +0.04 to +0.07 ATR higher when the trade agrees with: the day-trend condition (MCX +0.065 vs +0.007; NSE cash +0.051 vs +0.002; futures +0.042 vs +0.005), the EMA stack, momentum and VWAP side | **Context matters more than the pattern.** Trend / day-trend agreement is the only consistent signal, the same mechanism as the existing Gold/Silver day-trend shadow strategy. It is still below costs when attached to a pattern. |
| Commodity / side specific? | MCX: no commodity has any significant cell; share of cells positive in both DEV and VALID is 22–34 % per commodity (≈ chance); BUY and SELL alike | **No hidden pocket.** |
| Earlier tests contaminated? | Two methodology faults were found and fixed **during** this programme, before any stage-2 decision (Addenda B and C): averaging daily means (changes the estimand), and a quarter-level control that leaked the regime's later drift. Earlier studies picked best variants from tens of thousands without a family-level max-statistic | Earlier apparent winners were selection noise. CRSB was already shown to be (adjusted p 0.34). |

## 5. Stage-2 results (pre-registered, survivors only)
| Survivor | Frozen choice (DEV+VALID, 2× cost) | DEV / VALID net R | **OOS net R 1× (2×)** | OOS control | OOS 95 % CI | Verdict |
|---|---|---|---|---|---|---|
| MCX COPPER 20-day breakout BUY, 5-session hold | next open · 1.5 ATR stop · 12-session time exit | +0.34 (123) / +0.64 (11) | **+0.25 (+0.24), 18 trades** | +0.13 | −0.37 … +1.05 | **Rejected:** CI includes 0, only 18 trades. It is a variant of the already-live MCX daily breakout BUY family, so it adds no new strategy. |
| NSE_FUT ZEEL NR7 breakdown SELL, 5-session hold | stop at trigger · pattern stop · time exit | +0.69 (52) / −0.14 (17) | **no OOS trades** (ZEEL left F&O) | — | — | **Rejected:** VALID negative, untestable OOS; 1 of 1,296 cells (false-discovery level). |

## 6. Diagnostic execution test (labelled, cannot produce a candidate)
For the 6 strongest MCX and 4 strongest NSE-futures intraday families (ranked by DEV t), all 12 executions were run at
1× and 2× costs, each against matched random entries with the same execution.
- **MCX:** the best execution per family, chosen on DEV+VALID, gives OOS −0.09 … +0.13R. Over all executions, 54 % of OOS
  results are > 0 and the mean is +0.01R. This is chance.
- **NSE futures 1h:** OOS is better than matched controls in 98 % of executions (+0.05 to +0.10R). Every one is still
  negative after costs (−0.08 … −0.17R).
- Files: `results/stage2_diag_mcx.csv`, `results/stage2_diag_nse_fut.csv`.

## 7. What this means for the programme
1. Testing more pattern definitions, filters or exits on these data will not create an edge. The base information is
   absent (MCX) or smaller than costs (NSE), and selection makes noise look like discoveries.
2. The one consistent effect is trend / day-trend persistence. It is already being forward-tested as the Gold/Silver
   day-trend continuation in shadow mode. That is the right place for attention, and its shadow record is the evidence
   that matters.
3. Positional MCX BUY breakouts (production) remain consistent with section 5. COPPER's out-of-sample result is positive
   but too small a sample to add anything.
4. **Data that could change this conclusion:**
   - MCX intraday OI (being recorded live since 30-Oct);
   - point-in-time intraday stock lists;
   - an earnings calendar for overnight equity risk.

## 8. Reproduce
```
python research/mcxe003/data_quality.py
python -m research.adapters.nse_stkfut_pit 2018-01-01 2026-11-06
python research/mcxe003/tests/test_mcxe003.py                      # 6 tests incl. no look-ahead
python research/mcxe003/run_discovery.py mcx|nse_fut|nse_eq        # intraday events (parquet, git-ignored)
python research/mcxe003/daily.py mcx|nse_fut|nse_eq                # daily events
python research/mcxe003/stage1.py mcx|nse_fut|nse_eq --recells     # + daily_mcx_btst, daily_nsefut_pos5, daily_nseeq_btst ...
python research/mcxe003/stage2_daily.py ; python research/mcxe003/stage2_diag.py mcx 6
python research/mcxe003/report.py                                  # results/summary.json
```
Committed outputs: `results/stage1_cells_*.csv.gz` (every cell with label), `stage1_families_*.csv` (incl. max-stat p),
`stage1_context_*.csv`, `stage2_*.csv/json`, `summary.json`, `data_audit.json`.
