"""Stock-futures OI BREAKOUT alerts (NSE F&O stocks, lot size < 3000) – the only stock rule that passed a pre-registered
hold-out test (research/search/REPORT_STOCK_OI.md, STOCK-OI-001). Alert only – no orders.

Daily candles, evaluated once after the NSE close (first scan after 15:30 IST):
  BUY : close > 20-day high, volume > 1.5× 20-day average, price up AND futures OI up ≥ 2% (long buildup), close > EMA200
  SELL: close < 20-day low,  volume > 1.5×,              price down AND OI up ≥ 2% (short buildup), close < EMA200
  OI is ignored in the 3 sessions before and the 2 after a monthly expiry (rollover distorts it).
Plan: entry next session open · SL 2 ATR · 3-ATR trailing stop on daily closes · exit on expiry day or after 40 sessions.
Backtest (after costs): design +0.20R/trade, unseen hold-out +0.085R/trade, ~47% wins, ~25 alerts a month.
"""
import os
import time
import numpy as np
import pandas as pd
from alerts import patterns as PT, breakout as BO, signals as S, report as RP, optfilter as OF, tradeplan as TP
from crude import data as CD, indicators as I
from alerts import dataquality as DQ
from alerts import candle_setups as CS

ENABLED = True
# the 15:30 scan of ~180 stock futures can take longer than the alerts step's time limit (scripts/market_loop.sh, 1200 s);
# it stops after this many seconds and continues with the remaining stocks in the next cycle (progress kept in state)
SCAN_BUDGET_SEC = float(os.getenv("STOCK_SCAN_BUDGET_SEC", "720"))
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
        tk = getattr(r, "tick", None)
        out[r.name] = dict(symbol=r.symbol, token=str(r.token), expiry=str(r.expiry_dt.date()), lot=int(r.lotsize),
                           tick=float(tk) if tk is not None and tk == tk and tk > 0 else None)
    return out


def last_block_end(now):
    if now.weekday() >= 5:
        return None
    a, b = CD.hm(now, "12:15"), CD.hm(now, "15:30")
    return str(b) if now >= b + pd.Timedelta(minutes=1) else str(a) if now >= a + pd.Timedelta(minutes=1) else None


def prev_oi_label(api, c, h, day, now):
    """OI label of the last completed session before `day`: LB price↑ OI↑, SB price↓ OI↑, SC price↑ OI↓, LU price↓ OI↓.
    None when unknown (no OI, or the session was the first after an expiry – OI of a new contract is not comparable)."""
    try:
        oi = api.oi_history("NFO", c["token"], "ONE_DAY", pd.Timestamp(day) - pd.Timedelta(days=15), now)
    except Exception:
        return None
    d = daily_with_oi(h, oi)
    d = d[d["day"] < pd.Timestamp(day)].tail(2)
    if len(d) < 2 or d["oi"].isna().any() or first_session_after_expiry(d["time"].iloc[-1]):
        return None
    dp = d["close"].iloc[-1] / d["close"].iloc[-2] - 1
    do = d["oi"].iloc[-1] / d["oi"].iloc[-2] - 1
    return "LB" if dp > 0 and do > 0 else "SB" if dp < 0 and do > 0 else "SC" if dp > 0 and do < 0 else "LU" if dp < 0 and do < 0 else None


def sweep_oi_change(api, c, t0, t1):
    """OI % change over a candle [t0, t1): last 15-minute OI before t0 vs the last one inside the candle. None if missing."""
    try:
        o = api.oi_history("NFO", c["token"], "FIFTEEN_MINUTE", pd.Timestamp(t0) - pd.Timedelta(days=4), pd.Timestamp(t1))
    except Exception:
        return None
    if o is None or o.empty:
        return None
    o = o.assign(time=pd.to_datetime(o["time"])).sort_values("time")
    b, d = o[o["time"] < t0], o[(o["time"] >= t0) & (o["time"] < t1)]
    if b.empty or d.empty or not b["oi"].iloc[-1] > 0:
        return None
    return float((d["oi"].iloc[-1] / b["oi"].iloc[-1] - 1) * 100)


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
    if "doi" in d:                                     # validated by dataquality.validate_daily_oi (NaN = invalid)
        doi = d["doi"].iloc[-1]
        oi_why = d["oi_reason"].iloc[-1] if "oi_reason" in d else None
    else:
        doi = d["oi"].pct_change().iloc[-1] if d["oi"].notna().iloc[-2:].all() else np.nan
        oi_why = None
    out = dict(candle=str(x.time), close=float(x.close), hh=float(hh), ll=float(ll), ema200=float(e), atr=a,
               vol_x=float(x.volume / va) if va else None, dp=float(dp), doi=None if pd.isna(doi) else float(doi),
               adx=float(I.adx(d).iloc[-1]), rsi=float(I.rsi(c, 14).iloc[-1]))
    vok = out["vol_x"] is not None and out["vol_x"] > CFG["vol_x"]
    if in_rollover_window(x.time):
        return dict(out, side=None, why="OI change not usable (rollover window)")
    if pd.isna(doi):
        bo = (x.close > hh and vok and dp > 0 and x.close > e) or (x.close < ll and vok and dp < 0 and x.close < e)
        return dict(out, side=None, why=f"OI change not usable ({oi_why or 'missing'})", oi_blocked=bool(bo))
    if x.close > hh and vok and dp > 0 and doi >= CFG["oi_up"] and x.close > e:
        return dict(out, side="BUY")
    if x.close < ll and vok and dp < 0 and doi >= CFG["oi_up"] and x.close < e:
        return dict(out, side="SELL")
    return dict(out, side=None, why="no OI-confirmed breakout")


# CANDLE-001 (research/search/REGISTRY_CANDLE.md): BEARISH ENGULFING on a stock future after a rise, volume > 1.5× ->
# SELL, SL 1.5 ATR, target 1R, max 10 sessions. Win 55% / 68%, ₹2,065 / ₹7,208 per lot at 2× costs, 66% of stocks +.
# All bullish candles (hammer, bullish engulfing, morning star) failed and are not used.
BEAR_ENGULF_ENABLED = True
MAX_SL_PCT = 6.0      # stock futures: a stop further than 6% from entry is not sent (2-ATR stops on volatile stocks)


def evaluate_bear_engulf(d):
    if d is None or len(d) < 30:
        return dict(side=None)
    o, h, l, c, v = d["open"], d["high"], d["low"], d["close"], d["volume"].astype(float)
    x, p = d.iloc[-1], d.iloc[-2]
    e20 = I.ema(c, 20).iloc[-1]; r5 = c.iloc[-1] / c.iloc[-6] - 1
    va = v.rolling(20).mean().shift(1).iloc[-1]
    vx = float(x.volume / va) if va and va > 0 else 0
    eng = x.close < x.open and p.close > p.open and x.close <= p.open and x.open >= p.close
    out = dict(candle=str(x.time), close=float(x.close), atr=float(I.atr(d, 14).iloc[-1]), vol_x=vx, ema200=float(I.ema(c, 200).iloc[-1]),
               adx=float(I.adx(d).iloc[-1]), rsi=float(I.rsi(c, 14).iloc[-1]), pattern="BEARISH ENGULFING", level=float(p.open),
               hh=float(h.iloc[-21:-1].max()), ll=float(l.iloc[-21:-1].min()), k=1.5, tr=1.0, max_days=10,
               doi=float(d["oi"].pct_change().iloc[-1]) if "oi" in d and d["oi"].notna().iloc[-2:].all() else None)
    # same as the research: at the engulfing candle, close above EMA20 and up over the last 5 candles (it ended a rise)
    if eng and x.close > e20 and r5 > 0 and vx > 1.5 and not in_rollover_window(x.time):
        return dict(out, side="SELL")
    return dict(out, side=None)


def validate_pending(p, ltp, now, quote=None):
    """Stock calls are sent after the close with entry = the close. At the next session (from 09:16) the opening price
    must still be inside the entry zone. -> ("wait" | "cancel" | "active", message).
    quote given (live scan): its exchange timestamp must be present, parseable, fresh and not in the future – otherwise
    the call keeps waiting (never activated or cancelled on an unverified price); the reason is the message."""
    if not ltp or now < now.normalize() + pd.Timedelta(hours=9, minutes=16) or str(now.date()) <= p["last_candle"][:10]:
        return "wait", None
    if quote is not None:
        _, bad = TP.quote_check(quote, now, require=True)
        if bad:
            return "wait", f"{p['name']} pending check postponed: {bad}"
    s = 1 if p["side"] == "BUY" else -1
    t = p.get("tick") or 0.05
    ltp = float(ltp); a_ = p.get("atr") or p["risk"]
    mv = s * (ltp - p["entry"]) / a_
    why_c = ("opened beyond the stop-loss" if s * (ltp - p["stop"]) <= 0 else
             f"opened {mv:.2f} ATR past the entry (no chasing)" if mv > TP.MAX_CHASE_ATR else
             f"opened {-mv:.2f} ATR against the entry" if mv < -TP.MAX_AGAINST_ATR else None)
    if why_c:
        return "cancel", (f"🚫 CANCELLED – {p['name']} FUT {p['side']} (entry {TP.fmt(p['entry'], t)}): {why_c} "
                          f"(price {TP.fmt(ltp, t)}). Do not take this call.")
    return "active", (f"✅ ACTIVE – {p['name']} FUT {p['side']}: price {TP.fmt(ltp, t)} is inside the entry zone. "
                      f"SL {TP.fmt(p['stop'], t)}" + (f" · target {TP.fmt(p['target'], t)}" if p.get("target") else ""))


def reason_engulf(name, sig, lv):
    L = [f"📌 WHY – {name} SELL", "━━━━━━━━━━━━━━",
         f"• Chart   : Daily candle closed {BO._f(sig['close'])}",
         f"• Setup   : BEARISH ENGULFING after a rise – today's red candle swallowed yesterday's green one (open {BO._f(sig['level'])})",
         f"• Volume  : {sig['vol_x']:.1f}× average ✅"]
    if sig.get("doi") is not None:
        L.append(f"• OI      : {sig['doi'] * 100:+.1f}% today ({'short buildup' if sig['doi'] > 0 else 'long unwinding'})")
    L.append(f"• RSI/ADX : {sig['rsi']:.0f} / {sig['adx']:.0f}")
    nxt = lv["support"][:1]
    if nxt:
        L.append(f"• Next support: {BO._f(nxt[0][0])}")
    L += ["• Exit    : SL or target (1R) · max 10 sessions",
          "• Backtest: stock futures 2022-26, win 55% / 68%, profitable after costs – not guaranteed", "Not investment advice."]
    return "\n".join(L)


def reason_msg(name, sig, lv, plan=None):
    """Message 2 – WHY (same clean layout as the MCX / index calls)."""
    s = 1 if sig["side"] == "BUY" else -1
    lvl = sig["hh"] if s > 0 else sig["ll"]
    L = [f"📌 WHY – {name} {sig['side']}", "━━━━━━━━━━━━━━",
         f"• Chart   : Daily candle closed {BO._f(sig['close'])}",
         f"• Setup   : {'BREAKOUT above 20-day high' if s > 0 else 'BREAKDOWN below 20-day low'} {BO._f(lvl)}",
         f"• Volume  : {sig['vol_x']:.1f}× average ✅",
         f"• OI      : {'Long buildup' if s > 0 else 'Short buildup'} (OI {sig['doi'] * 100:+.1f}%, price {sig['dp'] * 100:+.1f}%) ✅",
         f"• Trend   : {'above' if s > 0 else 'below'} 200-day EMA {BO._f(sig['ema200'])} ✅",
         f"• RSI/ADX : {sig['rsi']:.0f} / {sig['adx']:.0f}"]
    nxt = (lv["resistance"] if s > 0 else lv["support"])[:1]
    if nxt:
        L.append(f"• Next {'resistance' if s > 0 else 'support'}: {BO._f(nxt[0][0])}")
    L += ["• Exit    : trailing SL updates · exit before expiry", "Not investment advice."]
    return "\n".join(L)


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


def rescale_for_corporate_actions(st, state, msgs, now, registry=None):
    """Open calls whose stock went ex-split / ex-bonus after the signal: entry / SL / target rescaled once by the verified
    factor (prices now trade in new units). Demerger (no official factor): tracking stops – levels are not comparable."""
    reg = DQ.REGISTRY if registry is None else registry
    keep = []
    for p in st.get("active", []):
        k = str(p.get("key", ""))
        sig_day = pd.Timestamp(k.split("|")[-1][:10]) if k.count("|") >= 2 else None
        drop = False
        for e in reg.get(p["name"], []):
            tag = str(e["ex"].date())
            if sig_day is None or not (sig_day < e["ex"] <= now.normalize()) or tag in p.get("ca_rescaled", []):
                continue
            p.setdefault("ca_rescaled", []).append(tag)
            f = e.get("price_factor")
            if e["type"] == "market":
                continue
            if f is None:
                msgs.append(f"ℹ️ {p['name']}: {e['type']} on {tag} – no official price factor, the open call's levels are no "
                            "longer comparable; tracking stopped (manage it manually).")
                for L in state.get("ledger", []):
                    if L.get("key") in (p.get("key"), k + "|OPT") and L["status"] == "OPEN":
                        L.update(status="CLOSED", exit=None, note=f"{e['type']} – untracked", closed=str(now))
                DQ.shadow_event(st, p.get("key"), now, status="closed", exit_price=None, exit_time=str(now),
                                exit_reason=f"{e['type']} – untracked", flags=["no comparable exit price"])
                drop = True
                break
            DQ.apply_ca_to_call(p, state, st, e, tag)
            msgs.append(f"ℹ️ {p['name']}: {e['type']} on {tag} (price ×{float(f):g}) – open call levels rescaled: "
                        f"entry {BO._f(p['entry'])} · SL {BO._f(p['stop'])} · lot ×{e.get('adj_factor', 1 / float(f)):g} "
                        "(risk per lot and R:R unchanged)")
        if not drop:
            keep.append(p)
    st["active"] = keep


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
    rescale_for_corporate_actions(st, state, msgs, now)
    if st["active"] and (engine.is_open("NFO", now) or engine._just_closed("NFO", now)):
        try:
            q = api.quotes({"NFO": [p["token"] for p in st["active"]]})
        except Exception:
            q = {}
        keep = []
        for p in st["active"]:
            s = 1 if p["side"] == "BUY" else -1
            ltp = (q.get(p["token"]) or {}).get("ltp")
            if p.get("pending"):
                verdict, note = validate_pending(p, ltp, now, quote=q.get(p["token"]) or {})
                if verdict == "wait":
                    if note:
                        print("[stock pending]", note)
                    keep.append(p); continue
                msgs.append(note)
                if verdict == "cancel":
                    for L in state.get("ledger", []):
                        if L.get("key") in (p.get("key"), (p.get("key") or "") + "|OPT") and L["status"] == "OPEN":
                            L.update(status="CLOSED", exit=L["entry"], note="cancelled – gap", closed=str(now))
                    DQ.shadow_event(st, p.get("key"), now, status="cancelled", cancel_price=float(ltp), cancel_time=str(now))
                    continue
                p["pending"] = False
                DQ.shadow_event(st, p.get("key"), now, status="active", entry_fill=float(ltp), entry_time=str(now),
                                entry_quote_time=TP.quote_time(q.get(p["token"]) or {}) and str(TP.quote_time(q.get(p["token"]))),
                                entry_basis="first scan LTP after the open – not a broker fill")
                keep.append(p); continue
            if ltp and p.get("target") and s * (ltp - p["target"]) >= 0:
                r = s * (ltp - p["entry"]) / p["risk"]
                msgs.append(f"✅ EXIT – {p['name']} FUT {p['side']} at ~{BO._f(ltp)}: 🎯 TARGET HIT · result {r:+.2f}R")
                BO.close_ledger(state, p.get("key"), float(p["target"]), "target", now)
                DQ.shadow_event(st, p.get("key"), now, status="closed", exit_price=float(p["target"]), exit_time=str(now), exit_reason="target")
                continue
            if ltp and s * (ltp - p["stop"]) <= 0:
                r = s * (ltp - p["entry"]) / p["risk"]
                msgs.append(f"{'✅' if r > 0 else '❌'} EXIT – {p['name']} FUT {p['side']} at ~{BO._f(ltp)}: "
                            f"{'trailing stop' if p['trailed'] else 'stop-loss'} hit · result {r:+.2f}R")
                state["day"].setdefault("outcomes", []).append(dict(name=p["name"], tf="1d", side=p["side"], result=f"stop {r:+.2f}R"))
                BO.close_ledger(state, p.get("key"), float(ltp), "stop", now)
                DQ.shadow_event(st, p.get("key"), now, status="closed", exit_price=float(ltp), exit_time=str(now),
                                exit_reason="trailing stop" if p["trailed"] else "stop", exit_basis="scan LTP – not a broker fill")
            else:
                keep.append(p)
        st["active"] = keep
    if STOCK3H_ENABLED and engine.is_open("NFO", now):
        manage3h_quotes(api, st, msgs, state)
    if engine.is_open("NFO", now):                            # 30-Oct: LIVE trigger / stop / target messages for stock setups
        try:
            CS.live_watch(state, msgs, api, now)
        except Exception as e_:
            print(f"[setup] live watch skipped: {type(e_).__name__}: {e_}")
    blk = last_block_end(now)
    if blk is None or st["last_block"] == blk:
        rep["stocks"]["scan"] = "stock scans run after 12:15 (3h) and after the 15:30 close (3h + daily)"
        return
    daily_block = blk.endswith("15:30:00")
    if not daily_block and not STOCK3H_ENABLED and not CS.ENABLED.get("STK_SWEEP3H"):
        st["last_block"] = blk
        return
    prog = st.get("progress") or {}
    if prog.get("blk") != blk:
        prog = dict(blk=blk, done=[])
    st["progress"] = prog                                  # saved with the state even if a later step fails
    found, complete, t0 = 0, True, time.monotonic()
    qoi = {}
    if daily_block:                                         # live quote OI to cross-check the daily OI (flag only)
        try:
            qq = api.quotes({"NFO": [c["token"] for n, c in uni.items() if n not in prog["done"]]}) or {}
            qoi = {t: v.get("opnInterest") for t, v in qq.items()}
        except Exception:
            qoi = {}
    for name, c in uni.items():
        if name in prog["done"]:
            continue
        if time.monotonic() - t0 > SCAN_BUDGET_SEC:
            complete = False
            break
        prog["done"].append(name)

        def _fetch(_c=c):
            try:
                h_ = api.candles("NFO", _c["token"], "ONE_HOUR", now - pd.Timedelta(days=400 if daily_block else 200), now)
                oi_ = (api.oi_history("NFO", _c["token"], "ONE_DAY", now - pd.Timedelta(days=60), now)
                       if daily_block and hasattr(api, "oi_history") else None)
            except Exception:
                h_, oi_ = None, None
            return h_, oi_
        h, oi = _fetch()
        blocked = lambda: hasattr(api, "failfast") and api.failfast()
        if (h is None or h.empty) and blocked() and hasattr(api, "wait_clear") and api.wait_clear():
            h, oi = _fetch()                                   # 29-Oct: wait out an Angel rate-limit pause once, then retry
        if h is None or h.empty:
            if blocked():                                      # still blocked: this stock was NOT scanned -> resume next
                prog["done"].remove(name)                      # cycle (was: counted as done, the 12:15 scan of 29-Oct
                complete = False                               # skipped all 207 stocks and reported "done")
                break
            continue
        h = engine.closed(h.sort_values("time").drop_duplicates("time").reset_index(drop=True), "NFO", 60, now)
        try:                                                    # 29-Oct: option idea when a proven stock setup triggers
            from obuy import improve as IMP
            CS.OPTION_HOOK = lambda r, _h=h: IMP.option_for_futures_call(
                api, master, r["name"], 1 if r["side"] == "BUY" else -1, r["entry"], r["stop"], r["target"], now,
                daily=BO.daily_candles(_h, None).iloc[:-1], hold_days=3)
        except Exception:
            CS.OPTION_HOOK = None
        if CS.ENABLED.get("STK_SWEEP3H"):                       # 29-Oct (approved, live): 3h equal-highs sweep SELL
            try:
                CS.OI_NOTE = None                                # never carry another stock's OI text
                CS.on_stock_3h(state, msgs, name, c, frame3h(h), now,
                               lambda day, _c=c, _h=h: prev_oi_label(api, _c, _h, day, now),
                               lambda t0, t1, _c=c: sweep_oi_change(api, _c, t0, t1))
            except Exception as e_:
                print(f"[setup] STK_SWEEP3H {name} skipped: {type(e_).__name__}: {e_}")
        if STOCK3H_ENABLED:
            try:
                found += scan3h(name, c, h, frame3h(h), now, master, st, state, msgs)
            except Exception as e:
                rep.setdefault("errors3h", []).append(f"{name}: {type(e).__name__}")
        if not daily_block:
            continue
        d = daily_with_oi(h, oi)
        d, h, dq = DQ.reconcile(name, d, h)
        if dq["holds"]:
            st.setdefault("dq_holds", {})[name] = dict(time=str(now), reasons=dq["holds"])
            rep.setdefault("stock_skips", []).append(f"{name}: data hold – {'; '.join(dq['holds'])}")
        else:
            st.setdefault("dq_holds", {}).pop(name, None)
        d = DQ.validate_daily_oi(d, qoi.get(c["token"]), dq["ca_days"])
        for p in [p for p in st["active"] if p["name"] == name]:
            s_ = 1 if p["side"] == "BUY" else -1
            new = d[d["time"] > pd.Timestamp(p["last_candle"])]
            if len(new) and p.get("target"):
                p["n"] += len(new); p["last_candle"] = str(d["time"].iloc[-1])
            elif len(new):
                p["best"] = (max if s_ > 0 else min)([p["best"], *new["close"].tolist()])
                p["n"] += len(new)
                p["last_candle"] = str(d["time"].iloc[-1])
                a = float(I.atr(d, 14).iloc[-1])
                ns = p["best"] - s_ * CFG["trail_atr"] * a
                if s_ * (ns - p["stop"]) > 0.25 * a:
                    p["stop"], p["trailed"] = round(ns, 2), True
                    msgs.append(f"🔁 TRAIL UPDATE – {name} FUT {p['side']} · new stop {BO._f(p['stop'])} · "
                                f"open {s_ * (p['best'] - p['entry']) / p['risk']:+.1f}R")
            if now.normalize() >= pd.Timestamp(p["expiry"]) or p["n"] >= p.get("max_days", CFG["max_days"]):
                px = float(d["close"].iloc[-1])
                r = s_ * (px - p["entry"]) / p["risk"]
                msgs.append(f"⏹ EXIT – {name} FUT {p['side']} at ~{BO._f(px)}: "
                            f"{'expiry day – exit (or roll with the same stop)' if p['n'] < p.get('max_days', CFG['max_days']) else 'time exit'} · {r:+.2f}R")
                BO.close_ledger(state, p.get("key"), px, "expiry/time exit", now)
                DQ.shadow_event(st, p.get("key"), now, status="closed", exit_price=px, exit_time=str(now),
                                exit_reason="expiry/time exit", exit_basis="daily close")
                st["active"] = [x for x in st["active"] if x is not p]
        try:                                                # 29-Oct (approved, live): daily hanging-man SELL setup
            CS.OI_NOTE = CS.oi_from_daily(d)                # 30-Oct: OI line in the setup / entry messages
            CS.on_stock_daily(state, msgs, name, c, d, now, allow_new=not dq["holds"] and not first_session_after_expiry(d["time"].iloc[-1]))
        except Exception as e_:
            print(f"[setup] {name} skipped: {type(e_).__name__}: {e_}")
        if len(d) < 30:
            continue
        last = str(d["time"].iloc[-1])
        k = f"STKOI|{name}"
        if state["last_eval"].get(k) == last:
            continue
        state["last_eval"][k] = last
        if dq["holds"]:
            continue                                        # suppressed until the data is verified / corrected
        sig = evaluate(d)
        if sig.get("oi_blocked"):
            rep.setdefault("stock_skips", []).append(f"{name}: breakout not confirmed – {sig['why']}")
        if not sig["side"] and BEAR_ENGULF_ENABLED:
            be = evaluate_bear_engulf(d)
            if be["side"]:
                sig = be
        if not sig["side"] or first_session_after_expiry(sig["candle"]) or any(p["name"] == name for p in st["active"]):
            continue
        cc = dict(symbol=c["symbol"], expiry=c["expiry"])
        k_ = sig.get("k", CFG["stop_atr"])
        plan = TP.futures_plan(name=name, ex="NFO", contract=c["symbol"], tf="1d", side=sig["side"], signal_time=sig["candle"],
                               signal_close=sig.get("close"), atr=sig.get("atr"), stop_mult=k_, target_r=sig.get("tr") or None,
                               tick=c.get("tick"), lot=c["lot"], mult=c["lot"], max_sl_pct=MAX_SL_PCT, live=None, now=now,
                               require_live=False)
        if not plan["valid"]:
            rep.setdefault("stock_skips", []).append(f"{name}: {plan['reason']}"); continue
        lv = S.levels(d, h, sig["close"], sig["atr"])
        msgs.append(BO.call_msg(name, "NFO", cc, "1d", sig, lv, lot=c["lot"], plan=plan))
        key = f"{name}|1dSTK|{last}"
        # entry = today's close; the call becomes ACTIVE only if tomorrow's opening price is still inside the entry zone
        st["active"].append(dict(name=name, token=c["token"], expiry=c["expiry"], side=sig["side"], entry=plan["entry"],
                                 stop=plan["sl"], risk=plan["risk_unit"], target=plan["target"], tick=plan["tick"], atr=float(sig["atr"]),
                                 max_days=sig.get("max_days", CFG["max_days"]), pending=True, lot=c["lot"],
                                 best=plan["entry"], trailed=False, n=0, last_candle=last, key=key))
        RP.add(state, key=key, mark_key=c["token"], seg="NSE", cat="FUTURES", name=name, symbol=c["symbol"], type="Positional",
               side=sig["side"], entry=plan["entry"], sl=plan["sl"], target=plan["target"], tick=plan["tick"],
               lot=c["lot"], mult=c["lot"], time=str(now))
        if sig["side"] == "BUY" and not sig.get("pattern"):  # shadow log – the +2–4 % label never changes this call
            DQ.shadow_add(st, key=key, name=name, sig=sig, plan=plan, lot=c["lot"], now=now, oi_flags=d["oi_flags"].iloc[-1] or "")
        opt = BO.option_idea(master, name, "NFO", plan["entry"], sig["side"], "1d", now)
        why_ = reason_engulf(name, sig, lv) if sig.get("pattern") else reason_msg(name, sig, lv)
        why_ = why_.replace("Not investment advice.", f"• Entry   : next open must be within {TP.MAX_CHASE_ATR} ATR of {TP.fmt(plan['entry'], plan['tick'])} "
                            "– otherwise the call is cancelled at 09:17\nNot investment advice.")
        if opt:
            ok, prem, onotes, oskip = OF.check(api, "NFO", name, opt, plan["entry"], d, now)
            oplan = TP.option_plan(premium=prem, sl_pct=BO.OPT_SL_TG["1d"][0], tg_pct=BO.OPT_SL_TG["1d"][1], tick=opt.get("tick"),
                                   lot=opt["lot"]) if ok else dict(valid=False, reason=oskip)
            if not oplan["valid"]:
                why_ = why_.replace("Not investment advice.", f"• Option  : no option-buy call – {oplan['reason']}\nNot investment advice.")
            else:
                why_ = why_.replace("Not investment advice.", f"• Option  : {' · '.join(onotes)}\nNot investment advice.")
                msgs.append(BO.option_msg(name, "NFO", "1d", sig, opt, oplan["entry"], oplan=oplan)[0])
                RP.add(state, key=key + "|OPT", mark_key=c["token"], seg="NSE", cat="OPTION BUY", name=name, symbol=opt["symbol"],
                       type="Positional", side="BUY", entry=oplan["entry"], sl=oplan["sl"], target=oplan["target"], tick=oplan["tick"],
                       lot=opt["lot"], mult=opt["lot"], time=str(now), und_entry=plan["entry"], und_side=sig["side"])
        msgs.append(why_)
        state["day"]["alerts"] += 1
        found += 1
        if hasattr(api, "api"):
            time.sleep(0.1)
    if complete:
        st["last_block"] = blk
        st.pop("progress", None)
    if daily_block:
        rep["stocks"]["candle_setups"] = CS.summary(state)
    if daily_block and st.get("shadow"):
        rep["stocks"]["shadow_OI_2_4"] = DQ.shadow_summary(st)
    if st.get("dq_holds"):
        rep["stocks"]["data_holds"] = sorted(st["dq_holds"])
    left = len([n for n in uni if n not in prog["done"]])
    rep["stocks"].update(scan=(f"{'3h + daily' if daily_block else '3h'} scan of {len(uni)} stock futures done" if complete else
                               f"stock scan paused (time budget or Angel rate limit) – {left} stocks left, continues next cycle"),
                         new_calls=found)
