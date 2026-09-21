# Setup Guide: no software install, browser only

You'll create 3 free accounts or keys, upload the files to GitHub, and paste 6 secrets.

---

## STEP 1: Telegram bot (5 min, on your phone)
1. In Telegram, search **@BotFather** and send `/newbot`.
2. Give it a name (e.g. *My Option Bot*) and a username ending in `bot` (e.g. `sunil_options_bot`).
3. BotFather replies with a **token** like `7234567890:AAH...`. Copy it. This is your **TELEGRAM_TOKEN**.
4. Open your new bot and press **START**, then send it any message (e.g. "hi").
5. In a browser, open: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   (replace `<YOUR_TOKEN>`, keeping the word `bot` in front of it).
6. Find `"chat":{"id":123456789`. That number is your **TELEGRAM_CHAT_ID**.

## STEP 2: Angel One SmartAPI key (10 min)
1. Go to **https://smartapi.angelone.in** → **Sign Up** (use the same email or mobile as your Angel One account) → log in.
2. Click **Create an App**:
   - Type: **Trading APIs**
   - App name: anything
   - Redirect URL: `https://127.0.0.1`
   - Angel Client ID: your client code
   - If it asks for a **Static IP**: that is only used for placing orders, and this bot never places orders. Enter your current IP (search "what is my ip" on Google).
3. Copy the **API Key**. This is your **ANGEL_API_KEY**.
4. Turn on TOTP: open **https://smartapi.angelone.in/enable-totp**, then enter your Client ID, MPIN and the OTP.
   A QR code appears with a **secret key text** under it (like `JBSWY3DPEHPK3PXP`).
   Copy that text. This is your **ANGEL_TOTP_SECRET**.
5. **ANGEL_CLIENT_ID** is your Angel client code (e.g. `S123456`). **ANGEL_PIN** is your 4-digit MPIN.

## STEP 3: GitHub account and repository (10 min)
1. Go to **https://github.com** → **Sign up** (free) → verify your email.
2. Click **+** (top right) → **New repository**:
   - Name: `option-bot`
   - Select **Private** (important, so only you can see your trades)
   - Click **Create repository**
3. On the new repo page, click **"uploading an existing file"**.
4. Unzip `option-seller-bot.zip` on your PC and open the `option-seller-bot` folder. Select **everything inside it** (including the `.github` folder) and drag it into the GitHub page. Then click **Commit changes**.
5. **Check the result:** you should see a `.github` folder in the repo.
   If it's missing (Mac Finder hides it), do this instead:
   - Click **Add file → Create new file**.
   - Name it exactly: `.github/workflows/bot.yml`
   - Open `bot.yml` from the zip in Notepad, copy all of it, paste it in, and click **Commit changes**.

## STEP 4: Add your secrets (5 min)
1. In the repo, go to **Settings → Secrets and variables → Actions → New repository secret**.
2. Add each of these, one at a time (the name must match exactly):

| Name | Value |
|---|---|
| `ANGEL_API_KEY` | from Step 2 |
| `ANGEL_CLIENT_ID` | your client code |
| `ANGEL_PIN` | your MPIN |
| `ANGEL_TOTP_SECRET` | the TOTP secret text |
| `TELEGRAM_TOKEN` | from Step 1 |
| `TELEGRAM_CHAT_ID` | from Step 1 |

**Optional WhatsApp:**
1. Save **+34 684 72 30 13** in your contacts and WhatsApp it: `I allow callmebot to send me messages`
2. You'll get an API key back. Add two more secrets:
   - `CALLMEBOT_PHONE` = `91XXXXXXXXXX`
   - `CALLMEBOT_APIKEY` = the key

## STEP 5: Allow the bot to save its trade book
Go to **Settings → Actions → General**, scroll to **Workflow permissions**, select **Read and write permissions**, and click **Save**.

## STEP 6: Test it
1. Open the **Actions** tab. If asked, click **"I understand my workflows, go ahead and enable them"**.
2. Click **Option Selling Bot** on the left → **Run workflow** → keep mode `test` → click the green **Run workflow**.
3. Within 1–2 minutes Telegram should show:
   **"✅ Option-selling bot connected! NIFTY … PCR … ATM IV … VIX …"**
   - Run this test **during market hours** (9:15 AM–3:30 PM) so live option prices are available.
   - A red ❌ run means something failed. Click the run, then **Run bot**, to read the error. The bot also sends errors to Telegram.

**That's it.** From now on it runs automatically:
- every 15 minutes from 9:15 AM to 4:15 PM on trading days (option calls, management and RSI)
- hourly from 4 PM to 11 PM (MCX RSI alerts)
- To get the report on demand: **Run workflow** with mode `report`.
- To pause the bot: **Actions → Option Selling Bot → ··· → Disable workflow**.

---

## Changing settings later (no install)
Open `config.py` in GitHub, click the ✏️ pencil icon, edit, and click **Commit changes**. For example:
- `OPTION_ENGINE_ENABLED` / `RSI_ENGINE_ENABLED`: turn either engine on or off
- `SELL_STYLE`: `"HEDGED"` (spreads, low margin) or `"NAKED"` (single CE/PE sell or strangle, high margin)
- `EVENT_DATES`: add RBI, Fed, Budget and CPI dates to block new trades on those days
- `CAPITAL_RS`, `MAX_OPEN_POSITIONS`, `MAX_DAILY_LOSS_RS`: your risk limits
- `RSI_OVERSOLD` / `RSI_OVERBOUGHT` / `RSI_ALERT_MODE` / `RSI_MCX`: RSI alert settings
- `MONTHLY_STOCKS`, `DELTA`, `RULES`: the stock list, strike deltas, target %, SL multiple and adjust delta

## Cost
- GitHub gives **2,000 free minutes a month** for private repos. This bot uses about **1,300**, including the hourly MCX evening runs for RSI alerts.
- Angel One API and Telegram are free.

## Common problems
| Symptom | Fix |
|---|---|
| `Angel login failed` | Re-check ANGEL_PIN (MPIN, not password) and the TOTP secret (no spaces) |
| No Telegram message | Check the chat ID, and that you pressed START on your bot |
| `no chain` | Run the test during market hours |
| Workflow doesn't run on schedule | Actions tab → make sure the workflow is enabled. GitHub can delay runs 5–15 minutes |
