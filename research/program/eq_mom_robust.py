"""EQ-MOM-002 – robustness of the monthly relative-strength portfolio (EQ-MOM-001b, fixed rules: L=252 skip 21, vol-adj,
top 10, market filter). No re-optimisation – every check uses the rules chosen on 2006-15.
  1 risk-adjusted: Sharpe, Sortino, beta / alpha vs the equal-weight liquid universe (monthly regression)
  2 regimes: returns in market-proxy bull / sideways / bear months (classified at the month start, no look-ahead)
  3 costs: 1x / 2x / 3x the delivery cost; turnover and cost drag per year
  4 timing luck: same rules rebalanced on the 10th trading day of each month instead of month-end
  5 concentration: average pairwise 126-day return correlation of the 10 holdings (vs random 10 from the universe);
    correlation-cluster cap (max 2 names per cluster of the liquid universe, clusters by hierarchical clustering on
    the trailing 252-day correlations – a data-driven sector proxy until the NSE industry map arrives)
python research/program/eq_mom_robust.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import eq_momentum as MO, eq_data as ED  # noqa: E402

OUT = ROOT / "research/program/results"


def run_variant(D, cost_mult=1.0, day_offset=None, cluster_cap=None, N=10):
    """MO.backtest with optional cost multiplier, rebalance offset and cluster cap (re-implemented loop, same rules)."""
    days = D.days
    if day_offset is None:
        me = list(D.me)
    else:
        per = pd.Series(np.arange(len(days)), index=days).groupby(days.to_period("M"))
        me = [g.iloc[min(day_offset, len(g) - 1)] for _, g in per]
    me = [i for i in me if days[i] >= pd.Timestamp("2006-01-01")]
    lr = np.log(D.c[1:] / D.c[:-1])
    held = np.array([], int); rows, corrs = [], []
    for ia, ib in zip(me[:-1], me[1:]):
        if ib + 1 >= len(days):
            break
        i_in, i_out = ia + 1, ib + 1
        on = D.mkt[ia] > D.ma[ia]
        new = np.array([], int)
        if on and ia >= 252:
            el = (D.t[ia] >= ED.MIN_TURNOVER) & (D.c[ia] >= ED.MIN_PRICE) & (D.hist[ia] >= 250) & ~np.isnan(D.o[i_in]) & ~np.isnan(D.c[ia - 252])
            sc = (D.c[ia - 21] / D.c[ia - 252] - 1) / D.vol[ia]
            sc = np.where(el & np.isfinite(sc), sc, -np.inf)
            order = np.argsort(-sc)
            order = order[np.isfinite(sc[order])]
            if cluster_cap:
                R = lr[max(0, ia - 252):ia][:, order[:80]]
                ok = ~np.isnan(R).any(axis=0)
                cand = order[:80][ok]
                if len(cand) > N:
                    C_ = np.corrcoef(np.nan_to_num(lr[max(0, ia - 252):ia][:, cand]).T)
                    from scipy.cluster.hierarchy import linkage, fcluster
                    from scipy.spatial.distance import squareform
                    dist = np.clip(1 - C_, 0, 2); np.fill_diagonal(dist, 0)
                    lab = fcluster(linkage(squareform(dist, checks=False), "average"), t=0.6, criterion="distance")
                    pick, cnt = [], {}
                    for j, l_ in zip(cand, lab):
                        if cnt.get(l_, 0) < cluster_cap:
                            pick.append(j); cnt[l_] = cnt.get(l_, 0) + 1
                        if len(pick) == N:
                            break
                    new = np.array(pick)
                else:
                    new = cand[:N]
            else:
                new = order[:N]
        if len(new):
            px_out = np.where(np.isnan(D.o[i_out, new]), D.cf[i_out, new], D.o[i_out, new])
            r = px_out / D.o[i_in, new] - 1
            W = np.nan_to_num(lr[max(0, ia - 126):ia][:, new])
            if len(new) > 1:
                cm = np.corrcoef(W.T); corrs.append(np.nanmean(cm[np.triu_indices_from(cm, 1)]))
        else:
            r = np.array([])
        turn = len(set(new) - set(held)) + len(set(held) - set(new))
        pr = (np.nanmean(r) if len(r) else 0.0) - cost_mult * MO.CF / 2 * turn / max(len(new), len(held), 1)
        rows.append(dict(start=days[i_in], end=days[i_out], ret=pr, n=len(new), turn=turn, invested=bool(len(new))))
        held = new
    return pd.DataFrame(rows), (np.nanmean(corrs) if corrs else np.nan)


def stats(R, bench=None):
    r = R.ret.values; eq = np.cumprod(1 + r); yrs = len(r) / 12
    dn = r[r < 0]
    out = dict(CAGR=round(100 * (eq[-1] ** (1 / yrs) - 1), 1), sharpe=round(r.mean() / r.std() * np.sqrt(12), 2),
               sortino=round(r.mean() / (np.sqrt((dn ** 2).mean()) if len(dn) else np.nan) * np.sqrt(12), 2),
               maxDD=round(100 * (eq / np.maximum.accumulate(eq) - 1).min(), 1))
    if bench is not None:
        b = bench.set_index("start").ret.reindex(R.start).values
        m = ~np.isnan(b)
        beta, alpha = np.polyfit(b[m], r[m], 1)
        out.update(beta=round(beta, 2), alpha_pa=round(100 * alpha * 12, 1))
    return out


def main():
    D = MO.Data(*MO.panels())
    base, corr = run_variant(D)
    bench, _ = MO.backtest(D, L=252, N=10_000, filt=False)
    rows = []
    for lab, a, b in (("2006-15", "2006", "2016"), ("2016-26 OOS", "2016", "2030"), ("all", "2006", "2030")):
        x = base[(base.start >= a) & (base.start < b)]; y = bench[(bench.start >= a) & (bench.start < b)]
        rows.append(dict(test="base vs EW universe", period=lab, **stats(x, y), EW_CAGR=stats(y)["CAGR"], EW_maxDD=stats(y)["maxDD"]))
    # regimes (month start): bull = proxy > MA200 and MA50 > MA200; bear = proxy < MA200 and MA50 < MA200; else sideways
    mk = pd.Series(D.mkt, index=D.days); ma50 = mk.rolling(50).mean(); ma200 = mk.rolling(200).mean()
    def reg(t):
        i = D.days.get_loc(t) - 1
        if mk.iloc[i] > ma200.iloc[i] and ma50.iloc[i] > ma200.iloc[i]:
            return "bull"
        if mk.iloc[i] < ma200.iloc[i] and ma50.iloc[i] < ma200.iloc[i]:
            return "bear"
        return "sideways"
    base["regime"] = base.start.map(reg); bench["regime"] = bench.start.map(reg)
    g = base.groupby("regime").ret.agg(["size", "mean"]); gb = bench.groupby("regime").ret.mean()
    print("monthly return by regime (portfolio vs EW universe):")
    print(pd.DataFrame({"months": g["size"], "portfolio_%": (100 * g["mean"]).round(2), "EW_%": (100 * gb).round(2)}))
    for cm in (2.0, 3.0):
        R, _ = run_variant(D, cost_mult=cm)
        rows.append(dict(test=f"costs x{cm:g}", period="2016-26 OOS", **stats(R[R.start >= "2016"])))
    for off in (9, 4):
        R, _ = run_variant(D, day_offset=off)
        rows.append(dict(test=f"rebalance on trading day {off + 1} of month", period="2016-26 OOS", **stats(R[R.start >= "2016"])))
        rows.append(dict(test=f"rebalance on trading day {off + 1} of month", period="2006-15", **stats(R[(R.start >= "2006") & (R.start < "2016")])))
    Rc, corr_c = run_variant(D, cluster_cap=2)
    for lab, a, b in (("2006-15", "2006", "2016"), ("2016-26 OOS", "2016", "2030")):
        rows.append(dict(test="cluster cap 2 per correlation cluster", period=lab, **stats(Rc[(Rc.start >= a) & (Rc.start < b)])))
    turn = base[base.invested].turn.mean() / 2
    S = pd.DataFrame(rows)
    S.to_csv(OUT / "eqmom_robust.csv", index=False)
    pd.set_option("display.width", 250)
    print(S.to_string(index=False))
    print(f"\navg names replaced per rebalance {turn:.1f} of 10 · cost drag ≈ {100 * MO.CF / 2 * base.turn.sum() / max(1, base[base.invested].n.mean()) / (len(base) / 12):.2f}% per year")
    print(f"avg pairwise 126-day correlation of holdings: base {corr:.2f} · with cluster cap {corr_c:.2f}")
    yr = base.assign(y=base.start.dt.year).groupby("y").ret.apply(lambda x: np.prod(1 + x) - 1)
    yb = bench.assign(y=bench.start.dt.year).groupby("y").ret.apply(lambda x: np.prod(1 + x) - 1)
    print("years portfolio beat EW universe:", int((yr > yb.reindex(yr.index)).sum()), "of", len(yr))


if __name__ == "__main__":
    main()
