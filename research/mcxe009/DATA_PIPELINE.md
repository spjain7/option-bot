> **Correction (MCXE-010, 7-Nov):** the live loop DOES save candles. `scripts/market_loop.sh` exports 1-minute WebSocket bars (MCX + NFO, price / volume / OI) to branch `ws-bars` after every job (MCX 30-Oct → 06-Nov). The rows below that say "not persisted" are wrong. See research/mcxe010/AUDIT.md.

# MCXE-009 fresh-data pipeline (evidence as of 2026-11-07 16:30 IST)

## 1. Existing data sources and storage (verified in the repository)

| Data | Producer | Schedule | Storage | Broker API? |
|---|---|---|---|---|
| NSE F&O daily bhavcopy (all FUTSTK / FUTIDX / options, OHLC, volume, OI) | `.github/workflows/nse-bhav.yml` → `research/adapters/nse_daily` | **automatic**, Mon–Fri 20:11 IST (runs on 4, 5, 6 Nov all successful) | branch `research-nse-bhav`: `research/data/nse_bhav_raw/YYYYMMDD.zip` | No (NSE public archive) |
| MCX daily bhavcopy (all contracts, OHLC, volume, OI) | `.github/workflows/mcx-bhav.yml` → `research/adapters/mcx_bhav` | **automatic**, Mon–Fri 01:07 IST (runs on 5, 6, 7 Nov all successful) | branch `research-mcx-bhav`: `research/data/mcx_bhav/days/YYYYMMDD.csv` | No (MCX website) |
| Angel candles: MCX front-stitched 1D / 1h / 15m / 5m / 3m, NSE index futures 1D / 1h, NSE cash | `.github/workflows/research-data.yml` → `research/adapters/angel_hist` | **manual only** (last runs 3 Nov 18:12 UTC with MCX 5m; 6 Nov 21:32 UTC with NSE cash only) | branch `research-data`: `research/data/angel/...` + `manifest.csv` | Yes (repo secrets; same concurrency group as the live bot) |
| Live bot candles | `angel.py` / `wsbars.py` (fetched every run) | live | **not persisted.** The state branches `alerts-state`, `cash-state`, `crude-state` and `obuy-state` hold JSON state only. `paper-state` holds one daily bar from 20 Oct (stale). | — |
| Research store used by MCXE-004…008 | copies of the above | — | `research/data/nse_fut_pit/days`, `research/data/mcx_bhav/days`, `research/data/angel/` (git-ignored, local) | — |

## 2. Latest available candles (after running `sync_fresh.py`)

| Series | Latest bar anywhere in the repo | Local research store | Fresh vs research cut-off |
|---|---|---|---|
| NSE F&O daily (stock + index futures) | 2026-11-06 | 2026-11-06 | None yet. The cut-off is 6 Nov, and the next session is Mon 9 Nov. |
| MCX daily (bhavcopy, all contracts + OI) | 2026-11-06 | **2026-11-06** (6 Nov imported today) | **4, 5, 6 Nov available** (3 sessions after the 3 Nov cut-off) |
| MCX 5-minute (Angel, 7 commodities, front-stitched) | **2026-11-03 23:50** | 2026-11-03 23:50 | **None** |
| MCX 1-hour (Angel) | 2026-10-21 | 2026-10-21 | None. H1.12L builds its 1h bars from 5-minute data, so the 1h file isn't needed. |
| NSE index futures 1-hour (Angel) | 2026-10-21 | 2026-10-21 | None. FINNIFTY's stitched 1h file is listed in the manifest but missing on disk. |

## 3. Data gaps
1. **MCX intraday after 2026-11-03.** This is the only gap that blocks H1.12L. No branch, cache, state file or log in the repository contains it.
2. **NSE intraday (1h)** after 2026-10-21. Not needed for current work.
3. **NSE daily:** no gap. It simply has no sessions after 6 Nov yet; the scheduled job will collect 9 Nov onwards automatically.
4. **Angel OI history:** never stored, so exchange OI is the only OI source.

## 4. Cheapest reliable collection method
- **NSE daily futures:** already automatic and free (`nse-bhav.yml`).
  - `research/mcxe009/sync_fresh.py` converts the branch zips into the research format, with no network and no duplicates (it skips dates already present).
  - Verified: the converted 6 Nov file is identical to the existing research file (667 contracts, 0 close and 0 OI differences).
- **MCX daily:** already automatic and free (`mcx-bhav.yml`). The same sync script copies new days.
- **MCX 5-minute (for H1.12L):** the only legitimate source in this setup is the Angel candle API through the existing `research-data.yml` workflow. MCX publishes no free intraday candles.
  - As written, the workflow **re-downloads about 4.4 years** of 5-minute history per commodity (17 pages × 7 = about 119 requests). That is duplicate data.
  - **Incremental mode** (prepared on the research branch, offline-tested by `research/mcxe009/test_incremental.py`):
    - fetches only from the last stored bar and appends: **1 request per commodity (7 total)**;
    - keeps the full history, never creates duplicates, and leaves the file intact when the API returns nothing.
  - It cannot run from the research branch today. That branch is 339 commits behind `main`, and its `angel.py` lacks main's 6-Nov throttle and `wsbars` changes, so a research-branch run would use outdated broker-client code. **It should be merged to `main`** (2 files, about 15 lines, research tooling only; default behaviour unchanged) before it is used.

## 5. What is needed from you (one action; no files to export)
H1.12L is blocked only on MCX 5-minute bars after 3 Nov. Pick one:
- **A. Works today, no code change:**
  - Go to GitHub → Actions → **"Research data (manual, no alerts)"** → Run workflow on `main`.
  - Inputs:
    - `names` = `CRUDEOIL,NATURALGAS,GOLD,SILVER,COPPER,ZINC,ALUMINIUM`
    - `dataset` = `futures`
    - `intervals` = `FIVE_MINUTE`
  - About 119 read-only Angel requests. It queues behind the live bot (shared concurrency group). Best run outside market hours.
- **B. Cheapest long-term (needs your approval to touch `main`):**
  - Merge the incremental patch: `research/adapters/angel_hist.py` + the `incremental` input in `research-data.yml`, as on `exp/strategy-program-001`.
  - Optionally add a nightly schedule. Each top-up is then 7 requests.

After either one, I run `python research/mcxe009/sync_fresh.py` and `python research/mcxe007/shadow/h112l_tracker.py`. Nothing else needs exporting: the live bot does not store candles, so there are no files on your side to copy.

## 6. Can H1.12L tracking resume?
- **Not yet.** The tracker is ready and tested, and it reads exactly the files that option A or B produces.
- Forward trades remain 0 until MCX 5-minute data after 2026-11-03 23:50 exists.
- Fresh **daily** MCX (4–6 Nov) and the automatic NSE daily feed are already in place for future daily research. No strategy tests were run in MCXE-009.

**Safety:**
- No broker call was made.
- No production file, setting, alert or strategy changed; `main` is untouched at bc3153e6.
- The changes to `research/adapters/angel_hist.py` and `.github/workflows/research-data.yml` exist only on the research branch.
