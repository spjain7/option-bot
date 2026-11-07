"""Robustness of MCXE-006 candidates on DEV + VALID only (OOS never computed here):
per instrument, per month, without the best 5 trades, by side, by regime, cost 3x.
python research/mcxe006/robustness.py H1.11 H1.12L ... -> results/robustness_<id>.txt"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "research/mcxe006"


def rep(i):
    T = pd.read_parquet(D / "results" / f"trades_{i}.parquet")
    assert not (T.period == "OOS").any()
    T["r3"] = T.r1 - 2 * T.cost_R
    L = [f"# {i}  (DEV + VALID only)", ""]
    pd.set_option("display.width", 200)
    L.append(T.groupby(["inst", "period"]).r2.agg(["size", "mean"]).round(3).unstack().to_string()); L.append("")
    T["month"] = T.date.dt.to_period("M")
    mm = T.groupby("month").r2.agg(["size", "sum"]).round(2)
    L.append("monthly net R (2x): " + ", ".join(f"{k}:{v:+.1f}({n})" for k, (n, v) in mm.iterrows()))
    L.append(f"positive months: {(mm['sum'] > 0).sum()} / {len(mm)}")
    s = T.sort_values("r2")
    L.append(f"exp 2x all {T.r2.mean():+.3f} | without best 5 {s.r2.iloc[:-5].mean():+.3f} | without best 10 {s.r2.iloc[:-10].mean():+.3f} | 3x cost {T.r3.mean():+.3f}")
    L.append(f"share of net R from best 5 trades: {s.r2.iloc[-5:].sum() / T.r2.sum():.0%}")
    L.append(T.groupby(["side", "period"]).r2.agg(["size", "mean"]).round(3).unstack().to_string())
    L.append(T.groupby(["regime"]).r2.agg(["size", "mean"]).round(3).T.to_string())
    L.append(T.groupby("etype").r2.agg(["size", "mean"]).round(3).T.to_string())
    L.append(f"median hold bars {T.hold.median()}, median MFE {T.mfe.median():.2f}R, median MAE {T.mae.median():.2f}R")
    out = "\n".join(L)
    (D / "results" / f"robustness_{i}.txt").write_text(out)
    return out


if __name__ == "__main__":
    for i in sys.argv[1:]:
        print(rep(i)); print()
