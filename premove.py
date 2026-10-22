"""
👀 PRE-MOVE WATCH  (part of the OI/volume flow; information only, never a trade call)

Nobody can predict a move. What CAN be seen before many moves is "coiling": price stays unusually quiet for an hour
while open interest keeps rising and volume picks up, i.e. new positions are being built and one side will have to give.
If that happens near the day's high or low, the alert says which break to watch.

Uses only the 15-minute futures snapshots flow.py already takes (no extra API calls). Missing OI or volume = no alert.

Honesty check built in: every watch alert is tracked for 2 hours ("did a big move follow?"), and for each alert a
random instrument of the same kind is tracked the same way as a control. The daily report shows both hit rates, so
we can see whether these alerts beat chance before relying on them.
"""
import random
import pandas as pd
import config as C
import notify
import strategy as S

TS = pd.Timestamp


def coil(rec, now, kind, session_start):
    """Quiet-price + rising-OI + rising-volume check on the last hour of snapshots. Returns details or None. Pure."""
    h = [x for x in rec.get("hist", []) if now - TS(x[0]) <= pd.Timedelta(minutes=C.PREMOVE_WINDOW_MIN + 5)]
    if len(h) < 4 or len(h[0]) < 6 or now - TS(h[0][0]) < pd.Timedelta(minutes=C.PREMOVE_WINDOW_MIN - 20):
        return None
    px = [x[1] for x in h]
    ltp, lo, hi = px[-1], min(px), max(px)
    if not ltp or not h[0][2] or not h[-1][2] or not h[-1][3]:          # no OI or no volume -> no alert (never guessed)
        return None
    rng = (hi - lo) / ltp * 100
    doi = (h[-1][2] / h[0][2] - 1) * 100
    mins = (TS(h[-1][0]) - TS(h[0][0])).total_seconds() / 60
    session_min = max((now - session_start).total_seconds() / 60, mins)
    pace = h[-1][3] / session_min * mins                                # the day's average volume for this many minutes
    spike = (h[-1][3] - h[0][3]) / pace if pace > 0 else 0
    if rng > C.PREMOVE_MAX_RANGE[kind] or doi < C.PREMOVE_MIN_OI[kind] or spike < C.PREMOVE_VOL_X:
        return None
    dhi, dlo = h[-1][4], h[-1][5]
    pos = (ltp - dlo) / (dhi - dlo) if dhi > dlo else 0.5
    side = "UP" if pos >= 0.75 else "DOWN" if pos <= 0.25 else None
    return {"ltp": ltp, "range": rng, "doi": doi, "spike": spike, "mins": mins, "hi": hi, "lo": lo,
            "day_hi": dhi, "day_lo": dlo, "side": side}


def moved(rec, item, now):
    """Did price move >= the big-move size from the alert price within the tracking window? True / False / None (open)."""
    t0, end = TS(item["t"]), TS(item["t"]) + pd.Timedelta(minutes=C.PREMOVE_TRACK_MIN)
    after = [x for x in rec.get("hist", []) if t0 < TS(x[0]) <= end] if rec else []
    size = C.FAST_MOVE_PCT[item["kind"]] * C.PREMOVE_MOVE_X
    if any(abs(x[1] / item["px"] - 1) * 100 >= size for x in after):
        return True
    if now >= end:
        return False if after else None                                # no data at all = not counted
    return None


def track(st, snaps, now):
    """Resolve open watch/control items; returns the stats dict."""
    pm = st.setdefault("premove", {"open": [], "stats": {"watch": [0, 0], "control": [0, 0]}, "last": {}})
    keep = []
    for it in pm["open"]:
        r = moved(snaps.get(it["token"]), it, now)
        if r is None and now < TS(it["t"]) + pd.Timedelta(minutes=C.PREMOVE_TRACK_MIN):
            keep.append(it)
        elif r is not None:
            pm["stats"][it["group"]][0] += 1
            pm["stats"][it["group"]][1] += int(r)
    pm["open"] = keep
    return pm


def rate(pm, group):
    n, hit = pm["stats"][group]
    return (hit / n * 100 if n else None), n


def summary_line(st):
    pm = st.get("premove")
    if not pm:
        return None
    (w, nw), (c, nc) = rate(pm, "watch"), rate(pm, "control")
    if not nw:
        return "👀 Pre-move watch: no alerts tracked yet."
    return (f"👀 Pre-move watch so far: {nw} alerts, {w:.0f}% followed by a big move within "
            f"{C.PREMOVE_TRACK_MIN // 60} h, vs {c:.0f}% for random scripts ({nc} tracked)" if nc else
            f"👀 Pre-move watch so far: {nw} alerts, {w:.0f}% followed by a big move (no control yet)")


def run(bot, live, now, session_start_of):
    """live: flow universe items with fresh snapshots. Sends one message with new watch alerts."""
    st = bot.st.s
    snaps = st.get("snap", {})
    pm = track(st, snaps, now)
    found = []
    for u in live:
        rec = snaps.get(u["token"])
        if not rec:
            continue
        last = pm["last"].get(u["token"])
        if last and now - TS(last) < pd.Timedelta(minutes=C.PREMOVE_COOLDOWN_MIN):
            continue
        c = coil(rec, now, u["kind"], session_start_of(u["exch"]))
        if c:
            found.append({**u, **c})
    if not found:
        return
    found.sort(key=lambda f: f["doi"] * f["spike"], reverse=True)
    found = found[:C.PREMOVE_MAX_PER_MSG]
    # matched random controls: same kind, not alerted, with enough snapshots
    pool = [u for u in live if u["token"] not in {f["token"] for f in found} and len(snaps.get(u["token"], {}).get("hist", [])) >= 4]
    for f in found:
        pm["last"][f["token"]] = str(now)
        pm["open"].append({"token": f["token"], "kind": f["kind"], "t": str(now), "px": f["ltp"], "group": "watch"})
        same = [u for u in pool if u["kind"] == f["kind"]]
        if same:
            u = random.choice(same); pool.remove(u)
            pm["open"].append({"token": u["token"], "kind": u["kind"], "t": str(now), "px": snaps[u["token"]]["hist"][-1][1], "group": "control"})
    w, nw = rate(pm, "watch")
    c, nc = rate(pm, "control")
    L = [f"👀 *PRE-MOVE WATCH* – {now:%d %b %H:%M}", ""]
    for f in found:
        where = {"UP": "near the day high", "DOWN": "near the day low", None: "mid-range"}[f["side"]]
        L.append(f"🔍 *{f['name']}* fut {f['ltp']:,.1f} – quiet for {f['mins']:.0f} min (range {f['range']:.2f}%) while "
                 f"OI {f['doi']:+.1f}% and volume {f['spike']:.1f}× → positions building, {where}")
        L.append(f"    Watch: above {f['hi']:,.1f} = possible up-move | below {f['lo']:,.1f} = possible down-move")
        for p in st.get("positions", []):
            if p["name"] == f["name"] and len(p["legs"]) == 1:
                l = p["legs"][0]
                L.append(f"    ⚠️ Your open SELL #{p['id']} {S.k_(l['K'])} {l['typ']} – a sharp move may come; keep SL ₹{p['sl_val']} ready")
    track_txt = (f"So far {w:.0f}% of these were followed by a big move within {C.PREMOVE_TRACK_MIN // 60} h, "
                 f"vs {c:.0f}% for random scripts." if nw >= C.PREMOVE_MIN_SAMPLE and nc else "Hit rate is still being measured.")
    L += ["", f"📖 _Early warning, not a call: the move can go either way, or not come at all. {track_txt}_"]
    notify.send("\n".join(L))
