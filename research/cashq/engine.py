"""Run a signal over every stock and collect the trade ledger."""
import numpy as np
import pandas as pd
from . import sim

COST = dict(delivery=0.00393, intraday=0.00163)   # eq_data.cost_frac (Angel One schedule + slippage 0.05 / 0.04 % per side)


def daily_trades(W, sig, rdist, side=1, R=2.0, max_bars=20, trail=None, cost=COST["delivery"], extra_slip=0.0):
    O, H, L, C = (W[x] for x in ("open", "high", "low", "close"))
    cols = sig.columns[sig.values.any(0)]
    idx = C.index
    zeros = np.zeros(len(idx), np.int64)
    out = []
    for k in cols:
        s = sig[k].values.astype(np.bool_)
        tr = trail[k].values.astype(float) if trail is not None else np.full(len(idx), np.nan)
        ei, xi, ep, xp, gr, cd = sim.run(O[k].values, H[k].values, L[k].values, C[k].values, s, side,
                                         rdist[k].values.astype(float), R, max_bars, tr, zeros, zeros, False, 0, 0)
        if len(ei):
            out.append(pd.DataFrame(dict(key=k, entry_time=idx[ei], exit_time=idx[xi], entry=ep, exit=xp, grossR=gr, code=cd,
                                         bars=xi - ei + 1, risk=rdist[k].values[ei - 1])))
    return _finish(out, side, cost + 2 * extra_slip)


def intraday_trades(frames, sigs, rdists, side, R, cost=COST["intraday"], last_entry=14 * 60 + 30, sq=15 * 60 + 15):
    out = []
    for k, d in frames.items():
        s = sigs[k]
        if not s.any():
            continue
        t = d["time"]
        day = (t.dt.normalize().values.astype("datetime64[D]").astype(np.int64))
        mins = (t.dt.hour * 60 + t.dt.minute).values.astype(np.int64)
        ei, xi, ep, xp, gr, cd = sim.run(d["open"].values, d["high"].values, d["low"].values, d["close"].values, s.astype(np.bool_),
                                         side, rdists[k].astype(float), R, 0, np.full(len(d), np.nan), day, mins, True, last_entry, sq)
        if len(ei):
            out.append(pd.DataFrame(dict(key=k, entry_time=t.values[ei], exit_time=t.values[xi], entry=ep, exit=xp, grossR=gr, code=cd,
                                         bars=xi - ei + 1, risk=rdists[k][ei - 1])))
    return _finish(out, side, cost)


def _finish(out, side, cost):
    if not out:
        return pd.DataFrame(columns=["key", "entry_time", "exit_time", "entry", "exit", "grossR", "code", "bars", "risk", "costR", "netR", "netpct"])
    T = pd.concat(out, ignore_index=True)
    T["entry_time"] = pd.to_datetime(T["entry_time"]); T["exit_time"] = pd.to_datetime(T["exit_time"])
    T["costR"] = cost * T["entry"] / T["risk"]
    T["netR"] = T["grossR"] - T["costR"]
    T["netpct"] = side * (T["exit"] - T["entry"]) / T["entry"] - cost
    return T.sort_values("entry_time").reset_index(drop=True)
