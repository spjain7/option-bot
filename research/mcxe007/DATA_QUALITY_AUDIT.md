# MCXE-007 data-quality audit

| Check | Finding | Effect / handling |
|---|---|---|
| NSE window calendar | 247 trading days 2025-11-07 → 2026-11-06 in the point-in-time F&O bhavcopy; 0 duplicate (date, symbol, expiry) rows | — |
| Stock-futures universe accuracy | 237 FUTSTK symbols traded in the window. 209 framed. **28 excluded** by the existing builder's ≥ 120-session rule (e.g. ANANDRATHI, ATHERENERG, HUDCO, IRCTC, IGL …: added to or removed from F&O mid-window) | Partial survivorship / listing bias. Not corrected, to keep the validated builder. Disclosed. |
| Short series | 15 framed symbols have fewer than 247 rows (e.g. ADANIPOWER, HYUNDAI, NAM-INDIA at 150) | Fewer signals for those symbols only |
| Expired contracts | Every expiry row is kept. Front month rolls when ≤ 2 sessions remain; ratio back-adjusted with both contracts' closes on the day before the roll | No trade spans a roll (forced exit before) |
| **Roll-rule defect (new)** | The "≤ 2 sessions remain" count uses trading days present in the dataset, so in the **last 3 sessions of the data (4–6 Nov 2026)** the series rolls early to the next expiry (GLENMARK and TITAN show December on 4-Nov) | Affects only the last 3 OOS sessions. `doi` is NaN on the false roll day. Disclosed, not fixed (the builder is shared with MCXE-005). |
| Split / bonus | 8 symbols have unexplained > 20 % gaps treated as new segments (ANGELONE, CAMS, HDFCAMC, KOTAKBANK, LICI, MCX, TRENT, VEDL) | Segments break holding periods. Research used futures only, so no cash-derived prices were used. |
| Missing values | raw front-contract close: 0 % missing. OI change: 5.7 % NaN (first day and roll days) | Rows with NaN OI fail OI filters (conservative) |
| Index futures | NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50: all 247 sessions, 12–13 rolls each | Sample too small for daily breakouts |
| MCX daily | 7 commodities, 257–258 sessions (from 5-minute stitched data). Contract switches: GOLD 6, SILVER 5, others 12 | Positions are force-exited before a switch |
| MCX contract specifications | `research/instruments.py` lot / multiplier / tick values are **current** (21-Oct-2026 scrip master). Historical spec changes are not tracked. | Rupee figures assume today's specs |
| MCX intraday sessions (shadow) | 174 short 1-hour sessions logged (holidays with evening-only trading, e.g. 2025-11-05 with 7 bars). No duplicate 5-minute timestamps in the window. Data ends 2026-11-03 23:00 | Logged in `shadow/data_issues.csv` |
| **Exchange vs broker OI** | The research Angel store has **no OI column**, so only the three recorded production values can be compared: PETRONET 2-Nov: Angel +2.42 % vs bhavcopy +1.88 %. GLENMARK / TITAN 4-Nov: bhavcopy NaN because of the roll-rule defect above (production: +3.53 % / +5.49 %) | The OI-filtered research results use exchange OI only |
| Lot sizes (NSE) | Current Angel scrip master; 4 framed symbols have no current lot (delisted from F&O) | Rupee results are approximate; R results are unaffected |
| Timestamps | Daily bars are dated by session; 1-hour MCX bars by bar start (IST) | Signals act at the next bar's open |
| Duplicate signals | One position per instrument per strategy; one signal per breakout event (retest / failed logic de-duplicated) | — |
