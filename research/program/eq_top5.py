"""EQ-TOP5-001 – daily historical simulation of a top-5 cash-delivery shortlist vs taking every qualifying signal.

Input: eq_research trades (results/eqbhav_trades.csv.gz, regime 'all', with signal-time features) + the strategy variants
to use (default: those that PASS in eqbhav_summary.csv; if none pass, the best variant per strategy by the walk-forward
rule, clearly labelled NOT validated).
Ranking (no look-ahead): score = prior expectancy of the variant (expanding window, only trades that EXITED before the
signal day, shrunk toward 0 with n/(n+100)) + 0.5 x RS percentile + 0.2 x min(volume ratio, 3)/3.
Selection per day: highest scores first, max 5 new names, max 2 per sector (unknown sector = its own), skip a stock already
held, skip a candidate whose 60-day return correlation with an already-picked name today is > 0.7.
Portfolio accounting: every trade risks 1 unit (R); daily P&L booked on the exit day; drawdown on that equity curve.
Reports: R per trade, PF, win %, max drawdown, concurrent positions, average pairwise correlation of picks, distribution
of days with 0..5 qualifying stocks, all by block (2005-10 / 2011-15 / 2016-20 / 2021-26).
python research/program/eq_top5.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "research/program/results"
K = ["strat", "entry", "stop", "exit"]


def pick_variants(S):
    p = S[S.PASS & (S.regime == "all")]
    if len(p):
        return p[K + ["regime"]].drop_duplicates(), True
    x = S[(S.regime == "all") & (S.n >= 300)].copy()
    x["minb"] = x[[f"b{k}_R" for k in range(3)]].min(axis=1)              # walk-forward: choose on blocks 0-2 only
    x = x.sort_values("minb", ascending=False).groupby("strat").head(1)
    return x[K + ["regime"]], False


def closes_pivot():
    from research.program import eq_bhav as EB
    P = EB.panel()
    A = EB.adjusted(P)
    rows = [pd.Series(d.close.values, index=d.time.values, name=d.symbol.iat[-1]) for d in A.values()]
    return pd.concat(rows, axis=1).sort_index()


def simulate(T, ind, piv, top=5, cap_sector=2, max_corr=0.7):
    T = T.sort_values("time").reset_index(drop=True)
    T["vid"] = T[K].astype(str).agg("|".join, axis=1)
    # prior expectancy per variant from trades that exited before each signal day
    T["prior"] = 0.0
    hist = {}
    ex_sorted = T.sort_values("exit_time")[["vid", "exit_time", "R"]].values
    ptr = 0; sums = {}; cnts = {}
    rets = piv.pct_change()
    for day, g in T.groupby("time", sort=True):
        while ptr < len(ex_sorted) and ex_sorted[ptr][1] < day:
            v, _, r = ex_sorted[ptr]; sums[v] = sums.get(v, 0) + r; cnts[v] = cnts.get(v, 0) + 1; ptr += 1
        for i in g.index:
            v = T.at[i, "vid"]; n = cnts.get(v, 0)
            T.at[i, "prior"] = (sums.get(v, 0) / n) * n / (n + 100) if n else 0.0
    T["score"] = T.prior + 0.5 * T.rs.fillna(0) + 0.2 * np.minimum(T.volx.fillna(0), 3) / 3
    held = {}                                   # sym -> exit_time
    picks, counts, corrs = [], [], []
    for day, g in T.groupby("time", sort=True):
        held = {s: e for s, e in held.items() if e >= day}
        g = g.sort_values("score", ascending=False).drop_duplicates("sym")
        q = g[~g.sym.isin(held)]
        counts.append((day, min(len(q), top), len(q)))
        chosen, sect = [], {}
        win = rets.loc[:day].tail(60)
        for _, r in q.iterrows():
            if len(chosen) >= top:
                break
            sc = ind.get(r.sym) or f"_{r.sym}"
            if sect.get(sc, 0) >= cap_sector:
                continue
            if chosen and r.sym in win:
                cc = [win[r.sym].corr(win[c.sym]) for c in chosen if c.sym in win]
                if cc and np.nanmax(cc) > max_corr:
                    continue
            chosen.append(r); sect[sc] = sect.get(sc, 0) + 1
        if len(chosen) > 1:
            m = win[[c.sym for c in chosen if c.sym in win]].corr().values
            corrs.append(np.nanmean(m[np.triu_indices_from(m, 1)]))
        for r in chosen:
            picks.append(r); held[r.sym] = r.exit_time
    return pd.DataFrame(picks), pd.DataFrame(counts, columns=["day", "picked", "qualifying"]), np.nanmean(corrs) if corrs else np.nan


def stats(X, label):
    if not len(X):
        return dict(set=label, n=0)
    R = X.R.values; w, ls = R[R > 0], R[R <= 0]
    daily = X.groupby("exit_time").R.sum().sort_index().cumsum()
    blk = pd.cut(pd.to_datetime(X.time), pd.to_datetime(["2000", "2011", "2016", "2021", "2030"]), labels=["2005-10", "2011-15", "2016-20", "2021-26"])
    by = X.groupby(blk, observed=True).R.mean().round(3).to_dict()
    yrs = X.groupby(pd.to_datetime(X.time).dt.year).R.sum()
    return dict(set=label, n=len(R), per_month=round(len(R) / max(1, X.time.dt.to_period("M").nunique()), 1), win=round(100 * (R > 0).mean(), 1),
                R=round(R.mean(), 3), PF=round(w.sum() / -ls.sum(), 2) if len(ls) else np.nan, avg_win=round(w.mean(), 2),
                avg_loss=round(ls.mean(), 2), total_R=round(R.sum(), 0), maxDD_R=round((daily.cummax() - daily).max(), 1),
                years_pos=f"{int((yrs > 0).sum())}/{len(yrs)}", **{f"R_{k}": v for k, v in by.items()})


def main():
    S = pd.read_csv(OUT / "eqbhav_summary.csv")
    V, validated = pick_variants(S)
    print("variants used:", "VALIDATED (PASS)" if validated else "NOT validated – best walk-forward variant per strategy")
    print(V.to_string(index=False))
    T = pd.read_csv(OUT / "eqbhav_trades.csv.gz", parse_dates=["time", "exit_time"])
    T = T.merge(V[K], on=K)
    from research.program import eq_data as ED
    uf = ED.EQ / "universe.csv"
    ind = dict(zip(*pd.read_csv(uf)[["symbol", "industry"]].fillna("").values.T)) if uf.exists() else {}
    piv = closes_pivot()
    res = []
    for strat, g in [("ALL strategies", T)] + list(T.groupby("strat")):
        P, C, corr = simulate(g, ind, piv)
        res.append(dict(stats(g.drop_duplicates(["sym", "time"]), f"{strat} · every signal"), avg_corr=np.nan))
        res.append(dict(stats(P, f"{strat} · TOP-5 shortlist"), avg_corr=round(corr, 2)))
        if strat == "ALL strategies":
            dist = C.picked.value_counts().sort_index()
            print("\ndays with 0..5 qualifying stocks (after sector / correlation caps):",
                  {int(k): int(v) for k, v in dist.items()}, f"of {len(C)} signal days")
            C.to_csv(OUT / "eqtop5_daily_counts.csv", index=False); P.to_csv(OUT / "eqtop5_picks.csv", index=False)
    R_ = pd.DataFrame(res)
    R_.to_csv(OUT / "eqtop5_summary.csv", index=False)
    pd.set_option("display.width", 260)
    print(R_.to_string(index=False))


if __name__ == "__main__":
    main()
