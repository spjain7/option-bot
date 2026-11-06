"""Signal funnel (6-Nov-2026, owner mission: "explain exactly why a call was generated or rejected").

For every rule and day: how many raw signals fired, how many were REJECTED (and by which filter), how many were only LOGGED
(registry shadow) and how many were SENT – plus data failures (no candles / scan paused) that may have hidden signals.
Each signal is counted once per instrument + candle (the engine re-checks every 15 minutes). Stored in the alert state
under "funnel" (last 10 days) and summarised in one message after the MCX close.
"""
import pandas as pd

KEEP_DAYS = 10


def _day(state, now=None):
    d = (state.get("day") or {}).get("date") or (str(pd.Timestamp(now).date()) if now is not None else None)
    root = state.setdefault("funnel", {})
    for k in sorted(root)[:-KEEP_DAYS]:
        root.pop(k, None)
    return root.setdefault(d or "unknown", {})


def note(state, rule, stage, reason=None, key=None, now=None):
    """stage: 'signal' | 'rejected' | 'shadow' | 'sent' | 'data'. key (instrument|candle) de-duplicates repeated checks."""
    day = _day(state, now)
    r = day.setdefault(rule, dict(signal=0, rejected={}, shadow=0, sent=0, data=0, keys=[]))
    if key is not None:
        kk = f"{stage}|{key}"
        if kk in r["keys"]:
            return
        r["keys"] = (r["keys"] + [kk])[-400:]
    if stage == "rejected":
        why = (reason or "unknown")[:60]
        r["rejected"][why] = r["rejected"].get(why, 0) + 1
    elif stage in r:
        r[stage] += 1


def classify(text):
    """Breakout engine info string -> (stage, reason)."""
    t = text or ""
    if "logged only" in t:
        return "shadow", None
    for tag in ("skipped:", "not sent:", "rejected by grade:"):
        if tag in t:
            return "rejected", t.split(tag, 1)[1].strip()
    if "already" in t:
        return "rejected", "already in an open call"
    return None, None


def summary(state, date=None):
    root = state.get("funnel") or {}
    if not root:
        return None
    d = date or sorted(root)[-1]
    day = root.get(d) or {}
    if not day:
        return None
    L = [f"🔎 SIGNAL FUNNEL – {d}", "rule · signals → sent / logged-only / rejected (top reasons)"]
    tot = dict(signal=0, sent=0, shadow=0, rej=0, data=0)
    for rule in sorted(day):
        r = day[rule]
        rej = sum(r["rejected"].values())
        tot["signal"] += r["signal"]; tot["sent"] += r["sent"]; tot["shadow"] += r["shadow"]; tot["rej"] += rej; tot["data"] += r["data"]
        if not (r["signal"] or r["data"]):
            continue
        top = sorted(r["rejected"].items(), key=lambda x: -x[1])[:3]
        L.append(f"• {rule}: {r['signal']} → {r['sent']} sent / {r['shadow']} logged / {rej} rejected"
                 + (f" ({'; '.join(f'{k} ×{v}' for k, v in top)})" if top else "")
                 + (f" · ⚠️ {r['data']} data failures" if r["data"] else ""))
    L.insert(2, f"TOTAL: {tot['signal']} signals → {tot['sent']} sent · {tot['shadow']} logged only · {tot['rej']} rejected"
                + (f" · {tot['data']} data failures" if tot["data"] else ""))
    return "\n".join(L)
