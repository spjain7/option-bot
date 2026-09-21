"""
⚡ OI / VOLUME ACTIVITY ALERTS  (part of the option-selling engine - never uses RSI)

Every run (15 min) we snapshot price, OI and volume of near-month FUTURES:
index (NIFTY, BANKNIFTY, SENSEX), ALL F&O stocks, and MCX commodities.
Compared with ~1 hour ago:
    price ↑ + OI ↑ = LONG BUILDUP   (fresh buying)      -> PE-sell side
    price ↓ + OI ↑ = SHORT BUILDUP  (fresh selling)     -> CE-sell side
    price ↑ + OI ↓ = SHORT COVERING (sellers exiting)   -> up-move may fade
    price ↓ + OI ↓ = LONG UNWINDING (buyers exiting)    -> down-move may fade
Only alerted when volume also spikes (>= 2x the day's normal pace).
Also produces today's strongest stock futures for the monthly stock scan (MONTHLY_STOCKS = "AUTO").
"""
import pandas as pd
import config as C
import market as M
import strategy as S
import notify
from angel import now_ist

LABEL = {  # (price up?, oi up?) -> text
    (True, True): ("🟢", "LONG BUILDUP", "fresh buying", "BULLISH"),
    (False, True): ("🔴", "SHORT BUILDUP", "fresh selling", "BEARISH"),
    (True, False): ("🟡", "SHORT COVERING", "sellers exiting – up-move may fade", None),
    (False, False): ("🟠", "LONG UNWINDING", "buyers exiting – down-move may fade", None),
}
OPEN = {"NFO": ("09:15", "15:30"), "BFO": ("09:15", "15:30"), "MCX": ("09:00", "23:30")}


def _t(s):
    h, m = map(int, s.split(":"))
    return now_ist().normalize() + pd.Timedelta(hours=h, minutes=m)


def universe(master):
    """Near-month future for every index / F&O stock / MCX commodity we follow."""
    today = now_ist().normalize()
    fut = master[master["instrumenttype"].isin(["FUTIDX", "FUTSTK", "FUTCOM"]) & (master["expiry_dt"] >= today)]
    out = []
    for (ex, name), g in fut.groupby(["exch_seg", "name"]):
        if ex == "MCX" and name not in set(C.MCX_UNDERLYINGS) | set(C.RSI_MCX):
            continue
        if ex in ("NFO", "BFO") and g["instrumenttype"].iloc[0] == "FUTIDX" and name not in C.INDEX_TOKENS:
            continue
        g = g.sort_values("expiry_dt")
        row = g.iloc[0]
        if (row["expiry_dt"] - today).days < 2 and len(g) > 1:          # roll near expiry
            row = g.iloc[1]
        kind = "mcx" if ex == "MCX" else ("index" if name in C.INDEX_TOKENS else "stock")
        out.append({"name": name, "exch": ex, "token": str(row["token"]), "kind": kind})
    return out


def run(bot, nse_on, mcx_on):
    st, now = bot.st.s, now_ist()
    snaps = st.setdefault("snap", {})
    last_alert = st.setdefault("flow_last", {})
    day = f"{now:%Y-%m-%d}"
    live = [u for u in universe(bot.master)
            if (u["exch"] == "MCX" and mcx_on or u["exch"] != "MCX" and nse_on)
            and _t(OPEN[u["exch"]][0]) <= now <= _t(OPEN[u["exch"]][1])]
    if not live:
        return
    by_ex = {}
    for u in live:
        by_ex.setdefault(u["exch"], []).append(u["token"])
    qs = bot.api.quotes(by_ex)

    events, big = [], []
    for u in live:
        q = qs.get(u["token"])
        if not q or not q.get("ltp"):
            continue
        ltp, oi, vol = float(q["ltp"]), float(q.get("opnInterest") or 0), float(q.get("tradeVolume") or 0)
        rec = snaps.setdefault(u["token"], {"name": u["name"], "hist": [], "prev_oi": None, "day": day})
        if rec["day"] != day:                                   # new day: remember yesterday's last OI
            rec["prev_oi"] = rec["hist"][-1][2] if rec["hist"] else None
            rec["hist"], rec["day"] = [], day
        rec["hist"].append([str(now), ltp, oi, vol, float(q.get("high") or ltp), float(q.get("low") or ltp)])
        rec["hist"] = rec["hist"][-12:]
        rec["pchg"] = float(q.get("percentChange") or 0)
        rec["oi_day"] = (oi / rec["prev_oi"] - 1) * 100 if rec.get("prev_oi") else None
        rec["kind"], rec["exch"], rec["ltp"] = u["kind"], u["exch"], ltp

        if C.BIGMOVE_ENABLED:
            bm = big_move(u, rec, now, ltp, oi, vol)
            if bm:
                big.append(bm)

        # compare with the snapshot taken >= 45 min ago (today)
        ref = [h for h in rec["hist"][:-1] if now - pd.Timestamp(h[0]) >= pd.Timedelta(minutes=45)]
        if not ref or not ref[-1][2] or not ref[-1][1]:
            continue
        r = ref[-1]
        mins = (now - pd.Timestamp(r[0])).total_seconds() / 60
        dpx = (ltp / r[1] - 1) * 100
        doi = (oi / r[2] - 1) * 100
        session_min = max((now - _t(OPEN[u["exch"]][0])).total_seconds() / 60, mins)
        normal = vol / session_min * mins                       # day's average pace for this many minutes
        spike = (vol - r[3]) / normal if normal > 0 else 0
        k = u["kind"]
        if spike < C.FLOW_VOL_SPIKE_X or abs(doi) < C.FLOW_MIN_OI_CHG[k] or abs(dpx) < C.FLOW_MIN_PX_CHG[k]:
            continue
        la = last_alert.get(u["token"])
        if la and now - pd.Timestamp(la) < pd.Timedelta(minutes=C.FLOW_COOLDOWN_MIN):
            continue
        icon, label, meaning, bias = LABEL[(dpx > 0, doi > 0)]
        events.append({**u, "ltp": ltp, "dpx": dpx, "doi": doi, "spike": spike, "icon": icon, "label": label,
                       "meaning": meaning, "bias": bias, "score": spike * abs(doi)})

    if big:
        send_big(bot, big, now)
    if not events:
        return
    events.sort(key=lambda e: e["score"], reverse=True)
    events = events[:C.FLOW_MAX_PER_MSG]
    ideas = 0
    L = [f"⚡ *OI / VOLUME ALERT* – {now:%d %b %H:%M}", ""]
    for e in events:
        last_alert[e["token"]] = str(now)
        L.append(f"{e['icon']} *{e['name']}* fut {e['ltp']:,.1f} ({e['dpx']:+.2f}% in 1h) | OI {e['doi']:+.1f}% | "
                 f"Volume {e['spike']:.1f}x\n    → *{e['label']}* ({e['meaning']})")
        if e["bias"] and ideas < C.FLOW_STRIKE_IDEAS:
            idea = strike_idea(bot, e)
            if idea:
                ideas += 1
                L.append(f"    💡 Nearest safe strike to sell: {idea}")
    L += ["", "📖 _Buildup = new positions (stronger move). Covering / unwinding = old positions closing (weaker move)._",
          "_Info only – tracked SELL calls with SL/target come separately._"]
    notify.send("\n".join(L))


def strike_idea(bot, e):
    """Nearest strike still outside SAFE_EM_DISTANCE x expected move (most decay without high gamma)."""
    try:
        ex, name = e["exch"], e["name"]
        min_dte = C.MCX_MIN_DTE if ex == "MCX" else (2 if e["kind"] == "stock" else 0)
        exps = [x for x in M.expiries(bot.master, name, ex) if M.dte(x) >= min_dte]
        if not exps:
            return None
        rng = 0.25 if ex == "MCX" else (0.15 if e["kind"] == "stock" else 0.06)
        ch = M.build_chain(bot.api, bot.master, name, exps[0], e["ltp"], rng, ex)
        if not ch:
            return None
        typ = "PE" if e["bias"] == "BULLISH" else "CE"
        min_oi = C.MCX_MIN_SHORT_OI if ex == "MCX" else C.MIN_SHORT_OI
        o = S.pick_nearest_safe(ch["df"], typ, C.DELTA_BAND["intraday"], ch["F"], ch.get("exp_move"), min_oi,
                                M.dte(exps[0]))
        if o is None:
            return None
        return (f"{name} {S.k_(o['K'])} {typ} @ ₹{o['mid']:.1f} (Δ {abs(o['delta']):.2f}, exp {pd.Timestamp(exps[0]):%d %b}, "
                f"≈ ₹{-o['theta'] * ch['lot']:,.0f}/lot/day decay)")
    except Exception as ex_:
        print("idea error", ex_)
        return None


def stock_picks(bot):
    """Strongest F&O stock futures today (for the monthly stock scan)."""
    rows = []
    for tok, r in bot.st.s.get("snap", {}).items():
        if r.get("kind") != "stock" or r.get("day") != f"{now_ist():%Y-%m-%d}":
            continue
        p, oid = r.get("pchg") or 0, r.get("oi_day")
        if abs(p) < 1.0:
            continue
        if oid is not None and oid < 2:                        # need fresh positions when we know OI
            continue
        rows.append((abs(p) * (1 + max(oid or 0, 0) / 5), r["name"]))
    rows.sort(reverse=True)
    return [n for _, n in rows[:C.AUTO_STOCK_PICKS]]


# ─────────────── OI status (used in views, calls, report) ───────────────
def _lab(px, oi):
    icon, label, _, _ = LABEL[(px > 0, oi > 0)]
    return f"{icon} {label.capitalize()}"


def status(st, token):
    """{'day': text or None, 'hour': text or None} from stored futures snapshots."""
    rec = st.get("snap", {}).get(str(token))
    out = {"day": None, "hour": None}
    if not rec or not rec.get("hist"):
        return out
    h = rec["hist"]
    last = h[-1]
    if rec.get("prev_oi"):
        oi_d = (last[2] / rec["prev_oi"] - 1) * 100
        out["day"] = f"{_lab(rec.get('pchg', 0), oi_d)} (price {rec.get('pchg', 0):+.1f}%, OI {oi_d:+.1f}%)"
    elif len(h) >= 2 and h[0][2]:
        px, oi_d = (last[1] / h[0][1] - 1) * 100, (last[2] / h[0][2] - 1) * 100
        out["day"] = f"{_lab(px, oi_d)} since {pd.Timestamp(h[0][0]):%H:%M} (price {px:+.1f}%, OI {oi_d:+.1f}%)"
    now = pd.Timestamp(last[0])
    ref = [x for x in h[:-1] if now - pd.Timestamp(x[0]) >= pd.Timedelta(minutes=45)]
    if ref and ref[-1][2]:
        px, oi_d = (last[1] / ref[-1][1] - 1) * 100, (last[2] / ref[-1][2] - 1) * 100
        out["hour"] = f"{_lab(px, oi_d)} ({px:+.1f}%, OI {oi_d:+.1f}%)"
    return out


def buildup_dict(st, token):
    """Same shape as market.futures_buildup(), built from snapshots (works for MCX too)."""
    rec = st.get("snap", {}).get(str(token))
    if not rec or not rec.get("hist"):
        return None
    last, h = rec["hist"][-1], rec["hist"]
    if rec.get("prev_oi"):
        px, oi_d = rec.get("pchg", 0), (last[2] / rec["prev_oi"] - 1) * 100
    elif len(h) >= 2 and h[0][2]:
        px, oi_d = (last[1] / h[0][1] - 1) * 100, (last[2] / h[0][2] - 1) * 100
    else:
        return None
    label = {(True, True): "Long buildup", (False, True): "Short buildup",
             (True, False): "Short covering", (False, False): "Long unwinding"}[(px >= 0, oi_d >= 0)]
    score = {"Long buildup": 1, "Short buildup": -1, "Short covering": 0.5, "Long unwinding": -0.5}[label]
    return {"label": label, "score": score, "px_chg": round(px, 2), "oi_chg": round(oi_d, 2)}


# ─────────────── 🚨 big-move early warning ───────────────
def big_move(u, rec, now, ltp, oi, vol):
    h = rec["hist"]
    prev = [x for x in h[:-1] if pd.Timedelta(minutes=10) <= now - pd.Timestamp(x[0]) <= pd.Timedelta(minutes=35)]
    if not prev:
        return None
    p = prev[-1]
    if len(p) < 6 or not p[1]:
        return None
    mins = (now - pd.Timestamp(p[0])).total_seconds() / 60
    d = (ltp / p[1] - 1) * 100
    session_min = max((now - _t(OPEN[u["exch"]][0])).total_seconds() / 60, mins)
    normal = vol / session_min * mins
    spike = (vol - p[3]) / normal if normal > 0 else 0
    doi = (oi / p[2] - 1) * 100 if p[2] else 0
    kind = None
    if abs(d) >= C.FAST_MOVE_PCT[u["kind"]]:
        kind = "FAST RISE" if d > 0 else "FAST FALL"
    elif ltp > p[4] and spike >= C.BREAKOUT_VOL_X and doi > 0:
        kind = "BREAKOUT"
    elif ltp < p[5] and spike >= C.BREAKOUT_VOL_X and doi > 0:
        kind = "BREAKDOWN"
    if not kind:
        return None
    return {**u, "ltp": ltp, "d": d, "mins": mins, "spike": spike, "doi": doi, "move": kind,
            "hi": p[4], "lo": p[5]}


def send_big(bot, big, now):
    last = bot.st.s.setdefault("big_last", {})
    big = [b for b in big if not (last.get(b["token"]) and
                                  now - pd.Timestamp(last[b["token"]]) < pd.Timedelta(minutes=C.BIGMOVE_COOLDOWN_MIN))]
    if not big:
        return
    big.sort(key=lambda b: abs(b["d"]) * max(b["spike"], 1), reverse=True)
    L = [f"🚨 *BIG MOVE ALERT* – {now:%d %b %H:%M}", ""]
    for b in big[:C.FLOW_MAX_PER_MSG]:
        last[b["token"]] = str(now)
        up = b["move"] in ("FAST RISE", "BREAKOUT")
        icon = "🚀" if up else "🔻"
        what = {"FAST RISE": f"jumped {b['d']:+.2f}% in {b['mins']:.0f} min",
                "FAST FALL": f"fell {b['d']:+.2f}% in {b['mins']:.0f} min",
                "BREAKOUT": f"broke day high {b['hi']:,.1f} with {b['spike']:.1f}x volume & fresh OI",
                "BREAKDOWN": f"broke day low {b['lo']:,.1f} with {b['spike']:.1f}x volume & fresh OI"}[b["move"]]
        st = status(bot.st.s, b["token"])
        L.append(f"{icon} *{b['name']}* {b['ltp']:,.1f} – {what}")
        if st["hour"]:
            L.append(f"    OI last 1h: {st['hour']}")
        for p in bot.st.s.get("positions", []):
            if p["name"] != b["name"] or len(p["legs"]) != 1:
                continue
            l = p["legs"][0]
            if (l["typ"] == "CE" and up) or (l["typ"] == "PE" and not up):
                L.append(f"    ⚠️ Your open SELL #{p['id']} {p['name']} {S.k_(l['K'])} {l['typ']} is at risk – "
                         f"keep SL ₹{p['sl_val']} ready")
    L += ["", "📖 _Nobody can predict big moves. This flags one as it STARTS – moves can continue or reverse._"]
    notify.send("\n".join(L))
