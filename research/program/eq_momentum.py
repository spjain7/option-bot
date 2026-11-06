"""EQ-MOM-001 – H-A: cross-sectional momentum (relative strength) portfolio on NSE cash, monthly rebalance.

Why different: short swing setups (<= 20 sessions) have ~0 gross edge and lose the 0.39 % round trip; momentum works on
3-12-month horizons where moves are large relative to costs.
Rules (pre-registered): each month's last session, eligible = point-in-time liquid universe (60-session median turnover
>= ₹25 cr, price >= ₹50, >= 250 sessions history). Score = return over [t-L, t-21] sessions (skip last month), L in {126, 252};
optional volatility-adjusted score (return / 126-day stdev). Buy the top N (5 / 10 / 20) at the NEXT session's open, equal
weight, hold to the next rebalance open. Market filter: invested only when the point-in-time equal-weight top-100 index
closes above its 200-session average at the signal (else cash, 0 %). Costs: delivery round trip 0.393 % on every name
bought + sold (names kept are not traded). Survivorship: delisted stocks in the data; a stock that stops trading is
exited at its last close.
Walk-forward: choose (L, N, vol-adj, filter) on 2005-2015 only by Sharpe; report 2016-2026 untouched.
python research/program/eq_momentum.py"""
import sys
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import eq_bhav as EB, eq_data as ED  # noqa: E402

OUT = ROOT / "research/program/results"
CF = ED.cost_frac("delivery")


def panels():
    P = EB.panel(); A = EB.adjusted(P)
    C, O, T = {}, {}, {}
    for k, d in A.items():
        s = d.symbol.iat[-1] + ("" if d.symbol.iat[-1] not in C else f"#{k[-4:]}")
        C[s] = pd.Series(d.close.values, d.time.values); O[s] = pd.Series(d.open.values, d.time.values)
        T[s] = pd.Series((d.close * d.volume).rolling(60, min_periods=40).median().values, d.time.values)
    C, O, T = (pd.concat(x, axis=1).sort_index() for x in (C, O, T))
    mkt = EB.market(A).set_index("time").close.reindex(C.index).ffill()
    return C, O, T, mkt


def backtest(C, O, T, mkt, L=252, N=10, voladj=False, filt=True, start="2006-01-01"):
    days = C.index
    hist = C.notna().cumsum()
    me = pd.Series(days, index=days).groupby(days.to_period("M")).last().values      # month-end sessions
    me = [d for d in me if d >= pd.Timestamp(start)]
    ma200 = mkt.rolling(200).mean()
    ret_daily = C.pct_change(fill_method=None)
    held, rows, picks = [], [], []
    for a, b in zip(me[:-1], me[1:]):
        ia = days.get_loc(a); ib = days.get_loc(b)
        if ia + 1 >= len(days) or ib + 1 >= len(days):
            break
        d_in, d_out = days[ia + 1], days[ib + 1]
        el = (T.loc[a] >= ED.MIN_TURNOVER) & (C.loc[a] >= ED.MIN_PRICE) & (hist.loc[a] >= 250) & C.loc[d_in].notna() & O.loc[d_in].notna()
        on = (not filt) or (mkt.loc[a] > ma200.loc[a])
        new = []
        if on and ia >= L:
            sc = C.iloc[ia - 21] / C.iloc[ia - L] - 1
            if voladj:
                sc = sc / ret_daily.iloc[ia - 126:ia].std()
            sc = sc[el].dropna().sort_values(ascending=False)
            new = list(sc.index[:N])
        # period return: open(d_in) -> open(d_out) per name; a name that stops trading exits at its last close
        r = []
        for s in new:
            seg = C[s].loc[d_in:d_out]
            last = seg.dropna()
            if last.empty:
                continue
            px_out = O[s].loc[d_out] if pd.notna(O[s].get(d_out)) else last.iloc[-1]
            r.append(px_out / O[s].loc[d_in] - 1)
        turn = len(set(new) - set(held)) + len(set(held) - set(new))
        cost = CF / 2 * turn / max(len(new), 1) if new else (CF / 2 * len(held) / max(len(held), 1) if held else 0)
        pr = (np.mean(r) if r else 0.0) - (cost if (new or held) else 0.0)
        rows.append(dict(start=d_in, end=d_out, ret=pr, n=len(new), invested=bool(new)))
        picks += [dict(month=d_in, sym=s, ret=x) for s, x in zip(new, r)]
        held = new
    return pd.DataFrame(rows), pd.DataFrame(picks)


def metrics(R, lab):
    if R.empty:
        return dict(set=lab)
    r = R.ret.values; eq = np.cumprod(1 + r)
    yrs = (R.end.iloc[-1] - R.start.iloc[0]).days / 365.25
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    return dict(set=lab, months=len(r), CAGR=round(100 * (eq[-1] ** (1 / yrs) - 1), 1), vol=round(100 * r.std() * np.sqrt(12), 1),
                sharpe=round(r.mean() / r.std() * np.sqrt(12), 2) if r.std() > 0 else np.nan, maxDD=round(100 * dd, 1),
                months_pos=round(100 * (r > 0).mean(), 0), invested=round(100 * R.invested.mean(), 0))


def bench(C, O, T, mkt, start, end):
    R, _ = backtest(C, O, T, mkt, L=252, N=10_000, filt=False, start=start)          # equal-weight eligible universe
    return R[(R.start >= start) & (R.start < end)]


def main():
    C, O, T, mkt = panels()
    grid = list(product((126, 252), (5, 10, 20), (False, True), (False, True)))
    res = []
    for L, N, va, fl in grid:
        R, P = backtest(C, O, T, mkt, L, N, va, fl)
        tr, te = R[R.start < "2016-01-01"], R[R.start >= "2016-01-01"]
        res.append(dict(L=L, N=N, voladj=va, filt=fl, **{f"train_{k}": v for k, v in metrics(tr, "").items() if k != "set"},
                        **{f"test_{k}": v for k, v in metrics(te, "").items() if k != "set"}))
    G = pd.DataFrame(res).sort_values("train_sharpe", ascending=False)
    G.to_csv(OUT / "eqmom_grid.csv", index=False)
    pd.set_option("display.width", 260)
    print(G.to_string(index=False))
    b = G.iloc[0]
    print(f"\nchosen on 2005-15 only: L={b.L} N={b.N} voladj={b.voladj} filter={b.filt}")
    R, P = backtest(C, O, T, mkt, int(b.L), int(b.N), bool(b.voladj), bool(b.filt))
    R.to_csv(OUT / "eqmom_best_months.csv", index=False); P.to_csv(OUT / "eqmom_best_picks.csv", index=False)
    out = [metrics(R[R.start < "2016"], "momentum 2006-15 (train)"), metrics(R[R.start >= "2016"], "momentum 2016-26 (OUT OF SAMPLE)"),
           metrics(bench(C, O, T, mkt, "2006-01-01", "2016-01-01"), "EW liquid universe 2006-15"),
           metrics(bench(C, O, T, mkt, "2016-01-01", "2030-01-01"), "EW liquid universe 2016-26")]
    for y0, y1 in (("2016", "2019"), ("2019", "2022"), ("2022", "2027")):
        out.append(metrics(R[(R.start >= y0) & (R.start < y1)], f"momentum {y0}-{int(y1) - 1}"))
    print(pd.DataFrame(out).to_string(index=False))
    print(f"\nper holding (stock-month): n {len(P)} · win {100 * (P.ret > 0).mean():.0f}% · mean {100 * P.ret.mean():+.2f}% · "
          f"median {100 * P.ret.median():+.2f}% (before costs)")
    yr = R.assign(y=R.start.dt.year).groupby("y").ret.apply(lambda x: np.prod(1 + x) - 1)
    print("calendar years:", {int(k): round(100 * v, 1) for k, v in yr.items()})


if __name__ == "__main__":
    main()
