"""CLI for the BUY/SELL alert engine (used by .github/workflows/alerts.yml).

  python -m alerts.run scan     # fetch, evaluate, write state + outbox (no Telegram here)
  python -m alerts.run flush    # send the outbox AFTER the state was pushed (SAVE_OK=success|failure)
"""
import json, os, sys, time, traceback
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


def scan_record(prev, started, finished, stats, rep, n_msgs):
    """Outcome of one scan, stored in the state (state['scan']) and in scan.json beside it, so the loop can prove the state
    it saves comes from THIS scan (seq advanced) and say what was skipped. Outcomes:
      SUCCESS          every planned API call was made, no errors
      PARTIAL_SUCCESS  finished, but some instruments reported errors
      RATE_LIMITED     Angel refused calls and some data was skipped
      BUDGET_EXHAUSTED the time budget ran out; later calls were skipped (scan still saved)
      NO_DATA          no instrument could be evaluated
    (FAILED = the scan never wrote its record; the loop reports that.)"""
    st = dict(stats or {})
    errs = len((rep or {}).get("errors", []))
    inst = (rep or {}).get("instruments", {}) or {}
    if st.get("deadline_skips"):
        status = "BUDGET_EXHAUSTED"
    elif st.get("rate_limited") and (st.get("skipped") or st.get("failed")):
        status = "RATE_LIMITED"
    elif inst and all(not v for v in inst.values()):
        status = "NO_DATA"
    elif errs:
        status = "PARTIAL_SUCCESS"
    else:
        status = "SUCCESS"
    note = (f"api requests {st.get('calls', 0)} ok {st.get('ok', 0)} rate-limited {st.get('rate_limited', 0)} "
            f"skipped {st.get('skipped', 0)} (budget {st.get('deadline_skips', 0)}) failed {st.get('failed', 0)} · errors {errs} · messages {n_msgs}")
    return dict(seq=int((prev or {}).get("seq", 0)) + 1, started=str(started), finished=str(finished),
                seconds=int((finished - started).total_seconds()), status=status, note=note,
                api={k: st.get(k, 0) for k in ("calls", "ok", "rate_limited", "skipped", "deadline_skips", "failed", "mem_hits", "disk_hits")},
                errors=errs, messages=n_msgs)


def scan():
    import time
    # P0 4-Nov: own time budget even when the loop script is an older copy (a running job keeps its checkout; this file
    # comes from the latest main) – 1020 s inside the loop's 1200 s timeout, see angel.ANGEL_DEADLINE
    os.environ.setdefault("ANGEL_DEADLINE", str(time.time() + 1020))
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
    try:                                                      # 4-Nov-2026: MCX news / event context – never blocks a call
        from alerts import news as NW
        msgs = NW.enrich(msgs, now) + NW.alerts(state, now)
    except Exception as e:
        print(f"::warning::news step failed: {type(e).__name__}: {e}")
    from alerts import strategies as STR                      # 4-Nov: shadow-call messages are logged, never sent
    shadow_msgs = [m for m in msgs if STR.SHADOW_MARK in str(m)]
    if shadow_msgs:
        msgs = [m for m in msgs if STR.SHADOW_MARK not in str(m)]
        log = state.setdefault("shadow_log", [])
        log.extend(dict(time=str(now), text=str(m).replace(STR.SHADOW_MARK, "", 1).strip()[:600]) for m in shadow_msgs)
        state["shadow_log"] = log[-300:]
        print(f"[shadow] {len(shadow_msgs)} shadow-call message(s) logged, not sent")
    from alerts import paper as PP                            # hard guard: PAPER_ONLY items are never sent
    msgs, dropped = PP.guard_outbox(msgs)
    if dropped:
        print(f"::error::{len(dropped)} PAPER_ONLY message(s) reached the outbox and were dropped (not sent)")
    import share                                              # prices for the website, with this same Angel session
    print("website price snapshot:", share.push(api, master, now))
    state["scan"] = scan_record(state.get("scan"), now, now_ist(), getattr(api, "stats", {}), rep, len(msgs))
    print(f"[scan] outcome {state['scan']['status']} · seq {state['scan']['seq']} · {state['scan']['started'][11:19]}–"
          f"{state['scan']['finished'][11:19]} IST ({state['scan']['seconds']} s) · {state['scan']['note']}")
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(state, indent=1, default=str)); os.replace(tmp, STATE)
    (SD / "scan.json").write_text(json.dumps(state["scan"], indent=1))
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
    import requests, paperguard
    if paperguard.blocked(caption):
        return False, "blocked: PAPER_ONLY"
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
    import paperguard
    msgs = [m for m in msgs if not paperguard.blocked(m)]          # hard guard, also for pending / hand-edited outboxes
    stale = 0
    if PENDING.exists():                                   # messages that could not be delivered last time
        old, nowt = json.loads(PENDING.read_text()), time.time()
        keep = []
        for x in old:                                      # 6-Nov: never deliver a stale CALL (> 30 min after it was made)
            m_, t_ = (x.get("m"), x.get("t", nowt)) if isinstance(x, dict) else (x, nowt)
            if nowt - t_ > STALE_SEC and _is_call(m_):
                stale += 1; continue
            keep.append(m_)
        msgs = keep + msgs + ([f"⚠️ {stale} call alert(s) could not be delivered in time and were dropped (stale – do not act on old levels)."]
                              if stale else [])
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
        PENDING.write_text(json.dumps([dict(m=m, t=time.time()) for m in failed]))
        print(f"::warning::{len(failed)} message(s) kept for the next run")
    _delivery_note(len(msgs) - len(failed), len(failed), stale)
    return 1 if failed else 0


STALE_SEC = 30 * 60


def _is_call(m):
    t = str(m)
    return ("Entry   :" in t or "Entry  :" in t) and ("SL      :" in t or "Stop-loss" in t)


def _delivery_note(sent, failed, stale):
    """Per-day Telegram delivery counts (read by the signal-funnel summary): sent / failed / stale calls dropped."""
    p = PENDING.parent / "delivery.json"
    try:
        d = json.loads(p.read_text())
    except Exception:
        d = {}
    day = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 19800))
    e = d.setdefault(day, dict(sent=0, failed=0, stale_dropped=0))
    e["sent"] += sent; e["failed"] += failed; e["stale_dropped"] += stale
    for k in sorted(d)[:-10]:
        d.pop(k, None)
    try:
        p.write_text(json.dumps(d))
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(flush() if (sys.argv[1:] or ["scan"])[0] == "flush" else scan())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(); sys.exit(2)
