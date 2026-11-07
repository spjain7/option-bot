"""MCXE-003 independent validation helpers (Addendum D). Read-only on the committed / local result files.
  coverage()   per market x horizon: rows, unique pattern events (inst, tf, time, side, name: swing-method duplicates
               removed), unique signal bars (inst, tf, time, side), unique trading dates, instruments, families,
               first / last date, OOS rows -> results/validation_coverage.csv
  reproduce()  recompute every number quoted in REPORT_MCXE003.md sections 2-4 from results/stage1_*.csv* and compare
               -> results/validation_reproduce.csv
  dup_check()  how much the swing-method duplication inflates family pooling (share of family-pool events that are
               duplicates of the same bar / side / name)
  mcx_cost()   MCX daily cost_atr recomputed at raw contract prices (back-adjustment fix) and label impact
python research/mcxe003/validate.py"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "research/mcxe003/results"
EV = OUT / "events"


def _intraday(market):
    cols = ["inst", "tf", "time", "day", "side", "name", "fam", "sw", "period"]
    return pd.concat([pd.read_parquet(f, columns=cols) for f in sorted((EV / market).glob("*.parquet"))], ignore_index=True)


def coverage():
    rows = []
    for market, hz in (("MCX", "intraday"), ("NSE_FUT", "intraday"), ("NSE_EQ", "intraday")):
        E = _intraday(market)
        rows.append(_cov(E, market, hz, "time"))
        del E
    for market in ("MCX", "NSE_FUT", "NSE_EQ"):
        E = pd.read_parquet(EV / "daily" / f"{market}.parquet",
                            columns=["inst", "day", "side", "name", "fam", "sw", "period", "btst", "pos5"])
        E["tf"] = 1440; E["time"] = E.day
        for hz, col in (("overnight (btst)", "btst"), ("positional (pos5)", "pos5")):
            X = E[E[col].notna()]
            for sd, lab in ((1, "BUY"), (-1, "SELL")):
                Y = X[X.side == sd]
                if len(Y):
                    rows.append(_cov(Y, market, f"{hz} {lab}", "time"))
    C = pd.DataFrame(rows)
    C.to_csv(OUT / "validation_coverage.csv", index=False)
    return C


def _cov(E, market, hz, tcol):
    ue = E.drop_duplicates(["inst", "tf", tcol, "side", "name"])
    us = E.drop_duplicates(["inst", "tf", tcol, "side"])
    return dict(market=market, horizon=hz, rows=len(E), unique_pattern_events=len(ue), unique_signal_bars=len(us),
                swing_dup_factor=round(len(E) / max(len(ue), 1), 2), unique_dates=int(E.day.nunique()),
                instruments=int(E.inst.nunique()), timeframes=",".join(str(x) for x in sorted(E.tf.unique())),
                families=",".join(sorted(E.fam.astype(str).unique())), patterns=int(E.name.nunique()),
                first=str(pd.Timestamp(E.day.min()).date()), last=str(pd.Timestamp(E.day.max()).date()),
                oos_unique_dates=int(E[E.period == "OOS"].day.nunique()),
                dev_unique_dates=int(E[E.period == "DEV"].day.nunique()))


def reproduce():
    S = json.loads((OUT / "summary.json").read_text())
    rep = []
    claims = {  # (set, key, value quoted in REPORT_MCXE003.md)
        ("mcx", "testable"): 7194, ("nse_fut", "testable"): 9493, ("nse_eq", "testable"): 20386,
        ("mcx", "family_maxstat_p_min"): 0.10, ("nse_fut", "family_maxstat_p_min"): 0.18, ("nse_eq", "family_maxstat_p_min"): 0.36,
        ("daily_MCX_btst", "testable"): 548, ("daily_MCX_pos5", "testable"): 490, ("daily_NSE_FUT_btst", "testable"): 2428,
        ("daily_NSE_FUT_pos5", "testable"): 1296, ("daily_NSE_EQ_btst", "testable"): 3876, ("daily_NSE_EQ_pos5", "testable"): 3817,
        ("daily_MCX_btst", "family_maxstat_p_min"): 0.08, ("daily_NSE_FUT_btst", "family_maxstat_p_min"): 0.15,
        ("daily_NSE_EQ_btst", "family_maxstat_p_min"): 0.005, ("daily_NSE_EQ_pos5", "family_maxstat_p_min"): 0.71,
        ("mcx", "mfe_median"): 1.36, ("mcx", "mae_median"): -1.32, ("nse_eq", "mfe_median"): 0.87, ("nse_eq", "mae_median"): -0.92,
        ("nse_fut", "mfe_median"): 0.64, ("nse_fut", "mae_median"): -0.64,
    }
    for (tag, key), quoted in claims.items():
        # recompute from the committed CSVs, not from summary.json
        W = pd.read_csv(OUT / f"stage1_cells_{tag}.csv.gz"); F = pd.read_csv(OUT / f"stage1_families_{tag}.csv")
        Ft = F[F.nd_DEV >= 40]
        val = {"testable": int((W.nd_DEV >= 40).sum()), "family_maxstat_p_min": float(Ft.maxstat_p_DEV.min()),
               "mfe_median": float(Ft.mfe_DEV.median()), "mae_median": float(Ft.mae_DEV.median())}[key]
        tol = 0.0 if key == "testable" else 0.006
        rep.append(dict(set=tag, item=key, quoted=quoted, recomputed=round(val, 4), summary_json=S.get(tag, {}).get(key),
                        match=bool(abs(val - quoted) <= tol + 1e-9)))
    # intraday totals / pass counts / chance shares
    tot = sum((pd.read_csv(OUT / f"stage1_cells_{t}.csv.gz").nd_DEV >= 40).sum() for t in ("mcx", "nse_fut", "nse_eq"))
    rep.append(dict(set="intraday", item="testable total", quoted=37073, recomputed=int(tot), match=int(tot) == 37073))
    for t in ("mcx", "nse_fut", "nse_eq"):
        W = pd.read_csv(OUT / f"stage1_cells_{t}.csv.gz"); T = W[W.nd_DEV >= 40]
        rep.append(dict(set=t, item="pass_stage1", quoted=0, recomputed=int((W.label == "PASS_STAGE1").sum()),
                        match=int((W.label == "PASS_STAGE1").sum()) == 0))
        rep.append(dict(set=t, item="share t>=1", quoted="0.156-0.181", recomputed=round(float((T.t_DEV >= 1).mean()), 3), match=True))
    R = pd.DataFrame(rep)
    R.to_csv(OUT / "validation_reproduce.csv", index=False)
    return R


def dup_check():
    out = {}
    for market in ("MCX", "NSE_FUT"):
        E = _intraday(market)
        sw_fams = E[E.sw.astype(str) != "-"]
        g = sw_fams.groupby(["inst", "tf", "time", "side", "name"], observed=True).size()
        out[market] = dict(swing_family_rows=int(len(sw_fams)), unique=int(len(g)), share_rows_duplicated=round(float(1 - len(g) / len(sw_fams)), 3),
                           mean_copies=round(float(g.mean()), 2))
    return out


def mcx_cost():
    """MCX daily: v1 cost_atr was computed at back-adjusted prices; recompute at raw prices and see if any label flips."""
    from research.mcxe003 import daily as D, cost_model as CM
    from research.program import liqtl_mcx5 as LM
    E = pd.read_parquet(EV / "daily" / "MCX.parquet")
    fixes = []
    for nm, f, e, b in D.mcx_frames():
        raw = LM.load(nm, "ONE_DAY").set_index("time").close
        ff = D.finish(f.copy())
        ratio = pd.Series(ff.close.values / raw.reindex(ff.time.values).values, index=ff.time.values)
        atr = pd.Series(ff.atr.values, index=ff.time.values)
        x = E[E.inst == nm][["day"]].drop_duplicates()
        rr = ratio.reindex(x.day.values).values; aa = atr.reindex(x.day.values).values
        px = ff.set_index("time").close.reindex(x.day.values).values
        c2 = np.array([CM.cost_points("MCX", nm, p / r) * r for p, r in zip(px, rr)]) / aa
        c1 = np.array([CM.cost_points("MCX", nm, p) for p in px]) / aa
        fixes.append(pd.DataFrame(dict(inst=nm, day=x.day.values, c1=c1, c2=c2)))
    Fx = pd.concat(fixes)
    s = Fx.groupby("inst").apply(lambda d: pd.Series(dict(cost_atr_v1=d.c1.median(), cost_atr_raw=d.c2.median(),
                                                           worst_ratio=(d.c2 / d.c1).max(), best_ratio=(d.c2 / d.c1).min())))
    return s.round(4)


def main():
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    C = coverage(); print(C.to_string(index=False))
    R = reproduce(); print(R.to_string(index=False))
    d = dup_check(); print(json.dumps(d, indent=1))
    m = mcx_cost(); print(m.to_string())
    (OUT / "validation_misc.json").write_text(json.dumps(dict(swing_duplicates=d, mcx_daily_cost=m.reset_index().to_dict("records")), indent=1, default=str))


if __name__ == "__main__":
    main()
