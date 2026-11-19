"""ML-RANK-001 (19-Nov-2026, owner: "go deep into every repo, find what can work for us"). Idea taken from microsoft/qlib:
Alpha158-style price / volume factors, cross-sectionally ranked every day, a LightGBM model trained to predict the next-days
return RANKING, walk-forward (rolling 3-year window, refit every quarter, predictions only on the unseen next quarter).
Applied to the NSE F&O stocks (point-in-time F&O list 2018+, research/data/nse_fut_pit; prices = official cash bhavcopies,
back-adjusted; liquid universe ₹25 cr+), plus our own extra data: futures OI change, NSE delivery %.
TRADE TEST: every 5 sessions SELL the N stocks the model ranks WORST (and, separately, BUY the N best), entry next open, exit
at the close 5 sessions later; costs 0.14 % per trade (futures, ~2x statutory + slippage). Compared with (a) N random stocks
from the same universe and (b) a naive rule (SELL the weakest 20-day return / BUY the strongest).
python -m research.cashq.ml_rank -> results/ml_rank_trades.csv.gz, results/ml_rank_summary.csv, results/ml_rank_importance.csv"""
import glob
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D  # noqa: E402
from research.cashq.nse_bo_cash import fo_by_month  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
H, COST, START = 5, 0.0014, "2017-01-01"
WIN = (5, 10, 20, 60)


def load():
    W = D.daily_panel()
    sel = W["close"].index >= START
    P = {f: W[f].loc[sel].astype("float64") for f in ("open", "high", "low", "close", "volume", "value")}
    e = W["elig"].loc[sel].fillna(False)
    sym = W["symbol"]
    FO = fo_by_month(); fm = sorted(FO)
    mon = np.array([str(d)[:7] for d in P["close"].index])
    fo = np.zeros(P["close"].shape, bool); sy = sym.reindex(P["close"].columns).values
    for i, m in enumerate(mon):
        if m >= fm[0]:
            s = FO.get(m) or FO[max(x for x in fm if x <= m)]
            fo[i] = np.isin(sy, list(s))
    U = e & pd.DataFrame(fo, index=e.index, columns=e.columns)
    keep = U.columns[U.any()]
    P = {f: v[keep] for f, v in P.items()}; U = U[keep]; sym = sym[keep]
    mk = W["market"]["close"].loc[sel]
    return P, U, sym, mk


def side_data(P, sym):
    idx, cols = P["close"].index, P["close"].columns
    k_of = {s: k for k, s in sym.items()}
    # futures OI (sum of all expiries) per symbol and day
    rows = []
    for p in sorted(glob.glob(str(ROOT / "research/data/nse_fut_pit/days/*.csv.gz"))):
        d = pd.read_csv(p, usecols=["date", "symbol", "kind", "oi"])
        d = d[d.kind == "STK"].groupby("symbol").oi.sum().rename(pd.Timestamp(Path(p).name[:8]))
        rows.append(d)
    OI = pd.concat(rows, axis=1).T
    OI = OI.rename(columns=k_of)[[c for c in OI.columns.map(lambda s: k_of.get(s)) if c is not None]] if False else \
        OI[[s for s in OI.columns if s in k_of]].rename(columns=k_of)
    OI = OI.loc[:, ~OI.columns.duplicated()].reindex(index=idx, columns=cols)
    X = pd.concat([pd.read_parquet(p, columns=["date", "symbol", "deliv_pct"]) for p in sorted(glob.glob(str(ROOT / "research/data/nse_deliv/*.parquet")))
                   if int(Path(p).stem) >= int(START[:4])])
    X = X[X.symbol.isin(k_of)]; X["key"] = X.symbol.map(k_of)
    DP = X.pivot_table(index="date", columns="key", values="deliv_pct", aggfunc="last").reindex(index=idx, columns=cols)
    return OI, DP


def factors(P, OI, DP, mk):
    o, h, l, c, v = (P[x] for x in ("open", "high", "low", "close", "volume"))
    F = {}
    rg = (h - l).replace(0, np.nan)
    F["KMID"] = (c - o) / o; F["KLEN"] = (h - l) / o; F["KMID2"] = (c - o) / rg
    F["KUP2"] = (h - np.maximum(o, c)) / rg; F["KLOW2"] = (np.minimum(o, c) - l) / rg; F["KSFT2"] = (2 * c - h - l) / rg
    F["GAP"] = o / c.shift(1) - 1
    r1 = c / c.shift(1) - 1; lv = np.log(v + 1)
    for d in WIN:
        F[f"ROC{d}"] = c / c.shift(d) - 1
        F[f"MA{d}"] = c.rolling(d).mean() / c
        F[f"STD{d}"] = r1.rolling(d).std()
        F[f"MAX{d}"] = h.rolling(d).max() / c; F[f"MIN{d}"] = l.rolling(d).min() / c
        F[f"RSV{d}"] = (c - l.rolling(d).min()) / (h.rolling(d).max() - l.rolling(d).min()).replace(0, np.nan)
        F[f"CNTD{d}"] = (r1 > 0).astype(float).rolling(d).mean() - (r1 < 0).astype(float).rolling(d).mean()
        F[f"VMA{d}"] = v.rolling(d).mean() / (v + 1)
        F[f"VSTD{d}"] = lv.rolling(d).std()
        F[f"CORR{d}"] = c.rolling(d).corr(lv) if d >= 10 else None
    F = {k: x for k, x in F.items() if x is not None}
    F["ROC120"] = c / c.shift(120) - 1; F["ROC250"] = c / c.shift(250) - 1
    oi = OI.ffill(limit=2)
    F["OI1"] = oi / oi.shift(1) - 1; F["OI5"] = oi / oi.shift(5) - 1
    F["OIxP5"] = np.sign(F["ROC5"]) * F["OI5"]                 # + = build-up in the price direction
    F["DP"] = DP; F["DPX"] = DP / DP.rolling(20, min_periods=10).mean()
    mr = mk / mk.shift(20) - 1
    F["MKT20"] = pd.DataFrame(np.repeat(mr.values[:, None], c.shape[1], 1), index=c.index, columns=c.columns)
    F["MKTMA"] = pd.DataFrame(np.repeat((mk / mk.rolling(50).mean()).values[:, None], c.shape[1], 1), index=c.index, columns=c.columns)
    return F


def main():
    import lightgbm as lgb
    P, U, sym, mk = load()
    OI, DP = side_data(P, sym)
    F = factors(P, OI, DP, mk)
    c, o = P["close"], P["open"]
    fwd = c.shift(-H) / o.shift(-1) - 1                                   # next open -> close H sessions later
    names = list(F)
    print("factors", len(names), "stocks", c.shape[1], "days", c.shape[0], flush=True)
    stack = lambda df: df.where(U).stack(future_stack=True)
    base = stack(fwd).rename("fwd").to_frame()
    base = base[U.stack(future_stack=True).reindex(base.index).fillna(False).values]
    for n in names:
        x = F[n].where(U)
        base[n] = x.rank(axis=1, pct=True).stack(future_stack=True).reindex(base.index).astype("float32") if n not in ("MKT20", "MKTMA") else \
            x.stack(future_stack=True).reindex(base.index).astype("float32")
    base = base.reset_index().rename(columns={"level_0": "day", "level_1": "key"})
    base["day"] = pd.to_datetime(base["day"])
    base = base[base.day >= "2018-01-01"]
    base["y"] = base.groupby("day").fwd.rank(pct=True)                   # target: cross-sectional return rank
    days = np.sort(base.day.unique())
    qs = pd.date_range("2020-01-01", base.day.max(), freq="QS")
    pred = []
    for q0 in qs:
        q1 = q0 + pd.offsets.QuarterBegin(1)
        tr = base[(base.day < q0 - pd.Timedelta(days=10)) & (base.day >= q0 - pd.DateOffset(years=3)) & base.y.notna()]
        te = base[(base.day >= q0) & (base.day < q1)]
        if len(tr) < 20000 or not len(te):
            continue
        m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=31, min_child_samples=200, subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.7, reg_lambda=1.0, verbose=-1)
        m.fit(tr[names], tr.y)
        te = te.assign(score=m.predict(te[names]))
        pred.append(te[["day", "key", "fwd", "score", "ROC20"]])
        if q0.month == 1:
            imp = pd.Series(m.feature_importances_, index=names)
        print(q0.date(), "train", len(tr), "test", len(te), flush=True)
    Pd = pd.concat(pred)
    Pd["ic"] = 0
    ic = Pd.groupby("day").apply(lambda g: g.score.corr(g.fwd, method="spearman"))
    print("rank IC mean", round(ic.mean(), 4), "IC>0 share", round((ic > 0).mean(), 3), flush=True)
    rb = sorted(Pd.day.unique())[::H]
    R = Pd[Pd.day.isin(rb)].copy()
    rng = np.random.default_rng(3); rows = []
    for d, g in R.groupby("day"):
        g = g.dropna(subset=["fwd"])
        if len(g) < 40:
            continue
        for N in (3, 5, 10):
            lo, hi = g.nsmallest(N, "score"), g.nlargest(N, "score")
            mlo, mhi = g.nsmallest(N, "ROC20"), g.nlargest(N, "ROC20")
            rnd = g.sample(N, random_state=int(rng.integers(1e9)))
            for lab, x, s in (("ML SELL bottom", lo, -1), ("ML BUY top", hi, 1), ("naive SELL weakest 20d", mlo, -1),
                              ("naive BUY strongest 20d", mhi, 1), ("random SELL", rnd, -1), ("random BUY", rnd, 1)):
                for _, t in x.iterrows():
                    rows.append(dict(day=d, N=N, strat=lab, key=t.key, symbol=sym.get(t.key), ret=s * t.fwd - COST))
    T = pd.DataFrame(rows); T.to_csv(OUT / "ml_rank_trades.csv.gz", index=False)
    T["year"] = pd.to_datetime(T.day).dt.year
    T["period"] = np.where(T.year <= 2021, "2020-21", np.where(T.year <= 2023, "2022-23", "2024-26"))
    S = T.groupby(["N", "strat"]).agg(trades=("ret", "size"), win=("ret", lambda x: round(100 * (x > 0).mean(), 1)),
                                       avg_pct=("ret", lambda x: round(100 * x.mean(), 3))).reset_index()
    for p in ("2020-21", "2022-23", "2024-26"):
        g = T[T.period == p].groupby(["N", "strat"]).ret
        S[f"{p}_win"] = S.set_index(["N", "strat"]).index.map(g.apply(lambda x: round(100 * (x > 0).mean(), 1)))
        S[f"{p}_avg"] = S.set_index(["N", "strat"]).index.map(g.apply(lambda x: round(100 * x.mean(), 3)))
    S.to_csv(OUT / "ml_rank_summary.csv", index=False)
    imp.sort_values(ascending=False).to_csv(OUT / "ml_rank_importance.csv")
    pd.set_option("display.width", 220)
    print(S.to_string(index=False))
    print("\ntop factors:", imp.sort_values(ascending=False).head(15).to_dict())


if __name__ == "__main__":
    main()
