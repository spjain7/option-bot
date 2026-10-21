"""Crude Oil PAPER engine – one scan. Intraday: 15-min entries + 1-hour trend. Positional: completed 3-hour candles.

  scan(api, master, now, mode="scan" | "health", state_path, ...)  -> (run record, outbox messages, exit code)

mode "health" evaluates everything and reports, but never opens/closes positions and never writes state.
Exit codes: 0 ok · 2 data/evaluation problem (reported) · 3 state could not be loaded/saved (reported).
"""
import os, traceback
import pandas as pd
from crude import config as K, data as D, rules as R, paper as P, report as REP

def _fetch(api, rec, label, exch, token, interval, frm, to):
    try:
        df = api.candles(exch, token, interval, frm, to)
    except Exception as e:
        rec["api"][label] = f"error: {type(e).__name__}: {str(e)[:120]}"
        return None
    if df is None or df.empty:
        rec["api"][label] = "FAILED: no candles returned (API error, rate limit or no trading)"
        return None
    df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    rec["api"][label] = f"ok ({len(df)} candles, last start {df['time'].iloc[-1]:%d-%b %H:%M})"
    return df


def _alert_once(state, outbox, key, text):
    day = state["day"]
    if key in day["alerted"]:
        return
    day["alerted"].append(key)
    if K.TELEGRAM["errors"]:
        outbox.append(text)


def _new_day(state, now):
    d = str(now.date())
    if not state.get("day") or state["day"]["date"] != d:
        state["day"] = dict(date=d, realized={"intraday": 0.0, "positional": 0.0}, generated=0, blocked=0, ignored=0,
                            startup_sent=False, eod_sent=False, alerted=[], trades=[])


def scan(api, master, now, mode="scan", state_path="state/crude/state.json", allow_new=False, run_info=None):
    rec = dict(time=str(now), version=K.VERSION, mode=K.MODE, run_mode=mode, run=run_info or {}, api={}, data={},
               decisions={}, actions=[], errors=[], session=D.session_status(now))
    outbox = []
    try:
        state, created = P.load(state_path, now, allow_new)
    except P.StateError as e:
        rec["errors"].append(str(e))
        return rec, [REP.error_msg(now, "STATE LOAD FAILED – scan stopped, nothing evaluated", str(e))], 3
    if created:
        rec["actions"].append("new paper account created")
    _new_day(state, now)
    code = 0
    try:
        code = _scan(api, master, now, mode, state, rec, outbox)
    except Exception as e:
        traceback.print_exc()
        rec["errors"].append(f"evaluation crashed: {type(e).__name__}: {e}")
        code = 2
    if rec["errors"]:
        state["last_error"] = dict(time=str(now), error=rec["errors"][-1])
        _alert_once(state, outbox, "err:" + rec["errors"][-1].split(":")[0][:40], REP.error_msg(now, "Crude engine problem", "; ".join(rec["errors"])))
    rec["last_error"] = state.get("last_error")
    rec["state_summary"] = REP.state_summary(state, rec)
    if mode == "health":
        outbox.insert(0, REP.health(rec)) if K.TELEGRAM["startup"] else None
        return rec, outbox, code
    if not state["day"]["startup_sent"] and K.TELEGRAM["startup"]:
        outbox.insert(0, REP.health(rec, title="STARTUP / DAILY HEALTH"))
        state["day"]["startup_sent"] = True
    state["runs"] = (state["runs"] + [dict(time=rec["time"], session=rec["session"], api=rec["api"], data=rec["data"],
                                           decisions={k: dict(decision=v.get("decision"), side=v.get("side"),
                                                              blocks=v.get("blocks"), bar=v.get("bar_time"))
                                                      for k, v in rec["decisions"].items()},
                                           actions=rec["actions"], errors=rec["errors"])])[-60:]
    try:
        P.save(state_path, state)
    except P.StateError as e:
        rec["errors"].append(str(e))
        return rec, [REP.error_msg(now, "STATE SAVE FAILED – this scan's results are NOT persisted", str(e))], 3
    return rec, outbox, code


def _scan(api, master, now, mode, state, rec, outbox):
    code = 0
    cs = D.resolve(master, now)
    sig, trade = cs["signal"], cs["trade"]
    rec["contract"] = dict(signal=sig, trade=trade, front=cs["front"]["symbol"], rolled=cs["rolled"], issues=cs["issues"])
    for i in cs["issues"]:
        rec["errors"].append("contract: " + i)
    # ── data ──
    c15 = _fetch(api, rec, "15m", "MCX", sig["token"], "FIFTEEN_MINUTE", now - pd.Timedelta(days=21), now)
    h1 = _fetch(api, rec, "1h", "MCX", sig["token"], "ONE_HOUR", now - pd.Timedelta(days=100), now)
    toks = [sig["token"]] + ([trade["token"]] if trade else [])
    try:
        q = api.quotes({"MCX": toks})
    except Exception as e:
        q = {}
        rec["api"]["quote"] = f"error: {type(e).__name__}: {str(e)[:120]}"
    qs, qt = q.get(sig["token"]), q.get(trade["token"]) if trade else None
    rec["api"].setdefault("quote", "ok" if qs and qt else f"FAILED: signal quote {'ok' if qs else 'missing'}, trade quote {'ok' if qt else 'missing'}")
    # roll continuity (signal contract is the vendor-stitched front token unless we are inside the roll window)
    swk = f"{sig['symbol']}|{now.date()}"
    if h1 is not None and cs["signal_is_front"] and cs["after"]:
        if swk not in state["switches"]:
            nx = _fetch(api, rec, "1h-next(roll check)", "MCX", cs["after"]["token"], "ONE_HOUR", now - pd.Timedelta(days=100), now)
            state["switches"] = {swk: [(str(t), s, qlt) for t, s, qlt in D.detect_switches(h1, nx, sig["expiry"])] if nx is not None else []}
        sw = [(pd.Timestamp(t), s, qlt) for t, s, qlt in state["switches"][swk]]
        if not sw:
            prev = D.previous_expiries(sig["expiry"], 1)[0]
            rec["errors"].append("roll continuity: next-contract history unavailable – using only bars after the last expiry")
            h1 = D.continuity(h1, [], horizon_start=prev + pd.Timedelta(days=1))
            c15 = D.continuity(c15, [], horizon_start=prev + pd.Timedelta(days=1)) if c15 is not None else None
        else:
            h1 = D.continuity(h1, sw)
            c15 = D.continuity(c15, sw) if c15 is not None else None
        rec["data"]["roll"] = ", ".join(f"{t:%d-%b} {('old−new ' + format(s, '+.0f')) if q_ == 'measured' else 'not measurable (history cut)'}" for t, s, q_ in sw) or "history cut at last expiry"
    else:
        rec["data"]["roll"] = "signal contract is not the stitched front token – its own data, no adjustment"
    c15c = D.closed(c15, 15, now) if c15 is not None else None
    h1c = D.closed(h1, 60, now) if h1 is not None else None
    h3c = D.three_hour(h1c, now) if h1c is not None else None
    for lbl, d in (("15m", c15c), ("1h", h1c), ("3h", h3c)):
        rec["data"][f"last_closed_{lbl}"] = None if d is None or d.empty else str(d["time"].iloc[-1])
        rec["data"][f"bars_{lbl}"] = 0 if d is None else len(d)
    # freshness: entries need a recently closed 15-min candle; a data PROBLEM is when the exchange is trading
    # (live quote current) but no new candle has appeared for > 25 min. A session resuming after a break (holiday
    # morning) has an old last-closed candle but a new forming one – that is not a problem.
    fresh = False
    in_session = rec["session"] == "OPEN" and now >= D.hm(now, K.SESSION_OPEN) + pd.Timedelta(minutes=K.STALE_15M_MIN + 15)
    if c15c is not None and not c15c.empty:
        last_end = D.bar_end(c15c["time"].iloc[-1], 15)
        age = (now - last_end).total_seconds() / 60
        rec["data"]["age_15m_min"] = round(age, 1)
        fresh = rec["session"] == "OPEN" and age <= K.STALE_15M_MIN
        raw_age = (now - c15["time"].iloc[-1]).total_seconds() / 60
        if in_session and raw_age > 15 + 10:
            rec["stale"] = f"newest 15-min candle started {raw_age:.0f} min ago, last closed one ended {age:.0f} min ago"
    elif in_session:
        rec["stale"] = "no 15-min candles returned"
    if h1c is None and rec["session"] == "OPEN":
        rec["errors"].append("NO 1-HOUR DATA during the session")
        code = 2
    qfresh = False
    if qs:
        ft = D.parse_feed_time(qs.get("exchFeedTime", ""))
        qage = None if ft is None else (now - ft).total_seconds() / 60
        qfresh = qage is not None and qage <= K.STALE_QUOTE_MIN
        rec["data"]["quote_age_min"] = None if qage is None else round(qage, 1)
        rec["data"]["ltp"] = qs.get("ltp")
        rec["data"]["day_volume"] = qs.get("tradeVolume")
    if rec.get("stale"):
        if qfresh:                                        # exchange is trading but candles lag -> real data problem
            rec["errors"].append("STALE CANDLES: " + rec["stale"] + " while the live quote is current")
            code = 2
        else:                                             # nothing trading: holiday / session break / feed down
            rec["warnings"] = rec.get("warnings", []) + ["NO FRESH DATA: " + rec["stale"] + "; live quote also not current – exchange closed (holiday?) or feed down"]
            _alert_once(state, outbox, "nofresh", REP.error_msg(now, "No fresh Crude data", rec["warnings"][-1]))
    rec["data"]["volume"] = "available" if c15c is not None and len(c15c) and (c15c["volume"] > 0).mean() > 0.9 else "UNAVAILABLE/partial"
    # OI from live snapshots only
    snap = None
    if qs and isinstance(qs.get("opnInterest"), (int, float)) and qs.get("opnInterest") > 0:
        ft = D.parse_feed_time(qs.get("exchFeedTime", "")) or now
        snap = dict(time=str(ft), contract=sig["symbol"], oi=qs["opnInterest"], ltp=qs.get("ltp"), volume=qs.get("tradeVolume"))
    oi = D.oi_change(state["oi_snaps"], sig["symbol"], snap)
    rec["data"]["oi_current"] = None if snap is None else snap["oi"]
    rec["data"]["oi_change"] = oi
    rec["data"]["oi_history"] = "UNAVAILABLE (Angel getOIData returns AB1012 for MCX)"
    if snap and mode != "health":
        state["oi_snaps"] = [s for s in state["oi_snaps"] if (now - pd.Timestamp(s["time"])).days < 3] + [snap]
    # ── manage open positions ──
    ltp_t = qt.get("ltp") if qt else None
    if mode != "health":
        _manage(api, master, state, rec, outbox, now, cs, h3c, ltp_t)
    # ── evaluate entries ──
    loss_today = sum(state["day"]["realized"].values()) + sum(P.mtm(p, ltp_t) for e in state["engines"].values()
                                                                for p in e["open"] if ltp_t)
    limit = -K.DAILY_LOSS_PCT * (state["capital"] + state["realized"])
    rec["data"]["daily_pnl"] = round(loss_today, 2)
    gates = []
    if rec["session"] != "OPEN":
        gates.append(f"market {rec['session']}")
    if not fresh:
        gates.append("15-min data not fresh")
    if not qfresh:
        gates.append("live quote missing/stale")
    if not qt or not qt.get("ltp"):
        gates.append("paper-contract quote missing")
    if cs["issues"]:
        gates.append("contract data issue")
    if qs and (qs.get("tradeVolume") or 0) < K.MIN_DAY_VOLUME["signal"]:
        gates.append(f"signal contract illiquid today ({qs.get('tradeVolume')} lots < {K.MIN_DAY_VOLUME['signal']})")
    if qt and (qt.get("tradeVolume") or 0) < K.MIN_DAY_VOLUME["trade"]:
        gates.append(f"paper contract illiquid today ({qt.get('tradeVolume')} lots)")
    # intraday
    if c15c is not None and len(c15c) and h1c is not None:
        bar = str(c15c["time"].iloc[-1])
        end15 = D.bar_end(c15c["time"].iloc[-1], 15)
        h1_ok = D.htf_closed_by(h1c, end15)
        dec = R.intraday(c15c, h1_ok)
        dec["bar_time"] = bar
        win = D.hm(now, K.FIRST_ENTRY) <= c15c["time"].iloc[-1] and end15 <= D.session_close(now) - pd.Timedelta(minutes=K.LAST_ENTRY_BEFORE_CLOSE_MIN)
        g = gates + ([] if win else ["outside the intraday entry window"])
        _decide(state, rec, outbox, now, "intraday", dec, bar, g, oi, cs, qs, qt, mode)
    else:
        rec["decisions"]["intraday"] = dict(decision="NONE", blocks=["no 15-min / 1-hour data"])
    # positional
    if h3c is not None and len(h3c):
        bar = str(h3c["time"].iloc[-1])
        dec = R.positional(h3c)
        dec["bar_time"] = bar
        g = gates + ([] if sig["days_left"] > K.FLAT_BEFORE_EXPIRY_DAYS else ["contract too close to expiry"])
        _decide(state, rec, outbox, now, "positional", dec, bar, g, oi, cs, qs, qt, mode)
    else:
        rec["decisions"]["positional"] = dict(decision="NONE", blocks=["no completed 3-hour candles"])
    # end of day
    if mode != "health" and now > D.session_close(now) and not state["day"]["eod_sent"]:
        if K.TELEGRAM["eod"]:
            outbox.append(REP.eod(state, rec))
        state["day"]["eod_sent"] = True
    return code


def _decide(state, rec, outbox, now, engine, dec, bar, gates, oi, cs, qs, qt, mode):
    eng = state["engines"][engine]
    new_bar = eng["last_eval_bar"] != bar
    dec["new_candle"] = new_bar
    rec["decisions"][engine] = dec
    if dec["decision"] == "SIGNAL":
        ob, tag = R.oi_gate(dec["side"], oi)
        dec["oi"] = tag
        if ob:
            dec["decision"], dec["blocks"] = "BLOCKED", dec["blocks"] + [ob]
    if mode == "health" or not new_bar:
        return
    eng["last_eval_bar"] = bar
    print(f"[{engine}] candle {bar}: {dec['decision']} {dec.get('side', '')} | " + " | ".join(dec.get("blocks") or dec.get("reasons") or []))
    if dec["decision"] == "BLOCKED":
        state["day"]["blocked"] += 1
        return
    if dec["decision"] != "SIGNAL":
        return
    state["day"]["generated"] += 1
    sid = f"{engine}|{cs['signal']['symbol']}|{bar}|{dec['side']}"
    why = None
    if sid in state["seen"]:
        why = "duplicate signal id (already handled)"
    elif gates:
        why = "; ".join(gates)
    elif state["day"]["realized"][engine] + sum(P.mtm(p, qt["ltp"]) for p in eng["open"]) <= -K.DAILY_LOSS_PCT * (state["capital"] + state["realized"]):
        why = f"{engine} daily loss limit ({K.DAILY_LOSS_PCT:.0%} of equity) reached"
    elif len(eng["open"]) >= K.MAX_OPEN[engine]:
        why = f"max open {engine} positions ({K.MAX_OPEN[engine]}) reached"
    elif eng["last_exit_bar"] and _bars_since(eng["last_exit_bar"], bar, engine) < K.COOLDOWN_BARS[engine]:
        why = f"cool-down after the last exit ({K.COOLDOWN_BARS[engine]} candles)"
    plan = dec["plan"]
    a, P_ = plan["atr"], (K.INTRA if engine == "intraday" else K.POS)
    if not why and abs(qs["ltp"] - dec["signal_close"]) > P_["max_chase_atr"] * a:
        why = f"price ran {abs(qs['ltp'] - dec['signal_close']):.0f} pts from the signal close (> {P_['max_chase_atr']} ATR) – not chased"
    t = cs["trade"]
    lots = 0
    if not why:
        cap = state["capital"] + state["realized"]
        lots, budget, per_lot = P.size(cap, plan["stop_dist"], qt["ltp"], t["lotsize"], t["tick"])
        if lots < 1:
            why = f"1 lot of {t['symbol']} risks ₹{per_lot:,.0f} > budget ₹{budget:,.0f} ({K.RISK_PCT:.2%} of ₹{cap:,.0f})"
    state["seen"] = (state["seen"] + [sid])[-500:]
    if why:
        state["day"]["ignored"] += 1
        dec["ignored"] = why
        rec["actions"].append(f"{engine} {dec['side']} signal ignored: {why}")
        return
    fill = P.slip(dec["side"], qt["ltp"], t["tick"], opening=True)
    pos = P.open_position(engine, dec["side"], fill, plan, lots, t["lotsize"], t["tick"], t["symbol"],
                          dict(id=sid, time=str(now), last_bar=None, signal_contract=cs["signal"]["symbol"],
                               expiry=t["expiry"], setup=dec["setup"], oi=dec.get("oi"), signal_bar=bar,
                               reasons=dec["reasons"], ltp_at_entry=qt["ltp"]))
    pos["last_bar"] = str(D.floor15(now) - pd.Timedelta(minutes=15))
    eng["open"].append(pos)
    rec["actions"].append(f"{engine} {dec['side']} opened {lots} lot(s) {t['symbol']} @ {fill}")
    if K.TELEGRAM["signals"]:
        outbox.append(REP.entry_msg(pos, dec, cs, state))


def _bars_since(a, b, engine):
    m = 15 if engine == "intraday" else 180
    return (pd.Timestamp(b) - pd.Timestamp(a)).total_seconds() / 60 / m


def _manage(api, master, state, rec, outbox, now, cs, h3c, ltp):
    opens = [(e, p) for e, eng in state["engines"].items() for p in eng["open"]]
    if not opens:
        return
    bars_by, ltp_by = {}, {cs["trade"]["token"]: ltp}
    for e, p in opens:
        tok = cs["trade"]["token"] if p["contract"] == cs["trade"]["symbol"] else None
        if tok is None:                                   # position in the previous contract (we are now in the roll window)
            m = D.futures(master, K.TRADE_NAME)
            m = m[m["symbol"] == p["contract"]]
            tok = str(m["token"].iloc[0]) if len(m) else None
            if tok and tok not in ltp_by:
                try:
                    ltp_by[tok] = (api.quotes({"MCX": [tok]}).get(tok) or {}).get("ltp")
                except Exception:
                    ltp_by[tok] = None
        if tok and tok not in bars_by:
            d = _fetch(api, rec, f"15m {p['contract']}", "MCX", tok, "FIFTEEN_MINUTE", pd.Timestamp(p["entry_time"]) - pd.Timedelta(hours=1), now)
            bars_by[tok] = D.closed(d, 15, now) if d is not None else None
        bars = bars_by.get(tok)
        exit_ = None
        if bars is not None:
            new = bars[bars["time"] > pd.Timestamp(p["last_bar"])] if p["last_bar"] else bars
            new = new[new["time"] >= D.floor15(pd.Timestamp(p["entry_time"]))]
            for b in new.itertuples():
                entry_bar = b.time == D.floor15(pd.Timestamp(p["entry_time"]))
                if p["engine"] == "intraday" and D.bar_end(b.time, 15) > D.session_close(b.time) - pd.Timedelta(minutes=K.SQUARE_OFF_BEFORE_CLOSE_MIN):
                    exit_ = (P.slip(p["side"], b.open, p["tick"], False), "intraday square-off", b.time)
                    break
                r = P.step_bar(p, b._asdict(), stop_only=entry_bar)
                p["last_bar"] = str(b.time)
                if r:
                    exit_ = (r[0], r[1], D.bar_end(b.time, 15))
                    break
        lt = ltp_by.get(tok)
        if not exit_ and lt:
            ltp = lt
            sgn = 1 if p["side"] == "BUY" else -1
            if sgn * (ltp - p["stop"]) <= 0:
                exit_ = (P.slip(p["side"], ltp, p["tick"], False), "stop-loss (live price)", now)
            elif sgn * (ltp - p["target"]) >= p["tick"]:
                exit_ = (p["target"], "target (live price)", now)
            elif p["engine"] == "intraday" and now >= D.session_close(now) - pd.Timedelta(minutes=K.SQUARE_OFF_BEFORE_CLOSE_MIN):
                exit_ = (P.slip(p["side"], ltp, p["tick"], False), "intraday square-off", now)
        if not exit_ and p["engine"] == "positional":
            exit_ = _positional_rules(p, h3c, ltp_by.get(tok), now, cs)
        if exit_:
            done = P.close_position(p, exit_[0], exit_[1], exit_[2])
            eng = state["engines"][e]
            eng["open"] = [x for x in eng["open"] if x["id"] != p["id"]]
            eng["closed"] = (eng["closed"] + [done])[-400:]
            eng["last_exit_bar"] = str(D.floor15(pd.Timestamp(exit_[2]))) if e == "intraday" else (str(h3c["time"].iloc[-1]) if h3c is not None and len(h3c) else str(now))
            state["realized"] = round(state["realized"] + done["pnl"], 2)
            state["day"]["realized"][e] = round(state["day"]["realized"][e] + done["pnl"], 2)
            state["day"]["trades"].append(dict(engine=e, side=p["side"], pnl=done["pnl"], r=done["r"], reason=done["exit_reason"]))
            rec["actions"].append(f"{e} {p['side']} closed @ {exit_[0]} ({exit_[1]}) P&L ₹{done['pnl']:,.0f}")
            if K.TELEGRAM["signals"]:
                outbox.append(REP.exit_msg(done, state))


def _positional_rules(p, h3c, ltp, now, cs):
    if ltp is None:
        return None
    sgn = 1 if p["side"] == "BUY" else -1
    days_left = D.trading_days_between(now.normalize(), p["expiry"])
    if days_left <= K.FLAT_BEFORE_EXPIRY_DAYS:
        return (P.slip(p["side"], ltp, p["tick"], False), f"roll: contract expires in {days_left} trading days", now)
    if h3c is not None and len(h3c) > K.POS["ema_slow"]:
        done = h3c[h3c["time"] > pd.Timestamp(p["signal_bar"])]
        if len(done):
            from crude.indicators import ema
            e = ema(h3c["close"], K.POS["ema_slow"]).iloc[-1]
            if sgn * (h3c["close"].iloc[-1] - e) < 0:
                return (P.slip(p["side"], ltp, p["tick"], False), f"3-hour close beyond EMA{K.POS['ema_slow']} (trend failed)", now)
    sess = set(p["sessions"]) | {str(now.date())}
    p["sessions"] = sorted(sess)
    if len(sess) > K.POS["max_hold_sessions"]:
        return (P.slip(p["side"], ltp, p["tick"], False), f"time stop ({K.POS['max_hold_sessions']} sessions)", now)
    return None
