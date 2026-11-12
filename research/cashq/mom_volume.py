"""CASHQ-PF – what works in NSE cash: relative-strength PORTFOLIOS, now with volume (owner 10-Nov: "keep volume in
consideration, find what works for the cash segment"). Single-stock breakout calls are weak (1 in 3 wins); the monthly
relative-strength portfolio is the only strong cash result – this tests whether VOLUME information improves it.
Same engine and rules as the live cash-mom-1.2 (EQ-MOM-003): point-in-time liquid universe, buy at the next open, equal
weight, MA100 market filter (cash when off), delivery cost 0.393 % round trip on names traded.
Pre-registered scores (8) x rebalance {monthly, every 10 sessions} x holdings {10, 20} = 32 variants:
  B0  12-1 month return / 126-day volatility                     (the live rule)
  V1  B0, only stocks whose turnover is rising: median 60d / median 250d >= 1.0
  V2  B0, turnover rising strongly: >= 1.3
  V3  B0, only accumulation: up-day volume / down-day volume over 63 sessions >= 1.2
  V4  average rank of B0 and nearness to the 52-week high (close / 252-day high)
  V5  nearness to the 52-week high only
  V6  6-1 month return / volatility
  V7  V4 + turnover rising (>= 1.0) + accumulation (>= 1.0)
Selection on 2006-2015 by Sharpe only; 2016-2026 reported untouched (note: B0's 2016-26 result was already known).
python -m research.cashq.mom_volume"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import eq_bhav as EB, eq_data as ED  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
CF = ED.cost_frac("delivery")


def load():
    A = EB.adjusted_cached()
    C, O, V = {}, {}, {}
    for k, d in A.items():
        s = d.symbol.iat[-1] + ("" if d.symbol.iat[-1] not in C else f"#{k[-4:]}")
        t = d.time.values
        C[s] = pd.Series(d.close.values, t); O[s] = pd.Series(d.open.values, t); V[s] = pd.Series((d.close * d.volume).values, t)
    C, O, V = (pd.concat(x, axis=1).sort_index().astype("float32") for x in (C, O, V))
    mkt = EB.market(A).set_index("time").close.reindex(C.index).ffill()
    return C, O, V, mkt


class D:
    def __init__(self, C, O, V, mkt):
        self.days, self.syms = C.index, np.array(C.columns)
        self.c, self.o = C.values, O.values
        self.cf = C.ffill().values
        self.hist = np.cumsum(~np.isnan(self.c), axis=0)
        t60 = V.rolling(60, min_periods=40).median()
        self.t = t60.values
        self.tt = (t60 / V.rolling(250, min_periods=150).median()).values            # turnover trend
        up = V.where(C > C.shift(1), 0.0).rolling(63, min_periods=40).sum()
        dn = V.where(C < C.shift(1), 0.0).rolling(63, min_periods=40).sum()
        self.ud = (up / dn.replace(0, np.nan)).values
        self.near = (C / C.rolling(252, min_periods=200).max()).values
        self.vol = np.log(C / C.shift(1)).rolling(126, min_periods=60).std().values
        self.mkt, self.ma = mkt.values, mkt.rolling(100).mean().values
        me = pd.Series(self.days, index=self.days).groupby(self.days.to_period("M")).last().values
        self.me = np.array([self.days.get_loc(x) for x in me])


def rank01(x, ok):
    out = np.full(len(x), np.nan)
    v = np.where(ok & np.isfinite(x))[0]
    if len(v):
        out[v] = pd.Series(x[v]).rank(pct=True).values
    return out


def score(d, ia, kind):
    c = d.c
    el = (d.t[ia] >= ED.MIN_TURNOVER) & (c[ia] >= ED.MIN_PRICE) & (d.hist[ia] >= 250) & ~np.isnan(c[ia - 252])
    b0 = (c[ia - 21] / c[ia - 252] - 1) / d.vol[ia]
    if kind == "B0":
        s = b0
    elif kind == "V1":
        s = np.where(d.tt[ia] >= 1.0, b0, np.nan)
    elif kind == "V2":
        s = np.where(d.tt[ia] >= 1.3, b0, np.nan)
    elif kind == "V3":
        s = np.where(d.ud[ia] >= 1.2, b0, np.nan)
    elif kind == "V4":
        s = (rank01(b0, el) + rank01(d.near[ia], el)) / 2
    elif kind == "V5":
        s = d.near[ia]
    elif kind == "V6":
        s = (c[ia - 21] / c[ia - 126] - 1) / d.vol[ia]
    elif kind == "V7":
        s = np.where((d.tt[ia] >= 1.0) & (d.ud[ia] >= 1.0), (rank01(b0, el) + rank01(d.near[ia], el)) / 2, np.nan)
    return np.where(el & np.isfinite(s), s, -np.inf)


def backtest(d, kind, N, step, start="2006-01-01"):
    s0 = np.searchsorted(d.days.values, np.datetime64(start))
    pts = [i for i in d.me if i >= s0] if step == "M" else list(range(max(s0, 260), len(d.days) - 1, step))
    held = np.array([], int); rows, picks = [], []
    for ia, ib in zip(pts[:-1], pts[1:]):
        if ib + 1 >= len(d.days):
            break
        i_in, i_out = ia + 1, ib + 1
        new = np.array([], int)
        if d.mkt[ia] > d.ma[ia] and ia >= 252:
            sc = score(d, ia, kind)
            sc = np.where(np.isnan(d.o[i_in]), -np.inf, sc)
            k = min(N, int(np.isfinite(sc).sum()))
            if k > 0:
                new = np.argpartition(-sc, k - 1)[:k]
        if len(new):
            px_out = np.where(np.isnan(d.o[i_out, new]), d.cf[i_out, new], d.o[i_out, new])
            r = px_out / d.o[i_in, new] - 1
        else:
            r = np.array([])
        turn = len(set(new) - set(held)) + len(set(held) - set(new))
        pr = (np.nanmean(r) if len(r) else 0.0) - CF / 2 * turn / max(len(new), len(held), 1)
        rows.append(dict(start=d.days[i_in], end=d.days[i_out], ret=pr, n=len(new), turn=turn))
        picks += [dict(start=d.days[i_in], sym=d.syms[j], ret=x) for j, x in zip(new, r)]
        held = new
    return pd.DataFrame(rows), pd.DataFrame(picks)


def metrics(R, a, b):
    R = R[(R.start >= a) & (R.start < b)]
    if len(R) < 6:
        return {}
    r = R.ret.values; eq = np.cumprod(1 + r)
    yrs = (R.end.iloc[-1] - R.start.iloc[0]).days / 365.25
    ppy = len(r) / yrs
    return dict(CAGR=round(100 * (eq[-1] ** (1 / yrs) - 1), 1), sharpe=round(r.mean() / r.std() * np.sqrt(ppy), 2),
                maxDD=round(100 * (eq / np.maximum.accumulate(eq) - 1).min(), 1), win_periods=round(100 * (r > 0).mean()),
                invested=round(100 * (R.n > 0).mean()), trades_per_year=round(R.turn.sum() / 2 / yrs, 1))


def main():
    d = D(*load())
    rows, keep = [], {}
    for kind in ("B0", "V1", "V2", "V3", "V4", "V5", "V6", "V7"):
        for step in ("M", 10):
            for N in (10, 20):
                R, P = backtest(d, kind, N, step)
                keep[(kind, step, N)] = (R, P)
                row = dict(score=kind, rebalance="monthly" if step == "M" else "10 sessions", N=N)
                for lab, (a, b) in dict(DEV=("2006-01-01", "2016-01-01"), OOS=("2016-01-01", "2027-01-01")).items():
                    row.update({f"{lab}_{k}": v for k, v in metrics(R, a, b).items()})
                yr = R.groupby(R.start.dt.year).ret.apply(lambda x: np.prod(1 + x) - 1)
                row["oos_years_pos"] = f"{int((yr[yr.index >= 2016] > 0).sum())}/{int((yr.index >= 2016).sum())}"
                row["y2024"], row["y2025"], row["y2026"] = (round(100 * yr.get(y, np.nan), 1) for y in (2024, 2025, 2026))
                rows.append(row)
                print(row, flush=True)
    L = pd.DataFrame(rows).sort_values("DEV_sharpe", ascending=False)
    L.to_csv(OUT / "mom_volume.csv", index=False)
    best = L.iloc[0]
    R, P = keep[(best.score, "M" if best.rebalance == "monthly" else 10, int(best.N))]
    R.to_csv(OUT / "mom_volume_best_periods.csv", index=False); P.to_csv(OUT / "mom_volume_best_picks.csv", index=False)
    print(L.to_string(index=False))


if __name__ == "__main__":
    main()
