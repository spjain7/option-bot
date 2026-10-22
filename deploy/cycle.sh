#!/usr/bin/env bash
# One 15-minute cycle on your own server: update code, then run the option bot, the buy/sell alerts and the crude
# paper engine. State lives OUTSIDE the repo in $STATE_ROOT, so code updates never touch it. No orders anywhere.
set -uo pipefail
APP=${APP:-/opt/option-bot}; STATE_ROOT=${STATE_ROOT:-/var/lib/option-bot}
exec 9>"$STATE_ROOT/.lock"; flock -n 9 || { echo "previous cycle still running – skipped"; exit 0; }
cd "$APP"
set -a; . /etc/option-bot.env; set +a
export ALERTS_STATE_DIR="$STATE_ROOT/alerts" CRUDE_STATE_DIR="$STATE_ROOT/crude" ALERTS_TELEGRAM=1 CRUDE_TELEGRAM=1 SAVE_OK=success
mkdir -p "$ALERTS_STATE_DIR" "$CRUDE_STATE_DIR" "$STATE_ROOT/main"
# 1) code update (keeps the option bot's own state files)
git fetch -q origin main && git reset -q --hard origin/main && cp -f "$STATE_ROOT"/main/*.json state/ 2>/dev/null
PY="$APP/.venv/bin/python"
# 2) option-selling bot (existing engines, unchanged)
timeout 600 "$PY" runner.py auto; echo "option bot exit $?"
cp -f state/*.json "$STATE_ROOT/main/" 2>/dev/null
# 3) buy/sell alerts
[ -f "$ALERTS_STATE_DIR/state.json" ] || export ALERTS_NEW_STATE=1
timeout 600 "$PY" -m alerts.run scan; echo "alerts exit $?"
[ -f "$ALERTS_STATE_DIR/outbox.json" ] && "$PY" -m alerts.run flush && rm -f "$ALERTS_STATE_DIR/outbox.json"
# 4) crude paper engine
[ -f "$CRUDE_STATE_DIR/state.json" ] || export CRUDE_NEW_ACCOUNT=1
timeout 300 "$PY" -m crude.run scan; echo "crude exit $?"
[ -f "$CRUDE_STATE_DIR/outbox.json" ] && "$PY" -m crude.run flush && rm -f "$CRUDE_STATE_DIR/outbox.json"
