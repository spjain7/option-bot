# MCXE-003 programme — research audit (7-Nov-2026)

Scope: owner directives "AUTONOMOUS MCX STRATEGY DISCOVERY — MCXE-003" and "SCOPE EXPANSION — ALL NSE CASH, NSE STOCK
FUTURES & MCX FUTURES". Branch `exp/strategy-program-001`. Research only: no production, Telegram, broker or risk change.

Sources checked: `research/program/REPORT.md` (1,025 lines, 60+ studies), `research/program/*.py` (≈ 110 scripts),
`research/program/results/` (201 files), `research/program/tests/test_mcx_engine.py`, `research/tests/test_research.py`,
`research/data/**` manifests, `alerts/` (live rules).

Note on naming: `REPORT.md` already contains a section titled "MCXE-003 – price-action setups inside the established day
trend". That earlier study is called **MCXE-003a** here. This programme is "MCXE-003", and its code lives in `research/mcxe003/`.

The owner's MCX brief arrived cut off after "§12 FIND FAILURE MECHANISMS … Pos". Sections 1–11 and the start of §12 were
received. Failure classification is still implemented (see `failure_analysis.py`).

## 1. Verification of the owner's summary of earlier findings

| Owner statement | Verified against files | Correction / nuance |
|---|---|---|
| MCXI-001: thousands of breakout variants, costs consumed the edge | Yes (`mcxi_ledger.csv`, 6,940 rows) | **Partly an artefact.** The MCXI-001 cost model charged 2.4–4.5× a realistic round trip (audit in MCXD-001). Even before costs, breakouts beat random entries by only +0.05–0.1R, so the conclusion "no usable edge" still stands. |
| MCXE-001 had defects and was superseded | Yes | It had four defects: an unstable seed, an unmatched random control, overlapping positions, and optimistic same-bar fills. Its files are renamed `*_PROVISIONAL_*`. |
| MCXE-002: about 51,740 experiments, matched controls | Yes (51,740) | 60 of 840 walk-forward streams survived. Out of sample, 30 were positive and 30 negative, pooled +0.02R, median control rank 0.56. |
| Silver flag / trendline breakout failed further validation | Yes | Flag: 5 out-of-sample trades, untestable. Trendline 15m: walk-forward +0.50R, then −0.23R out of sample. |
| Crude 30m S/R breakout rejected after selection adjustment | Yes (CRSB) | Adjusted p = 0.34. Over 2021–23 the frozen rule earned +0.02R. |
| Candles / structure add little inside the day trend | Yes (MCXE-003a) | Adding the day-trend context raises every family by about 0.06–0.08R, but none turns positive. |
| Day-trend continuation (DTC) is the strongest intraday candidate | Yes (MCXD-002/004/005) | Gold carries it (t 3.4); Silver is weak (t 1.8). It is in shadow mode only (`alerts/mcx_dtc.py`, LIVE=False). |

## 2. Inventory

### 2.1 Strategy families and detectors already implemented (MCX intraday)
| Family | Detector / file | Tested | Status |
|---|---|---|---|
| Range breakout (opening range, consolidation, previous-day H/L) | `mcxi.py` | MCXI-001, 3 timeframes × 3 range types | **Rejected, strong evidence** (gross ≈ random) |
| Breakout of 20 bars / N bars | `search_all.py`, `search_v2.py`, `bo1h.py`, `mcx_lookback.py` | 15m–1d | 15m/30m rejected (costs ≥ edge); 1h–1d BUY with the daily trend robust (in production) |
| Sweep REV / BOS / CHoCH | `mcx_engine.py` (pivot ±3 only) | MCXE-002 | Rejected (walk-forward −0.01 … −0.24R; sweep+BOS +0.05R, out of sample ≈ 0) |
| S/R zones BRK / RET / REJ | `mcx_engine.py`, `sdzone.py` | MCXE-002, CRSB | Rejected (selection-adjusted) |
| Trendline BRK / RET / REJ (last 2 swings only) | `mcx_engine.py` | MCXE-002 | **Tested too simply**: one swing method, 2-touch lines only, no touch/age/slope quality |
| Channel break | `mcx_engine.py` | MCXE-002 | Walk-forward +0.12R; out of sample not confirmed |
| Market structure BOS / CHoCH | `mcx_engine.py`, `structx.py` (MSS) | MCXE-002, STRUCTX | Rejected (MSS fails repeatedly inside down-legs) |
| Candles ENGULF / PIN at levels | `mcx_engine.py` | MCXE-002/003a | Rejected |
| Flag / triangle | `mcx_engine.py` | MCXE-002 | Few trades; not validated |
| Failed breakout, VWAP mean reversion, exhaustion, US-open momentum, compression→expansion (Bollinger), trend pull-back | `mcx_disc.py` | MCXD-001 | All negative except DTC and Silver trend pull-back (tail-driven) |
| EIA release | `mcxi.py` | MCXI-002 | Rejected |
| RSI extreme reversal | `rsix.py` | RSIX-001 (241k combinations) | Rejected intraday |
| Liquidity-trendline indicator (owner's Pine script) | `liqtl*.py` | LIQTL-001…004 | Rejected |
| Day-trend continuation | `mcx_dtc.py` | MCXD-002/004/005 | **Only survivor** (shadow) |

### 2.2 Never tested, or not tested adequately (MCX intraday)
- **Swing definitions:** only a fixed ±3 pivot was ever used. No ATR zig-zag, no multi-scale (internal vs external) structure.
- **Trendlines:** no 3-touch lines, touch quality, line age, slope, ATR-normalised fit, compression before the break, or
  break after a sweep.
- **Candles:** hammer, shooting star, inverted hammer, hanging man, morning/evening star, piercing / dark cloud, inside
  bar, outside bar, doji, three-bar reversal, NR4/NR7 and multi-candle compression were **never tested on MCX intraday**.
  They were tested on daily/1h bars for stocks, index and MCX (HAM-001, DCP-001, ALLPAT-001, SEARCH-V2 INSIDE/PIN).
- **Classic chart patterns:** double top/bottom, head & shoulders, wedges and rectangles were **never tested intraday**.
  They were tested on 3h/daily (CMP, OFF after the exit-bug fix; ALLPAT is candles only).
- **Failed-breakout family** beyond previous-day/opening range (failed S/R zone, trendline, flag or BOS): not tested.
- **Volatility-regime transitions** (ATR compression, range→trend): only the Bollinger squeeze (VCE) was tested.
- **Session behaviour by commodity** (first-hour continuation, afternoon continuation, session-transition sweep): only the
  DTC checkpoints and the US-open hypothesis were tested.
- **Mechanism measurement:** every earlier study judged setups only on net trade P&L. None measured whether an event carries
  **any** forward information before costs, relative to a time-matched control. So "no information" was never separated
  from "information smaller than costs" or "information already spent by entry".

### 2.3 Other markets
| Market × horizon | Earlier work | Status |
|---|---|---|
| NSE cash, delivery swing ≤ 20 days | EQ (bhavcopy 2005-26, point-in-time, 288 combinations); EQ-001 (Angel) | Rejected (gross ≈ costs) |
| NSE cash, monthly momentum portfolio | EQ-MOM-001/2/3 | **Implemented** (cash-mom-1.2, BUY-only, production) |
| NSE cash, intraday | EQ intraday (57 sessions); EQ-001 ORB (500 days, 432 combinations) | Rejected (opening-range breakout only; BUY negative) |
| NSE cash, BTST | none | **Not tested** |
| NSE cash, STBT | none | **Blocked** (see §4) |
| NSE stock futures, positional (daily / 2h–4h) | S4/S5, SEARCH-ALL, STK-ANCHOR, WALLS | SELL in a daily downtrend robust (in production); BUY decaying |
| NSE stock futures, intraday | PREMOVE/REV5 (5m, 3 months) | Too short, rejected |
| NSE stock futures, BTST / STBT | none | **Not tested** |
| MCX, overnight (BTST/STBT) | none | **Not tested** |
| MCX, positional (1h–monthly) | SEARCH-ALL, WKMO, LONG20, ROLLCHECK | BUY robust after roll correction (in production); SELL loses |

## 3. Known defects and limits of earlier work (verified)
1. **Contaminated holdouts.** The MCX 5-minute history (2023-26) has been used for selection by MCXI, MCXD, MCXE-001/2/3a and CRSB.
   No untouched intraday MCX history remains, except Crude 15m 2020-10…2023-09 (used once, by CRSB, for one rule only).
   New families tested here have never been selected on any period. Their holdouts are honest for *these* hypotheses,
   but the market data is not fresh.
2. **Survivorship bias.** The Angel NSE_EQ universe (472 stocks) and the stock-futures list are *today's* lists. The NSE cash
   bhavcopy research (2005-26) is point-in-time; for stock futures, the F&O bhavcopy (2022-07…2026-10) is point-in-time and
   contract-level.
3. **Unadjusted daily MCX stitch.** Fixed by ROLLCHECK-001; rules re-validated.
4. **Single swing definition** (pivot ±3) throughout MCXE; no sensitivity to the swing method.
5. **Effective sample size** was not reported in MCXE-002 (overlapping days across streams). It is reported here.
6. **Selection-aware testing** was only applied once (CRSB). Here every family is judged at family level, with BH-FDR plus a
   max-statistic test.
7. **Execution assumptions (reused, verified by 14 tests):** next-bar entry, stop before target, gap fills at the open,
   no same-bar optimistic stop-entry, square-off 23:00, no entries after 22:00, roll days excluded. Costs: statutory fees +
   1.5 ticks/side (realistic), ×2 stress.

## 4. Legal / execution constraints applied
- **NSE cash STBT is not executable for retail:** a cash short sold intraday must be bought back the same day (auction penalty
  otherwise). Overnight shorts need SLB, which we do not model. → Cell marked **blocked**. Short exposure overnight is
  tested only via stock futures.
- Cash intraday shorts are allowed (intraday square-off). These are tested as research, but the owner's live rule "cash stocks
  BUY-only" stands. Any cash SELL finding stays information only.

## 5. Coverage matrix (start of MCXE-003; updated in `REPORT_MCXE003.md`)
| Market | Intraday | BTST | STBT | Positional |
|---|---|---|---|---|
| NSE cash | ORB only, rejected → **this programme** | **not tested → this programme** | **blocked** (no overnight cash short) | swing rejected; monthly momentum live |
| NSE stock futures | 3 months only → **1h, 16 months, this programme** | **not tested → this programme** | **not tested → this programme** | partly tested (SELL with trend robust) → event study here |
| MCX futures | many families rejected; DTC shadow → **new families, this programme** | **not tested → this programme** | **not tested → this programme** | BUY robust (1h–monthly) → event study here |

## 6. Design decision for this programme (why it differs from MCXE-002)
Earlier studies jumped from "detector" straight to "trade grid × filters × executions". That produced 50k+ correlated
experiments, then selection bias. This programme separates two questions:
1. **Information stage (event study).** Does the event shift the forward move, measured in ATR before costs, beyond a
   control at the same instrument, timeframe, time of day and quarter? This is measured from the detection bar and from
   the executable entry. Effective n = days. BH-FDR across *all* cells, plus a family-level max-statistic.
2. **Execution stage, only for events that pass stage 1:** trades with realistic costs (1× and 2×), the same execution
   applied to matched control entries, and walk-forward/holdout.

Each failed cell gets a mechanism label, so the result explains *why* it fails:
NO_INFO · WRONG_SIGN · TOO_SMALL_VS_COST · INFO_SPENT_BEFORE_ENTRY · UNSTABLE · TOO_FEW.
