"""MCXE-003 summary numbers for the report (reads results/stage1_*.csv*). Prints markdown-ready tables and writes
results/summary.json.   python research/mcxe003/report.py"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/mcxe003/results"
SETS = [("mcx", "MCX intraday"), ("nse_fut", "NSE stock futures intraday (1h)"), ("nse_eq", "NSE cash intraday"),
        ("daily_MCX_btst", "MCX overnight (BTST/STBT)"), ("daily_MCX_pos5", "MCX positional (5 sessions)"),
        ("daily_NSE_FUT_btst", "NSE stock futures overnight (BTST/STBT)"), ("daily_NSE_FUT_pos5", "NSE stock futures positional"),
        ("daily_NSE_EQ_btst", "NSE cash BTST (BUY)"), ("daily_NSE_EQ_pos5", "NSE cash positional (BUY)")]


def one(tag):
    cf, ff = OUT / f"stage1_cells_{tag}.csv.gz", OUT / f"stage1_families_{tag}.csv"
    if not cf.exists():
        return None
    W = pd.read_csv(cf); F = pd.read_csv(ff)
    T = W[W.nd_DEV >= 40]
    nt = len(T)
    lab = W.label.value_counts().to_dict()
    Ft = F[F.nd_DEV >= 40]
    best = Ft.sort_values("t_DEV", ascending=False).iloc[0] if len(Ft) else None
    r = dict(cells=int(len(W)), testable=int(nt), labels=lab,
             share_t_ge1=round(float((T.t_DEV >= 1).mean()), 3), chance_t_ge1=round(float(stats.norm.sf(1)), 3),
             share_t_le_m2=round(float((T.t_DEV <= -2).mean()), 3), chance_t_le_m2=round(float(stats.norm.cdf(-2)), 3),
             pass_stage1=int((W.label == "PASS_STAGE1").sum()),
             family_rows=int(len(Ft)), family_dev_valid_both_pos=round(float(((Ft.m_DEV > 0) & (Ft.m_VALID > 0)).mean()), 3),
             family_maxstat_p_min=round(float(Ft.maxstat_p_DEV.min()), 3), maxstat95=round(float(F.maxstat_95.iat[0]), 2),
             cost_atr_median=round(float(Ft.cost_DEV.median()), 3), raw_abs_median=round(float(Ft.raw_DEV.abs().median()), 3),
             excess_abs_median=round(float(Ft.m_DEV.abs().median()), 3),
             spent_median=round(float((Ft.x_fd_DEV - Ft.m_DEV).median()), 3),
             mfe_median=round(float(Ft.mfe_DEV.median()), 2), mae_median=round(float(Ft.mae_DEV.median()), 2))
    if best is not None:
        r["best_family"] = dict(name=f"{best['fam']} {best['name']} {'BUY' if best.side > 0 else 'SELL'} tf{int(best.tf)}",
                                nd=int(best.nd_DEV), x_DEV=round(float(best.m_DEV), 3), t_DEV=round(float(best.t_DEV), 2),
                                x_VALID=round(float(best.m_VALID), 3) if best.m_VALID == best.m_VALID else None,
                                maxstat_p=round(float(best.maxstat_p_DEV), 3), raw_DEV=round(float(best.raw_DEV), 3),
                                cost=round(float(best.cost_DEV), 3))
    if "tf" in F:
        r["by_tf"] = {int(k): dict(cost=round(float(g.cost_DEV.median()), 3), raw_abs=round(float(g.raw_DEV.abs().median()), 3),
                                   x_abs=round(float(g.m_DEV.abs().median()), 3)) for k, g in Ft.groupby("tf")}
    return r


def main():
    res = {}
    for tag, lab in SETS:
        r = one(tag)
        if r:
            res[tag] = dict(label=lab, **r)
            print(f"\n## {lab} [{tag}]\n" + json.dumps(r, indent=1, default=str))
    (OUT / "summary.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
