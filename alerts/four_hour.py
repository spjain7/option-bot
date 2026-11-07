"""4-HOUR futures calls (owner approved 30-Oct-2026; research TFNH-001 / TFLOG-002, research branch exp/strategy-program-001).

  MCX 4h BUY   : 4-hour candles 09-13 / 13-17 / 17-21 / 21-close. Close above the 10-candle high, volume ≥ 1.5× the 20-candle
                 average, daily trend up (6-Nov). Stop 2 ATR, target 3R, time exit 10 sessions, stop cap 2.5 %.
                 Backtest 2022-26 (2× costs): +0.42R/trade, 259 trades (+0.48 / +0.09 / +0.55 by period).
  STOCK 3h SELL: 3-hour candles 09:15-12:15 / 12:15-15:15, 5-candle low, volume ≥ 2×, daily trend down, 1.5 ATR / 2R (6-Nov).
  STOCK 4h SELL: NSE 4-hour candles 09:15-13:15 and 13:15-15:30 (fixed day blocks, so live = test). Close below the 5-candle
                 low, volume > 2×, close below EMA200. Stop 2 ATR, target 2R, time exit 40 candles (~20 sessions), cap 4 %.
                 Backtest 2023-26 with these day blocks: +0.12R/trade, 1,452 trades (+0.10 / −0.02 / +0.18) – weaker than BUY.
Owner rules on top (30-Oct):
  * OI must support the move, measured over the signal candle from the live 1-minute OI (BUY: long buildup / short covering;
    SELL: short buildup / long unwinding). OI not available -> no call (never assumed).
  * No nearby level against the call: no resistance (BUY) / support (SELL) within 0.5R of the entry (tested: within 0.5R is
    neutral to slightly positive; within 1R or more lowered results).
Tracking: every scan on the live price (stop / target touched -> exit message), time exit, exit 1 session before expiry.
ALERTS ONLY – no orders.
"""
import pandas as pd
from crude import indicators as I
from alerts import tradeplan as TP, report as RP, signals as S

# 6-Nov (owner approved, SEARCH-ALL-001 walk-forward + FDR): MCX 4h BUY = 10-candle high, volume ≥ 1.5×, DAILY TREND UP (previous
#  day EMA20 > EMA50 and close > EMA50) instead of EMA200, stop 2 ATR, target 3R: 259 trades, 44 %, +0.42R, all 7 commodities positive.
#  NEW stock 3h SELL ("NFO3H"): 5-candle low, volume ≥ 2×, daily trend DOWN, stop 1.5 ATR, target 2R: 1,335 trades, 50 %, +0.13R.
#  The owner rules (OI over the candle must support, no opposing level within 0.5R) stay on top of both.
RULES = {"MCX": dict(side="BUY", N=10, vol=1.5, k=2.0, r=3.0, cap=2.5, max_days=10, ema=False, dtrend=1, tf="4h",
                     label="SWING (4-hour candles)"),
         "NFO": dict(side="SELL", N=5, vol=2.0, k=2.0, r=2.0, cap=4.0, max_days=20, tf="4h", label="SWING (4-hour candles)"),
         "NFO3H": dict(side="SELL", N=5, vol=2.0, k=1.5, r=2.0, cap=4.0, max_days=20, ema=False, dtrend=-1, tf="3h",
                       label="SWING (3-hour candles)")}
TFTXT = {"4h": "4-hour", "3h": "3-hour"}
GOOD = {"BUY": ("Long buildup", "Short covering"), "SELL": ("Short buildup", "Long unwinding")}
NEAR_R = 0.5
OPTION_HOOK = None        # set by alerts.stocks.scan4h: (call, 1h candles) -> option-idea message
STATS = {"MCX": "📚 Backtest 2022-26 (after 2× costs): +0.42R per trade, 259 trades, 44% won, positive in every period, 7/7 commodities.",
         "NFO": "📚 Backtest 2023-26 (after 2× costs): +0.12R per trade, 1,452 trades; slightly negative in 2024-25 – smaller size.",
         "NFO3H": "📚 Backtest 2022-26 (after 2× costs): +0.13R per trade, 1,335 trades, 50% won, positive in every period."}
WARN = "Alert only – not investment advice."


def store(state):
    return state.setdefault("fourh", dict(open=[], closed=[], last={}))


def four_hour(h1, ex, now):
    """Completed 4-hour candles from completed 1-hour candles."""
    if h1 is None or h1.empty:
        return None
    d = h1.copy()
    d["day"] = d["time"].dt.normalize()
    if ex == "MCX":
        d["k"] = ((d["time"].dt.hour - 9).clip(lower=0) // 4).astype(int)
        ends = {0: (13, 0), 1: (17, 0), 2: (21, 0), 3: (23, 30)}
    else:
        d["k"] = (d["time"].dt.strftime("%H:%M") >= "13:15").astype(int)
        ends = {0: (13, 15), 1: (15, 30)}
    g = d.groupby(["day", "k"])
    out = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum")).reset_index()
    out["end"] = [day + pd.Timedelta(hours=ends[k][0], minutes=ends[k][1]) for day, k in zip(out["day"], out["k"])]
    out = out[out["end"] + pd.Timedelta(minutes=1) <= now]
    return out[["time", "open", "high", "low", "close", "volume", "end"]].reset_index(drop=True)


def candle_oi(api, ex, token, t0, t1, d_price):
    """OI change over [t0, t1] from the live 1-minute OI (WebSocket bars) -> dict(chg_pct, label) or None."""
    try:
        o = api.oi_history(ex, str(token), "ONE_MINUTE", pd.Timestamp(t0) - pd.Timedelta(minutes=1), pd.Timestamp(t1))
    except Exception:
        o = None
    if o is None or len(o) < 2:
        return None
    o = o.dropna(subset=["oi"])
    o = o[o["oi"] > 0]
    if len(o) < 2:
        return None
    a, b = float(o["oi"].iloc[0]), float(o["oi"].iloc[-1])
    chg = b / a - 1
    if chg == 0 or d_price == 0:
        return dict(oi=b, chg_pct=0.0, label=None)
    lab = ("Long buildup" if d_price > 0 else "Short buildup") if chg > 0 else ("Short covering" if d_price > 0 else "Long unwinding")
    return dict(oi=b, chg_pct=round(chg * 100, 2), label=lab)


def evaluate(fr, rule):
    """Last completed 4h candle -> dict(side or None, why, numbers)."""
    need = 210 if rule.get("ema", True) else 60
    if fr is None or len(fr) < need:
        return dict(side=None, why=f"needs {need} candles, have {0 if fr is None else len(fr)}")
    c, h, l, v = fr["close"], fr["high"], fr["low"], fr["volume"].astype(float)
    i = len(fr) - 1
    hh, ll = float(h.shift(1).rolling(rule["N"]).max().iloc[i]), float(l.shift(1).rolling(rule["N"]).min().iloc[i])
    va = float(v.rolling(20).mean().shift(1).iloc[i])
    vx = float(v.iloc[i]) / va if va > 0 else 0.0
    e = float(I.ema(c, 200).iloc[i]); a = float(I.atr(fr, 14).iloc[i]); x = float(c.iloc[i])
    out = dict(candle=str(fr["time"].iloc[i]), end=str(fr["end"].iloc[i]), close=x, hh=hh, ll=ll, ema200=e, atr=a, vol_x=round(vx, 2),
               open=float(fr["open"].iloc[i]))
    use_e = rule.get("ema", True)
    if rule["side"] == "BUY":
        ok = x > hh and vx >= rule["vol"] and (x > e or not use_e)
        why = f"no {rule['N']}-candle breakout" if x <= hh else f"volume {vx:.1f}× (< {rule['vol']:g}×)" if vx < rule["vol"] else "below EMA200"
    else:
        ok = x < ll and vx >= rule["vol"] and (x < e or not use_e)
        why = f"no {rule['N']}-candle breakdown" if x >= ll else f"volume {vx:.1f}× (< {rule['vol']:g}×)" if vx < rule["vol"] else "above EMA200"
    return dict(out, side=rule["side"] if ok else None, why="" if ok else why)


def on_candles(state, msgs, api, name, ex, c, h1, fr, q, now, mult, after_close=False, rule_key=None, dtrend=None):
    """Funnel wrapper (6-Nov): counts every fired signal once per candle and why it was not sent."""
    global LAST_SIG
    LAST_SIG = None
    res = _on_candles(state, msgs, api, name, ex, c, h1, fr, q, now, mult, after_close, rule_key, dtrend)
    if LAST_SIG:
        try:
            from alerts import funnel as FN
            rk = rule_key or ex
            rule = f"{'MCX' if ex == 'MCX' else 'STOCK'} {RULES[rk].get('tf', '4h')} {LAST_SIG[0]}"
            key = f"{name}|{LAST_SIG[1]}"
            FN.note(state, rule, "signal", key=key, now=now)
            if res == "SENT":
                FN.note(state, rule, "sent", key=key, now=now)
            else:
                FN.note(state, rule, "rejected", str(res).replace("skipped: ", "").replace("not sent: ", ""), key=key, now=now)
        except Exception as e_:
            print(f"[funnel] {name} skipped: {type(e_).__name__}: {e_}")
    return res


LAST_SIG = None


def _on_candles(state, msgs, api, name, ex, c, h1, fr, q, now, mult, after_close=False, rule_key=None, dtrend=None):
    """Called with the instrument's completed candles (fr: 4h, or 3h for rule NFO3H). Sends at most one new call per candle.
    dtrend: +1 / -1 / 0 daily trend of the last completed day (rules with 'dtrend' require it to agree)."""
    st = store(state)
    rk = rule_key or ex
    rule = RULES[rk]
    tft = TFTXT[rule.get("tf", "4h")]
    if fr is None or not len(fr):
        return f"no {tft} candles"
    last = str(fr["time"].iloc[-1])
    k = f"{name}|{ex}" if rk == ex else f"{name}|{rk}"
    if st["last"].get(k) == last:
        return "already checked"
    st["last"][k] = last
    sig = evaluate(fr, rule)
    if not sig["side"]:
        return sig["why"]
    global LAST_SIG
    LAST_SIG = (sig["side"], sig["candle"])
    if rule.get("dtrend") and dtrend != rule["dtrend"]:
        print(f"[{rule.get('tf', '4h')}] {name} {sig['side']} skipped: daily trend not {'up' if rule['dtrend'] > 0 else 'down'}")
        return f"skipped: daily trend not {'up' if rule['dtrend'] > 0 else 'down'}"
    if any(r["name"] == name and r["ex"] == ex and not r.get("rule") for r in st["open"]):
        return "already in an open swing (4-hour / 3-hour) call"
    s_ = 1 if sig["side"] == "BUY" else -1
    oi = candle_oi(api, ex, c["token"], sig["candle"], sig["end"], sig["close"] - sig["open"])
    if oi is None or oi.get("label") is None:
        print(f"[4h] {name} {sig['side']} skipped: OI over the candle not available")
        return "skipped: OI over the candle not available"
    if oi["label"] not in GOOD[sig["side"]]:
        print(f"[4h] {name} {sig['side']} skipped: OI {oi['label']} does not support it")
        return f"skipped: OI {oi['label']}"
    live = float((q or {}).get("ltp") or 0) or None
    lv = S.levels(fr.drop(columns=["end"]), h1, sig["close"], sig["atr"])
    plan = TP.futures_plan(name=name, ex=ex, contract=c["symbol"], tf=rule.get("tf", "4h"), side=sig["side"], signal_time=sig["candle"],
                           signal_close=sig["close"], atr=sig["atr"], stop_mult=rule["k"], target_r=rule["r"], tick=c.get("tick"),
                           lot=c.get("lot"), mult=mult, max_sl_pct=rule["cap"], live=None if after_close else live,
                           quote=None if after_close else q, now=now, require_live=not after_close, levels=lv)
    if not plan["valid"]:
        print(f"[4h] {name} {sig['side']} rejected: {plan['reason']}")
        return f"skipped: {plan['reason']}"
    opp = [x for x in (lv["resistance"] if s_ > 0 else lv["support"]) if s_ * (x[0] - plan["entry"]) > 0]
    if opp and s_ * (opp[0][0] - plan["entry"]) < NEAR_R * plan["risk_unit"]:
        what = "resistance" if s_ > 0 else "support"
        print(f"[4h] {name} {sig['side']} skipped: {what} {opp[0][0]} ({opp[0][1]}) within {NEAR_R}R")
        return f"skipped: {what} {opp[0][0]:,.2f} within {NEAR_R}R"
    from alerts import strategies as ST_
    clash = ST_.conflict(state, name, sig["side"], rule.get("tf", "4h"))  # 4-Nov: no contradictory / duplicate live calls
    if clash:
        print(f"[4h] {name} {sig['side']} not sent: {clash}")
        return f"not sent: {clash}"
    t = plan["tick"]
    nxt = opp[0] if opp else None
    sr = (f"• {'Resistance' if s_ > 0 else 'Support':10s}: none found {'above' if s_ > 0 else 'below'} ✅" if nxt is None else
          f"• {'Resistance' if s_ > 0 else 'Support':10s}: {TP.fmt(nxt[0], t)} ({nxt[1]}) at {s_ * (nxt[0] - plan['entry']) / plan['risk_unit']:.1f}R"
          + (" – before the target, may pause there" if s_ * (nxt[0] - plan["target"]) < 0 else " – beyond the target ✅"))
    msgs.append("\n".join([
        f"{'🟢 BUY' if s_ > 0 else '🔴 SELL'}  {name} FUT  ·  {rule['label']}",
        "━━━━━━━━━━━━━━",
        f"Entry   : {TP.fmt(plan['entry'], t)}",
        f"SL      : {TP.fmt(plan['sl'], t)}",
        f"Target  : {TP.fmt(plan['target'], t)}  ({rule['r']:g}R)",
        f"Lot     : {c.get('lot') or '-'}  ·  {pd.Timestamp(c['expiry']):%b} expiry  ·  {'MCX' if ex == 'MCX' else 'NSE'}"]
        + (["ENTRY at the next session's open (skip if it opens more than 0.5 ATR past this price)"] if after_close else [])))
    msgs.append("\n".join([
        f"📌 WHY – {name} {sig['side']} ({tft})",
        f"• Candle  : {pd.Timestamp(sig['candle']):%d-%b %H:%M}–{pd.Timestamp(sig['end']):%H:%M} closed {TP.fmt(sig['close'], t)} "
        f"{'above the ' + str(rule['N']) + '-candle high' if s_ > 0 else 'below the ' + str(rule['N']) + '-candle low'} {TP.fmt(sig['hh'] if s_ > 0 else sig['ll'], t)}",
        f"• Volume  : {sig['vol_x']:.1f}× the 20-candle average ✅",
        f"• OI      : {oi['oi']:,.0f} ({oi['chg_pct']:+.2f}% during the candle) → {oi['label']} ✅",
        (f"• Trend   : {'above' if s_ > 0 else 'below'} EMA200 {TP.fmt(sig['ema200'], t)} ✅" if rule.get("ema", True) else
         f"• Trend   : daily trend {'UP' if s_ > 0 else 'DOWN'} (EMA20 {'>' if s_ > 0 else '<'} EMA50, close {'above' if s_ > 0 else 'below'} EMA50) ✅"),
        sr,
        f"• Risk    : {TP.fmt(plan['risk_unit'], t)} pts ({plan['sl_pct']:.2f}%) · ₹{plan['risk_lot']:,.0f} per lot · "
        f"time exit after {rule['max_days']} sessions",
        STATS[rk], WARN]))
    key = f"{'4H' if rule.get('tf', '4h') == '4h' else '3H'}|{name}|{last}"
    st["open"].append(dict(name=name, ex=ex, token=str(c["token"]), contract=c["symbol"], expiry=c["expiry"], side=sig["side"],
                           entry=plan["entry"], stop=plan["sl"], target=plan["target"], risk=plan["risk_unit"], tick=t, mult=mult,
                           opened=str(now), days=[str(now.date())], key=key, max_days=rule["max_days"], tfl=tft))
    gf = {}
    try:                                                  # 4-Nov: shadow grade (alerts/intel.py) – stored only, never blocks
        import config as C_
        if getattr(C_, "INTEL_SHADOW", True):
            from alerts import intel as IN, breakout as BO_
            dd_ = BO_.daily_candles(h1, None)
            if dd_ is not None and len(dd_):
                dd_ = dd_[dd_["time"].dt.normalize() < pd.Timestamp(now).normalize()]
            gf = IN.shadow_fields(sig["side"], "breakout", fr.drop(columns=["end"], errors="ignore"), daily=dd_, intraday=None,
                                  plan=dict(plan, atr=sig["atr"]), oi_label=oi.get("label"), tag=f"{name} 4h")
    except Exception as e_:
        print(f"[intel] {name} 4h grade skipped: {type(e_).__name__}: {e_}")
    RP.add(state, key=key, mark_key=str(c["token"]), seg="MCX" if ex == "MCX" else "NSE", cat="FUTURES", name=name, symbol=c["symbol"],
           type=f"Swing ({tft})", side=sig["side"], entry=plan["entry"], sl=plan["sl"], target=plan["target"], tick=t,
           lot=c.get("lot"), mult=mult, time=str(now), **gf)
    state["day"]["alerts"] = state["day"].get("alerts", 0) + 1
    if OPTION_HOOK is not None and ex == "NFO":           # 1-Nov: option idea, in-the-money strike near delta 0.75 (DELTA-001)
        try:
            m_ = OPTION_HOOK(dict(name=name, side=sig["side"], entry=plan["entry"], stop=plan["sl"], target=plan["target"]), h1)
            if m_:
                msgs.append(m_)
        except Exception as e_:
            print(f"[4h] option idea {name} skipped: {type(e_).__name__}: {e_}")
    print(f"[4h] {name} {sig['side']} SENT entry {plan['entry']} SL {plan['sl']} target {plan['target']} OI {oi['label']}")
    return "SENT"


def track(state, msgs, api, now, is_open):
    """Every scan: live price vs stop / target, time exit, exit one session before expiry."""
    from alerts import breakout as BO
    st = store(state)
    if not st["open"]:
        return
    keep = []
    by_ex = {}
    for r in st["open"]:
        by_ex.setdefault(r["ex"], []).append(r["token"])
    qq = {}
    for ex, toks in by_ex.items():
        if is_open(ex, now):
            try:
                qq.update(api.quotes({ex: sorted(set(toks))}) or {})
            except Exception:
                pass
    for r in st["open"]:
        s_ = 1 if r["side"] == "BUY" else -1
        if not is_open(r["ex"], now):
            keep.append(r); continue
        d = str(now.date())
        if d not in r["days"]:
            r["days"].append(d)
        ltp = float((qq.get(r["token"]) or {}).get("ltp") or 0)
        if r.get("pending"):                                  # 6-Nov RSIX: stop-entry call waiting for its trigger
            if d not in r["pending_days"]:
                r["pending_days"].append(d)
            if ltp > 0 and s_ * (ltp - r["invalid"]) < 0:
                note = "cancelled – setup candle broken the other way before the trigger"
            elif ltp > 0 and s_ * (ltp - r["trigger"]) >= 0:
                r["pending"] = False; r["days"] = [d]; r["opened"] = str(now)
                if not r.get("shadow"):
                    try:
                        from alerts import funnel as FN_
                        FN_.triggered(state, r.get("rule", "?"), r["key"], now)
                    except Exception:
                        pass
                    msgs.append(f"⚡ ACTIONABLE CALL – TRIGGERED – {r['name']} FUT {r['side']} ({r.get('tfl', 'daily')}) through {TP.fmt(r['trigger'], r['tick'])} "
                                f"(live {TP.fmt(ltp, r['tick'])}) · SL {TP.fmt(r['stop'], r['tick'])} · T2 {TP.fmt(r['target'], r['tick'])}")
                    RP.add(state, key=r["key"], mark_key=r["token"], seg="MCX" if r["ex"] == "MCX" else "NSE", cat="FUTURES",
                           name=r["name"], symbol=r["contract"], type=f"{r.get('tfl', 'daily').capitalize()} RSIX", side=r["side"],
                           entry=r["entry"], sl=r["stop"], target=r["target"], tick=r["tick"], lot=None, mult=r["mult"], time=str(now))
                    state.setdefault("day", {})["alerts"] = state.get("day", {}).get("alerts", 0) + 1
                keep.append(r); continue
            elif len(r["pending_days"]) > r.get("pending_max", 3):
                note = "expired – trigger not reached in 3 sessions"
            else:
                keep.append(r); continue
            if not r.get("shadow"):
                msgs.append(f"⛔ INVALIDATED – {r['name']} FUT {r['side']} ({r.get('tfl', 'daily')}) trigger {TP.fmt(r['trigger'], r['tick'])}: {note} · no trade")
            r.update(exit=None, exit_reason=note, closed=str(now), result_R=None)
            st["closed"] = (st["closed"] + [r])[-200:]
            continue
        why = px = None
        if ltp > 0 and s_ * (ltp - r["stop"]) <= 0:
            why, px = ("trailing stop" if r.get("trailed") else "stop-loss"), r["stop"]
        elif ltp > 0 and r.get("target") is not None and s_ * (ltp - r["target"]) >= 0:
            why, px = "🎯 target", r["target"]
        elif ltp > 0 and len(r["days"]) > r["max_days"]:
            why, px = f"time exit ({r['max_days']} sessions)", ltp
        elif ltp > 0 and (pd.Timestamp(r["expiry"]).normalize() - now.normalize()).days <= 1:
            why, px = "expiry – exit (re-enter in the next month if you wish)", ltp
        if why:
            res = s_ * (px - r["entry"]) / r["risk"] if r["risk"] else 0
            rs = s_ * (px - r["entry"]) * float(r["mult"] or 1)
            icon = "✅" if res > 0 else "❌" if res < 0 else "➖"
            if not r.get("shadow"):                       # 6-Nov rulebook: logged-only calls are tracked silently
                msgs.append(f"{icon} EXIT – {r['name']} FUT {r['side']} ({r.get('tfl', '4-hour')}) at {TP.fmt(px, r['tick'])}: {why} · {res:+.2f}R · "
                            f"{'+' if rs >= 0 else '−'}₹{abs(rs):,.0f} per lot before costs")
                BO.close_ledger(state, r["key"], float(px), why.replace("🎯 ", ""), now)
            r.update(exit=float(px), exit_reason=why, closed=str(now), result_R=round(res, 3))
            st["closed"] = (st["closed"] + [r])[-200:]
        else:
            keep.append(r)
    st["open"] = keep
