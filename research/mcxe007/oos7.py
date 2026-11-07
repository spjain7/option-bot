"""MCXE-007 OOS – run ONCE on FROZEN.md. Writes results/oos7_results.json and results/oos7_trades_<id>.parquet.
python research/mcxe007/oos7.py"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe007 import engine7 as EN, data7 as DA, lab7 as LB  # noqa: E402
from research.mcxe007.exp7 import EXPS  # noqa: E402
from research.mcxe004 import register as RG, window as W  # noqa: E402

FROZEN = ["SE_failed_oiup_h/L"]
D = ROOT / "research/mcxe007"
OUT = D / "results/oos7_results.json"


def rnd_control(e, side, T, seeds=50):
    fs = {f.attrs["name"]: f for f in DA.frames(e["market"])}
    want = T.groupby("inst").size().to_dict()
    res = []
    for s in range(seeds):
        rng = np.random.default_rng(9000 + s)

        def rnd(f, side, extra=None, **kw):
            n = len(f); sig = np.zeros(n, bool)
            per = np.asarray(W.period(f.time, f.attrs["wkey"]))
            cand = np.flatnonzero((per == "OOS") & f.sig_ok.values.astype(bool) & (np.arange(n) >= 30))
            k = want.get(f.attrs["name"], 0)
            if k and len(cand):
                sig[rng.choice(cand, size=min(k, len(cand)), replace=False)] = True
            return dict(sig=sig, warm=30, entry="open")
        C = EN.run([fs[x] for x in want], rnd, {}, e.get("exit", {}), side, oos=True, extra=LB.extra())
        if e.get("hedge"):
            C = LB.hedge(C)
        C = C[C.period == "OOS"]
        res.append(C.r2.mean() if len(C) else np.nan)
    return round(float(np.nanmean(res)), 4), round(float(np.nanpercentile(res, 95)), 4)


def main():
    if OUT.exists():
        raise SystemExit("OOS already evaluated (results/oos7_results.json exists) – run-once rule")
    out = {}
    for rid in FROZEN:
        i, sfx = rid.split("/"); e = EXPS[i]; side = 1 if sfx == "L" else -1
        T = LB.run_exp(e, side, oos=True)
        O = T[T.period == "OOS"].copy()
        O.to_parquet(D / "results" / f"oos7_trades_{rid.replace('/', '_')}.parquet", index=False)
        m1 = RG.metrics(O.assign(date=O.date), "r1"); m2 = RG.metrics(O.assign(date=O.date), "r2")
        st, why = RG.classify(m1, m2, "positional", selection_overlaps_window=True, controls_run=True)
        em = EN.metrics(O, "r2")
        cm, c95 = rnd_control(e, side, O)
        nd = O.date.dt.normalize().nunique()
        days = len(pd.bdate_range(W.get("NSE_FUT")["oos_from"], W.get("NSE_FUT")["reference"]))
        out[rid] = dict(status=st, reason=why, oos_1x=m1, oos_2x=m2,
                        wo_top1_2x=em["wo_top1"], wo_top3_2x=em["wo_top3"], wo_top5_2x=em["wo_top5"],
                        random_hedged_control_2x=cm, random_control_p95=c95,
                        rs_net_per_trade_1x=round(float(O.rs_net_1x.mean()), 0), rs_net_total_1x=round(float(O.rs_net_1x.sum()), 0),
                        exposure_avg_open_positions=round(float(O.hold.sum() / days), 2), turnover_trades_per_month=round(len(O) / 3, 1),
                        hedge_R_mean=round(float(O.hedge_R.mean()), 4) if "hedge_R" in O else None,
                        **EN.concentration(O),
                        by_month=O.groupby(O.date.dt.to_period("M").astype(str)).r2.agg(["size", "mean", "sum"]).round(3).to_dict("index"),
                        by_regime=O.groupby("regime").r2.agg(["size", "mean"]).round(3).to_dict("index"),
                        by_exit=O.groupby("etype").r2.agg(["size", "mean"]).round(3).to_dict("index"),
                        top_insts=O.groupby("inst").r2.agg(["size", "sum"]).sort_values("sum").round(3).tail(5).to_dict("index"),
                        signal_dates=nd)
        print(rid, st, why, json.dumps({k: m1[k] for k in ("trades", "unique_dates", "win_rate", "avg_win", "avg_loss", "expectancy_R", "profit_factor",
                                                             "max_drawdown_R", "ci95")}), "2x", m2["expectancy_R"], "ctrl", cm, c95, flush=True)
    OUT.write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
