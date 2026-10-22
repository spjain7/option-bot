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


def call_msg(name, ex, c, tf, sig, levels, oi_line, vol_line, live=None):
    s = 1 if sig["side"] == "BUY" else -1
    a = sig["atr"]
    ref = live or sig["close"]
    sl = ref - s * CFG["stop_atr"] * a
    R = CFG["stop_atr"] * a
    L = [f"{'🟢 BUY' if s > 0 else '🔴 SELL'} BREAKOUT – {name} FUT | {TFLABEL[tf]}", "━━━━━━━━━━━━━━━━━━",
         f"Contract : {c['symbol']} ({'MCX' if ex == 'MCX' else 'NSE F&O'}) · expiry {pd.Timestamp(c['expiry']):%d-%b-%Y}",
         f"Entry    : ~{_f(ref)} (next candle open; avoid chasing beyond {_f(ref + s * 0.5 * a)})",
         f"Stop loss: {_f(sl)} (2 ATR) → then TRAIL 3 ATR below the best close (we will send updates)",
         f"Levels   : 1R {_f(ref + s * R)} · 2R {_f(ref + 2 * s * R)} · 3R {_f(ref + 3 * s * R)} (reference – profits come from trailing)",
         "━━━━━━━━━━━━━━━━━━",
         f"Resistance : {_lv(levels['resistance'])}", f"Support    : {_lv(levels['support'])}", "━━━━━━━━━━━━━━━━━━",
         f"Breakout : close {_f(sig['close'])} {'above the 20-candle high' if s > 0 else 'below the 20-candle low'} {_f(sig['hh'] if s > 0 else sig['ll'])}",
         f"Volume   : {sig['vol_x']:.2f}× the 20-candle average (needs > 1.5×)" + (f" · {vol_line}" if vol_line else ""),
         oi_line,
         f"Trend    : {'above' if s > 0 else 'below'} EMA200 {_f(sig['ema200'])} · ADX {sig['adx']:.0f} · RSI {sig['rsi']:.0f}",
         "━━━━━━━━━━━━━━━━━━",
         f"Why this call: price broke {'out above' if s > 0 else 'down below'} its 20-candle range with {sig['vol_x']:.1f}× normal volume "
         f"(real participation, not a thin move) and in the direction of the 200-EMA trend. This rule was the most robust in "
         f"4 years of tests (≈40% winners; profit comes from a few long trends, so keep losses at the stop and let winners trail).",
         f"Signal candle {pd.Timestamp(sig['candle']):%d-%b %H:%M} (closed).",
         "Alert only – no auto trade. Backtested, not guaranteed; not investment advice."]
    return "\n".join(L)


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
