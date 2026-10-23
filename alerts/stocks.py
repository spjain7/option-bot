"""Stock-futures OI BREAKOUT alerts (NSE F&O stocks, lot size < 3000) – the only stock rule that passed a pre-registered
hold-out test (research/search/REPORT_STOCK_OI.md, STOCK-OI-001). Alert only – no orders.

Daily candles, evaluated once after the NSE close (first scan after 15:30 IST):
  BUY : close > 20-day high, volume > 1.5× 20-day average, price up AND futures OI up ≥ 2% (long buildup), close > EMA200
  SELL: close < 20-day low,  volume > 1.5×,              price down AND OI up ≥ 2% (short buildup), close < EMA200
  OI is ignored in the 3 sessions before and the 2 after a monthly expiry (rollover distorts it).
Plan: entry next session open · SL 2 ATR · 3-ATR trailing stop on daily closes · exit on expiry day or after 40 sessions.
Backtest (after costs): design +0.20R/trade, unseen hold-out +0.085R/trade, ~47% wins, ~25 alerts a month.
"""
import time
import numpy as np
import pandas as pd
from alerts import breakout as BO, signals as S
from crude import data as CD, indicators as I

ENABLED = True
MAX_LOT = 3000
CFG = dict(N=20, vol_x=1.5, oi_up=0.02, ema=200, stop_atr=2.0, trail_atr=3.0, max_days=40)
NOTE = "📚 Stock rule backtest (2022-26, after costs): design +0.20R, unseen 2024-26 +0.085R per trade, ~47% wins – modest edge."


def nfo_expiry(y, m):
    last = pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)
    wd = 3 if pd.Timestamp(y, m, 1) < pd.Timestamp("2025-09-01") else 1        # Thursday, Tuesday from Sep-2025
    while last.weekday() != wd:
        last -= pd.Timedelta(days=1)
    return last


def first_session_after_expiry(day):
    d = pd.Timestamp(day).normalize()
    for back in (0, 1):
        m = d - pd.DateOffset(months=back)
        if d == (nfo_expiry(m.year, m.month) + pd.offsets.BDay(1)).normalize():
            return True
    return False


def in_rollover_window(day):
    """3 sessions before .. 2 sessions after a monthly expiry: OI change is meaningless (positions roll)."""
    d = pd.Timestamp(day).normalize()
    for k in (-1, 0, 1):
        m = d + pd.DateOffset(months=k)
        e = nfo_expiry(m.year, m.month)
        if e - pd.offsets.BDay(3) <= d <= e + pd.offsets.BDay(2):
            return True
    return False


def universe(master, now):
    m = master[(master["exch_seg"] == "NFO") & (master["instrumenttype"] == "FUTSTK") & (master["expiry_dt"] >= now.normalize())
               & (master["lotsize"] < MAX_LOT)].sort_values("expiry_dt")
    out = {}
    for r in m.itertuples():
        if r.name in out or CD.trading_days_between(now.normalize(), r.expiry_dt) <= 2:
            continue
        out[r.name] = dict(symbol=r.symbol, token=str(r.token), expiry=str(r.expiry_dt.date()), lot=int(r.lotsize))
    return out


def last_block_end(now):
    if now.weekday() >= 5:
        return None
    a, b = CD.hm(now, "12:15"), CD.hm(now, "15:30")
    return str(b) if now >= b + pd.Timedelta(minutes=1) else str(a) if now >= a + pd.Timedelta(minutes=1) else None


def daily_with_oi(h1c, oi):
    d = BO.daily_candles(h1c, None)
    d["day"] = d["time"].dt.normalize()
    if oi is not None and len(oi):
        o = oi.copy()
        o["day"] = pd.to_datetime(o["time"]).dt.normalize()
        d = d.merge(o.groupby("day")["oi"].last().reset_index(), on="day", how="left")
    else:
        d["oi"] = np.nan
    return d


def evaluate(d):
    if d is None or len(d) < CFG["ema"] + 5:
        return dict(side=None, why="not enough daily history")
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"].astype(float)
    x = d.iloc[-1]
    hh, ll = h.shift(1).rolling(CFG["N"]).max().iloc[-1], l.shift(1).rolling(CFG["N"]).min().iloc[-1]
    va = v.rolling(20).mean().shift(1).iloc[-1]
    e = I.ema(c, CFG["ema"]).iloc[-1]
    a = float(I.atr(d, 14).iloc[-1])
    dp = c.pct_change().iloc[-1]
    doi = d["oi"].pct_change().iloc[-1] if d["oi"].notna().iloc[-2:].all() else np.nan
    out = dict(candle=str(x.time), close=float(x.close), hh=float(hh), ll=float(ll), ema200=float(e), atr=a,
               vol_x=float(x.volume / va) if va else None, dp=float(dp), doi=None if pd.isna(doi) else float(doi),
               adx=float(I.adx(d).iloc[-1]), rsi=float(I.rsi(c, 14).iloc[-1]))
    if in_rollover_window(x.time) or pd.isna(doi):
        return dict(out, side=None, why="OI change not usable (rollover window / missing)")
    vok = out["vol_x"] is not None and out["vol_x"] > CFG["vol_x"]
    if x.close > hh and vok and dp > 0 and doi >= CFG["oi_up"] and x.close > e:
        return dict(out, side="BUY")
    if x.close < ll and vok and dp < 0 and doi >= CFG["oi_up"] and x.close < e:
        return dict(out, side="SELL")
    return dict(out, side=None, why="no OI-confirmed breakout")


def reason_msg(name, sig, lv):
    s = 1 if sig["side"] == "BUY" else -1
    lvl = sig["hh"] if s > 0 else sig["ll"]
    pts = [f"{'📈' if s > 0 else '📉'} Breakout: closed {BO._f(sig['close'])}, "
           f"{'above the 20-day high (resistance)' if s > 0 else 'below the 20-day low (support)'} {BO._f(lvl)}",
           f"🔊 Volume: {sig['vol_x']:.1f}× the 20-day average – real participation",
           f"🏦 OI: {sig['doi'] * 100:+.1f}% with price {sig['dp'] * 100:+.1f}% → "
           f"{'LONG BUILDUP – fresh buyers' if s > 0 else 'SHORT BUILDUP – fresh sellers'} ✅",
           f"🧭 Trend: {'above' if s > 0 else 'below'} the 200-day EMA ({BO._f(sig['ema200'])}) – with the main trend",
           f"💪 ADX {sig['adx']:.0f} · 📊 RSI {sig['rsi']:.0f}"
           + (" ⚠️ stretched – don't chase" if (s > 0 and sig['rsi'] > 75) or (s < 0 and sig['rsi'] < 25) else "")]
    nxt = (lv["resistance"] if s > 0 else lv["support"])[:1]
    if nxt:
        pts.append(f"🧱 Next {'resistance' if s > 0 else 'support'}: {BO._f(nxt[0][0])} ({nxt[0][1]})")
    pts.append(NOTE)
    return "\n".join([f"💡 WHY THIS {sig['side']} – {name} FUT (daily)", "━━━━━━━━━━━━━━━━━━", *pts,
                      "Backtested, not guaranteed · not investment advice."])


def scan(api, master, now, state, msgs, rep, engine):
    if not ENABLED:
        rep["stocks"] = "disabled"
        return
    st = state.setdefault("stk", dict(active=[], last_block=None))
    st.setdefault("active", [])
    old = [p for p in st["active"] if "expiry" not in p]          # alerts from the withdrawn 22-Oct rule
    if old:
        st["active"] = [p for p in st["active"] if "expiry" in p]
        msgs.append(f"ℹ️ {len(old)} stock alerts from the earlier rule (22-Oct evening, partly not delivered) are no longer "
                    "tracked – ignore any of them you may have. New stock calls use the tested OI-breakout rule.")
    uni = universe(master, now)
    rep["stocks"] = dict(universe=len(uni))
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
                msgs.append(f"{'✅' if r > 0 else '❌'} EXIT – {p['name']} FUT {p['side']} at ~{BO._f(ltp)}: "
                            f"{'trailing stop' if p['trailed'] else 'stop-loss'} hit · result {r:+.2f}R")
                state["day"].setdefault("outcomes", []).append(dict(name=p["name"], tf="1d", side=p["side"], result=f"stop {r:+.2f}R"))
            else:
                keep.append(p)
        st["active"] = keep
    blk = last_block_end(now)
    if blk is None or not blk.endswith("15:30:00") or st["last_block"] == blk:
        rep["stocks"]["scan"] = "daily stock scan runs once after the 15:30 close"
        return
    st["last_block"] = blk
    found = 0
    for name, c in uni.items():
        try:
            h = api.candles("NFO", c["token"], "ONE_HOUR", now - pd.Timedelta(days=400), now)
            oi = api.oi_history("NFO", c["token"], "ONE_DAY", now - pd.Timedelta(days=60), now) if hasattr(api, "oi_history") else None
        except Exception:
            h, oi = None, None
        if h is None or h.empty:
            continue
        h = engine.closed(h.sort_values("time").drop_duplicates("time").reset_index(drop=True), "NFO", 60, now)
        d = daily_with_oi(h, oi)
        for p in [p for p in st["active"] if p["name"] == name]:
            s_ = 1 if p["side"] == "BUY" else -1
            new = d[d["time"] > pd.Timestamp(p["last_candle"])]
            if len(new):
                p["best"] = (max if s_ > 0 else min)([p["best"], *new["close"].tolist()])
                p["n"] += len(new)
                p["last_candle"] = str(d["time"].iloc[-1])
                a = float(I.atr(d, 14).iloc[-1])
                ns = p["best"] - s_ * CFG["trail_atr"] * a
                if s_ * (ns - p["stop"]) > 0.25 * a:
                    p["stop"], p["trailed"] = round(ns, 2), True
                    msgs.append(f"🔁 TRAIL UPDATE – {name} FUT {p['side']} · new stop {BO._f(p['stop'])} · "
                                f"open {s_ * (p['best'] - p['entry']) / p['risk']:+.1f}R")
            if now.normalize() >= pd.Timestamp(p["expiry"]) or p["n"] >= CFG["max_days"]:
                px = float(d["close"].iloc[-1])
                r = s_ * (px - p["entry"]) / p["risk"]
                msgs.append(f"⏹ EXIT – {name} FUT {p['side']} at ~{BO._f(px)}: "
                            f"{'expiry day – exit (or roll with the same stop)' if p['n'] < CFG['max_days'] else '40-session time exit'} · {r:+.2f}R")
                st["active"] = [x for x in st["active"] if x is not p]
        if len(d) < 30:
            continue
        last = str(d["time"].iloc[-1])
        k = f"STKOI|{name}"
        if state["last_eval"].get(k) == last:
            continue
        state["last_eval"][k] = last
        sig = evaluate(d)
        if not sig["side"] or first_session_after_expiry(sig["candle"]) or any(p["name"] == name for p in st["active"]):
            continue
        lv = S.levels(d, h, sig["close"], sig["atr"])
        cc = dict(symbol=c["symbol"], expiry=c["expiry"])
        msgs.append(BO.call_msg(name, "NFO", cc, "1d", sig, lv).replace("POSITIONAL (daily candles)", "STOCK FUTURE · daily")
                    + f"\n📦 Lot size: {c['lot']}")
        msgs.append(reason_msg(name, sig, lv))
        s_ = 1 if sig["side"] == "BUY" else -1
        st["active"].append(dict(name=name, token=c["token"], expiry=c["expiry"], side=sig["side"], entry=sig["close"],
                                 stop=round(sig["close"] - s_ * CFG["stop_atr"] * sig["atr"], 2), risk=CFG["stop_atr"] * sig["atr"],
                                 best=sig["close"], trailed=False, n=0, last_candle=last))
        state["day"]["alerts"] += 1
        found += 1
        if hasattr(api, "api"):
            time.sleep(0.1)
    rep["stocks"].update(scan=f"daily scan of {len(uni)} stock futures done", new_calls=found)
