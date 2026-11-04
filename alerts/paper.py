"""PAPER-ONLY strategies (4-Nov-2026). A paper strategy is recorded and tracked like a trade, but it is NEVER sent:
this module has no access to the Telegram message list, and alerts/run.py drops (and reports) any outgoing message that
carries the PAPER_ONLY marker. Paper results live in state["paper"], separate from the live ledger (state["ledger"]).

E_BUY_v1 – compression breakout BUY (research RSIFAM-001, family E, BUY side). Rules FROZEN; a copy with the periods
already examined is in docs/strategies/E_BUY_v1.md. Any rule change = a new version id, never an edit of this one.

  Signal (completed MCX 1-hour candle i):
    ATR14 < 0.8 x its 100-candle median on each of candles i-4..i (volatility contraction)
    close[i] > highest high of the 20 candles before i
    volume[i] >= 1.5 x average volume of the 20 candles before i (contracts without valid volume are skipped)
    RSI14[i] >= 60
  Trade (hypothetical): entry = open of candle i+1; stop = close[i] - 1.5 x ATR14[i]; R = entry - stop (must be > 0 and
    <= 6 ATR); T1 = entry + 1R (half closed, stop moves to entry); T2 = entry + 2R (rest closed); time stop after 30
    candles at the close. A candle touching stop and a target counts as stop (stop first). Costs 0.04 % of entry
    price per round trip, in R. One open paper trade per commodity. MFE / MAE from candle highs / lows (not ticks).
"""
import math
import numpy as np
import pandas as pd

from paperguard import MARKER as PAPER_ONLY   # every Telegram sender refuses text containing this marker
STRATEGY = "E_BUY_v1"
COST_PCT = 0.04
MAX_BARS = 30
KEEP_CLOSED = 400


def _rma(x, n):
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def features(h1):
    """Indicators on completed 1-hour candles (roll-adjusted). Returns DataFrame aligned to h1."""
    c, h, l, v = (h1[k].astype(float) for k in ("close", "high", "low", "volume"))
    d = c.diff()
    rsi = 100 - 100 / (1 + _rma(d.clip(lower=0), 14) / _rma((-d).clip(lower=0), 14).replace(0, np.nan))
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = _rma(tr, 14)
    med = atr.rolling(100, min_periods=50).median()
    quiet = (atr < 0.8 * med).astype(float).rolling(5).min() == 1
    return pd.DataFrame(dict(rsi=rsi, atr=atr, quiet=quiet, hh20=h.rolling(20).max().shift(1),
                             vavg=v.rolling(20).mean().shift(1), vol=v))


def check_signal(h1):
    """-> dict(signal fields) when the LAST completed candle triggers E_BUY_v1, else dict(reason=...)."""
    if h1 is None or len(h1) < 130:
        return dict(reason="not enough completed 1-hour candles")
    f = features(h1)
    i = len(h1) - 1
    x = f.iloc[i]
    if not (math.isfinite(x.vavg) and x.vavg > 0 and math.isfinite(x.vol)):
        return dict(reason="volume not valid – rule cannot be checked")
    if not bool(x.quiet):
        return dict(reason="no volatility contraction")
    c = float(h1["close"].iloc[i])
    if not c > x.hh20:
        return dict(reason="no close above the 20-candle high")
    if x.vol < 1.5 * x.vavg:
        return dict(reason=f"volume {x.vol / x.vavg:.1f}x < 1.5x")
    if not x.rsi >= 60:
        return dict(reason=f"RSI {x.rsi:.0f} < 60")
    return dict(signal=True, candle=str(h1["time"].iloc[i]), close=c, atr=float(x.atr), stop=c - 1.5 * float(x.atr),
                vol_x=round(float(x.vol / x.vavg), 2), rsi=round(float(x.rsi), 1))


def _book(state):
    p = state.setdefault("paper", {})
    b = p.setdefault(STRATEGY, {"pending": [], "open": [], "closed": [], "seen": []})
    return b


def on_candles(state, name, ex, contract, h1, now, grade_fields=None, data_ok=True):
    """Called once per scan with this commodity's completed, roll-adjusted 1-hour candles. Records new paper signals,
    fills pending ones at the next candle's open and walks open ones forward. Returns a short status string.
    NOTE: no message list parameter on purpose – paper trades cannot be sent from here."""
    if ex != "MCX" or h1 is None or len(h1) == 0:
        return "n/a"
    b = _book(state)
    h1 = h1.reset_index(drop=True)
    times = h1["time"].astype(str).tolist()
    out = []
    # 1) pending -> open at the first candle after the signal candle
    for p in list(b["pending"]):
        if p["name"] != name:
            continue
        later = [k for k, t in enumerate(times) if t > p["candle"]]
        if not later:
            continue
        k = later[0]
        e = float(h1["open"].iloc[k])
        R = e - p["stop"]
        b["pending"].remove(p)
        if not (R > 0 and R <= 6 * p["atr"]):
            p.update(status="VOID", note=f"entry {e:g} leaves risk {R:g} outside (0, 6 ATR]", closed=str(now))
            b["closed"] = (b["closed"] + [p])[-KEEP_CLOSED:]; out.append("voided"); continue
        p.update(status="ACTIVE", entry=e, entry_time=times[k], R=R, t1=e + R, t2=e + 2 * R, cur_stop=p["stop"], half=False,
                 mfe_px=e, mae_px=e, bars=0, last=times[k], t1_hit=False, t2_hit=False, stop_hit=False)
        b["open"].append(p); out.append("filled")
        _walk(b, p, h1, k, now, include_entry_bar=True)
    # 2) walk open trades over new candles
    for p in list(b["open"]):
        if p["name"] != name or p.get("status") != "ACTIVE":
            continue
        start = [k for k, t in enumerate(times) if t > p["last"]]
        if start:
            _walk(b, p, h1, start[0], now)
    # 3) new signal on the last completed candle
    if not any(q["name"] == name for q in b["open"] + b["pending"]):
        s = check_signal(h1)
        if s.get("signal"):
            sid = f"{STRATEGY}|{name}|{s['candle']}"
            if sid not in b["seen"]:
                b["seen"] = (b["seen"] + [sid])[-500:]
                rec = dict(id=sid, strategy=STRATEGY, status="PENDING", mode=PAPER_ONLY, name=name, ex=ex, contract=contract,
                           tf="1h", side="BUY", candle=s["candle"], signal_close=s["close"], atr=s["atr"], stop=s["stop"],
                           vol_x=s["vol_x"], rsi=s["rsi"], recorded=str(now), data_ok=bool(data_ok),
                           measure="1-hour candle highs/lows", **(grade_fields or {}))
                b["pending"].append(rec); out.append("signal")
                print(f"[paper] {STRATEGY} {name} BUY signal on {s['candle']} close {s['close']:g} stop {s['stop']:g} "
                      f"(vol {s['vol_x']}x, RSI {s['rsi']}) – {PAPER_ONLY}, not sent")
        else:
            out.append(s.get("reason", "no signal"))
    return "; ".join(out) or "tracking"


def _walk(b, p, h1, k0, now, include_entry_bar=False):
    """Advance one ACTIVE paper trade over candles k0.. (stop first, half at T1 then stop to entry, T2, time stop)."""
    e, R = p["entry"], p["R"]
    cost = COST_PCT / 100 * e / R
    for k in range(k0, len(h1)):
        hi, lo, op, cl = (float(h1[c_].iloc[k]) for c_ in ("high", "low", "open", "close"))
        t = str(h1["time"].iloc[k])
        p["bars"] += 1; p["last"] = t
        p["mfe_px"] = max(p["mfe_px"], hi); p["mae_px"] = min(p["mae_px"], lo)
        if lo <= p["cur_stop"]:
            px = op if (op < p["cur_stop"] and not (include_entry_bar and k == k0)) else p["cur_stop"]
            r = (0.5 * 1.0 + 0.5 * (px - e) / R) if p["half"] else (px - e) / R
            p["stop_hit"] = not p["half"]
            return _close(b, p, t, px, r - cost, "stop" if not p["half"] else "breakeven stop after T1")
        if not p["half"] and hi >= p["t1"]:
            p["half"] = True; p["t1_hit"] = True; p["cur_stop"] = e
        if p["half"] and hi >= p["t2"]:
            p["t2_hit"] = True
            return _close(b, p, t, p["t2"], 0.5 * 1.0 + 0.5 * 2.0 - cost, "T2")
        if p["bars"] >= MAX_BARS:
            r = (0.5 + 0.5 * (cl - e) / R) if p["half"] else (cl - e) / R
            return _close(b, p, t, cl, r - cost, "time stop")
    p["mfe_R"] = round((p["mfe_px"] - e) / R, 3); p["mae_R"] = round((p["mae_px"] - e) / R, 3)


def _close(b, p, t, px, r, why):
    e, R = p["entry"], p["R"]
    p.update(status="CLOSED", exit=px, exit_time=t, exit_reason=why, net_R=round(r, 3),
             mfe_R=round((p["mfe_px"] - e) / R, 3), mae_R=round((p["mae_px"] - e) / R, 3))
    b["open"].remove(p)
    b["closed"] = (b["closed"] + [p])[-KEEP_CLOSED:]
    print(f"[paper] {p['strategy']} {p['name']} closed: {why} · net {p['net_R']:+.2f}R · MFE {p['mfe_R']:+.2f}R MAE {p['mae_R']:+.2f}R")


def summary(state, strategy=STRATEGY):
    b = (state.get("paper") or {}).get(strategy) or {}
    cl = [x for x in b.get("closed", []) if x.get("status") == "CLOSED"]
    r = np.array([x["net_R"] for x in cl], float)
    return dict(strategy=strategy, mode=PAPER_ONLY, closed=len(cl), open=len(b.get("open", [])), pending=len(b.get("pending", [])),
                t1_hit=float(np.mean([x["t1_hit"] for x in cl])) if cl else None,
                profitable=float((r > 0).mean()) if len(r) else None, exp_R=float(r.mean()) if len(r) else None,
                pf=float(r[r > 0].sum() / -r[r < 0].sum()) if len(r) and (r < 0).any() else None)


def guard_outbox(msgs):
    """Hard guard: drop any outgoing message that carries the PAPER_ONLY marker. Returns (clean, dropped)."""
    clean, dropped = [], []
    for m in msgs:
        (dropped if PAPER_ONLY in str(m) else clean).append(m)
    return clean, dropped
