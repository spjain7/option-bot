"""Telegram (primary) + WhatsApp via CallMeBot (optional). Both free."""
import os, io, requests

TG_TOKEN  = os.getenv("TELEGRAM_TOKEN")
TG_CHAT   = os.getenv("TELEGRAM_CHAT_ID")
WA_PHONE  = os.getenv("CALLMEBOT_PHONE")
WA_APIKEY = os.getenv("CALLMEBOT_APIKEY")


def _plain(t):
    return t.replace("*", "").replace("_", "")


def send(text, csv_df=None, fname="signals.csv"):
    print("\n" + text + "\n")
    if TG_TOKEN and TG_CHAT:
        base = f"https://api.telegram.org/bot{TG_TOKEN}"
        try:
            r = requests.post(f"{base}/sendMessage", timeout=20,
                              data={"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown"})
            if not r.ok:
                requests.post(f"{base}/sendMessage", timeout=20, data={"chat_id": TG_CHAT, "text": _plain(text)})
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
