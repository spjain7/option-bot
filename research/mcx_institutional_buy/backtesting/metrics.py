"""Performance metrics on a trade list (columns: name, entry, exit_t, netR, mfeR, maeR, bars)."""
import numpy as np
import pandas as pd
from scipy import stats as SS


def max_consec_losses(r):
    k = m = 0
    for x in r:
        k = k + 1 if x <= 0 else 0; m = max(m, k)
    return m


def summary(T):
    r = T.netR.values if len(T) else np.array([])
    if len(r) == 0:
        return dict(n=0)
    w = r > 0
    seq = T.sort_values("exit_t").netR.values
    eq = np.cumsum(seq); dd = float((np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max())
    dm = T.groupby(pd.to_datetime(T.entry).dt.normalize()).netR.mean()
    tday = float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm)))) if len(dm) > 2 and dm.std(ddof=1) > 0 else np.nan
    return dict(n=int(len(r)), win=round(100 * w.mean(), 1), R=round(float(r.mean()), 3),
                PF=round(float(r[w].sum() / -r[~w].sum()), 2) if (~w).any() and w.any() else (np.inf if w.all() else 0.0),
                maxDD_R=round(dd, 1), avg_win=round(float(r[w].mean()), 2) if w.any() else np.nan,
                avg_loss=round(float(r[~w].mean()), 2) if (~w).any() else np.nan, mfe=round(float(T.mfeR.mean()), 2),
                mae=round(float(T.maeR.mean()), 2), hold=round(float(T.bars.mean()), 1), max_consec_loss=max_consec_losses(seq),
                t_day=round(tday, 2) if np.isfinite(tday) else np.nan)


def p_from_t(t, df=60):
    return float(2 * SS.t.sf(abs(t), df)) if np.isfinite(t) else np.nan


def bh(p, q=0.10):
    p = np.asarray(p, float); ok = np.isfinite(p); out = np.zeros(len(p), bool)
    if ok.sum() == 0:
        return out
    ps = p[ok]; o = np.argsort(ps); m = len(ps)
    thr = q * np.arange(1, m + 1) / m; passed = ps[o] <= thr
    k = np.where(passed)[0].max() + 1 if passed.any() else 0
    sel = np.zeros(m, bool); sel[o[:k]] = True; out[np.where(ok)[0]] = sel
    return out


def bootstrap_ci(r, n=2000, seed=7, block_days=None):
    r = np.asarray(r, float)
    if len(r) < 5:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed); m = rng.choice(r, (n, len(r)), replace=True).mean(axis=1)
    return (round(float(np.percentile(m, 2.5)), 3), round(float(np.percentile(m, 97.5)), 3))
