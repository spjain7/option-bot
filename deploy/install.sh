#!/usr/bin/env bash
# One-time setup on a free Ubuntu server (Oracle Cloud Always Free / Google e2-micro / old PC / Raspberry Pi).
#   curl -fsSL <raw link to this file> -o install.sh && sudo bash install.sh
# Asks for your secrets once and stores them in /etc/option-bot.env (readable by root only). Nothing is sent anywhere
# except Angel One (market data) and Telegram (alerts).
set -euo pipefail
APP=/opt/option-bot; STATE_ROOT=/var/lib/option-bot
apt-get update -qq && apt-get install -y -qq git python3 python3-venv tzdata > /dev/null
timedatectl set-timezone Asia/Kolkata
read -rp "GitHub repo (owner/name) [spjain7/option-bot]: " REPO; REPO=${REPO:-spjain7/option-bot}
read -rsp "GitHub read-only token (needed only if the repo is PRIVATE; Enter to skip): " GHT; echo
URL="https://github.com/$REPO.git"; [ -n "$GHT" ] && URL="https://x-access-token:$GHT@github.com/$REPO.git"
[ -d "$APP/.git" ] || git clone -q "$URL" "$APP"
git -C "$APP" remote set-url origin "$URL"
python3 -m venv "$APP/.venv" && "$APP/.venv/bin/pip" -q install -r "$APP/requirements.txt"
if [ ! -f /etc/option-bot.env ]; then
  umask 077
  : > /etc/option-bot.env
  for k in ANGEL_API_KEY ANGEL_CLIENT_ID ANGEL_PIN ANGEL_TOTP_SECRET TELEGRAM_TOKEN TELEGRAM_CHAT_ID; do
    read -rsp "$k: " v; echo; printf '%s=%q\n' "$k" "$v" >> /etc/option-bot.env
  done
  chmod 600 /etc/option-bot.env
fi
mkdir -p "$STATE_ROOT"/{alerts,crude,main}
# carry over today's state from GitHub (open alerts, paper account) so nothing restarts from zero
for b in alerts crude; do
  git -C "$APP" fetch -q origin "$b-state" 2>/dev/null && git -C "$APP" archive FETCH_HEAD "$b" | tar -x -C "$STATE_ROOT" || true
done
cp -n "$APP"/state/*.json "$STATE_ROOT/main/" 2>/dev/null || true
cp "$APP/deploy/option-bot.service" "$APP/deploy/option-bot.timer" /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now option-bot.timer
echo "✅ Installed. Check: systemctl list-timers option-bot.timer   ·   logs: journalctl -u option-bot -n 80"
