"""Dependence-aware confidence intervals for trade samples (MCXE-003 Addendum D).

Trades are first aggregated to TRADING-DATE clusters (sum of R and count per entry date), then resampled with a circular
MOVING-BLOCK bootstrap over the chronologically ordered dates (blocks of L consecutive dates), so both same-day
clustering and serial dependence between nearby dates are preserved. The statistic is the ratio estimator
mean R = sum(R) / sum(n) over the resampled clusters.

block_ci(dates, r, B=10000, L=None, seed)  -> dict with
  n trades, n_dates, L, mean, ci95 (percentile), se_boot, n_eff (Geyer initial-positive-sequence on the date-level
  series), t_ci95 (mean +- t_{n_eff-1} * cluster-robust se, a cross-check), small_sample flag (n_dates < 30) and
  sensitivity of the CI to L in {1, 2, 3, 5}.
L default = max(1, round(n_dates ** (1/3))) (standard rate for block length).
"""
import numpy as np
import pandas as pd
from scipy import stats


def _clusters(dates, r):
    d = pd.DataFrame(dict(d=pd.to_datetime(dates), r=np.asarray(r, float))).dropna()
    g = d.groupby("d").r.agg(["sum", "count"]).sort_index()
    return g["sum"].values, g["count"].values.astype(float)


def _mbb(S, N, L, B, rng):
    m = len(S)
    nb = int(np.ceil(m / L))
    starts = rng.integers(0, m, size=(B, nb))
    idx = (starts[:, :, None] + np.arange(L)[None, None, :]) % m          # circular blocks
    idx = idx.reshape(B, -1)[:, :m]
    return S[idx].sum(1) / N[idx].sum(1)


def n_eff(x):
    """effective sample size of a series (Geyer initial positive sequence of autocorrelations)."""
    x = np.asarray(x, float); n = len(x)
    if n < 4 or np.std(x) == 0:
        return float(n)
    xc = x - x.mean(); v = (xc ** 2).mean()
    rho = [1.0] + [float((xc[:-k] * xc[k:]).mean() / v) for k in range(1, n // 2)]
    s = 0.0
    for k in range(1, len(rho) - 1, 2):                                   # pairs Gamma_k = rho_k + rho_{k+1}
        gk = rho[k] + rho[k + 1]
        if gk <= 0:
            break
        s += gk
    return float(max(1.0, min(n, n / (1 + 2 * s))))


def block_ci(dates, r, B=10000, L=None, seed=20261107):
    S, N = _clusters(dates, r)
    m = len(S)
    out = dict(n=int(N.sum()), n_dates=int(m))
    if m == 0:
        return dict(out, mean=None, ci95=None, note="no trades")
    mean = float(S.sum() / N.sum())
    out["mean"] = round(mean, 4)
    if m < 2:
        return dict(out, ci95=None, note="one date: no interval")
    L0 = L or max(1, int(round(m ** (1 / 3))))
    rng = np.random.default_rng(seed)
    bs = _mbb(S, N, L0, B, rng)
    daym = S / N
    ne = n_eff(daym)
    se = float(np.sqrt(((S - N * mean) ** 2).sum() * m / max(m - 1, 1)) / N.sum())
    tq = stats.t.ppf(0.975, max(ne - 1, 1))
    sens = {}
    for Lk in (1, 2, 3, 5):
        if Lk <= m:
            b = _mbb(S, N, Lk, B, np.random.default_rng(seed + Lk))
            sens[Lk] = [round(float(np.percentile(b, 2.5)), 3), round(float(np.percentile(b, 97.5)), 3)]
    out.update(L=L0, ci95=[round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)],
               se_boot=round(float(bs.std()), 4), n_eff=round(ne, 1), se_cluster=round(se, 4),
               t_ci95=[round(mean - tq * se, 3), round(mean + tq * se, 3)],
               p_one_sided_t=round(float(stats.t.sf(mean / se, max(ne - 1, 1))) if se > 0 else np.nan, 4),
               ci_by_L=sens, small_sample=bool(m < 30),
               note=("fewer than 30 dates: percentile bootstrap intervals are too narrow in small samples; "
                     "decisions use ci95_conservative = the widest of the block-bootstrap (all L) and t intervals") if m < 30 else "")
    los = [out["ci95"][0], out["t_ci95"][0]] + [v[0] for v in sens.values()]
    his = [out["ci95"][1], out["t_ci95"][1]] + [v[1] for v in sens.values()]
    out["ci95_conservative"] = [round(float(min(los)), 3), round(float(max(his)), 3)]   # widest of all intervals
    out["t_ci95"] = [float(v) for v in out["t_ci95"]]
    return out
