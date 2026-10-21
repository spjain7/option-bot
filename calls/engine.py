"""
TELEGRAM TRADING-CALL ENGINE (Engine D) – intraday + positional, MCX commodities + NIFTY / BANKNIFTY futures,
with an option-buying idea on every call. ALERTS ONLY: no order API is called anywhere.

Runs inside runner.py every 15 minutes (switch: config.CALLS_ENABLED). Own state file: state/calls.json.
  INTRADAY  : 1-hour closed candles of the traded contract -> CALL with entry / SL / T1 / T2, follow-ups for T1, T2,
              SL and the session square-off.
  POSITIONAL: daily closed candles -> CALL valid for the next session open (cancelled if price ran > 0.5 ATR),
              then ENTRY ACTIVE / CANCELLED, stop updates, ROLL reminder before expiry and EXIT on the 20-day channel.
Status words used in messages: WATCHLIST, CALL, NO TRADE (+ follow-ups for calls already sent).
Rules: calls/rules.py. These rules are NOT validated: the intraday version lost money after costs in the earlier
backtests and the positional one did not meet the pass criteria. Every message says so in one line.
"""
import json, re
from pathlib import Path
import numpy as np
import pandas as pd
import config as C
import market as M
import notify
from angel import now_ist
from calls import rules as R, options as O

STATE_FILE = Path(__file__).resolve().parents[1] / "state" / "calls.json"
VERSION = "CALLS_v1"
WARN = "⚠️ Unvalidated rules (backtests: intraday negative after costs, positional below pass criteria). Not advice."

MCX = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]
NSE = ["NIFTY", "BANKNIFTY"]
MINI = {"GOLD": "GOLDM", "SILVER": "SILVERM", "CRUDEOIL": "CRUDEOILM", "NATURALGAS": "NATGASMINI"}
SESSION = {"MCX": dict(open="09:00", first="10:00", last="22:00", squareoff="23:00", close="23:30", candle_end="23:55"),
           "NFO": dict(open="09:15", first="10:15", last="14:30", squareoff="15:10", close="15:30", candle_end="15:30")}
SET = dict(risk_intraday=0.01, risk_positional=0.005, max_open_intraday=4, max_open_positional=6, max_calls_name_day=2,
           roll_days={"MCX": 5, "NFO": 2}, cost_order_rs=getattr(C, "COST_PER_ORDER_RS", 40), options=True)


def exch_of(name):
    return "MCX" if name in MCX else "NFO"


def at(s, now=None):
    now = now or now_ist()
    h, m = map(int, s.split(":"))
    return now.normalize() + pd.Timedelta(hours=h, minutes=m)


def px(x):
    return "-" if x is None else (f"{x:,.2f}" if abs(x) < 1000 else f"{x:,.0f}")


def rs(x):
    return f"₹{x:,.0f}" if x >= 0 else f"-₹{abs(x):,.0f}"


class CallEngine:
    def __init__(self, api, master, now=None, send=None):
        self.api, self.master = api, master
        self.now = pd.Timestamp(now) if now is not None else now_ist()
        self.send = send or notify.send
        self.s = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        for k, v in dict(open=[], closed=[], pending=[], done={}, last_state={}, summary={}, next_id=1).items():
            self.s.setdefault(k, v)
        self.sent = []

    # ─────────────── plumbing ───────────────
    def save(self):
        cut = f"{self.now - pd.Timedelta(days=10):%Y-%m-%d}"
        self.s["done"] = {k: v for k, v in self.s["done"].items() if v >= cut}
        self.s["closed"] = self.s["closed"][-500:]
        STATE_FILE.parent.mkdir(exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp"); tmp.write_text(json.dumps(self.s, indent=1, default=str)); tmp.replace(STATE_FILE)

    def msg(self, text, key=None):
        if key:
            if key in self.s["done"]:
                return False
            self.s["done"][key] = f"{self.now:%Y-%m-%d}"
        self.sent.append(text)
        self.send(text)
        return True

    def state_changed(self, sk, sig):
        last = self.s["last_state"].get(sk); self.s["last_state"][sk] = sig
        return last != sig

    def contract(self, name, min_days):
        ex = exch_of(name)
        ft = M.FUT_TYPES["MCX" if ex == "MCX" else "NFO"]
        m = self.master[(self.master["name"] == name) & (self.master["exch_seg"] == ex) & self.master["instrumenttype"].isin(ft)
                        & (self.master["expiry_dt"] >= self.now.normalize())].sort_values("expiry_dt")
        if m.empty:
            return None, None
        nearest = m.iloc[0]
        for _, c in m.iterrows():
            if np.busday_count(self.now.date(), c["expiry_dt"].date()) > min_days:
                return c.to_dict(), nearest.to_dict()
        return m.iloc[-1].to_dict(), nearest.to_dict()

    def mult(self, name, contract):
        return C.MCX_RS_PER_POINT.get(name, 1) if exch_of(name) == "MCX" else int(contract["lotsize"])

    def lots_text(self, name, contract, R_pts, risk_pct):
        budget = C.CAPITAL_RS * risk_pct
        m = self.mult(name, contract)
        lots = int(budget // (R_pts * m))
        out = f"{lots} lot(s)" if lots else f"0 (1 lot risks {rs(R_pts * m)} = {R_pts * m / C.CAPITAL_RS * 100:.1f}% of capital)"
        mini = MINI.get(name)
        if mini and C.MCX_RS_PER_POINT.get(mini):
            mm = C.MCX_RS_PER_POINT[mini]; ml = int(budget // (R_pts * mm))
            out += f" | mini {mini}: {ml} lot(s) ({rs(R_pts * mm)}/lot)"
        return out, lots, m, budget

    def closed_candles(self, df, ex, tf):
        S = SESSION[ex]
        if df is None or df.empty:
            return None
        df = df.copy(); df["time"] = pd.to_datetime(df["time"])
        df = df[~df["time"].duplicated()].sort_values("time")
        bad = (df["high"] < df[["open", "close"]].max(axis=1)) | (df["low"] > df[["open", "close"]].min(axis=1)) | (df[["open", "close"]] <= 0).any(axis=1)
        df = df[~bad]
        if tf == "1h":
            h, m = map(int, S["candle_end"].split(":"))
            end = df["time"].map(lambda t: min(t + pd.Timedelta(hours=1), t.normalize() + pd.Timedelta(hours=h, minutes=m)))
            return df[end <= self.now].reset_index(drop=True)
        done = self.now >= at(S["candle_end"], self.now) + pd.Timedelta(minutes=1)
        return df[df["time"].dt.normalize() < self.now.normalize()].reset_index(drop=True) if not done else df.reset_index(drop=True)

    def quote(self, ex, tokens):
        return self.api.quotes({ex: [str(t) for t in tokens]}) if tokens else {}

    def option_block(self, oi):
        if not oi:
            return []
        if "symbol" not in oi:
            return [f"📈 Option: {oi.get('note')}"]
        L = [f"📈 *Option buy idea:* {oi['symbol']} (exp {oi['expiry']}) @ {px(oi['entry'])}  Δ{oi['delta']}"
             + (f", IV {oi['iv']}%" if oi.get("iv") else ""),
             f"   SL ~{px(oi['sl'])}" + (f" | T1 ~{px(oi['t1'])}" if oi.get("t1") else "") + (f" | T2 ~{px(oi['t2'])}" if oi.get("t2") else "")
             + f" | cost {rs(oi['cost_lot'])}/lot, risk {rs(oi['risk_lot'])}/lot" + (f", {oi['lots']} lot(s)" if "lots" in oi else "")]
        return L

    # ─────────────── INTRADAY ───────────────
    def intraday_scan(self):
        today = f"{self.now:%Y-%m-%d}"
        for name in MCX + NSE:
            ex = exch_of(name); S = SESSION[ex]
            if not (at(S["first"], self.now) <= self.now <= at(S["last"], self.now)):
                continue
            if len([p for p in self.s["open"] if p["mode"] == "intraday"]) >= SET["max_open_intraday"]:
                return
            if any(p["name"] == name and p["mode"] == "intraday" for p in self.s["open"]):
                continue
            if sum(1 for p in self.s["open"] + self.s["closed"] if p["name"] == name and p["mode"] == "intraday"
                   and p["opened"][:10] == today) >= SET["max_calls_name_day"]:
                continue
            c, nearest = self.contract(name, SET["roll_days"][ex] if ex == "MCX" else 2)
            if c is None:
                continue
            df = self.api.candles(ex, c["token"], "ONE_HOUR", self.now - pd.Timedelta(days=90), self.now)
            df = self.closed_candles(df, ex, "1h")
            if df is None or df.empty or df["time"].iloc[-1].normalize() != self.now.normalize():
                continue
            key = f"intra|{name}|{df['time'].iloc[-1]:%Y-%m-%d %H:%M}"
            if key in self.s["done"]:
                continue
            self.s["done"][key] = today
            sig, why = R.intraday(df)
            print(f"calls intraday {name}: {why if sig is None else sig['side'] + (' blocked' if sig.get('blocked') else '')}")
            if sig is None:
                continue
            warn = []
            if str(c["token"]) == str(nearest["token"]):
                warn.append("traded contract is the nearest one: older candles may include the previous contract")
            if sig.get("blocked"):
                if self.state_changed(f"intra|{name}|{sig['side']}", "blocked"):
                    self.msg(self.fmt_intra(name, ex, c, sig, None, None, [sig["blocked"]], warn), key + "|nt")
                continue
            q = self.quote(ex, [c["token"]]).get(str(c["token"]), {})
            ltp = float(q.get("ltp") or sig["close"]); s = 1 if sig["side"] == "BUY" else -1
            if s * (ltp - sig["close"]) > R.INTRA["chase_atr"] * sig["atr"]:
                self.msg(self.fmt_intra(name, ex, c, sig, None, None,
                                        [f"price {px(ltp)} already > {R.INTRA['chase_atr']} ATR beyond the signal close (chase)"], warn), key + "|nt")
                continue
            plan = R.intraday_plan(sig, ltp)
            lots_txt, lots, mult, budget = self.lots_text(name, c, plan["R"], SET["risk_intraday"])
            oi = None
            if SET["options"]:
                try:
                    oi = O.idea(self.api, self.master, name, ex, sig["side"], ltp, plan["R"], plan["R"], 2 * plan["R"],
                                "intraday", budget)
                except Exception as e:
                    oi = dict(note=f"option idea failed ({type(e).__name__})")
            call = dict(id=self.s["next_id"], mode="intraday", name=name, exch=ex, side=sig["side"], symbol=c["symbol"],
                        token=str(c["token"]), expiry=f"{c['expiry_dt']:%d-%b-%Y}", mult=mult, **{k: round(v, 2) for k, v in plan.items()},
                        t1_hit=False, opened=f"{self.now:%Y-%m-%d %H:%M}", candle=sig["candle"],
                        opt=oi if oi and "token" in oi else None)
            self.s["next_id"] += 1
            self.s["open"].append(call)
            self.msg(self.fmt_intra(name, ex, c, sig, call, lots_txt, None, warn, oi), key + "|call")

    def fmt_intra(self, name, ex, c, sig, call, lots_txt, blocks, warn, oi=None):
        buy = sig["side"] == "BUY"
        head = (f"{'🟢' if buy else '🔴'} *CALL – INTRADAY {sig['side']} {name}*  #{call['id']}" if call
                else f"⛔ *NO TRADE – intraday {sig['side']} {name}*")
        L = [head, f"{'MCX' if ex == 'MCX' else 'NSE F&O'} | {c['symbol']} (exp {c['expiry_dt']:%d-%b-%Y}) | 1H | {VERSION}",
             f"Signal candle {sig['candle'][:16]} (closed) | data {self.now:%d-%b %H:%M} IST"]
        if call:
            L += [f"Entry: *{px(call['entry'])}* (live) | SL: *{px(call['sl'])}* | T1: {px(call['t1'])} | T2: {px(call['t2'])}",
                  f"Risk {px(call['R'])} pts = {rs(call['R'] * call['mult'])}/lot | Qty: {lots_txt} (≤{SET['risk_intraday'] * 100:g}% of {rs(C.CAPITAL_RS)})",
                  f"After T1: book half, SL to cost. Square off by {SESSION[ex]['squareoff']}."]
        why = (f"{'up' if buy else 'down'}trend (EMA20/50/200), ADX {sig['adx']:.0f}, broke 5-hr {'high ' + px(sig['level_hi']) if buy else 'low ' + px(sig['level_lo'])}, "
               f"RSI {sig['rsi']:.0f}" + (f", volume {sig['vol_x']:.1f}x" if sig.get("vol_x") else ""))
        L.append("Why: " + why)
        if blocks:
            L.append("Rejected: " + "; ".join(blocks))
        L += self.option_block(oi)
        if warn:
            L.append("⚠️ " + " | ".join(warn))
        L.append(WARN)
        return "\n".join(L)

    def intraday_monitor(self):
        opens = [p for p in self.s["open"] if p["mode"] == "intraday"]
        if not opens:
            return
        by_ex = {}
        for p in opens:
            by_ex.setdefault(p["exch"], []).append(p["token"])
            if p.get("opt") and p["opt"].get("token"):
                by_ex[p["exch"]].append(p["opt"]["token"])
        q = {}
        for ex, toks in by_ex.items():
            q.update(self.quote(ex, sorted(set(toks))))
        ltp = lambda t: float((q.get(str(t)) or {}).get("ltp") or 0)
        for p in opens:
            f = ltp(p["token"])
            if not f:
                continue
            s = 1 if p["side"] == "BUY" else -1
            o = ltp(p["opt"]["token"]) if p.get("opt") else 0
            S = SESSION[p["exch"]]
            if not p["t1_hit"] and s * (f - p["t1"]) >= 0:
                p.update(t1_hit=True, t1_px=f, sl=p["entry"], opt_t1_px=o or None)
                self.msg(f"✅ *T1 hit – {p['name']} {p['side']}* #{p['id']}\nFuture {px(f)} ({rs(s * (f - p['entry']) * p['mult'])}/lot)"
                         + (f" | Option {px(o)}" if o else "") + f"\nBook half. SL moved to cost {px(p['entry'])}.", f"t1|{p['id']}")
                continue
            why = None
            if s * (f - p["t2"]) >= 0:
                why = "🎯 T2 hit"
            elif s * (f - p["sl"]) <= 0:
                why = "🟰 Exit at cost (after T1)" if p["t1_hit"] else "🛑 SL hit"
            elif self.now >= at(S["squareoff"], self.now):
                why = "⏰ Square-off time"
            if why:
                self.close(p, f, o, why)

    def close(self, p, f, o, why):
        s = 1 if p["side"] == "BUY" else -1
        half = 0.5 if p.get("t1_hit") else 1.0
        pts = (1 - half) * s * (p.get("t1_px", f) - p["entry"]) + half * s * (f - p["entry"])
        pnl = pts * p["mult"] - 2 * SET["cost_order_rs"]
        p.update(exit=f, exit_reason=why, closed=f"{self.now:%Y-%m-%d %H:%M}", pnl_rs_per_lot=round(pnl))
        L = [f"{why} – *{p['name']} {p['side']}* #{p['id']} ({p['mode']})",
             f"Future exit {px(f)} (entry {px(p['entry'])}) → *{rs(pnl)}/lot*"]
        if p.get("opt") and o:
            ot1 = p.get("opt_t1_px") or o
            opnl = ((1 - half) * (ot1 - p["opt"]["entry"]) + half * (o - p["opt"]["entry"])) * p["opt"]["rs_per_point"] - 2 * SET["cost_order_rs"]
            p["opt_pnl_rs_per_lot"] = round(opnl)
            L.append(f"Option {p['opt']['symbol']} {px(o)} (entry {px(p['opt']['entry'])}) → {rs(opnl)}/lot")
        self.s["open"].remove(p); self.s["closed"].append(p)
        self.msg("\n".join(L), f"close|{p['id']}")

    # ─────────────── POSITIONAL ───────────────
    def positional_scan(self):
        for name in MCX + NSE:
            ex = exch_of(name)
            c, nearest = self.contract(name, SET["roll_days"][ex])
            if c is None:
                continue
            d = self.api.candles(ex, nearest["token"], "ONE_DAY", self.now - pd.Timedelta(days=420), self.now)
            d = self.closed_candles(d, ex, "1d")
            if d is None or len(d) < 210:
                continue
            candle = f"{d['time'].iloc[-1]:%Y-%m-%d}"
            key = f"pos|{name}|{candle}"
            if key in self.s["done"]:
                continue
            self.s["done"][key] = candle
            self.positional_manage(name, d)
            if any(p["name"] == name and p["mode"] == "positional" for p in self.s["open"] + self.s["pending"]):
                continue
            state, info = R.positional(d)
            if state is None:
                self.s["last_state"][f"pos|{name}"] = None
                continue
            sk = f"pos|{name}"; sig = f"{state}|{info.get('side')}"
            warn = self.roll_warning(d)
            if state == "WATCH":
                if self.state_changed(sk, sig):
                    self.msg(self.fmt_pos_watch(name, ex, c, info, warn), key + "|watch")
                continue
            if state == "BLOCKED":
                if self.state_changed(sk, sig):
                    self.msg(self.fmt_pos(name, ex, c, info, None, [info["why"]], warn), key + "|nt")
                continue
            if len([p for p in self.s["open"] if p["mode"] == "positional"]) >= SET["max_open_positional"]:
                self.msg(self.fmt_pos(name, ex, c, info, None, [f"max {SET['max_open_positional']} positional calls open"], warn), key + "|nt")
                continue
            self.state_changed(sk, sig)
            R_pts = R.POS["stop_atr"] * info["atr"]
            lots_txt, lots, mult, budget = self.lots_text(name, c, R_pts, SET["risk_positional"])
            oi = None
            if SET["options"]:
                try:
                    oi = O.idea(self.api, self.master, name, ex, info["side"], info["close"], R_pts, None, None,
                                "positional", budget)
                except Exception as e:
                    oi = dict(note=f"option idea failed ({type(e).__name__})")
            pend = dict(id=self.s["next_id"], mode="positional", name=name, exch=ex, side=info["side"], symbol=c["symbol"],
                        token=str(c["token"]), expiry=f"{c['expiry_dt']:%Y-%m-%d}", mult=mult, signal_close=info["close"],
                        level=info["level"], atr=info["atr"], candle=candle, created=f"{self.now:%Y-%m-%d %H:%M}",
                        opt=oi if oi and "token" in oi else None, lots_text=lots_txt)
            self.s["next_id"] += 1
            self.s["pending"].append(pend)
            self.msg(self.fmt_pos(name, ex, c, info, pend, None, warn, oi), key + "|call")

    def roll_warning(self, d):
        """Vendor history switches contract at expiry: a big unexplained jump inside the 56-day window can distort levels."""
        w = d.tail(57).copy(); r = w["close"].pct_change().abs(); a = (w["high"] - w["low"]).mean() / w["close"].mean()
        v = w["volume"].astype(float); jump = (v / v.shift(1).replace(0, np.nan)) > 3
        sus = (r > 2.5 * a) & jump
        return ["possible contract-switch jump inside the 55-day window – levels may be shifted"] if sus.any() else []

    def fmt_pos_watch(self, name, ex, c, info, warn):
        L = [f"👀 *WATCHLIST – positional {info['side']} {name}*",
             f"{'MCX' if ex == 'MCX' else 'NSE F&O'} | {c['symbol']} (exp {c['expiry_dt']:%d-%b-%Y}) | 1D | {VERSION}",
             f"Candle {info['candle']} (closed): close {px(info['close'])} is {info['distance_atr']} ATR from the 55-day "
             f"{'high' if info['side'] == 'BUY' else 'low'} {px(info['level'])}. Not a call yet – needs a daily close beyond it.",
             f"Trend: 200-day avg {px(info['sma'])} | RSI {info['rsi']:.0f}"]
        if warn:
            L.append("⚠️ " + " | ".join(warn))
        return "\n".join(L)

    def fmt_pos(self, name, ex, c, info, pend, blocks, warn, oi=None):
        buy = info["side"] == "BUY"; s = 1 if buy else -1
        head = (f"{'🟢' if buy else '🔴'} *CALL – POSITIONAL {info['side']} {name}*  #{pend['id']}" if pend
                else f"⛔ *NO TRADE – positional {info['side']} {name}*")
        L = [head, f"{'MCX' if ex == 'MCX' else 'NSE F&O'} | {c['symbol']} (exp {c['expiry_dt']:%d-%b-%Y}) | 1D | {VERSION}",
             f"Signal candle {info['candle']} (closed) | data {self.now:%d-%b %H:%M} IST"]
        if pend:
            R_pts = R.POS["stop_atr"] * info["atr"]
            L += [f"Entry: {info['side']} at the next session open, valid only if price is ≤ {R.POS['chase_atr']} ATR beyond "
                  f"{px(info['close'])} (≤ {px(info['close'] + s * R.POS['chase_atr'] * info['atr'])}) and still beyond {px(info['level'])}",
                  f"Indicative SL: {px(info['close'] - s * R_pts)} (2×ATR {px(info['atr'])}; reset from the actual entry)",
                  f"Exit: daily close {'below' if buy else 'above'} the 20-day {'low' if buy else 'high'} "
                  f"(now {px(info['exit_long'] if buy else info['exit_short'])}) → exit next open. No fixed target.",
                  f"Risk {px(R_pts)} pts = {rs(R_pts * self.mult(name, c))}/lot | Qty: {pend['lots_text']} "
                  f"(≤{SET['risk_positional'] * 100:g}% of {rs(C.CAPITAL_RS)})"]
        L.append(f"Why: close {px(info['close'])} {'>' if buy else '<'} 55-day {'high' if buy else 'low'} {px(info['level'])}, "
                 f"{'above' if buy else 'below'} 200-day avg {px(info['sma'])}, RSI {info['rsi']:.0f}")
        if blocks:
            L.append("Rejected: " + "; ".join(blocks))
        L += self.option_block(oi)
        if warn:
            L.append("⚠️ " + " | ".join(warn))
        L.append(WARN)
        return "\n".join(L)

    def positional_activate(self):
        """First run of the session after a positional CALL: entry ACTIVE at the live price, or CANCELLED."""
        for p in list(self.s["pending"]):
            S = SESSION[p["exch"]]
            if not (at(S["open"], self.now) + pd.Timedelta(minutes=5) <= self.now <= at(S["close"], self.now)):
                continue
            if self.now.normalize() <= pd.Timestamp(p["candle"]):
                continue                                             # still the signal day
            q = self.quote(p["exch"], [p["token"]] + ([p["opt"]["token"]] if p.get("opt") else []))
            f = float((q.get(p["token"]) or {}).get("ltp") or 0)
            if not f:
                continue
            s = 1 if p["side"] == "BUY" else -1
            self.s["pending"].remove(p)
            why = None
            if s * (f - p["signal_close"]) > R.POS["chase_atr"] * p["atr"]:
                why = f"price {px(f)} more than {R.POS['chase_atr']} ATR beyond the signal close {px(p['signal_close'])} (chase)"
            elif s * (f - p["level"]) <= 0:
                why = f"price {px(f)} back {'below' if s > 0 else 'above'} the breakout level {px(p['level'])}"
            if why:
                self.msg(f"⛔ *NO TRADE – positional {p['side']} {p['name']}* #{p['id']} cancelled\n{why}", f"cancel|{p['id']}")
                continue
            sl = f - s * R.POS["stop_atr"] * p["atr"]
            o = float((q.get(p["opt"]["token"]) or {}).get("ltp") or 0) if p.get("opt") else 0
            p.update(entry=f, sl=sl, R=R.POS["stop_atr"] * p["atr"], opened=f"{self.now:%Y-%m-%d %H:%M}", exit_pending=False,
                     t1_hit=False)
            if p.get("opt") and o:
                p["opt"]["entry"] = o
            self.s["open"].append(p)
            self.msg(f"✅ *ENTRY ACTIVE – positional {p['side']} {p['name']}* #{p['id']}\n{p['symbol']} entry {px(f)} | "
                     f"SL {px(sl)} (2×ATR from entry) | risk {rs(p['R'] * p['mult'])}/lot"
                     + (f"\nOption {p['opt']['symbol']} now {px(o)}" if p.get("opt") and o else "")
                     + "\nExit only on the 20-day channel or the SL. " + WARN, f"active|{p['id']}")

    def positional_manage(self, name, d):
        """On a new daily candle: channel exit (next open) and roll reminder."""
        for p in [p for p in self.s["open"] if p["mode"] == "positional" and p["name"] == name]:
            if not p.get("exit_pending") and R.positional_exit(d, p["side"]):
                p["exit_pending"] = True
                self.msg(f"🔔 *EXIT at next open – {p['name']} {p['side']}* #{p['id']}\nDaily close {px(float(d['close'].iloc[-1]))} "
                         f"crossed the 20-day channel.", f"exitsig|{p['id']}")
            left = np.busday_count(self.now.date(), pd.Timestamp(p["expiry"]).date())
            if left <= SET["roll_days"][p["exch"]] and not p.get("roll_noted"):
                nc, _ = self.contract(name, SET["roll_days"][p["exch"]])
                if nc is not None and nc["symbol"] != p["symbol"]:
                    p["roll_noted"] = True
                    self.msg(f"🔁 *ROLL – {p['name']} {p['side']}* #{p['id']}\n{p['symbol']} expires in {left} trading days. "
                             f"Move to {nc['symbol']} (exp {nc['expiry_dt']:%d-%b-%Y}); shift the SL by the price difference between "
                             f"the two contracts at the time you roll.", f"roll|{p['id']}")

    def positional_monitor(self):
        opens = [p for p in self.s["open"] if p["mode"] == "positional"]
        for p in opens:
            S = SESSION[p["exch"]]
            if not (at(S["open"], self.now) + pd.Timedelta(minutes=5) <= self.now <= at(S["close"], self.now)):
                continue
            q = self.quote(p["exch"], [p["token"]] + ([p["opt"]["token"]] if p.get("opt") else []))
            f = float((q.get(p["token"]) or {}).get("ltp") or 0)
            if not f:
                continue
            o = float((q.get(p["opt"]["token"]) or {}).get("ltp") or 0) if p.get("opt") else 0
            s = 1 if p["side"] == "BUY" else -1
            if s * (f - p["sl"]) <= 0:
                self.close(p, f, o, "🛑 SL hit (positional)")
            elif p.get("exit_pending"):
                self.close(p, f, o, "🔚 Channel exit (positional)")

    # ─────────────── summary ───────────────
    def summary(self):
        today = f"{self.now:%Y-%m-%d}"
        if self.now < at("23:05", self.now) or self.s["summary"].get(today):
            return
        self.s["summary"][today] = True
        day = [c for c in self.s["closed"] if c.get("closed", "")[:10] == today]
        op = self.s["open"]
        if not day and not op:
            return
        L = [f"📊 *Calls – {self.now:%d %b}*"]
        for c in day:
            L.append(f"{'✅' if c['pnl_rs_per_lot'] > 0 else '❌'} {c['name']} {c['side']} ({c['mode']}) {px(c['entry'])}→{px(c['exit'])} "
                     f"{rs(c['pnl_rs_per_lot'])}/lot")
        if day:
            L.append(f"Day: *{rs(sum(c['pnl_rs_per_lot'] for c in day))}/lot* on {len(day)} closed call(s)")
        if op:
            L.append("Open: " + ", ".join(f"{p['name']} {p['side']} ({p['mode']})" for p in op))
        self.msg("\n".join(L), f"summary|{today}")


def run(api, master, force=False, now=None, send=None):
    e = CallEngine(api, master, now, send)
    try:
        e.positional_activate()
        e.intraday_monitor()
        e.positional_monitor()
        e.intraday_scan()
        e.positional_scan()
        e.summary()
    finally:
        e.save()
    return e
