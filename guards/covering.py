"""🔄 SHORT-COVERING / LONG-UNWINDING alert (information only, part of the OI/volume flow; no extra API calls).

Short covering: price has climbed well off the day's low while open interest FALLS (sellers buying back, not fresh
buying). Long unwinding: the mirror (price well off the day's high while OI falls). These moves can be sharp but often
fade once the covering ends; the alert also warns about open SELL positions on that side.
"""
import pandas as pd
import config as C
import notify
import strategy as S

TS = pd.Timestamp


def detect(rec, kind, now):
    """rec: flow snapshot record (hist rows: [time, ltp, oi, vol, day_high, day_low]). Returns dict or None. Pure."""
    h = rec.get("hist", [])
    if len(h) < 2 or len(h[-1]) < 6:
        return None
    last = h[-1]
    ref = [x for x in h[:-1] if now - TS(x[0]) >= pd.Timedelta(minutes=40)]
    if not ref:
        return None
    r = ref[-1]
    ltp, oi, dhi, dlo = last[1], last[2], last[4], last[5]
    if not (ltp and oi and r[2] and dlo and dhi):
        return None
    doi = (oi / r[2] - 1) * 100
    dpx = (ltp / r[1] - 1) * 100
    if doi > -C.COVERING_MIN_OI_DROP[kind]:
        return None
    up = (ltp / dlo - 1) * 100
    down = (1 - ltp / dhi) * 100
    if dpx > 0 and up >= C.COVERING_MIN_MOVE[kind]:
        return {"type": "SHORT COVERING", "ltp": ltp, "from": dlo, "pts": ltp - dlo, "pct": up, "doi": doi,
                "oi_day": rec.get("oi_day"), "up": True}
    if dpx < 0 and down >= C.COVERING_MIN_MOVE[kind]:
        return {"type": "LONG UNWINDING", "ltp": ltp, "from": dhi, "pts": dhi - ltp, "pct": down, "doi": doi,
                "oi_day": rec.get("oi_day"), "up": False}
    return None


def run(bot, live, now):
    st = bot.st.s
    snaps, last = st.get("snap", {}), st.setdefault("covering_last", {})
    out = []
    for u in live:
        rec = snaps.get(u["token"])
        if not rec:
            continue
        la = last.get(u["token"])
        if la and now - TS(la) < pd.Timedelta(minutes=C.COVERING_COOLDOWN_MIN):
            continue
        d = detect(rec, u["kind"], now)
        if d:
            last[u["token"]] = str(now)
            out.append({**u, **d})
    if not out:
        return
    L = []
    for e in sorted(out, key=lambda x: x["pct"], reverse=True)[:C.FLOW_MAX_PER_MSG]:
        word = "up" if e["up"] else "down"
        side = "today's low" if e["up"] else "today's high"
        L += [f"🔄 {e['type']} • {e['name']} fut {e['ltp']:,.1f}",
              f"{'Up' if e['up'] else 'Down'} {e['pts']:,.1f} ({e['pct']:.1f}%) from {side} {e['from']:,.1f}",
              f"OI {e['doi']:+.1f}% in 1 hour" + (f", {e['oi_day']:+.1f}% today" if e.get("oi_day") is not None else "")
              + (" → sellers buying back, not fresh buying" if e["up"] else " → buyers exiting, not fresh selling")]
        for p in st.get("positions", []):
            if p["name"] != e["name"] or len(p["legs"]) != 1:
                continue
            l = p["legs"][0]
            if (l["typ"] == "CE") == e["up"]:
                L.append(f"⚠️ Your open SELL #{p['id']} {S.k_(l['K'])} {l['typ']} is on the wrong side – keep SL ₹{p['sl_val']} ready")
        L.append("")
    L.append(f"📖 Moves on covering/unwinding can be sharp but often fade. Information only – not a call.")
    notify.send("\n".join(L))
