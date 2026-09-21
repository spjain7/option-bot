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

    events = []
    for u in live:
        q = qs.get(u["token"])
        if not q or not q.get("ltp"):
            continue
        ltp, oi, vol = float(q["ltp"]), float(q.get("opnInterest") or 0), float(q.get("tradeVolume") or 0)
        rec = snaps.setdefault(u["token"], {"name": u["name"], "hist": [], "prev_oi": None, "day": day})
        if rec["day"] != day:                                   # new day: remember yesterday's last OI
            rec["prev_oi"] = rec["hist"][-1][2] if rec["hist"] else None
            rec["hist"], rec["day"] = [], day
        rec["hist"].append([str(now), ltp, oi, vol])
        rec["hist"] = rec["hist"][-12:]
        rec["pchg"] = float(q.get("percentChange") or 0)
        rec["oi_day"] = (oi / rec["prev_oi"] - 1) * 100 if rec.get("prev_oi") else None
        rec["kind"], rec["exch"], rec["ltp"] = u["kind"], u["exch"], ltp

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
