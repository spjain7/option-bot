"""v2 evidence-first redesign tests (research / paper only).

  python -m research.audit_v2     # Phase 1 audit (run first)
  python -m research.run_v2       # Phases 3 & 6 -> research/output_v2/

Data: Angel MCX front-month daily, data holes flagged (no entries for 60 bars after a hole, trades spanning a hole
marked invalid and excluded), back-adjusted by ESTIMATED roll gaps ("REAL-EST-ADJ"). The unadjusted series is also run.
Periods = the v1 MCX_DAILY_REAL periods (unchanged). Criteria = research/CRITERIA.md (unchanged).
Selection of improvements uses TRAIN + VALIDATION only; OOS is reported, never used to choose.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research import engine_daily as ED, roll_adjust as RA, metrics as MT, portfolio_mtm as PM
from research.run_all import split, walk_forward, GRID_C, GRID_B, grade

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output_v2"
COMMOD = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]
PERIODS = ("2005-12-31", "2016-05-27", "2021-08-08")     # identical to v1 MCX_DAILY_REAL (proportional rule)
WF_FROM = 2017
CAPITAL = 2_500_000
COUNT = {"variants": 0}

BASE = dict(ED.STRATS["C"])
# one feature at a time, each in long/short and long-only form
FEATURES = {
    "base (C)": {},
    "+RSI block (>70 no BUY, <30 no SELL)": dict(rsi_block=True),
    "+lagged volume ≥1.5x": dict(vol=1.5, vol_lag=True),
    "+regime (ADX≥20, ATR% 10-90 pct)": dict(regime=True),
    "exit: 10-day channel": dict(exit=10),
    "exit: 3 ATR trailing stop": dict(exit_mode="trail", trail_atr=3.0),
    "+chase limit 0.5 ATR": dict(chase=0.5),
}
SIDES = {"long/short": (1, -1), "long-only": (1,)}


def w(df, *parts):
    f = OUT.joinpath(*parts); f.parent.mkdir(parents=True, exist_ok=True); df.to_csv(f, index=False); return f


def frames(adjusted):
    return {n: ED.add_indicators(RA.load_mcx(n, adjusted)[0]) for n in COMMOD}


def run(fr, over, cost_x=1.0):
    COUNT["variants"] += 1
    ts = [ED.run(n, d, {**BASE, **over}, cost_x) for n, d in fr.items()]
    t = pd.concat([x for x in ts if not x.empty], ignore_index=True)
    return t[t["valid"]] if "valid" in t else t, int((~t["valid"]).sum()) if "valid" in t else 0


def evaluate(fr, label, over, data_grade="REAL-EST-ADJ", grid=GRID_C):
    t, invalid = run(fr, over)
    tr, va, oos = split(t, PERIODS)
    s = {p: MT.stats(x) for p, x in (("train", tr), ("validation", va), ("oos", oos))}
    stress2 = MT.stats(split(run(fr, over, 2.0)[0], PERIODS)[2]).get("expectancy_R", np.nan)
    before = MT.stats(split(run(fr, over, 0.0)[0], PERIODS)[2]).get("expectancy_R", np.nan)
    grid = [(g, run(fr, {**over, **g})[0]) for g in grid]
    oe = [MT.stats(split(x, PERIODS)[2]).get("expectancy_R", np.nan) for _, x in grid]
    wf, _ = walk_forward(grid, WF_FROM)
    wfo = MT.period(wf, PERIODS[2]) if not wf.empty else wf
    row = dict(variant=label, train_trades=s["train"].get("trades", 0), train_exp_R=s["train"].get("expectancy_R"),
               val_trades=s["validation"].get("trades", 0), val_exp_R=s["validation"].get("expectancy_R"),
               oos_trades=s["oos"].get("trades", 0), oos_exp_R=s["oos"].get("expectancy_R", np.nan),
               oos_exp_R_before_costs=before, oos_pf=s["oos"].get("pf", np.nan), oos_win_pct=s["oos"].get("win_pct"),
               oos_boot_p5=s["oos"].get("boot_p5_R", np.nan), oos_max_dd_R=s["oos"].get("max_dd_R", np.nan),
               oos_years_pos=s["oos"].get("years_pos_pct", np.nan), oos_exp_R_2x=stress2,
               stability_pct=round(np.nanmean([e > 0 for e in oe]) * 100),
               wf_exp_R=round(wfo["net_R"].mean(), 3) if not wfo.empty else np.nan,
               oos_long_exp_R=s["oos"].get("long_exp_R"), oos_short_exp_R=s["oos"].get("short_exp_R"),
               oos_max_consec_losses=s["oos"].get("max_consec_losses"), oos_avg_days=s["oos"].get("avg_days"),
               invalid_trades_excluded=invalid,
               top5_share_oos_pct=round(oos.net_R.nlargest(5).sum() / oos.net_R.sum() * 100) if len(oos) and oos.net_R.sum() > 0 else np.nan)
    row["grade"], f = grade(row, data_grade, False)
    row["missed"] = "; ".join(f)
    return row, t


def main():
    OUT.mkdir(exist_ok=True)
    fa, fu = frames(True), frames(False)
    rows, trades = [], {}
    # ---- corrected comparison of the v1 daily strategies (B..H4) on corrected data
    corr = []
    for s in ["B", "C", "D", "E", "G", "H1", "H2", "H4"]:
        for tag, fr in (("unadjusted+holes", fu), ("est-adjusted+holes", fa)):
            r, _ = evaluate(fr, s, ED.STRATS[s], grid=GRID_B if s == "B" else GRID_C)
            corr.append(dict(strategy=s, data=tag, **{k: r[k] for k in ("oos_trades", "oos_exp_R", "oos_pf", "oos_boot_p5",
                                                                       "val_exp_R", "stability_pct", "wf_exp_R", "grade", "missed")}))
            print("corrected", s, tag, r["oos_exp_R"], r["grade"], flush=True)
    w(pd.DataFrame(corr), "corrected_comparison_mcx_daily.csv")

    # ---- one feature at a time
    for side_lbl, sides in SIDES.items():
        for f_lbl, over in FEATURES.items():
            lbl = f"{f_lbl} | {side_lbl}"
            r, t = evaluate(fa, lbl, {**over, "sides": sides})
            r.update(feature=f_lbl, sides=side_lbl, kind="single")
            rows.append(r); trades[lbl] = t
            print(lbl, "val", r["val_exp_R"], "oos", r["oos_exp_R"], r["grade"], flush=True)
    rows.append(dict(variant="+OI confirmation", feature="+OI confirmation", sides="both", kind="single",
                     grade="NOT TESTED", missed="MCX historical OI not available (Angel does not serve it) – missing, not negative"))
    single = pd.DataFrame(rows)
    # ---- combinations: features that beat base in BOTH train and validation (chosen without looking at OOS)
    combos = []
    for side_lbl, sides in SIDES.items():
        b = single[(single.feature == "base (C)") & (single.sides == side_lbl)].iloc[0]
        better = single[(single.sides == side_lbl) & (single.kind == "single") & (single.feature != "base (C)")
                        & (single.train_exp_R > b.train_exp_R) & (single.val_exp_R > b.val_exp_R)]
        feats = better.feature.tolist()
        exits = [f for f in feats if f.startswith("exit:")]
        if len(exits) > 1:                                        # only one exit rule can be active: keep best by validation
            keep = better[better.feature.isin(exits)].sort_values("val_exp_R").feature.iloc[-1]
            feats = [f for f in feats if not f.startswith("exit:") or f == keep]
        if len(feats) >= 2:
            over = {}
            for f in feats:
                over.update(FEATURES[f])
            lbl = " + ".join(feats) + f" | {side_lbl}"
            r, t = evaluate(fa, lbl, {**over, "sides": sides})
            r.update(feature="COMBO: " + ", ".join(feats), sides=side_lbl, kind="combo")
            combos.append(r); trades[lbl] = t
            print("combo", lbl, r["oos_exp_R"], r["grade"], flush=True)
    allv = pd.concat([single, pd.DataFrame(combos)], ignore_index=True)
    base_val = {s: allv[(allv.feature == "base (C)") & (allv.sides == s)].val_exp_R.iloc[0] for s in SIDES}
    allv["val_delta_vs_base"] = allv.apply(lambda r: round(r.val_exp_R - base_val.get(r.sides, np.nan), 3)
                                           if pd.notna(r.get("val_exp_R")) and r.sides in base_val else np.nan, axis=1)
    allv = allv.sort_values(["val_delta_vs_base"], ascending=False, na_position="last")
    allv.insert(0, "rank_by_validation", range(1, len(allv) + 1))
    w(allv, "improvements_ranked.csv")
    for lbl, t in trades.items():
        safe = "".join(c if c.isalnum() else "_" for c in lbl)[:90]
        w(t, "trades", f"{safe}.csv")

    # ---- Phase 6: risk levels with portfolio limits (MTM, margin, correlated groups, daily loss), OOS and full
    cands = ["base (C) | long/short", "base (C) | long-only"] + [c["variant"] for c in combos]
    risk_rows = []
    for lbl in cands:
        t = trades[lbl].copy()
        for rp in (0.0025, 0.005, 0.01):
            for per, tt in (("oos", MT.period(t, PERIODS[2])), ("full", t)):
                tl, eq, s = PM.simulate(tt, fa, CAPITAL, risk_pct=rp, max_pos=5, max_open_risk=4 * rp, group_risk=2 * rp,
                                        max_capital_use=0.5, daily_loss=0.03)
                risk_rows.append(dict(variant=lbl, risk_per_trade_pct=rp * 100, period=per, **s))
                if per == "oos" and not eq.empty:
                    safe = "".join(c if c.isalnum() else "_" for c in lbl)[:70]
                    w(eq, "equity", f"{safe}_risk{rp * 100:g}.csv")
    w(pd.DataFrame(risk_rows), "risk_levels_portfolio.csv")
    (OUT / "run_v2_config.json").write_text(json.dumps(dict(periods=PERIODS, wf_from=WF_FROM, capital=CAPITAL, base=BASE,
                                                            features=FEATURES, variants_run=COUNT["variants"]), indent=1, default=str))
    print("variants run:", COUNT["variants"])


if __name__ == "__main__":
    main()
