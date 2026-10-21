"""
PAPER ENGINE – MCX DAILY TREND ALERTS (research / paper mode only, separate from every live engine)

Rules (base C, as backtested in research/): signal on the CLOSED daily candle of the front-month future
  BUY  : close > highest high of the previous 55 days AND close > 200-day average
  SELL : close < lowest low of the previous 55 days AND close < 200-day average      (only if SIDES allows shorts)
  RSI rule (kept as the user defined it): RSI(14) > 70 blocks a fresh BUY, RSI(14) < 30 blocks a fresh SELL.
           A blocked signal is NOT reversed - it becomes NO TRADE.
  Entry  : next session open (paper fill = open +/- slippage); cancelled if the open is more than CHASE_ATR x ATR
           beyond the signal close (NO TRADE - chase)
  Stop   : 2 x ATR(20) from the entry; a gap through the stop fills at the open
  Exit   : close beyond the opposite 20-day channel -> exit at the next open
Alert states: WATCHLIST (setup developing), CONFIRMED PAPER SIGNAL (all conditions + risk checks pass),
              NO TRADE (signal present but blocked: data, chase, risk, exposure, RSI rule ...)
Own state file, own event log, own dedup keys. Telegram only when PAPER_TELEGRAM=1 (off by default).
Nothing here is a recommendation; results are paper results.
"""
import json, os, math
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = "MCX_DAILY_TREND_v2"

# ─────────────── settings (paper engine only – the live config.py is not touched) ───────────────
CFG = dict(
    instruments=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"],
    entry_n=55, exit_n=20, trend_n=200, atr_n=20, stop_atr=2.0,
    sides=(1, -1),                 # research candidate variant: (1,) = long-only
    rsi_block=True,                # user rule: RSI>70 blocks BUY, RSI<30 blocks SELL
    chase_atr=0.5,                 # NO TRADE if next open is > 0.5 ATR beyond the signal close
    watch_atr=0.5,                 # WATCHLIST when close is within 0.5 ATR of the breakout level
    capital=2_500_000, risk_pct=0.005, max_positions=5, max_open_risk_pct=0.02, group_risk_pct=0.01,
    max_capital_use=0.5, daily_loss_pct=0.03, max_stop_pct=0.15, min_volume=1,
    stale_days=4,                  # NO TRADE if the latest candle is older than this many calendar days
    roll_days=5,                   # trade the next contract when the front has <= 5 days to expiry
)
MULT = {"GOLD": 100, "SILVER": 30, "CRUDEOIL": 100, "NATURALGAS": 1250, "COPPER": 2500, "ZINC": 5000, "ALUMINIUM": 5000}
MINI = {"GOLD": ("GOLDM", 10), "SILVER": ("SILVERM", 5), "CRUDEOIL": ("CRUDEOILM", 10), "NATURALGAS": ("NATGASMINI", 250),
        "ZINC": ("ZINCMINI", 1000), "ALUMINIUM": ("ALUMINI", 1000)}
SLIP = {"GOLD": 5, "SILVER": 20, "CRUDEOIL": 2, "NATURALGAS": 0.3, "COPPER": 0.3, "ZINC": 0.2, "ALUMINIUM": 0.2}
MARGIN = {"GOLD": 0.10, "SILVER": 0.12, "CRUDEOIL": 0.30, "NATURALGAS": 0.35, "COPPER": 0.10, "ZINC": 0.10, "ALUMINIUM": 0.10}
GROUP = {"GOLD": "precious", "SILVER": "precious", "CRUDEOIL": "energy", "NATURALGAS": "energy",
         "COPPER": "base", "ZINC": "base", "ALUMINIUM": "base"}


def round_trip_cost(name, price, lots=1, mult=None):
    """MCX non-agri: CTT 0.01% sell, exch 0.0021%, SEBI ₹10/cr, stamp 0.002% buy, GST 18%, ₹20/order + slippage."""
    m = mult or MULT[name]
    tv = price * m * lots
    exch, sebi, brk = 2 * tv * 0.000021, 2 * tv * 1e-6, 40.0
    return brk + exch + sebi + 0.18 * (brk + exch + sebi) + tv * 0.0001 + tv * 0.00002 + 2 * SLIP[name] * m * lots


def indicators(d):
    d = d.copy().reset_index(drop=True)
    c, h, l = d["close"], d["high"], d["low"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(CFG["atr_n"]).mean()
    d["sma"] = c.rolling(CFG["trend_n"]).mean()
    dd = c.diff()
    u, v = dd.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(), (-dd.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + u / v.replace(0, 1e-9))
    d["hi_in"] = h.shift(1).rolling(CFG["entry_n"]).max(); d["lo_in"] = l.shift(1).rolling(CFG["entry_n"]).min()
    d["hi_out"] = h.shift(1).rolling(CFG["exit_n"]).max(); d["lo_out"] = l.shift(1).rolling(CFG["exit_n"]).min()
    d["gap_days"] = d["time"].diff().dt.days
    return d


# ─────────────── state / log ───────────────
class Book:
    def __init__(self, state_file, log_file):
        self.state_file, self.log_file = Path(state_file), Path(log_file)
        self.s = json.loads(self.state_file.read_text()) if self.state_file.exists() else {}
        for k, v in {"open": [], "closed": [], "pending": [], "keys": {}, "equity": CFG["capital"], "next_id": 1,
                     "last_equity": CFG["capital"], "block_new": False, "processed": {}}.items():
            self.s.setdefault(k, v)

    def log(self, event, **kw):
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a") as f:
            f.write(json.dumps(dict(event=event, strategy=STRATEGY, **kw), default=str) + "\n")

    def seen(self, key):
        return key in self.s["keys"]

    def mark(self, key, day):
        self.s["keys"][key] = str(day)[:10]

    def save(self):
        cut = sorted(self.s["keys"].values())[-2000:] if self.s["keys"] else []
        if len(self.s["keys"]) > 3000:
            keep = set(cut)
            self.s["keys"] = {k: v for k, v in self.s["keys"].items() if v in keep}
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.s, indent=1, default=str))


# ─────────────── alert text ───────────────
def fmt(x):
    return f"{x:,.2f}" if abs(x) < 1000 else f"{x:,.0f}"


def alert_text(a):
    icon = {"CONFIRMED PAPER SIGNAL": "🟢" if a["direction"] == "BUY" else "🔴", "WATCHLIST": "👀", "NO TRADE": "⛔"}[a["state"]]
    L = [f"{icon} *{a['state']}* – {a['instrument']} {a['direction']}  [PAPER · {STRATEGY}]",
         f"Exchange: MCX | Contract: {a['contract']} (expiry {a['expiry']}) | Timeframe: 1 day",
         f"Signal candle: {a['signal_time']} | Data as of: {a['data_time']}"]
    if a["state"] == "WATCHLIST":
        L += [f"Setup developing: close {fmt(a['close'])} is {a['distance_atr']:.2f} ATR from the "
              f"{CFG['entry_n']}-day {'high' if a['direction'] == 'BUY' else 'low'} {fmt(a['level'])}.",
              "Not confirmed. No entry unless a daily CLOSE breaks the level and all checks pass."]
    else:
        L += [f"Entry rule: {a['direction']} at the next session open (09:00 IST); cancelled if the open is more than "
              f"{CFG['chase_atr']} ATR beyond {fmt(a['close'])}",
              f"Estimated entry: {fmt(a['est_entry'])} | Stop: {fmt(a['stop'])} ({CFG['stop_atr']:g}×ATR)",
              f"Exit condition: daily close {'below' if a['direction'] == 'BUY' else 'above'} the {CFG['exit_n']}-day "
              f"{'low' if a['direction'] == 'BUY' else 'high'} (now {fmt(a['exit_level'])}) → exit next open; or the stop",
              f"Risk per lot: ₹{a['risk_lot']:,.0f}" + (f" | mini {a['mini']}: ₹{a['risk_mini']:,.0f}" if a.get("mini") else ""),
              f"Est. round-trip costs: ₹{a['cost_lot']:,.0f} per {a.get('cost_contract', 'lot')} lot (charges + slippage)",
              f"Suggested quantity: {a['qty_text']}"]
    if a.get("reasons"):
        L.append("Why: " + "; ".join(a["reasons"]))
    if a.get("blocks"):
        L.append("Blocked by: " + "; ".join(a["blocks"]))
    if a.get("warnings"):
        L.append("⚠️ " + " | ".join(a["warnings"]))
    L.append("_Paper alert for research. Not advice. Past backtests do not prove future profit; no target is guaranteed._")
    return "\n".join(L)


# ─────────────── engine ───────────────
@dataclass
class Engine:
    provider: object                      # .daily(name) -> DataFrame (closed candles); .contract(name, day) -> dict
    book: Book
    send: object = None                   # callable(text) or None
    alerts: list = field(default_factory=list)

    def emit(self, a):
        key = f"{STRATEGY}|{a['instrument']}|{a['contract']}|{a['signal_time']}|{a['state']}"
        if self.book.seen(key):
            return
        self.book.mark(key, a["signal_time"])
        # WATCHLIST / NO TRADE are sent only when the situation CHANGES (a breakout can persist for weeks);
        # every evaluation is still written to the log.
        sk = f"{a['instrument']}|{a['direction']}"
        import re
        sig = (a["state"], tuple(sorted(re.sub(r"[\d.,₹%]+", "#", b.split(" (")[0].split(":")[0]) for b in a.get("blocks") or [])))
        last = self.book.s.setdefault("last_state", {}).get(sk)
        self.book.s["last_state"][sk] = list(sig)
        if a["state"] != "CONFIRMED PAPER SIGNAL" and last is not None and tuple(last[0:1]) == sig[0:1] \
                and tuple(last[1]) == sig[1]:
            self.book.log("ALERT_SUPPRESSED", instrument=a["instrument"], state=a["state"], day=a["signal_time"])
            return
        txt = alert_text(a)
        self.alerts.append(dict(a, text=txt))
        self.book.log("ALERT", **{k: v for k, v in a.items() if k != "text"})
        if self.send:
            try:
                self.send(txt)
            except Exception as e:
                self.book.log("ERROR", where="send", error=str(e)[:200])

    # -- portfolio checks (at the time of the signal; re-checked at fill)
    def limits(self, name, risk_rs, margin_rs):
        s, eq, blocks = self.book.s, self.book.s["equity"], []
        if s["block_new"]:
            blocks.append(f"daily loss limit hit (>{CFG['daily_loss_pct'] * 100:g}% yesterday)")
        if len(s["open"]) + len(s["pending"]) >= CFG["max_positions"]:
            blocks.append(f"max {CFG['max_positions']} positions")
        open_risk = sum(p["risk_rs"] for p in s["open"] + s["pending"])
        if open_risk + risk_rs > CFG["max_open_risk_pct"] * eq:
            blocks.append(f"total open risk would exceed {CFG['max_open_risk_pct'] * 100:g}% of equity")
        g = GROUP[name]
        if sum(p["risk_rs"] for p in s["open"] + s["pending"] if GROUP[p["instrument"]] == g) + risk_rs > CFG["group_risk_pct"] * eq:
            blocks.append(f"{g} group risk would exceed {CFG['group_risk_pct'] * 100:g}%")
        if sum(p["margin_rs"] for p in s["open"] + s["pending"]) + margin_rs > CFG["max_capital_use"] * eq:
            blocks.append(f"margin use would exceed {CFG['max_capital_use'] * 100:g}% of equity")
        return blocks

    def size(self, name, R, price):
        budget = CFG["risk_pct"] * self.book.s["equity"]
        mult = MULT[name]; lots = int(budget // (R * mult)); which = name
        if lots == 0 and name in MINI:
            which, mult = MINI[name]; lots = int(budget // (R * mult))
        return which, mult, lots

    # -- daily cycle for one instrument, as of the latest closed candle
    def on_open(self, name, d, i):
        """Fill pending entries / exits at today's open (bar i)."""
        bar = d.iloc[i]; s = self.book.s
        for p in [p for p in s["pending"] if p["instrument"] == name]:
            s["pending"].remove(p)
            side = 1 if p["direction"] == "BUY" else -1
            if side * (bar.open - p["signal_close"]) > CFG["chase_atr"] * p["atr"]:
                self.book.log("REJECTED", instrument=name, reason="chase", open=bar.open, signal_close=p["signal_close"],
                              day=bar.time)
                a = dict(p["alert"], state="NO TRADE", data_time=str(bar.time.date()),
                         blocks=[f"opened {fmt(bar.open)}: more than {CFG['chase_atr']} ATR beyond the signal close (chase)"])
                self.emit(a); continue
            fill = bar.open + side * SLIP[name]
            stop = fill - side * CFG["stop_atr"] * p["atr"]
            pos = dict(id=s["next_id"], instrument=name, direction=p["direction"], side=side, entry_time=str(bar.time.date()),
                       entry=fill, stop=stop, R=CFG["stop_atr"] * p["atr"], lots=p["lots"], mult=p["mult"], lot_name=p["lot_name"],
                       contract=p["contract"], risk_rs=p["lots"] * p["mult"] * CFG["stop_atr"] * p["atr"],
                       margin_rs=p["lots"] * p["mult"] * fill * MARGIN[name], signal_time=p["signal_time"],
                       rsi=p["rsi"], best=fill, exit_pending=False)
            s["next_id"] += 1; s["open"].append(pos)
            self.book.log("ENTRY", **pos)
        for pos in [p for p in s["open"] if p["instrument"] == name and p["exit_pending"]]:
            self.close(pos, bar.open - pos["side"] * SLIP[name], "channel exit", bar.time)

    def on_bar(self, name, d, i):
        """Stops during bar i, then decisions at its close."""
        bar = d.iloc[i]; s = self.book.s
        for pos in [p for p in s["open"] if p["instrument"] == name]:
            side = pos["side"]
            if pos["entry_time"] != str(bar.time.date()) and side * (bar.open - pos["stop"]) <= 0:
                self.close(pos, bar.open - side * SLIP[name], "gap through stop", bar.time); continue
            if side * ((bar.low if side > 0 else bar.high) - pos["stop"]) <= 0:
                self.close(pos, pos["stop"] - side * SLIP[name], "stop", bar.time); continue
            lvl = bar.lo_out if side > 0 else bar.hi_out
            if not pos["exit_pending"] and side * (bar.close - lvl) < 0:
                pos["exit_pending"] = True
                self.book.log("EXIT_SIGNAL", id=pos["id"], instrument=name, day=bar.time, close=bar.close, level=lvl)

    def close(self, pos, px, why, day):
        s = self.book.s
        cost = round_trip_cost(pos["instrument"], pos["entry"], pos["lots"], pos["mult"])
        pnl = pos["side"] * (px - pos["entry"]) * pos["mult"] * pos["lots"] - cost
        pos.update(exit_time=str(pd.Timestamp(day).date()), exit=px, exit_reason=why, cost_rs=cost, pnl_rs=pnl,
                   r_multiple=pos["side"] * (px - pos["entry"]) / pos["R"] - cost / (pos["R"] * pos["mult"] * max(pos["lots"], 1)),
                   stop_slippage_rs=(abs(px - pos["stop"]) * pos["mult"] * pos["lots"]) if "stop" in why else 0.0)
        s["open"].remove(pos); s["closed"].append(pos); s["equity"] += pnl
        self.book.log("EXIT", **pos)

    def evaluate(self, name, d, i, contract):
        """Alert state for the candle i close."""
        bar = d.iloc[i]
        if pd.isna(bar.atr) or pd.isna(bar.sma) or pd.isna(bar.hi_in):
            return
        common = dict(instrument=name, contract=contract.get("symbol", "?"), expiry=contract.get("expiry", "?"),
                      signal_time=str(bar.time.date()), data_time=str(bar.time.date()), close=bar.close)
        warnings = []
        if contract.get("roll_note"):
            warnings.append(contract["roll_note"])
        warnings.append("Signal series = vendor-stitched front month (not roll-adjusted)")
        for side, lvl_in, word in ((1, bar.hi_in, "BUY"), (-1, bar.lo_in, "SELL")):
            trend_ok = side * (bar.close - bar.sma) > 0
            broke = side * (bar.close - lvl_in) > 0
            if not trend_ok:
                continue
            if not broke:
                dist = side * (lvl_in - bar.close) / bar.atr
                if 0 <= dist <= CFG["watch_atr"] and side in CFG["sides"] and \
                        not any(p["instrument"] == name for p in self.book.s["open"]):
                    self.emit(dict(common, state="WATCHLIST", direction=word, level=lvl_in, distance_atr=dist,
                                   reasons=[f"close {'above' if side > 0 else 'below'} the {CFG['trend_n']}-day average "
                                            f"{fmt(bar.sma)}"], warnings=warnings))
                continue
            if side not in CFG["sides"]:
                continue                                    # direction switched off for this variant: silently ignored
            R = CFG["stop_atr"] * bar.atr
            est = bar.close
            lot_name, mult, lots = self.size(name, R, est)
            blocks, reasons = [], [f"close {fmt(bar.close)} broke the {CFG['entry_n']}-day "
                                   f"{'high' if side > 0 else 'low'} {fmt(lvl_in)}",
                                   f"{'above' if side > 0 else 'below'} the {CFG['trend_n']}-day average {fmt(bar.sma)}",
                                   f"RSI {bar.rsi:.0f}"]
            if CFG["rsi_block"] and ((side > 0 and bar.rsi > 70) or (side < 0 and bar.rsi < 30)):
                blocks.append(f"RSI {bar.rsi:.0f} {'> 70 blocks a fresh BUY' if side > 0 else '< 30 blocks a fresh SELL'}")
            age = (pd.Timestamp(contract.get("now", bar.time)) - bar.time).days
            if age > CFG["stale_days"]:
                blocks.append(f"data stale ({age} days old)")
            if bar.volume < CFG["min_volume"]:
                blocks.append("no volume on the signal candle")
            recent_gap = d["gap_days"].iloc[max(0, i - 260):i + 1].max()
            if recent_gap > 7:
                blocks.append(f"data hole of {int(recent_gap)} days inside the indicator window")
            if R / bar.close > CFG["max_stop_pct"]:
                blocks.append(f"stop distance {R / bar.close * 100:.1f}% of price is too wide")
            if lots == 0:
                smallest = (f"even 1 {MINI[name][0]} lot (₹{R * MINI[name][1]:,.0f})" if name in MINI
                            else f"1 lot (₹{R * MULT[name]:,.0f})")
                blocks.append(f"{smallest} risks more than {CFG['risk_pct'] * 100:g}% of equity "
                              f"(₹{CFG['risk_pct'] * self.book.s['equity']:,.0f})")
            margin = lots * mult * est * MARGIN[name]
            if any(p["instrument"] == name for p in self.book.s["open"] + self.book.s["pending"]):
                self.book.log("SKIP", instrument=name, day=bar.time, reason="already in a position / pending")
                continue                                            # holding already: no new alert
            blocks += self.limits(name, lots * mult * R, margin)
            a = dict(common, direction=word, est_entry=est, stop=est - side * R, exit_level=bar.lo_out if side > 0 else bar.hi_out,
                     risk_lot=R * MULT[name], mini=MINI.get(name, (None,))[0],
                     risk_mini=R * MINI[name][1] if name in MINI else None,
                     cost_lot=round_trip_cost(name, est, 1, mult if lots else MULT[name]), cost_contract=lot_name,
                     qty_text=(f"{lots} × {lot_name} (risk ₹{lots * mult * R:,.0f} = "
                               f"{lots * mult * R / self.book.s['equity'] * 100:.2f}% of paper equity)") if lots and not blocks else "none",
                     reasons=reasons, warnings=warnings, rsi=bar.rsi)
            if blocks:
                self.book.log("REJECTED", instrument=name, day=bar.time, direction=word, blocks=blocks)
                self.emit(dict(a, state="NO TRADE", blocks=blocks))
            else:
                self.emit(dict(a, state="CONFIRMED PAPER SIGNAL"))
                self.book.s["pending"].append(dict(instrument=name, direction=word, signal_close=bar.close, atr=float(bar.atr),
                                                   lots=lots, mult=mult, lot_name=lot_name, contract=common["contract"],
                                                   signal_time=common["signal_time"], rsi=float(bar.rsi), alert=a,
                                                   risk_rs=lots * mult * R, margin_rs=margin))

    def end_of_day(self, marks):
        """marks: {instrument: close}. Mark-to-market for the daily-loss limit."""
        s = self.book.s
        unreal = sum(p["side"] * (marks.get(p["instrument"], p["entry"]) - p["entry"]) * p["mult"] * p["lots"] for p in s["open"])
        eq = s["equity"] + unreal
        s["block_new"] = (eq / s["last_equity"] - 1) < -CFG["daily_loss_pct"] if s["last_equity"] > 0 else False
        s["last_equity"] = eq
        return eq


# ─────────────── providers ───────────────
class ReplayProvider:
    """Historical replay through the same engine code (labelled REPLAY - not live paper)."""
    def __init__(self, frames):
        self.frames = {n: indicators(f) for n, f in frames.items()}

    def contract(self, name, day):
        return dict(symbol=f"{name} front month (replay)", expiry="n/a", now=day)


class AngelProvider:
    """Live: Angel vendor-stitched front-month daily candles + the contract you would actually trade."""
    def __init__(self, api, master):
        self.api, self.master = api, master

    def daily(self, name):
        from angel import now_ist
        now = now_ist()
        m = self.master[(self.master["name"] == name) & (self.master["instrumenttype"] == "FUTCOM")
                        & (self.master["expiry_dt"] >= now.normalize())].sort_values("expiry_dt")
        if m.empty:
            return None
        df = self.api.candles("MCX", m.iloc[0]["token"], "ONE_DAY", now - pd.Timedelta(days=420), now)
        if df is None or df.empty:
            return None
        session_over = now >= now.normalize() + pd.Timedelta(hours=23, minutes=56)
        if not session_over:                                       # today's candle is still forming: drop it
            df = df[df["time"].dt.normalize() < now.normalize()]
        return indicators(df)

    def contract(self, name, day):
        from angel import now_ist
        now = now_ist()
        m = self.master[(self.master["name"] == name) & (self.master["instrumenttype"] == "FUTCOM")
                        & (self.master["expiry_dt"] >= now.normalize())].sort_values("expiry_dt")
        if m.empty:
            return dict(symbol="?", expiry="?", now=now)
        front = m.iloc[0]
        days_left = int(np.busday_count(now.date(), front["expiry_dt"].date()))
        pick = m.iloc[1] if days_left <= CFG["roll_days"] and len(m) > 1 else front
        note = (f"front {front['symbol']} has {days_left} trading days left: trade {pick['symbol']}"
                if pick is not front else None)
        return dict(symbol=pick["symbol"], expiry=f"{pick['expiry_dt']:%d-%b-%Y}", token=str(pick["token"]), now=now,
                    roll_note=note)


def replay(frames, start, end=None, sides=None, send=None, state_dir=None):
    """Run the engine bar by bar over history. Returns (book, engine)."""
    if sides is not None:
        CFG["sides"] = sides
    sd = Path(state_dir or (ROOT / "paper" / "replay"))
    for f in ("state.json", "log.jsonl"):
        (sd / f).unlink(missing_ok=True)
    book = Book(sd / "state.json", sd / "log.jsonl")
    prov = ReplayProvider(frames)
    eng = Engine(prov, book, send)
    days = sorted(set().union(*[set(f["time"]) for f in prov.frames.values()]))
    days = [d for d in days if d >= pd.Timestamp(start) and (end is None or d <= pd.Timestamp(end))]
    idx = {n: {t: i for i, t in enumerate(f["time"])} for n, f in prov.frames.items()}
    curve = []
    for day in days:
        marks = {}
        for n, f in prov.frames.items():
            i = idx[n].get(day)
            if i is None:
                continue
            eng.on_open(n, f, i)
            eng.on_bar(n, f, i)
            marks[n] = f.at[i, "close"]
        for n, f in prov.frames.items():
            i = idx[n].get(day)
            if i is not None:
                eng.evaluate(n, f, i, prov.contract(n, day))
        curve.append(dict(date=day, equity=eng.end_of_day(marks), open=len(book.s["open"])))
    book.s["curve"] = curve
    book.save()
    return book, eng


def report(book, out_dir, label):
    """Paper performance report: after-cost P&L, missed fills, stop slippage, drawdown, long/short, instrument."""
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    c = pd.DataFrame(book.s["closed"])
    log = [json.loads(x) for x in Path(book.log_file).read_text().splitlines()] if Path(book.log_file).exists() else []
    rej = [x for x in log if x["event"] == "REJECTED"]
    alerts = [x for x in log if x["event"] == "ALERT"]
    curve = pd.DataFrame(book.s.get("curve", []))
    res = dict(label=label, closed_trades=len(c), alerts=len(alerts),
               alerts_by_state=pd.Series([a["state"] for a in alerts]).value_counts().to_dict() if alerts else {},
               rejected=len(rej), missed_fills_chase=sum(1 for x in rej if x.get("reason") == "chase"),
               start_equity=CFG["capital"], end_equity=round(book.s["equity"]))
    if not c.empty:
        res.update(net_pnl_rs=round(c.pnl_rs.sum()), costs_rs=round(c.cost_rs.sum()), win_pct=round((c.pnl_rs > 0).mean() * 100, 1),
                   avg_R=round(c.r_multiple.mean(), 3), stop_slippage_rs=round(c.stop_slippage_rs.sum()),
                   long_pnl_rs=round(c.loc[c.side == 1, "pnl_rs"].sum()), short_pnl_rs=round(c.loc[c.side == -1, "pnl_rs"].sum()),
                   by_instrument={k: round(v) for k, v in c.groupby("instrument").pnl_rs.sum().items()},
                   by_exit={k: int(v) for k, v in c.exit_reason.value_counts().items()})
        c.to_csv(out / f"{label}_trades.csv", index=False)
    if not curve.empty:
        curve.to_csv(out / f"{label}_equity.csv", index=False)
        dd = curve.equity / curve.equity.cummax() - 1
        res.update(max_dd_pct=round(dd.min() * 100, 1), return_pct=round((curve.equity.iloc[-1] / CFG["capital"] - 1) * 100, 1))
    pd.DataFrame(alerts).to_csv(out / f"{label}_alerts.csv", index=False)
    (out / f"{label}_summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def run_live():
    """Manual / scheduled paper run against Angel data. Telegram only if PAPER_TELEGRAM=1."""
    import sys
    sys.path.insert(0, str(ROOT))
    from angel import Angel, load_master
    import notify
    send = notify.send if os.getenv("PAPER_TELEGRAM") == "1" else None
    book = Book(ROOT / "state" / "paper_mcx_daily.json", ROOT / "state" / "paper_mcx_daily_log.jsonl")
    prov = AngelProvider(Angel(), load_master())
    eng = Engine(prov, book, send)
    marks = {}
    for n in CFG["instruments"]:
        try:
            d = prov.daily(n)
            if d is None or d.empty:
                book.log("ERROR", instrument=n, error="no data"); continue
            i = len(d) - 1
            day = str(d.at[i, "time"].date())
            if book.s["processed"].get(n) == day:                 # this candle was already processed: nothing to do
                book.log("SKIP", instrument=n, reason="candle already processed", day=day); continue
            book.s["processed"][n] = day
            eng.on_open(n, d, i); eng.on_bar(n, d, i)
            eng.evaluate(n, d, i, prov.contract(n, d.at[i, "time"]))
            marks[n] = d.at[i, "close"]
        except Exception as e:
            book.log("ERROR", instrument=n, error=f"{type(e).__name__}: {str(e)[:200]}")
    eng.end_of_day(marks)
    book.save()
    for a in eng.alerts:
        print(a["text"], "\n")


if __name__ == "__main__":
    run_live()
