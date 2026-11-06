"""EQ-TREND-001 – H-B: 52-week-high breakout with a LONG trend-following hold (NSE cash delivery, actual cash prices).

Why different: the 20-session swing setups capture ~0 gross; leaders that make new 52-week highs often trend for months.
Rules (pre-registered): signal = close at a new N-session closing high (N in {126, 250}) after none in the prior 20 sessions,
60-session turnover >= ₹25 cr, price >= ₹50; optional RS filter (63-day relative strength top 30 % of the universe) and
market filter (equal-weight top-100 index above its 200-session average). Entry next open. Initial stop 3 x ATR(20).
Exit {EMA50: close below EMA50 -> next open, CH4: 4-ATR chandelier from the highest close} or after 250 sessions.
Costs: delivery round trip 0.393 % + gap fills at the open.
Portfolio: 10 equal slots; when more signals than free slots, highest RS first; no stock twice.
Validation: blocks 2005-10 / 2011-15 / 2016-20 / 2021-26, variant chosen on 2005-15 only, 2016-26 reported out of sample.
python research/program/eq_trend.py"""
import sys
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import eq_bhav as EB, eq_data as ED  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
CF = ED.cost_frac("delivery")


@njit(cache=True)
def sim(o, h, l, c, atr, e50, idx, mode, maxh, cf):
    n = len(c); oi = np.empty(len(idx), np.int64); ox = np.empty(len(idx), np.int64)
    pr = np.empty(len(idx)); rr = np.empty(len(idx)); k = 0; busy = -1
    for q in range(len(idx)):
        i = idx[q]
        if i <= busy or i + 2 >= n or not atr[i] > 0:
            continue
        j = i + 1; e = o[j]; st = e - 3.0 * atr[i]; R = e - st; best = c[j]
        px = 0.0; t = j; done = False
        while t < n:
            if t > j and o[t] <= st:
                px = o[t]; done = True; break
            if l[t] <= st:
                px = st; done = True; break
            if mode == 0:
                if c[t] < e50[t] and t + 1 < n:
                    px = o[t + 1]; t += 1; done = True; break
            else:
                best = max(best, c[t]); ns = best - 4.0 * atr[t]
                if ns > st:
                    st = ns
            if t - j >= maxh:
                px = c[t]; done = True; break
            t += 1
        if not done:
            px = c[n - 1]; t = n - 1
        oi[k] = i; ox[k] = t; pr[k] = px / e - 1 - cf; rr[k] = (px - e - cf * e) / R; k += 1
        busy = t
    return oi[:k], ox[:k], pr[:k], rr[:k]


def run():
    P = EB.panel(); A = EB.adjusted(P)
    mk = EB.market(A).set_index("time").close
    mfilt = (mk > mk.rolling(200).mean()).shift(1)
    # RS percentile (63-day return) across the liquid universe
    rs_rows = []
    for k, d in A.items():
        to = (d.close * d.volume).rolling(60, min_periods=40).median().shift(1)
        el = (to >= ED.MIN_TURNOVER) & (d.close.shift(1) >= ED.MIN_PRICE) & (pd.Series(np.arange(len(d))) >= 250)
        rs_rows.append(pd.DataFrame(dict(time=d.time, key=k, r63=np.where(el, d.close.pct_change(63), np.nan))))
    X = pd.concat(rs_rows); X["rs"] = X.groupby("time").r63.rank(pct=True)
    RS = {k: g.set_index("time").rs for k, g in X.groupby("key")}
    rows = []
    for k, d in A.items():
        if len(d) < 300:
            continue
        o, h, l, c = (d[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
        atr = np.nan_to_num(I.atr(d, 20).values).astype(np.float64)
        e50 = d.close.ewm(span=50, adjust=False).mean().values.astype(np.float64)
        to = (d.close * d.volume).rolling(60, min_periods=40).median().shift(1).values
        el = (to >= ED.MIN_TURNOVER) & (np.r_[np.nan, c[:-1]] >= ED.MIN_PRICE) & (np.arange(len(d)) >= 250)
        rs = RS[k].reindex(d.time.values).values
        mf = mfilt.reindex(d.time.values).fillna(False).values.astype(bool)
        for N, mode, rf, mfl in product((126, 250), (0, 1), (0, 1), (0, 1)):
            hiN = pd.Series(c).rolling(N).max().values
            newhi = c >= hiN
            fresh = newhi & ~(pd.Series(newhi).shift(1).rolling(20).max().fillna(0).values.astype(bool))
            m = fresh & el
            if rf:
                m &= np.nan_to_num(rs) >= 0.7
            if mfl:
                m &= mf
            idx = np.flatnonzero(m).astype(np.int64)
            if not len(idx):
                continue
            oi, ox, pr, rr = sim(o, h, l, c, atr, e50, idx, mode, 250, CF)
            for a, b, p_, r_ in zip(oi, ox, pr, rr):
                rows.append((d.symbol.iat[a], N, "EMA50" if mode == 0 else "CH4", rf, mfl, d.time.iat[a], d.time.iat[b], b - a, p_, r_,
                             rs[a] if rs[a] == rs[a] else 0.0))
    T = pd.DataFrame(rows, columns=["sym", "N", "exit", "rs_filter", "mkt_filter", "time", "exit_time", "bars", "ret", "R", "rs"])
    T.to_csv(OUT / "eqtrend_trades.csv.gz", index=False)
    return T


def portfolio(T, slots=10):
    """10 equal-capital slots, highest RS first; returns monthly portfolio return series and the trades taken."""
    T = T.sort_values(["time", "rs"], ascending=[True, False])
    held, taken = [], []
    for day, g in T.groupby("time", sort=True):
        held = [x for x in held if x[0] >= day]
        for _, r in g.iterrows():
            if len(held) >= slots:
                break
            if any(h[1] == r.sym for h in held):
                continue
            held.append((r.exit_time, r.sym)); taken.append(r)
    X = pd.DataFrame(taken)
    if X.empty:
        return X, pd.Series(dtype=float)
    # each trade contributes ret/slots on its exit day (capital per slot = 1/slots of equity at that time: approx. simple)
    pnl = X.groupby(X.exit_time.dt.to_period("M")).ret.sum() / slots
    return X, pnl


def summary(T):
    blk = lambda t: pd.cut(t, pd.to_datetime(["2000", "2011", "2016", "2021", "2030"]), labels=["05-10", "11-15", "16-20", "21-26"])  # noqa: E731
    rows = []
    for (N, ex, rf, mf), g in T.groupby(["N", "exit", "rs_filter", "mkt_filter"]):
        b = g.groupby(blk(g.time), observed=True)
        rows.append(dict(N=N, exit=ex, rs_filter=rf, mkt_filter=mf, n=len(g), win=round(100 * (g.ret > 0).mean(), 1),
                         ret=round(100 * g.ret.mean(), 2), R=round(g.R.mean(), 3), med_bars=int(g.bars.median()),
                         PF=round(g.ret[g.ret > 0].sum() / -g.ret[g.ret <= 0].sum(), 2),
                         **{f"R_{k}": round(v, 3) for k, v in b.R.mean().items()},
                         train_R=round(g[g.time < "2016"].R.mean(), 3), test_R=round(g[g.time >= "2016"].R.mean(), 3)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    T = run()
    S = summary(T)
    S.to_csv(OUT / "eqtrend_summary.csv", index=False)
    pd.set_option("display.width", 260)
    print(S.sort_values("train_R", ascending=False).to_string(index=False))
    best = S.sort_values("train_R", ascending=False).iloc[0]
    g = T[(T.N == best.N) & (T.exit == best.exit) & (T.rs_filter == best.rs_filter) & (T.mkt_filter == best.mkt_filter)]
    X, pnl = portfolio(g)
    eq = (1 + pnl).cumprod()
    for lab, s in (("2006-15", pnl[pnl.index < pd.Period("2016-01", "M")]), ("2016-26 OOS", pnl[pnl.index >= pd.Period("2016-01", "M")])):
        e = (1 + s).cumprod(); yrs = len(s) / 12
        print(f"portfolio {lab}: CAGR {100 * (e.iloc[-1] ** (1 / yrs) - 1):.1f}% · maxDD {100 * (e / e.cummax() - 1).min():.1f}% · "
              f"months + {100 * (s > 0).mean():.0f}% · trades {len(X[(X.time >= ('2016' if 'OOS' in lab else '2005')) & (X.time < ('2030' if 'OOS' in lab else '2016'))])}")
    X.to_csv(OUT / "eqtrend_portfolio_trades.csv", index=False)
