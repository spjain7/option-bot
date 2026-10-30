"""VOLUME BREAKOUT alerts (3-hour swing + daily positional) – the strongest rule found in research/search (STRAT-SEARCH-004/005).

BUY : candle closes above the highest high of the previous 20 candles AND its volume > 1.5× the 20-candle average
      AND close above EMA200 (trend side).            SELL: mirror (below the 20-candle low, below EMA200).
Plan: entry next candle open (≈ live price) · initial SL 2 ATR · then a 3 ATR trailing stop on candle closes ·
      exit when the trailing stop is hit or after 40 candles. Reference levels 1R / 2R / 3R are shown, not fixed exits.
Backtest (Jul-2022 → Oct-2026, 9 futures, after costs + slippage, exploratory): 3h ≈ +0.15R/trade at 2× costs, ~41% wins;
daily ≈ +0.2R. ALERTS ONLY – no orders.
"""
import numpy as np
import pandas as pd
from crude import indicators as I
from alerts import tradeplan as TP

CFG = dict(N=20, vol_x=1.5, stop_atr=2.0, trail_atr=3.0, max_candles=40, ema=200)
# Exits – PAT-002 (27-Oct-2026, research/search/REGISTRY_PAT2.md, corrected simulator): ONE stop + ONE target, no trailing.
#  3h : breakout + volume + EMA200, stop 2 ATR, target 2R       (win 43% / 43%, profit in both periods, 67% of instruments)
#  1d : breakout + volume + EMA200, stop 1.5 ATR, target 3R     (win 45% / 46%, 78% of instruments)
#  1w : 20-week breakout, stop 3 ATR(weekly), target 2R         (win 50% / 51%, big targets; only 20 + 41 trades – small sample)
#  Trend change (close back across EMA20 of the same chart) = WARNING message before the stop, not an automatic exit.
#  Small targets (0.5R) won 66-77% of trades but LOST money – so no 80-90% setup is used.
#  1m : MONTHLY breakout/breakdown (SR-001): first daily close beyond last month's high/low, with the weekly AND monthly
#       trend agreeing; stop 1.5 ATR(daily), target 2R, max 20 sessions. ₹6,030 / ₹24,459 per lot (2× costs), win 50% / 46%,
#       profitable in both periods but only 5 of 9 instruments positive – a near-pass, labelled as such.
STOP_ATR = {"3h": 2.0, "1d": 1.5, "1w": 3.0, "1m": 1.5}
TARGET_R = {"3h": 2.0, "1d": 3.0, "1w": 2.0, "1m": 2.0}
TRAIL = {"3h": False, "1d": False, "1w": False, "1m": False}
TREND_EXIT_EMA = {}
TREND_WARN_EMA = {"3h": 20, "1d": 20, "1w": 20, "1m": 20}
MAX_CANDLES = {"3h": 40, "1d": 40, "1w": 26, "1m": 20}
# 28-Oct sanity rule: a call whose stop-loss is too far from entry is not tradable for one lot -> no call.
# (weekly SILVER SELL had its SL 28% away; daily SILVER 1.5 ATR ≈ 7%.)
MAX_SL_PCT = {"3h": 2.5, "1d": 4.0, "1w": 0.0, "1m": 4.0}
# option-buy calls: SL / target as % of the premium (same as the intraday option-buy engine), not from the futures move
OPT_SL_TG = {"3h": (0.30, 0.60), "1d": (0.35, 0.80), "1m": (0.35, 0.80)}


def stop_k(tf):
    return STOP_ATR.get(tf, CFG["stop_atr"])
TFLABEL = {"3h": "SWING (3-hour candles)", "1d": "POSITIONAL (daily candles)", "1w": "POSITIONAL (weekly candles)", "1m": "POSITIONAL (monthly level)"}


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


def weekly_candles(daily):
    if daily is None or daily.empty:
        return None
    w = daily.copy(); w["wk"] = w["time"].dt.to_period("W")
    return w.groupby("wk").agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                               close=("close", "last"), volume=("volume", "sum")).reset_index(drop=True)


def evaluate_weekly(df):
    """Weekly: close beyond the 20-week high/low (no EMA200 – needs 4 years of weeks). Only COMPLETED weeks."""
    if df is None or len(df) < 25:
        return dict(side=None, why="needs 25 weekly candles")
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"].astype(float)
    hh, ll = h.shift(1).rolling(20).max().iloc[-1], l.shift(1).rolling(20).min().iloc[-1]
    va = v.rolling(20).mean().shift(1).iloc[-1]
    x = df.iloc[-1]
    out = dict(candle=str(x.time), close=float(x.close), hh=float(hh), ll=float(ll), ema200=float(I.ema(c, 20).iloc[-1]),
               atr=float(I.atr(df, 14).iloc[-1]), vol_x=float(x.volume / va) if va and va > 0 else None,
               adx=float(I.adx(df).iloc[-1]), rsi=float(I.rsi(c, 14).iloc[-1]))
    side = "BUY" if x.close > hh else "SELL" if x.close < ll else None
    return dict(out, side=side, why=None if side else "no 20-week breakout")


def htf_levels(daily):
    """Support / resistance from completed daily candles: last week's and last month's high / low, monthly pivot."""
    if daily is None or len(daily) < 30:
        return None
    d = daily.copy(); t = d["time"]
    last = t.iloc[-1]
    w, m = t.dt.to_period("W"), t.dt.to_period("M")
    pw = d[w == (last.to_period("W") - 1)]; pm = d[m == (last.to_period("M") - 1)]
    if pw.empty or pm.empty:
        return None
    ph, pl, pc = float(pm["high"].max()), float(pm["low"].min()), float(pm["close"].iloc[-1])
    return dict(pwh=float(pw["high"].max()), pwl=float(pw["low"].min()), pmh=ph, pml=pl, mp=(ph + pl + pc) / 3)


def evaluate_monthly(daily):
    """MONTHLY breakout / breakdown on the last completed daily candle (SR-001 MB|mtf)."""
    if daily is None or len(daily) < 150:
        return dict(side=None, why="needs 150 daily candles")
    d = daily.reset_index(drop=True)
    lv = htf_levels(d.iloc[:-1])
    if lv is None:
        return dict(side=None, why="no previous month")
    t = d["time"]
    W = d.groupby(t.dt.to_period("W"))["close"].last(); M = d.groupby(t.dt.to_period("M"))["close"].last()
    W, M = W.iloc[:-1], M.iloc[:-1]                                   # completed weeks / months only
    wtr = np.sign(W.iloc[-1] - W.ewm(span=20, adjust=False).mean().iloc[-1])
    mtr = np.sign(M.iloc[-1] - M.ewm(span=10, adjust=False).mean().iloc[-1])
    x, pc = d.iloc[-1], d["close"].iloc[-2]
    v = d["volume"].astype(float); va = v.rolling(20).mean().shift(1).iloc[-1]
    out = dict(candle=str(x.time), close=float(x.close), hh=lv["pmh"], ll=lv["pml"], ema200=float(I.ema(d["close"], 200).iloc[-1]),
               atr=float(I.atr(d, 14).iloc[-1]), vol_x=float(x.volume / va) if va and va > 0 else None,
               adx=float(I.adx(d).iloc[-1]), rsi=float(I.rsi(d["close"], 14).iloc[-1]), monthly=True)
    if x.close > lv["pmh"] >= pc and wtr > 0 and mtr > 0:
        return dict(out, side="BUY")
    if x.close < lv["pml"] <= pc and wtr < 0 and mtr < 0:
        return dict(out, side="SELL")
    return dict(out, side=None, why="no monthly breakout with weekly + monthly trend")


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


OPT_MIN_DAYS = {"3h": 2, "1d": 2, "1w": 20, "1m": 10}      # nearest option expiry with at least 2 days left (user choice 27-Oct)


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
        tk = r.get("tick") if hasattr(r, "get") else None
        return dict(symbol=r["symbol"], token=str(r["token"]), K=float(r["K"]), typ=typ, expiry=pd.Timestamp(r["expiry_dt"]),
                    lot=int(r["lotsize"]), tick=float(tk) if tk is not None and tk == tk and tk > 0 else None)
    except Exception:
        return None


def call_msg(name, ex, c, tf, sig, levels, live=None, lot=None, kind=None, k=None, opt=None, tr=None, plan=None):
    """Message 1 – the futures call: entry, SL, one target, lot. Nothing else. tr: target in R (0 = trailing, no target).
    With `plan` (alerts/tradeplan.py) the message shows exactly the validated, tick-rounded levels that are tracked."""
    if plan is not None:
        t = plan["tick"]
        return "\n".join([
            f"{'🟢 BUY' if plan['side'] == 'BUY' else '🔴 SELL'}  {name} FUT  ·  Positional",
            "━━━━━━━━━━━━━━",
            f"Entry   : {TP.fmt(plan['entry'], t)}",
            f"SL      : {TP.fmt(plan['sl'], t)}",
            f"Target  : {TP.fmt(plan['target'], t)}" if plan.get("target") else "Target  : trail – exit on TREND CHANGE alert",
            f"Lot     : {lot or plan.get('lot') or c.get('lot') or '-'}  ·  {pd.Timestamp(c['expiry']):%b} expiry  ·  {'MCX' if ex == 'MCX' else 'NSE'}"])
    s, ref, R = _levels(sig, live, k or stop_k(tf))
    tg = TARGET_R.get(tf) if tr is None else (tr or None)
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


CHART = {"3h": "3-hour", "1d": "Daily", "1w": "Weekly", "1m": "Daily"}


def reason_msg(name, tf, sig, levels, oi=None, q=None, plan=None, htf=None):
    """Message 2 – WHY: candle timeframe, setup, volume, OI position, trend, next level, exit plan."""
    s = 1 if sig["side"] == "BUY" else -1
    if sig.get("pattern"):
        setup = f"{sig['pattern'].title()} – closed {'above' if s > 0 else 'below'} {_f(sig['level'])}"
    else:
        lvl = sig["hh"] if s > 0 else sig["ll"]
        what = "last month's" if tf == "1m" else f"20-{'week' if tf == '1w' else 'candle'}"
        setup = f"{'MONTHLY ' if tf == '1m' else 'WEEKLY ' if tf == '1w' else ''}{'BREAKOUT above' if s > 0 else 'BREAKDOWN below'} {what} {'high' if s > 0 else 'low'} {_f(lvl)}"
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
    if tf == "1m":
        L.append("• Trend   : weekly and monthly trend agree ✅ (near-pass rule: profitable in both test periods, 5 of 9 instruments)")
    L.append(f"• Trend   : {'above' if sig['close'] > sig['ema200'] else 'below'} {'20-week' if tf == '1w' else '200'} EMA {_f(sig['ema200'])} "
             f"{'✅' if (sig['close'] > sig['ema200']) == (s > 0) else '⚠️'}")
    L.append(f"• RSI/ADX : {sig.get('rsi') or 0:.0f} / {sig.get('adx') or 0:.0f}")
    nxt = (levels["resistance"] if s > 0 else levels["support"])[:1]
    if nxt:
        L.append(f"• Next {'resistance' if s > 0 else 'support'}: {_f(nxt[0][0])}")
    if htf:
        L.append(f"• Levels  : week H {_f(htf['pwh'])} / L {_f(htf['pwl'])} · month H {_f(htf['pmh'])} / L {_f(htf['pml'])} · "
                 f"monthly pivot {_f(htf['mp'])}")
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
            L["hi"], L["lo"] = max(L.get("hi", fut_exit), fut_exit), min(L.get("lo", fut_exit), fut_exit)
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
        _fp = (lambda x, t=p.get("tick"): TP.fmt(x, t)) if p.get("tick") else _f
        done = None
        bars = c15[c15["time"] > pd.Timestamp(p["checked"])] if c15 is not None and len(c15) else pd.DataFrame()
        tg = p["target"] if "target" in p else (p["entry"] + s * TARGET_R[tf] * p["risk"] if TARGET_R.get(tf) else None)
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
                    if not p.get("shadow"):
                        msgs.append(f"🔁 TRAIL UPDATE – {name} {p['side']} ({tf}) · new stop {_fp(p['stop'])} · best close {_fp(p['best'])}")
            te = TREND_EXIT_EMA.get(tf)
            if te and len(frame) > te:
                e = float(I.ema(frame["close"], te).iloc[-1])
                if (cl < e) if s > 0 else (cl > e):
                    done = (cl, f"TREND CHANGE – daily close {'below' if s > 0 else 'above'} EMA{te} ({_fp(e)})")
            tw = TREND_WARN_EMA.get(tf)
            if done is None and tw and len(frame) > tw and not p.get("warned") and not p.get("shadow"):
                e = float(I.ema(frame["close"], tw).iloc[-1])
                if (cl < e) if s > 0 else (cl > e):
                    p["warned"] = True
                    msgs.append(f"⚠️ TREND CHANGE WARNING – {name} {p['side']}: {CHART.get(tf, tf)} close {_fp(cl)} {'below' if s > 0 else 'above'} "
                                f"EMA{tw} ({_fp(e)}) · stop {_fp(p['stop'])} · consider exiting early to cut the loss "
                                f"(open {s * (cl - p['entry']) / p['risk']:+.1f}R)")
            if done is None and p["n"] >= MAX_CANDLES.get(tf, CFG["max_candles"]):
                done = (cl, f"time exit after {MAX_CANDLES.get(tf, CFG['max_candles'])} candles")
        if done and p.get("shadow"):                       # log-only record: outcome kept, nothing sent, no ledger row
            r = s * (done[0] - p["entry"]) / p["risk"]
            state.setdefault("shadow_bo", []).append(dict(label=p["shadow"], name=name, tf=tf, side=p["side"], entry=p["entry"],
                                                          stop=p["stop"], target=p.get("target"), exit=float(done[0]), why=done[1],
                                                          r=round(r, 3), opened=p.get("opened"), closed=str(now)))
            state["shadow_bo"] = state["shadow_bo"][-1000:]
            print(f"[shadow] {name} {tf} {p['side']} {p['shadow']}: {done[1]} {r:+.2f}R")
        elif done:
            r = s * (done[0] - p["entry"]) / p["risk"]
            msgs.append(f"{'✅' if r > 0 else '❌'} EXIT – {name} {p['side']} ({tf}) at ~{_fp(done[0])}: {done[1]} · "
                        f"result {r:+.2f}R (entry {_fp(p['entry'])})")
            state["day"].setdefault("outcomes", []).append(dict(name=name, tf=tf, side=p["side"], result=f"{done[1]} {r:+.2f}R"))
            close_ledger(state, p.get("key"), float(done[0]), done[1], now)
        else:
            keep.append(p)
    state["bo_active"] = keep


def option_msg(name, ex, tf, sig, opt, prem, live=None, k=None, tr=None, oplan=None):
    """OPTION-BUY call for the same signal: ATM CE (buy) / PE (sell). SL / target on the PREMIUM (kept separate from the
    futures stop); also exit when the futures call exits. With `oplan` the tracked, tick-rounded levels are shown."""
    if oplan is None:
        slp, tgp = OPT_SL_TG.get(tf, (0.35, 0.80))
        oplan = TP.option_plan(premium=prem, sl_pct=slp, tg_pct=tgp, tick=opt.get("tick"), lot=opt["lot"])
    t = oplan["tick"]
    ok = oplan["valid"]
    L = [f"{'🟢' if opt['typ'] == 'CE' else '🔴'} BUY  {name} {opt['K']:g} {opt['typ']}  ·  Positional",
         "━━━━━━━━━━━━━━",
         f"Entry   : {('₹' + TP.fmt(oplan['entry'], t)) if ok else 'market (LTP n/a)'}",
         f"SL      : {('₹' + TP.fmt(oplan['sl'], t)) if ok else '-'}  (−{oplan.get('sl_pct', 0) * 100:.0f}%)",
         f"Target  : {('₹' + TP.fmt(oplan['target'], t)) if ok else '-'}  (+{oplan.get('tg_pct', 0) * 100:.0f}%)",
         f"Lot     : {opt['lot']}  ·  exp {opt['expiry']:%d-%b}  ·  {'MCX' if ex == 'MCX' else 'NSE'}",
         "Also exit when the futures call exits"]
    return "\n".join(L), ((oplan["sl"], oplan["target"]) if ok else (None, None))
