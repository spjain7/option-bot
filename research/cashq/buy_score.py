"""CASHQ-BUY stage 2 – transparent 100-point score for positional BUY candidates (50-day breakout events).
Built ONLY from features whose effect had the same direction in DEV (2005-14) and VALID (2015-19) (see ABLATION in
BUY_ENGINE.md); thresholds are DEV tercile cut points, frozen below. Features that did NOT help consistently and get no
points: volume expansion (RVOL), OBV / CMF / up-down volume, market MA100 filter, new highs-lows, extension, 52-week high.
Sector strength: no sector data -> 0 points (the user's 10 sector points are redistributed to relative strength).
  relative strength (35): rs126 >= 0.85 -> 35 · >= 0.70 -> 22 · >= 0.50 -> 10
  trend strength   (25): ADX >= 30 -> 25 · >= 22 -> 15 · >= 16 -> 6
  base quality     (20): ATR10/ATR50 before the breakout <= 0.85 -> 20 · <= 1.0 -> 10
  entry quality    (10): close NOT in the top 15 % of the day's range (clv <= 0.85) -> 10   (blow-off closes did worse)
  market breadth   (10): share of stocks above EMA50 >= 0.55 -> 10 · >= 0.40 -> 5
The score is a RANK, not a probability. python -m research.cashq.buy_score"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from . import validate as V

OUT = Path(__file__).resolve().parent / "results"


def score(T):
    s = np.select([T.rs126 >= 0.85, T.rs126 >= 0.70, T.rs126 >= 0.50], [35, 22, 10], 0)
    s = s + np.select([T.adx >= 30, T.adx >= 22, T.adx >= 16], [25, 15, 6], 0)
    s = s + np.select([T.tight <= 0.85, T.tight <= 1.0], [20, 10], 0)
    s = s + np.where(T.clv <= 0.85, 10, 0)
    s = s + np.select([T.breadth50 >= 0.55, T.breadth50 >= 0.40], [10, 5], 0)
    return s


def card(t):
    if not len(t):
        return dict(n=0)
    r = t.netR.values
    w, lo = r[r > 0].sum(), -r[r < 0].sum()
    eq = np.cumsum(r)
    return dict(n=len(t), win=round(100 * (r > 0).mean(), 1), T1=round(100 * t.T1.mean(), 1), T2=round(100 * t.T2.mean(), 1),
                stop=round(100 * (t.code == 1).mean(), 1), avgR=round(r.mean(), 3), pct=round(100 * t.netpct.mean(), 2),
                PF=round(w / lo, 2) if lo > 0 else np.inf, maxDD_R=round(float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq)), 1),
                hold=round(t.bars.mean(), 1))


def main():
    T = pd.read_csv(OUT / "buy_events.csv.gz", parse_dates=["entry_time", "signal_time", "exit_time"])
    last = T.exit_time.max()
    T["open_trade"] = (T.exit_time >= last) & (T.code == 3) & (T.bars < 250)
    T["score"] = score(T)
    T["bucket"] = pd.cut(T.score, [-1, 39, 54, 69, 100], labels=["0-39", "40-54", "55-69", "70-100"])
    C = T[~T.open_trade]
    rows = []
    for nm, (a, b) in V.DAILY_SPLITS.items():
        d = C[(C.entry_time >= a) & (C.entry_time <= b)]
        rows.append(dict(period=nm, bucket="ALL", **card(d)))
        for bk, g in d.groupby("bucket", observed=True):
            rows.append(dict(period=nm, bucket=str(bk), **card(g)))
    R = pd.DataFrame(rows)
    R.to_csv(OUT / "buy_score_buckets.csv", index=False)
    print(R.to_string(index=False))
    T.to_csv(OUT / "buy_events_scored.csv.gz", index=False)
    o = C[C.entry_time >= "2020"]
    yr = o[o.score >= 70].groupby(o.entry_time.dt.year).netR.agg(["size", "mean"]).round(3)
    print("score>=70 by year (OOS):"); print(yr.to_string())
    reg = o[o.score >= 70].groupby("mkt_on").netR.agg(["size", "mean"]).round(3); print(reg.to_string())
    top = o[o.score >= 70].groupby("symbol").netR.sum().sort_values(ascending=False)
    print("top5 share of profit", round(top.head(5).sum() / top[top > 0].sum(), 2), "stocks", o[o.score >= 70].symbol.nunique())


if __name__ == "__main__":
    main()
