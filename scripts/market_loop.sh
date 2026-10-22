#!/usr/bin/env bash
# Runs the alert engine and the crude PAPER engine every 15 minutes (2 min after each candle closes) until END (IST HH:MM).
# Used because GitHub's cron skips most scheduled runs. State is restored/saved to its branch around every scan;
# Telegram is sent only after the save. A failed iteration is reported and the loop continues.
set -uo pipefail
END="$1"                                  # e.g. 14:50
git config user.name "option-bot loop"; git config user.email "bot@users.noreply.github.com"

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
    for f in "$@"; do [ -f "state/$sub/$f" ] && cp "state/$sub/$f" "/tmp/sv/$sub/"; done
    (cd /tmp/sv && git add "$sub" && (git diff --cached --quiet || git commit -qm "$sub state $(date -u +%F_%H%M)") \
       && git push -q origin "HEAD:refs/heads/$br") && return 0
    sleep 5
  done
  return 1
}

iteration() {
  # ---- buy/sell alerts ----
  if n=$(restore alerts-state alerts); then
    export ALERTS_NEW_STATE=$n
    python -m alerts.run scan; rc=$?
    if [ -f state/alerts/state.json ] && save alerts-state alerts state.json; then SAVE_OK=success; else SAVE_OK=failure; fi
    [ -f state/alerts/outbox.json ] && SAVE_OK=$SAVE_OK python -m alerts.run flush
    echo "alerts scan exit $rc, save $SAVE_OK"
  else
    echo "::error::alerts state restore failed"
  fi
  # ---- crude paper engine ----
  if n=$(restore crude-state crude); then
    export CRUDE_NEW_ACCOUNT=$n MODE=scan
    python -m crude.run scan; rc=$?
    if [ -f state/crude/state.json ] && save crude-state crude state.json scan_log.jsonl last_run.json; then SAVE_OK=success; else SAVE_OK=failure; fi
    SAVE_OK=$SAVE_OK python -m crude.run flush
    echo "crude scan exit $rc, save $SAVE_OK"
  else
    echo "::error::crude state restore failed"
  fi
}

h=$(TZ=Asia/Kolkata date +%-H)
if [ "$h" -ge 1 ] && [ "$h" -lt 8 ]; then echo "outside the market day (IST $h h) – nothing to do"; exit 0; fi
end_s=$(TZ=Asia/Kolkata date -d "today $END" +%s)
if [ "${END%%:*}" -lt 6 ] && [ "$h" -ge 6 ]; then end_s=$((end_s + 86400)); fi    # 00:20 = after midnight
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
