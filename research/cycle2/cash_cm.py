"""Cycle 2 · 3 – cash CONTINUATION BUY (CM-CONT-BUY-v1, unchanged in shadow): dependence on the bullish market, and
whether it adds independent value to the live monthly momentum portfolio (B0: 12-1 month return / volatility, 10 stocks,
monthly, MA100 market filter).
Conditions at the signal week (one at a time; inside vs outside; DEV / VALID / OOS; OOS Welch t):
  mkt_up_ema200 · mkt_ma100 (the momentum rule's own filter) · breadth > 50 % · breadth > 60 % · sector_up · sector_rs_top ·
  rs_top30 (stock 63-day RS in the top 30 %)
Portfolio: CM monthly return = sum of closed trades' net R x 0.5 % risk per trade (booked in the exit month); momentum
monthly return from the research backtest. OLS of CM on momentum (alpha, t), correlation, Sharpe of each and of an
equal-volatility blend, 2006–15 and 2016–26 separately, plus the same with CM restricted to mkt_ma100 (a SEPARATE
research version CM-v2a, never a change to v1).
python -m research.cycle2.cash_cm  ->  results/cash_cm.json"""
import json
import numpy as np
import pandas as pd

from research.cycle2 import common as C
from research.rsidiv import cash as RC

CUTS = RC.CUTS


def st(r):
    r = pd.Series(r, dtype=float).dropna()
    if len(r) < 3:
        return dict(n=len(r))
    w = r > 0; gl = -r[~w].sum()
    return dict(n=len(r), win=round(100 * w.mean(), 1), R=round(r.mean(), 3), PF=round(r[w].sum() / gl, 2) if gl > 0 else None)


def per(T):
    lab = C.E.periods(T.entry.values, CUTS)
    return {p: st(T.netR.values[lab == p]) for p, _ in CUTS}


def sharpe(x):
    x = pd.Series(x).dropna()
    return round(float(x.mean() / x.std() * np.sqrt(12)), 2) if len(x) > 12 and x.std() > 0 else None


def ols(y, x):
    X = np.c_[np.ones(len(x)), x]; b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b; s2 = e @ e / (len(y) - 2); se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    return dict(alpha_monthly_pct=round(100 * b[0], 3), alpha_t=round(b[0] / se[0], 2), beta=round(b[1], 3))


def main():
    cs = C.cash_context(); reg = cs["reg"]
    T = pd.read_csv(C.ROOT / "research/shadow/results/parity_CM-CONT-BUY-v1.csv.gz", parse_dates=["signal", "entry", "exit"])
    T = T[T.status.isin(["trade", "open"])].copy()
    al = lambda s: s.reindex(pd.DatetimeIndex(T.signal), method="ffill").values
    T["mkt_up_ema200"] = al(reg["mkt_up"]).astype(bool); T["mkt_ma100"] = al(reg["mkt_ma100"]).astype(bool)
    T["breadth"] = al(reg["breadth"]); T["breadth50"] = T.breadth > 0.5; T["breadth60"] = T.breadth > 0.6
    sec = T.name.map(cs["sector_of"]).fillna("")
    T["sector_up"] = [bool(cs["s_up"][s].asof(d)) if s in cs["s_up"] else np.nan for s, d in zip(sec, T.signal)]
    T["sector_rs_top"] = [bool(cs["s_rs"][s].asof(d) >= 0.5) if s in cs["s_rs"] else np.nan for s, d in zip(sec, T.signal)]
    T["rs_top30"] = [bool(cs["rs"][n].asof(d) >= 0.7) if n in cs["rs"] and pd.notna(cs["rs"][n].asof(d)) else np.nan for n, d in zip(T.name, T.signal)]
    res = dict(all=st(T.netR), by_period=per(T), conditions={})
    oos0 = pd.Timestamp(CUTS[-1][1])
    for c in ("mkt_up_ema200", "mkt_ma100", "breadth50", "breadth60", "sector_up", "sector_rs_top", "rs_top30"):
        k = T[c].dropna().astype(bool); X = T.loc[k.index]
        inn, out = X[k], X[~k]
        a, b = inn.netR[inn.entry >= oos0], out.netR[out.entry >= oos0]
        res["conditions"][c] = dict(known_for=len(X), inside=dict(all=st(inn.netR), **per(inn)), outside=dict(all=st(out.netR), **per(out)),
                                    oos_inside_minus_outside=round(float(a.mean() - b.mean()), 3) if len(a) and len(b) else None,
                                    oos_welch_t=round(float(C.welch(a, b)), 2) if np.isfinite(C.welch(a, b)) else None)
    # portfolio value vs the live momentum rule
    from research.cashq import mom_volume as MV
    d = MV.D(*MV.load()); MR, MP = MV.backtest(d, "B0", 10, "M")
    MR["month"] = pd.to_datetime(MR.start).dt.to_period("M")
    mom = MR.groupby("month").ret.sum()
    out = {}
    for lab, X in (("CM-v1 (all signals)", T), ("CM-v2a (only when the momentum MA100 filter is on)", T[T.mkt_ma100])):
        cm = (X.netR * 0.005).groupby(X.exit.dt.to_period("M")).sum().reindex(mom.index, fill_value=0.0)
        r = dict()
        for per_, (a_, b_) in (("2006-2015", ("2006-01", "2015-12")), ("2016-2026", ("2016-01", "2026-12"))):
            m_, c_ = mom.loc[a_:b_], cm.loc[a_:b_]
            k = m_.std() / c_.std() if c_.std() > 0 else 0
            blend = 0.5 * m_ + 0.5 * k * c_
            r[per_] = dict(months=len(m_), corr=round(float(m_.corr(c_)), 3), sharpe_momentum=sharpe(m_), sharpe_cm=sharpe(c_),
                           sharpe_equal_vol_blend=sharpe(blend), cm_on_momentum=ols(c_.values, m_.values),
                           cm_months_positive_pct=round(100 * float((c_[c_ != 0] > 0).mean()), 1),
                           cm_when_momentum_negative=round(float(c_[m_ < 0].mean() * 100), 3))
        r["trades"] = len(X); r["avg_R"] = round(float(X.netR.mean()), 3)
        out[lab] = r
    res["portfolio_vs_momentum"] = out
    # concurrency / capital: open positions per week at ₹5 lakh per position
    wk = pd.date_range(T.entry.min(), T.exit.max(), freq="W-FRI")
    openp = np.array([((T.entry <= w) & (T.exit >= w)).sum() for w in wk])
    res["concurrency"] = dict(max_open=int(openp.max()), median_open=float(np.median(openp)), p95_open=float(np.percentile(openp, 95)),
                              capital_at_p95_lakh=round(float(np.percentile(openp, 95)) * 5, 0))
    json.dump(res, open(C.OUT / "cash_cm.json", "w"), indent=1, default=str)
    print(json.dumps(res, default=str)[:8000])


if __name__ == "__main__":
    main()
