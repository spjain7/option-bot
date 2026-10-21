"""Backtest of Engine C (mcx_trade.py) on 1-hour commodity futures.
Data: backtest/data/<NAME>.csv (hourly, IST). International futures are used as a proxy for MCX
(MCX = international price x USD/INR), restricted to MCX session hours.
Results are in R (1R = the trade's stop-loss distance), so currency doesn't matter."""
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = Path(__file__).parent / "data"

BASE = dict(ema_fast=20, ema_slow=50, ema_trend=200, min_adx=20, brk=5, rsi_buy=(55, 75), rsi_sell=(25, 45),
            vol_x=1.2, sl_atr=(1.0, 2.0), t1_r=1.0, t2_r=2.0, chase_atr=0.5, first="10:00", last="22:00",
            exit="22:30", max_day=2, cost_pct=0.03, spike_atr=2.5, book_half=True, sides=("BUY", "SELL"),
            trail_atr=None, adx_max=None, carry=False, max_bars=80)


def load(name):
    d = pd.read_csv(DATA / f"{name}.csv", index_col=0, parse_dates=True)
    t = d.index
    mins = t.hour * 60 + t.minute
    d = d[(mins >= 9 * 60) & (mins + 60 <= 23 * 60 + 30)]          # MCX session bars only
    return d.reset_index().rename(columns={d.index.name or "index": "time", "Datetime": "time"})


def indicators(d, p):
    c, h, l = d["close"], d["high"], d["low"]
    ema = lambda s, n: s.ewm(span=n, adjust=False).mean()
    d["e20"], d["e50"], d["e200"] = ema(c, p["ema_fast"]), ema(c, p["ema_slow"]), ema(c, p["ema_trend"])
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    up, dn = h.diff(), -l.diff()
    pdm, ndm = up.where((up > dn) & (up > 0), 0.0), dn.where((dn > up) & (dn > 0), 0.0)
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr
    ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False).mean() / atr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    d["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean()
    dd = c.diff()
    u = dd.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    v = (-dd.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + u / v.replace(0, 1e-9))
    d["atr"] = atr
    n = p["brk"]
    d["hh"], d["ll"] = h.shift(1).rolling(n).max(), l.shift(1).rolling(n).min()
    d["swl"], d["swh"] = l.rolling(n).min(), h.rolling(n).max()
    avg = d["volume"].shift(1).rolling(20).mean()
    d["volx"] = np.where(avg > 0, d["volume"] / avg, np.nan)
    d["rng"] = h - l
    return d


def signals(d, p):
    base = (d["adx"] >= p["min_adx"]) & (d["rng"] <= p["spike_atr"] * d["atr"]) & \
           (d["volx"].isna() | (d["volx"] >= p["vol_x"]))
    if p["adx_max"]:
        base &= d["adx"] <= p["adx_max"]
    c = d["close"]
    buy = base & (c > d["e20"]) & (d["e20"] > d["e50"]) & (c > d["e200"]) & (c > d["hh"]) & \
        d["rsi"].between(*p["rsi_buy"])
    sell = base & (c < d["e20"]) & (d["e20"] < d["e50"]) & (c < d["e200"]) & (c < d["ll"]) & \
        d["rsi"].between(*p["rsi_sell"])
    s = np.where(buy, 1, np.where(sell, -1, 0))
    s[: p["ema_trend"] + 5] = 0
    return s


def hm(s):
    h, m = map(int, s.split(":")); return h * 60 + m


def run(name, p=None, d=None):
    p = {**BASE, **(p or {})}
    d = indicators(load(name) if d is None else d.copy(), p)
    sig = signals(d, p)
    t = d["time"]; mins = (t.dt.hour * 60 + t.dt.minute).values; day = t.dt.normalize().values
    O, H, L, Cl, A = (d[k].values for k in ("open", "high", "low", "close", "atr"))
    trades, i, n = [], 0, len(d)
    per_day = {}
    while i < n - 1:
        s = sig[i]
        end = mins[i] + 60
        if s == 0 or not (hm(p["first"]) <= end <= hm(p["last"])) or \
                ("BUY" if s > 0 else "SELL") not in p["sides"] or per_day.get(day[i], 0) >= p["max_day"]:
            i += 1; continue
        j = i + 1
        if day[j] != day[i]:
            i += 1; continue
        entry = O[j]
        if s * (entry - Cl[i]) > p["chase_atr"] * A[i]:
            i += 1; continue
        lo, hi = p["sl_atr"]
        swing = (d["swl"].values[i] - 0.2 * A[i]) if s > 0 else (d["swh"].values[i] + 0.2 * A[i])
        R = min(max(abs(entry - swing), lo * A[i]), hi * A[i])
        sl, t1, t2 = entry - s * R, entry + s * p["t1_r"] * R, entry + s * p["t2_r"] * R
        per_day[day[i]] = per_day.get(day[i], 0) + 1
        got1, booked, k, res, reason = False, 0.0, j, None, None
        best = entry
        while k < n and (p["carry"] or day[k] == day[i]):
            if (not p["carry"] and mins[k] >= hm(p["exit"])) or (p["carry"] and k - j >= p["max_bars"]):
                res, reason = O[k], "time"; break
            hi_, lo_ = H[k], L[k]
            if s * ((lo_ if s > 0 else hi_) - sl) <= 0:                 # stop first (conservative)
                res, reason = sl, "be" if got1 else "sl"; break
            if not got1 and s * ((hi_ if s > 0 else lo_) - t1) >= 0:
                got1 = True
                if p["book_half"]:
                    booked = 0.5 * s * (t1 - entry) / R
                sl = entry
            if s * ((hi_ if s > 0 else lo_) - t2) >= 0:
                res, reason = t2, "t2"; break
            if p["trail_atr"] and got1:
                best = max(best, hi_) if s > 0 else min(best, lo_)
                sl = max(sl, best - p["trail_atr"] * A[k]) if s > 0 else min(sl, best + p["trail_atr"] * A[k])
            k += 1
        else:
            k -= 1; res, reason = Cl[k], "time"
        rest = 0.5 if (got1 and p["book_half"]) else 1.0
        r = booked + rest * s * (res - entry) / R
        r -= p["cost_pct"] / 100 * 2 * entry / R                           # costs + slippage, both sides
        trades.append(dict(name=name, time=t[i], side="BUY" if s > 0 else "SELL", entry=entry, R_pts=R,
                           exit=res, reason=reason, r=r, hour=mins[i] // 60 + 1))
        i = k + 1 if k > i else i + 1
    return pd.DataFrame(trades)


def stats(tr):
    if tr.empty:
        return dict(trades=0)
    r = tr["r"]
    eq = r.cumsum(); dd = (eq - eq.cummax()).min()
    w, l = r[r > 0], r[r <= 0]
    months = max((tr["time"].max() - tr["time"].min()).days / 30.4, 1)
    return dict(trades=len(r), per_month=round(len(r) / months, 1), win=round((r > 0).mean() * 100),
                avg_r=round(r.mean(), 3), total_r=round(r.sum(), 1),
                pf=round(w.sum() / -l.sum(), 2) if l.sum() else np.inf, max_dd_r=round(dd, 1))


NAMES = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ALUMINIUM"]

if __name__ == "__main__":
    allt = pd.concat([run(n) for n in NAMES])
    print(pd.DataFrame({n: stats(allt[allt.name == n]) for n in NAMES} | {"ALL": stats(allt)}).T)
