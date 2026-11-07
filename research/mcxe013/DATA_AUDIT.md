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
| 3 | research-data.yml uses concurrency group `option-bot` (old bot), not `market-loop`; its comment claims it never overlaps the live bot — false; overlapped 6-Nov 16:13→00:19 IST on the same API key | confirmed config bug, impact on refusals suspected |
| 4 | Any refused/blocked call returns None → series dropped for that scan (funnel "data" note only) | confirmed behaviour; mitigated by fixes 1–2 |
| 5 | 3-Nov: no daytime loop (ws exports start 15:15) | confirmed gap, cause unknown |
| 6 | [dq] daily jumps >8 % on NATURALGAS (72), CRUDEOIL (12), SILVER (8) — daily bars are built from 1h history of the current contract (BO.daily_candles(full_1h)); thin early-life contract prints suspected | suspected |
| 7 | OI: present on 100 % of WebSocket minutes (all exports); MCX historical OI not taken from getOIData (code path skips it) | confirmed |
| 8 | MCX evening: 6-Nov evening job 72 REST requests, 0 refused; ws bars to 23:55 on 30-Oct, 2…6-Nov | confirmed working |

## Next
Merge `fix/ws-nfo-volume-units` after review; on the first trading day check `[ws] verify NFO … OK` and the
`[angel-stats]` refused count; move manual research workflows outside market hours.
