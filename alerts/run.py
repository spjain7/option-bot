"""CLI for the BUY/SELL alert engine (used by .github/workflows/alerts.yml).

  python -m alerts.run scan     # fetch, evaluate, write state + outbox (no Telegram here)
  python -m alerts.run flush    # send the outbox AFTER the state was pushed (SAVE_OK=success|failure)
"""
import json, os, sys, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SD = Path(os.getenv("ALERTS_STATE_DIR", str(ROOT / "state" / "alerts")))
STATE, OUTBOX = SD / "state.json", SD / "outbox.json"


def log_report(rep):
    """Run-log lines (GitHub Actions log): per-instrument status, stock scan summary, every rejected / held stock signal."""
    for n, i in rep["instruments"].items():
        print(f"[{n}] " + " | ".join(f"{k}: {v}" for k, v in i.items()))
    if isinstance(rep.get("stocks"), dict):
        print("[stocks] " + " | ".join(f"{k}: {v}" for k, v in rep["stocks"].items()))
    for x in rep.get("stock_skips", []):
        print("[rejected] stock", x)
    for e in rep["errors"]:
        print("::warning::" + e)


def scan():
    from alerts import engine as E
    from angel import Angel, load_master, now_ist
    now = now_ist()
    SD.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        state = json.loads(STATE.read_text())                 # unreadable state -> exception -> run fails, no reset
    elif os.getenv("ALERTS_NEW_STATE") == "1":
        state = E.new_state()
    else:
        raise SystemExit("::error::alert state missing and not allowed to create a new one")
    try:
        api, master = Angel(), load_master()
    except Exception as e:
        OUTBOX.write_text(json.dumps(dict(messages=[f"⚠️ ALERTS – Angel login / instrument list failed: {type(e).__name__}. No alerts this run."])))
        print("::error::login failed"); return 2
    state, msgs, rep = E.scan(api, master, now, state)
    import share                                              # prices for the website, with this same Angel session
    print("website price snapshot:", share.push(api, master, now))
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(state, indent=1, default=str)); os.replace(tmp, STATE)
    OUTBOX.write_text(json.dumps(dict(messages=msgs), indent=1))
    log_report(rep)
    summ = os.getenv("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a") as f:
            f.write(f"## Buy/sell alerts – {now:%d-%b %H:%M} IST\n\n{len(msgs)} message(s) queued\n\n```\n"
                    + "\n".join(f"{n}: {i}" for n, i in rep["instruments"].items()) + "\n```\n")
    return 0


PENDING = SD / "pending.json"
GAP_SEC = 3.2           # Telegram allows ~20 messages/minute into one group/channel
MAX_SINGLE = 24         # more than this in one run -> pack messages into combined posts (fewer API calls)


def _pack(msgs, limit=3800):
    out, cur = [], ""
    for m in msgs:
        if cur and len(cur) + len(m) + 2 > limit:
            out.append(cur); cur = ""
        cur = (cur + "\n\n" + m) if cur else m
    if cur:
        out.append(cur)
    return out


def send_photo(path, caption):
    """Send a PNG to the Telegram chat. Returns (ok, detail). Never prints the token."""
    import requests
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not tok or not chat or not Path(path).exists():
        return False, "no token/chat or image"
    try:
        with open(path, "rb") as f:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendPhoto", data={"chat_id": chat, "caption": caption[:1000]},
                              files={"photo": f}, timeout=30)
        return (True, "ok") if r.ok else (False, f"HTTP {r.status_code}")
    except Exception as e:
        return False, type(e).__name__


def flush():
    import time
    from crude.run import telegram
    if not OUTBOX.exists():
        print("::error::no outbox"); return 1
    msgs = json.loads(OUTBOX.read_text())["messages"]
    if PENDING.exists():                                   # messages that could not be delivered last time
        msgs = json.loads(PENDING.read_text()) + msgs
        PENDING.unlink()
    if os.getenv("SAVE_OK", "success") != "success":
        msgs = ["⚠️ ALERTS – state could not be saved this run; alerts below may repeat next run.\n"] + msgs
    if len(msgs) > MAX_SINGLE:
        photos = [m for m in msgs if m.startswith("PHOTO::")]
        msgs = photos + _pack([m for m in msgs if not m.startswith("PHOTO::")])
    failed = []
    for k, m in enumerate(msgs):
        if m.startswith("PHOTO::"):
            _, path, cap = m.split("::", 2)
            ok, d = send_photo(path, cap) if os.getenv("ALERTS_TELEGRAM", "1") == "1" else (True, "telegram off")
            if not ok:
                ok, d = True, f"photo not sent ({d}) – text version follows"
        else:
            ok, d = telegram(m) if os.getenv("ALERTS_TELEGRAM", "1") == "1" else (True, "telegram off")
        print(("sent" if ok else "TELEGRAM FAILED") + f": {d} | {m.splitlines()[0][:80]}")
        if not ok:
            failed.append(m)
        if k + 1 < len(msgs) and os.getenv("ALERTS_TELEGRAM", "1") == "1":
            time.sleep(GAP_SEC)
    if failed:                                             # keep them for the next run instead of losing them
        PENDING.write_text(json.dumps(failed))
        print(f"::warning::{len(failed)} message(s) kept for the next run")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(flush() if (sys.argv[1:] or ["scan"])[0] == "flush" else scan())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(); sys.exit(2)
