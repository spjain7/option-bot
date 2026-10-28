"""STRATEGY-PROGRAM-001 · HIGH-ACCURACY search (the owner's 75–90 % win-rate goal), with economic gates.
Pre-declared family per strategy × side: exits {X3 stop 2 ATR · target 0.5R, X4 stop 3 ATR · target 0.5R} ×
entry filters {none + the 13 harness filters} = 28 variants. Gate in EVERY split (train, validation, test separately):
win rate ≥ 75 %, net expectancy at 2× costs > 0, profit factor ≥ 1.2; train n ≥ 20, validation / test n ≥ 10.
Selection happens on train; validation and test are only checked. ~400 variant tests → chance passes are expected; any
survivor still needs paper testing.   python research/program/run_highacc.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, run_futures as RF  # noqa: E402

OUT = ROOT / "research/program/results"
HX = {"X3 2ATR/0.5R": (2.0, 0.5), "X4 3ATR/0.5R": (3.0, 0.5)}


def one(job):
    ds, name, ex = job
    rows = []
    for strat, df in RF.frames(ds, name, ex):
        if df is None or len(df) < 300:
            continue
        f = H.features(df)
        cost = H.cost_series(name, f, ds)
        sig = H.monthly_signal(f) if strat == "S3" else H.bo_signal(f)
        P = H.LIVE[strat]; start = 60 if strat == "S3" else 210
        for side in (1, -1):
            fl = {"none": np.ones(len(f), bool), **{k: np.asarray(v, bool) for k, v in H.F(f, side).items()}}
            for xl, (k, r) in HX.items():
                for fl_n, m in fl.items():
                    s2 = np.where(m, sig, 0)
                    rows += [dict(t, variant=f"{xl} + {fl_n}", dataset=ds, name=name, strat=strat)
                             for t in H.simulate(f, s2, side, k, r, P["maxh"], P["cap"], cost, start)]
    return rows


def gate(m, nmin):
    return m.get("n", 0) >= nmin and (m.get("win") or 0) >= 75 and (m.get("exp2") or -1) > 0 and (m.get("pf") or 0) >= 1.2


def main():
    with Pool(8) as p:
        rows = [r for x in p.map(one, RF.JOBS) for r in x]
    T = pd.DataFrame(rows)
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T["split"] = [RF.split(d, pd.Series([t]))[0] for d, t in zip(T["dataset"], T["time"])]
    T.to_csv(OUT / "highacc_trades.csv.gz", index=False)
    res = []
    for (ds, st, side, v), G in T.groupby(["dataset", "strat", "side", "variant"]):
        m = {sp: H.metrics(G[G["split"] == sp]) for sp in ("1-train", "2-valid", "3-test")}
        g = [gate(m["1-train"], 20), gate(m["2-valid"], 10), gate(m["3-test"], 10)]
        res.append(dict(dataset=ds, strat=st, side=side, variant=v,
                        **{f"{sp[2:]}_{k}": m[sp].get(k) for sp in m for k in ("n", "win", "exp2", "pf")},
                        verdict="PASS all 3" if all(g) else "train+valid only" if g[0] and g[1] else "train only" if g[0] else "fail"))
    R = pd.DataFrame(res)
    R.to_csv(OUT / "highacc_candidates.csv", index=False)
    L = ["# High-accuracy search (≥75 % wins AND exp at 2× costs > 0 AND PF ≥ 1.2 in every split)\n",
         f"variants tested: {len(R)} · pass train: {(R.verdict != 'fail').sum()} · pass train+valid: "
         f"{R.verdict.isin(['train+valid only', 'PASS all 3']).sum()} · PASS all 3: {(R.verdict == 'PASS all 3').sum()}\n"]
    keep = R[R.verdict != "fail"].sort_values(["verdict", "dataset", "strat", "side"])
    L.append(keep.to_markdown(index=False) if len(keep) else "_no variant passes even the train gate_")
    (OUT / "highacc_tables.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
