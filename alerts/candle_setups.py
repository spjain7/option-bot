"""CANDLE SETUP calls – LIVE (owner approved 29-Oct-2026, "do live not in log mode"). Alerts only, no orders.
Research: branch exp/strategy-program-001, research/program/REPORT.md (DCP-001, EMAX-003, RR1, verify_exits).

  MCX_HAMMER   MCX daily hammer -> BUY above the hammer's high (stop-buy, valid 3 sessions). Stop 0.05 ATR below the
               hammer's low, target 2R from the entry, exit after 20 sessions. Backtest 2022-26 after costs: +0.36R per
               trade, 52 % wins, 333 trades, every year and all 7 commodities positive (with downtrend: +0.31R, 102).
  STK_HANGMAN  Stock futures daily hanging man in an uptrend (EMA20 > EMA50) -> SELL below its low (stop-sell, valid
               3 sessions). Stop 0.05 ATR above its high, target 2R, 20 sessions. Backtest +0.18R, 44 % wins, 1,217 trades.
               Follow-ups are sent after the 15:30 close (daily candles), so place the stop-loss and target as orders.
  MCX_EMA1348  MCX 3-hour EMA13 crosses above EMA48 with ADX(14) ≥ 20 and rising -> BUY at the next 3-hour open.
               Exit at the next open after EMA13 closes back below EMA48; safety stop 3 ATR; max 120 candles.
               Backtest +0.67R, 48 % wins – but only 79 trades and mostly GOLD: labelled "small sample".

Shape: lower wick ≥ 2× body, upper wick ≤ 0.3× range. Tracking: MCX on completed 15-minute candles (daily candles if
15-minute data is missing), stocks on completed daily candles. Gap through stop/target fills at the open; if one candle
touches both, the stop is counted (cautious). A contract change closes the call at the last price.

HOURLY_SKIP: rule for any future 1-hour candle-pattern call – no pattern candle starting 14:15 or 15:15 (NSE). In 2022-26
they won 44-48 % against 51-55 % for the rest of the day and caused about two-thirds of the 1-hour stock loss.
"""
import numpy as np
import pandas as pd
from crude import indicators as I
from alerts import tradeplan as TP, report as RP

ENABLED = {"MCX_HAMMER": True, "STK_HANGMAN": True, "MCX_EMA1348": True}
HOURLY_SKIP = ("14:15", "15:15")
KEEP_CLOSED = 600
P = dict(entry_window=3, stop_buf_atr=0.05, target_r=2.0, max_days=20, max_stop_pct=6.0)
EMA = dict(fast=13, slow=48, adx_min=20.0, adx_lookback=3, stop_atr=3.0, max_candles=120)
WARN = "Alert only – no auto trade. Not investment advice."
STATS = {
    "MCX_HAMMER": "Backtest 2022-26 after costs: +0.36R per trade, 52% wins, 333 trades; every year and all 7 commodities positive.",
    "STK_HANGMAN": "Backtest 2022-26 after costs: +0.18R per trade, 44% wins, 1,217 trades (flat in 2023 and 2025).",
    "MCX_EMA1348": "Backtest 2022-26 after costs: +0.67R per trade, 48% wins – SMALL SAMPLE (79 trades, mostly GOLD). Use small size.",
}
TITLE = {"MCX_HAMMER": "DAILY HAMMER BREAKOUT", "STK_HANGMAN": "DAILY HANGING-MAN BREAKDOWN", "MCX_EMA1348": "3-HOUR EMA 13/48 CROSS"}
LINE = "━━━━━━━━━━━━━━━━━━"


def hourly_pattern_allowed(candle_start):
    """False for 1-hour pattern candles starting 14:15 or 15:15 (see HOURLY_SKIP)."""
    return pd.Timestamp(candle_start).strftime("%H:%M") not in HOURLY_SKIP


def _store(state):
    s = state.setdefault("candle_setups", dict(open=[], closed=[], seen=[]))
    for k in ("open", "closed", "seen"):
        s.setdefault(k, [])
    return s


def hammer_shape(df):
    o, h, l, c = (df[x].astype(float) for x in ("open", "high", "low", "close"))
    body, rng = (c - o).abs(), h - l
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    return (rng > 0) & (lw >= 2 * body) & (uw <= 0.3 * rng)


def trend_flags(df):
    c = df["close"].astype(float)
    e20, e50 = I.ema(c, 20), I.ema(c, 50)
    return (e20 < e50) & (c.shift(1) < e50.shift(1)), (e20 > e50) & (c.shift(1) > e50.shift(1))


def _f(r, x):
    return TP.fmt(float(x), r.get("tick") or 0.05)


def _who(r):
    return f"{r['name']} FUT ({'MCX' if r['setup'].startswith('MCX') else 'NSE'})"


def _rs(r, pts):
    return f"₹{abs(pts) * (r.get('mult') or 1):,.0f}"


# ─────────────── messages ───────────────
def setup_msg(r):
    buy = r["side"] == "BUY"
    risk = abs(r["trigger"] - r["stop"])
    tgt = r["trigger"] + (2 if buy else -2) * risk
    return (f"{'🟢 BUY' if buy else '🔴 SELL'} SETUP – {_who(r)} · {TITLE[r['setup']]}\n{LINE}\n"
            f"Contract : {r['contract']} · pattern candle {pd.Timestamp(r['pattern_time']):%d-%b-%Y}\n"
            f"Candle   : O {_f(r, r['pattern']['open'])} H {_f(r, r['pattern']['high'])} L {_f(r, r['pattern']['low'])} "
            f"C {_f(r, r['pattern']['close'])} · volume {r.get('vol_x') or 0:.1f}× avg\n"
            f"• {'BUY above ' if buy else 'SELL below'} : {_f(r, r['trigger'])}  (stop-{'buy' if buy else 'sell'} order, valid next 3 sessions)\n"
            f"• Stop-loss  : {_f(r, r['stop'])}\n"
            f"• Target 2R  : {_f(r, tgt)}  (2× risk from the entry; reset if price gaps past the trigger)\n"
            f"• Risk       : {_f(r, risk)} pts ({risk / r['trigger'] * 100:.2f}%) · {_rs(r, risk)} per lot\n"
            f"• Time exit  : after 20 sessions if neither stop nor target is hit\n"
            f"• Trend      : {('downtrend (EMA20 < EMA50)' if buy else 'uptrend (EMA20 > EMA50)') if r.get('trend_ok') else 'no prior downtrend (pattern only)'}\n"
            f"{STATS[r['setup']]}\n"
            + ("Follow-ups for stock calls are sent after the 15:30 close – keep the stop-loss and target as orders.\n"
               if r["setup"] == "STK_HANGMAN" else "")
            + WARN)


def ema_msg(r, live=None):
    return (f"🟢 BUY – {_who(r)} · {TITLE['MCX_EMA1348']}\n{LINE}\n"
            f"Contract : {r['contract']} · 3-hour candle {pd.Timestamp(r['pattern_time']):%d-%b %H:%M} closed with EMA13 above EMA48\n"
            f"• Entry      : at market now (~{_f(r, live or r['cross_close'])}); tracked from the next 3-hour open\n"
            f"• Safety SL  : 3 ATR below the entry (~{_f(r, (live or r['cross_close']) - EMA['stop_atr'] * r['atr'])}); exact level sent at entry\n"
            f"• Exit       : when EMA13 closes back below EMA48 on the 3-hour chart – an exit alert will follow\n"
            f"• Target     : none fixed (trend-following; winners averaged about 2R)\n"
            f"• ADX(14)    : {r['adx']} and rising\n"
            f"{STATS['MCX_EMA1348']}\n{WARN}")


def entry_msg(r, gapped):
    return (f"✅ TRIGGERED – {_who(r)} {r['side']} ({TITLE[r['setup']].lower()}) at {_f(r, r['entry'])}"
            + (" (opened beyond the trigger – filled at the open)" if gapped else "")
            + f"\nStop-loss {_f(r, r['stop'])}" + (f" · target {_f(r, r['target'])}" if r.get("target") else
                                                   " · exit on the opposite EMA cross")
            + f" · risk {_rs(r, r['risk'])} per lot. {WARN}")


def exit_msg(r):
    g = r.get("gross_pts")
    if r.get("entry") is None or r.get("exit") is None:
        return f"⏹ CANCELLED – {_who(r)} {r['side']} setup from {pd.Timestamp(r['pattern_time']):%d-%b}: {r['exit_reason']}."
    icon = "✅" if (g or 0) > 0 else "❌" if (g or 0) < 0 else "➖"
    return (f"{icon} EXIT – {_who(r)} {r['side']} ({TITLE[r['setup']].lower()}) at {_f(r, r['exit'])}: {r['exit_reason']} · "
            f"{r.get('gross_R', 0):+.2f}R · {'+' if (g or 0) >= 0 else '−'}{_rs(r, g or 0)} per lot before costs")


# ─────────────── tracking ───────────────
def _close(s, msgs, state, r, px, t, why, now):
    sd = 1 if r["side"] == "BUY" else -1
    r.update(status="closed", exit=None if px is None else round(float(px), 4), exit_time=str(t), exit_reason=why)
    if px is not None and r.get("entry") is not None and r.get("risk"):
        r["gross_pts"] = round(sd * (float(px) - r["entry"]), 4)
        r["gross_R"] = round(r["gross_pts"] / r["risk"], 3)
        for L in state.get("ledger", []):
            if L.get("key") == r["key"] and L["status"] == "OPEN":
                L.update(status="CLOSED", exit=round(float(px), 2), note=why[:24], closed=str(now))
    s["closed"] = (s["closed"] + [r])[-KEEP_CLOSED:]
    if ENABLED.get(r["setup"]):
        msgs.append(exit_msg(r))
    print(f"[setup] {r['setup']} {r['name']} {r['side']} closed: {why} {px} ({r.get('gross_R')}R gross)")


def _enter(state, msgs, r, e0, t, gapped):
    sd = 1 if r["side"] == "BUY" else -1
    risk = sd * (e0 - r["stop"])
    r.update(status="open", entry=round(e0, 4), entry_time=str(t), risk=round(risk, 4))
    if r["setup"] != "MCX_EMA1348":
        r["target"] = round(e0 + sd * P["target_r"] * risk, 4)
    RP.add(state, key=r["key"], mark_key=r.get("token"), seg="MCX" if r["setup"].startswith("MCX") else "NSE", cat="FUTURES",
           name=r["name"], symbol=r["contract"], type=TITLE[r["setup"]].title(), side=r["side"], entry=r["entry"], sl=r["stop"],
           target=r.get("target"), tick=r.get("tick"), lot=r.get("lot"), mult=r.get("mult"), time=str(t))
    if ENABLED.get(r["setup"]):
        msgs.append(entry_msg(r, gapped))
    print(f"[setup] {r['setup']} {r['name']} {r['side']} entered {e0} stop {r['stop']} target {r.get('target')}")


def _sessions_after(daily, t):
    """Completed daily candles strictly after the day of t."""
    if daily is None or not len(daily):
        return 0
    return int((daily["time"].dt.normalize() > pd.Timestamp(t).normalize()).sum())


def _step_pattern(state, msgs, r, bars, daily, now):
    """bars: completed candles (15-minute for MCX, daily for stocks). Returns (done, px, t, why)."""
    sd = 1 if r["side"] == "BUY" else -1
    day0 = pd.Timestamp(r["pattern_time"]).normalize()
    new = bars[(bars["time"] > pd.Timestamp(r["last_bar"])) & (bars["time"].dt.normalize() > day0)]
    window_end = None
    if daily is not None and len(daily):
        after = daily[daily["time"].dt.normalize() > day0]["time"].dt.normalize()
        if len(after) >= P["entry_window"]:
            window_end = after.iloc[P["entry_window"] - 1]
    prev_day = None
    for b in new.itertuples():
        r["last_bar"] = str(b.time)
        o, h, l, c = float(b.open), float(b.high), float(b.low), float(b.close)
        newday = prev_day is None or pd.Timestamp(b.time).normalize() != prev_day
        prev_day = pd.Timestamp(b.time).normalize()
        st = r["stop"]
        if r["status"] == "pending":
            if window_end is not None and pd.Timestamp(b.time).normalize() > window_end:
                return True, None, b.time, "no breakout within 3 sessions"
            trig = r["trigger"]
            if sd * (o - trig) > 0:
                if sd * (o - st) <= 0:
                    return True, None, b.time, "opened beyond the stop"
                _enter(state, msgs, r, o, b.time, True)
            elif (l <= st) if sd > 0 else (h >= st):
                return True, None, b.time, "stop level touched before the breakout"
            elif (h > trig) if sd > 0 else (l < trig):
                _enter(state, msgs, r, trig, b.time, False)
                if (h >= r["target"]) if sd > 0 else (l <= r["target"]):
                    return True, r["target"], b.time, "🎯 target 2R"
                continue
            else:
                continue
            newday = False
        tp = r["target"]
        if newday:
            if sd * (o - st) <= 0:
                return True, o, b.time, "stop-loss (gap)"
            if sd * (o - tp) >= 0:
                return True, o, b.time, "🎯 target 2R (gap)"
        if (l <= st) if sd > 0 else (h >= st):
            return True, st, b.time, "stop-loss"
        if (h >= tp) if sd > 0 else (l <= tp):
            return True, tp, b.time, "🎯 target 2R"
    if r["status"] == "pending" and _sessions_after(daily, r["pattern_time"]) >= P["entry_window"]:
        return True, None, now, "no breakout within 3 sessions"
    if r["status"] == "open" and _sessions_after(daily, r["entry_time"]) >= P["max_days"] - 1:
        return True, float(daily["close"].iloc[-1]), daily["time"].iloc[-1], "time exit (20 sessions)"
    return False, None, None, None


def _ema_feats(df):
    c = df["close"].astype(float)
    ef, es = I.ema(c, EMA["fast"]), I.ema(c, EMA["slow"])
    return (ef > es) & (ef.shift(1) <= es.shift(1)), (ef < es) & (ef.shift(1) >= es.shift(1)), I.adx(df, 14)


def _step_ema(state, msgs, r, f3, c15, now):
    up, dn, ax = _ema_feats(f3)
    for k in np.flatnonzero((f3["time"] > pd.Timestamp(r["last_candle"])).values):
        b = f3.iloc[k]
        o = float(b["open"])
        if r["status"] == "pending":
            r["stop"] = round(o - EMA["stop_atr"] * r["atr"], 4)
            _enter(state, msgs, r, o, b["time"], False)
            r["n"] = 0
        elif r.get("exit_next_open"):
            return True, o, b["time"], "EMA13 closed back below EMA48"
        elif o <= r["stop"]:
            return True, o, b["time"], "safety stop (gap)"
        r["last_candle"] = str(b["time"])
        r["n"] = r.get("n", 0) + 1
        if float(b["low"]) <= r["stop"]:
            return True, r["stop"], b["time"], "safety stop 3 ATR"
        if bool(dn.iloc[k]):
            r["exit_next_open"] = True
            if ENABLED.get("MCX_EMA1348"):
                msgs.append(f"⚠️ {_who(r)} BUY (3-hour EMA 13/48): EMA13 closed below EMA48 – exit at the next open "
                            f"(~{_f(r, float(b['close']))}). {WARN}")
        if r["n"] >= EMA["max_candles"]:
            return True, float(b["close"]), b["time"], "time exit (120 candles)"
    if r["status"] == "open" and c15 is not None and len(c15):     # safety stop between 3-hour closes
        x = c15[c15["time"] > pd.Timestamp(r["last_bar"])] if r.get("last_bar") else c15[c15["time"] >= pd.Timestamp(r["entry_time"])]
        for b in x.itertuples():
            r["last_bar"] = str(b.time)
            if float(b.low) <= r["stop"]:
                return True, min(float(b.open), r["stop"]), b.time, "safety stop 3 ATR"
    return False, None, None, None


def _manage(state, msgs, s, setup, name, contract, bars, daily, now, f3=None):
    keep = []
    for r in s["open"]:
        if r["setup"] != setup or r["name"] != name:
            keep.append(r); continue
        if contract and r.get("contract") and r["contract"] != contract:
            px_ = r.get("last_px", r.get("entry")) if r["status"] == "open" else None
            _close(s, msgs, state, r, px_, now,
                   "contract changed – closed at the last price" if r["status"] == "open" else "contract changed", now)
            continue
        try:
            if setup == "MCX_EMA1348":
                done, px, t, why = _step_ema(state, msgs, r, f3, bars, now)
            else:
                done, px, t, why = _step_pattern(state, msgs, r, bars, daily, now)
        except Exception as e:
            print(f"[setup] {setup} {name} step error: {type(e).__name__}: {e}")
            keep.append(r); continue
        src = bars if bars is not None and len(bars) else f3
        if src is not None and len(src):
            r["last_px"] = float(src["close"].iloc[-1])
        if done:
            _close(s, msgs, state, r, px, t, why, now)
        else:
            keep.append(r)
    s["open"] = keep


def _new_pattern(state, msgs, s, setup, name, c, side, df, now, mult, lot):
    if not ENABLED.get(setup) or any(r["setup"] == setup and r["name"] == name for r in s["open"]):
        return
    if df is None or len(df) < 60:
        return
    i = len(df) - 1
    if not bool(hammer_shape(df).iloc[i]):
        return
    down, up = trend_flags(df)
    tr = bool((down if side == "BUY" else up).iloc[i])
    if setup == "STK_HANGMAN" and not tr:
        return
    sid = f"{setup}|{name}|{df['time'].iloc[i]}"
    if sid in s["seen"]:
        return
    s["seen"] = (s["seen"] + [sid])[-3000:]
    a = float(I.atr(df, 14).iloc[i])
    if not a > 0:
        return
    sd = 1 if side == "BUY" else -1
    hi, lo = float(df["high"].iloc[i]), float(df["low"].iloc[i])
    stop = lo - P["stop_buf_atr"] * a if sd > 0 else hi + P["stop_buf_atr"] * a
    trig = hi if sd > 0 else lo
    if abs(trig - stop) / trig * 100 > P["max_stop_pct"]:
        print(f"[setup] {setup} {name}: stop {abs(trig - stop) / trig * 100:.1f}% away – not sent"); return
    tick = c.get("tick") or 0.05
    v = df["volume"].astype(float)
    va = v.rolling(20).mean().shift(1).iloc[i]
    r = dict(setup=setup, name=name, contract=c["symbol"], token=c.get("token"), side=side, status="pending",
             pattern_time=str(df["time"].iloc[i]),
             pattern=dict(open=float(df["open"].iloc[i]), high=hi, low=lo, close=float(df["close"].iloc[i])),
             trigger=TP.tick_round(trig, tick), stop=TP.tick_round(stop, tick, "down" if sd > 0 else "up"), atr=round(a, 4), tick=tick, mult=mult, lot=lot,
             trend_ok=tr, vol_x=round(float(v.iloc[i] / va), 2) if va and va > 0 else None,
             last_bar=str(df["time"].iloc[i]), logged=str(now), key=f"{setup}|{name}|{str(df['time'].iloc[i])[:10]}")
    s["open"].append(r)
    msgs.append(setup_msg(r))
    print(f"[setup] {setup} {name} {side} pattern {r['pattern_time']}: trigger {r['trigger']} stop {r['stop']} trend {tr}")


def _new_ema(state, msgs, s, name, c, f3, now, mult, live):
    if not ENABLED.get("MCX_EMA1348") or any(r["setup"] == "MCX_EMA1348" and r["name"] == name for r in s["open"]):
        return
    if f3 is None or len(f3) < 120:
        return
    up, dn, ax = _ema_feats(f3)
    i = len(f3) - 1
    if not bool(up.iloc[i]) or not (ax.iloc[i] >= EMA["adx_min"] and ax.iloc[i] > ax.iloc[i - EMA["adx_lookback"]]):
        return
    sid = f"MCX_EMA1348|{name}|{f3['time'].iloc[i]}"
    if sid in s["seen"]:
        return
    s["seen"] = (s["seen"] + [sid])[-3000:]
    r = dict(setup="MCX_EMA1348", name=name, contract=c["symbol"], token=c.get("token"), side="BUY", status="pending",
             pattern_time=str(f3["time"].iloc[i]), cross_close=float(f3["close"].iloc[i]), atr=round(float(I.atr(f3, 14).iloc[i]), 4),
             adx=round(float(ax.iloc[i]), 1), tick=c.get("tick") or 1.0, mult=mult, lot=c.get("lot"),
             last_candle=str(f3["time"].iloc[i]), logged=str(now), key=f"MCX_EMA1348|{name}|{f3['time'].iloc[i]}")
    s["open"].append(r)
    msgs.append(ema_msg(r, live))
    print(f"[setup] MCX_EMA1348 {name} BUY cross {r['pattern_time']} ADX {r['adx']}")


# ─────────────── entry points ───────────────
def on_mcx(state, msgs, name, ex, c, daily, three_h, c15, now, live=None):
    """From alerts.engine._breakouts (MCX only): completed daily, 3-hour and 15-minute candles of the current contract."""
    if ex != "MCX":
        return
    s = _store(state)
    mult = RP.mult_for(name, ex, c.get("lot"))
    if daily is not None and len(daily) >= 60:
        bars = c15 if c15 is not None and len(c15) else daily
        _manage(state, msgs, s, "MCX_HAMMER", name, c["symbol"], bars, daily, now)
        _new_pattern(state, msgs, s, "MCX_HAMMER", name, c, "BUY", daily, now, mult, c.get("lot"))
    if three_h is not None and len(three_h) >= 120:
        _manage(state, msgs, s, "MCX_EMA1348", name, c["symbol"], c15, daily, now, f3=three_h)
        _new_ema(state, msgs, s, name, c, three_h, now, mult, live)


def on_stock_daily(state, msgs, name, c, d, now, allow_new=True):
    """From alerts.stocks.scan after the 15:30 close: completed, data-checked daily candles."""
    if d is None or not len(d):
        return
    s = _store(state)
    _manage(state, msgs, s, "STK_HANGMAN", name, c["symbol"], d, d, now)
    if allow_new:
        _new_pattern(state, msgs, s, "STK_HANGMAN", name, c, "SELL", d, now, int(c.get("lot") or 1), c.get("lot"))


def summary(state):
    s = state.get("candle_setups") or {}
    out = {}
    for setup in ENABLED:
        cl = [r for r in s.get("closed", []) if r["setup"] == setup and r.get("gross_R") is not None]
        op = [r for r in s.get("open", []) if r["setup"] == setup]
        out[setup] = dict(waiting=sum(r["status"] == "pending" for r in op), open=sum(r["status"] == "open" for r in op),
                          closed=len(cl), wins=sum(r["gross_R"] > 0 for r in cl),
                          avg_gross_R=round(float(np.mean([r["gross_R"] for r in cl])), 3) if cl else None)
    return out
