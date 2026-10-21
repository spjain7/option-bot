"""
PAPER ENGINE v3 – MCX DAILY TREND (paper only: no order API is imported or called anywhere in this package)

Strategy (fixed, from research – no tuning):
  BUY  when the CLOSED daily candle closes above the highest high of the previous 55 days AND above the 200-day average
  Stop : 2 x ATR(20) from the ACTUAL paper fill;  Exit: close below the 20-day low -> next open;  LONG ONLY.
  RSI(14) > 70 blocks a fresh BUY (the user's rule) – a blocked BUY is never turned into a SELL.
  Volume / OI filters: OFF (volume did not pass independent testing; MCX OI history is unavailable).
Execution (paper): next session open of the actual contract, +slippage; cancelled if that open is > 0.5 ATR above
  the signal close or back below the breakout level. Size = floor(0.5% x marked-to-market equity / (fill - stop)
  x rupees per point) lots (main contract, else mini). Risk, exposure and margin are checked at the signal AND again
  at the fill. Positions roll at the close when <= 5 trading days remain, both legs costed, stop moved by the exact gap.
Alert statuses: WATCHLIST, CONFIRMED PAPER SIGNAL, NO TRADE (exactly these three).
"""
import json, os, re, datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = "MCX_DAILY_TREND_v3"
SCHEMA = 3
STATUSES = ("WATCHLIST", "CONFIRMED PAPER SIGNAL", "NO TRADE")

CFG = dict(
    instruments=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"],
    entry_n=55, exit_n=20, trend_n=200, atr_n=20, stop_atr=2.0,
    long_only=True,
    rsi_block=True, rsi_max_buy=70,
    use_volume_filter=False, use_oi_filter=False,          # not validated -> off
    chase_atr=0.5, watch_atr=0.5,
    capital=2_500_000, risk_pct=0.005,
    max_positions=5, max_open_risk_pct=0.02, group_risk_pct=0.01, max_margin_pct=0.5, daily_loss_pct=0.03,
    max_stop_pct=0.15, min_contract_volume=20, stale_days=4, hole_days=7, roll_days=5,
)
MULT = {"GOLD": 100, "SILVER": 30, "CRUDEOIL": 100, "NATURALGAS": 1250, "COPPER": 2500, "ZINC": 5000, "ALUMINIUM": 5000}
MINI = {"GOLD": ("GOLDM", 10), "SILVER": ("SILVERM", 5), "CRUDEOIL": ("CRUDEOILM", 10), "NATURALGAS": ("NATGASMINI", 250),
        "ZINC": ("ZINCMINI", 1000), "ALUMINIUM": ("ALUMINI", 1000)}
SLIP = {"GOLD": 5, "SILVER": 20, "CRUDEOIL": 2, "NATURALGAS": 0.3, "COPPER": 0.3, "ZINC": 0.2, "ALUMINIUM": 0.2}
MARGIN = {"GOLD": 0.10, "SILVER": 0.12, "CRUDEOIL": 0.30, "NATURALGAS": 0.35, "COPPER": 0.10, "ZINC": 0.10, "ALUMINIUM": 0.10}
GROUP = {"GOLD": "precious", "SILVER": "precious", "CRUDEOIL": "energy", "NATURALGAS": "energy",
         "COPPER": "base", "ZINC": "base", "ALUMINIUM": "base"}


def sides():
    """Allowed directions. Long-only is enforced here, not only by configuration."""
    return (1,) if CFG["long_only"] else (1, -1)


def round_trip_cost(name, price, lots=1, mult=None):
    """MCX non-agri: CTT 0.01% sell, exchange 0.0021%, SEBI ₹10/cr, stamp 0.002% buy, GST 18%, ₹20/order;
    slippage SLIP points per side is charged separately in the fill prices."""
    m = mult or MULT[name]; tv = price * m * lots
    exch, sebi, brk = 2 * tv * 0.000021, 2 * tv * 1e-6, 40.0
    return brk + exch + sebi + 0.18 * (brk + exch + sebi) + tv * 0.0001 + tv * 0.00002


def indicators(d):
    d = d.copy().reset_index(drop=True)
    c, h, l = d["close"], d["high"], d["low"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(CFG["atr_n"]).mean()
    d["sma"] = c.rolling(CFG["trend_n"]).mean()
    dd = c.diff()
    u, v = dd.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(), (-dd.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + u / v.replace(0, 1e-9))
    d["hi_in"] = h.shift(1).rolling(CFG["entry_n"]).max()
    d["lo_out"] = l.shift(1).rolling(CFG["exit_n"]).min()
    d["gap_days"] = d["time"].diff().dt.days
    d["hole_in_window"] = d["gap_days"].rolling(CFG["entry_n"] + CFG["atr_n"], min_periods=1).max() > CFG["hole_days"]
    if "unknown_in_window" not in d:
        d["unknown_in_window"] = False
    return d


def fmt(x):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else (f"{x:,.2f}" if abs(x) < 1000 else f"{x:,.0f}")


# ─────────────── state ───────────────
class StateError(RuntimeError):
    pass


class Book:
    """Persistent paper account. A missing state file is only accepted when new_account=True."""
    def __init__(self, folder, new_account=False):
        self.dir = Path(folder); self.file = self.dir / "paper_state.json"; self.log_file = self.dir / "paper_log.jsonl"
        if self.file.exists():
            try:
                self.s = json.loads(self.file.read_text())
            except Exception as e:
                raise StateError(f"state file unreadable – refusing to start a new account: {e}")
            if self.s.get("schema") != SCHEMA:
                raise StateError(f"state schema {self.s.get('schema')} != {SCHEMA}")
        elif new_account:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.s = dict(schema=SCHEMA, strategy=STRATEGY, created=str(dt.datetime.utcnow()), cash=CFG["capital"],
                          positions=[], pending=[], closed=[], sent={}, last_state={}, processed={},
                          day_open_equity={}, day_close_equity={}, next_id=1, marks={})
        else:
            raise StateError("no paper state found and new_account was not requested – stopping safely")

    def log(self, event, **kw):
        with self.log_file.open("a") as f:
            f.write(json.dumps(dict(ts=str(dt.datetime.utcnow()), event=event, strategy=STRATEGY, **kw), default=str) + "\n")

    def save(self):
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.s, indent=1, default=str))
        tmp.replace(self.file)                                   # atomic replace: no half-written state

    # equity = cash + open positions marked at their contract's latest close
    def equity(self):
        return self.s["cash"] + sum(p["side"] * (self.s["marks"].get(p["contract"], p["entry"]) - p["entry"]) * p["mult"] * p["lots"]
                                    for p in self.s["positions"])

    def locked(self, day):
        """Entry lock for `day`: the previous recorded trading day lost more than the daily limit (open->close)."""
        prev = [d for d in self.s["day_close_equity"] if d < str(day)[:10]]
        if not prev:
            return None
        p = max(prev)
        o, c = self.s["day_open_equity"].get(p), self.s["day_close_equity"][p]
        if o and c / o - 1 < -CFG["daily_loss_pct"]:
            return f"daily loss limit: {p} equity fell {abs(c / o - 1) * 100:.1f}% (limit {CFG['daily_loss_pct'] * 100:g}%)"
        return None


# ─────────────── alerts ───────────────
def alert_text(a):
    icon = {"CONFIRMED PAPER SIGNAL": "🟢", "WATCHLIST": "👀", "NO TRADE": "⛔"}[a["status"]]
    head = f"{icon} *{a['status']}*{' – ' + a['stage'] if a.get('stage') else ''} | {a['instrument']} {a['direction']}"
    L = [head,
         f"Paper ID {a['paper_id']} · generated {a['generated']} UTC · {STRATEGY} · timeframe 1 day",
         f"Exchange: MCX | Contract: {a.get('contract')} | Expiry: {a['expiry']}",
         f"Signal candle: {a['signal_time']} (closed) | Data as of: {a['data_time']}"]
    if a["status"] == "WATCHLIST":
        L += [f"Setup developing: close {fmt(a.get('close'))} is {a.get('distance_atr'):.2f} ATR below the {CFG['entry_n']}-day high "
              f"{fmt(a.get('level'))}. Not a trade: entry needs a daily CLOSE above it and every check passing."]
    elif a.get("fill") is not None:
        L += [f"Paper fill (actual simulated): {fmt(a['fill'])} at the {a['fill_time']} open incl. {SLIP[a['instrument']]} pts slippage",
              f"Stop (recalculated from the fill): {fmt(a['stop'])} = fill − {CFG['stop_atr']:g}×ATR {fmt(a.get('atr'))}",
              f"Quantity: {a['qty_text']} | Risk ₹{a['risk_rs']:,.0f} ({a['risk_pct_eq']:.2f}% of paper equity)",
              f"Exit condition: daily close below the {CFG['exit_n']}-day low → exit at the next open; or the stop",
              f"Est. charges round trip: ₹{a['cost_rs']:,.0f} + slippage {SLIP[a['instrument']]} pts/side"]
    else:
        L += [f"Entry condition: BUY at the next session open of {a.get('contract')}, only if that open is ≤ {CFG['chase_atr']} ATR "
              f"above {fmt(a.get('close'))} and still above the breakout level {fmt(a.get('level'))}",
              f"Indicative (signal-based, not a fill): entry ≈ {fmt(a.get('close'))} | stop ≈ {fmt(a.get('ind_stop'))} "
              f"({CFG['stop_atr']:g}×ATR {fmt(a.get('atr'))}); the real stop is recalculated from the paper fill",
              f"Exit condition: daily close below the {CFG['exit_n']}-day low (now {fmt(a.get('exit_level'))}) → next open; or the stop",
              f"Indicative risk: ₹{fmt(a.get('risk_lot'))}/lot" + (f", ₹{fmt(a.get('risk_mini'))}/{a['mini']} lot" if a.get("mini") else "")
              + f" | quantity: {a.get('qty_text', '-')}",
              f"Est. charges round trip: ₹{fmt(a.get('cost_rs'))} per {a.get('cost_contract', 'lot')} lot + slippage {SLIP[a['instrument']]} pts/side"]
    L.append(f"Values used: close {fmt(a.get('close'))}, {CFG['entry_n']}d high {fmt(a.get('level'))}, "
             f"{CFG['trend_n']}d avg {fmt(a.get('sma'))}, RSI(14) {fmt(a.get('rsi'))}, ATR(20) {fmt(a.get('atr'))}")
    if a.get("reasons"):
        L.append("Passed: " + "; ".join(a["reasons"]))
    if a.get("blocks"):
        L.append("Rejected because: " + "; ".join(a["blocks"]))
    if a.get("warnings"):
        L.append("⚠️ " + " | ".join(a["warnings"]))
    L.append("_Paper alert for research only – no order is placed. Not advice. No target or profit is promised._")
    return "\n".join(L)


# ─────────────── engine ───────────────
class Engine:
    def __init__(self, provider, book, send=None):
        if CFG["long_only"] and -1 in sides():
            raise AssertionError("long-only violated")
        self.p, self.book, self.send, self.alerts = provider, book, send, []
        self._idx = {}

    def emit(self, a):
        assert a["status"] in STATUSES
        if a["direction"] == "SELL" and CFG["long_only"] and a["status"] == "CONFIRMED PAPER SIGNAL":
            raise AssertionError("long-only: a confirmed SELL must never be produced")
        s = self.book.s
        key = "|".join([STRATEGY, a["instrument"], a["contract"], a["direction"], a["signal_time"], a["status"], a.get("stage") or ""])
        if key in s["sent"]:
            return False
        s["sent"][key] = a["signal_time"]
        sig = [a["status"], sorted(re.sub(r"[\d.,₹%-]+", "#", b)[:40] for b in a.get("blocks") or [])]
        sk = f"{a['instrument']}|{a['direction']}"
        last = s["last_state"].get(sk)
        s["last_state"][sk] = sig
        if a["status"] != "CONFIRMED PAPER SIGNAL" and last == sig:   # unchanged WATCHLIST / NO TRADE: log only
            self.book.log("ALERT_SUPPRESSED", key=key)
            return False
        a = dict(a, paper_id=f"P{s['next_id']:05d}", generated=dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M"))
        s["next_id"] += 1
        txt = alert_text(a)
        self.alerts.append(dict(a, text=txt))
        self.book.log("ALERT", key=key, **{k: v for k, v in a.items() if k != "text"})
        if self.send:
            try:
                self.send(txt)
            except Exception as e:
                self.book.log("ERROR", where="telegram", error=str(e)[:200])
        return True

    # ---------- limits ----------
    def limits(self, name, risk_rs, margin_rs, day, exclude_pending=False):
        s, eq, blocks = self.book.s, self.book.equity(), []
        lock = self.book.locked(day)
        if lock:
            blocks.append(lock)
        book = s["positions"] + ([] if exclude_pending else s["pending"])
        if len(book) >= CFG["max_positions"]:
            blocks.append(f"max {CFG['max_positions']} positions")
        if sum(p["risk_rs"] for p in book) + risk_rs > CFG["max_open_risk_pct"] * eq:
            blocks.append(f"total open risk would exceed {CFG['max_open_risk_pct'] * 100:g}% of equity")
        g = GROUP[name]
        if sum(p["risk_rs"] for p in book if GROUP[p["instrument"]] == g) + risk_rs > CFG["group_risk_pct"] * eq:
            blocks.append(f"{g} group risk would exceed {CFG['group_risk_pct'] * 100:g}% of equity")
        used = sum(p["margin_rs"] for p in book)
        if used + margin_rs > CFG["max_margin_pct"] * eq:
            blocks.append(f"margin ₹{used + margin_rs:,.0f} would exceed {CFG['max_margin_pct'] * 100:g}% of equity")
        if used + margin_rs > eq:
            blocks.append("not enough free equity for margin")
        return blocks

    def size(self, name, R):
        budget = CFG["risk_pct"] * self.book.equity()
        lots = int(budget // (R * MULT[name]))
        if lots >= 1:
            return name, MULT[name], lots
        if name in MINI:
            lots = int(budget // (R * MINI[name][1]))
            if lots >= 1:
                return MINI[name][0], MINI[name][1], lots
        return None, None, 0

    # ---------- daily steps ----------
    def at_open(self, name, day):
        s = self.book.s
        for pos in [p for p in s["positions"] if p["instrument"] == name and p.get("exit_pending")]:
            bar = self.p.contract_bar(pos["contract"], day)
            if bar is None:
                self.book.log("ERROR", instrument=name, error=f"no candle for {pos['contract']} on {day}: exit delayed"); continue
            self.close(pos, bar["open"] - pos["side"] * SLIP[name], "channel exit (next open)", day)
        for pend in [p for p in s["pending"] if p["instrument"] == name]:
            s["pending"].remove(pend)
            self.fill(pend, day)

    def fill(self, pend, day):
        name, a = pend["instrument"], pend["alert"]
        bar = self.p.contract_bar(pend["contract"], day)
        rej = []
        if bar is None:
            rej.append(f"no {day} candle for {pend['contract']} (contract data missing)")
        else:
            if bar["open"] - pend["signal_close"] > CFG["chase_atr"] * pend["atr"]:
                rej.append(f"opened {fmt(bar['open'])}: more than {CFG['chase_atr']} ATR above the signal close (chase)")
            if bar["open"] <= pend["level"]:
                rej.append(f"opened {fmt(bar['open'])}: back below the breakout level {fmt(pend['level'])}")
        if not rej:
            fill = bar["open"] + SLIP[name]
            R = CFG["stop_atr"] * pend["atr"]; stop = fill - R
            lot_name, mult, lots = self.size(name, R)
            if lots == 0:
                rej.append("1 lot (incl. mini) would risk more than the per-trade limit at the fill")
            else:
                margin = lots * mult * fill * MARGIN[name]
                rej += self.limits(name, lots * mult * R, margin, day, exclude_pending=True)
        if rej:
            self.book.log("REJECTED_AT_FILL", instrument=name, day=day, blocks=rej)
            self.emit(dict(a, status="NO TRADE", stage="at fill", data_time=str(day)[:10], blocks=rej))
            return
        eq = self.book.equity()
        pos = dict(id=f"{name}-{str(day)[:10]}", instrument=name, side=1, direction="BUY", contract=pend["contract"],
                   expiry=pend["expiry"], entry_time=str(day)[:10], entry=fill, stop=stop, R=R, lots=lots, mult=mult,
                   lot_name=lot_name, risk_rs=lots * mult * R, margin_rs=lots * mult * fill * MARGIN[name],
                   signal_time=pend["signal_time"], rsi=pend["rsi"], rolls=0, roll_cost=0.0, exit_pending=False)
        self.book.s["positions"].append(pos)
        self.book.s["marks"][pos["contract"]] = bar["close"]
        self.book.log("ENTRY", **pos)
        cost = round_trip_cost(name, fill, lots, mult)
        self.emit(dict(a, status="CONFIRMED PAPER SIGNAL", stage="paper fill recorded", data_time=str(day)[:10], fill=fill,
                       fill_time=str(day)[:10], stop=stop, qty_text=f"{lots} × {lot_name}", risk_rs=lots * mult * R,
                       risk_pct_eq=lots * mult * R / eq * 100, cost_rs=cost))

    def manage(self, name, day, sig_row):
        """Stops on the contract candle, rolls, then the exit signal at the close (signal series)."""
        s = self.book.s
        for pos in [p for p in s["positions"] if p["instrument"] == name]:
            bar = self.p.contract_bar(pos["contract"], day)
            if bar is None:
                self.book.log("ERROR", instrument=name, error=f"no candle for held {pos['contract']} on {day}"); continue
            s["marks"][pos["contract"]] = bar["close"]
            if pos["entry_time"] != str(day)[:10] and bar["open"] <= pos["stop"]:
                self.close(pos, bar["open"] - SLIP[name], "gap through stop (filled at open)", day); continue
            if bar["low"] <= pos["stop"]:
                self.close(pos, pos["stop"] - SLIP[name], "stop", day); continue
            roll = self.p.roll_due(pos, day)
            if roll:
                self.roll(pos, roll, day)
            if sig_row is not None and not pos["exit_pending"] and sig_row["close"] < sig_row["lo_out"]:
                pos["exit_pending"] = True
                self.book.log("EXIT_SIGNAL", id=pos["id"], day=day, close=sig_row["close"], level=sig_row["lo_out"])

    def roll(self, pos, new, day):
        old_bar, new_bar = self.p.contract_bar(pos["contract"], day), self.p.contract_bar(new["symbol"], day)
        if old_bar is None or new_bar is None:
            self.book.log("ERROR", instrument=pos["instrument"], error=f"roll to {new['symbol']} not possible on {day}: "
                                                                   "missing contract candle – position kept, retried tomorrow")
            return
        gap = new_bar["close"] - old_bar["close"]
        cost = round_trip_cost(pos["instrument"], old_bar["close"], pos["lots"], pos["mult"]) + 2 * SLIP[pos["instrument"]] * pos["mult"] * pos["lots"]
        realised = pos["side"] * (old_bar["close"] - pos["entry"]) * pos["mult"] * pos["lots"]
        self.book.s["cash"] += realised - cost
        self.book.log("ROLL", id=pos["id"], day=day, old=pos["contract"], new=new["symbol"], gap=gap, cost=cost, realised=realised)
        pos.update(contract=new["symbol"], expiry=new["expiry"], entry=new_bar["close"], stop=pos["stop"] + gap,
                   rolls=pos["rolls"] + 1, roll_cost=pos["roll_cost"] + cost, realised_before_roll=pos.get("realised_before_roll", 0) + realised)
        self.book.s["marks"][new["symbol"]] = new_bar["close"]

    def close(self, pos, px, why, day):
        s = self.book.s
        cost = round_trip_cost(pos["instrument"], pos["entry"], pos["lots"], pos["mult"])
        pnl = pos["side"] * (px - pos["entry"]) * pos["mult"] * pos["lots"] - cost
        total = pnl + pos.get("realised_before_roll", 0) - pos["roll_cost"]
        pos.update(exit_time=str(day)[:10], exit=px, exit_reason=why, cost_rs=cost + pos["roll_cost"],
                   pnl_rs=total, r_multiple=total / (pos["R"] * pos["mult"] * pos["lots"]),
                   gap_loss_rs=max(0.0, (pos["stop"] - px) * pos["mult"] * pos["lots"]) if "stop" in why else 0.0)
        s["cash"] += pnl
        s["positions"].remove(pos); s["closed"].append(pos)
        s["marks"].pop(pos["contract"], None)
        self.book.log("EXIT", **pos)

    def evaluate(self, name, day, d, i, issues):
        bar = d.iloc[i]
        if pd.isna(bar["atr"]) or pd.isna(bar["sma"]) or pd.isna(bar["hi_in"]):
            return
        if any(p["instrument"] == name for p in self.book.s["positions"] + self.book.s["pending"]):
            return                                                   # already in this instrument: no new alert
        con = self.p.contract_for(name, day)
        level, R = bar["hi_in"], CFG["stop_atr"] * bar["atr"]
        common = dict(instrument=name, direction="BUY", contract=con.get("symbol") or "unknown", expiry=con.get("expiry") or "unknown",
                      signal_time=str(bar["time"])[:10], data_time=str(con.get("asof", bar["time"]))[:10], close=bar["close"],
                      level=level, sma=bar["sma"], rsi=bar["rsi"], atr=bar["atr"], exit_level=bar["lo_out"],
                      warnings=con.get("warnings", []))
        if bar["close"] <= bar["sma"]:
            return                                                   # long trend filter not met: nothing to say
        if bar["close"] <= level:
            dist = (level - bar["close"]) / bar["atr"]
            if dist <= CFG["watch_atr"]:
                self.emit(dict(common, status="WATCHLIST", distance_atr=dist,
                               reasons=[f"close above the {CFG['trend_n']}-day average"]))
            return
        blocks, reasons = [], [f"close {fmt(bar['close'])} > {CFG['entry_n']}-day high {fmt(level)}",
                               f"close > {CFG['trend_n']}-day average {fmt(bar['sma'])}"]
        if CFG["rsi_block"] and bar["rsi"] > CFG["rsi_max_buy"]:
            blocks.append(f"RSI {bar['rsi']:.1f} > {CFG['rsi_max_buy']} blocks a fresh BUY (not reversed)")
        else:
            reasons.append(f"RSI {bar['rsi']:.1f} ≤ {CFG['rsi_max_buy']}")
        blocks += [f"data: {x}" for x in issues]
        if bar["hole_in_window"]:
            blocks.append("data hole inside the 75-bar indicator window")
        if bar["unknown_in_window"]:
            blocks.append("contract switch with UNKNOWN roll gap inside the 56-bar signal window (breakout/ATR not trusted)")
        if not con.get("symbol"):
            blocks.append("tradable contract / expiry not available")
        elif con.get("volume") is not None and con["volume"] < CFG["min_contract_volume"]:
            blocks.append(f"illiquid: {con['symbol']} traded {con['volume']} lots on the signal day (< {CFG['min_contract_volume']})")
        if R / bar["close"] > CFG["max_stop_pct"]:
            blocks.append(f"stop distance {R / bar['close'] * 100:.1f}% of price is too wide")
        lot_name, mult, lots = self.size(name, R)
        if lots == 0:
            blocks.append("even 1 lot (incl. mini) risks more than "
                          f"{CFG['risk_pct'] * 100:g}% of paper equity (₹{CFG['risk_pct'] * self.book.equity():,.0f})")
        else:
            blocks += self.limits(name, lots * mult * R, lots * mult * bar["close"] * MARGIN[name], day)
        a = dict(common, ind_stop=bar["close"] - R, risk_lot=R * MULT[name], mini=MINI.get(name, (None,))[0],
                 risk_mini=R * MINI[name][1] if name in MINI else None,
                 cost_rs=round_trip_cost(name, bar["close"], 1, mult or MULT[name]), cost_contract=lot_name or name,
                 qty_text=f"{lots} × {lot_name} (indicative; final size set at the fill)" if lots else "none",
                 reasons=reasons)
        if blocks:
            self.book.log("REJECTED", instrument=name, day=day, blocks=blocks)
            self.emit(dict(a, status="NO TRADE", stage="at signal", blocks=blocks))
            return
        self.emit(dict(a, status="CONFIRMED PAPER SIGNAL", stage="signal – fill at next open"))
        self.book.s["pending"].append(dict(instrument=name, contract=con["symbol"], expiry=con.get("expiry"),
                                           signal_close=bar["close"], level=level, atr=float(bar["atr"]), rsi=float(bar["rsi"]),
                                           signal_time=common["signal_time"], risk_rs=lots * mult * R,
                                           margin_rs=lots * mult * bar["close"] * MARGIN[name], alert=a))

    # ---------- run over every unprocessed day ----------
    def run_days(self, days):
        s = self.book.s
        for day in days:
            dkey = str(day)[:10]
            if s["processed"].get("__day__", "") >= dkey:
                continue                                             # this day was already processed: no duplicates
            s["day_open_equity"].setdefault(dkey, self.book.equity())
            for name in CFG["instruments"]:
                d, issues = self.p.series(name)
                if d is None:
                    continue
                m = self._idx.setdefault(name, {})
                if not m or m.get("__len__") != len(d):
                    m.clear(); m.update({t: k for k, t in enumerate(d["time"].dt.normalize())}); m["__len__"] = len(d)
                i = m.get(pd.Timestamp(day).normalize())
                if i is None:
                    continue
                self.at_open(name, day)
                self.manage(name, day, d.iloc[i])
                self.evaluate(name, day, d, i, issues if i == len(d) - 1 else [])
            s["day_close_equity"][dkey] = self.book.equity()
            s["processed"]["__day__"] = dkey


# ─────────────── providers ───────────────
class ReplayProvider:
    """History replay. mode="estimated": research series back-adjusted by ESTIMATED roll gaps (labelled; replay only).
    mode="strict": vendor series as recorded, switches treated as UNKNOWN gaps -> signals near them are refused and a
    held position is closed at the last close before an unknown switch (its P&L would otherwise include the jump)."""
    def __init__(self, mode="estimated", instruments=None):
        from research import roll_adjust as RA
        self.mode, self.data, self.flags = mode, {}, {}
        for n in instruments or CFG["instruments"]:
            raw, _ = RA.load_mcx(n, adjusted=False)
            if mode == "estimated":
                d, _ = RA.load_mcx(n, adjusted=True)
                d = d[["time", "open", "high", "low", "close", "volume", "roll"]].copy()
                d["unknown_in_window"] = False
            else:
                d = raw[["time", "open", "high", "low", "close", "volume"]].copy()
                unk = np.zeros(len(d), bool)
                for i in RA.detect_rolls(raw, n):
                    unk[i] = True
                d["roll"] = unk
                d["unknown_in_window"] = pd.Series(unk.astype(int)).rolling(CFG["entry_n"] + 1, min_periods=1).max().astype(bool).values
            self.data[n] = indicators(d)
            self.rows = getattr(self, "rows", {})
            self.rows[n] = {t: r for t, r in zip(self.data[n]["time"].dt.normalize(), self.data[n].to_dict("records"))}

    def series(self, name):
        return self.data.get(name), []

    def contract_for(self, name, day):
        return dict(symbol=f"{name}-SERIES-{self.mode}", expiry="n/a (replay)", asof=day,
                    warnings=[f"REPLAY ({self.mode} roll handling) – not a live contract"])

    def contract_bar(self, symbol, day):
        return self.rows[symbol.split("-SERIES")[0]].get(pd.Timestamp(day).normalize())

    def roll_due(self, pos, day):
        b = self.contract_bar(pos["contract"], day)
        return b is not None and bool(b["roll"]) and dict(symbol=pos["contract"], expiry="n/a")


class AngelProvider:
    """Live paper data: vendor front-month series for signals (exact roll gaps from the contract store only) and the
    actual contract's own candles for fills, stops and rolls. Read-only market data calls; no order methods used."""
    def __init__(self, api, master, store, now):
        self.api, self.master, self.store, self.now = api, master, store, pd.Timestamp(now)
        self.cache = {}

    def _listed(self, name):
        m = self.master[(self.master["name"] == name) & (self.master["instrumenttype"] == "FUTCOM")
                        & (self.master["expiry_dt"] >= self.now.normalize())]
        return m.sort_values("expiry_dt")

    def refresh(self, name, bootstrap_days=400):
        """Record the front and next contracts' own candles, then build the signal series."""
        from paper.contracts import validate, signal_series
        from research.roll_adjust import detect_rolls
        listed = self._listed(name)
        if listed.empty:
            self.cache[name] = (None, ["no listed contract"]); return
        for k, (_, c) in enumerate(listed.head(2).iterrows()):
            have = self.store.get(c["symbol"])
            frm = self.now - pd.Timedelta(days=bootstrap_days if have is None else 15)
            cd = self.api.candles("MCX", c["token"], "ONE_DAY", frm, self.now)
            if cd is None or cd.empty:
                continue
            cd, _ = validate(self._closed(cd))
            if k == 0:
                # The NEAREST token returns the vendor-stitched history (older days belong to expired contracts), so
                # for the front contract only days after what is already recorded are stored; on a brand-new store
                # only the latest closed candle is stored. Its earlier own history was recorded while it was "next".
                last = None if have is None else have["time"].max()
                cd = cd.tail(1) if last is None else cd[pd.to_datetime(cd["time"]).dt.normalize() > last]
            if not cd.empty:
                self.store.put(c["symbol"], name, c["token"], c["expiry_dt"], cd)
        vendor = self.api.candles("MCX", listed.iloc[0]["token"], "ONE_DAY", self.now - pd.Timedelta(days=420), self.now)
        vendor, issues = validate(self._closed(vendor) if vendor is not None else None, now=self.now,
                                  stale_days=CFG["stale_days"], hole_days=CFG["hole_days"])
        if vendor is None or vendor.empty:
            self.cache[name] = (None, issues); return
        unknown = [vendor["time"].iloc[i] for i in detect_rolls(vendor, name)]
        sig, sw = signal_series(vendor, self.store, name, unknown, window=CFG["entry_n"] + 1)
        self.cache[name] = (indicators(sig), issues)

    def _closed(self, df):
        """Closed candles only: today's candle counts only after the MCX session (23:56 IST)."""
        if self.now >= self.now.normalize() + pd.Timedelta(hours=23, minutes=56):
            return df
        return df[pd.to_datetime(df["time"]).dt.normalize() < self.now.normalize()]

    def series(self, name):
        if name not in self.cache:
            self.refresh(name)
        return self.cache[name]

    def contract_for(self, name, day):
        listed = self._listed(name)
        if listed.empty:
            return dict(symbol=None)
        front = listed.iloc[0]
        left = int(np.busday_count(self.now.date(), front["expiry_dt"].date()))
        pick = listed.iloc[1] if left <= CFG["roll_days"] and len(listed) > 1 else front
        b = self.store.bar(pick["symbol"], day)
        w = [f"front {front['symbol']} has {left} trading days left – {pick['symbol']} is the tradable contract"] if pick is not front else []
        return dict(symbol=pick["symbol"], expiry=f"{pick['expiry_dt']:%d-%b-%Y}", asof=self.now,
                    volume=None if b is None else float(b["volume"]), warnings=w)

    def contract_bar(self, symbol, day):
        return self.store.bar(symbol, day)

    def roll_due(self, pos, day):
        exp = pd.Timestamp(pos["expiry"])
        if int(np.busday_count(pd.Timestamp(day).date(), exp.date())) > CFG["roll_days"]:
            return None
        listed = self._listed(pos["instrument"])
        nxt = listed[listed["expiry_dt"] > exp]
        return None if nxt.empty else dict(symbol=nxt.iloc[0]["symbol"], expiry=f"{nxt.iloc[0]['expiry_dt']:%d-%b-%Y}")


# ─────────────── runners ───────────────
def replay(start, end=None, mode="estimated", state_dir=None, send=None):
    sd = Path(state_dir or (ROOT / "paper" / "replay"))
    for f in ("paper_state.json", "paper_log.jsonl"):
        (sd / f).unlink(missing_ok=True)
    book = Book(sd, new_account=True)
    prov = ReplayProvider(mode)
    eng = Engine(prov, book, send)
    days = sorted(set().union(*[set(d["time"].dt.normalize()) for d in prov.data.values()]))
    days = [x for x in days if x >= pd.Timestamp(start) and (end is None or x <= pd.Timestamp(end))]
    curve = []
    for day in days:
        eng.run_days([day])
        if mode == "strict":                                         # close before an unknown switch (no fake P&L)
            for pos in list(book.s["positions"]):
                n = pos["instrument"]; d = prov.data[n]; k = eng._idx.get(n, {}).get(day)
                if k is not None and k + 1 < len(d) and d.at[k + 1, "roll"]:
                    eng.close(pos, d.at[k, "close"] - SLIP[n], "closed before unknown roll", day)
        curve.append(dict(date=day, equity=book.equity()))
    book.s["curve"] = curve
    book.save()
    return book, eng


def report(book, out_dir, label):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    c = pd.DataFrame(book.s["closed"])
    log = [json.loads(x) for x in book.log_file.read_text().splitlines()] if book.log_file.exists() else []
    alerts = [x for x in log if x["event"] == "ALERT"]
    curve = pd.DataFrame(book.s.get("curve", []))
    res = dict(label=label, alerts=len(alerts),
               alerts_by_status=pd.Series([f"{a['status']} ({a.get('stage') or '-'})" for a in alerts]).value_counts().to_dict() if alerts else {},
               confirmed_signals=sum(1 for a in alerts if a["status"] == "CONFIRMED PAPER SIGNAL" and str(a.get("stage", "")).startswith("signal")),
               fills=sum(1 for x in log if x["event"] == "ENTRY"),
               rejected_at_fill=sum(1 for x in log if x["event"] == "REJECTED_AT_FILL"),
               closed_trades=len(c), start_equity=CFG["capital"], end_equity=round(book.equity()))
    if not c.empty:
        r = c["r_multiple"]; w, l = r[r > 0], r[r <= 0]
        streak = mx = 0
        for x in r:
            streak = streak + 1 if x <= 0 else 0; mx = max(mx, streak)
        c["exit_time"] = pd.to_datetime(c["exit_time"])
        res.update(net_pnl_rs=round(c.pnl_rs.sum()), costs_rs=round(c.cost_rs.sum()), win_pct=round((r > 0).mean() * 100, 1),
                   avg_R=round(r.mean(), 3), profit_factor=round(w.sum() / -l.sum(), 2) if l.sum() < 0 else None,
                   max_dd_R=round(float((r.cumsum() - r.cumsum().cummax()).min()), 2), longest_losing_streak=mx,
                   gap_losses_rs=round(c.gap_loss_rs.sum()), rolls=int(c.rolls.sum()),
                   by_instrument={k: round(v) for k, v in c.groupby("instrument").pnl_rs.sum().items()},
                   by_year={str(k): round(v) for k, v in c.groupby(c.exit_time.dt.year).pnl_rs.sum().items()},
                   by_exit={k: int(v) for k, v in c.exit_reason.value_counts().items()})
        c.to_csv(out / f"{label}_trades.csv", index=False)
    if not curve.empty:
        curve.to_csv(out / f"{label}_equity.csv", index=False)
        e = curve.equity; ddr = e - e.cummax()
        res.update(max_dd_rs=round(ddr.min()), max_dd_pct=round((e / e.cummax() - 1).min() * 100, 1),
                   return_pct=round((e.iloc[-1] / CFG["capital"] - 1) * 100, 1),
                   monthly_pct={str(k): round(v * 100, 2) for k, v in
                                curve.set_index(pd.to_datetime(curve.date)).equity.resample("ME").last().pct_change().dropna().items()})
    pd.DataFrame(alerts).to_csv(out / f"{label}_alerts.csv", index=False)
    (out / f"{label}_summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def run_live(state_dir=None, new_account=False, now=None, api=None, master=None):
    """One paper run against Angel market data (read-only). Telegram only if PAPER_TELEGRAM=1."""
    import sys
    sys.path.insert(0, str(ROOT))
    from paper.contracts import ContractStore
    sd = Path(state_dir or os.getenv("PAPER_STATE_DIR", ROOT / "state" / "paper"))
    book = Book(sd, new_account=new_account or os.getenv("PAPER_NEW_ACCOUNT") == "1")
    if api is None:
        from angel import Angel, load_master, now_ist
        api, master, now = Angel(), load_master(), now_ist()
    send = None
    if os.getenv("PAPER_TELEGRAM") == "1":
        import notify
        send = notify.send
    store = ContractStore(sd / "contracts")
    prov = AngelProvider(api, master, store, now)
    eng = Engine(prov, book, send)
    for n in CFG["instruments"]:
        try:
            prov.refresh(n)
        except Exception as e:
            book.log("ERROR", instrument=n, error=f"{type(e).__name__}: {str(e)[:200]}")
            prov.cache[n] = (None, [f"refresh failed: {type(e).__name__}"])
    days = sorted(set().union(*[set(d["time"].dt.normalize()) for d, _ in prov.cache.values() if d is not None]))
    last = book.s["processed"].get("__day__")
    todo = [d for d in days if last is None or str(d)[:10] > last]
    if last is None:
        todo = todo[-1:]                                              # new account starts from the latest closed candle
    eng.run_days(todo)
    book.save()
    print(f"paper run done: processed {len(todo)} day(s) {[str(d)[:10] for d in todo]}, alerts {len(eng.alerts)}, "
          f"equity ₹{book.equity():,.0f}, open {len(book.s['positions'])}, pending {len(book.s['pending'])}")
    for a in eng.alerts:
        print("\n" + a["text"])
    return book, eng


if __name__ == "__main__":
    run_live()
