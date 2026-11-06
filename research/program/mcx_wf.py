"""MCXE-002 walk-forward selection on the quarter-level ledger (results/mcxe2_quarters.csv.gz).

Stream = (commodity, timeframe, family, sub-type, side). Parameters chosen per stream = (filter, entry, stop, exit) – 80 options.
Rolling selection: at the start of each test quarter 2024Q3 … 2026Q2, pick the option with the best mean net R over the
previous 4 quarters (>= 20 trades and positive, else the stream sits out that quarter); record its result in the test quarter.
UNTOUCHED out-of-sample = 2026Q3 + 2026Q4 (to 3-Nov): the option chosen with the 4 quarters to 2026-06-30, evaluated once.
Output: results/mcxe2_wf.csv (per stream), results/mcxe2_wf_quarters.csv (choices per quarter).
python research/program/mcx_wf.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/program/results"
STREAM = ["name", "tf", "fam", "sub", "side"]
PARAM = ["filt", "entry", "stop", "exit"]
TEST_Q = [str(q) for q in pd.period_range("2024Q3", "2026Q2", freq="Q")]
OOS_Q = ["2026Q3", "2026Q4"]


TAG = sys.argv[1] if len(sys.argv) > 1 else "mcxe2"


def main():
    Q = pd.read_csv(OUT / f"{TAG}_quarters.csv.gz")
    Q["qp"] = pd.PeriodIndex(Q.q, freq="Q")
    choices = []
    for key, g in Q.groupby(STREAM):
        piv = g.pivot_table(index=PARAM, columns="q", values=["n", "s", "ss", "gs", "cs", "w"], aggfunc="sum", fill_value=0)
        qs = sorted(g.q.unique())
        for tq in TEST_Q + ["OOS"]:
            tqp = pd.Period("2026Q3" if tq == "OOS" else tq, freq="Q")
            train = [str(tqp - k) for k in range(1, 5)]
            train = [x for x in train if x in qs]
            if not train:
                continue
            n_tr = piv["n"][train].sum(axis=1); s_tr = piv["s"][train].sum(axis=1)
            m = (s_tr / n_tr.replace(0, np.nan))[(n_tr >= 20)]
            if m.empty or m.max() <= 0:
                choices.append(dict(zip(STREAM, key), test=tq, chosen=None, train_n=int(n_tr.max()), train_R=float(m.max()) if len(m) else np.nan, n=0, s=0.0, gs=0.0, cs=0.0, w=0, ss=0.0))
                continue
            best = m.idxmax()
            test = OOS_Q if tq == "OOS" else [tq]
            test = [x for x in test if x in qs]
            row = dict(zip(STREAM, key), test=tq, chosen="|".join(best), train_n=int(n_tr[best]), train_R=float(m[best]))
            for f in ("n", "s", "gs", "cs", "w", "ss"):
                row[f] = float(piv[f].loc[best, test].sum()) if test else 0.0
            choices.append(row)
    C = pd.DataFrame(choices)
    C.to_csv(OUT / f"{TAG}_wf_quarters.csv", index=False)
    wf = C[C.test != "OOS"]; oos = C[C.test == "OOS"]
    agg = wf.groupby(STREAM).apply(lambda x: pd.Series(dict(
        wf_quarters_traded=int((x.n > 0).sum()), wf_n=int(x.n.sum()), wf_R=x.s.sum() / x.n.sum() if x.n.sum() else np.nan,
        wf_gross=x.gs.sum() / x.n.sum() if x.n.sum() else np.nan, wf_cost=x.cs.sum() / x.n.sum() if x.n.sum() else np.nan,
        wf_quarters_pos=int(((x.n > 0) & (x.s > 0)).sum()), wf_win=100 * x.w.sum() / x.n.sum() if x.n.sum() else np.nan,
        wf_stress=(x.gs.sum() - 2 * x.cs.sum()) / x.n.sum() if x.n.sum() else np.nan)))
    o = oos.set_index(STREAM)[["chosen", "n", "s", "gs", "cs"]].rename(columns={"n": "oos_n"})
    o["oos_R"] = o.s / o.oos_n.replace(0, np.nan); o["oos_stress"] = (o.gs - 2 * o.cs) / o.oos_n.replace(0, np.nan)
    A = agg.join(o[["chosen", "oos_n", "oos_R", "oos_stress"]]).reset_index()
    A["wf_t"] = np.nan
    A.to_csv(OUT / f"{TAG}_wf.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200)
    good = A[(A.wf_n >= 60) & (A.wf_R > 0) & (A.wf_stress > 0) & (A.wf_quarters_pos >= 0.6 * A.wf_quarters_traded)]
    print(f"streams {len(A)} · WF-positive (>= 60 OOS trades, net and 2x-stress > 0, >= 60 % quarters positive): {len(good)}")
    print(good.sort_values("wf_R", ascending=False).round(3).head(40).to_string(index=False))
    print("\nfamily summary (all streams): mean WF net R, share of streams WF-positive")
    fam = A[A.wf_n >= 30].groupby(["fam", "sub"]).apply(lambda x: pd.Series(dict(streams=len(x), wf_R=x.wf_R.mean(), pos=(x.wf_R > 0).mean())))
    print(fam.round(3).sort_values("wf_R", ascending=False).to_string())


if __name__ == "__main__":
    main()
