# Research data – what we keep, where, and how fresh (26-Nov-2026)

Live alerts never depend on these sets. They exist so market-setup research is not limited by Angel (which only serves
history for LIVE contracts, about 3 months intraday / OI). Every set is archived daily on its own branch; `alerts/health.py`
(watchdog) sends a Telegram notice when a set was not refreshed after the previous session.

Bring everything into `research/data`: `bash research/fetch_data.sh` (or name sets: `bash research/fetch_data.sh nse_fut ws`).

| Set (fetch name) | Branch | Content | From | Refresh | Source |
|---|---|---|---|---|---|
| `nse_fut` | research-nse-fut | ALL NSE stock + index futures, daily OHLC, contracts, turnover, **open interest** (parquet per year) | backfill to 2015 (manual run, resumable) | nightly 20:26 IST | NSE archive (no Angel) |
| `nse_bhav` | research-nse-bhav | full NSE F&O bhavcopy zips (futures + **options**, OI) | 22-Oct-2026 | nightly 20:11 IST | NSE archive |
| `mcx_bhav` | research-mcx-bhav | MCX bhavcopy, all contracts, OHLC + **OI** | Jul-2022 | nightly 01:07 IST | MCX site |
| `ws` | ws-bars | **1-minute bars + OI** of every subscribed future (≈240 NFO stock/index futures + MCX) from the live WebSocket | 30-Oct-2026 | each loop job end (14:50 / 19:50 / 00:20) | live feed |
| `stocks` | research-stocks | stock futures 1-hour + daily OI (Angel, live contracts) | rolling | after midnight (started by the evening loop job, 26-Nov) | Angel, quiet hours |
| `m5` | research-m5 | 5-min stock futures + OI, 5-min cash (one-off) | Jul–Oct 2026 | manual | Angel, quiet hours |
| `angel` | research-data | Angel daily / hourly / 5-min history (NSE cash 2006+, MCX contracts, indices) | varies | manual | Angel, quiet hours |
| `nse_cm` | research-nse-cm | NSE cash-market bhavcopy history | 2005 | manual | NSE archive |

Rules: Angel downloads run only outside live-loop hours (`scripts/angel_quiet_hours.py`, Mon–Fri 08:30–00:30 IST blocked);
NSE / MCX archive downloads never touch Angel. Intraday OI history grows only from `ws-bars` (Angel cannot backfill it), so
that archive must never stop – the watchdog checks it every weekday.
