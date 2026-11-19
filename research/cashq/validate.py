"""Metrics, splits, gates. R = profit / initial risk; costs in R = cost_frac × entry / risk."""
import numpy as np
import pandas as pd

DAILY_SPLITS = dict(DEV=("2005-01-01", "2014-12-31"), VALID=("2015-01-01", "2019-12-31"), OOS=("2020-01-01", "2026-12-31"))
INTRA_SPLITS = dict(DEV=("2024-10-01", "2025-09-30"), VALID=("2025-10-01", "2026-03-31"), OOS=("2026-04-01", "2026-12-31"))


def metrics(T):
    """T: trades with columns netR, entry_time, exit_time, key, bars."""
    if T is None or not len(T):
        return dict(n=0)
    r = T["netR"].values
    eq = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq)) if len(eq) else 0.0
    loss = r < 0
    mx = cur = 0
    for x in loss:
        cur = cur + 1 if x else 0; mx = max(mx, cur)
    w, lo = r[r > 0].sum(), -r[r < 0].sum()
    by_day = T.groupby(T["entry_time"].dt.normalize())["netR"].sum()
    rng = np.random.default_rng(7)
    if len(by_day) >= 10:                               # day-block bootstrap of the mean R per trade
        days = by_day.index.values
        cnt = T.groupby(T["entry_time"].dt.normalize()).size().reindex(days).values
        tot = by_day.values
        bs = []
        for _ in range(400):
            i = rng.integers(0, len(days), len(days))
            bs.append(tot[i].sum() / max(cnt[i].sum(), 1))
        lo95, hi95 = np.percentile(bs, [2.5, 97.5])
    else:
        lo95 = hi95 = np.nan
    top = T.groupby("key")["netR"].sum().sort_values(ascending=False)
    pos = top[top > 0].sum()
    return dict(n=len(r), win=round(100 * (r > 0).mean(), 1), avgR=round(r.mean(), 3), grossR=round(T["grossR"].mean(), 3),
                costR=round(T["costR"].mean(), 3), pct=round(100 * T["netpct"].mean(), 3), PF=round(w / lo, 2) if lo > 0 else np.inf,
                maxDD_R=round(dd, 1), max_consec_loss=int(mx), hold=round(T["bars"].mean(), 1),
                lo95=round(lo95, 3), hi95=round(hi95, 3), stocks=int(T["key"].nunique()),
                top5_share=round(top.head(5).clip(lower=0).sum() / pos, 2) if pos > 0 else np.nan,
                per_day=round(len(r) / max(T["entry_time"].dt.normalize().nunique(), 1), 2))


def split(T, splits):
    return {k: T[(T["entry_time"] >= a) & (T["entry_time"] <= b + " 23:59")] for k, (a, b) in splits.items()}


def bh(p):
    p = np.asarray(p, float); m = len(p)
    if m == 0:
        return p
    o = np.argsort(p); q = np.empty(m)
    q[o] = np.minimum.accumulate((p[o] * m / np.arange(1, m + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def verdict(row, min_oos=100):
    """Protocol: a variant is SELECTED only on DEV + VALID (both positive after costs, VALID PF >= 1.1, n >= 50 each);
    the untouched OOS then decides: PASS needs OOS n >= 100, avgR > 0 with bootstrap lower bound > 0, PF >= 1.30,
    top-5 stocks < 50 % of the profit, q < 0.10 among the selected, and >= 60 calendar days of OOS."""
    if not (row.get("DEV_n", 0) >= 50 and row.get("VALID_n", 0) >= 50 and row.get("DEV_avgR", -1) > 0 and row.get("VALID_avgR", -1) > 0
            and row.get("VALID_PF", 0) >= 1.1):
        return "NOT_SELECTED"
    if row.get("OOS_n", 0) < min_oos:
        return "INSUFFICIENT_EVIDENCE"
    ok = (row["OOS_avgR"] > 0 and row["OOS_lo95"] > 0 and row["OOS_PF"] >= 1.3 and (row["OOS_top5_share"] < 0.5)
          and row.get("OOS_q", 1) < 0.10)
    return "PASS" if ok else "FAIL_OOS"
