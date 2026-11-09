# MCXE-013 — Angel One data-reliability audit (7-Nov-2026)

Evidence: market-loop run log 6-Nov (5,563 lines, 3 jobs), ws-bars exports 30-Oct…7-Nov (16 files), production code at c2225f7.

## Root cause (confirmed)
REST overload caused by the WebSocket bars being rejected, not by Angel alone.
1. **Split-minute volume bug** (wsbars keep-last) → WebSocket bars had 0 volume (MCX 100 % of minutes in every morning
   export 30-Oct…6-Nov) → hourly REST check failed "volume ratio 0.0" → every engine used REST → 6-Nov morning job:
   920 requests, 443 refused, 438 skipped, 186 budget-skipped, 65 lost; ws hits 870 vs REST fallback 1,530 for the day.
   Fixed on main by 986483d (6-Nov 14:03 IST). After it: MCX check OK (ratio 1.0) all afternoon/evening.
2. **NFO volume units** (new, this audit): after fix 1, every NFO check still failed with ratio = lot size
   (NIFTY 64.99/65, BPCL 1977.72/1975, KPITTECH 789.13/775). WebSocket = shares, REST candles = lots.
   Fix: branch `fix/ws-nfo-volume-units` (e707dc1), PR open, not merged.

## Other findings
| # | Finding | Status |
|---|---|---|
| 3 | research-data.yml uses concurrency group `option-bot` (old bot), not `market-loop`; its comment claims it never overlaps the live bot — false; overlapped the live loop on 6-Nov 15:15–20:16 IST on the same API key | confirmed config bug, impact on refusals suspected |
| 4 | Any refused/blocked call returns None → series dropped for that scan (funnel "data" note only) | confirmed behaviour; mitigated by fixes 1–2 |
| 5 | 3-Nov: no daytime loop (ws exports start 15:15) | confirmed gap, cause unknown |
| 6 | [dq] daily jumps >8 % on NATURALGAS (72), CRUDEOIL (12), SILVER (8) — daily bars are built from 1h history of the current contract (BO.daily_candles(full_1h)); thin early-life contract prints suspected | suspected |
| 7 | OI: present on 100 % of WebSocket minutes (all exports); MCX historical OI not taken from getOIData (code path skips it) | confirmed |
| 8 | MCX evening: 6-Nov evening job 72 REST requests, 0 refused; ws bars to 23:55 on 30-Oct, 2…6-Nov | confirmed working |

## Next
Merge `fix/ws-nfo-volume-units` after review; on the first trading day check `[ws] verify NFO … OK` and the
`[angel-stats]` refused count; move manual research workflows outside market hours.

## Update 7-Nov (evening)
- PR #54 merged (5609246) after checks: only angel.py / wsbars.py / wsfeed.py + tests; MCX and OI paths unchanged; unknown lot -> REST;
  dry run on the real scrip master: 240/240 NFO + 7/7 MCX tokens get a lot; 39 tests pass (test_share.py fails on main too);
  `git revert e707dc1` restores main exactly. Live result: NOT yet confirmed (first trading day 9-Nov).
- 3-Nov gap: GitHub never fired the morning market-loop crons (first scheduled run created 10:45 UTC = 16:15 IST; same on 2-Nov).
  Fixed 3-Nov evening by standby.yml chain (d6d523a); 4/5/6-Nov started 08:41 IST by dispatch. Monday depends on the Sunday cron.
- MCX >8 % jumps: GENUINE. MCX bhavcopy (exchange data, 1,118 days since Jul-2022) front-month closes >8 %: NATURALGAS 49,
  CRUDEOIL 12, SILVER 7 – matches the [dq] counts; crude 1h jumps (13-Jun-25, 9-Mar-26, 8-Apr-26 −17 %) confirmed in bhavcopy.
- MCX historical OI: Angel getOIData returns AB1012 for MCX (probe 21-Oct, crude/data.py). Sources in use: daily OI from MCX
  bhavcopy (branch research-mcx-bhav, oi_lots) and 1-min OI from WebSocket bars (since 30-Oct). Nothing is substituted silently.
- research-data.yml: PR #55 merged – quiet-hours guard on the 7 manual Angel research workflows.

## 9-Nov live morning (first day with PR #54)
- Requests 1,206 · refused 447 (all getCandleData; getOIData 189/0) · blocked 203 · budget 111 · failed 66 (6-Nov: 920/443/438/186/65).
- NFO check 6/6 MISMATCH (ratio 0.0–0.59), MCX 3 MISMATCH / 3 OK (0.67–0.83); ws hits 216 vs REST 586. PR #54 NOT confirmed.
- NEW confirmed bug: collector started 08:42 sees the previous day's cumulative volume (NFO sample 27,300); Builder's max() kept
  every minute at 0 until today's total passed yesterday's (MCX 100 % zero 09h, NIFTY 0 until ~12:20). Pre-open stale prints
  created phantom minutes (NIFTY 06:55, CRUDEOIL 03:26/08:45). MCX passed the day-ratio check at 0.67 with zero morning bars.
  Fixed: PR #56 (e3843c8) – reset on stale counter, drop pre-open minutes, zero-volume bars fail the check. Live test: 10-Nov.
- Refusals at ~320 candle requests/h (all engines of the job) – far below the ~5,000/h community figure; none before 09:15.
  Suspected: another consumer of the same Angel account/key during NSE hours, or an undocumented per-account candle limit. Open.
