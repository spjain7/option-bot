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
    import time
    for attempt in range(4):                       # Telegram rate limit (HTTP 429): wait as told and retry
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                              data={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"})
            j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        except Exception as e:
            if attempt == 3:
                return False, f"{type(e).__name__}"
            time.sleep(3); continue
        if j.get("ok"):
            return True, "ok"
        wait = (j.get("parameters") or {}).get("retry_after")
        if r.status_code == 429 and wait and attempt < 3:
            time.sleep(min(float(wait) + 1, 90)); continue
        return False, f"HTTP {r.status_code}: {j.get('description', '')[:120]}"
    return False, "rate limited"


def run_context(now):
    """Phase-6 monitoring: how late this scheduled run started, and how the PREVIOUS run of this workflow ended
    (catches failed state pushes / Telegram deliveries of the last run). Never prints the token."""
    import pandas as pd
    info = dict(event=os.getenv("GITHUB_EVENT_NAME", "local"), number=os.getenv("GITHUB_RUN_NUMBER", "-"))
    slot = (now - pd.Timedelta(minutes=2)).floor("15min") + pd.Timedelta(minutes=2)
    info["delay_min"] = round((now - slot).total_seconds() / 60, 1) if info["event"] == "schedule" else None
    tok, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if tok and repo:
        try:
            r = requests.get(f"https://api.github.com/repos/{repo}/actions/workflows/crude-paper.yml/runs",
                             params={"per_page": 5, "status": "completed"}, timeout=15,
                             headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
            runs = [x for x in r.json().get("workflow_runs", []) if str(x.get("run_number")) != info["number"]]
            if runs:
                info["previous_run"] = dict(number=runs[0]["run_number"], event=runs[0]["event"],
                                            conclusion=runs[0]["conclusion"], started=runs[0]["run_started_at"])
        except Exception as e:
            info["previous_run"] = dict(conclusion=f"unknown ({type(e).__name__})")
    return info


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
    info = run_context(now)
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
    if info.get("delay_min") is not None and info["delay_min"] > K.RUN_DELAY_WARN_MIN:
        rec.setdefault("warnings", []).append(f"scheduled run started {info['delay_min']:.0f} min late (GitHub cron delay)")
    pr = info.get("previous_run") or {}
    if pr.get("conclusion") not in (None, "success"):
        rec.setdefault("warnings", []).append(f"previous run #{pr.get('number')} ended '{pr.get('conclusion')}' – check Actions")
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
