# Run the bot on a FREE server (so the repo can be private)

This setup runs the same code as GitHub Actions: the option bot, the buy/sell alerts and the crude paper engine, every 15 minutes. Your secrets stay on your own server.

## 1. Get a free server (pick one)
| Option | Cost | Notes |
|---|---|---|
| **Oracle Cloud "Always Free"** (recommended) | ₹0 forever | A card is needed only to verify identity. Choose region **Mumbai or Hyderabad**, shape **VM.Standard.A1.Flex (1 OCPU, 6 GB)** or **VM.Standard.E2.1.Micro**, image **Ubuntu 22.04/24.04**. |
| Google Cloud e2-micro free tier | ₹0 | US regions only (works, slightly higher latency). |
| Your own old PC / laptop / Raspberry Pi with Ubuntu | ₹0 | Must stay on and online during market hours. |

## 2. Install (about 5 minutes)
SSH into the server, then run:
```
git clone https://github.com/spjain7/option-bot.git /tmp/ob && sudo bash /tmp/ob/deploy/install.sh
```
- **What the installer asks for:** your Angel API key, client ID, PIN, TOTP secret, Telegram token and chat ID. They are saved to `/etc/option-bot.env`, which only root can read.
- **What it brings over:** today's open alerts and the crude paper account, copied from GitHub so nothing restarts from zero.
- **Check it is running:** `systemctl list-timers option-bot.timer` and `journalctl -u option-bot -n 80`.

## 3. Switch off GitHub Actions (avoids duplicate alerts)
Do this once the server's first cycle has sent its Telegram startup message.

Go to GitHub → **Actions** and, for each workflow below, choose **"…" → Disable workflow**:
- Option Selling Bot
- Market loop
- Buy-Sell alerts
- Crude Oil PAPER engine

## 4. Make the repo private
1. GitHub → **Settings → General → Danger Zone → Change visibility → Private**.
2. Create a **read-only token** for the server: GitHub → Settings → Developer settings → Fine-grained tokens → this repo only → *Contents: Read-only*.
3. On the server, run `sudo bash /opt/option-bot/deploy/install.sh` again and paste the token when asked. The server keeps pulling code updates.
4. With Actions disabled, a private repo costs **₹0**: there are no Action minutes left to pay for.

## Safety checklist
- Turn on 2-factor login for GitHub, Angel One and the Oracle account.
- Never paste tokens into chats or files. If a token was ever exposed, regenerate it at the provider and update `/etc/option-bot.env`.
- The server only reads market data and sends Telegram messages. There is no order code in this repo's alert or paper engines.
- Angel One's static-IP rule is for order APIs. If Angel ever asks for it for market data, register the server's public IP in the Angel API dashboard.
