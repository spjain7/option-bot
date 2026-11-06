"""EQ-002 daily top-5 portfolio test on the eq_research trade log (BUY-only cash stocks, research only).
Pre-specified, not tuned: for every combination in eq_summary, each signal day keep at most 5 new signals ranked by
63-day relative strength (rs, known at signal time), max 2 per industry. Compare with all signals and with a random-5
pick (same caps, 200 draws). PASS bar = eq_research bar: positive in all 4 time blocks, BH q < 0.10, n >= 300.
python research/program/eq_top5_simple.py
(Simple cross-check; the fuller portfolio simulation is eq_top5.py.)"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/program/results"
KEY = ["strat", "regime", "entry", "stop", "exit"]


def pick(g, ind, rng=None):
    """per signal day: rank (rs desc, or random), max 2 per industry, keep 5."""
    g = g.assign(ind=g.sym.map(ind).fillna("?"))
    g = g.assign(o=np.random.default_rng(rng).random(len(g))) if rng is not None else g.assign(o=-g.rs)
    g = g.sort_values(["time", "o"])
    g = g[g.groupby(["time", "ind"]).cumcount() < 2]
    return g[g.groupby("time").cumcount() < 5]


def bh(p):
    p = np.asarray(p); o = np.argsort(p); n = len(p)
    q = np.empty(n); q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def main():
    T = pd.read_csv(OUT / "eq_trades.csv.gz", parse_dates=["time"])
    u = pd.read_csv(ROOT / "research/data/angel/NSE_EQ/universe.csv")
    ind = dict(zip(u.symbol, u.industry.fillna("?")))
    edges = np.quantile(T.time.astype("int64"), [0, .25, .5, .75, 1])
    rows = []
    for k, g in T.groupby(KEY):
        top = pick(g, ind)
        rnd = [pick(g, ind, s).R.mean() for s in range(200)]
        r = top.R.values
        t, p = stats.ttest_1samp(r, 0) if len(r) > 2 else (0, 1)
        blk = pd.cut(top.time.astype("int64"), edges, include_lowest=True, labels=False)
        bR = top.groupby(blk).R.mean()
        rows.append(dict(zip(KEY, k), n_all=len(g), R_all=g.R.mean(), n=len(r), R=r.mean(), R_random5=np.mean(rnd),
                         p=p / 2 if t > 0 else 1 - p / 2, blocks_pos=int((bR > 0).sum()), worst_block=bR.min(),
                         stocks_pos=(top.groupby("sym").R.mean() > 0).mean()))
    S = pd.DataFrame(rows); S["q"] = bh(S.p)
    S["PASS"] = (S.blocks_pos == 4) & (S.q < 0.10) & (S.n >= 300)
    S = S.sort_values("R", ascending=False)
    S.round(4).to_csv(OUT / "eq_top5_summary.csv", index=False)
    pd.set_option("display.width", 250)
    print(S.head(15).round(3).to_string(index=False))
    print("combinations", len(S), "PASS", int(S.PASS.sum()))


if __name__ == "__main__":
    main()
