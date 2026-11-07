# MCXE-003 independent validation (7-Nov-2026)

Scope: check MCXE-003 itself (code, numbers, claims), correct what is wrong, and mark what was never tested.
- No new strategy search was run.
- Research only: no production, broker, Telegram or alert change.
- New and changed files:
  - `bootstrap.py`, `stage2_daily_v2.py`, `validate.py`, and a new test in `tests/test_mcxe003.py` (7 tests pass);
  - Addendum D in `PREREGISTRATION.md`;
  - corrected outputs `results/stage2_daily_v2*.{json,csv}`, `results/validation_*.csv|json`,
    `results/data_audit_nse_fut_pit.json`, and the regenerated `results/summary.json`.

**Bottom line:**
- The two corrections in stage 2 (bootstrap, controls/costs) do **not** change any verdict. Both daily survivors stay rejected.
- Every number in the report reproduces from the committed files.
- Several of the report's general statements were **overstated**. The biggest:
  - "pattern information is essentially absent" is wrong for NSE futures and NSE cash;
  - "costs are 3–6× larger than any gross move" is true only as a median;
  - "no stop/target design can create expectancy" is a theoretical implication, not a tested fact;
  - "all market × horizon cells were tested" is wrong: several families and timeframes were not tested.
- The research also never asked whether a pattern **improves an existing trend strategy**. That question is
  **untested**, not failed.

---

## A. Bootstrap correction (Addendum D)

`stage2_daily.py` (v1, line 87) resampled individual trade returns IID, although the pre-registration promised a
day-block bootstrap. `bootstrap.block_ci` replaces it:
- trades are summed per trading date (cluster);
- dates are resampled in chronological circular moving blocks (L = round(n_dates^(1/3)), sensitivity L = 1, 2, 3, 5);
- the statistic is Σ R / Σ n;
- n, n_dates, n_eff (Geyer initial positive sequence) and a cluster-robust t-interval are reported;
- **the decision uses the widest interval** (`ci95_conservative`), because a percentile bootstrap is too narrow with
  fewer than 30 dates.

Tested:
- an IID series gives the textbook width;
- 10 identical trades per date give an interval more than 2.5× wider than an IID trade bootstrap;
- AR(1) data gives n_eff < n;
- empty and one-date samples are handled.

Corrected stage 2 (v2: also fixed controls and MCX costs, see B). Frozen execution unchanged from v1.

| Survivor | Period | n trades | dates | n_eff | mean net R 1× | block CI (L) | t CI | **conservative CI** | v1 IID CI | Control mean | Event − control |
|---|---|---|---|---|---|---|---|---|---|---|---|
| MCX COPPER 20-day breakout BUY | DEV | 123 | 123 | 123 | +0.335 | +0.08 … +0.61 (5) | +0.04 … +0.63 | +0.04 … +0.64 | +0.05 … +0.64 | +0.14 (219) | +0.19 |
| | VALID | 11 | 11 | 11 | +0.635 | −0.06 … +1.46 (2) | −0.44 … +1.71 | −0.44 … +1.71 | −0.21 … +1.53 | −0.39 (22) | +1.03 |
| | **OOS** | **18** | **18** | **18** | **+0.252** (2×: +0.235) | −0.44 … +1.06 (3) | −0.55 … +1.06 | **−0.55 … +1.09** | −0.37 … +1.05 | +0.11 (24) | +0.14 |
| NSE_FUT ZEEL NR7 breakdown SELL | DEV | 52 | 52 | 52 | +0.687 | +0.28 … +1.11 | +0.22 … +1.16 | +0.22 … +1.16 | +0.26 … +1.15 | +0.30 (53) | +0.39 |
| | VALID | 17 | 17 | 17 | −0.140 | −0.54 … +0.22 | −0.64 … +0.36 | −0.64 … +0.36 | −0.56 … +0.32 | +0.28 (19) | −0.42 |
| | **OOS** | **0** | — | — | — | — | — | — | — | — | — |

- **Conclusion unchanged.** COPPER's OOS interval is **wider** than reported (−0.55 vs −0.37 at the lower end) and still
  includes zero, so it is rejected.
- ZEEL has no OOS trades: its futures left F&O in mid-2024, which was verified in the point-in-time files. It is rejected,
  and VALID was negative anyway.
- With one instrument and one position at a time, every date holds exactly one trade, so n_dates = n.
  The date-level autocorrelation is not positive, so n_eff = n.

## B. Stage-2 execution audit: every defect found
| # | Item | Finding | Severity | Status |
|---|---|---|---|---|
| B1 | Bootstrap | IID trade resampling instead of the promised day-block bootstrap | Method error | **Fixed (v2)**; verdicts unchanged |
| B2 | Control sampling | v1 re-drew controls inside every execution × cost loop, with replacement. 1× and 2× controls were different samples: OOS control +0.126 at 1× vs −0.091 at 2×, a swing far larger than the cost difference | Method error | **Fixed:** one fixed set without replacement, reused (v2 reuse count = 0) |
| B3 | Control excludes signal days | v1 could draw the survivor's own signal days as controls | Minor | **Fixed** |
| B4 | Control count | Controls equal the number of *signals* per period, not the number of *trades*. One-at-a-time skipping removes more events (COPPER 259 of 411 signals not traded: overlaps and roll windows) than controls (random days rarely overlap). OOS: 18 trades vs 24 control trades | Comparability | Documented; means are compared, so not biased, but the sample sizes differ |
| B5 | Control entry type | Controls always enter at the next open. When the frozen execution is a stop-entry (ZEEL), entry types differ | Comparability | Documented; ZEEL rejected anyway |
| B6 | Control matching | Matched on instrument, side, research period, holding rule (same 12-session / roll-capped exit), and stop distance (event median in ATR). **Not** matched on volatility regime or trend state | Comparability | Documented. The control answers "a random day of that period", not "a similar day" |
| B7 | MCX cost scale | Costs were computed at the back-adjusted price. The adjustment ratio is up to 1.78 for COPPER (6.0 Crude, 8.2 Natural Gas in the 2000s), so fixed tick slippage was mis-scaled | Cost error | **Fixed in v2** for stage 2: COPPER median cost 0.29 → 0.38 points, net R −0.006. Stage-1 MCX daily `cost_atr` is still understated (median Crude 0.021 → 0.040 ATR, Natural Gas 0.014 → 0.039; up to 4–5× on single days). This can only make cells fail more, and no MCX daily label depends on it; only the COPPER cell passed, with raw 0.55 vs cost 0.03 |
| B8 | MCX daily back-adjustment | Ratio taken from switch-day open / previous close. This removes that day's real overnight gap together with the roll basis (about 1 day per month). Positions never cross a switch, so per-trade returns are exact; pattern levels spanning a roll are slightly shifted | Minor | Documented (DATA_AUDIT already says so) |
| B9 | Rolls / gaps | Verified in code: no entry on a switch day (an entry that would fall on one is not taken), forced exit at the close before the roll, gap through the stop fills at the open, stop checked before the target, no target on the entry bar | OK | — |
| B10 | Event → trade mapping | Events filtered to name / side / swing method, de-duplicated by bar, eligible days only (COPPER 430 raw → 411; ZEEL 125 → 108 after de-duplication); one position at a time | OK; skip counts now reported | — |
| B11 | Holding period | The stage-1 horizon was 5 sessions; the stage-2 frozen exit is a 12-session time stop (allowed by the pre-registered menu) | Note | Documented |
| B12 | Cost model by horizon | Overnight / positional futures: fees + slippage only; no financing cost (carry is inside the futures price). Cash: delivery cost (STT both sides, DP charge) | OK | — |
| B13 | Diagnostic stage 2 (`stage2_diag.py`) | Controls drawn per event *with replacement* from the same minute × period pool; reuse not counted. The "98 % of executions beat controls" (NSE futures) counts 48 correlated executions on the same 4 families' trades, so it is not 48 independent results | Overstatement | Wording corrected in the report |
| B14 | Stage-1 control | The period × minute control mean includes the event bars themselves (they are a small share of all bars) | Minor | Documented |
| B15 | Stage-1 family pooling | Pooled family rows include the same bar / side / pattern once per swing method: **49.5 % of MCX swing-family rows and 24 % of NSE futures rows are duplicates**. Family means are weighted by detection multiplicity. Day-clustered standard errors keep inference valid, but the event counts were inflated | Reporting error | Report corrected (C, D) |
| B16 | Max-statistic | The permutation statistic is the self-normalised day-sum ratio Σs/√Σs². The table shows the centred cluster-robust t. The adjusted p belongs to a closely related but not identical statistic | Minor | Documented |
| B17 | Data | Point-in-time futures dataset (new): 2,828 traded rows with close outside high–low (NSE reports the F&O close as a last-half-hour weighted average) and 927 rows with zero open/high/low, almost all far-month contracts. **0 among the nearest-expiry rows**; 12 among next-month rows used in roll windows (one zero-OHLC row: JUSTDIAL 24-Mar-2020) | Minor data defect | Documented; negligible effect |

## C. The report's strongest claims, graded
| Claim (REPORT_MCXE003.md) | Evidence checked | Grade | Corrected statement |
|---|---|---|---|
| "No stop or target design can create expectancy" | Excursions are symmetric in median **and** tails (MCX 12-bar MFE p90 +4.13 vs MAE p10 −4.04 ATR; NSE cash +2.63 / −2.58; futures 1h +1.89 / −1.80). Only 12 executions were tested, on the strongest families only | **Overstated** (theory, not a tested fact) | If the expected move after the event is zero, no exit rule can create expectancy (optional stopping). The data show near-zero, symmetric moves, and the 12 tested exit designs confirm this for the strongest families. Other exit designs were not tested empirically. |
| "Pattern information is essentially absent" | MCX intraday: share of t ≥ 1 is 17.1 % (6 bars) / 18.6 % (end of day) vs 15.9 % by chance; no family survives max-stat; none has t ≥ 2 in both DEV and VALID at end of day. **NSE futures 1h:** 18.1 % at 6 bars and **32.5 % at end of day**, the strongest families beat matched controls. **NSE cash BTST:** trendline-break BUY family max-stat p = 0.005. NSE cash intraday end of day: one family (FIRST-HOUR BUY 60m) has t ≥ 2 in both DEV and VALID | **Incorrect as a general statement**; supported for MCX intraday | MCX intraday: no detectable information beyond time-of-day controls. NSE futures and NSE cash: **small but real** information in several families (about +0.02 to +0.10 ATR), below costs. The cell-share comparisons are descriptive: cells are correlated, so they are not independent tests. |
| "Costs are 3–6× larger than gross moves" | Family-level cost / \|raw gross\| at 6 bars: MCX median 4.2× (p10 1.3×, p90 28×; 6.4 % of families have raw > cost); NSE futures 7.5×; NSE cash 6.4×. At end of day: MCX median 2.3×, 12 % of families raw > cost, 2.7 % raw > 2× cost. Daily bars: cost is small (MCX 0.015–0.09 ATR after B7, NSE cash 0.12, futures 0.05) | **Overstated** ("any gross move") | At the 6-bar horizon the **median** family's cost is 4–8× its gross move. A minority of families clear cost before selection, and very few clear 2× cost. On daily horizons cost is not the binding problem; lack of information is. |
| "All relevant market and horizon cells were tested" | See D | **Incorrect** | All 12 market × horizon cells were *visited*, but coverage is partial. Not tested: gap-up/gap-down/gap-fill; triple tops/bottoms; cup and handle (declared not implementable); RSI/MACD filters; OI, breadth and sector context; MCX 3/5-min and 1-min; NSE futures intraday below 1h; positional horizons 10 and 20 days (descriptive only); cash short horizons (blocked). |
| "The data audit covers all relevant data" | `data_quality.py` sampled every 20th MCX bhavcopy file. It did not audit the new point-in-time futures files (done now, B17), the Angel NFO_STK 1h files, or the MCX daily back-adjusted series against contract-level prices. It relied on an earlier check for the NSE cash bhavcopy | **Not established** | The audit covers MCX intraday, Angel equity and the old F&O files fully. The point-in-time futures files are now checked. The others are listed as gaps. |
| "Day-trend context is the only consistent signal" | Pooled context tables (MCX +0.065 vs +0.007, NSE cash +0.051 vs +0.002, NSE futures +0.042 vs +0.005) are averages across families weighted by days. There is no significance test of the difference | **Supported but uncertain** | Consistent direction in all three markets; magnitude not formally tested. |
| "16.4 / 18.3 million events" | 18.35 M detector rows = **15.36 M unique pattern events** = **5.22 M unique signal bars** (instrument, timeframe, time, side) | **Overstated as a count of independent observations** | Use unique pattern events and dates (table D). None of these are trades. |
| Report numbers (testable cells, label counts, max-stat p, MFE/MAE, pass counts) | 29 quoted numbers recomputed from the committed CSVs (`validation_reproduce.csv`) | **Reproduced: 29 / 29 match** | — |

## D. Coverage matrix (unique counts; events are not trades)
Columns:
- **Unique pattern events** = (instrument, timeframe, time, side, pattern), after removing swing-method duplicates.
- **Unique signal bars** = (instrument, timeframe, time, side).
- **Trades** exist only in stage 2.
- **Untouched OOS** means the period was not used for any MCXE-003 decision. Earlier studies had already looked at the
  same MCX intraday and NSE futures 1h data.

| Market | Universe | TF | Horizon | Source | Span | Point-in-time | Families | Detector rows | Unique pattern events | Unique signal bars | Unique dates (DEV / OOS) | Stage-2 trades | OOS | Coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MCX | 7 commodities (no LEAD / NICKEL intraday) | 15/30/60m | intraday, 6 bars | Angel 5-min front-month stitch | 2022-11 → 2026-11-03 | n/a (fixed list), contracts stitched | A–J | 3,207,886 | 1,979,435 | 565,452 | 1,021 (611 / 217) | 0 (no survivor) | yes, but the data were seen by earlier studies | **partial** (no 1/3/5-min, no OI) |
| NSE futures | 178 stocks | 60m | intraday | Angel 1-hour | 2022-07 → 2026-10 | **no** (today's list) | A–J | 3,091,604 | 2,628,635 | 789,979 | 1,052 (479 / 325) | 0 | yes, data seen earlier | **partial** (survivorship, 1h only) |
| NSE cash | 218 liquid stocks | 15/60m | intraday | Angel 5-min | 2024-10 → 2026-11 | **no** | A–J | 9,925,643 | 8,751,448 | 3,069,832 | 512 (176 / 210) | 0 | yes | **partial** (2 years, DEV only 176 days, survivorship) |
| MCX | 7 commodities | 1d | BTST / STBT (close → next close) | Angel daily stitch, roll-adjusted | 2006 → 2026-10 | n/a | A–I | 91,755 (both horizons, both sides) | 86,835 | 33,838 | 5,662 | 0 | yes | **full for the tested families** |
| MCX | 7 commodities | 1d | positional 5 sessions | same | same | n/a | A–I | (same events) | | | | 152 (COPPER, frozen exec) + 265 control trades | yes | **partial** (10/20-day descriptive) |
| NSE futures | 346 stocks incl. delisted | 1d | BTST / STBT | official F&O bhavcopy, point-in-time, roll-adjusted | 2018-01 → 2026-11-05 | **yes** | A–I | 991,003 | 937,591 | 371,942 | 2,112 | 0 | yes | **full for the tested families** |
| NSE futures | same | 1d | positional 5 sessions | same | same | yes | A–I | (same) | | | | 69 (ZEEL) + 72 controls | **no OOS for ZEEL** | **partial** |
| NSE cash | 979 liquid securities incl. delisted | 1d | BTST (BUY) | official cash bhavcopy, adjusted | 2006 → 2026-11 | **yes** | A–I | 1,035,230 | 979,102 | 385,665 | 5,143 | 0 | yes | **full for the tested families**; earnings not modelled |
| NSE cash | same | 1d | STBT | — | — | — | — | — | — | — | — | — | — | **blocked** (no overnight cash short for retail) |
| NSE cash | same | 1d | positional 5 sessions (BUY) | same | same | yes | A–I | (same) | | | | 0 | yes | **partial** (BUY only by rule; 10/20-day descriptive) |

Per side and horizon detail: `results/validation_coverage.csv`.

## E. Architecture review: is the research over-focused on stand-alone event prediction?
**Yes.** Every MCXE-003 test asks "does this pattern, on its own, predict direction better than a random time-matched
entry?" The context tables invert that question ("does context improve the pattern?") but never ask whether a pattern
improves an existing strategy.

| Question | Was it tested? | Status |
|---|---|---|
| Does the pattern improve an existing trend strategy (e.g. the Gold/Silver day-trend continuation in shadow)? | No. MCXE-003a tested patterns *inside* day-trend days against patterns outside; not the base strategy with and without the pattern | **UNTESTED** |
| Does it improve trade selection (take / skip base-strategy trades)? | No | **UNTESTED** |
| Does it improve entry timing (enter the base trade on the pattern instead of at the checkpoint)? | No. Only signal close vs next open was measured, for the pattern itself | **UNTESTED** |
| Does it reduce drawdown or adverse excursion of a base strategy? | No. MFE/MAE were measured per event only | **UNTESTED** |
| Does it improve expectancy after costs vs the same base strategy without it? | No | **UNTESTED** |
| Stand-alone directional information of the pattern | Yes | Tested: absent on MCX intraday; small and below costs on NSE |

None of the five untested questions should be described as "failed". A minimal pre-registered design for later (not
run here):
- **Base:** the 542 historical day-trend continuation trades, Gold and Silver.
- **Overlay:** the same-direction pattern events of families A–J within the previous N bars (selection), or the first
  such event after the checkpoint (timing).
- **Compare:** base vs base-with-overlay on identical days: expectancy at 1× / 2× cost, MAE, drawdown, trade count.
- **Statistics:** a day-block bootstrap of the paired difference, and a max-statistic over the families tried.

## F. Discrepancy table: original report vs validated findings
| # | Original report | Validated finding | Changes the conclusion? |
|---|---|---|---|
| 1 | Stage-2 OOS CI COPPER −0.37 … +1.05 ("day-block bootstrap") | IID trade bootstrap was used. Day-block (all L) plus t gives **−0.55 … +1.09**; n = 18 trades, 18 dates, n_eff 18 | No (still rejected) |
| 2 | COPPER OOS control +0.13 (1×) / −0.09 (2×) | Fixed control set: +0.11 / +0.10 | No |
| 3 | Copper costs | Raw-price costs are 32 % higher; net R −0.006 | No |
| 4 | "18.3 million events tested" | 15.36 M unique pattern events; 5.22 M unique signal bars; 0 trades in stage 1 | No, but wording corrected |
| 5 | "Pattern information essentially absent" | True for MCX intraday only. NSE futures 1h and NSE cash (BTST trendline breaks; first-hour BUY 60m) show small real information | **Yes, for the explanation**: on NSE the binding constraint is cost, not absence of information |
| 6 | "Costs 3–6× larger than any gross move" | Median 4.2× (MCX) – 7.5× (NSE futures) at 6 bars; 6 % of MCX families exceed cost before selection; end of day median 2.3×; daily horizons: cost small | Partly: costs are the binding constraint intraday, not on daily horizons |
| 7 | "No stop/target design can create expectancy" | A theoretical implication of zero drift; 12 designs tested | No, but wording corrected |
| 8 | "All market × horizon cells tested" | Visited, but partial: gap/gap-fill, triple tops, RSI/MACD, OI/breadth/sector, MCX < 15 m, NSE futures < 1 h and 10/20-day horizons untested | Yes for coverage claims |
| 9 | "Data audit covers all data" | Point-in-time futures now audited (B17); NFO_STK 1h and the MCX back-adjusted daily series are not audited against contract prices | No |
| 10 | MCX daily cost_atr | Understated 1.1–5× (Crude, Natural Gas early years) | No (cannot create passes) |
| 11 | Family-pool event counts | MCX swing families: 49.5 % of rows are duplicates across swing methods | No (inference day-clustered) |
| 12 | "Beat controls in 98 % of executions" | 48 correlated executions on 4 families, not independent | No |
| 13 | (absent) | Pattern-as-overlay on existing strategies is **untested** | Opens the next research question |

## Reproduce
```
python research/mcxe003/tests/test_mcxe003.py        # 7 tests incl. block bootstrap
python research/mcxe003/stage2_daily_v2.py           # corrected stage 2 -> results/stage2_daily_v2*.json|csv
python research/mcxe003/validate.py                  # coverage, reproduction, duplicate and cost checks
python research/mcxe003/report.py                    # regenerates results/summary.json (incl. v2 and validation)
```
