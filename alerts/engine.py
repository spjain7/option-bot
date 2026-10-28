"""Telegram BUY/SELL alert engine – RSI extreme + candlestick reversal, 15-min / 1-hour / positional (3-hour).
MCX futures + NIFTY / BANKNIFTY futures. ALERTS ONLY: no orders, no auto-trading, no order code in this package.

  scan(api, master, now, state) -> (state, messages, report)
"""
import os
import pandas as pd
from crude import data as CD, indicators as I
from alerts import signals as S, breakout as BO, patterns as PT, report as RP, optfilter as OF, tradeplan as TP
from alerts import candle_setups as CS
PATTERN_TFS = ()               # OFF: chart-pattern calls failed once the exit-simulator bug was fixed (INST-PAT-001)

RSI_REVERSAL_CALLS = False   # off since 22-Oct-2026: the RSI-reversal rule lost money in every test (alerts/STATS.md,
                             # research/search). Volume-breakout alerts replace it. Set True to bring the old calls back.

MCX = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]
NFO = ["NIFTY", "BANKNIFTY"]
ROLL_DAYS = {"MCX": 4, "NFO": 2}
TFS = (("15m", "FIFTEEN_MINUTE", 15, 25), ("1h", "ONE_HOUR", 60, 400), ("3h", None, 180, None))
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
    tk = getattr(use, "tick", None)
    return dict(symbol=use.symbol, token=str(use.token), expiry=str(use.expiry_dt.date()), is_front=(k == 0), lot=int(use.lotsize),
                tick=float(tk) if tk is not None and tk == tk and tk > 0 else None,
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


LINE = "━━━━━━━━━━━━━━━━━━"
TFNAME = {"15m": "15-MIN (intraday)", "1h": "1-HOUR (intraday)", "3h": "POSITIONAL (3-hour candles)"}


def _lv(xs):
    return " · ".join(f"{_f(v)} ({n})" for v, n in xs) or "none nearby"


def _oi_line(oi):
    if not oi or oi.get("oi") is None:
        return "OI     : not available from the live quote"
    s = f"OI     : {oi['oi']:,.0f}"
    if oi.get("chg_pct") is None:
        return s + " · change: first reading this session (needs a 2nd scan 10-40 min later)"
    return s + f" ({oi['chg_pct']:+.2f}% in {oi['gap_min']:.0f} min, price {oi['d_price']:+.2f}) → {oi['label'] or 'flat – no clear buildup'}"


def _vol_line(sig, q):
    v = f"Volume : {sig['vol_x']}× usual for this time" if sig.get("vol_x") else "Volume : same-time comparison not available"
    if q and q.get("tradeVolume") is not None:
        v += f" · today {q['tradeVolume']:,.0f} lots"
    return v


def _why(sig, side, oi, sr_near):
    s = 1 if side == "BUY" else -1
    bits = [f"RSI {'dropped below 25 (oversold – sellers stretched)' if s > 0 else 'rose above 75 (overbought – buyers stretched)'}",
            f"the {sig['tf']} candle closed as {', '.join(p.split(' (')[0].lower() for p in sig['patterns'])}, showing "
            f"{'buyers pushing back from the lows' if s > 0 else 'sellers pushing back from the highs'}"]
    if sig.get("vol_x") and sig["vol_x"] >= 1.2:
        bits.append(f"on {sig['vol_x']}× normal volume (real participation)")
    elif sig.get("vol_x"):
        bits.append(f"but volume is only {sig['vol_x']}× normal (weaker confirmation)")
    if sr_near:
        bits.append(f"near {'support' if s > 0 else 'resistance'} {_f(sr_near[0])} ({sr_near[1]})")
    if oi and oi.get("label"):
        good = {"BUY": ("Short covering", "Long buildup"), "SELL": ("Long unwinding", "Short buildup")}[side]
        bits.append(f"OI shows {oi['label'].lower()}" + (" (supports the call)" if oi["label"] in good else " (does NOT support the call – caution)"))
    counter = (s > 0 and sig["trend"] == "DOWN") or (s < 0 and sig["trend"] == "UP")
    tail = (" This is a counter-trend reversal against the main " + sig["trend"].lower() + "trend, so risk is higher – smaller size.") if counter else ""
    return "Why this call: " + "; ".join(bits) + "." + tail


def call_msg(name, ex, c, sig, oi=None, q=None):
    side = sig["kind"]
    s = 1 if side == "BUY" else -1
    a = sig["atr"]
    lv = sig.get("levels") or dict(support=[], resistance=[])
    near = (lv["support"][:1] if s > 0 else lv["resistance"][:1])
    near = near[0] if near and abs(near[0][0] - sig["entry"]) <= 1.5 * a else None
    block = lv["resistance"] if s > 0 else lv["support"]
    warn = ""
    if block and s * (block[0][0] - sig["entry"]) < sig["risk"]:
        warn = f"\n⚠️ {'Resistance' if s > 0 else 'Support'} {_f(block[0][0])} ({block[0][1]}) comes before T1 – consider booking there."
    L = [f"{'🟢 BUY' if s > 0 else '🔴 SELL'} CALL – {name} FUT | {TFNAME[sig['tf']]}", LINE,
         f"Contract : {c['symbol']} ({'MCX' if ex == 'MCX' else 'NSE F&O'}) · expiry {pd.Timestamp(c['expiry']):%d-%b-%Y}",
         f"Entry    : {_f(sig['entry'] - 0.1 * a)} – {_f(sig['entry'] + 0.1 * a)} ({side} zone, signal close {_f(sig['entry'])})",
         f"Stop loss: {_f(sig['sl'])} ({'below' if s > 0 else 'above'} the reversal candles)",
         f"Target 1 : {_f(sig['t1'])} (1R) → book 50%, move SL to entry",
         f"Target 2 : {_f(sig['t2'])} (2R)",
         f"Risk/Reward: 1 : 2 · risk {_f(sig['risk'])} pts", LINE,
         f"Resistance : {_lv(lv['resistance'])}",
         f"Support    : {_lv(lv['support'])}", LINE,
         _vol_line(sig, q), _oi_line(oi),
         f"RSI(14): {sig['rsi_min'] if s > 0 else sig['rsi_max']:.1f} ({'oversold < 25' if s > 0 else 'overbought > 75'}) · now {sig['rsi']:.1f}",
         f"Candle : {', '.join(sig['patterns'])}",
         f"Trend  : {sig['trend']} (EMA20 {_f(sig['ema20'])} / EMA50 {_f(sig['ema50'])}" + (f", ADX {sig['adx']:.0f})" if sig.get("adx") else ")"),
         LINE, _why(sig, side, oi, near) + warn,
         f"Signal candle {pd.Timestamp(sig['candle']):%d-%b %H:%M} (closed). Invalid if a candle closes {'below' if s > 0 else 'above'} {_f(sig['sl'])}."
         + (" Exit by session close." if sig["tf"] != "3h" else " Max 10 sessions, exit before expiry."),
         WARN]
    return "\n".join(L)


def watch_msg(name, ex, c, sig, oi=None, q=None):
    side = "BUY" if sig["kind"] == "WATCH_BUY" else "SELL"
    s = 1 if side == "BUY" else -1
    a = sig["atr"]
    lv = sig.get("levels") or dict(support=[], resistance=[])
    trig = sig["last_high"] if s > 0 else sig["last_low"]
    sl = (sig["swing_low3"] - 0.2 * a) if s > 0 else (sig["swing_high3"] + 0.2 * a)
    risk = max(s * (trig - sl), a)
    L = [f"🟡 WATCH {side} – {name} FUT | {TFNAME[sig['tf']]}", LINE,
         f"Contract : {c['symbol']} · expiry {pd.Timestamp(c['expiry']):%d-%b-%Y}",
         f"Price    : {_f(sig['close'])} · RSI(14) {sig['rsi']:.1f} ({'oversold < 25' if s > 0 else 'overbought > 75'})",
         f"No {'bullish' if s > 0 else 'bearish'} reversal candle yet – NOT a call.",
         f"Possible {side} if a {'bullish' if s > 0 else 'bearish'} reversal candle closes {'above' if s > 0 else 'below'} {_f(trig)}:",
         f"  SL ~{_f(trig - s * risk)} · T1 ~{_f(trig + s * risk)} · T2 ~{_f(trig + 2 * s * risk)} (final levels come with the call)", LINE,
         f"Resistance : {_lv(lv['resistance'])}",
         f"Support    : {_lv(lv['support'])}", LINE,
         _vol_line(sig, q), _oi_line(oi),
         f"Trend  : {sig['trend']}" + (f" (ADX {sig['adx']:.0f})" if sig.get("adx") else ""),
         f"Candle {pd.Timestamp(sig['candle']):%d-%b %H:%M} (closed).", WARN]
    return "\n".join(L)


def oi_reading(state, symbol, q, now):
    """Current OI from the live quote; change only vs this engine's own snapshot 10-40 min earlier (never invented)."""
    if not q or not isinstance(q.get("opnInterest"), (int, float)) or q["opnInterest"] <= 0:
        return None
    snaps = state.setdefault("oi", {})
    prev = snaps.get(symbol)
    out = dict(oi=float(q["opnInterest"]), chg_pct=None)
    if prev:
        gap = (now - pd.Timestamp(prev["time"])).total_seconds() / 60
        if 10 <= gap <= 40 and pd.Timestamp(prev["time"]).normalize() == now.normalize() and prev["oi"] > 0:
            ch = (out["oi"] - prev["oi"]) / prev["oi"] * 100
            dp = (q.get("ltp") or 0) - prev["ltp"]
            lab = ("Flat OI" if abs(ch) < 0.2 or dp == 0 else
                   ("Long buildup" if ch > 0 else "Short covering") if dp > 0 else ("Short buildup" if ch > 0 else "Long unwinding"))
            out.update(chg_pct=ch, gap_min=gap, d_price=dp, label=lab if lab != "Flat OI" else None)
    if not prev or (now - pd.Timestamp(prev["time"])).total_seconds() / 60 >= 10:
        snaps[symbol] = dict(time=str(now), oi=out["oi"], ltp=q.get("ltp") or 0)
    return out


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
    quotes, cmap = {}, {}
    for name, ex in names:
        if is_open(ex, now) or _just_closed(ex, now):
            cc = contracts(master, name, ex, now)
            if cc:
                cmap[name] = cc
    for ex in ("MCX", "NFO"):
        toks = [cmap[n]["token"] for n, e in names if e == ex and n in cmap]
        if toks:
            try:
                quotes.update(api.quotes({ex: toks}))
            except Exception as e:
                rep["errors"].append(f"quotes {ex}: {type(e).__name__}")
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
            df = None
            for attempt in range(3):                       # Angel rate limit (AB1021) returns nothing -> wait and retry
                try:
                    df = api.candles(ex, c["token"], iv, now - pd.Timedelta(days=days), now + pd.Timedelta(minutes=attempt))   # new minute = bypass the per-run cache
                except Exception as e:
                    rep["errors"].append(f"{name} {tf}: {type(e).__name__}")
                if df is not None and not df.empty:
                    break
                if hasattr(api, "failfast") and api.failfast():     # Angel is blocking us: more retries only make it worse
                    break
                if attempt < 2 and hasattr(api, "api"):
                    import time; time.sleep(2 + 2 * attempt)
            if df is None or df.empty:
                info[tf] = "NO DATA"; rep["errors"].append(f"{name} {tf}: no candles"); continue
            frames[tf] = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
        full_1h = frames["1h"].copy() if "1h" in frames else None   # RAW 400-day history for breakouts (as in the backtest)
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
            if sw and full_1h is not None:                 # breakouts: remove the roll jump, keep all history
                for t_, step, q_ in sw:
                    if q_ == "measured":
                        full_1h.loc[full_1h["time"] < t_, ["open", "high", "low", "close"]] -= step
            if sw:
                for tf in frames:
                    frames[tf] = CD.continuity(frames[tf], sw)
                for tf in frames:
                    frames[tf] = frames[tf][frames[tf]["time"] >= sw[0][0] - pd.Timedelta(days=60)]
                info["roll"] = f"switch {sw[0][0]:%d-%b} adjusted by {sw[0][1]:+.1f}"
        full_1h = closed(full_1h if full_1h is not None else frames.get("1h"), ex, 60, now)
        cl = {tf: closed(frames.get(tf), ex, m, now) for tf, _, m, _ in TFS[:2]}
        if cl.get("1h") is not None:
            cl["3h"] = positional_candles(cl["1h"], ex, now)
        _follow_up(state, msgs, name, ex, cl.get("15m"), now)
        q = quotes.get(c["token"])
        oi = oi_reading(state, c["symbol"], q, now)
        info["oi"] = "n/a" if not oi else f"{oi['oi']:,.0f}" + ("" if oi.get("chg_pct") is None else f" ({oi['chg_pct']:+.2f}%)")
        _breakouts(state, msgs, info, name, ex, c, full_1h, cl.get("15m"), now, oi, q, sw_day=_switch_day(state, c, d), master=master, api=api)
        for tf, _, mins, _ in TFS:
            if not RSI_REVERSAL_CALLS:
                break
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
            sig = S.evaluate(dfc, tf, cl.get("1h"))
            info[tf] = f"{sig['kind'] or 'none'} · RSI {sig.get('rsi')} · {sig.get('why', ', '.join(sig.get('patterns', [])))}"
            sid = f"{k}|{last}|{sig['kind']}"
            if sig.get("suppressed"):
                state["day"]["suppressed"] = state["day"].get("suppressed", 0) + 1
                print(f"[suppressed] {name} {tf} {sig['why']}")
            if not sig["kind"] or sid in state["seen"]:
                continue
            state["seen"] = (state["seen"] + [sid])[-2000:]
            if sig["kind"] in ("BUY", "SELL") and oi and oi.get("label") in {"BUY": ("Short buildup", "Long unwinding"), "SELL": ("Long buildup", "Short covering")}[sig["kind"]]:
                info[tf] += f" | suppressed: OI {oi['label']} contradicts {sig['kind']}"
                state["day"]["suppressed"] = state["day"].get("suppressed", 0) + 1
                continue
            if sig["kind"] in ("BUY", "SELL"):
                # adjusted history never changes the signal candle itself (offset 0 after the last switch)
                msgs.append(call_msg(name, ex, c, sig, oi, q))
                state["day"]["alerts"] += 1
                state["active"].append(dict(id=sid, name=name, ex=ex, tf=tf, side=sig["kind"], entry=sig["entry"], sl=sig["sl"],
                                            t1=sig["t1"], t2=sig["t2"], time=last, t1_hit=False, contract=c["symbol"], expiry=c["expiry"]))
            else:
                msgs.append(watch_msg(name, ex, c, sig, oi, q))
                state["day"]["watches"] += 1
    try:                                                   # stock futures – never allowed to break the MCX/index alerts
        import sys
        from alerts import stocks as STK
        STK.scan(api, master, now, state, msgs, rep, sys.modules[__name__])
    except Exception as e:
        rep["errors"].append(f"stock futures scan failed: {type(e).__name__}: {str(e)[:100]}")
    if not state["day"]["startup_sent"] and now.hour >= 8 and any(is_open(e, now) for e in ("MCX", "NFO")):
        msgs.insert(0, startup_msg(now, rep))
        state["day"]["startup_sent"] = True
    # end-of-day call reports (table image + text): Index + Stock after the NSE close, MCX after the MCX close
    for seg, ex, flag in (("NSE", "NFO", "rep_nse"), ("MCX", "MCX", "rep_mcx")):
        if state["day"].get(flag) or now.weekday() >= 5 or is_open(ex, now) or not _after_close(ex, now):
            continue
        state["day"][flag] = True
        try:
            toks = sorted({r["mark_key"] for r in state.get("ledger", []) if r["seg"] == seg and r["status"] == "OPEN" and r.get("mark_key")})
            qq = api.quotes({ex: toks}) if toks else {}
            marks = {t: float((qq.get(t) or {}).get("ltp") or 0) or None for t in toks}
            msgs += RP.build(state, seg, now, marks, os.getenv("ALERTS_STATE_DIR", "state/alerts"))
        except Exception as e:
            rep["errors"].append(f"report {seg}: {type(e).__name__}: {str(e)[:80]}")
    if all(not is_open(ex, now) for ex in ("MCX", "NFO")) and now > CD.session_close(now) and not state["day"]["eod_sent"]:
        state["day"]["eod_sent"] = True                  # replaced by the call reports above
    return state, msgs, rep


def _after_close(ex, now):
    """True from 5 minutes after this exchange's close until midnight (NSE 15:30; MCX = the day's MCX close)."""
    if ex == "NFO":
        return now >= now.normalize() + pd.Timedelta(hours=15, minutes=35)
    try:
        return now > CD.session_close(now) + pd.Timedelta(minutes=5)
    except Exception:
        return now >= now.normalize() + pd.Timedelta(hours=23, minutes=35)


def _switch_day(state, c, d):
    sw = state["switches"].get(f"{c['symbol']}|{d}") or []
    return pd.Timestamp(sw[0][0]).normalize() if sw else None


SHADOW_ONLY = {("3h", "SELL")}        # 28-Oct-2026 (approved): logged and tracked, never sent


def _shadow_rec(name, tf, side, plan, last, now, c, key, label):
    return dict(name=name, tf=tf, side=side, entry=plan["entry"], stop=plan["sl"], target=plan["target"], risk=plan["risk_unit"],
                best=plan["entry"], trailed=False, n=0, last_candle=last, tick=plan["tick"], checked=str(now),
                contract=c["symbol"], key=key, token=c["token"], shadow=label, opened=str(now))


def ha_tags(fr, sig):
    """HA-1 conditions (STRATEGY-PROGRAM-001): RSI(14) < 75 and/or prior compression (20-bar range in ATR ≤ its 100-bar median)."""
    tags = []
    if sig.get("rsi") is not None and sig["rsi"] < 75:
        tags.append("RSI<75")
    try:
        a = I.atr(fr, 14)
        comp = (fr["high"].rolling(20).max() - fr["low"].rolling(20).min()) / a
        if comp.iloc[-1] <= comp.rolling(100, min_periods=40).median().iloc[-1]:
            tags.append("compression")
    except Exception:
        pass
    return tags


def _breakouts(state, msgs, info, name, ex, c, h1full, c15, now, oi, q, sw_day=None, master=None, api=None):
    """Volume-breakout alerts on 3-hour and daily candles + trailing-stop follow-ups."""
    if h1full is None or h1full.empty:
        info["breakout"] = "no 1-hour history"; return
    if "volume" in h1full and float(h1full["volume"].tail(100).fillna(0).sum()) == 0:
        info["not_traded"] = True                         # 28-Oct: ALUMINIUM / ZINC mega contracts show no volume
        info["breakout"] = "skipped: contract not traded (zero volume) – volume rule cannot work"; return
    frames = {"3h": positional_candles(h1full, ex, now)}
    dd = BO.daily_candles(h1full, None)
    if dd is not None and len(dd) and is_open(ex, now):                # today's daily candle is still forming
        dd = dd[dd["time"].dt.normalize() < now.normalize()]
    frames["1d"] = dd
    wk = BO.weekly_candles(dd)                                      # completed weeks only (current week still forming)
    if wk is not None and len(wk) and pd.Timestamp(wk["time"].iloc[-1]).to_period("W") == now.to_period("W"):
        wk = wk.iloc[:-1]
    # weekly calls OFF 28-Oct: stop-loss 3 weekly ATR = 13-28% away (GOLD / SILVER) – not tradable
    frames["1m"] = dd                                               # monthly breakout is checked on daily closes
    htf = BO.htf_levels(dd)
    state.setdefault("bo_active", [])
    if ex == "MCX":                                                  # 29-Oct (approved, live): candle-setup calls
        try:
            lv_ = (q or {}).get("ltp")
            CS.on_mcx(state, msgs, name, ex, c, dd, frames["3h"], c15, now, live=float(lv_) if lv_ not in (None, "", 0) else None)
            info["setups"] = " · ".join(f"{r['setup']} {r['status']}" for r in state["candle_setups"]["open"] if r["name"] == name) or "none"
        except Exception as e_:
            print(f"[setup] {name} skipped: {type(e_).__name__}: {e_}")
    for tf, fr in frames.items():
        BO.manage(state, msgs, name, tf, fr, c15, now)
        if fr is None or len(fr) < 30:
            info[f"bo_{tf}"] = "insufficient candles"; continue
        last = str(fr["time"].iloc[-1])
        k = f"BO|{name}|{tf}"
        if state["last_eval"].get(k) == last:
            continue
        state["last_eval"][k] = last
        sig = BO.evaluate_weekly(fr) if tf == "1w" else BO.evaluate_monthly(fr) if tf == "1m" else BO.evaluate(fr)
        info[f"bo_{tf}"] = f"{sig['side'] or 'none'} · {sig.get('why', '')} · vol {sig.get('vol_x') or 0:.2f}×"
        if sig.get("hh") is not None:
            state.setdefault("status", {})[f"{name}|{tf}"] = dict(candle=last, close=round(sig["close"], 2), buy_above=round(sig["hh"], 2),
                                                                   sell_below=round(sig["ll"], 2), ema200=round(sig["ema200"], 2),
                                                                   vol_x=round(sig.get("vol_x") or 0, 2), result=sig["side"] or sig.get("why"))
        if not sig["side"] and tf in PATTERN_TFS:                     # no breakout -> chart pattern (INST-PAT-001)
            ps = PT.evaluate(fr)
            info[f"pat_{tf}"] = ps.get("pattern") or ps.get("why")
            if ps["side"]:
                sig = ps
        if not sig["side"]:
            continue
        if sw_day is not None and pd.Timestamp(sig["candle"]).normalize() == sw_day:
            info[f"bo_{tf}"] += " · skipped: contract-switch day (volume distorted)"; continue
        if oi and oi.get("label") and oi["label"] not in {"BUY": ("Long buildup", "Short covering"), "SELL": ("Short buildup", "Long unwinding")}[sig["side"]]:
            info[f"bo_{tf}"] += f" · skipped: OI {oi['label']} does not confirm"; continue
        if any(p["name"] == name and p["tf"] in (tf, "1d", "1m") and tf in ("1d", "1m") and p["tf"] != "3h" and not p.get("shadow")
               for p in state["bo_active"]) and tf in ("1d", "1m"):
            info[f"bo_{tf}"] += " · already in an open daily/monthly call"; continue
        shadow_only = (tf, sig["side"]) in SHADOW_ONLY
        if any(p["name"] == name and p["tf"] == tf and bool(p.get("shadow")) == shadow_only for p in state["bo_active"]):
            info[f"bo_{tf}"] += " · already in an open breakout alert" + (" (log-only)" if shadow_only else ""); continue
        sid = f"{k}|{last}|{sig['side']}" + (f"|{sig['pattern']}" if sig.get("pattern") else "")
        if sid in state["seen"]:
            continue
        state["seen"] = (state["seen"] + [sid])[-2000:]
        lv = S.levels(fr, h1full, sig["close"], sig["atr"]) if TP.finite(sig.get("close"), sig.get("atr")) else dict(support=[], resistance=[])
        live = (q or {}).get("ltp")
        live = float(live) if live not in (None, "", 0) else None
        s_ = 1 if sig["side"] == "BUY" else -1
        plan = TP.futures_plan(name=name, ex=ex, contract=c["symbol"], tf=tf, side=sig["side"], signal_time=sig["candle"],
                               signal_close=sig.get("close"), atr=sig.get("atr"), stop_mult=BO.stop_k(tf), target_r=BO.TARGET_R.get(tf),
                               tick=c.get("tick"), lot=c.get("lot"), mult=RP.mult_for(name, ex, c.get("lot")),
                               max_sl_pct=BO.MAX_SL_PCT.get(tf, 4.0), live=live, quote=q, now=now, require_live=is_open(ex, now),
                               levels=lv)
        if not plan["valid"]:
            print(f"[rejected] {name} {tf} {sig['side']}: {plan['reason']}")
            info[f"bo_{tf}"] += f" · skipped: {plan['reason']}"; continue
        key = f"{name}|{tf}|{last}"
        if shadow_only:                                   # 28-Oct approval: 3h SELL lost money in every test -> log only
            state["bo_active"].append(_shadow_rec(name, tf, sig["side"], plan, last, now, c, key, "3h SELL (log only, not sent)"))
            info[f"bo_{tf}"] += " · 3h SELL logged only (not sent – STRATEGY-PROGRAM-001)"
            print(f"[shadow] {name} {tf} SELL logged only: entry {plan['entry']} SL {plan['sl']} target {plan['target']}")
            continue
        opt = BO.option_idea(master, name, ex, plan["entry"], sig["side"], tf, now) if master is not None else None
        msgs.append(BO.call_msg(name, ex, c, tf, sig, lv, plan=plan))
        reason = BO.reason_msg(name, tf, sig, lv, oi, q, htf=htf)
        if plan.get("warn"):
            reason = reason.replace("Not investment advice.", f"• Note    : {plan['warn']}\nNot investment advice.")
        if tf == "3h" and sig["side"] == "BUY":            # 28-Oct approval: high-accuracy variant HA-1, log only
            try:
                ha = TP.futures_plan(name=name, ex=ex, contract=c["symbol"], tf=tf, side="BUY", signal_time=sig["candle"],
                                     signal_close=sig.get("close"), atr=sig.get("atr"), stop_mult=3.0, target_r=0.5, tick=c.get("tick"),
                                     lot=c.get("lot"), mult=RP.mult_for(name, ex, c.get("lot")), max_sl_pct=2.5, live=live, quote=q,
                                     now=now, require_live=is_open(ex, now), min_rr=0.45)
                tags = ha_tags(fr, sig)
                if ha["valid"] and tags:
                    state["bo_active"].append(_shadow_rec(name, tf, "BUY", ha, last, now, c, key + "|HA1", "HA-1 " + "+".join(tags)))
            except Exception as e_:
                print("HA-1 shadow skipped:", e_)
        state["bo_active"].append(dict(name=name, tf=tf, side=sig["side"], entry=plan["entry"], stop=plan["sl"], target=plan["target"],
                                       risk=plan["risk_unit"], best=plan["entry"], trailed=False, n=0, last_candle=last, tick=plan["tick"],
                                       checked=str(now), contract=c["symbol"], key=key, token=c["token"]))
        seg = "MCX" if ex == "MCX" else "NSE"
        RP.add(state, key=key, mark_key=c["token"], seg=seg, cat="FUTURES", name=name, symbol=c["symbol"], type=RP.CALL_TYPE[tf],
               side=sig["side"], entry=plan["entry"], sl=plan["sl"], target=plan["target"], tick=plan["tick"],
               lot=c.get("lot"), mult=plan["mult"], time=str(now))
        if opt and api is not None:
            ok, prem, onotes, oskip = OF.check(api, ex, name, opt, plan["entry"], dd, now)
            oplan = TP.option_plan(premium=prem, sl_pct=BO.OPT_SL_TG.get(tf, (0.35, 0.8))[0], tg_pct=BO.OPT_SL_TG.get(tf, (0.35, 0.8))[1],
                                   tick=opt.get("tick"), lot=opt["lot"]) if ok else dict(valid=False, reason=oskip)
            if not oplan["valid"]:
                reason = reason.replace("Not investment advice.", f"• Option  : no option-buy call – {oplan['reason']}\nNot investment advice.")
            else:
                reason = reason.replace("Not investment advice.", f"• Option  : {' · '.join(onotes)}\nNot investment advice.")
                msgs.append(BO.option_msg(name, ex, tf, sig, opt, oplan["entry"], oplan=oplan)[0])
                RP.add(state, key=key + "|OPT", mark_key=c["token"], seg=seg, cat="OPTION BUY", name=name, symbol=opt["symbol"],
                       type=RP.CALL_TYPE[tf], side="BUY", entry=oplan["entry"], sl=oplan["sl"], target=oplan["target"], tick=oplan["tick"],
                       lot=opt["lot"], mult=opt["lot"], time=str(now), und_entry=plan["entry"], und_side=sig["side"])
        msgs.append(reason)
        state["day"]["alerts"] += 1


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
            "Strategy: VOLUME BREAKOUT – close beyond the 20-candle high/low with volume > 1.5× average, in the 200-EMA "
            "trend direction. Swing (3-hour candles) + positional (daily candles). SL 2 ATR, then 3-ATR trailing stop updates.\n"
            f"Instruments with data now: {', '.join(n for n in ok if not rep['instruments'][n].get('not_traded')) or 'none (markets closed)'}\n"
            + (f"Not traded (zero volume, no calls possible): {', '.join(n for n in ok if rep['instruments'][n].get('not_traded'))}\n"
               if any(rep['instruments'][n].get('not_traded') for n in ok) else "")
            + (f"Data problems: {'; '.join(rep['errors'][:6])}\n" if rep["errors"] else "") + WARN)


def eod_msg(day, state):
    o = day.get("outcomes", [])
    return (f"📋 ALERTS – END OF DAY {pd.Timestamp(day['date']):%d-%b-%Y}\n"
            f"BUY/SELL alerts: {day['alerts']} · watch messages: {day['watches']} · suppressed by quality filter: {day.get('suppressed', 0)}\n"
            f"Closed today: " + (", ".join(f"{x['name']} {x['side']} {x['tf']}: {x['result'].split(' –')[0]}" for x in o) or "none") + "\n"
            f"Still open: " + (", ".join(f"{a['name']} {a['side']} {a['tf']}" for a in state["active"]) or "none") + f"\n{WARN}")
