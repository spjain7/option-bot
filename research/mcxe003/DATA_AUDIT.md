# MCXE-003 data audit (7-Nov-2026)

- Script: `research/mcxe003/data_quality.py`. Raw numbers: `research/mcxe003/results/data_audit.json`.
- Every number below comes from that run, or from the earlier NSE-cash check (`research/program/results/eq_data_check.json`).

## MCX (Angel front-month stitch, `research/data/angel/MCX`, loader `liqtl_mcx5.load`)
| Commodity | 5-min span | Missing 5-min bars | Zero-volume bars | 3-min | 1-hour | Daily | Open gap on roll days vs normal (daily ATR) |
|---|---|---|---|---|---|---|---|
| GOLD | 2023-06 → 2026-11-03 | 7.0 % | 0.07 % | 2023-09 → | 2022-07 → | 2005 → | 0.80 vs 0.20 |
| SILVER | 2023-07 → | 5.0 % | 0.05 % | 2023-10 → | 2022-07 → | 2005 → | 1.24 vs 0.18 |
| CRUDEOIL | 2023-09 → (15m from 2020-10) | 0.13 % | 0.02 % | 2023-12 → | 2022-07 → | 2005 → | 0.26 vs 0.16 |
| NATURALGAS | 2023-09 → | 0.02 % | 0.02 % | 2024-01 → | 2022-07 → | 2016 → | 0.93 vs 0.15 |
| COPPER | 2023-04 → | 9.2 % | 0.8 % | 2023-06 → | 2022-07 → | 2005 → | 0.64 vs 0.18 |
| ZINC | 2023-02 → | 12.4 % | 1.2 % | 2023-02 → | 2022-07 → | 2006 → | 0.77 vs 0.18 |
| ALUMINIUM | 2022-11 → | 17.2 % | 2.7 % | 2023-01 → | 2022-07 → | 2005 → | 0.98 vs 0.19 |
| LEAD, NICKEL | **none** in Angel | — | — | — | — | MCX bhavcopy daily only (2022-07 →); NICKEL OI is zero on 82 % of rows (illiquid) | — |

What passed:
- No duplicate timestamps, no out-of-order bars, no zero or negative prices.
- No high below max(open, close) on 5- or 3-minute bars. A handful of 1-hour/daily rows have low > min(open, close) by one tick.
- Every session starts at 09:00 IST, so the timezone is correct.
- Sessions end at 23:25/23:30 (US summer) or 23:50/23:55 (US winter). Daylight-saving shifts the close, so session-end logic must
  use the day's own last bar, not a fixed clock time.
- A few days end at 16:55/17:00 (half sessions or exchange outages).

Findings and how this programme handles them:
1. **Thin contracts have missing bars.** Missing 5-min bars mean no trades in that interval: Aluminium 17 %, Zinc 12 %, Copper 9 %,
   Gold 7 %. Their volume is unreliable as a filter, so volume confirmation is tested only on CRUDEOIL, NATURALGAS, SILVER and
   GOLD. Signals for thin contracts are taken only on bars that traded.
2. **Roll gaps are large.** The stitched series is not back-adjusted. Open gaps on contract-switch days are 4–7× normal (Gold
   0.80, Silver 1.24, Natural Gas 0.93 daily ATR). Rules:
   - switch days are excluded from signals;
   - no position is held across a switch;
   - multi-day indicators (swings, S/R, trendlines) are **reset at each switch**, so no level straddles two contracts;
   - daily / overnight research uses contract-level MCX bhavcopy prices (below), not the stitch.
3. **No 1-minute data**; 3-minute is the finest. Coverage is 2023-26 for every commodity (Crude 15m from 2020-10).
4. **No historical intraday OI.** Daily contract OI exists from the bhavcopy (2022-07 →). The OI hypotheses are therefore
   tested only on daily or overnight horizons. The live 1-minute OI stream started ~30-Oct-2026 and is far too short.
5. **Contamination.** All 2023-26 MCX intraday data has been looked at by earlier studies (see RESEARCH_AUDIT §3).

## MCX bhavcopy (contract level, `research/data/mcx_bhav/days`)
- 1,117 days, 2022-07-01 → 2026-11-05.
- Every contract has its own OHLC, OI and volume. Mini contracts (GOLDM, SILVERM, CRUDEOILM, NATGASMINI…) are separate symbols.
- OI = 0 on 30–50 % of rows for the big contracts: these are far-month contracts with no trading.
- The front month is taken as the nearest expiry with OI > 0, rolled 3 sessions before expiry.

## NSE stock futures
| Dataset | Span | Point-in-time? | Use |
|---|---|---|---|
| `nse_opt/days` (front-month FUT rows) | 2022-07 → 2026-10-28 | **No.** Filtered to today's 183 F&O names; e.g. DELTACORP, INDIACEM, ZEEL, PVR, GNFC, BALRAMCHIN are absent in 2022 | Not used for selection |
| **`nse_fut_pit/days`** (new adapter `research/adapters/nse_stkfut_pit.py`) | 2018-01 → 2026-11-06 | **Yes.** Every FUTSTK/FUTIDX row, every expiry, from the official NSE archive (verified: DELTACORP present in Jan-2023) | Stock-futures BTST / STBT / positional |
| Angel `NFO_STK` 1-hour | 2025-06 → 2026-10 (181 names, today's list) | No | Intraday futures (survivorship noted; only 16 months) |

## NSE cash
| Dataset | Span | Point-in-time? | Checks |
|---|---|---|---|
| Official cash bhavcopy (`nse_cm`, `eq_bhav.py`) | 2005-01-03 → 2026-11-05, 5,393 sessions | **Yes.** 3,029 securities that stopped trading are included | 0 duplicates, 0 non-positive prices; 35,010 corporate-action factors (2,456 split/bonus); 29 unexplained > 40 % gaps |
| Angel daily (`NSE_EQ`) | 2006 → 2026-11-06, 496 names | No (today's Nifty-500 list) | 0 dup / 0 bad OHLC |
| Angel 5-min (`NSE_EQ`) | 2024-10-14 → 2026-11-06, 218 liquid names | No | 8.3 M bars; median 0.28 % missing; 141 bar jumps > 8 % (corporate actions / circuit moves → excluded around split dates) |

Consequences:
- BTST and positional cash research uses the point-in-time bhavcopy.
- Intraday cash research has only the survivorship-biased 218-name, 2-year set. Results there are labelled with that caveat.
  The bias mostly flatters BUY-side multi-day holds and matters less for same-day trades.
- Corporate actions:
  - The bhavcopy series is adjusted by the exchange PREVCLOSE factors.
  - BTST trades whose exit day has an adjustment factor ≠ 1 are dropped (ex-dates / splits).
  - **Earnings dates are not in our data**, so earnings-day overnight risk is measured only as part of the gap distribution
    (stated limitation).

## Data that cannot be obtained here, and its impact
| Missing | Impact | What remains possible |
|---|---|---|
| MCX 1-minute bars | No 1m timeframe | 3m/5m |
| MCX intraday OI history | OI hypotheses intraday untestable | Daily OI (bhavcopy); live stream accumulating |
| LEAD / NICKEL intraday | Intraday untestable | Daily, bhavcopy (NICKEL too illiquid) |
| Point-in-time intraday stock lists | Intraday cash/futures results have survivorship bias | Labelled; overnight/positional uses point-in-time data |
| Earnings / results calendar | Cannot isolate earnings gaps | Gap-risk measured in aggregate |
