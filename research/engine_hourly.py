"""Hourly backtest of strategy A (= live Engine C rules in mcx_trade.py), research only.

Signal on a CLOSED 1-hour bar -> entry at the next bar's open (skipped if that open already ran more than
0.5 ATR past the signal close, as the live engine does). Stop/targets checked on each later bar's high/low;
stop assumed first when a bar touches both. T1 = 1R books half and moves the stop to cost, T2 = 2R.
Everything is closed at the session's square-off time. Same-day only (intraday), like the live engine.
"""
import numpy as np
import pandas as pd
from research.instruments import REGISTRY, trade_cost_points, mcx_ref_price

SESS = {"MCX": dict(first="10:00", last="22:00", exit="22:30", open="09:00", close="23:30"),
        "NSE": dict(first="10:15", last="14:30", exit="15:15", open="09:15", close="15:30")}
BASE = dict(fast=20, slow=50, trend=200, min_adx=20, brk=5, rsi_buy=(55, 75), rsi_sell=(25, 45), vol_x=1.2,
            sl_atr=(1.0, 2.0), t1=1.0, t2=2.0, chase=0.5, spike=2.5, max_day=2)


def hm(s):
    h, m = map(int, s.split(":")); return h * 60 + m


def session_bars(d, exch):
    s = SESS[exch]
    m = d["time"].dt.hour * 60 + d["time"].dt.minute
    return d[(m >= hm(s["open"])) & (m < hm(s["close"]))].reset_index(drop=True)


def indicators(d, p):
    d = d.copy(); c, h, l = d["close"], d["high"], d["low"]
    ema = lambda x, n: x.ewm(span=n, adjust=False).mean()
    d["e1"], d["e2"], d["e3"] = ema(c, p["fast"]), ema(c, p["slow"]), ema(c, p["trend"])
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    up, dn = h.diff(), -l.diff()
    pdm, ndm = up.where((up > dn) & (up > 0), 0.0), dn.where((dn > up) & (dn > 0), 0.0)
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr
    ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False).mean() / atr
    d["adx"] = (100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)).ewm(alpha=1 / 14, adjust=False).mean()
    dd = c.diff()
    u, v = dd.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(), (-dd.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + u / v.replace(0, 1e-9))
    n = p["brk"]
    d["hh"], d["ll"] = h.shift(1).rolling(n).max(), l.shift(1).rolling(n).min()
    d["swl"], d["swh"] = l.rolling(n).min(), h.rolling(n).max()
    avg = d["volume"].shift(1).rolling(20).mean()
    d["volx"] = np.where(avg > 0, d["volume"] / avg, np.nan)
    return d


def signals(d, p):
    base = (d["adx"] >= p["min_adx"]) & ((d["high"] - d["low"]) <= p["spike"] * d["atr"]) & \
        (d["volx"].isna() | (d["volx"] >= p["vol_x"]))
    c = d["close"]
    buy = base & (c > d["e1"]) & (d["e1"] > d["e2"]) & (c > d["e3"]) & (c > d["hh"]) & d["rsi"].between(*p["rsi_buy"])
    sell = base & (c < d["e1"]) & (d["e1"] < d["e2"]) & (c < d["e3"]) & (c < d["ll"]) & d["rsi"].between(*p["rsi_sell"])
    s = np.where(buy, 1, np.where(sell, -1, 0)); s[: p["trend"] + 5] = 0
    return s


def run(name, raw, overrides=None, cost_x=1.0):
    r = REGISTRY[name]; exch = r["exchange"]; S = SESS[exch]
    p = {**BASE, **(overrides or {})}
    d = indicators(session_bars(raw, exch), p)
    s = signals(d, p)
    t = d["time"]; mins = (t.dt.hour * 60 + t.dt.minute).values; day = t.dt.normalize().values
    O, H, L, C, A = (d[k].values for k in ("open", "high", "low", "close", "atr"))
    bar = int(np.median(np.diff(mins)[np.diff(mins) > 0])) if len(d) > 2 else 60
    out, per_day, i, n = [], {}, 0, len(d)
    while i < n - 1:
        side = s[i]; end = mins[i] + bar
        if side == 0 or not (hm(S["first"]) <= end <= hm(S["last"])) or per_day.get(day[i], 0) >= p["max_day"]:
            i += 1; continue
        j = i + 1
        if day[j] != day[i] or side * (O[j] - C[i]) > p["chase"] * A[i]:
            i += 1; continue
        e = O[j]
        swing = (d["swl"].values[i] - 0.2 * A[i]) if side > 0 else (d["swh"].values[i] + 0.2 * A[i])
        R = min(max(abs(e - swing), p["sl_atr"][0] * A[i]), p["sl_atr"][1] * A[i])
        sl, t1, t2 = e - side * R, e + side * p["t1"] * R, e + side * p["t2"] * R
        per_day[day[i]] = per_day.get(day[i], 0) + 1
        got1, booked, k, x, why, mae, mfe = False, 0.0, j, None, None, 0.0, 0.0
        while k < n and day[k] == day[i]:
            if mins[k] >= hm(S["exit"]):
                x, why = O[k], "time"; break
            hi_, lo_ = H[k], L[k]
            mae = min(mae, side * ((lo_ if side > 0 else hi_) - e)); mfe = max(mfe, side * ((hi_ if side > 0 else lo_) - e))
            if side * ((lo_ if side > 0 else hi_) - sl) <= 0:
                x, why = sl, "cost_exit" if got1 else "stop"; break
            if not got1 and side * ((hi_ if side > 0 else lo_) - t1) >= 0:
                got1, booked, sl = True, 0.5 * p["t1"], e
            if side * ((hi_ if side > 0 else lo_) - t2) >= 0:
                x, why = t2, "t2"; break
            k += 1
        else:
            k -= 1; x, why = C[k], "time"
        rest = 0.5 if got1 else 1.0
        gross_R = booked + rest * side * (x - e) / R
        cpts = trade_cost_points(name, e, r["kind"] == "commodity", cost_x) * (1.5 if got1 else 1.0)    # half booked at T1 = one extra exit order
        out.append(dict(instrument=name, signal_time=t[i], entry_time=t[j], exit_time=t[k],
                        side="LONG" if side > 0 else "SHORT", entry_px=e, exit_px=x, stop_px=e - side * R, R_pts=R,
                        cost_pts=cpts, gross_R=gross_R, net_R=gross_R - cpts / R, mae_R=mae / R, mfe_R=mfe / R,
                        exit_reason=why, days=1, adx=d["adx"].values[i], rolls=0))
        i = k + 1
    t = pd.DataFrame(out)
    if not t.empty:
        proxy_c = r["kind"] == "commodity"                     # commodity hourly data is always a proxy here
        t["pt_scale"] = (mcx_ref_price(name) / t["entry_px"].abs()) if proxy_c else 1.0
        t["net_pts"] = t["net_R"] * t["R_pts"]; t["pnl_rs_1lot"] = t["net_pts"] * t["pt_scale"] * r["mult"]
        t["cost_rs_1lot"] = t["cost_pts"] * t["pt_scale"] * r["mult"]
    return t
