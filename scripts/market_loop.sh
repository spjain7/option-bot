#!/usr/bin/env bash
# Runs the option-selling engine, the option-buy engine and the buy/sell alert engine every 15 minutes (2 min after each candle closes) until END (IST HH:MM).
# Used because GitHub's cron skips most scheduled runs. State is restored/saved to its branch around every scan;
# Telegram is sent only after the save. A failed iteration is reported and the loop continues.
set -uo pipefail
END="$1"                                  # e.g. 14:50
[ "${MARKET_LOOP_DRY:-0}" = "1" ] || { git config user.name "option-bot loop"; git config user.email "bot@users.noreply.github.com"; }   # not in the offline test

restore() {  # $1 branch  $2 subdir
  rm -rf "state/$2"; mkdir -p "state/$2"
  if git ls-remote --exit-code --heads origin "$1" > /dev/null 2>&1; then
    git fetch -q origin "$1" && git archive FETCH_HEAD "$2" | tar -x -C state || return 1
    test -f "state/$2/state.json" || return 1
    echo 0
  else
    echo 1
  fi
}

save() {     # $1 branch  $2 subdir  files...
  local br="$1" sub="$2"; shift 2
  for attempt in 1 2 3; do
    rm -rf /tmp/sv && git worktree prune
    if git ls-remote --exit-code --heads origin "$br" > /dev/null 2>&1; then
      git fetch -q origin "$br" && git worktree add -q /tmp/sv FETCH_HEAD
    else
      git worktree add -q --detach /tmp/sv && (cd /tmp/sv && git checkout -q --orphan "$br" && git rm -rqf --ignore-unmatch .)
    fi
    mkdir -p "/tmp/sv/$sub"
    for f in "$@"; do
      if [ -f "state/$sub/$f" ]; then cp "state/$sub/$f" "/tmp/sv/$sub/"; else rm -f "/tmp/sv/$sub/$f"; fi
    done
    (cd /tmp/sv && git add "$sub" && (git diff --cached --quiet || git commit -qm "$sub state $(date -u +%F_%H%M)") \
       && git push -q origin "HEAD:refs/heads/$br") && return 0
    sleep 5
  done
  return 1
}

options() {
  # ---- option-selling engine (runner.py auto, same as the Option Selling Bot workflow; state on main: state/*.json) ----
  # Runs in a fresh worktree of the latest main, so it always uses the newest code and state; the instrument list cache is shared.
  rm -rf /tmp/opt; git worktree prune
  if ! (git fetch -q origin main && git worktree add -q --detach /tmp/opt FETCH_HEAD); then echo "::error::option engine checkout failed"; return; fi
  mkdir -p .cache && ln -sfn "$PWD/.cache" /tmp/opt/.cache
  (cd /tmp/opt && timeout 600 python runner.py auto); local rc=$?   # a hung API call can never block the loop
  (cd /tmp/opt && git add state/*.json 2>/dev/null
   if ! git diff --cached --quiet; then
     git commit -qm "state $(date -u +%F_%H%M)"
     for a in 1 2 3; do git pull -q --rebase origin main && git push -q origin HEAD:main && break; sleep 5; done
   fi)
  echo "option engine exit $rc"
}

save_shallow() {   # $1 branch  $2 subdir  file – add one file on top of the branch tip without fetching its history
  local br="$1" sub="$2" f="$3"
  for attempt in 1 2 3; do
    rm -rf /tmp/svs && git worktree prune
    if git ls-remote --exit-code --heads origin "$br" > /dev/null 2>&1; then
      git fetch -q --depth 1 origin "$br" && git worktree add -q /tmp/svs FETCH_HEAD
    else
      git worktree add -q --detach /tmp/svs && (cd /tmp/svs && git checkout -q --orphan "$br" && git rm -rqf --ignore-unmatch .)
    fi
    mkdir -p "/tmp/svs/$sub/$(TZ=Asia/Kolkata date +%Y-%m)" && cp "state/$sub/$f" "/tmp/svs/$sub/$(TZ=Asia/Kolkata date +%Y-%m)/"
    (cd /tmp/svs && git add "$sub" && (git diff --cached --quiet || git commit -qm "$sub $(date -u +%F_%H%M)") \
       && git push -q origin "HEAD:refs/heads/$br") && return 0
    sleep 5
  done
  return 1
}

obuy() {
  # ---- option-BUY alerts (test phase; NSE hours only) ----
  if n=$(restore obuy-state obuy); then
    export OBUY_NEW_STATE=$n
    # run the latest code (fresh worktree made by options()), state stays in this job's state/obuy
    if [ -d /tmp/opt ]; then (cd /tmp/opt && OBUY_STATE_DIR="$OLDPWD/state/obuy" timeout 420 python -m obuy.run scan); else timeout 420 python -m obuy.run scan; fi; local rc=$?
    if [ -f state/obuy/state.json ] && save obuy-state obuy state.json; then SAVE_OK=success; else SAVE_OK=failure; fi
    SAVE_OK=$SAVE_OK OBUY_STATE_DIR="$PWD/state/obuy" python -m obuy.run flush
    echo "option-buy scan exit $rc, save $SAVE_OK"
  else
    echo "::error::option-buy state restore failed"
  fi
}

iteration() {
  # 29-Oct: futures calls run FIRST (they were last and found Angel already rate-limiting -> NIFTY / BANKNIFTY / MCX skipped).
  # The fresh worktree of the latest main is made here (it was made by options()).
  rm -rf /tmp/opt; git worktree prune
  (git fetch -q origin main && git worktree add -q --detach /tmp/opt FETCH_HEAD && mkdir -p .cache && ln -sfn "$PWD/.cache" /tmp/opt/.cache) \
    || { echo "::warning::fresh checkout failed - alerts run on this job's code"; rm -rf /tmp/opt; }
  # ---- buy/sell alerts ----
  if n=$(restore alerts-state alerts); then
    export ALERTS_NEW_STATE=$n
    # run the LATEST main code (fresh worktree made by options()), so fixes pushed during the day apply at the next scan
    if [ -d /tmp/opt ]; then (cd /tmp/opt && ALERTS_STATE_DIR="$OLDPWD/state/alerts" timeout 1200 python -m alerts.run scan); \
    else timeout 1200 python -m alerts.run scan; fi; rc=$?   # the 15:30 stock scan (181 futures) can take ~10 min
    if [ -f state/alerts/state.json ] && save alerts-state alerts state.json; then SAVE_OK=success; else SAVE_OK=failure; fi
    [ -f state/alerts/outbox.json ] && SAVE_OK=$SAVE_OK python -m alerts.run flush
    save alerts-state alerts state.json pending.json || echo "::warning::could not save the undelivered-message queue"
    echo "alerts scan exit $rc, save $SAVE_OK"
  else
    echo "::error::alerts state restore failed"
  fi
  [ -f .cache/ws/feed.log ] && { echo "[ws] collector:"; tail -n 2 .cache/ws/feed.log; }
  options
  obuy   # intraday STOCK option buys (VWAP + RSI + OI); positional option buys come with the futures calls (alerts/)
}

# ---- trading-day window (IST). The loop only runs from 08:40 until 00:20 (NSE 09:15-15:30, MCX 09:00-23:30/23:55) on Mon-Fri
# sessions. A run started outside the window (a late backup / queued run) exits at once, so it never sits idle through the night
# and never blocks the next morning's start. ${MARKET_LOOP_NOW} (epoch seconds) is only used by the offline test.
NOW_S="${MARKET_LOOP_NOW:-$(date +%s)}"
ist() { TZ=Asia/Kolkata date -d "@$NOW_S" "$@"; }
h=$(ist +%-H); mi=$(ist +%-M); m=$((h * 60 + mi))
dow=$(TZ=Asia/Kolkata date -d "@$((NOW_S - 18000))" +%u)         # trading day this minute belongs to (00:00-00:20 = still the previous day's MCX session)
if [ "$dow" -ge 6 ]; then echo "weekend – no market session (IST $(ist '+%a %H:%M')) – nothing to do"; exit 0; fi
if [ "$m" -ge 20 ] && [ "$m" -lt 520 ]; then echo "outside the market day (IST $(ist +%H:%M); loop window 08:40-00:20) – nothing to do"; exit 0; fi
if [ "$m" -lt 20 ]; then                                          # after midnight: only the last job (END 00:20) may still run
  [ "$END" = "00:20" ] || { echo "after midnight – earlier job window is over – nothing to do"; exit 0; }
  end_s=$(TZ=Asia/Kolkata date -d "$(ist +%F) $END" +%s)
else
  end_s=$(TZ=Asia/Kolkata date -d "$(ist +%F) $END" +%s)
  [ "${END%%:*}" -lt 6 ] && end_s=$((end_s + 86400))              # 00:20 = after midnight
fi
# never run into GitHub's 6-hour job limit (358 min in the workflow): stop by 345 min after this job started
cap_s=$(( $(date +%s) + 345 * 60 ))
[ -z "${MARKET_LOOP_NOW:-}" ] && [ "$end_s" -gt "$cap_s" ] && end_s=$cap_s
if [ "${MARKET_LOOP_DRY:-0}" = "1" ]; then echo "would run until $(TZ=Asia/Kolkata date -d "@$end_s" '+%d-%b %H:%M') IST"; exit 0; fi
# ---- live 1-minute futures bars from the Angel WebSocket (29-Oct: the candle API rate-limits far below its published limit).
# The engines read today's candles from .cache/ws and call the candle API only for older history (once a day) and as a
# fallback. ANGEL_WS=0 switches this off. The collector is restarted if it exits and stopped when this job ends.
if [ "${ANGEL_WS:-1}" = "1" ]; then
  mkdir -p .cache/ws
  # restarts are paced (20 s, and 5 min after 4 restarts within 30 min) so Angel never sees a burst of logins
  ( r=0; t0=$(date +%s); while true; do timeout 21600 python -m wsfeed; rc=$?
      now=$(date +%s); [ $((now - t0)) -gt 1800 ] && { r=0; t0=$now; }; r=$((r + 1))
      if [ "$r" -ge 4 ]; then echo "[ws] collector exited ($rc) - $r restarts in 30 min, pausing 5 min"; sleep 300; r=0; t0=$(date +%s)
      else echo "[ws] collector exited ($rc) - restart in 20 s"; sleep 20; fi
    done ) >> .cache/ws/feed.log 2>&1 &
  WS_LOOP=$!
  ws_end() {
    kill $WS_LOOP 2>/dev/null; pkill -f "python -m wsfeed" 2>/dev/null; sleep 2
    echo "[ws] collector log (last lines):"; tail -n 15 .cache/ws/feed.log 2>/dev/null
    # keep the day's bars (5-min, price / volume / OI incl. MCX OI that Angel has no history for) on the "ws-bars" branch
    f="ws_$(TZ=Asia/Kolkata date +%Y%m%d_%H%M).csv.gz"; mkdir -p state/wsbars
    # 1-minute bars as recorded (futures + options: price, volume, OI); shallow fetch so the growing branch is never cloned
    if n=$(python -c "import wsbars; print(wsbars.export('state/wsbars/$f', step='ONE_MINUTE'))") && [ "${n:-0}" -gt 0 ]; then
      save_shallow ws-bars wsbars "$f" && echo "[ws] saved $n one-minute bars to ws-bars/$f" || echo "::warning::ws bars not saved"
    fi
  }
  trap ws_end EXIT
  echo "[ws] WebSocket collector started"
fi
while true; do
  now_s=$(TZ=Asia/Kolkata date +%s)
  [ "$now_s" -ge "$end_s" ] && { echo "reached $END IST – job done"; break; }
  echo "=== scan at $(TZ=Asia/Kolkata date '+%d-%b %H:%M:%S') IST ==="
  iteration
  # sleep until the next slot: minute 02, 17, 32 or 47 IST
  m=$(TZ=Asia/Kolkata date +%-M); s=$(TZ=Asia/Kolkata date +%-S)
  next=$(( ( (m + 13) / 15 ) * 15 + 2 )); [ "$next" -le "$m" ] && next=$((next + 15))
  wait=$(( (next - m) * 60 - s )); [ "$wait" -lt 30 ] && wait=$((wait + 900))
  now_s=$(TZ=Asia/Kolkata date +%s)
  [ $((now_s + wait)) -ge "$end_s" ] && { echo "next slot is after $END IST – job done"; break; }
  echo "sleeping ${wait}s"; sleep "$wait"
done
