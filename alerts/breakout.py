"""VOLUME BREAKOUT alerts (3-hour swing + daily positional) – the strongest rule found in research/search (STRAT-SEARCH-004/005).

BUY : candle closes above the highest high of the previous 20 candles AND its volume > 1.5× the 20-candle average
      AND close above EMA200 (trend side).            SELL: mirror (below the 20-candle low, below EMA200).
Plan: entry next candle open (≈ live price) · initial SL 2 ATR · then a 3 ATR trailing stop on candle closes ·
      exit when the trailing stop is hit or after 40 candles. Reference levels 1R / 2R / 3R are shown, not fixed exits.
Backtest (Jul-2022 → Oct-2026, 9 futures, after costs + slippage, exploratory): 3h ≈ +0.15R/trade at 2× costs, ~41% wins;
daily ≈ +0.2R. ALERTS ONLY – no orders.
"""
import pandas as pd
from crude import indicators as I

CFG = dict(N=20, vol_x=1.5, stop_atr=2.0, trail_atr=3.0, max_candles=40, ema=200)
# Exits (27-Oct-2026, after fixing a short-side bug in the exit simulator – research/search/REGISTRY_EXIT.md):
#  3h : stop 2 ATR + ONE target at 3R (full exit) + 40-candle time exit. Trend change = WARNING message only
#       (exiting on it tested worse). Booking 50% at T1 was REMOVED – with the corrected test it lost money.
#  1d : stop 1.5 ATR, no fixed target – trailing stop 3 ATR + exit when a daily close crosses back over EMA20
#       (both better than the old exit in design and hold-out). A fixed daily target cut profit by 35-90%.
STOP_ATR = {"3h": 2.0, "1d": 1.5}
TARGET_R = {"3h": 3.0, "1d": None}
TRAIL = {"3h": False, "1d": True}
TREND_EXIT_EMA = {"1d": 20}
TREND_WARN_EMA = {"3h": 20}


def stop_k(tf):
    return STOP_ATR.get(tf, CFG["stop_atr"])
TFLABEL = {"3h": "SWING (3-hour candles)", "1d": "POSITIONAL (daily candles)"}


def daily_candles(h1c, session_close):
    """Completed daily candles from completed 1-hour candles (a day counts once its session has closed)."""
    if h1c is None or h1c.empty:
        return h1c
    g = h1c.groupby(h1c["time"].dt.normalize())
    d = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
              close=("close", "last"), volume=("volume", "sum")).reset_index(drop=True)
    return d


def evaluate(df):
    """df = completed candles. Returns dict with side BUY/SELL/None and the numbers behind it."""
    if df is None or len(df) < CFG["ema"] + 5:
        return dict(side=None, why=f"needs {CFG['ema'] + 5} candles, have {0 if df is None else len(df)}")
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"].astype(float)
    hh = h.shift(1).rolling(CFG["N"]).max().iloc[-1]
    ll = l.shift(1).rolling(CFG["N"]).min().iloc[-1]
    va = v.rolling(20).mean().shift(1).iloc[-1]
    e = I.ema(c, CFG["ema"]).iloc[-1]
    a = float(I.atr(df, 14).iloc[-1])
    x = df.iloc[-1]
    vx = float(x.volume / va) if va and va > 0 else None
    out = dict(candle=str(x.time), close=float(x.close), hh=float(hh), ll=float(ll), ema200=float(e), atr=a, vol_x=vx,
               adx=float(I.adx(df).iloc[-1]), rsi=float(I.rsi(c, 14).iloc[-1]))
    if vx is None:
        return dict(out, side=None, why="volume not available")
    if x.close > hh and vx > CFG["vol_x"] and x.close > e:
        return dict(out, side="BUY")
    if x.close < ll and vx > CFG["vol_x"] and x.close < e:
        return dict(out, side="SELL")
    why = ("breakout without enough volume" if (x.close > hh or x.close < ll) and vx <= CFG["vol_x"]
           else "breakout against the 200-EMA trend" if (x.close > hh or x.close < ll) else "no 20-candle breakout")
    return dict(out, side=None, why=why)


def _f(x):
    return f"{x:,.2f}" if abs(x) < 1000 else f"{x:,.0f}"


def _lv(xs):
    return " · ".join(f"{_f(v)} ({n})" for v, n in xs) or "none nearby"


SHORT_TF = {"3h": "Swing · 3-hour", "1d": "Positional · daily"}


def _levels(sig, live, k=2.0):
    s = 1 if sig["side"] == "BUY" else -1
    ref = live or sig["close"]
    R = k * sig["atr"]
    return s, ref, R


OPT_MIN_DAYS = {"3h": 2, "1d": 2}      # nearest option expiry with at least 2 days left (user choice 27-Oct)


def option_idea(master, name, ex, px, side, tf, now):
    """ATM option to BUY for this futures call (CE for BUY, PE for SELL), nearest expiry ≥ OPT_MIN_DAYS away. None if not found."""
    try:
        typ = "CE" if side == "BUY" else "PE"
        types = ["OPTFUT", "OPTCOM"] if ex == "MCX" else ["OPTIDX", "OPTSTK"]
        lo = pd.Timestamp(now).normalize() + pd.Timedelta(days=OPT_MIN_DAYS.get(tf, 5))
        o = master[(master["name"] == name) & (master["exch_seg"] == ex) & master["instrumenttype"].isin(types)
                   & master["symbol"].str.endswith(typ) & (master["expiry_dt"] >= lo)]
        if o.empty:
            return None
        o = o[o["expiry_dt"] == o["expiry_dt"].min()].copy()
        o["K"] = o["strike"].astype(float) / 100
        r = o.iloc[(o["K"] - px).abs().argsort().iloc[0]]
        return dict(symbol=r["symbol"], token=str(r["token"]), K=float(r["K"]), typ=typ, expiry=pd.Timestamp(r["expiry_dt"]),
                    lot=int(r["lotsize"]))
    except Exception:
        return None


def call_msg(name, ex, c, tf, sig, levels, live=None, lot=None, kind=None, k=None, opt=None):
    """Message 1 – the futures call: entry, SL, one target, lot. Nothing else."""
    s, ref, R = _levels(sig, live, k or stop_k(tf))
    tg = TARGET_R.get(tf)
    lot = lot or c.get("lot")
    return "\n".join([
        f"{'🟢 BUY' if s > 0 else '🔴 SELL'}  {name} FUT  ·  Positional",
        "━━━━━━━━━━━━━━",
        f"Entry   : {_f(ref)}",
        f"SL      : {_f(ref - s * R)}",
        f"Target  : {_f(ref + s * tg * R)}" if tg else "Target  : trail – exit on TREND CHANGE alert",
        f"Lot     : {lot or '-'}  ·  {pd.Timestamp(c['expiry']):%b} expiry  ·  {'MCX' if ex == 'MCX' else 'NSE'}"])


def details(ex, c, tf, sig, levels, live=None, k=None):
    """Trade-management details shown in message 2."""
    s, ref, R = _levels(sig, live, k or stop_k(tf))
    return ["📋 TRADE PLAN",
            f"📄 Contract: {c['symbol']} ({'MCX' if ex == 'MCX' else 'NSE F&O'}) · exp {pd.Timestamp(c['expiry']):%d-%b-%Y}",
            f"🚫 Don't chase beyond {_f(ref + s * 0.5 * sig['atr'])}",
            (f"✅ One target {TARGET_R[tf]:g}R – full exit there · ⚠️ TREND CHANGE warning if a 3h close crosses EMA20 against you"
             if TARGET_R.get(tf) else
             "✅ No fixed target – exit on the trailing stop (3 ATR from best close) OR the TREND CHANGE alert (daily close across EMA20)"),
            f"🧱 Resistance: {_lv(levels['resistance'])}",
            f"🛟 Support   : {_lv(levels['support'])}",
            f"⏱ Signal candle {pd.Timestamp(sig['candle']):%d-%b %H:%M} ({TFLABEL[tf]}) · alert only – no auto trade",
            "━━━━━━━━━━━━━━━━━━", "📌 WHY"]


CHART = {"3h": "3-hour", "1d": "Daily"}


def reason_msg(name, tf, sig, levels, oi=None, q=None, plan=None):
    """Message 2 – WHY: candle timeframe, setup, volume, OI position, trend, next level, exit plan."""
    s = 1 if sig["side"] == "BUY" else -1
    if sig.get("pattern"):
        setup = f"{sig['pattern'].title()} – closed {'above' if s > 0 else 'below'} {_f(sig['level'])}"
    else:
        lvl = sig["hh"] if s > 0 else sig["ll"]
        setup = f"{'BREAKOUT above' if s > 0 else 'BREAKDOWN below'} 20-candle {'high' if s > 0 else 'low'} {_f(lvl)}"
    L = [f"📌 WHY – {name} {sig['side']}", "━━━━━━━━━━━━━━",
         f"• Chart   : {CHART.get(tf, tf)} candle closed {_f(sig['close'])}",
         f"• Setup   : {setup}"]
    if sig.get("vol_x"):
        L.append(f"• Volume  : {sig['vol_x']:.1f}× average {'✅' if sig['vol_x'] > 1.5 else ''}")
    if oi and oi.get("label"):
        good = {"BUY": ("Long buildup", "Short covering"), "SELL": ("Short buildup", "Long unwinding")}[sig["side"]]
        L.append(f"• OI      : {oi['label']} (OI {oi['chg_pct']:+.2f}%) {'✅' if oi['label'] in good else '⚠️ not confirming'}")
    else:
        L.append("• OI      : not available")
    L.append(f"• Trend   : {'above' if sig['close'] > sig['ema200'] else 'below'} 200 EMA {_f(sig['ema200'])} "
             f"{'✅' if (sig['close'] > sig['ema200']) == (s > 0) else '⚠️'}")
    L.append(f"• RSI/ADX : {sig.get('rsi') or 0:.0f} / {sig.get('adx') or 0:.0f}")
    nxt = (levels["resistance"] if s > 0 else levels["support"])[:1]
    if nxt:
        L.append(f"• Next {'resistance' if s > 0 else 'support'}: {_f(nxt[0][0])}")
    L.append("• Exit    : SL or target · ⚠️ TREND CHANGE alert comes before the SL" if TARGET_R.get(tf)
             else "• Exit    : trailing SL updates · TREND CHANGE alert = exit")
    L.append("Not investment advice.")
    return "\n".join(L)


def close_ledger(state, key, fut_exit, why, now):
    """Close the futures row and its option-buy row (option exit ≈ entry premium + 0.5 × futures move)."""
    for L in state.get("ledger", []):
        if L["status"] != "OPEN" or not key:
            continue
        if L.get("key") == key:
            L.update(status="CLOSED", exit=round(fut_exit, 2), note=why.replace("🎯 ", "")[:24], closed=str(now))
        elif L.get("key") == key + "|OPT":
            s = 1 if L.get("und_side") == "BUY" else -1
            L.update(status="CLOSED", exit=round(max(0.05, L["entry"] + 0.5 * s * (fut_exit - L["und_entry"])), 2),
                     note=why.replace("🎯 ", "")[:24], closed=str(now))


def manage(state, msgs, name, tf, frame, c15, now):
    """Follow-ups for open breakout alerts of this instrument/timeframe: stop, single target, trailing, trend change."""
    keep = []
    for p in state.get("bo_active", []):
        if p["name"] != name or p["tf"] != tf:
            keep.append(p); continue
        s = 1 if p["side"] == "BUY" else -1
        done = None
        bars = c15[c15["time"] > pd.Timestamp(p["checked"])] if c15 is not None and len(c15) else pd.DataFrame()
        tg = p["entry"] + s * TARGET_R[tf] * p["risk"] if TARGET_R.get(tf) else None
        for b in bars.itertuples():                       # stop first inside a candle (conservative)
            if (b.low <= p["stop"]) if s > 0 else (b.high >= p["stop"]):
                done = (p["stop"], "trailing stop hit" if p["trailed"] else "stop-loss hit"); break
            if tg is not None and ((b.high >= tg) if s > 0 else (b.low <= tg)):
                done = (tg, "🎯 TARGET HIT"); break
        if len(bars):
            p["checked"] = str(bars["time"].iloc[-1])
        if done is None and frame is not None and len(frame) and str(frame["time"].iloc[-1]) != p["last_candle"]:
            new = frame[frame["time"] > pd.Timestamp(p["last_candle"])]
            a = float(I.atr(frame, 14).iloc[-1])
            for b in new.itertuples():
                p["best"] = max(p["best"], b.close) if s > 0 else min(p["best"], b.close)
                p["n"] += 1
            p["last_candle"] = str(frame["time"].iloc[-1])
            cl = float(frame["close"].iloc[-1])
            if TRAIL.get(tf):
                ns = p["best"] - s * CFG["trail_atr"] * a
                if s * (ns - p["stop"]) > 0.25 * a:
                    p["stop"], p["trailed"] = round(ns, 2), True
                    msgs.append(f"🔁 TRAIL UPDATE – {name} {p['side']} ({tf}) · new stop {_f(p['stop'])} · best close {_f(p['best'])}")
            te = TREND_EXIT_EMA.get(tf)
            if te and len(frame) > te:
                e = float(I.ema(frame["close"], te).iloc[-1])
                if (cl < e) if s > 0 else (cl > e):
                    done = (cl, f"TREND CHANGE – daily close {'below' if s > 0 else 'above'} EMA{te} ({_f(e)})")
            tw = TREND_WARN_EMA.get(tf)
            if done is None and tw and len(frame) > tw and not p.get("warned"):
                e = float(I.ema(frame["close"], tw).iloc[-1])
                if (cl < e) if s > 0 else (cl > e):
                    p["warned"] = True
                    msgs.append(f"⚠️ TREND CHANGE WARNING – {name} {p['side']} ({tf}): 3h close {_f(cl)} {'below' if s > 0 else 'above'} "
                                f"EMA{tw} ({_f(e)}) · stop {_f(p['stop'])} · consider exiting early to cut the loss "
                                f"(open {s * (cl - p['entry']) / p['risk']:+.1f}R)")
            if done is None and p["n"] >= CFG["max_candles"]:
                done = (cl, f"time exit after {CFG['max_candles']} candles")
        if done:
            r = s * (done[0] - p["entry"]) / p["risk"]
            msgs.append(f"{'✅' if r > 0 else '❌'} EXIT – {name} {p['side']} ({tf}) at ~{_f(done[0])}: {done[1]} · "
                        f"result {r:+.2f}R (entry {_f(p['entry'])})")
            state["day"].setdefault("outcomes", []).append(dict(name=name, tf=tf, side=p["side"], result=f"{done[1]} {r:+.2f}R"))
            close_ledger(state, p.get("key"), float(done[0]), done[1], now)
        else:
            keep.append(p)
    state["bo_active"] = keep


def option_msg(name, ex, tf, sig, opt, prem, live=None, k=None):
    """OPTION-BUY call for the same signal: ATM CE (buy) / PE (sell). Premium SL/target ≈ futures levels × delta 0.5."""
    s, ref, R = _levels(sig, live, k or stop_k(tf))
    sl_f, tg_f = ref - s * R, (ref + s * TARGET_R[tf] * R if TARGET_R.get(tf) else None)
    est = lambda fut: max(0.05, prem + 0.5 * s * (fut - ref)) if prem else None
    L = [f"{'🟢' if opt['typ'] == 'CE' else '🔴'} BUY  {name} {opt['K']:g} {opt['typ']}  ·  Positional",
         "━━━━━━━━━━━━━━",
         f"Entry   : {('₹' + _f(prem)) if prem else 'market (LTP n/a)'}",
         f"SL      : {('₹' + _f(est(sl_f)) + '  ') if prem else ''}(fut {_f(sl_f)})",
         (f"Target  : {('₹' + _f(est(tg_f)) + '  ') if prem else ''}(fut {_f(tg_f)})") if tg_f else "Target  : trail – exit with the futures call",
         f"Lot     : {opt['lot']}  ·  exp {opt['expiry']:%d-%b}  ·  {'MCX' if ex == 'MCX' else 'NSE'}"]
    return "\n".join(L), (est(sl_f), est(tg_f) if tg_f else None)
