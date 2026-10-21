"""
ENGINE C - MCX BUY / SELL ALERTS  (commodity futures + option buying)

Alerts only - no orders are ever placed. Separate from the option-selling engine (A) and RSI alerts (B):
own rules, own state file (state/mcx_trades.json), shares only market data + Telegram.

Signal (on a COMPLETED 1-hour candle of the main near-month future):
  BUY  = price > EMA20 > EMA50, price above EMA200 (higher-timeframe uptrend), ADX >= 20,
         close breaks the previous 5-hour high, RSI 55-75, volume >= 1.2x average
  SELL = the mirror image.
Trade plan: entry at live price, SL beyond the 5-hour swing (1-2 ATR), T1 = 1R, T2 = 2R,
SL to cost after T1, square-off at 23:00. Option idea: buy ~ATM CE (BUY) / PE (SELL), managed on the
future's levels plus a premium stop.
"""
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import config as C
import market as M
import notify
from angel import now_ist

STATE_FILE = Path(__file__).parent / "state" / "mcx_trades.json"
SESSION_CLOSE = "23:55"


def at(s):
    h, m = map(int, s.split(":"))
    return now_ist().normalize() + pd.Timedelta(hours=h, minutes=m)


def rs(x):
    return f"₹{x:,.0f}" if x >= 0 else f"-₹{abs(x):,.0f}"


def px(x):
    return f"{x:,.2f}" if x < 100 else f"{x:,.1f}" if x < 1000 else f"{x:,.0f}"


# ─────────────── indicators ───────────────
def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, 1e-9))


def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def signal(df):
    """df = completed 1-hour candles. Returns dict(side, ...) or None plus a short reason."""
    need = C.MCXT_EMA_TREND + 5
    if df is None or len(df) < need:
        return None, "not enough candles"
    c = df["close"]
    e20, e50, e200 = (M.ema(c, n).iloc[-1] for n in (C.MCXT_EMA_FAST, C.MCXT_EMA_SLOW, C.MCXT_EMA_TREND))
    last = float(c.iloc[-1])
    a = M.adx(df)
    r = float(rsi(c).iloc[-1])
    at_ = float(atr(df).iloc[-1])
    prev = df.iloc[-1 - C.MCXT_BREAKOUT_BARS:-1]
    hh, ll = float(prev["high"].max()), float(prev["low"].min())
    vol = df["volume"].astype(float)
    avg = float(vol.iloc[-21:-1].mean())
    vx = float(vol.iloc[-1]) / avg if avg > 0 else None           # volume ratio (None if feed has no volume)
    rng = float(df["high"].iloc[-1] - df["low"].iloc[-1])
    info = dict(close=last, e20=float(e20), e50=float(e50), e200=float(e200), adx=round(a, 1), rsi=round(r, 1),
                atr=at_, hh=hh, ll=ll, vol_x=round(vx, 2) if vx else None,
                swing_low=float(df["low"].iloc[-C.MCXT_BREAKOUT_BARS:].min()),
                swing_high=float(df["high"].iloc[-C.MCXT_BREAKOUT_BARS:].max()))
    if a < C.MCXT_MIN_ADX:
        return None, f"ADX {a:.0f} < {C.MCXT_MIN_ADX} (no trend)"
    if rng > 2.5 * at_:
        return None, "signal candle too big (spike)"
    if vx is not None and vx < C.MCXT_MIN_VOL_X:
        return None, f"volume only {vx:.1f}x"
    if last > e20 > e50 and last > e200 and last > hh and C.MCXT_RSI_BUY[0] <= r <= C.MCXT_RSI_BUY[1]:
        return {**info, "side": "BUY"}, "ok"
    if last < e20 < e50 and last < e200 and last < ll and C.MCXT_RSI_SELL[0] <= r <= C.MCXT_RSI_SELL[1]:
        return {**info, "side": "SELL"}, "ok"
    return None, "no breakout in trend direction"


def plan(sig, entry):
    """Entry / SL / targets from live price. SL just beyond the 5-hour swing, kept within 1-2 ATR."""
    a, s = sig["atr"], 1 if sig["side"] == "BUY" else -1
    lo, hi = C.MCXT_SL_ATR
    swing = sig["swing_low"] - 0.2 * a if s > 0 else sig["swing_high"] + 0.2 * a
    dist = min(max(abs(entry - swing), lo * a), hi * a)
    return {"entry": entry, "sl": entry - s * dist, "t1": entry + s * C.MCXT_T1_R * dist,
            "t2": entry + s * C.MCXT_T2_R * dist, "risk_pts": dist}


def lots_for(risk_rs_per_lot, margin_per_lot):
    if risk_rs_per_lot <= 0:
        return 0
    n = int(C.CAPITAL_RS * C.MCXT_RISK_PCT // risk_rs_per_lot)
    if margin_per_lot > 0:
        n = min(n, int(C.CAPITAL_RS * C.MAX_CAPITAL_USE // margin_per_lot))
    return max(n, 0)


# ─────────────── engine ───────────────
class MCXTrader:
    def __init__(self, api, master):
        self.api, self.master = api, master
        self.s = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        for k, v in {"next_id": 1, "open": [], "closed": [], "done": {}, "summary": {}}.items():
            self.s.setdefault(k, v)

    def save(self):
        cutoff = f"{now_ist() - pd.Timedelta(days=5):%Y-%m-%d}"
        self.s["done"] = {k: v for k, v in self.s["done"].items() if v >= cutoff}
        self.s["closed"] = self.s["closed"][-500:]
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps(self.s, indent=1, default=str))

    def future(self, name):
        today = now_ist().normalize()   # same contract as RSI engine (expiry >= 3 days away) -> shared candles
        return M.near_future(self.master, name, "MCX", on_or_after=today + pd.Timedelta(days=3))

    def candles(self, fut):
        now = now_ist()
        df = self.api.candles("MCX", fut["token"], "ONE_HOUR", now - pd.Timedelta(days=90), now)
        if df is None or df.empty:
            return None
        ch, cm = map(int, SESSION_CLOSE.split(":"))
        end = df["time"].map(lambda t: min(t + pd.Timedelta(hours=1), t.normalize() + pd.Timedelta(hours=ch, minutes=cm)))
        df = df[end <= now].reset_index(drop=True)                     # completed candles only
        if df.empty or df["time"].iloc[-1].normalize() != now.normalize():
            return None                                                # holiday / no candle today yet
        return df

    # ---------- scan for new calls ----------
    def scan(self, force=False):
        now = now_ist()
        if not force and not (at(C.MCXT_FIRST_SCAN) <= now <= at(C.MCXT_LAST_ENTRY)):
            return []
        today = f"{now:%Y-%m-%d}"
        made = []
        for name, mini in C.MCXT_UNDERLYINGS.items():
            if len(self.s["open"]) >= C.MCXT_MAX_OPEN:
                break
            if any(p["name"] == name for p in self.s["open"]):
                continue
            if sum(1 for p in self.s["closed"] + self.s["open"]
                   if p["name"] == name and p["opened"][:10] == today) >= C.MCXT_MAX_PER_NAME_DAY:
                continue
            fut = self.future(name)
            if fut is None:
                continue
            df = self.candles(fut)
            if df is None:
                continue
            key = f"{name}|{df['time'].iloc[-1]:%Y-%m-%d %H:%M}"
            if key in self.s["done"]:
                continue
            self.s["done"][key] = today
            sig, why = signal(df)
            print(f"MCX buy/sell {name}: {sig['side'] if sig else why}")
            if not sig:
                continue
            q = self.api.quotes({"MCX": [fut["token"]]}).get(str(fut["token"]), {})
            ltp = float(q.get("ltp") or sig["close"])
            s = 1 if sig["side"] == "BUY" else -1
            if s * (ltp - sig["close"]) > C.MCXT_MAX_CHASE_ATR * sig["atr"]:
                print(f"  skipped {name}: price already ran away ({ltp} vs {sig['close']})")
                continue
            pos = self.open_call(name, mini, fut, sig, ltp, df)
            made.append(pos)
        return made

    def option_idea(self, name, side, fut_price, p):
        if not C.MCXT_OPTIONS:
            return None
        exps = [e for e in M.expiries(self.master, name, "MCX") if M.dte(e) >= C.MCXT_OPT_MIN_DTE]
        if not exps:
            return None
        ch = M.build_chain(self.api, self.master, name, exps[0], fut_price, width_pct=0.04, exch="MCX")
        if not ch:
            return None
        typ = "CE" if side == "BUY" else "PE"
        d = ch["df"]
        d = d[(d.typ == typ) & d["delta"].notna() & (d["oi"] >= C.MCXT_OPT_MIN_OI)
              & (d["ba_pct"] <= C.MCXT_OPT_MAX_BA_PCT) & (d["ask"] > 0)]
        if d.empty:
            return {"note": "options illiquid now – use the future"}
        o = d.iloc[(d["delta"].abs() - 0.55).abs().argsort().iloc[0]]        # ATM / slightly ITM
        prem, delta, gamma = float(o["ask"]), abs(float(o["delta"])), float(o["gamma"] or 0)
        mv = lambda pts: delta * pts + 0.5 * gamma * pts * pts                 # premium change for a fut move
        sl = max(prem - mv(p["risk_pts"]), prem * (1 - C.MCXT_OPT_SL_PCT / 100))
        t1 = prem + mv(p["risk_pts"] * C.MCXT_T1_R)
        t2 = prem + mv(p["risk_pts"] * C.MCXT_T2_R)
        rpp = C.MCX_RS_PER_POINT.get(name, 1)
        return {"symbol": o["symbol"], "token": str(o["token"]), "K": float(o["K"]), "typ": typ,
                "expiry": f"{pd.Timestamp(ch['expiry']):%Y-%m-%d}", "entry": prem, "delta": round(delta, 2),
                "iv": round(float(o["iv"]), 1) if o["iv"] else None, "sl": round(sl, 2), "t1": round(t1, 2),
                "t2": round(t2, 2), "risk_lot": (prem - sl) * rpp, "cost_lot": prem * rpp,
                "lots": lots_for((prem - sl) * rpp, 0)}

    def open_call(self, name, mini, fut, sig, ltp, df):
        p = plan(sig, ltp)
        rpp = C.MCX_RS_PER_POINT.get(name, 1)
        margin = ltp * rpp * C.MARGIN_PCT["mcx"]
        lots = lots_for(p["risk_pts"] * rpp, margin)
        mini_lots = 0
        if mini:
            mr = C.MCX_RS_PER_POINT.get(mini, 0)
            mini_lots = lots_for(p["risk_pts"] * mr, ltp * mr * C.MARGIN_PCT["mcx"]) if mr else 0
        opt = None
        try:
            opt = self.option_idea(name, sig["side"], ltp, p)
        except Exception as e:
            print("option idea error:", e)
        pos = {"id": self.s["next_id"], "name": name, "mini": mini, "side": sig["side"], "symbol": fut["symbol"],
               "token": str(fut["token"]), "rpp": rpp, **{k: round(v, 2) for k, v in p.items()},
               "sl0": round(p["sl"], 2), "lots": lots, "mini_lots": mini_lots, "t1_hit": False,
               "opened": f"{now_ist():%Y-%m-%d %H:%M}", "candle": f"{df['time'].iloc[-1]:%H:%M}",
               "opt": opt if opt and "token" in opt else None,
               "sig": {k: sig[k] for k in ("adx", "rsi", "vol_x")}}
        self.s["next_id"] += 1
        self.s["open"].append(pos)
        notify.send(self.fmt_entry(pos, sig, opt))
        return pos

    def fmt_entry(self, p, sig, opt):
        buy = p["side"] == "BUY"
        L = [f"{'🟢' if buy else '🔴'} *MCX {p['side']} – {p['name']}*  (1H, #{p['id']})",
             f"{p['symbol']}", "",
             f"Entry: *{px(p['entry'])}*  (CMP)",
             f"SL: *{px(p['sl'])}*   T1: {px(p['t1'])}   T2: {px(p['t2'])}",
             f"Risk {px(p['risk_pts'])} pts = {rs(p['risk_pts'] * p['rpp'])}/lot | R:R 1:{C.MCXT_T2_R:g}",
             f"Lots: *{p['lots']}*" + (" (1 lot risks more than your limit)" if not p["lots"] else "")
             + (f"  |  Mini {p['mini']}: *{p['mini_lots']}*" if p["mini"] else "")
             + f"  (risk ≤ {C.MCXT_RISK_PCT * 100:g}% of capital)"]
        trend = "uptrend" if buy else "downtrend"
        brk = f"broke 5-hr {'high ' + px(sig['hh']) if buy else 'low ' + px(sig['ll'])}"
        why = f"{trend} (EMA20/50, {'above' if buy else 'below'} EMA200), ADX {sig['adx']:.0f}, {brk}, RSI {sig['rsi']:.0f}"
        if sig.get("vol_x"):
            why += f", volume {sig['vol_x']:.1f}x"
        L += ["", "Why: " + why]
        if opt and "token" in opt:
            L += ["", f"📈 *Option buy:* {opt['symbol']} @ {px(opt['entry'])}  (Δ {opt['delta']}"
                      + (f", IV {opt['iv']}%" if opt["iv"] else "") + ")",
                  f"SL ~{px(opt['sl'])} | T1 ~{px(opt['t1'])} | T2 ~{px(opt['t2'])}",
                  f"Cost {rs(opt['cost_lot'])}/lot | Risk {rs(opt['risk_lot'])}/lot | Lots: {opt['lots'] or '0 (over risk limit)'}",
                  "_Option exits follow the future's SL/targets (premium levels are estimates)._"]
        elif opt:
            L += ["", f"📈 Option: {opt['note']}"]
        L += ["", f"After T1: book half, move SL to cost. Exit all by {C.MCXT_EXIT_TIME}.",
              "_Alert only, not advice. Check margin with your broker before trading._"]
        return "\n".join(L)

    # ---------- manage open calls ----------
    def monitor(self):
        if not self.s["open"]:
            return
        toks = {p["token"] for p in self.s["open"]} | {p["opt"]["token"] for p in self.s["open"] if p.get("opt") and p["opt"].get("token")}
        q = self.api.quotes({"MCX": sorted(toks)})
        ltp = lambda t: float((q.get(str(t)) or {}).get("ltp") or 0)
        now = now_ist()
        for p in list(self.s["open"]):
            f = ltp(p["token"])
            if not f:
                continue
            s = 1 if p["side"] == "BUY" else -1
            o = ltp(p["opt"]["token"]) if p.get("opt") and p["opt"].get("token") else 0
            if not p["t1_hit"] and s * (f - p["t1"]) >= 0:
                p["t1_hit"], p["t1_px"], p["sl"] = True, f, p["entry"]
                if o:
                    p["opt_t1_px"] = o
                notify.send(f"✅ *T1 hit – {p['name']} {p['side']}* (#{p['id']})\nFuture {px(f)} "
                            f"(+{rs(s * (f - p['entry']) * p['rpp'])}/lot)" + (f" | Option {px(o)}" if o else "")
                            + "\nBook half. SL moved to cost " + px(p["entry"]) + ".")
                continue
            reason = None
            if s * (f - p["t2"]) >= 0:
                reason = "🎯 T2 hit"
            elif s * (f - p["sl"]) <= 0:
                reason = "🟰 Exit at cost (after T1)" if p["t1_hit"] else "🛑 SL hit"
            elif now >= at(C.MCXT_EXIT_TIME):
                reason = "⏰ Time exit"
            elif o and p.get("opt") and o <= p["opt"]["entry"] * (1 - C.MCXT_OPT_SL_PCT / 100):
                p["opt_closed"] = o                                        # option stop only; future continues
                notify.send(f"🛑 *Option stop – {p['opt']['symbol']}* (#{p['id']}) premium {px(o)} "
                            f"(-{C.MCXT_OPT_SL_PCT}%). Exit the option; future trade continues.")
                p["opt"] = {**p["opt"], "exit": o}
                p["opt"]["token_closed"] = p["opt"].pop("token")
                continue
            if reason:
                self.close(p, f, o, reason)

    def close(self, p, f, o, reason):
        s = 1 if p["side"] == "BUY" else -1
        half = 0.5 if p["t1_hit"] else 1.0      # with T1 booked: half at T1, half now
        pts = (1 - half) * (p.get("t1_px", f) - p["entry"]) * s + half * (f - p["entry"]) * s
        pnl = pts * p["rpp"] - 2 * C.COST_PER_ORDER_RS
        p.update(exit=f, exit_reason=reason, closed=f"{now_ist():%Y-%m-%d %H:%M}", pnl_rs_per_lot=round(pnl))
        L = [f"{reason} – *{p['name']} {p['side']}* (#{p['id']})",
             f"Future exit {px(f)} (entry {px(p['entry'])}) → *{rs(pnl)}/lot*"]
        if p.get("opt") and (o or p["opt"].get("exit")):
            ox = p["opt"].get("exit") or o
            ot1 = p.get("opt_t1_px", ox)
            opnl = ((1 - half) * (ot1 - p["opt"]["entry"]) + half * (ox - p["opt"]["entry"])) * p["rpp"] \
                - 2 * C.COST_PER_ORDER_RS
            p["opt_pnl_rs_per_lot"] = round(opnl)
            L.append(f"Option {p['opt']['symbol']} exit {px(ox)} (entry {px(p['opt']['entry'])}) → {rs(opnl)}/lot")
        day = [c for c in self.s["closed"] if c["closed"][:10] == p["closed"][:10]] + [p]
        L.append(f"Today MCX: {rs(sum(c['pnl_rs_per_lot'] for c in day))}/lot on {len(day)} trades")
        notify.send("\n".join(L))
        self.s["open"].remove(p)
        self.s["closed"].append(p)

    # ---------- end-of-day summary ----------
    def summary(self):
        now = now_ist()
        today = f"{now:%Y-%m-%d}"
        if now < at(C.MCXT_EXIT_TIME) or self.s["summary"].get(today):
            return
        day = [c for c in self.s["closed"] if c["closed"][:10] == today]
        self.s["summary"][today] = True
        self.s["summary"] = {k: v for k, v in self.s["summary"].items() if k >= f"{now - pd.Timedelta(days=10):%Y-%m-%d}"}
        if not day:
            return
        allc = self.s["closed"]
        wins = [c for c in allc if c["pnl_rs_per_lot"] > 0]
        L = [f"📊 *MCX Buy/Sell – {now:%d %b}*"]
        for c in day:
            L.append(f"{'✅' if c['pnl_rs_per_lot'] > 0 else '❌'} {c['name']} {c['side']} {px(c['entry'])}→{px(c['exit'])}"
                     f"  {rs(c['pnl_rs_per_lot'])}/lot")
        L += [f"\nDay: *{rs(sum(c['pnl_rs_per_lot'] for c in day))}/lot*",
              f"All-time: {rs(sum(c['pnl_rs_per_lot'] for c in allc))}/lot | Win rate "
              f"{len(wins) / len(allc) * 100:.0f}% ({len(allc)} trades)"]
        notify.send("\n".join(L))


def run(api, master, force=False):
    t = MCXTrader(api, master)
    try:
        t.monitor()
        t.scan(force=force)
        t.summary()
    finally:
        t.save()
    return t
