"""Attach signal-bar conditions to trades, and map higher-timeframe conditions onto lower-timeframe bars (causally)."""
import numpy as np
import pandas as pd
from . import runner as RN, data as D

TF_MIN = D.TF_MIN


def attach(T, tf, conds=None):
    """add c_<COND> columns (value on the signal bar) for every trade in T (one timeframe)."""
    parts = []
    for name, g in T.groupby("name"):
        F = RN.features(name, tf)
        ks = conds or list(F["COND"])
        g = g.copy()
        for k in ks:
            arr = F["COND"].get(k)
            g[f"c_{k}"] = np.asarray(arr, bool)[g.sig_i.values] if arr is not None else np.nan
        parts.append(g)
    return pd.concat(parts, ignore_index=False).sort_index()


def avail_time(F):
    """time at which each bar's values are known: bar start + bar length (daily: next calendar day 00:00)."""
    t = pd.to_datetime(F["time"])
    return t + (pd.Timedelta(days=1) if F["tf"] == "1d" else pd.Timedelta(minutes=TF_MIN[F["tf"]]))


def map_htf(F_ltf, F_htf, arr):
    """value of an HTF array at the last HTF bar COMPLETED by each LTF bar's close."""
    a = pd.DataFrame(dict(t=avail_time(F_htf), v=np.asarray(arr, float))).sort_values("t")
    q = pd.DataFrame(dict(t=avail_time(F_ltf))).reset_index()
    m = pd.merge_asof(q.sort_values("t"), a, on="t", direction="backward").sort_values("index")
    return m.v.values


def cond_lift(T, cond_cols, base_mask=None):
    """mean net R with / without each condition, per period (pooled trades)."""
    rows = []
    for c in cond_cols:
        x = T[c].astype(float)
        r = dict(condition=c[2:])
        for p in ("TRAIN", "VAL", "OOS"):
            g = T[T.period == p]; xc = g[c].astype(float)
            a, b = g.netR[xc == 1], g.netR[xc == 0]
            r[f"{p}_n_with"] = int(len(a)); r[f"{p}_R_with"] = round(float(a.mean()), 3) if len(a) else np.nan
            r[f"{p}_win_with"] = round(100 * float((a > 0).mean()), 1) if len(a) else np.nan
            r[f"{p}_R_without"] = round(float(b.mean()), 3) if len(b) else np.nan
            r[f"{p}_lift"] = round(r[f"{p}_R_with"] - r[f"{p}_R_without"], 3) if len(a) and len(b) else np.nan
        r["lift_positive_all3"] = bool(all((r[f"{p}_lift"] or 0) > 0 for p in ("TRAIN", "VAL", "OOS")))
        rows.append(r)
    return pd.DataFrame(rows)
