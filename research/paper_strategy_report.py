"""Validation report for the exact paper configuration (long-only, 55/20, 200d, 2 ATR, RSI>70 blocks BUY,
0.5 ATR chase limit) on the Angel MCX daily series with data holes excluded and ESTIMATED roll adjustment.

  python -m research.paper_strategy_report   -> research/output_v3/

Periods are the v1/v2 periods (train → 27-May-2016, validation → 07-Aug-2021, OOS from 08-Aug-2021).
All of them were already inspected earlier in this project; nothing here is untouched test data.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research import engine_daily as ED, roll_adjust as RA, metrics as MT, portfolio_mtm as PM
from research.run_all import split, walk_forward, GRID_C, grade

OUT = Path(__file__).resolve().parent / "output_v3"
NAMES = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]
PERIODS = ("2005-12-31", "2016-05-27", "2021-08-08")
PAPER = dict(rsi_block=True, sides=(1,), chase=0.5)


def run(fr, over=None, cost_x=1.0):
    t = pd.concat([ED.run(n, d, {**PAPER, **(over or {})}, cost_x) for n, d in fr.items()], ignore_index=True)
    return t[t.valid]


def main():
    OUT.mkdir(exist_ok=True)
    fr = {n: ED.add_indicators(RA.load_mcx(n, adjusted=True)[0]) for n in NAMES}
    t = run(fr)
    t.to_csv(OUT / "paper_config_trades_all.csv", index=False)
    tr, va, oos = split(t, PERIODS)
    rep = {"config": PAPER, "periods": PERIODS, "note": "all periods previously inspected; estimated roll adjustment"}
    for lab, x in (("train", tr), ("validation", va), ("oos", oos), ("full", t)):
        rep[lab] = MT.stats(x)
    # costs
    rep["cost_sensitivity_oos_expectancy_R"] = {f"{c:g}x": MT.stats(split(run(fr, cost_x=c), PERIODS)[2]).get("expectancy_R")
                                                for c in (0, 1, 2, 3)}
    # parameter stability (27 neighbours) + walk-forward
    grid = [(g, run(fr, g)) for g in GRID_C]
    st = pd.DataFrame([dict(**g, oos_trades=len(split(x, PERIODS)[2]), oos_expectancy_R=MT.stats(split(x, PERIODS)[2]).get("expectancy_R"))
                       for g, x in grid])
    st.to_csv(OUT / "parameter_stability.csv", index=False)
    rep["stability_pct_positive"] = round((st.oos_expectancy_R > 0).mean() * 100)
    wf, picks = walk_forward(grid, 2017)
    pd.DataFrame(picks).to_csv(OUT / "walkforward.csv", index=False)
    wfo = MT.period(wf, PERIODS[2])
    rep["walk_forward_oos_expectancy_R"] = round(wfo.net_R.mean(), 3) if len(wfo) else None
    # breakdowns (OOS)
    o = oos.copy(); o["year"] = pd.to_datetime(o.exit_time).dt.year
    by = lambda col: {str(k): dict(trades=int(len(g)), expectancy_R=round(g.net_R.mean(), 3), total_R=round(g.net_R.sum(), 1))
                      for k, g in o.groupby(col)}
    rep["oos_by_instrument"], rep["oos_by_year"], rep["oos_by_exit"] = by("instrument"), by("year"), by("exit_reason")
    rep["oos_gap_stop_trades"] = int((o.exit_reason == "gap_stop").sum())
    rep["oos_gap_stop_R"] = round(o.loc[o.exit_reason == "gap_stop", "net_R"].sum(), 2)
    rep["oos_top5_share_pct"] = round(o.net_R.nlargest(5).sum() / o.net_R.sum() * 100) if o.net_R.sum() > 0 else None
    rep["oos_without_top5_expectancy_R"] = round(o.drop(o.net_R.nlargest(5).index).net_R.mean(), 3) if len(o) > 5 else None
    # account level at 0.5% risk (MTM, margin, group limits, daily-loss)
    tl, eq, s = PM.simulate(oos, fr, 2_500_000, risk_pct=0.005, max_pos=5, max_open_risk=0.02, group_risk=0.01,
                            max_capital_use=0.5, daily_loss=0.03)
    rep["oos_account_0.5pct"] = s
    if not eq.empty:
        eq.to_csv(OUT / "oos_equity_0.5pct.csv", index=False)
        m = eq.set_index("date").equity.resample("ME").last().pct_change().dropna()
        rep["oos_monthly_pct"] = {str(k.date())[:7]: round(v * 100, 2) for k, v in m.items()}
        rep["oos_max_dd_rs"] = round((eq.equity - eq.equity.cummax()).min())
    # data coverage
    cov = {}
    for n in NAMES:
        d, tab = RA.load_mcx(n, adjusted=True)
        g = d.time.diff().dt.days
        cov[n] = dict(first=str(d.time.min().date()), bars=len(d), holes=int((g > 7).sum()), rolls_detected=len(tab),
                      rolls_expected_per_year=len(RA.RULES[n][0]))
    rep["data_coverage"] = cov
    rep["unsupported_or_missing"] = {"MCX open interest history": "not served by Angel – OI filter cannot be validated",
                                     "expired MCX contracts": "not served – historical roll gaps are estimates",
                                     "Crude roll detection": f"{cov['CRUDEOIL']['rolls_detected']} rolls found vs ~12/yr expected – undetected rolls stay in the series"}
    row = dict(oos_exp_R=rep["oos"].get("expectancy_R"), oos_boot_p5=rep["oos"].get("boot_p5_R"), oos_trades=rep["oos"].get("trades"),
               oos_pf=rep["oos"].get("pf"), oos_exp_R_2x=rep["cost_sensitivity_oos_expectancy_R"]["2x"],
               val_exp_R=rep["validation"].get("expectancy_R"), oos_years_pos=rep["oos"].get("years_pos_pct"),
               stability_pct=rep["stability_pct_positive"], wf_exp_R=rep["walk_forward_oos_expectancy_R"],
               oos_max_dd_R=rep["oos"].get("max_dd_R"))
    rep["grade"], rep["missed"] = grade(row, "REAL-EST-ADJ", False)
    (OUT / "paper_strategy_report.json").write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps({k: rep[k] for k in ("grade", "missed", "oos", "cost_sensitivity_oos_expectancy_R", "stability_pct_positive",
                                          "walk_forward_oos_expectancy_R", "oos_top5_share_pct", "oos_without_top5_expectancy_R",
                                          "oos_account_0.5pct")}, indent=1, default=str))


if __name__ == "__main__":
    main()
