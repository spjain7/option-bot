"""
🟢 OPTION-BUY ALERTS (TEST PHASE) – Engine E. Alerts only, never places orders. Independent of the selling bot.

Only the two setups that did best in the real-option-price backtest (research/search/obuy_month.py, Sep-Oct 2026):
  INTRADAY  (stock options only; indices lost money in the test)
     15-min futures candle crosses VWAP, RSI(14) >= 60 (BUY CE) / <= 40 (BUY PE), OI up over the last hour and price
     moving the same way over the last hour. Entries 9:30-14:30. SL -30%, target +60%, exit by 15:15.
  POSITIONAL (stocks + indices)
     Yesterday closed beyond the 20-day high/low with volume > 1.5x the 20-day average and OI up -> BUY CE/PE at the
     open. SL -35%, target +80%, exit by 15:15 on the 3rd session.
Option: ATM strike of the nearest monthly expiry with >= 3 days left. Skipped if the option has not traded today or
its bid-ask spread is over 3%. Every alert is tracked (SL / target / time) with real option prices, and a daily scorecard
is sent, so the setups prove themselves (or not) with real results.
"""
import numpy as np
import pandas as pd
from research.search import obuy_month as RM          # the SAME feature code the backtest used
from obuy import improve as IM                       # only the NSE F&O-ban check is used (29-Oct rules reverted by owner)

INDICES = {"NIFTY": "99926000", "BANKNIFTY": "99926009", "FINNIFTY": "99926037", "MIDCPNIFTY": "99926074"}
TOP_STOCKS = 40
RULES = {"intraday": {"sl": 0.30, "tg": 0.60, "days": 0}, "positional": {"sl": 0.35, "tg": 0.80, "days": 2}}
MAX_PER_DAY = {"intraday": 8, "positional": 4}
MAX_SPREAD = 0.03
POSITIONAL_ENABLED = False   # 27-Oct: daily breakout option buys now come with every futures call (alerts/) – no duplicates
BACKTEST = {"intraday": "last month +1.6% per trade, 45% wins (138 trades)",
            "positional": "last month +3% per trade, 42% wins (19 trades); 4-year model test positive"}


def new_state():
    return {"open": [], "closed": [], "done": {}, "next_id": 1, "universe": {}}


def hm(t):
    return t.strftime("%H:%M")


# ─────────────── pure signal checks (same conditions as the backtest) ───────────────
def intraday_signal(df, i):
    """df = RM.features(...) output; i = last COMPLETED bar. Returns +1 / -1 / 0."""
    if i < 60 or i >= len(df):
        return 0
    r, p = df.iloc[i], df.iloc[i - 1]
    if not ("09:30" <= hm(r["time"]) <= "14:30") or p["day"] != r["day"]:
        return 0
    if not (np.isfinite(r["vwap"]) and np.isfinite(p["vwap"]) and np.isfinite(r["oi_1h"]) and np.isfinite(r["px_1h"])):
        return 0
    if p["close"] <= p["vwap"] < r["close"] and r["rsi"] >= 60 and r["oi_1h"] > 0 and r["px_1h"] > 0:
        return 1
    if p["close"] >= p["vwap"] > r["close"] and r["rsi"] <= 40 and r["oi_1h"] > 0 and r["px_1h"] < 0:
        return -1
    return 0


def positional_signal(d):
    """d = daily bars up to and including YESTERDAY (columns as RM.daily). Returns +1 / -1 / 0."""
    if len(d) < 22:
        return 0
    r = d.iloc[-1]
    if not (np.isfinite(r["hh20"]) and np.isfinite(r["vol20"]) and np.isfinite(r["oichg"])):
        return 0
    if r["volume"] > 1.5 * r["vol20"] and r["oichg"] > 0:
        if r["close"] > r["hh20"]:
            return 1
        if r["close"] < r["ll20"]:
            return -1
    return 0


def last_completed(df, now):
    done = df[df["time"] + pd.Timedelta(minutes=15) <= now]
    return done.index[-1] if len(done) else None


# ─────────────── data ───────────────
def universe(api, master, now, state):
    day = f"{now:%Y-%m-%d}"
    if state["universe"].get("day") == day:
        return state["universe"]["items"]
    fut = master[master["instrumenttype"].isin(["FUTIDX", "FUTSTK"]) & (master["exch_seg"] == "NFO") & (master["expiry_dt"] >= now.normalize())]
    near = fut.sort_values("expiry_dt").groupby("name").head(1)
    stk = near[near["instrumenttype"] == "FUTSTK"]
    q = api.quotes({"NFO": list(stk["token"].astype(str))})
    act = sorted(((float(v.get("opnInterest") or 0) * float(v.get("ltp") or 0), k) for k, v in q.items()), reverse=True)[:TOP_STOCKS]
    top = {k for _, k in act}
    items = [{"name": r.name, "token": str(r.token), "lot": int(r.lotsize), "kind": "index" if r.name in INDICES else "stock"}
             for r in near.itertuples() if r.name in INDICES or str(r.token) in top]
    state["universe"] = {"day": day, "items": items}
    return items


def fut_frame(api, tok, frm, now):
    c = api.candles("NFO", tok, "FIFTEEN_MINUTE", frm, now)
    if c is None or c.empty:
        return None
    oi = api.oi_history("NFO", tok, "FIFTEEN_MINUTE", frm, now)
    c = c.merge(oi[["time", "oi"]], on="time", how="left") if oi is not None else c.assign(oi=np.nan)
    c = c[(c["time"].dt.strftime("%H:%M") >= "09:15") & (c["time"].dt.strftime("%H:%M") < "15:30")].reset_index(drop=True)
    return RM.features(c)


def daily_frame(api, tok, now):
    c = api.candles("NFO", tok, "ONE_DAY", now - pd.Timedelta(days=60), now)
    oi = api.oi_history("NFO", tok, "ONE_DAY", now - pd.Timedelta(days=60), now)
    if c is None or c.empty or oi is None:
        return None
    c["day"] = c["time"].dt.normalize()
    oi["day"] = oi["time"].dt.normalize()
    c = c.merge(oi[["day", "oi"]], on="day", how="left")
    c = c[c["day"] < now.normalize()]                                   # completed days only
    d = c[["day", "open", "high", "low", "close", "volume", "oi"]].reset_index(drop=True)
    d["hh20"], d["vol20"] = d["high"].rolling(20).max().shift(1), d["volume"].rolling(20).mean().shift(1)
    d["ll20"] = d["low"].rolling(20).min().shift(1)
    d["chg"], d["oichg"] = d["close"].pct_change(), d["oi"].pct_change()
    return d


def pick_option(master, name, px, typ, now, min_expiry=None):
    """ATM option of the nearest expiry on/after min_expiry (default: 3 days ahead)."""
    lo = min_expiry if min_expiry is not None else now.normalize() + pd.Timedelta(days=3)
    o = master[(master["name"] == name) & (master["exch_seg"] == "NFO") & master["instrumenttype"].isin(["OPTIDX", "OPTSTK"])
               & master["symbol"].str.endswith(typ) & (master["expiry_dt"] >= lo)]
    if o.empty:
        return None
    o = o[o["expiry_dt"] == o["expiry_dt"].min()].copy()
    o["K"] = o["strike"] / 100
    r = o.iloc[(o["K"] - px).abs().argsort().iloc[0]]
    return {"token": str(r["token"]), "symbol": r["symbol"], "K": float(r["K"]), "expiry": str(r["expiry_dt"].date()), "lot": int(r["lotsize"])}


def option_quote(q):
    """-> (ltp, bid, ask, traded_today) from an Angel FULL quote."""
    ltp = float(q.get("ltp") or 0)
    dep = q.get("depth") or {}
    bid = float((dep.get("buy") or [{}])[0].get("price") or 0)
    ask = float((dep.get("sell") or [{}])[0].get("price") or 0)
    return ltp, bid, ask, float(q.get("tradeVolume") or 0) > 0


def liquid(ltp, bid, ask, traded):
    if not traded or ltp <= 0:
        return False, "option not traded today"
    if bid > 0 and ask > 0 and (ask - bid) / ((ask + bid) / 2) > MAX_SPREAD:
        return False, f"bid-ask spread {(ask - bid) / ((ask + bid) / 2) * 100:.1f}% > 3%"
    return True, ""


# ─────────────── messages ───────────────
def rs_(x):
    return f"₹{x:,.2f}" if x < 100 else f"₹{x:,.1f}"


def entry_msg(a):
    """Two messages: the call, then WHY (same layout as every other call)."""
    up = a["dir"] > 0
    typ = "CE" if up else "PE"
    why = a["why"] if isinstance(a["why"], list) else [a["why"]]
    call = "\n".join([
        f"{'🟢' if up else '🔴'} BUY  {a['name']} {a['K']:g} {typ}  ·  {'Intraday' if a['mode'] == 'intraday' else 'Positional'}",
        "━━━━━━━━━━━━━━",
        f"Entry   : {rs_(a['entry'])}",
        f"SL      : {rs_(a['sl'])}",
        f"Target  : {rs_(a['tg'])}",
        f"Lot     : {a['lot']:,}  ·  exp {pd.Timestamp(a['expiry']):%d-%b}  ·  NSE",
        f"Exit by : {pd.Timestamp(a['exit_at']):%d %b} 15:15"])
    w = "\n".join([f"📌 WHY – {a['name']} {a['K']:g} {typ} BUY", "━━━━━━━━━━━━━━",
                    f"• Chart   : {'15-minute' if a['mode'] == 'intraday' else 'Daily'} futures candles",
                    *[f"• {x}" for x in why],
                    f"• Risk    : SL −{a['sl_pct']:.0f}% · target +{a['tg_pct']:.0f}% of premium",
                    "Not investment advice."])
    return [call, w]


def exit_msg(a):
    up = a["dir"] > 0
    head = {"target hit": "✅ TARGET HIT", "stop-loss hit": "❌ STOP-LOSS HIT", "time exit": "⏰ TIME EXIT"}[a["why_exit"]]
    if a["why_exit"] == "time exit":
        head = ("✅ " if a["ret"] > 0 else "❌ ") + "TIME EXIT"
    return "\n".join([f"{head} • {a['name']} {a['K']:g} {'CE' if up else 'PE'} (#{a['id']})",
                      f"{rs_(a['entry'])} → {rs_(a['exit'])}",
                      f"Result: {a['ret'] * 100:+.1f}% • {'+' if a['rs_lot'] >= 0 else '−'}₹{abs(a['rs_lot']):,.0f} per lot (after costs)"])


def scorecard(state, now):
    today = [a for a in state["closed"] if a["closed"][:10] == f"{now:%Y-%m-%d}"]
    allc = state["closed"]
    def line(xs):
        if not xs:
            return "no closed alerts"
        w = sum(a["ret"] > 0 for a in xs)
        return (f"{len(xs)} trades • {w} wins ({w / len(xs) * 100:.0f}%) • avg {np.mean([a['ret'] for a in xs]) * 100:+.1f}% • "
                f"{'+' if sum(a['rs_lot'] for a in xs) >= 0 else '−'}₹{abs(sum(a['rs_lot'] for a in xs)):,.0f}/lot")
    L = [f"📊 OPTION BUY SCORECARD • {now:%d %b}", "", f"Today: {line(today)}", f"Since start: {line(allc)}"]
    for m in ("intraday", "positional"):
        xs = [a for a in allc if a["mode"] == m]
        if xs:
            L.append(f"• {m.capitalize()}: {line(xs)}")
    L += [f"Open now: {len(state['open'])}", "", "🧪 After 30+ trades per setup, keep only a setup that is positive."]
    return "\n".join(L)


# ─────────────── one scan ───────────────
def cost_ret(entry, exitp, lot, kind):
    hs = RM.HALF_SPREAD[kind]
    buy, sell = entry, exitp * (1 - hs)                                  # entry already at the ask
    rs = (sell - buy - RM.FEES * sell) * lot - RM.BROKER_LOT
    return rs / (buy * lot), rs


def manage(api, state, now, msgs):
    if not state["open"]:
        return
    q = api.quotes({"NFO": [a["token"] for a in state["open"]]})
    keep = []
    for a in state["open"]:
        ltp = float((q.get(a["token"]) or {}).get("ltp") or 0)
        if ltp > 0:                                      # premium high / low after the call (daily report)
            a["hi"], a["lo"], a["last"] = max(a.get("hi", a["entry"]), ltp), min(a.get("lo", a["entry"]), ltp), ltp
        why = px = None
        if ltp > 0 and ltp <= a["sl"]:
            why, px = "stop-loss hit", a["sl"]
        elif ltp >= a["tg"]:
            why, px = "target hit", a["tg"]
        elif now >= pd.Timestamp(a["exit_at"]) and ltp > 0:
            why, px = "time exit", ltp
        if why:
            r, rs = cost_ret(a["entry"], px, a["lot"], a["kind"])
            a.update({"exit": round(px, 2), "ret": r, "rs_lot": round(rs), "why_exit": why, "closed": str(now)})
            state["closed"].append(a); msgs.append(exit_msg(a))
        else:
            keep.append(a)
    state["open"] = keep


def exit_time(now, mode):
    if mode == "intraday":
        return now.normalize() + pd.Timedelta(hours=15, minutes=15)
    d, n = now.normalize(), 0
    while n < RULES[mode]["days"]:
        d += pd.Timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return d + pd.Timedelta(hours=15, minutes=15)


def open_alert(api, master, state, now, u, mode, d, fut_px, why, msgs, rep):
    day = f"{now:%Y-%m-%d}"
    key = f"{mode}|{u['name']}|{day}"
    taken = sum(1 for k, v in state["done"].items() if k.startswith(mode + "|") and k.endswith(day) and v != "skipped")
    if state["done"].get(key) or taken >= MAX_PER_DAY[mode]:
        return
    typ = "CE" if d > 0 else "PE"
    # positional: the option must expire at least 2 days AFTER the planned exit (no holding into expiry-day decay)
    lo = exit_time(now, mode).normalize() + pd.Timedelta(days=2) if mode == "positional" else None
    o = pick_option(master, u["name"], fut_px, typ, now, lo)
    if not o:
        rep.append(f"{u['name']}: no option found"); return
    q = api.quotes({"NFO": [o["token"]]}).get(o["token"]) or {}
    ltp, bid, ask, traded = option_quote(q)
    ok, why_not = liquid(ltp, bid, ask, traded)
    if not ok:
        rep.append(f"{u['name']} {mode} signal skipped: {why_not}"); state["done"][key] = "skipped"; return
    entry = ask if ask > 0 else ltp
    try:                                                # same "expensive premium" guard as the futures-call option buys
        from alerts.optfilter import hv20, IV_HV_MAX
        from greeks import implied_vol
        dly = api.candles("NFO", u["token"], "ONE_DAY", now - pd.Timedelta(days=45), now)
        hv = hv20(dly[dly["time"].dt.normalize() < now.normalize()]) if dly is not None and len(dly) else None
        T = max((pd.Timestamp(o["expiry"]) - now.normalize()).days, 0.5) / 365
        iv = implied_vol(ltp, fut_px, o["K"], T, 0.065, typ)
        if iv and hv:
            if iv > IV_HV_MAX * hv:
                rep.append(f"{u['name']} {mode} signal skipped: premium expensive (IV {iv * 100:.0f}% vs {hv * 100:.0f}%)")
                state["done"][key] = "skipped"; return
            why = list(why) + [f"Premium fair: IV {iv * 100:.0f}% vs 20-day move {hv * 100:.0f}%"]
    except Exception:
        pass
    R = RULES[mode]
    a = {"id": state["next_id"], "mode": mode, "name": u["name"], "kind": u["kind"], "dir": d, **o, "entry": round(entry, 2),
         "sl": round(entry * (1 - R["sl"]), 2), "tg": round(entry * (1 + R["tg"]), 2), "sl_pct": R["sl"] * 100, "tg_pct": R["tg"] * 100,
         "opened": str(now), "exit_at": str(exit_time(now, mode)), "why": why}
    a["exit_by"] = f"{pd.Timestamp(a['exit_at']):%d %b %H:%M}"
    state["next_id"] += 1
    state["open"].append(a); state["done"][key] = str(now)
    msgs.extend(entry_msg(a))


def scan(api, master, now, state):
    msgs, rep = [], []
    if now.weekday() >= 5 or not (pd.Timestamp(now.date()) + pd.Timedelta(hours=9, minutes=15) <= now <= pd.Timestamp(now.date()) + pd.Timedelta(hours=16)):
        return state, msgs, rep
    manage(api, state, now, msgs)
    t = hm(now)
    if "09:30" <= t <= "14:47":
        items = universe(api, master, now, state)
        ban = IM.ban_list(state, now)                     # exchange rule: no new positions in F&O-ban stocks
        if ban is None:
            rep.append("F&O ban list not available – ban check skipped this run")
        elif ban:
            items = [u for u in items if u["name"] not in ban]
        if POSITIONAL_ENABLED and not state["done"].get(f"positional-scan|{now:%Y-%m-%d}"):
            state["done"][f"positional-scan|{now:%Y-%m-%d}"] = str(now)
            for u in items:
                try:
                    dd = daily_frame(api, u["token"], now)
                    s = positional_signal(dd) if dd is not None else 0
                    if s:
                        r = dd.iloc[-1]
                        fq = api.quotes({"NFO": [u["token"]]}).get(u["token"]) or {}
                        px = float(fq.get("ltp") or r["close"])
                        open_alert(api, master, state, now, u, "positional", s, px,
                                   [f"Closed {'above the 20-day high' if s > 0 else 'below the 20-day low'} yesterday",
                                    f"Volume {r['volume'] / r['vol20']:.1f}× normal",
                                    f"OI {r['oichg'] * 100:+.1f}% ({'long' if s > 0 else 'short'} build-up)"], msgs, rep)
                except Exception as e:
                    rep.append(f"{u['name']} positional error {type(e).__name__}")
        for u in items:
            if u["kind"] != "stock":
                continue
            try:
                df = fut_frame(api, u["token"], now - pd.Timedelta(days=7), now)
                try:                                     # 29-Oct (owner): 15-min liquidity sweep – SELL + volume + OI falling sent, rest logged
                    from alerts import candle_setups as CS
                    CS.sweep15_log(state, u["name"], u.get("symbol"), df, now, msgs, u.get("lot"))
                except Exception as e_:
                    rep.append(f"{u['name']} sweep15 log error {type(e_).__name__}")
                try:                                     # 29-Oct (owner): 1H BIG MOVE watch – information only, not a call
                    from alerts import watch1h as W1
                    W1.check(state, msgs, u["name"], "STOCK FUT", W1.hourly_from_15m(df, now), now)
                except Exception as e_:
                    rep.append(f"{u['name']} watch1h error {type(e_).__name__}")
                i = last_completed(df, now) if df is not None else None
                s = intraday_signal(df, i) if i is not None else 0
                if s:
                    r = df.iloc[i]
                    try:                                  # 30-Oct: nearest resistance (CE) / support (PE) on the futures
                        from alerts import signals as S_
                        from crude import indicators as I_
                        a15 = float(I_.atr(df.iloc[:i + 1], 14).iloc[-1])
                        lv_ = S_.levels(df.iloc[:i + 1], df.iloc[:i + 1], float(r["close"]), a15)
                        opp = (lv_["resistance"] if s > 0 else lv_["support"])[:1]
                        srl = (f"{'Resistance' if s > 0 else 'Support'} {opp[0][0]:,.1f} ({opp[0][1]}), "
                               f"{abs(opp[0][0] - float(r['close'])) / float(r['close']) * 100:.2f}% away") if opp else \
                              f"No {'resistance' if s > 0 else 'support'} level near"
                    except Exception:
                        srl = None
                    open_alert(api, master, state, now, u, "intraday", s, float(r["close"]),
                               ([srl] if srl else []) +
                               [f"Futures crossed {'above' if s > 0 else 'below'} VWAP ({r['vwap']:,.1f})",
                                f"RSI {r['rsi']:.0f} ({'strong' if s > 0 else 'weak'} momentum)",
                                f"Last 1 hour: price {r['px_1h'] * 100:+.2f}%, OI {r['oi_1h'] * 100:+.1f}%"], msgs, rep)
            except Exception as e:
                rep.append(f"{u['name']} intraday error {type(e).__name__}")
    open15 = {r["name"] for r in (state.get("sweep15") or {}).get("open", [])}
    if open15 and "14:47" < t <= "15:50":                 # follow open 15-min sweep calls to the close
        try:
            from alerts import candle_setups as CS
            for u in universe(api, master, now, state):
                if u["kind"] == "stock" and u["name"] in open15:
                    CS.sweep15_log(state, u["name"], u.get("symbol"), fut_frame(api, u["token"], now - pd.Timedelta(days=7), now),
                                   now, msgs, u.get("lot"))
        except Exception as e_:
            rep.append(f"sweep15 close tracking error {type(e_).__name__}")
    if t >= "15:30" and not state["done"].get(f"watch1h|{now:%Y-%m-%d}"):
        state["done"][f"watch1h|{now:%Y-%m-%d}"] = str(now)
        try:
            from alerts import watch1h as W1
            sm = W1.summary_msg(state, f"{now:%Y-%m-%d}", ["STOCK FUT"])
            if sm:
                msgs.append(sm)
        except Exception as e_:
            rep.append(f"watch1h summary error {type(e_).__name__}")
    if t >= "15:30" and not state["done"].get(f"scorecard|{now:%Y-%m-%d}"):
        state["done"][f"scorecard|{now:%Y-%m-%d}"] = str(now)
        if state["closed"] or state["open"]:
            msgs.append(scorecard(state, now))
    cutoff = f"{now - pd.Timedelta(days=10):%Y-%m-%d}"
    state["done"] = {k: v for k, v in state["done"].items() if k[-10:] >= cutoff}
    return state, msgs, rep
