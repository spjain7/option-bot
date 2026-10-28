"""Telegram (primary) + WhatsApp via CallMeBot (optional). Both free."""
import os, io, requests

TG_TOKEN  = os.getenv("TELEGRAM_TOKEN")
TG_CHAT   = os.getenv("TELEGRAM_CHAT_ID")
WA_PHONE  = os.getenv("CALLMEBOT_PHONE")
WA_APIKEY = os.getenv("CALLMEBOT_APIKEY")


def _plain(t):
    return t.replace("*", "").replace("_", "")


from pathlib import Path
import json, time
PENDING = Path(__file__).resolve().parent / "state" / "telegram_pending.json"


def _post(url, data, tries=4):
    """POST with Telegram rate-limit handling (HTTP 429 -> wait retry_after and retry). Returns the response or None."""
    for i in range(tries):
        try:
            r = requests.post(url, timeout=20, data=data)
        except Exception:
            time.sleep(3); continue
        if r.status_code == 429:
            try:
                wait = float(r.json().get("parameters", {}).get("retry_after", 5))
            except Exception:
                wait = 5
            time.sleep(min(wait + 1, 60)); continue
        return r
    return None


def _queue(text):
    try:
        q = json.loads(PENDING.read_text()) if PENDING.exists() else []
        PENDING.parent.mkdir(exist_ok=True)
        PENDING.write_text(json.dumps((q + [text])[-50:]))
    except Exception as e:
        print("could not queue Telegram message:", e)


def resend_pending():
    """Re-send messages that failed in an earlier run (called once per run by runner.py)."""
    if not (TG_TOKEN and TG_CHAT) or not PENDING.exists():
        return
    if not json.loads(PENDING.read_text() or "[]"):
        return
    q = json.loads(PENDING.read_text() or "[]")
    PENDING.write_text("[]")                         # keep the (empty) file so the state commit records the change
    for t in q:
        send(t)


def send(text, csv_df=None, fname="signals.csv"):
    print("\n" + text + "\n")
    if TG_TOKEN and TG_CHAT:
        base = f"https://api.telegram.org/bot{TG_TOKEN}"
        try:
            r = _post(f"{base}/sendMessage", {"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown"})
            if r is None or not r.ok:
                r = _post(f"{base}/sendMessage", {"chat_id": TG_CHAT, "text": _plain(text)})
            if r is None or not r.ok:
                _queue(text)                       # kept in state/telegram_pending.json and re-sent by the next run
            if csv_df is not None and not csv_df.empty:
                buf = io.BytesIO(csv_df.to_csv(index=False).encode())
                requests.post(f"{base}/sendDocument", timeout=60,
                              data={"chat_id": TG_CHAT}, files={"document": (fname, buf)})
        except Exception as e:
            print("Telegram error:", e)
    if WA_PHONE and WA_APIKEY:
        try:
            requests.get("https://api.callmebot.com/whatsapp.php", timeout=20,
                         params={"phone": WA_PHONE, "text": _plain(text)[:1500], "apikey": WA_APIKEY})
        except Exception as e:
            print("WhatsApp error:", e)


def telegram_check():
    """Print every chat that has messaged the bot (to find TELEGRAM_CHAT_ID) and send a test message."""
    if not TG_TOKEN:
        print("❌ TELEGRAM_TOKEN secret is missing."); return
    base = f"https://api.telegram.org/bot{TG_TOKEN}"
    me = requests.get(f"{base}/getMe", timeout=20).json()
    if not me.get("ok"):
        print("❌ Token rejected by Telegram:", me.get("description")); raise SystemExit(1)
    print(f"Bot: @{me['result']['username']}")
    r = requests.get(f"{base}/getUpdates", timeout=20).json()
    if not r.get("ok"):                                         # e.g. bot uses a webhook (left untouched)
        print("Can't list chats:", r.get("description"))
    ups = r.get("result", [])
    chats = {}
    for u in ups:
        m = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
        c = m.get("chat")
        if c:
            chats[c["id"]] = c.get("title") or c.get("username") or c.get("first_name")
    print("Chats that messaged the bot (use the number as TELEGRAM_CHAT_ID):")
    for cid, nm in chats.items():
        print(f"  CHAT_ID = {cid}   ({nm})")
    if not chats:
        print("  none yet - open the bot in Telegram, press Start / send 'hi', then run this again.")
    if TG_CHAT:
        r = requests.post(f"{base}/sendMessage", timeout=20,
                          data={"chat_id": TG_CHAT, "text": "✅ Telegram connected. MCX buy/sell + option alerts will arrive here."})
        print("Test message:", "SENT ✅" if r.ok else f"FAILED ❌ {r.text[:200]}")
        if not r.ok:
            raise SystemExit(1)
    else:
        print("TELEGRAM_CHAT_ID secret not set yet.")
