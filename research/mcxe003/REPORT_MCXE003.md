# MCXE-003 — pattern-edge discovery across MCX, NSE cash and NSE stock futures (7-Nov-2026)

Research only. No production, Telegram, broker or risk setting was touched. Backtests are not promises of future profit.

Related documents: [RESEARCH_AUDIT.md](RESEARCH_AUDIT.md) · [DATA_AUDIT.md](DATA_AUDIT.md) ·
[PREREGISTRATION.md](PREREGISTRATION.md) (written before any result; addenda A–D record every later methodology change).

> **Validated 7-Nov-2026 – see [INDEPENDENT_VALIDATION.md](INDEPENDENT_VALIDATION.md).**
> - Stage 2 was recomputed with the promised day-block bootstrap, a fixed control set and raw-price MCX costs; all
>   verdicts are unchanged.
> - Several general statements below were overstated; they are corrected in place and marked **[corrected]**.
> - All quoted numbers reproduce from the committed files (29/29).
> - The question "does a pattern improve an existing strategy?" was never tested. It is **untested**, not failed.

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
- **[corrected]** 18.35 M detector rows were tested. Removing the copies of the same bar/pattern found by several swing
  methods leaves **15.36 M unique pattern events** = **5.22 M unique signal bars**. None of these are trades; trades
  exist only in stage 2.
- **Intraday (3 markets):** 0 of 37,073 testable cells passed stage 1. No family survives the selection-aware
  max-statistic.
- **Daily (overnight / positional):** 2 single-instrument cells passed stage 1. Both failed the pre-registered stage 2.
- **[corrected]** On MCX intraday the share of "good-looking" cells is close to chance: 17 % with t ≥ 1 vs 15.9 %.
  Cells are correlated, so this is descriptive, not a test.
- On NSE futures (end-of-day horizon 32.5 %) and NSE cash (BTST trendline breaks, max-stat p 0.005) there is **small
  real information that is below costs**.

## 3. Coverage matrix (every market × horizon cell was visited; coverage is **partial** – [corrected], see validation §C–D)
Not tested in MCXE-003:
- gap-up / gap-down / gap-fill; triple tops; cup and handle;
- RSI / MACD filters; OI, breadth and sector context;
- MCX timeframes below 15 minutes; NSE futures intraday below 1 hour;
- 10 / 20-day positional horizons (descriptive only).
Intraday NSE universes are today's lists (survivorship).
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
| Is there any information? | Share of cells with t ≥ 1 is 15.6–18.1 % vs 15.9 % by chance; t ≤ −2 is 2.0–2.3 % vs 2.3 %. Excess over random time-matched entries: median \|0.03–0.06\| ATR at 6 bars | **[corrected]** MCX intraday: none detectable. NSE futures 1h and NSE cash: small real information in several families (+0.02 to +0.10 ATR), below costs. |
| Are costs destroying a real edge? | Round-trip cost (ATR of the signal timeframe): MCX 0.30 (15m) / 0.20 (30m) / 0.14 (60m); NSE cash 0.31 / 0.16; NSE futures 1h 0.21. Typical gross move after a pattern: 0.04–0.06 ATR | **[corrected]** At 6 bars the **median** family's cost is 4–8× its gross move (MCX 4.2×, NSE futures 7.5×, NSE cash 6.4×). 6 % of MCX families clear cost before selection, very few clear 2×. At end of day MCX's median is 2.3×. On daily horizons cost is small and lack of information is the binding problem. The NSE futures 1h strongest families beat matched controls out of sample (48 correlated executions on 4 families), but none is profitable after costs. |
| Are entries too late? | Information from the signal close vs from the next open (x_fd − x_fe): median −0.02 … +0.02 ATR | **No.** Nothing is lost between the signal and the executable entry. |
| Are stops / exits unsuitable? | 12-bar MFE vs MAE medians are symmetric: MCX +1.36 / −1.32 ATR, NSE cash +0.87 / −0.92, futures 1h +0.64 / −0.64, daily +1.3 / −1.3. The diagnostic run of 12 entry × stop × exit combinations on the strongest families gives out-of-sample mean ≈ 0 (MCX +0.01R) | **[corrected]** Not the cause for the tested designs. With near-zero drift after the event, exit rules cannot create expectancy in theory (optional stopping). Excursion tails are symmetric too, and the 12 tested designs confirm it. Other exit designs were not tested. |
| Wrong timeframe? | Gross excess grows only slightly with timeframe (MCX \|x\| 0.04 → 0.05 → 0.06 ATR at 15 → 30 → 60 min) while cost falls from 0.30 to 0.14 ATR. Daily bars: cost 0.015–0.12 ATR (MCX recomputed at raw prices), information still ≈ 0 | Higher timeframes reduce the cost problem but do not add information. |
| Wrong context? | Pooled over families, the excess is +0.04 to +0.07 ATR higher when the trade agrees with: the day-trend condition (MCX +0.065 vs +0.007; NSE cash +0.051 vs +0.002; futures +0.042 vs +0.005), the EMA stack, momentum and VWAP side | **Context matters more than the pattern** (supported but uncertain: consistent direction in all 3 markets; the difference was not formally tested). Trend / day-trend agreement is the only consistent signal, the same mechanism as the existing Gold/Silver day-trend shadow strategy. Whether patterns improve that strategy is **untested** (validation §E). |
| Commodity / side specific? | MCX: no commodity has any significant cell; share of cells positive in both DEV and VALID is 22–34 % per commodity (≈ chance); BUY and SELL alike | **No hidden pocket.** |
| Earlier tests contaminated? | Two methodology faults were found and fixed **during** this programme, before any stage-2 decision (Addenda B and C): averaging daily means (changes the estimand), and a quarter-level control that leaked the regime's later drift. Earlier studies picked best variants from tens of thousands without a family-level max-statistic | Earlier apparent winners were selection noise. CRSB was already shown to be (adjusted p 0.34). |

## 5. Stage-2 results (pre-registered, survivors only)
| Survivor | Frozen choice (DEV+VALID, 2× cost) | DEV / VALID net R | **OOS net R 1× (2×)** | OOS control | OOS 95 % CI | Verdict |
|---|---|---|---|---|---|---|
| MCX COPPER 20-day breakout BUY, 5-session hold | next open · 1.5 ATR stop · 12-session time exit | +0.34 (123) / +0.64 (11) | **+0.25 (+0.24), 18 trades, 18 dates** | +0.11 (v2 fixed controls) | **[corrected]** day-block + t: −0.55 … +1.09 (v1 IID: −0.37 … +1.05) | **Rejected:** CI includes 0, only 18 trades. It is a variant of the already-live MCX daily breakout BUY family, so it adds no new strategy. |
| NSE_FUT ZEEL NR7 breakdown SELL, 5-session hold | stop at trigger · pattern stop · time exit | +0.69 (52) / −0.14 (17) | **no OOS trades** (ZEEL left F&O) | — | — | **Rejected:** VALID negative, untestable OOS; 1 of 1,296 cells (false-discovery level). |

## 6. Diagnostic execution test (labelled, cannot produce a candidate)
For the 6 strongest MCX and 4 strongest NSE-futures intraday families (ranked by DEV t), all 12 executions were run at
1× and 2× costs, each against matched random entries with the same execution.
- **MCX:** the best execution per family, chosen on DEV+VALID, gives OOS −0.09 … +0.13R. Over all executions, 54 % of OOS
  results are > 0 and the mean is +0.01R. This is chance.
- **NSE futures 1h:** OOS is better than matched controls in 98 % of executions (+0.05 to +0.10R). Every one is still
  negative after costs (−0.08 … −0.17R).
- **[corrected]** These are 48 correlated executions on the same 4 families' trades, not independent results.
  The diagnostic controls were drawn with replacement.
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
