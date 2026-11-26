"""26-Nov-2026 (owner: "find a permanent solution and it should inform us when any issue").
System-health notices to the owner's Telegram chat. Information only: they never create, block or change a call.

Checked after every scan (alerts/run.py):
  ANGEL     Angel refused >= 35 % of requests over the last hour (>= 30 requests), or skipped >= 100 requests in a pause
  STOCKS    a stock block (12:15 / 15:30) finished with >= 15 stocks never scanned, or is still unfinished 45 min later
  SCAN      the scan errored / returned no data 3 times in a row, or ran longer than 900 s twice in a row (timeout is 1020 s)
  WEBSOCKET live WebSocket candles not used for 3 scans in a row while a market is open (all data from Angel requests)
  PREFETCH  the pre-open history download (08:40-09:13) cached < 90 % of stocks by 09:20
Outside the scan:
  job-failed  a market-loop job failed (workflow step, `python -m alerts.health job-failed <job> <url>`)
  watchdog    no scan saved for >= 40 min during 09:20-23:50 IST (health-watchdog.yml, every 30 min)
One message when an issue starts, a reminder every 2 h while it lasts (max 4 a day per issue), one when it is resolved."""
import json
import sys
from pathlib import Path

import pandas as pd

TAG = "🛠 SYSTEM HEALTH"
OK_TAG = "✅ SYSTEM HEALTH – resolved"
REMIND_MIN, MAX_PER_DAY = 120, 4
ANGEL_SHARE, ANGEL_MIN_CALLS, ANGEL_SKIPS, ANGEL_OK_SHARE = 0.35, 30, 100, 0.15
STOCK_FAIL_MIN, BLOCK_LATE_MIN = 15, 45
SLOW_SEC = 900
PREFETCH_MIN = 0.90


def _issue(h, msgs, key, active, now, text, ok_text):
    """Open / remind / resolve one issue. h = state['health']."""
    op = h.setdefault("open", {})
    day = str(now.date())
    e = op.get(key)
    if active:
        if e is None:
            e = op[key] = dict(since=str(now), last=None, day=day, sent_today=0)
        if e.get("day") != day:
            e["day"], e["sent_today"] = day, 0
        due = e["last"] is None or (now - pd.Timestamp(e["last"])).total_seconds() >= REMIND_MIN * 60
        if due and e["sent_today"] < MAX_PER_DAY:
            first = e["last"] is None
            msgs.append(f"{TAG} – {text}" + ("" if first else f"\n(still open since {pd.Timestamp(e['since']):%d-%b %H:%M})"))
            e["last"], e["sent_today"] = str(now), e["sent_today"] + 1
        return
    if e is not None:
        if e.get("last"):                                    # only report a resolution of something we reported
            msgs.append(f"{OK_TAG} – {ok_text} ({now:%H:%M} IST)")
        op.pop(key, None)


def _angel(h, msgs, now, stats):
    ring = [r for r in h.get("api", []) if (now - pd.Timestamp(r["t"])).total_seconds() <= 3600]
    ring.append(dict(t=str(now), calls=int(stats.get("calls", 0)), refused=int(stats.get("rate_limited", 0)) + int(stats.get("failed", 0)),
                     skipped=int(stats.get("skipped", 0))))
    h["api"] = ring
    calls = sum(r["calls"] for r in ring); refused = sum(r["refused"] for r in ring); skipped = sum(r["skipped"] for r in ring)
    share = refused / calls if calls else 0.0
    bad = (calls >= ANGEL_MIN_CALLS and share >= ANGEL_SHARE) or skipped >= ANGEL_SKIPS
    last2 = ring[-2:]
    good2 = len(last2) == 2 and all((r["refused"] / r["calls"] if r["calls"] else 0) < ANGEL_OK_SHARE and r["skipped"] < 20 for r in last2)
    if "angel" in h.get("open", {}) and not bad and not good2:
        bad = True                                            # hysteresis: stay open until 2 clean scans
    _issue(h, msgs, "angel", bad, now,
           f"Angel (broker data) is refusing requests: {refused} of {calls} refused ({share:.0%}) and {skipped} skipped in the "
           "last hour. Scans may miss instruments; calls already sent are unaffected.",
           "Angel requests are going through normally again")


def _stocks(h, msgs, now, state):
    st = state.get("stk") or {}
    fun = (state.get("funnel") or {}).get(str(now.date()), {}).get("STOCK data", {})
    keys = fun.get("keys", []) or []
    for blk_t in ("12:15", "15:30"):
        blk = f"{now:%Y-%m-%d} {blk_t}:00"
        done = st.get("last_block") is not None and str(st.get("last_block")) >= blk
        seen = h.setdefault("blocks", {})
        if done and not seen.get(blk):
            seen[blk] = True
            n = sum(1 for k in keys if k.endswith(f"|{blk}"))
            if n >= STOCK_FAIL_MIN:
                msgs.append(f"{TAG} – the {blk_t} stock scan finished with {n} stocks NOT scanned (no price data from Angel). "
                            "Setups on those stocks could not be checked in this block.")
        late = (not done and now >= pd.Timestamp(blk) + pd.Timedelta(minutes=BLOCK_LATE_MIN)
                and now < pd.Timestamp(blk) + pd.Timedelta(hours=3))
        _issue(h, msgs, f"block{blk_t}", late, now,
               f"the {blk_t} stock scan is still not finished {BLOCK_LATE_MIN}+ min later (rate limits / slow data). It keeps "
               "retrying every 15 min.", f"the {blk_t} stock scan has finished")
    h["blocks"] = {k: v for k, v in h.get("blocks", {}).items() if k[:10] == str(now.date())}


def _scan(h, msgs, now, rec):
    bad_run = rec.get("status") == "NO_DATA" or rec.get("errors", 0) > 0
    h["bad_runs"] = h.get("bad_runs", 0) + 1 if bad_run else 0
    h["slow_runs"] = h.get("slow_runs", 0) + 1 if rec.get("seconds", 0) > SLOW_SEC else 0
    _issue(h, msgs, "scan_err", h["bad_runs"] >= 3, now,
           f"the last {h['bad_runs']} scans ended with errors / no data (latest: {rec.get('status')} · {rec.get('note')}).",
           "scans are completing without errors")
    _issue(h, msgs, "scan_slow", h["slow_runs"] >= 2, now,
           f"scans are taking {rec.get('seconds')} s (limit 1020 s) – close to being cut off. Usually Angel rate limits.",
           "scan times are back to normal")


def _ws(h, msgs, now, stats, open_now):
    if not open_now:
        return
    miss = int(stats.get("ws_hits", 0)) == 0 and int(stats.get("ws_fallback", 0)) > 0
    h["ws_miss"] = h.get("ws_miss", 0) + 1 if miss else 0
    _issue(h, msgs, "ws", h["ws_miss"] >= 3, now,
           "live WebSocket candles are not being used (feed down or failing its check) – every candle comes from Angel "
           "requests, so rate-limit misses are more likely.", "live WebSocket candles are in use again")


def _prefetch(h, msgs, now):
    p = h.get("hist_prefetch") or {}
    if p.get("day") != str(now.date()) or h.get("prefetch_checked") == str(now.date()):
        return
    if now.hour * 60 + now.minute >= 9 * 60 + 20:
        h["prefetch_checked"] = str(now.date())
        tot, n = int(p.get("total", 0)), int(p.get("cached", 0))
        if tot and n / tot < PREFETCH_MIN:
            msgs.append(f"{TAG} – the pre-open history download cached only {n} of {tot} stock series. The 12:15 / 15:30 "
                        "stock scans will need extra Angel requests and may miss stocks.")


def check(state, now, rec, stats, open_now=True):
    """Called once per scan. Returns health messages (also stored per issue in state['health'])."""
    h = state.setdefault("health", {})
    msgs = []
    for f, a in ((_angel, (h, msgs, now, stats or {})), (_stocks, (h, msgs, now, state)), (_scan, (h, msgs, now, rec or {})),
                 (_ws, (h, msgs, now, stats or {}, open_now)), (_prefetch, (h, msgs, now))):
        try:
            f(*a)
        except Exception as e:                                # health checks must never break a scan
            print(f"[health] {f.__name__} skipped: {type(e).__name__}: {e}")
    return msgs


# ── outside the scan ────────────────────────────────────────────────────────────────────────────────────────────────────
def watchdog(scan_json, mem_path, now):
    """No scan saved for >= 40 min during 09:20-23:50 IST -> notice (every 2 h at most); 'resumed' once scans are back."""
    try:
        fin = pd.Timestamp(json.loads(Path(scan_json).read_text())["finished"])
    except Exception:
        fin = None
    try:
        mem = json.loads(Path(mem_path).read_text())
    except Exception:
        mem = {}
    out = []
    hm = now.hour * 60 + now.minute
    if now.weekday() >= 5 or not (9 * 60 + 20 <= hm <= 23 * 60 + 50):
        return out, mem
    age = (now - fin).total_seconds() / 60 if fin is not None else None
    stale = age is None or age >= 40
    if stale:
        last = mem.get("alerted")
        if last is None or (now - pd.Timestamp(last)).total_seconds() >= REMIND_MIN * 60:
            out.append(f"{TAG} – NO SCAN for {('?' if age is None else f'{age:.0f}')} min (last saved scan "
                       f"{'unknown' if fin is None else f'{fin:%d-%b %H:%M}'} IST). The bot may have stopped – no calls until it "
                       "restarts. (watchdog, checks every 30 min)")
            mem["alerted"] = str(now)
    elif mem.get("alerted"):
        out.append(f"{OK_TAG} – scans are running again (last scan {fin:%H:%M} IST).")
        mem.pop("alerted", None)
    return out, mem


def _send(lines):
    import notify
    for t in lines:
        notify.send(t)


def main(argv):
    from angel import now_ist
    if argv[:1] == ["job-failed"]:
        job, url = (argv[1:] + ["?", ""])[:2]
        _send([f"{TAG} – the market-loop '{job}' job FAILED at {now_ist():%H:%M} IST. Scans may have stopped; the watchdog "
               f"re-checks every 30 min. Run log: {url}"])
        return 0
    if argv[:1] == ["watchdog"]:
        scan_json, mem_path = argv[1], argv[2]
        out, mem = watchdog(scan_json, mem_path, now_ist())
        Path(mem_path).parent.mkdir(parents=True, exist_ok=True)
        Path(mem_path).write_text(json.dumps(mem))
        print("[watchdog]", out or "ok")
        _send(out)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
