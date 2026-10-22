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


def call_msg(name, ex, c, tf, sig, levels, live=None):
    """Message 1 – the call card (what to do)."""
    s = 1 if sig["side"] == "BUY" else -1
    a = sig["atr"]
    ref = live or sig["close"]
    R = CFG["stop_atr"] * a
    sl = ref - s * R
    head = "🟢🚀 BUY" if s > 0 else "🔴📉 SELL"
    return "\n".join([
        f"{head} | {name} FUT | {TFLABEL[tf]}",
        f"📄 {c['symbol']} ({'MCX' if ex == 'MCX' else 'NSE F&O'}) · exp {pd.Timestamp(c['expiry']):%d-%b-%Y}",
        "━━━━━━━━━━━━━━━━━━",
        f"🎯 Entry      : {_f(ref)}",
        f"🚫 Don't chase: beyond {_f(ref + s * 0.5 * a)}",
        f"🛑 Stop loss  : {_f(sl)}",
        f"✅ Target 1   : {_f(ref + s * R)} (1R) – book 30%",
        f"✅ Target 2   : {_f(ref + 2 * s * R)} (2R) – book 30%",
        f"🏁 Target 3   : {_f(ref + 3 * s * R)} (3R) – rest on trailing stop",
        f"🔁 Trailing SL: 3 ATR from best close (updates follow)",
        "━━━━━━━━━━━━━━━━━━",
        f"🧱 Resistance : {_lv(levels['resistance'])}",
        f"🛟 Support    : {_lv(levels['support'])}",
        f"⏱ Signal candle {pd.Timestamp(sig['candle']):%d-%b %H:%M} · Alert only – no auto trade"])


def reason_msg(name, tf, sig, levels, oi=None, q=None):
    """Message 2 – why the call was issued."""
    s = 1 if sig["side"] == "BUY" else -1
    lvl = sig["hh"] if s > 0 else sig["ll"]
    pts = []
    pts.append(f"{'📈' if s > 0 else '📉'} Breakout: closed at {_f(sig['close'])}, {'above' if s > 0 else 'below'} the 20-candle "
               f"{'high' if s > 0 else 'low'} {_f(lvl)} – price escaped its recent range.")
    pts.append(f"🔊 Volume: {sig['vol_x']:.1f}× normal – big players took part, so it is less likely to be a fake breakout.")
    pts.append(f"🧭 Trend: price is {'above' if s > 0 else 'below'} the 200 EMA ({_f(sig['ema200'])}) – trading with the main trend, not against it.")
    adx = sig.get("adx") or 0
    pts.append(f"💪 Trend strength (ADX {adx:.0f}): " + ("strong" if adx >= 25 else "building" if adx >= 18 else "weak – smaller size"))
    r = sig.get("rsi") or 50
    if (s > 0 and r > 75) or (s < 0 and r < 25):
        pts.append(f"⚠️ RSI {r:.0f}: already stretched – entry only near the call price, never chase.")
    else:
        pts.append(f"📊 RSI {r:.0f}: momentum supports the move.")
    if oi and oi.get("label"):
        good = {"BUY": ("Long buildup", "Short covering"), "SELL": ("Short buildup", "Long unwinding")}[sig["side"]]
        pts.append(f"🏦 OI: {oi['label']} ({oi['chg_pct']:+.2f}% in {oi['gap_min']:.0f} min) – "
                   + ("supports the call ✅" if oi["label"] in good else "does NOT confirm – be careful ⚠️"))
    elif oi:
        pts.append(f"🏦 OI {oi['oi']:,.0f}: change not measurable yet (needs a second reading).")
    nxt = (levels["resistance"] if s > 0 else levels["support"])[:1]
    if nxt:
        pts.append(f"🧱 Next {'resistance' if s > 0 else 'support'}: {_f(nxt[0][0])} ({nxt[0][1]}) – watch for a pause there.")
    pts.append("📚 Backtest 2022-26 (after costs): ≈40% of breakouts win, but winners are 2-3× bigger than losers – "
               "follow the stop strictly and let the trailing stop ride the trend.")
    return "\n".join([f"💡 WHY THIS {sig['side']} – {name} ({tf})", "━━━━━━━━━━━━━━━━━━", *pts,
                       "Backtested, not guaranteed · not investment advice."])


def manage(state, msgs, name, tf, frame, c15, now):
    """Trailing-stop follow-ups for open breakout alerts of this instrument/timeframe."""
    keep = []
    for p in state.get("bo_active", []):
        if p["name"] != name or p["tf"] != tf:
            keep.append(p); continue
        s = 1 if p["side"] == "BUY" else -1
        done = None
        bars = c15[c15["time"] > pd.Timestamp(p["checked"])] if c15 is not None and len(c15) else pd.DataFrame()
        for b in bars.itertuples():
            if (b.low <= p["stop"]) if s > 0 else (b.high >= p["stop"]):
                done = (p["stop"], "trailing stop hit" if p["trailed"] else "stop-loss hit"); break
        if len(bars):
            p["checked"] = str(bars["time"].iloc[-1])
        if done is None and frame is not None and len(frame) and str(frame["time"].iloc[-1]) != p["last_candle"]:
            new = frame[frame["time"] > pd.Timestamp(p["last_candle"])]
            a = float(I.atr(frame, 14).iloc[-1])
            for b in new.itertuples():
                p["best"] = max(p["best"], b.close) if s > 0 else min(p["best"], b.close)
                p["n"] += 1
            p["last_candle"] = str(frame["time"].iloc[-1])
            ns = p["best"] - s * CFG["trail_atr"] * a
            if s * (ns - p["stop"]) > 0.25 * a:
                p["stop"], p["trailed"] = round(ns, 2), True
                msgs.append(f"🔁 TRAIL UPDATE – {name} {p['side']} ({tf}) · new stop {_f(p['stop'])} · best close {_f(p['best'])} · "
                            f"open P&L {s * (p['best'] - p['entry']) / p['risk']:+.1f}R")
            if p["n"] >= CFG["max_candles"]:
                done = (frame["close"].iloc[-1], f"time exit after {CFG['max_candles']} candles")
        if done:
            r = s * (done[0] - p["entry"]) / p["risk"]
            msgs.append(f"{'✅' if r > 0 else '❌'} EXIT – {name} {p['side']} BREAKOUT ({tf}) at ~{_f(done[0])}: {done[1]} · "
                        f"result {r:+.2f}R (entry {_f(p['entry'])})")
            state["day"].setdefault("outcomes", []).append(dict(name=name, tf=tf, side=p["side"], result=f"{done[1]} {r:+.2f}R"))
        else:
            keep.append(p)
    state["bo_active"] = keep
