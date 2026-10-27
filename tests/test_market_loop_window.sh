#!/usr/bin/env bash
# Offline test of the start/stop window in scripts/market_loop.sh. Run: bash tests/test_market_loop_window.sh
cd "$(dirname "$0")/.."
fail=0
t() {  # "<IST date time>" END expect-substring
  local when="$1" end="$2" want="$3" ep out
  ep=$(TZ=Asia/Kolkata date -d "$when" +%s)
  out=$(MARKET_LOOP_NOW=$ep MARKET_LOOP_DRY=1 bash scripts/market_loop.sh "$end" 2>&1 | tail -1)
  if [[ "$out" == *"$want"* ]]; then echo "✅ $when  job-end $end -> $out"; else echo "❌ $when  job-end $end -> $out   (wanted: $want)"; fail=1; fi
}
# Tue 2026-10-27 = weekday
t "2026-10-27 08:55" 14:50 "would run until 27-Oct 14:50"
t "2026-10-27 11:39" 14:50 "would run until 27-Oct 14:50"
t "2026-10-27 08:30" 14:50 "outside the market day"
t "2026-10-27 08:45" 14:50 "would run until 27-Oct 14:50"
t "2026-10-27 04:00" 14:50 "outside the market day"
t "2026-10-27 06:09" 00:20 "outside the market day"
t "2026-10-27 14:55" 14:50 "would run until 27-Oct 14:50"     # already past END: loop exits at once after this check
t "2026-10-27 15:07" 19:50 "would run until 27-Oct 19:50"
t "2026-10-27 19:55" 00:20 "would run until 28-Oct 00:20"
t "2026-10-27 22:10" 00:20 "would run until 28-Oct 00:20"
t "2026-10-28 00:10" 00:20 "would run until 28-Oct 00:20"      # Tue night session still open until 00:20
t "2026-10-28 00:10" 14:50 "after midnight"                   # the 'morning' job must NOT loop all day when started after midnight
t "2026-10-28 00:25" 00:20 "outside the market day"
# weekend: Sat 2026-10-31, Sun 2026-11-01; Fri night session runs into Sat 00:00-00:20
t "2026-10-30 22:00" 00:20 "would run until 31-Oct 00:20"
t "2026-10-31 00:10" 00:20 "would run until 31-Oct 00:20"
t "2026-10-31 10:00" 14:50 "weekend"
t "2026-11-01 10:00" 14:50 "weekend"
t "2026-11-02 00:10" 00:20 "weekend"                          # Sunday night: no session
t "2026-11-02 09:00" 14:50 "would run until 02-Nov 14:50"      # Monday morning
[ "$fail" = 0 ] && echo "all market-loop window checks passed" || { echo "FAILED"; exit 1; }
