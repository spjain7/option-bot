"""CLI for the option-BUY alert engine (TEST PHASE), run inside scripts/market_loop.sh.

  python -m obuy.run scan     # fetch, evaluate, write state + outbox (no Telegram here)
  python -m obuy.run flush    # send the outbox AFTER the state was pushed (SAVE_OK=success|failure)
"""
import json, os, sys, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SD = Path(os.getenv("OBUY_STATE_DIR", str(ROOT / "state" / "obuy")))
STATE, OUTBOX = SD / "state.json", SD / "outbox.json"


def scan():
    from obuy import engine as E
    from angel import Angel, load_master, now_ist
    now = now_ist()
    SD.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        state = json.loads(STATE.read_text())
    elif os.getenv("OBUY_NEW_STATE") == "1":
        state = E.new_state()
    else:
        raise SystemExit("::error::option-buy state missing and not allowed to create a new one")
    if now.weekday() >= 5 or not ("09:15" <= f"{now:%H:%M}" <= "16:00"):
        OUTBOX.write_text(json.dumps(dict(messages=[]))); print("option-buy: outside NSE hours"); return 0
    try:
        api, master = Angel(), load_master()
    except Exception as e:
        OUTBOX.write_text(json.dumps(dict(messages=[f"⚠️ OPTION BUY – Angel login failed: {type(e).__name__}. No alerts this run."])))
        return 2
    state, msgs, rep = E.scan(api, master, now, state)
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(state, indent=1, default=str)); os.replace(tmp, STATE)
    OUTBOX.write_text(json.dumps(dict(messages=msgs), indent=1))
    for x in rep:
        print("option-buy:", x)
    print(f"option-buy: {len(msgs)} message(s), {len(state['open'])} open")
    return 0


def flush():
    from crude.run import telegram
    if not OUTBOX.exists():
        return 0
    msgs = json.loads(OUTBOX.read_text())["messages"]
    if msgs and os.getenv("SAVE_OK", "success") != "success":
        msgs = ["⚠️ OPTION BUY – state could not be saved this run; the alerts below may repeat.\n"] + msgs
    bad = 0
    for m in msgs:
        ok, d = telegram(m) if os.getenv("OBUY_TELEGRAM", "1") == "1" else (True, "telegram off")
        print(("sent" if ok else "TELEGRAM FAILED") + f": {d} | {m.splitlines()[0][:80]}")
        bad += not ok
    OUTBOX.unlink()
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.exit(flush() if (sys.argv[1:] or ["scan"])[0] == "flush" else scan())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(); sys.exit(2)
