"""Command line for the Crude Oil PAPER engine (used by .github/workflows/crude-paper.yml).

  python -m crude.run scan     # normal paper scan (opens/manages paper positions, saves state)
  python -m crude.run health   # status only: fetch + evaluate + report, never opens/closes positions, never saves
  python -m crude.run flush    # send queued Telegram messages AFTER the state was pushed (SAVE_OK=success|failure)

Telegram is sent only by `flush`, after the state has been saved, so a scan is never reported as successful when
saving failed. Env: CRUDE_STATE_DIR (default state/crude), CRUDE_TELEGRAM (1/0), CRUDE_NEW_ACCOUNT (1 allows creating
a new paper account when no state exists).
"""
import json, os, sys, traceback
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from crude import config as K  # noqa: E402

SD = Path(os.getenv("CRUDE_STATE_DIR", str(ROOT / "state" / "crude")))
OUTBOX, LAST, LOG = SD / "outbox.json", SD / "last_run.json", SD / "scan_log.jsonl"


def telegram(text):
    """Send plain text. Returns (ok, detail). Never prints the token."""
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not tok or not chat:
        return False, "TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not set"
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                          data={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"})
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return (bool(j.get("ok")), "ok" if j.get("ok") else f"HTTP {r.status_code}: {j.get('description', '')[:120]}")
    except Exception as e:
        return False, f"{type(e).__name__}"


def _write_outputs(rec, outbox, code):
    from crude import report as REP
    SD.mkdir(parents=True, exist_ok=True)
    OUTBOX.write_text(json.dumps(dict(messages=outbox, code=code, time=rec.get("time")), indent=1, default=str))
    LAST.write_text(json.dumps(dict(rec, exit_code=code), indent=1, default=str))
    if rec.get("run_mode") == "scan":
        lines = LOG.read_text().splitlines()[-1999:] if LOG.exists() else []
        lines.append(json.dumps(dict(time=rec["time"], session=rec["session"], api=rec["api"], data={k: v for k, v in rec["data"].items()},
                                     decisions={k: dict(decision=v.get("decision"), side=v.get("side"), bar=v.get("bar_time"),
                                                        new=v.get("new_candle"), blocks=v.get("blocks"), ignored=v.get("ignored"),
                                                        oi=v.get("oi"), metrics=v.get("metrics"))
                                                for k, v in rec["decisions"].items()},
                                     actions=rec["actions"], errors=rec["errors"], code=code), default=str))
        LOG.write_text("\n".join(lines) + "\n")
    summ = os.getenv("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a") as f:
            f.write(REP.markdown(rec, code))


def run(mode):
    from crude import engine as E, report as REP
    import pandas as pd
    from angel import now_ist
    now = now_ist()
    info = dict(event=os.getenv("GITHUB_EVENT_NAME", "local"), number=os.getenv("GITHUB_RUN_NUMBER", "-"))
    if not K.ENABLED and mode == "scan":
        print("crude engine disabled in crude/config.py (ENABLED = False) – nothing done")
        _write_outputs(dict(time=str(now), session="-", api={}, data={}, decisions={}, actions=["disabled"], errors=[],
                            run_mode=mode, version=K.VERSION, mode=K.MODE, run=info), [], 0)
        return 0
    try:
        from angel import Angel, load_master
        api = Angel()
    except Exception as e:
        msg = f"Angel login failed: {type(e).__name__}: {str(e)[:160]}"
        print("::error::" + msg)
        rec = dict(time=str(now), session="-", api={"login": "FAILED"}, data={}, decisions={}, actions=[], errors=[msg],
                   run_mode=mode, version=K.VERSION, mode=K.MODE, run=info)
        _write_outputs(rec, [REP.error_msg(now, "API AUTHENTICATION FAILED – no data, nothing evaluated", msg)], 2)
        return 2
    try:
        master = load_master()
    except Exception as e:
        msg = f"instrument master download failed: {type(e).__name__}"
        rec = dict(time=str(now), session="-", api={"master": "FAILED"}, data={}, decisions={}, actions=[], errors=[msg],
                   run_mode=mode, version=K.VERSION, mode=K.MODE, run=info)
        _write_outputs(rec, [REP.error_msg(now, "INSTRUMENT MASTER FAILED", msg)], 2)
        return 2
    rec, outbox, code = E.scan(api, master, now, mode=mode, state_path=SD / "state.json",
                               allow_new=os.getenv("CRUDE_NEW_ACCOUNT") == "1", run_info=info)
    print(REP.health(rec))
    for k, v in rec["decisions"].items():
        print(f"[decision] {k}: {v.get('decision')} {v.get('side', '')} bar={v.get('bar_time')} blocks={v.get('blocks')} reasons={v.get('reasons')}")
    _write_outputs(rec, outbox, code)
    for e in rec["errors"]:
        print("::error::" + e)
    for w in rec.get("warnings", []):
        print("::warning::" + w)
    return code


def flush():
    """Send the queued messages. SAVE_OK must be 'success' for normal messages to go out."""
    if not OUTBOX.exists():
        print("::error::no outbox – the scan step did not finish")
        ok, d = (telegram("⚠️ CRUDE ENGINE – the scan step crashed before writing its result. Check GitHub Actions.")
                 if os.getenv("CRUDE_TELEGRAM") == "1" else (True, "telegram off"))
        return 1
    box = json.loads(OUTBOX.read_text())
    msgs = box["messages"]
    if os.getenv("SAVE_OK", "success") != "success":
        msgs = ["⚠️ CRUDE ENGINE – STATE SAVE FAILED. This scan's paper positions/results were NOT persisted; "
                "nothing below should be treated as recorded.\n" + (msgs[0][:1500] if msgs else "")]
    if os.getenv("CRUDE_TELEGRAM") != "1":
        print(f"Telegram off – {len(msgs)} message(s) not sent:")
        for m in msgs:
            print("-----\n" + m)
        return 0
    bad = 0
    for m in msgs:
        ok, d = telegram(m)
        print(("sent" if ok else "TELEGRAM FAILED") + f": {d}")
        bad += not ok
    if bad:
        print(f"::error::{bad} Telegram message(s) failed")
        return 1
    return 0


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "health"
    try:
        sys.exit(flush() if m == "flush" else run(m if m in ("scan", "health") else "health"))
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(2)
