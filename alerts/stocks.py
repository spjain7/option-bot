"""Stock-futures VOLUME BREAKOUT alerts (NSE F&O stocks with lot size < 3000). Alert only – no orders.

Same rule as alerts/breakout.py on 3-hour (09:15-12:15, 12:15-15:30) and daily candles. To stay inside Angel's
rate limits the full stock list is scanned only right after an NSE 3-hour block closes (≈12:17 and ≈15:32 IST);
open stock alerts are checked against live prices every scan.
NOTE: the rule was validated on MCX commodities + NIFTY/BANKNIFTY (research/search). Stock futures are being
backtested separately (research/search/stock_check.py) – messages say so until that is done.
"""
import time
import pandas as pd
from alerts import breakout as BO, signals as S
from crude import data as CD

MAX_LOT = 3000
TAG = "📌 Stock futures: same rule, separate backtest pending"


def universe(master, now):
    m = master[(master["exch_seg"] == "NFO") & (master["instrumenttype"] == "FUTSTK") & (master["expiry_dt"] >= now.normalize())
               & (master["lotsize"] < MAX_LOT)].sort_values("expiry_dt")
    out = {}
    for r in m.itertuples():
        if r.name in out:
            continue
        if CD.trading_days_between(now.normalize(), r.expiry_dt) <= 2:      # too close to expiry -> next month
            continue
        out[r.name] = dict(symbol=r.symbol, token=str(r.token), expiry=str(r.expiry_dt.date()), lot=int(r.lotsize))
    return out


def last_block_end(now):
    """End time of the most recent COMPLETED NSE 3-hour block today (None before 12:15)."""
    if now.weekday() >= 5:
        return None
    a, b = CD.hm(now, "12:15"), CD.hm(now, "15:30")
    return str(b) if now >= b + pd.Timedelta(minutes=1) else str(a) if now >= a + pd.Timedelta(minutes=1) else None


def nfo_expiry(y, m):
    last = pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)
    wd = 3 if pd.Timestamp(y, m, 1) < pd.Timestamp("2025-09-01") else 1        # Thursday, Tuesday from Sep-2025
    while last.weekday() != wd:
        last -= pd.Timedelta(days=1)
    return last


def first_session_after_expiry(day):
    """Stock futures roll after the monthly expiry (last Tuesday from Sep-2025): the stitched series jumps there."""
    d = pd.Timestamp(day).normalize()
    for back in (0, 1):
        m = d - pd.DateOffset(months=back)
        e = nfo_expiry(m.year, m.month)
        nxt = e + pd.offsets.BDay(1)
        if d == nxt.normalize():
            return True
    return False


def scan(api, master, now, state, msgs, rep, engine):
    st = state.setdefault("stk", dict(active=[], last_block=None))
    uni = universe(master, now)
    rep["stocks"] = dict(universe=len(uni))
    # live-price stop checks for open stock alerts (cheap: one quote call)
    if st["active"] and (engine.is_open("NFO", now) or engine._just_closed("NFO", now)):
        try:
            q = api.quotes({"NFO": [p["token"] for p in st["active"]]})
        except Exception:
            q = {}
        keep = []
        for p in st["active"]:
            s = 1 if p["side"] == "BUY" else -1
            ltp = (q.get(p["token"]) or {}).get("ltp")
            if ltp and s * (ltp - p["stop"]) <= 0:
                r = s * (ltp - p["entry"]) / p["risk"]
                msgs.append(f"{'✅' if r > 0 else '❌'} EXIT – {p['name']} FUT {p['side']} ({p['tf']}) at ~{BO._f(ltp)}: "
                            f"{'trailing stop' if p['trailed'] else 'stop-loss'} hit · result {r:+.2f}R")
                state["day"].setdefault("outcomes", []).append(dict(name=p["name"], tf=p["tf"], side=p["side"], result=f"stop {r:+.2f}R"))
            else:
                keep.append(p)
        st["active"] = keep
    blk = last_block_end(now)
    if blk is None or st["last_block"] == blk:
        rep["stocks"]["scan"] = "waiting for the next NSE 3-hour block close (12:15 / 15:30)"
        return
    st["last_block"] = blk
    found = 0
    for name, c in uni.items():
        try:
            h = api.candles("NFO", c["token"], "ONE_HOUR", now - pd.Timedelta(days=400), now)
        except Exception:
            h = None
        if h is None or h.empty:
            continue
        h = engine.closed(h.sort_values("time").drop_duplicates("time").reset_index(drop=True), "NFO", 60, now)
        frames = {"3h": engine.positional_candles(h, "NFO", now)}
        dd = BO.daily_candles(h, None)
        if dd is not None and len(dd) and engine.is_open("NFO", now):
            dd = dd[dd["time"].dt.normalize() < now.normalize()]
        frames["1d"] = dd
        for tf, fr in frames.items():
            if fr is None or len(fr) < 30:
                continue
            # trailing updates for this stock's open alert
            for p in st["active"]:
                if p["name"] == name and p["tf"] == tf:
                    s_ = 1 if p["side"] == "BUY" else -1
                    new = fr[fr["time"] > pd.Timestamp(p["last_candle"])]
                    if len(new):
                        p["best"] = (max if s_ > 0 else min)([p["best"], *new["close"].tolist()])
                        p["last_candle"] = str(fr["time"].iloc[-1]); p["n"] += len(new)
                        a = float(BO.I.atr(fr, 14).iloc[-1])
                        ns = p["best"] - s_ * BO.CFG["trail_atr"] * a
                        if s_ * (ns - p["stop"]) > 0.25 * a:
                            p["stop"], p["trailed"] = round(ns, 2), True
                            msgs.append(f"🔁 TRAIL UPDATE – {name} FUT {p['side']} ({tf}) · new stop {BO._f(p['stop'])}")
            last = str(fr["time"].iloc[-1])
            k = f"STK|{name}|{tf}"
            if state["last_eval"].get(k) == last:
                continue
            state["last_eval"][k] = last
            sig = BO.evaluate(fr)
            if not sig["side"] or first_session_after_expiry(sig["candle"]):
                continue
            if any(p["name"] == name and p["tf"] == tf for p in st["active"]):
                continue
            lv = S.levels(fr, h, sig["close"], sig["atr"])
            cc = dict(symbol=c["symbol"], expiry=c["expiry"])
            msgs.append(BO.call_msg(name, "NFO", cc, tf, sig, lv) + f"\n📦 Lot size: {c['lot']}")
            msgs.append(BO.reason_msg(name, tf, sig, lv) + f"\n{TAG}")
            s_ = 1 if sig["side"] == "BUY" else -1
            st["active"].append(dict(name=name, token=c["token"], tf=tf, side=sig["side"], entry=sig["close"],
                                     stop=round(sig["close"] - s_ * BO.CFG["stop_atr"] * sig["atr"], 2),
                                     risk=BO.CFG["stop_atr"] * sig["atr"], best=sig["close"], trailed=False, n=0, last_candle=last))
            state["day"]["alerts"] += 1
            found += 1
        if hasattr(api, "api"):
            time.sleep(0.1)
    rep["stocks"].update(scan=f"scanned {len(uni)} stock futures after the {blk[11:16]} block", new_calls=found)
