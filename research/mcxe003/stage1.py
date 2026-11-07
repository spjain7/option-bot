"""MCXE-003 stage-1 analysis of the event files (results/events/<market>/*.parquet).

Cell = market x inst x tf x fam x name x side x sw.  Measure = x_fe6 (excess vs the time-of-day x quarter control, from
the executable next open, 6 bars, ATR units). Statistics: event-weighted mean with a DAY-CLUSTERED standard error (see clustered()). One-sided p (excess > 0) on DEV, BH-FDR over all testable cells (n_days DEV >= 40) of the
market. Then the pre-registered labels (failure_analysis.label).

Family-level view (answers "why"): per market x fam x name x side x tf pooled over instruments and swing methods,
day-clustered on CALENDAR days (cross-instrument correlation handled), DEV / VALID / OOS*, plus diagnostics:
  spent   = x_fd6 - x_fe6 (information lost between the signal close and the next open)
  cost    = median round-trip cost in ATR ;  raw = mean gross side-signed move (what a trade earns before costs)
  mfe/mae = median 12-bar favourable / adverse excursion (ATR)
  max-stat: 5,000 day sign-flips applied jointly to all family series of the market -> selection-adjusted p of each
            family's DEV t (the same flip for all families on a day keeps their correlation)
(*) OOS is reported only in the frozen stage-2 step; here OOS columns are written to disk but NOT used for any decision.
python research/mcxe003/stage1.py mcx|nse_eq|nse_fut
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe003 import failure_analysis as FA  # noqa: E402

OUT = ROOT / "research/mcxe003/results"
MK = {"mcx": "MCX", "nse_eq": "NSE_EQ", "nse_fut": "NSE_FUT"}
COLS = ["side", "fam", "name", "sw", "x_fe6", "x_fd6", "fe6", "cost_atr", "mfe", "mae", "day", "period", "inst", "tf"]


def load(market, cols=COLS):
    fs = sorted((OUT / "events" / market).glob("*.parquet"))
    E = pd.concat([pd.read_parquet(f, columns=cols) for f in fs], ignore_index=True)
    for c in ("fam", "name", "sw", "period", "inst"):
        if c in E:
            E[c] = E[c].astype("category")
    return E


def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    q = np.empty(n); q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def clustered(E, keys, val):
    """event-weighted mean of `val` per keys (+period) with a DAY-CLUSTERED (cluster-robust) standard error:
    m = sum / n over events ; se^2 = D/(D-1) * sum_d (s_d - n_d m)^2 / n^2 ; t = m / se ; nd = number of days.
    (7-Nov fix: the first version averaged per-day means, which changes the estimand – days with many events got the
    same weight as days with one; a trader taking every signal earns the event-weighted mean.)"""
    x = E[keys + ["period", "day", val]].dropna(subset=[val])
    d = x.groupby(keys + ["period", "day"], observed=True)[val].agg(["sum", "count"]).reset_index()
    g = d.groupby(keys + ["period"], observed=True)
    S = pd.DataFrame(dict(nd=g.size(), s=g["sum"].sum(), n=g["count"].sum()))
    S["m"] = S.s / S.n
    d = d.join(S.m, on=keys + ["period"])
    d["r2"] = (d["sum"] - d["count"] * d["m"]) ** 2
    v = d.groupby(keys + ["period"], observed=True).r2.sum()
    S["se"] = np.sqrt(v * S.nd / np.maximum(S.nd - 1, 1)) / S.n
    S["t"] = S.m / S.se
    return S[["nd", "m", "se", "t"]]


def cells(E):
    K = ["inst", "tf", "fam", "name", "side", "sw"]
    X = clustered(E, K, "x_fe6"); Fd = clustered(E, K, "x_fd6")
    n = E.groupby(K + ["period"], observed=True).size().rename("n")
    raw = E.groupby(K + ["period"], observed=True).fe6.mean().rename("raw")
    cost = E.groupby(K + ["period"], observed=True).cost_atr.median().rename("cost")
    T = pd.concat([X, Fd.t.rename("tfd"), n, raw, cost], axis=1).reset_index()
    W = T.pivot_table(index=K, columns="period", values=["nd", "m", "t", "tfd", "n", "raw", "cost"], observed=True)
    W.columns = [f"{a}_{b}" for a, b in W.columns]
    W = W.reset_index()
    for c in ("nd_DEV", "m_DEV", "t_DEV", "tfd_DEV", "m_VALID", "nd_VALID"):
        if c not in W:
            W[c] = np.nan
    W = W.rename(columns={"m_DEV": "x_DEV", "m_VALID": "x_VALID", "m_OOS": "x_OOS"})
    # raw / cost over DEV+VALID (event-weighted)
    dv = E[E.period.isin(["DEV", "VALID"])].groupby(K, observed=True).agg(raw_DV=("fe6", "mean"), cost_DV=("cost_atr", "median"))
    W = W.merge(dv.reset_index(), on=K, how="left")
    test = W.nd_DEV >= 40
    W["p_DEV"] = np.where(test, stats.t.sf(W.t_DEV.fillna(0), np.maximum(W.nd_DEV.fillna(2) - 1, 1)), np.nan)
    W["q_DEV"] = np.nan
    W.loc[test, "q_DEV"] = bh(W.loc[test, "p_DEV"].values)
    W["label"] = [FA.label(r) for r in W.itertuples(index=False)]
    return W


def families(E, nperm=5000, seed=20261107):
    K = ["fam", "name", "side", "tf"]
    X = clustered(E, K, "x_fe6"); Fd = clustered(E, K, "x_fd6")
    agg = E.groupby(K + ["period"], observed=True).agg(n=("x_fe6", "size"), raw=("fe6", "mean"), cost=("cost_atr", "median"),
                                                       mfe=("mfe", "median"), mae=("mae", "median"), insts=("inst", "nunique"))
    T = pd.concat([X, Fd.m.rename("x_fd"), agg], axis=1).reset_index()
    W = T.pivot_table(index=K, columns="period", values=["nd", "m", "t", "x_fd", "n", "raw", "cost", "mfe", "mae", "insts"], observed=True)
    W.columns = [f"{a}_{b}" for a, b in W.columns]
    W = W.reset_index()
    # joint day sign-flip max-stat on DEV, on day SUMS (event-weighted): T = sum_d s_d / sqrt(sum_d s_d^2)
    D = E[E.period == "DEV"].groupby(K + ["day"], observed=True).x_fe6.agg(["sum", "count"]).reset_index()
    D["key"] = D[K].astype(str).agg("|".join, axis=1)
    P = D.pivot_table(index="day", columns="key", values="sum", aggfunc="sum").fillna(0.0)
    nd = D.groupby("key").day.nunique().reindex(P.columns).values
    keys = list(P.columns); M0 = P.values
    den = np.sqrt((M0 ** 2).sum(0))
    t0 = M0.sum(0) / den
    rng = np.random.default_rng(seed); mx = np.empty(nperm)
    ok = nd >= 40
    for b in range(nperm):
        sg = rng.choice([-1.0, 1.0], size=(M0.shape[0], 1))
        tb = (M0 * sg).sum(0) / den
        mx[b] = np.max(np.where(ok, tb, -np.inf))
    adj = {k: (1 + (mx >= t).sum()) / (1 + nperm) if o else np.nan for k, t, o in zip(keys, t0, ok)}
    W["key"] = W[K].astype(str).agg("|".join, axis=1)
    W["maxstat_p_DEV"] = W.key.map(adj)
    W["maxstat_95"] = float(np.quantile(mx, 0.95))
    return W.drop(columns="key")


def context(E, cols):
    """excess by context bucket, DEV+VALID, per fam x side (pooled), day-clustered."""
    out = []
    X = E[E.period.isin(["DEV", "VALID"])]
    for c in cols:
        S = clustered(X.assign(period="DV"), ["fam", "side", c], "x_fe6").reset_index()
        S["ctx"] = c; S = S.rename(columns={c: "bucket"})
        out.append(S)
    return pd.concat(out, ignore_index=True)


def daily(market, horizon):
    """daily-bar horizons: horizon 'btst' (primary overnight: close -> next close; diagnostic column = gap part) or 'pos5'
    (entry next open -> close 5 sessions later; diagnostic = btst). Same cell / family / max-stat machinery."""
    E = pd.read_parquet(OUT / "events" / "daily" / f"{market}.parquet")
    diag = "gap" if horizon == "btst" else "btst"
    E = E.rename(columns={horizon: "fe6", "x_" + horizon: "x_fe6", "x_" + diag: "x_fd6"})
    E["tf"] = 1440
    E = E[["side", "fam", "name", "sw", "x_fe6", "x_fd6", "fe6", "cost_atr", "mfe", "mae", "day", "period", "inst", "tf"]]
    for c in ("fam", "name", "sw", "period", "inst"):
        E[c] = E[c].astype("category")
    tag = f"daily_{market}_{horizon}"
    print(tag, "events", len(E), flush=True)
    W = cells(E); W.to_csv(OUT / f"stage1_cells_{tag}.csv.gz", index=False)
    print(W.label.value_counts().to_string(), flush=True)
    F = families(E); F.to_csv(OUT / f"stage1_families_{tag}.csv", index=False)
    pd.set_option("display.width", 250)
    show = ["fam", "name", "side", "nd_DEV", "m_DEV", "t_DEV", "m_VALID", "t_VALID", "x_fd_DEV", "raw_DEV", "cost_DEV", "maxstat_p_DEV"]
    print(F[F.nd_DEV >= 40].sort_values("t_DEV", ascending=False)[show].head(25).round(3).to_string(index=False))
    print("maxstat95", F.maxstat_95.iat[0])


def main(which):
    if which.startswith("daily_"):
        _, mk, hz = which.split("_", 2) if which.count("_") == 2 else (None, None, None)
        mk, hz = which.split("_")[1].upper(), which.split("_")[-1]
        mk = {"NSEEQ": "NSE_EQ", "NSEFUT": "NSE_FUT", "MCX": "MCX"}[mk]
        return daily(mk, hz)
    mk = MK[which]
    E = load(mk)
    print(mk, "events", len(E), "cells", E.groupby(["inst", "tf", "fam", "name", "side", "sw"], observed=True).ngroups, flush=True)
    cf = OUT / f"stage1_cells_{which}.csv.gz"
    if cf.exists() and "--recells" not in sys.argv:
        W = pd.read_csv(cf)
    else:
        W = cells(E)
    W.to_csv(OUT / f"stage1_cells_{which}.csv.gz", index=False)
    print(W.label.value_counts().to_string(), flush=True)
    F = families(E)
    F.to_csv(OUT / f"stage1_families_{which}.csv", index=False)
    ctx_cols = ["c_trend", "c_ema", "c_dtrend", "c_vwap", "c_adx", "c_atr", "c_relvol", "c_sess", "c_imp", "c_day"]
    Ec = load(mk, ["side", "fam", "x_fe6", "day", "period"] + ctx_cols)
    C = context(Ec, ctx_cols)
    C.to_csv(OUT / f"stage1_context_{which}.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
    show = ["fam", "name", "side", "tf", "nd_DEV", "m_DEV", "t_DEV", "m_VALID", "t_VALID", "x_fd_DEV", "raw_DEV", "cost_DEV", "maxstat_p_DEV"]
    print(F.sort_values("t_DEV", ascending=False)[[c for c in show if c in F]].head(40).round(3).to_string(index=False))


if __name__ == "__main__":
    main((sys.argv[1:] or ["mcx"])[0])
