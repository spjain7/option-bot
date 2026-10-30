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
import itertools
import numpy as np
import pandas as pd
from crude import indicators as I
from alerts import tradeplan as TP, report as RP

ENABLED = {"MCX_HAMMER": True, "STK_HANGMAN": True, "MCX_EMA1348": True, "STK_SWEEP3H": True}
SWEEP15_LOG = True        # 15-minute stock sweep: every sweep is recorded (both sides) for review
SWEEP15_SEND = True       # 29-Oct (owner): SEND the 15-min SELL sweeps that have volume ≥ 1.5× AND OI falling (test phase)
HOURLY_SKIP = ("14:15", "15:15")
OPTION_HOOK = None        # set by alerts.stocks.scan: r -> option-idea message (obuy.improve.option_for_futures_call)
KEEP_CLOSED = 600
P = dict(entry_window=3, stop_buf_atr=0.05, target_r=2.0, max_days=20, max_stop_pct=6.0)
EMA = dict(fast=13, slow=48, adx_min=20.0, adx_lookback=3, stop_atr=3.0, max_candles=120)
WARN = "Alert only – no auto trade. Not investment advice."
STATS = {
    "MCX_HAMMER": "Backtest 2022-26 after costs: +0.36R per trade, 52% wins, 333 trades; every year and all 7 commodities positive.",
    "STK_HANGMAN": "Backtest 2022-26 after costs: +0.18R per trade, 44% wins, 1,217 trades (flat in 2023 and 2025).",
    "STK_SWEEP3H": "Backtest 2022-26 at 1:1 after costs (sweep + volume + previous-day OI not long buildup): 58% wins, +0.15R per trade, "
                   "387 trades, every year positive. The extra 'OI not rising on the sweep candle' check is new (15-min evidence only).",
    "MCX_EMA1348": "Backtest 2022-26 after costs: +0.67R per trade, 48% wins – SMALL SAMPLE (79 trades, mostly GOLD). Use small size.",
}
TITLE = {"MCX_HAMMER": "DAILY HAMMER BREAKOUT", "STK_HANGMAN": "DAILY HANGING-MAN BREAKDOWN", "MCX_EMA1348": "3-HOUR EMA 13/48 CROSS",
         "STK_SWEEP3H": "3-HOUR LIQUIDITY SWEEP (equal highs)"}
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
OI_NOTE = None        # 30-Oct: OI text for the instrument being processed, set by the caller (engine / stocks) before each call


def oi_from_daily(d):
    """Stock daily candles with an 'oi' column -> 'OI 1,23,450 (+3.2 % on the day, price −1.1 %) → Short buildup' or None."""
    try:
        x = d.dropna(subset=["oi"]).tail(2)
        if len(x) < 2 or x["oi"].iloc[0] <= 0:
            return None
        doi = x["oi"].iloc[1] / x["oi"].iloc[0] - 1
        dp = x["close"].iloc[1] / x["close"].iloc[0] - 1
        lab = ("Long buildup" if dp > 0 else "Short buildup") if doi > 0 else ("Short covering" if dp > 0 else "Long unwinding")
        return f"{x['oi'].iloc[1]:,.0f} ({doi * 100:+.1f}% on the day, price {dp * 100:+.2f}%) → {lab}"
    except Exception:
        return None


def _oi_txt(r, key="oi_note"):
    v = r.get(key)
    return f"• OI         : {v}\n" if v else "• OI         : not available\n"


def sr_line(df, side, trig, stop, target_r):
    """30-Oct (owner: "support / resistance must be taken care of in every call"): the nearest opposing level (resistance for a
    BUY, support for a SELL) from real candles (prev-day H/L, pivots, swing highs/lows – alerts.signals.levels), its distance in R
    and whether it lies before the target. -> (text, distance_in_R or None)"""
    try:
        from alerts import signals as S_
        a = float(I.atr(df, 14).iloc[-1])
        lv = S_.levels(df, None, float(trig), a)
        sd = 1 if side == "BUY" else -1
        opp = [x for x in (lv["resistance"] if sd > 0 else lv["support"]) if sd * (x[0] - trig) > 0]
        risk = abs(trig - stop)
        what = "Resistance" if sd > 0 else "Support"
        if not opp or not risk:
            return f"• {what:10s} : none found above the trigger ✅" if sd > 0 else f"• {what:10s} : none found below the trigger ✅", None
        v, nm = opp[0]
        dr = sd * (v - trig) / risk
        if target_r and dr < target_r:
            return (f"• {what:10s} : ⚠️ {v:,.2f} ({nm}) at {dr:.1f}R – BEFORE the {target_r:g}R target; price may stall there "
                    f"(consider booking part there)"), dr
        return f"• {what:10s} : {v:,.2f} ({nm}) at {dr:.1f}R – beyond the {target_r:g}R target ✅" if target_r else \
            f"• {what:10s} : nearest {v:,.2f} ({nm}) at {dr:.1f}R", dr
    except Exception as e:
        return f"• S/R        : not available ({type(e).__name__})", None


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
            + (f"{r['sr']}\n" if r.get("sr") else "") + _oi_txt(r) +
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
            + (f"{r['sr']}\n" if r.get("sr") else "") + _oi_txt(r) +
            f""
            f"• ADX(14)    : {r['adx']} and rising\n"
            f"{STATS['MCX_EMA1348']}\n{WARN}")


def entry_msg(r, gapped):
    return (f"✅ TRIGGERED – {_who(r)} {r['side']} ({TITLE[r['setup']].lower()}) at {_f(r, r['entry'])}"
            + (" (opened beyond the trigger – filled at the open)" if gapped else "")
            + f"\nStop-loss {_f(r, r['stop'])}" + (f" · target {_f(r, r['target'])}" if r.get("target") else
                                                   " · exit on the opposite EMA cross")
            + f" · risk {_rs(r, r['risk'])} per lot\n" + _oi_txt(r, "oi_entry") + WARN)


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
    r.update(status="open", entry=round(e0, 4), entry_time=str(t), risk=round(risk, 4), oi_entry=OI_NOTE)
    if r["setup"] != "MCX_EMA1348":
        r["target"] = round(e0 + sd * r.get("target_r", P["target_r"]) * risk, 4)
    RP.add(state, key=r["key"], mark_key=r.get("token"), seg="MCX" if r["setup"].startswith("MCX") else "NSE", cat="FUTURES",
           name=r["name"], symbol=r["contract"], type=TITLE[r["setup"]].title(), side=r["side"], entry=r["entry"], sl=r["stop"],
           target=r.get("target"), tick=r.get("tick"), lot=r.get("lot"), mult=r.get("mult"), time=str(t))
    if ENABLED.get(r["setup"]):
        msgs.append(entry_msg(r, gapped))
        if OPTION_HOOK is not None and r["setup"] in ("STK_HANGMAN", "STK_SWEEP3H"):
            try:
                m_ = OPTION_HOOK(r)
                if m_:
                    msgs.append(m_)
            except Exception as e_:
                print(f"[opt-idea] {r['name']} skipped: {type(e_).__name__}: {e_}")
    print(f"[setup] {r['setup']} {r['name']} {r['side']} entered {e0} stop {r['stop']} target {r.get('target')}")


LIVE_SETUPS = ("STK_HANGMAN", "STK_SWEEP3H")


def live_watch(state, msgs, api, now):
    """30-Oct (owner: "will I be notified when it's active?"): stock setups are confirmed on completed candles after the close,
    so during NSE hours the live price of every waiting / open stock setup is checked each scan (one quote call) and a LIVE
    message is sent once when the trigger, the stop or the target is crossed. The official entry / exit (and the P&L) is
    still confirmed on the completed candle after the close."""
    s = _store(state)
    rs = [r for r in s["open"] if r["setup"] in LIVE_SETUPS and ENABLED.get(r["setup"]) and r.get("token")]
    if not rs:
        return
    q = api.quotes({"NFO": sorted({str(r["token"]) for r in rs})}) or {}
    for r in rs:
        ltp = float((q.get(str(r["token"])) or {}).get("ltp") or 0)
        if ltp <= 0:
            continue
        sd = 1 if r["side"] == "BUY" else -1
        live = r.setdefault("live", {})
        trig_crossed = r["status"] == "open" or live.get("trigger") or sd * (ltp - r["trigger"]) > 0
        if r["status"] == "pending" and not live.get("trigger") and not live.get("stop") and sd * (ltp - r["trigger"]) > 0:
            live["trigger"] = str(now)
            tgt = r["trigger"] + sd * r.get("target_r", P["target_r"]) * sd * (r["trigger"] - r["stop"])
            msgs.append(f"🔔 LIVE – {_who(r)} {r['side']} setup is ACTIVE: price {_f(r, ltp)} crossed the trigger {_f(r, r['trigger'])}\n"
                        f"Stop-loss {_f(r, r['stop'])} · target ≈ {_f(r, tgt)} ({r.get('target_r', P['target_r']):g}R from the trigger). "
                        f"Confirmed on the completed candle after 15:30. {WARN}")
        elif r["status"] == "pending" and not trig_crossed and not live.get("stop") and sd * (ltp - r["stop"]) <= 0:
            live["stop"] = str(now)
            msgs.append(f"⚠️ LIVE – {_who(r)} {r['side']} setup: price {_f(r, ltp)} reached the stop level {_f(r, r['stop'])} "
                        f"before the trigger – the setup will be cancelled at the close. {WARN}")
        elif trig_crossed:
            tgt = r.get("target") or (r["trigger"] + r.get("target_r", P["target_r"]) * (r["trigger"] - r["stop"]))
            if not live.get("stop") and sd * (ltp - r["stop"]) <= 0:
                live["stop"] = str(now)
                msgs.append(f"❌ LIVE – {_who(r)} {r['side']}: stop-loss {_f(r, r['stop'])} touched (price {_f(r, ltp)}). "
                            f"Final exit confirmed after the close. {WARN}")
            elif not live.get("target") and sd * (ltp - tgt) >= 0:
                live["target"] = str(now)
                msgs.append(f"🎯 LIVE – {_who(r)} {r['side']}: target {_f(r, tgt)} reached (price {_f(r, ltp)}). "
                            f"Final exit confirmed after the close. {WARN}")


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
            elif setup == "STK_SWEEP3H":
                done, px, t, why = _step_bars(state, msgs, r, bars, now)
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
             sr=sr_line(df.iloc[:i + 1], side, trig, stop, P["target_r"])[0], oi_note=OI_NOTE,
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
    _px = float(f3["close"].iloc[i]); _a = float(I.atr(f3, 14).iloc[i])
    r["sr"] = sr_line(f3.iloc[:i + 1], "BUY", _px, _px - EMA["stop_atr"] * _a, None)[0]
    r["oi_note"] = OI_NOTE
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


# ─────────────── liquidity sweep above equal highs (stocks, 3-hour) ───────────────
SW = dict(lookback=40, pivots=6, eq_atr=0.1, vol_x=1.5, entry_window=3, max_candles=20, target_r=1.0)


def equal_high_at(df, i, atr_i):
    """Equal-highs level known BEFORE candle i (same as research/program/sweep.py levels()['EQ']): two pivot highs among
    the last 6 pivots of the previous 40 candles within 0.1 ATR of each other and still the highest high since."""
    if i < 45:
        return np.nan
    hv = df["high"].astype(float).values
    piv = [k - 1 for k in range(i - SW["lookback"], i) if 1 <= k - 1 < len(hv) - 1 and hv[k - 1] > hv[k - 2] and hv[k - 1] > hv[k]]
    out = np.nan
    for x, y in itertools.combinations(piv[-SW["pivots"]:], 2):
        if abs(hv[x] - hv[y]) <= SW["eq_atr"] * atr_i and max(hv[x], hv[y]) >= hv[min(x, y):i].max() - 1e-9:
            out = max(hv[x], hv[y])
    return out


def _step_bars(state, msgs, r, bars, now):
    """Breakout entry within 3 candles, then stop / 1R target / 20 candles – counted in the setup's own candles."""
    sd = 1 if r["side"] == "BUY" else -1
    new = bars[bars["time"] > pd.Timestamp(r["last_bar"])]
    for b in new.itertuples():
        r["last_bar"] = str(b.time)
        o, h, l, c = float(b.open), float(b.high), float(b.low), float(b.close)
        st = r["stop"]
        if r["status"] == "pending":
            r["waited"] = r.get("waited", 0) + 1
            if sd * (o - r["trigger"]) > 0:
                if sd * (o - st) <= 0:
                    return True, None, b.time, "opened beyond the stop"
                _enter(state, msgs, r, o, b.time, True); r["n"] = 0
            elif (l <= st) if sd > 0 else (h >= st):
                return True, None, b.time, "stop level touched before the entry"
            elif (h > r["trigger"]) if sd > 0 else (l < r["trigger"]):
                _enter(state, msgs, r, r["trigger"], b.time, False); r["n"] = 0
            elif r["waited"] >= SW["entry_window"]:
                return True, None, b.time, "no entry within 3 candles"
            else:
                continue
        else:
            if sd * (o - st) <= 0:
                return True, o, b.time, "stop-loss (gap)"
            if sd * (o - r["target"]) >= 0:
                return True, o, b.time, "🎯 target 1R (gap)"
        r["n"] = r.get("n", 0) + 1
        if (l <= st) if sd > 0 else (h >= st):
            return True, st, b.time, "stop-loss"
        if (h >= r["target"]) if sd > 0 else (l <= r["target"]):
            return True, r["target"], b.time, "🎯 target 1R"
        if r["n"] >= SW["max_candles"]:
            return True, c, b.time, "time exit (20 candles)"
    return False, None, None, None


def sweep_msg(r):
    risk = abs(r["stop"] - r["trigger"])
    return (f"🔴 SELL SETUP – {_who(r)} · {TITLE['STK_SWEEP3H']}\n{LINE}\n"
            f"Contract : {r['contract']} · 3-hour candle {pd.Timestamp(r['pattern_time']):%d-%b %H:%M}\n"
            f"Sweep    : high {_f(r, r['pattern']['high'])} went above equal highs {_f(r, r['level'])}, closed back below at "
            f"{_f(r, r['pattern']['close'])}\n"
            f"• SELL below : {_f(r, r['trigger'])}  (stop-sell order, valid next 3 three-hour candles)\n"
            f"• Stop-loss  : {_f(r, r['stop'])}\n"
            f"• Target 1R  : {_f(r, r['trigger'] - risk)}  (1:1 – reset from the actual entry if price gaps past the trigger)\n"
            f"• Risk       : {_f(r, risk)} pts ({risk / r['trigger'] * 100:.2f}%) · {_rs(r, risk)} per lot\n"
            f"• Volume     : {r['vol_x']:.1f}× average ✅\n"
            f"• OI         : previous day {r['oi_prev'] or 'n/a'} ✅ · during the sweep candle {r['oi_sweep_pct']:+.2f}% ✅ "
            f"(not rising – stops run, not fresh buying)\n"
            f"• Time exit  : after 20 three-hour candles (~10 sessions)\n"
            + (f"{r['sr']}\n" if r.get("sr") else "") +
            f"{STATS['STK_SWEEP3H']}\n{WARN}")


def on_stock_3h(state, msgs, name, c, f3, now, prev_oi_label, sweep_oi_change):
    """From alerts.stocks.scan after each 3-hour block. prev_oi_label(day) -> 'LB'/'SB'/'SC'/'LU'/None for the last completed
    day before `day`; sweep_oi_change(t0, t1) -> OI % change over the sweep candle or None. Both are called only for a
    candidate (one sweep at a time per stock), so no extra API load for ordinary scans."""
    if f3 is None or len(f3) < 60:
        return
    s = _store(state)
    _manage(state, msgs, s, "STK_SWEEP3H", name, c["symbol"], f3, None, now)
    if not ENABLED.get("STK_SWEEP3H") or any(r["setup"] == "STK_SWEEP3H" and r["name"] == name for r in s["open"]):
        return
    i = len(f3) - 1
    atr_ = I.atr(f3, 14)
    lv = equal_high_at(f3, i, float(atr_.iat[i]))
    h, l, cl = float(f3["high"].iat[i]), float(f3["low"].iat[i]), float(f3["close"].iat[i])
    if not (np.isfinite(lv) and h > lv and cl < lv):
        return
    sid = f"STK_SWEEP3H|{name}|{f3['time'].iat[i]}"
    if sid in s["seen"]:
        return
    s["seen"] = (s["seen"] + [sid])[-3000:]
    v = f3["volume"].astype(float)
    va = v.rolling(20).mean().shift(1).iat[i]
    vx = float(v.iat[i] / va) if va and va > 0 else 0.0
    t0 = pd.Timestamp(f3["time"].iat[i])
    why = []
    if vx < SW["vol_x"]:
        why.append(f"volume {vx:.1f}× < 1.5×")
    lab = prev_oi_label(t0.normalize()) if not why else None
    if not why and lab == "LB":
        why.append("previous day was a long buildup (backtest: no edge)")
    doi = sweep_oi_change(t0, t0 + pd.Timedelta(hours=3)) if not why else None
    if not why and (doi is None or not np.isfinite(doi)):
        why.append("OI during the sweep candle not available")
    elif not why and doi > 0:
        why.append(f"OI rose {doi:+.2f}% during the sweep (fresh buying, not a stop run)")
    if why:
        print(f"[setup] STK_SWEEP3H {name} sweep at {t0:%d-%b %H:%M} not sent: {'; '.join(why)}")
        return
    a = float(atr_.iat[i])
    tick = c.get("tick") or 0.05
    r = dict(setup="STK_SWEEP3H", name=name, contract=c["symbol"], token=c.get("token"), side="SELL", status="pending",
             pattern_time=str(t0), pattern=dict(open=float(f3["open"].iat[i]), high=h, low=l, close=cl), level=float(lv),
             trigger=TP.tick_round(l, tick), stop=TP.tick_round(h + 0.05 * a, tick, "up"), atr=round(a, 4), tick=tick,
             mult=int(c.get("lot") or 1), lot=c.get("lot"), vol_x=round(vx, 2), oi_prev=lab, oi_sweep_pct=round(float(doi), 2),
             target_r=SW["target_r"], last_bar=str(t0), logged=str(now), waited=0, key=f"STK_SWEEP3H|{name}|{t0}")
    r["sr"] = sr_line(f3.iloc[:i + 1], "SELL", r["trigger"], r["stop"], SW["target_r"])[0]
    if abs(r["stop"] - r["trigger"]) / r["trigger"] * 100 > P["max_stop_pct"]:
        print(f"[setup] STK_SWEEP3H {name}: stop too far – not sent"); return
    s["open"].append(r)
    msgs.append(sweep_msg(r))
    print(f"[setup] STK_SWEEP3H {name} SELL below {r['trigger']} stop {r['stop']} vol {vx:.1f}x OI prev {lab} sweep {doi:+.2f}%")


# ─────────────── 15-minute stock sweep – LOG ONLY ───────────────
def _s15_who(r):
    return f"{r['name']} FUT (NSE)"


def _s15_setup_msg(r):
    risk = r["stop"] - r["trigger"]
    lvl = "previous-day high" if r["level"] == "PD" else "20-candle high"
    return (f"🔴 SELL SETUP – {_s15_who(r)} · 15-MIN LIQUIDITY SWEEP (test phase)\n{LINE}\n"
            f"Sweep    : 15-min candle {pd.Timestamp(r['sweep_time']):%d-%b %H:%M} went above the {lvl} and closed back below\n"
            f"• SELL below : {r['trigger']:,.2f}  (stop-sell order, valid next 3 candles, today only)\n"
            f"• Stop-loss  : {r['stop']:,.2f}\n"
            f"• Target 1R  : {r['trigger'] - risk:,.2f}  (1:1)\n"
            f"• Risk       : {risk:,.2f} pts ({risk / r['trigger'] * 100:.2f}%)" + (f" · ₹{risk * r['lot']:,.0f} per lot" if r.get("lot") else "") + "\n"
            f"• Volume     : {r['vol_x']:.1f}× average ✅\n"
            f"• OI         : {r['oi_change_pct']:+.2f}% on the sweep candle ✅ (falling – stop run, not fresh buying)\n"
            f"• Exit       : by the day's close if neither stop nor target is hit\n"
            "Evidence: Aug–Oct 2026 only, 48 trades, 75% wins, +0.28R after costs – SMALL SAMPLE, test phase. "
            "BUY-side sweeps lost money and are not sent.\n" + WARN)


def sweep15_log(obstate, name, symbol, df, now, msgs=None, lot=None):
    """From obuy.engine.scan with the 15-minute futures frame (time/open/high/low/close/volume/oi) of a top-40 stock.
    Records every 15-minute sweep of the 20-candle high/low and previous-day high/low (both sides) with its volume and
    OI-direction flags, then tracks it to the day's close (1:1). SELL sweeps with volume ≥ 1.5× AND OI falling are SENT
    (SWEEP15_SEND) with TRIGGERED / EXIT follow-ups; everything else is log only."""
    msgs = msgs if msgs is not None else []
    if not SWEEP15_LOG or df is None or len(df) < 60:
        return
    s = obstate.setdefault("sweep15", dict(open=[], closed=[], seen=[]))
    f = df.reset_index(drop=True)
    day = f["time"].dt.normalize()
    keep = []
    for r in s["open"]:                                            # track open / pending records
        if r["name"] != name:
            keep.append(r); continue
        sd = 1 if r["side"] == "BUY" else -1
        rows = f[(f["time"] > pd.Timestamp(r["last_bar"])) & (day == pd.Timestamp(r["day"]))]
        done = None
        for b in rows.itertuples():
            r["last_bar"] = str(b.time)
            if r["status"] == "pending":
                r["waited"] = r.get("waited", 0) + 1
                if sd * (b.open - r["trigger"]) > 0:
                    e0 = b.open
                elif (b.low <= r["stop"]) if sd > 0 else (b.high >= r["stop"]):
                    done = ("cancelled", None); break
                elif (b.high > r["trigger"]) if sd > 0 else (b.low < r["trigger"]):
                    e0 = r["trigger"]
                elif r["waited"] >= 3:
                    done = ("cancelled", None); break
                else:
                    continue
                R = sd * (e0 - r["stop"])
                r.update(status="open", entry=float(e0), risk=float(R), target=float(e0 + sd * R), entry_time=str(b.time))
                if r.get("send"):
                    msgs.append(f"✅ TRIGGERED – {_s15_who(r)} SELL (15-min sweep) at {e0:,.2f} · stop {r['stop']:,.2f} · "
                                f"target {r['target']:,.2f}. {WARN}")
            if r["status"] == "open":                    # high / low after the call (daily report)
                r["hi"] = max(r.get("hi", r["entry"]), float(b.high)); r["lo"] = min(r.get("lo", r["entry"]), float(b.low))
            if (b.low <= r["stop"]) if sd > 0 else (b.high >= r["stop"]):
                done = ("stop", r["stop"]); break
            if (b.high >= r["target"]) if sd > 0 else (b.low <= r["target"]):
                done = ("target", r["target"]); break
        if done is None and (now.normalize() > pd.Timestamp(r["day"]) or f"{now:%H:%M}" >= "15:30"):
            last = f[day == pd.Timestamp(r["day"])]
            done = ("eod", float(last["close"].iloc[-1])) if r["status"] == "open" and len(last) else ("cancelled", None)
        if done:
            r.update(status="closed", exit_reason=done[0], exit=done[1], closed=str(now))
            if done[1] is not None and r.get("risk"):
                r["gross_R"] = round(sd * (done[1] - r["entry"]) / r["risk"], 3)
            if r.get("send"):
                if done[1] is None or not r.get("risk"):
                    msgs.append(f"⏹ CANCELLED – {_s15_who(r)} SELL 15-min sweep from {pd.Timestamp(r['sweep_time']):%H:%M}: no entry.")
                else:
                    g = r["gross_R"]
                    msgs.append(f"{'✅' if g > 0 else '❌' if g < 0 else '➖'} EXIT – {_s15_who(r)} SELL (15-min sweep) at "
                                f"{done[1]:,.2f}: {done[0]} · {g:+.2f}R" + (f" · {'+' if g >= 0 else '−'}₹{abs(g * r['risk'] * r['lot']):,.0f} per lot"
                                                                             if r.get("lot") else "") + " before costs")
            s["closed"] = (s["closed"] + [r])[-1500:]
        else:
            keep.append(r)
    s["open"] = keep
    i = len(f) - 1                                                 # newest completed candle
    if day.iat[i] != now.normalize() or f["time"].iat[i].strftime("%H:%M") > "14:30" or (day == day.iat[i]).sum() < 2:
        return
    if any(r["name"] == name for r in s["open"]):
        return
    h, l, c, v, oi = (f[x].astype(float).values for x in ("high", "low", "close", "volume", "oi"))
    a = I.atr(f, 14).values
    g = f.groupby(day)
    pdh = day.map(g["high"].max().shift(1)).values; pdl = day.map(g["low"].min().shift(1)).values
    swh = pd.Series(h).shift(1).rolling(20).max().values; swl = pd.Series(l).shift(1).rolling(20).min().values
    va = pd.Series(v).rolling(20).mean().shift(1).values
    for lvname, hi_, lo_ in (("PD", pdh, pdl), ("SW", swh, swl)):
        for side, lv in ((-1, hi_[i]), (1, lo_[i])):
            if not np.isfinite(lv) or not ((h[i] > lv and c[i] < lv) if side < 0 else (l[i] < lv and c[i] > lv)):
                continue
            sid = f"{name}|{f['time'].iat[i]}|{lvname}|{side}"
            if sid in s["seen"]:
                continue
            s["seen"] = (s["seen"] + [sid])[-4000:]
            doi = (oi[i] / oi[i - 1] - 1) * 100 if i > 0 and oi[i - 1] > 0 and np.isfinite(oi[i]) else None
            stop = h[i] + 0.05 * a[i] if side < 0 else l[i] - 0.05 * a[i]
            s["open"].append(dict(name=name, contract=symbol, side="SELL" if side < 0 else "BUY", level=lvname, status="pending",
                                  day=str(day.iat[i]), sweep_time=str(f["time"].iat[i]), trigger=float(l[i] if side < 0 else h[i]),
                                  stop=float(stop), vol_x=round(float(v[i] / va[i]), 2) if va[i] > 0 else None,
                                  oi_change_pct=None if doi is None else round(float(doi), 3),
                                  V=bool(va[i] > 0 and v[i] >= 1.5 * va[i]), OD=bool(doi is not None and doi < 0),
                                  last_bar=str(f["time"].iat[i]), logged=str(now), waited=0, lot=lot))
            rec = s["open"][-1]
            rec["send"] = bool(SWEEP15_SEND and side < 0 and rec["V"] and rec["OD"]
                               and (rec["stop"] - rec["trigger"]) / rec["trigger"] * 100 <= P["max_stop_pct"])
            if rec["send"]:
                msgs.append(_s15_setup_msg(rec))
            print(f"[sweep15-log] {name} {lvname} {'SELL' if side < 0 else 'BUY'} sweep {f['time'].iat[i]:%H:%M} "
                  f"vol {v[i] / va[i] if va[i] > 0 else 0:.1f}x OI {doi if doi is not None else float('nan'):+.2f}% (log only)")
            return


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
