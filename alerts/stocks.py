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
from alerts import patterns as PT, breakout as BO, signals as S, report as RP
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


def reason_msg(name, sig, lv, plan=None):
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
    return "\n".join([f"💡 {sig['side']} {name} FUT – details & reason", "━━━━━━━━━━━━━━━━━━", *(plan or []), *pts,
                      "Backtested, not guaranteed · not investment advice."])


# ── 3-hour stock calls (STOCK-PAT-001, research/search/REGISTRY_STKPAT.md): breakout, head & shoulders, double top/bottom,
#    flag on 3-hour candles (2 per session: 09:15-12:15, 12:15-15:15). Hold-out 2024-26 win rates 72-75%, 71-80% of stocks
#    positive after costs. Exits: stop 2 ATR, book 50% at T1 + stop to entry, trailing 3 ATR (3h closes), max 40 candles.
STOCK3H_ENABLED = False          # OFF: lost money once the exit-simulator bug was fixed (STOCK-PAT-001)
STOCK3H_KINDS = ("hs", "double", "flag")
NOTE3H = ("📚 Backtest 2022-26 (stock futures, 3h, after costs, book 50% at T1 + stop to entry): breakouts and patterns won "
          "~72-75% of trades in 2024-26 – not guaranteed.")


def frame3h(h):
    """3-hour candles exactly as in the research (ST.three_hour_generic); only COMPLETE 3-candle blocks."""
    from alerts import stats as STT
    d = h.copy()
    d["day"] = d["time"].dt.normalize()
    d["k"] = d.groupby("day").cumcount() // 3
    g = d.groupby(["day", "k"])
    out = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"), n=("close", "size")).reset_index(drop=True)
    out = out[out["n"] >= 2].reset_index(drop=True)
    if len(out) and out["n"].iloc[-1] < 3 and out["time"].iloc[-1].normalize() == d["day"].iloc[-1]:
        last_k = d["k"].iloc[-1]
        if last_k < 2:                                       # today's block still forming
            out = out.iloc[:-1]
    return out.drop(columns="n")


def manage3h_quotes(api, st, msgs, state):
    """Every scan during NSE hours: stop / T1 checks for open 3h stock calls from ONE quotes request."""
    act = st.get("active3h", [])
    if not act:
        return
    try:
        q = api.quotes({"NFO": [p["token"] for p in act]})
    except Exception:
        q = {}
    keep = []
    for p in act:
        s = 1 if p["side"] == "BUY" else -1
        ltp = (q.get(p["token"]) or {}).get("ltp")
        if not ltp:
            keep.append(p); continue
        if s * (ltp - p["stop"]) <= 0:
            r = s * (ltp - p["entry"]) / p["risk"]
            if p.get("t1"):
                r = 0.5 + 0.5 * r
            msgs.append(f"{'✅' if r > 0 else '❌'} EXIT – {p['name']} FUT {p['side']} (3h) at ~{BO._f(ltp)}: "
                        f"{'stop at entry (after T1)' if p.get('t1') and p['stop'] == p['entry'] else 'trailing stop' if p['trailed'] else 'stop-loss'} hit · result {r:+.2f}R")
            state["day"].setdefault("outcomes", []).append(dict(name=p["name"], tf="3h", side=p["side"], result=f"{r:+.2f}R"))
            continue
        t1 = p["entry"] + s * p["risk"]
        if not p.get("t1") and s * (ltp - t1) >= 0:
            p["t1"] = True
            p["stop"] = p["entry"]
            msgs.append(f"🎯 T1 HIT – {p['name']} FUT {p['side']} (3h) at {BO._f(t1)} · BOOK 50% now · move stop-loss to entry "
                        f"{BO._f(p['entry'])} for the rest")
        keep.append(p)
    st["active3h"] = keep


def scan3h(name, c, h, fr, now, master, st, state, msgs):
    """At a 3h close: trail / time-exit open 3h calls of this stock, then look for a new signal."""
    for p in [p for p in st.setdefault("active3h", []) if p["name"] == name]:
        s_ = 1 if p["side"] == "BUY" else -1
        new = fr[fr["time"] > pd.Timestamp(p["last_candle"])]
        if len(new):
            p["best"] = (max if s_ > 0 else min)([p["best"], *new["close"].tolist()])
            p["n"] += len(new)
            p["last_candle"] = str(fr["time"].iloc[-1])
            a = float(I.atr(fr, 14).iloc[-1])
            ns = p["best"] - s_ * CFG["trail_atr"] * a
            if s_ * (ns - p["stop"]) > 0.25 * a:
                p["stop"], p["trailed"] = round(ns, 2), True
                msgs.append(f"🔁 TRAIL UPDATE – {name} FUT {p['side']} (3h) · new stop {BO._f(p['stop'])}")
        if p["n"] >= 40 or in_rollover_window(now.normalize()):
            px = float(fr["close"].iloc[-1])
            r = s_ * (px - p["entry"]) / p["risk"]
            r = 0.5 + 0.5 * r if p.get("t1") else r
            msgs.append(f"⏹ EXIT – {name} FUT {p['side']} (3h) at ~{BO._f(px)}: "
                        f"{'time exit (40 candles)' if p['n'] >= 40 else 'rollover window – exit'} · {r:+.2f}R")
            st["active3h"] = [x for x in st["active3h"] if x is not p]
    if len(fr) < 230 or in_rollover_window(now.normalize()):
        return 0
    last = str(fr["time"].iloc[-1])
    k = f"STK3H|{name}"
    if state["last_eval"].get(k) == last:
        return 0
    state["last_eval"][k] = last
    sig = BO.evaluate(fr)
    if not sig["side"]:
        sig = PT.evaluate(fr, STOCK3H_KINDS)
    if not sig["side"] or any(p["name"] == name for p in st["active3h"]):
        return 0
    lv = S.levels(fr, h, sig["close"], sig["atr"])
    cc = dict(symbol=c["symbol"], expiry=c["expiry"])
    nxt = "" if now.hour < 14 else " · ENTRY at tomorrow's open (skip if it gaps > 0.5 ATR past this price)"
    kind = f"Stock future · 3-hour · {(sig.get('pattern') or 'breakout').title()}" + nxt
    opt = BO.option_idea(master, name, "NFO", sig["close"], sig["side"], "3h", now)
    msgs.append(BO.call_msg(name, "NFO", cc, "3h", sig, lv, lot=c["lot"], kind=kind, k=2.0, opt=opt))
    plan = BO.details("NFO", cc, "3h", sig, lv, k=2.0)
    if sig.get("pattern"):
        msgs.append(PT.reason_msg(name, "3h", sig, lv, None, plan, NOTE3H))
    else:
        msgs.append(BO.reason_msg(name, "3h", sig, lv, None, None, plan).replace(
            "📚 Backtest 2022-26 (after costs): ≈40% of breakouts win, but winners are 2-3× bigger than losers – "
            "follow the stop strictly and let the trailing stop ride the trend.", NOTE3H))
    s_ = 1 if sig["side"] == "BUY" else -1
    st["active3h"].append(dict(name=name, token=c["token"], expiry=c["expiry"], side=sig["side"], entry=sig["close"],
                               stop=round(sig["close"] - s_ * 2.0 * sig["atr"], 2), risk=2.0 * sig["atr"], best=sig["close"],
                               trailed=False, n=0, last_candle=last, kind=sig.get("pattern") or "BREAKOUT"))
    state["day"]["alerts"] += 1
    return 1


def scan(api, master, now, state, msgs, rep, engine):
    if not ENABLED:
        rep["stocks"] = "disabled"
        return
    st = state.setdefault("stk", dict(active=[], last_block=None))
    st.setdefault("active", [])
    if st.get("rescan_v") != 2:                                    # one-time: re-check today's close for stocks that
        st["rescan_v"] = 2                                          # were blocked by stale alerts of the old rule
        st["last_block"] = None
        for k in [k for k in state["last_eval"] if k.startswith("STKOI|")]:
            del state["last_eval"][k]
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
                BO.close_ledger(state, p.get("key"), float(ltp), "stop", now)
            else:
                keep.append(p)
        st["active"] = keep
    if STOCK3H_ENABLED and engine.is_open("NFO", now):
        manage3h_quotes(api, st, msgs, state)
    blk = last_block_end(now)
    if blk is None or st["last_block"] == blk:
        rep["stocks"]["scan"] = "stock scans run after 12:15 (3h) and after the 15:30 close (3h + daily)"
        return
    st["last_block"] = blk
    daily_block = blk.endswith("15:30:00")
    if not daily_block and not STOCK3H_ENABLED:
        return
    found = 0
    for name, c in uni.items():
        try:
            h = api.candles("NFO", c["token"], "ONE_HOUR", now - pd.Timedelta(days=400 if daily_block else 200), now)
            oi = (api.oi_history("NFO", c["token"], "ONE_DAY", now - pd.Timedelta(days=60), now)
                  if daily_block and hasattr(api, "oi_history") else None)
        except Exception:
            h, oi = None, None
        if h is None or h.empty:
            continue
        h = engine.closed(h.sort_values("time").drop_duplicates("time").reset_index(drop=True), "NFO", 60, now)
        if STOCK3H_ENABLED:
            try:
                found += scan3h(name, c, h, frame3h(h), now, master, st, state, msgs)
            except Exception as e:
                rep.setdefault("errors3h", []).append(f"{name}: {type(e).__name__}")
        if not daily_block:
            continue
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
                BO.close_ledger(state, p.get("key"), px, "expiry/time exit", now)
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
        msgs.append(BO.call_msg(name, "NFO", cc, "1d", sig, lv, lot=c["lot"], kind="Stock future · daily", k=CFG["stop_atr"],
                                opt=BO.option_idea(master, name, "NFO", sig["close"], sig["side"], "1d", now)))
        msgs.append(reason_msg(name, sig, lv, BO.details("NFO", cc, "1d", sig, lv, k=CFG["stop_atr"])))
        s_ = 1 if sig["side"] == "BUY" else -1
        key = f"{name}|1dSTK|{last}"
        st["active"].append(dict(name=name, token=c["token"], expiry=c["expiry"], side=sig["side"], entry=sig["close"],
                                 stop=round(sig["close"] - s_ * CFG["stop_atr"] * sig["atr"], 2), risk=CFG["stop_atr"] * sig["atr"],
                                 best=sig["close"], trailed=False, n=0, last_candle=last, key=key))
        RP.add(state, key=key, mark_key=c["token"], seg="NSE", cat="FUTURES", name=name, symbol=c["symbol"], type="Positional (daily)",
               side=sig["side"], entry=round(sig["close"], 2), sl=round(sig["close"] - s_ * CFG["stop_atr"] * sig["atr"], 2), target=None,
               lot=c["lot"], mult=c["lot"], time=str(now))
        opt = BO.option_idea(master, name, "NFO", sig["close"], sig["side"], "1d", now)
        if opt:
            prem = None
            try:
                prem = float((api.quotes({"NFO": [opt["token"]]}).get(opt["token"]) or {}).get("ltp") or 0) or None
            except Exception:
                prem = None
            om, (osl, otg) = BO.option_msg(name, "NFO", "1d", sig, opt, prem, k=CFG["stop_atr"])
            msgs.append(om)
            if prem:
                RP.add(state, key=key + "|OPT", mark_key=c["token"], seg="NSE", cat="OPTION BUY", name=name, symbol=opt["symbol"],
                       type="Positional (daily)", side="BUY", entry=round(prem, 2), sl=round(osl, 2), target=None, lot=opt["lot"],
                       mult=opt["lot"], time=str(now), und_entry=sig["close"], und_side=sig["side"])
        state["day"]["alerts"] += 1
        found += 1
        if hasattr(api, "api"):
            time.sleep(0.1)
    rep["stocks"].update(scan=f"{'3h + daily' if daily_block else '3h'} scan of {len(uni)} stock futures done", new_calls=found)
