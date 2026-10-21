"""Telegram BUY/SELL alert engine – RSI extreme + candlestick reversal, 15-min / 1-hour / positional (3-hour).
MCX futures + NIFTY / BANKNIFTY futures. ALERTS ONLY: no orders, no auto-trading, no order code in this package.

  scan(api, master, now, state) -> (state, messages, report)
"""
import pandas as pd
from crude import data as CD
from alerts import signals as S

MCX = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]
NFO = ["NIFTY", "BANKNIFTY"]
ROLL_DAYS = {"MCX": 4, "NFO": 2}
TFS = (("15m", "FIFTEEN_MINUTE", 15, 25), ("1h", "ONE_HOUR", 60, 100), ("3h", None, 180, None))
WARN = "Alert only – no auto trade. Rule not proven profitable; not investment advice."


# ─────────────── sessions / candles ───────────────
def s_open(ex, t):
    return CD.hm(t, "09:00" if ex == "MCX" else "09:15")


def s_close(ex, t):
    return CD.session_close(t) if ex == "MCX" else CD.hm(t, "15:30")


def is_open(ex, now):
    return now.weekday() < 5 and s_open(ex, now) <= now <= s_close(ex, now)


def closed(df, ex, minutes, now, grace=60):
    if df is None or df.empty:
        return df
    end = df["time"].map(lambda t: min(t + pd.Timedelta(minutes=minutes), s_close(ex, t)))
    return df[end + pd.Timedelta(seconds=grace) <= now].reset_index(drop=True)


def positional_candles(h1c, ex, now):
    """MCX: fixed 3-hour blocks 09-12-15-18-21-close (crude/data.three_hour). NSE: 09:15-12:15 and 12:15-15:30."""
    if h1c is None or h1c.empty:
        return h1c
    if ex == "MCX":
        return CD.three_hour(h1c, now)
    d = h1c.copy()
    d["day"] = d["time"].dt.normalize()
    d["k"] = (d["time"] >= d["day"] + pd.Timedelta(hours=12, minutes=15)).astype(int)
    g = d.groupby(["day", "k"])
    out = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"), n=("close", "size")).reset_index()
    out["end"] = out["day"] + pd.to_timedelta(["12:15:00" if k == 0 else "15:30:00" for k in out["k"]])
    out = out[(out["end"] + pd.Timedelta(seconds=60) <= now) & (out["n"] >= 2)]
    return out[["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


# ─────────────── contracts & roll continuity ───────────────
def contracts(master, name, ex, now):
    m = master[(master["name"] == name) & (master["exch_seg"] == ex) & master["instrumenttype"].isin(["FUTCOM", "FUTIDX"])
               & (master["expiry_dt"] >= now.normalize())].sort_values("expiry_dt")
    if m.empty:
        return None
    rows = list(m.itertuples())
    k = next((i for i, r in enumerate(rows) if CD.trading_days_between(now.normalize(), r.expiry_dt) > ROLL_DAYS[ex]), None)
    if k is None:
        return None
    use = rows[k]
    return dict(symbol=use.symbol, token=str(use.token), expiry=str(use.expiry_dt.date()), is_front=(k == 0),
                next_token=str(rows[k + 1].token) if k + 1 < len(rows) else None)


def find_switch(front, nxt):
    """Most recent contract switch in a vendor-stitched front series, MEASURED from the overlap with the next
    contract's own data: at the first candle of a day, (next − front) jumps by (old − new). Returns list for
    crude.data.continuity, or [] if no clear switch."""
    if front is None or nxt is None or front.empty or nxt.empty:
        return []
    m = front[["time", "close"]].merge(nxt[["time", "close", "volume"]], on="time", suffixes=("_f", "_n"))
    if len(m) < 30:
        return []
    m["diff"] = m["close_n"] - m["close_f"]
    noise = m["diff"].diff().abs().median() or 1e-9
    firsts = m.index[m["time"].dt.normalize() != m["time"].dt.normalize().shift()]
    best = None
    for i in firsts:
        if i < 3 or i + 3 > len(m):
            continue
        step = m["diff"].iloc[i:i + 3].median() - m["diff"].iloc[i - 3:i].median()
        sc = abs(step) / noise
        if best is None or sc > best[0]:
            best = (sc, m.at[i, "time"], float(step), float(m.at[i, "close_f"]))
    if best and best[0] >= 6 and abs(best[2]) / best[3] >= 0.0005:
        return [(best[1], best[2], "measured")]
    return []


# ─────────────── messages ───────────────
def _f(x):
    return f"{x:,.2f}" if abs(x) < 1000 else f"{x:,.0f}"


def call_msg(name, ex, c, sig):
    side = sig["kind"]
    s = 1 if side == "BUY" else -1
    tf = {"15m": "15-MIN", "1h": "1-HOUR", "3h": "POSITIONAL (3-hour candles)"}[sig["tf"]]
    rsi_txt = (f"RSI(14) {sig['rsi_max']:.1f} > 75 → overbought" if side == "SELL" else f"RSI(14) {sig['rsi_min']:.1f} < 25 → oversold")
    trend = sig["trend"]
    counter = (side == "BUY" and trend == "DOWN") or (side == "SELL" and trend == "UP")
    L = [f"{'🟢' if side == 'BUY' else '🔴'} {side} ALERT – {name} ({tf})",
         f"Contract: {c['symbol']} ({'MCX' if ex == 'MCX' else 'NSE F&O'}, exp {pd.Timestamp(c['expiry']):%d-%b-%Y})",
         f"Signal candle: {pd.Timestamp(sig['candle']):%d-%b %H:%M} (closed) · price {_f(sig['close'])}",
         "Why:",
         f"• {rsi_txt} (current {sig['rsi']:.1f})",
         *[f"• {p}" for p in sig["patterns"]],
         f"• Volume {sig['vol_x']}× usual for this time" if sig.get("vol_x") else "• Volume comparison not available",
         f"• Trend {trend} (EMA20 {_f(sig['ema20'])} / EMA50 {_f(sig['ema50'])}" + (f", ADX {sig['adx']:.0f})" if sig.get("adx") else ")")
         + (" → COUNTER-TREND reversal: higher risk, consider smaller size" if counter else ""),
         f"Plan: entry ~{_f(sig['entry'])} · SL {_f(sig['sl'])} ({'below' if s > 0 else 'above'} the pattern + buffer) · "
         f"T1 {_f(sig['t1'])} (1R) · T2 {_f(sig['t2'])} (2R)",
         f"After T1: book half, move SL to entry. Invalid if a candle closes {'below' if s > 0 else 'above'} {_f(sig['sl'])}."
         + (" Intraday: exit by session close." if sig["tf"] != "3h" else " Positional: max 10 sessions, exit before expiry."),
         WARN]
    return "\n".join(L)


def watch_msg(name, sig):
    side = "BUY" if sig["kind"] == "WATCH_BUY" else "SELL"
    return (f"🟡 WATCH {side} – {name} ({sig['tf']}) RSI {sig['rsi']:.1f} {'< 25 oversold' if side == 'BUY' else '> 75 overbought'} "
            f"at {pd.Timestamp(sig['candle']):%d-%b %H:%M}, price {_f(sig['close'])}. No {'bullish' if side == 'BUY' else 'bearish'} "
            f"reversal candle yet – a {side} alert follows only if one forms. {WARN}")


# ─────────────── scan ───────────────
def new_state():
    return dict(schema=1, seen=[], active=[], last_eval={}, switches={}, day=None, history=[])


def scan(api, master, now, state, only=None):
    msgs, rep = [], dict(time=str(now), instruments={}, errors=[])
    d = str(now.date())
    if state.get("day", {}) is None or (state.get("day") or {}).get("date") != d:
        prev = state.get("day")
        if prev and not prev.get("eod_sent"):
            msgs.append(eod_msg(prev, state))
        state["day"] = dict(date=d, alerts=0, watches=0, startup_sent=False, eod_sent=False, outcomes=[])
    names = [(n, "MCX") for n in MCX] + [(n, "NFO") for n in NFO]
    if only:
        names = [x for x in names if x[0] in only]
    for name, ex in names:
        info = rep["instruments"].setdefault(name, {})
        if not is_open(ex, now) and not _just_closed(ex, now):
            info["status"] = "session closed"
            continue
        c = contracts(master, name, ex, now)
        if c is None:
            info["status"] = "no live contract"; rep["errors"].append(f"{name}: no contract"); continue
        info["contract"] = c["symbol"]
        frames = {}
        for tf, iv, mins, days in TFS[:2]:
            try:
                df = api.candles(ex, c["token"], iv, now - pd.Timedelta(days=days), now)
            except Exception as e:
                df = None; rep["errors"].append(f"{name} {tf}: {type(e).__name__}")
            if df is None or df.empty:
                info[tf] = "NO DATA"; rep["errors"].append(f"{name} {tf}: no candles"); continue
            frames[tf] = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
        if c["is_front"] and c["next_token"] and "1h" in frames:
            key = f"{c['symbol']}|{d}"
            if key not in state["switches"]:
                try:
                    nx = api.candles(ex, c["next_token"], "ONE_HOUR", now - pd.Timedelta(days=100), now)
                except Exception:
                    nx = None
                state["switches"] = {k: v for k, v in state["switches"].items() if k.endswith(d)}
                state["switches"][key] = [(str(t), s, q) for t, s, q in find_switch(frames["1h"], nx)]
            sw = [(pd.Timestamp(t), s, q) for t, s, q in state["switches"][key]]
            if sw:
                for tf in frames:
                    frames[tf] = CD.continuity(frames[tf], sw)
                    frames[tf] = frames[tf][frames[tf]["time"] >= sw[0][0] - pd.Timedelta(days=60)]
                info["roll"] = f"switch {sw[0][0]:%d-%b} adjusted by {sw[0][1]:+.1f}"
        cl = {tf: closed(frames.get(tf), ex, m, now) for tf, _, m, _ in TFS[:2]}
        if cl.get("1h") is not None:
            cl["3h"] = positional_candles(cl["1h"], ex, now)
        _follow_up(state, msgs, name, ex, cl.get("15m"), now)
        for tf, _, mins, _ in TFS:
            dfc = cl.get(tf)
            if dfc is None or len(dfc) < 60:
                info[tf] = f"insufficient candles ({0 if dfc is None else len(dfc)})"; continue
            last = str(dfc["time"].iloc[-1])
            k = f"{name}|{tf}"
            if state["last_eval"].get(k) == last:
                info[tf] = f"no new candle (last {last[5:16]})"; continue
            state["last_eval"][k] = last
            age = (now - min(dfc["time"].iloc[-1] + pd.Timedelta(minutes=mins), s_close(ex, dfc["time"].iloc[-1]))).total_seconds() / 60
            if is_open(ex, now) and age > max(2 * mins, 40) and tf != "3h":
                info[tf] = f"STALE (last candle ended {age:.0f} min ago)"; continue
            sig = S.evaluate(dfc, tf)
            info[tf] = f"{sig['kind'] or 'none'} · RSI {sig.get('rsi')} · {sig.get('why', ', '.join(sig.get('patterns', [])))}"
            sid = f"{k}|{last}|{sig['kind']}"
            if not sig["kind"] or sid in state["seen"]:
                continue
            state["seen"] = (state["seen"] + [sid])[-2000:]
            if sig["kind"] in ("BUY", "SELL"):
                # adjusted history never changes the signal candle itself (offset 0 after the last switch)
                msgs.append(call_msg(name, ex, c, sig))
                state["day"]["alerts"] += 1
                state["active"].append(dict(id=sid, name=name, ex=ex, tf=tf, side=sig["kind"], entry=sig["entry"], sl=sig["sl"],
                                            t1=sig["t1"], t2=sig["t2"], time=last, t1_hit=False, contract=c["symbol"], expiry=c["expiry"]))
            else:
                msgs.append(watch_msg(name, sig))
                state["day"]["watches"] += 1
    if not state["day"]["startup_sent"]:
        msgs.insert(0, startup_msg(now, rep))
        state["day"]["startup_sent"] = True
    if all(not is_open(ex, now) for ex in ("MCX", "NFO")) and now > CD.session_close(now) and not state["day"]["eod_sent"]:
        msgs.append(eod_msg(state["day"], state))
        state["day"]["eod_sent"] = True
    return state, msgs, rep


def _just_closed(ex, now):
    c = s_close(ex, now)
    return now.weekday() < 5 and c < now <= c + pd.Timedelta(minutes=20)


def _follow_up(state, msgs, name, ex, c15, now):
    keep = []
    for a in state["active"]:
        if a["name"] != name:
            keep.append(a); continue
        s = 1 if a["side"] == "BUY" else -1
        done, note = False, None
        bars = c15[c15["time"] > pd.Timestamp(a["time"])] if c15 is not None else pd.DataFrame()
        for b in bars.itertuples():
            stop = a["entry"] if a["t1_hit"] else a["sl"]
            if (b.low <= stop) if s > 0 else (b.high >= stop):
                note = ("➖ Exit at cost after T1" if a["t1_hit"] else "❌ SL hit"); done = True; break
            if not a["t1_hit"] and ((b.high >= a["t1"]) if s > 0 else (b.low <= a["t1"])):
                a["t1_hit"] = True
                msgs.append(f"🎯 T1 hit – {name} {a['side']} ({a['tf']}) at {_f(a['t1'])}. Book half, SL to entry {_f(a['entry'])}.")
            if (b.high >= a["t2"]) if s > 0 else (b.low <= a["t2"]):
                note = "✅ T2 hit – alert complete"; done = True; break
        if c15 is not None and len(c15):
            a["time"] = max(a["time"], str(c15["time"].iloc[-1])) if not done else a["time"]
        if not done:
            end = s_close(ex, pd.Timestamp(a["id"].split("|")[2])) if a["tf"] != "3h" else None
            if end is not None and now >= end:
                note, done = "⏹ Session over – intraday alert closed" + (" (T1 was hit)" if a["t1_hit"] else " without T1/SL"), True
            elif a["tf"] == "3h" and (CD.trading_days_between(pd.Timestamp(a["id"].split("|")[2]).normalize(), now.normalize()) >= 10
                                      or CD.trading_days_between(now.normalize(), a["expiry"]) <= ROLL_DAYS[ex]):
                note, done = "⏹ Positional alert closed (10 sessions / near expiry)", True
        if done:
            msgs.append(f"{note} – {name} {a['side']} ({a['tf']}) from {pd.Timestamp(a['id'].split('|')[2]):%d-%b %H:%M}, entry {_f(a['entry'])}")
            state["day"]["outcomes"].append(dict(name=name, tf=a["tf"], side=a["side"], result=note))
        else:
            keep.append(a)
    state["active"] = keep


def startup_msg(now, rep):
    ok = [n for n, i in rep["instruments"].items() if i.get("contract")]
    return (f"📡 BUY/SELL ALERTS ACTIVE – {now:%d-%b-%Y %H:%M} IST\n"
            f"Rule: RSI(14) > 75 + bearish reversal candle → SELL alert · RSI < 25 + bullish reversal candle → BUY alert "
            f"(15-min, 1-hour, positional 3-hour). RSI extreme without a reversal candle → WATCH message.\n"
            f"Instruments with data now: {', '.join(ok) or 'none (markets closed)'}\n"
            + (f"Data problems: {'; '.join(rep['errors'][:6])}\n" if rep["errors"] else "") + WARN)


def eod_msg(day, state):
    o = day.get("outcomes", [])
    return (f"📋 ALERTS – END OF DAY {pd.Timestamp(day['date']):%d-%b-%Y}\n"
            f"BUY/SELL alerts: {day['alerts']} · watch messages: {day['watches']}\n"
            f"Closed today: " + (", ".join(f"{x['name']} {x['side']} {x['tf']}: {x['result'].split(' –')[0]}" for x in o) or "none") + "\n"
            f"Still open: " + (", ".join(f"{a['name']} {a['side']} {a['tf']}" for a in state["active"]) or "none") + f"\n{WARN}")
