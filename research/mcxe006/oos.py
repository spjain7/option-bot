"""MCXE-006 OOS evaluation – run ONCE on the frozen list (FROZEN.md). For each candidate:
  OOS trades at 1x / 2x cost, register.classify, matched random-entry control (same instruments, sides, count per
  instrument, exits, 50 seeds), breakdowns by instrument / side / month / regime / exit type, BH across candidates.
python research/mcxe006/oos.py -> results/oos_results.json, results/oos_trades_<id>.parquet"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe006 import engine as EN, strategies as ST  # noqa: E402
from research.mcxe006.experiments import EXPS  # noqa: E402
from research.mcxe006.lab import run_exp, extra_for  # noqa: E402
from research.mcxe004 import register as RG, window as W  # noqa: E402

FROZEN = ["H1.11", "H1.12L", "H5.2L"]
D = ROOT / "research/mcxe006"
OUT = D / "results/oos_results.json"


def control(e, T, seeds=50):
    """random entries inside OOS with the same per-instrument counts and side mix, same exit rules."""
    fs = []
    for tf in (e["tf"] if isinstance(e["tf"], list) else [e["tf"]]):
        fs += EN.frames(e["universe"], tf)
    want = T.groupby(["inst"]).side.agg(list).to_dict()
    res = []
    for s in range(seeds):
        rng = np.random.default_rng(1000 + s)

        def rnd(f, extra=None, **kw):
            n = len(f); side = np.zeros(n, int)
            per = np.asarray(W.period(f.time, f.attrs["wkey"]))
            cand = np.flatnonzero((per == "OOS") & f.sig_ok.values.astype(bool))
            sides = want.get(f.attrs["name"], [])
            if len(cand) and sides:
                pick = rng.choice(cand, size=min(len(sides), len(cand)), replace=False)
                side[np.sort(pick)] = rng.permutation(sides)[:len(pick)]
            return dict(side=side, dist=e["params"].get("k", 2.0) * f.atr.values, warm=60)
        C = EN.run(fs, rnd, {}, e["exit"], e["horizon"], oos=True)
        C = C[C.period == "OOS"]
        res.append(C.r1.mean() if len(C) else np.nan)
    return float(np.nanmean(res)), float(np.nanpercentile(res, 95))


def main():
    if OUT.exists():
        raise SystemExit("OOS already evaluated – results/oos_results.json exists (run once rule)")
    out = {}
    pvals = []
    for i in FROZEN:
        e = EXPS[i]
        T = run_exp(e, oos=True)
        O = T[T.period == "OOS"].copy()
        O.to_parquet(D / "results" / f"oos_trades_{i}.parquet", index=False)
        m1, m2 = RG.metrics(O.assign(date=O.date), "r1"), RG.metrics(O.assign(date=O.date), "r2")
        st, why = RG.classify(m1, m2, "positional", selection_overlaps_window=False, controls_run=True)
        cmean, c95 = control(e, O)
        # day-clustered one-sided p (daily mean R)
        dm = O.groupby(O.date.dt.normalize()).r1.sum()
        p = float(stats.ttest_1samp(dm, 0, alternative="greater").pvalue) if len(dm) > 2 else 1.0
        pvals.append(p)
        O["month"] = O.date.dt.to_period("M").astype(str)
        out[i] = dict(status=st, reason=why, oos_1x=m1, oos_2x=m2, control_random_entry_mean=round(cmean, 4),
                      control_random_entry_p95=round(c95, 4), p_day_clustered=round(p, 4),
                      by_inst=O.groupby("inst").r1.agg(["size", "mean"]).round(3).to_dict("index"),
                      by_side=O.groupby("side").r1.agg(["size", "mean"]).round(3).to_dict("index"),
                      by_month=O.groupby("month").r1.agg(["size", "mean", "sum"]).round(3).to_dict("index"),
                      by_regime=O.groupby("regime").r1.agg(["size", "mean"]).round(3).to_dict("index"),
                      by_exit=O.groupby("etype").r1.agg(["size", "mean"]).round(3).to_dict("index"),
                      without_best5=round(float(O.sort_values("r1").r1.iloc[:-5].mean()), 4) if len(O) > 5 else None,
                      stop_pct=round(100 * O.etype.isin(["stop", "gap"]).mean(), 1), median_hold=float(O.hold.median()))
        print(i, st, why, json.dumps({k: m1[k] for k in ("trades", "unique_dates", "win_rate", "expectancy_R", "profit_factor", "max_drawdown_R", "ci95")}),
              "2x", m2["expectancy_R"], "control", round(cmean, 3), flush=True)
    # BH across the frozen candidates
    p = np.asarray(pvals); k = len(p); o = np.argsort(p)
    q = np.empty(k); q[o] = np.minimum.accumulate((p[o] * k / np.arange(1, k + 1))[::-1])[::-1]
    q = np.minimum(q, 1.0)
    for j, i in enumerate(FROZEN):
        out[i]["bh_q"] = round(float(q[j]), 4)
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({i: (out[i]["status"], out[i]["bh_q"]) for i in FROZEN}))


if __name__ == "__main__":
    main()
