"""Per-module analysis tables for the final report (reports/mod_*.csv) – all from stage-1 trades, nothing re-tuned.
python -m research.mcx_institutional_buy.statistical_validation.modules"""
import gzip
import io
import subprocess
import warnings
import numpy as np
import pandas as pd
from ..backtesting import runner as RN, context as CX, data as D, metrics as M
from ..strategy_combinations import run as CB

warnings.filterwarnings("ignore")
R_ = RN.REPORTS
P3 = ("TRAIN", "VAL", "OOS")


def s1(tf):
    L = pd.read_csv(R_ / f"stage1_{tf}.csv")
    return CB.add_excess(L.assign(anchor=L.rule), L)


def per_period(T):
    r = {}
    for p in P3:
        s = M.summary(T[T.period == p]); r.update({f"{p}_n": s.get("n", 0), f"{p}_win": s.get("win"), f"{p}_R": s.get("R")})
    return r


def divergence():
    rows, inc = [], []
    for tf in RN.TFS:
        L = s1(tf); d = L[L.module == "A_divergence"]
        for _, r in d[d.exit == "3R"].iterrows():
            rows.append(dict(tf=tf, rule=r.rule, **{f"{p}_{a}": r[f"{p}_{a}"] for p in P3 for a in ("n", "win", "R", "excess")}))
        # incremental value: best individual (TRAIN-selected, regular R3, 3R exit) vs multi-indicator
        ind = d[(d.exit == "3R") & d.rule.str.match(r"DIV_[A-Z0-9]+_REG_R3$") & ~d.rule.str.contains("ANY|MULTI|SEQ") & (d.TRAIN_n >= 30)]
        if len(ind):
            best = ind.sort_values("TRAIN_R", ascending=False).iloc[0]
            for k in ("DIV_MULTI2CLUSTER_R3", "DIV_MULTI3CLUSTER_R3", "DIV_ANY_REG_R3", "DIV_SEQ_RSI14_R3"):
                m = d[(d.rule == k) & (d.exit == "3R")]
                if len(m):
                    m = m.iloc[0]
                    inc.append(dict(tf=tf, best_individual=best.rule, multi=k, **{f"{p}_best_R": best[f"{p}_R"] for p in P3},
                                    **{f"{p}_multi_R": m[f"{p}_R"] for p in P3}, **{f"{p}_multi_n": m[f"{p}_n"] for p in P3},
                                    multi_better_VAL_OOS=bool(m.VAL_R > best.VAL_R and m.OOS_R > best.OOS_R)))
    pd.DataFrame(rows).to_csv(R_ / "mod_divergence.csv", index=False)
    pd.DataFrame(inc).to_csv(R_ / "mod_divergence_multi_vs_best.csv", index=False)
    I = pd.DataFrame(inc)
    print("DIVERGENCE multi vs TRAIN-best individual:\n", I[["tf", "best_individual", "multi", "VAL_best_R", "VAL_multi_R", "OOS_best_R", "OOS_multi_R", "OOS_multi_n", "multi_better_VAL_OOS"]].to_string(index=False))


def simple_module(mod, fname, exits=("2R", "3R", "TRAIL3ATR")):
    rows = []
    for tf in RN.TFS:
        L = s1(tf); d = L[(L.module.isin(mod if isinstance(mod, list) else [mod])) & L.exit.isin(exits)]
        rows.append(d.assign(tf=tf)[["tf", "rule", "exit"] + [f"{p}_{a}" for p in P3 for a in ("n", "win", "R", "excess")] + ["FINAL_PASS"]])
    out = pd.concat(rows); out.to_csv(R_ / fname, index=False)
    g = out.groupby("tf").agg(tests=("rule", "size"), final=("FINAL_PASS", "sum"), med_OOS_R=("OOS_R", "median"), med_OOS_excess=("OOS_excess", "median"))
    print(fname, "\n", g.to_string())
    return out


def sweeps():
    rows = []
    for tf in RN.TFS:
        T = pd.read_parquet(D.CACHE / f"trades_stage1_{tf}.parquet", filters=[("exit", "==", "3R")])
        T = T[T.rule.str.startswith("SWEEP_") & T.rule.str.endswith("_RECLAIM")]
        for name, g in T.groupby("name"):
            F = RN.features(name, tf)
            for rule, gg in g.groupby("rule"):
                base = rule[:-len("_RECLAIM")]
                ev = F["EV"].get(base)
                if ev is None:
                    continue
                i = gg.sig_i.values
                oi = np.full(len(i), np.nan)
                if "oi_daily" in F:
                    od = F["oi_daily"].oi; ch = (od / od.shift(1) - 1).shift(1)
                    day = pd.to_datetime(F["time"][i]).normalize()
                    oi = pd.Series(day).map(ch).values if tf != "1d" else pd.Series(day).map((od / od.shift(1) - 1)).values
                hl = np.asarray(F["COND"]["HL_RECENT"], bool); bos = np.asarray(F["COND"]["BOS_RECENT"], bool)
                n = len(hl)
                fut_hl = np.array([hl[min(k + 1, n - 1):min(k + 11, n)].any() for k in i])
                fut_bos = np.array([bos[min(k + 1, n - 1):min(k + 21, n)].any() for k in i])
                rows.append(pd.DataFrame(dict(tf=tf, sweep=base, name=name, period=gg.period.values, netR=gg.netR.values, mfeR=gg.mfeR.values,
                                              maeR=gg.maeR.values, depth_atr=ev["depth_atr"][i], reclaim_atr=ev["reclaim_atr"][i],
                                              rvol=ev["rvol"][i], oi_chg_prevday=oi, hl_within10=fut_hl, lh_break_within20=fut_bos)))
    E = pd.concat(rows, ignore_index=True)
    E.to_parquet(D.CACHE / "sweep_events.parquet", index=False)
    desc = E.groupby(["tf", "sweep"]).agg(events=("netR", "size"), depth_atr_med=("depth_atr", "median"), reclaim_atr_med=("reclaim_atr", "median"),
                                            rvol_med=("rvol", "median"), oi_chg_med_pct=("oi_chg_prevday", lambda s: 100 * s.median()),
                                            hl_within10_pct=("hl_within10", lambda s: 100 * s.mean()),
                                            lh_break_within20_pct=("lh_break_within20", lambda s: 100 * s.mean()),
                                            mfe_med=("mfeR", "median"), mae_med=("maeR", "median"), R_3R=("netR", "mean"),
                                            win_3R=("netR", lambda s: 100 * (s > 0).mean())).round(2)
    desc.to_csv(R_ / "mod_sweep_events.csv")
    E["depth_bin"] = pd.cut(E.depth_atr, [0, 0.25, 0.5, 1, 2, 99], labels=["<0.25", "0.25-0.5", "0.5-1", "1-2", ">2"])
    E["rvol_bin"] = pd.cut(E.rvol, [0, 1, 1.5, 2.5, 999], labels=["<1", "1-1.5", "1.5-2.5", ">2.5"])
    a = E.groupby(["tf", "depth_bin", "period"]).netR.mean().unstack().round(3)
    b = E.groupby(["tf", "rvol_bin", "period"]).netR.mean().unstack().round(3)
    c = E.groupby(["tf", "hl_within10", "period"]).netR.mean().unstack().round(3)
    a.to_csv(R_ / "mod_sweep_by_depth.csv"); b.to_csv(R_ / "mod_sweep_by_rvol.csv"); c.to_csv(R_ / "mod_sweep_by_later_hl.csv")
    print("SWEEP descriptors\n", desc.to_string()); print(a.to_string()); print(b.to_string())


def cond_tables():
    """support / regime / volume / OI / global conditions: lift on pooled EARLY and CONF trades (3R exit), per timeframe."""
    out = []
    for tf in RN.TFS:
        T = pd.read_parquet(D.CACHE / f"trades_stage1_{tf}.parquet", filters=[("exit", "==", "3R")])
        L = pd.read_csv(R_ / f"stage1_{tf}.csv")
        fam = dict(zip(L.rule, L.family))
        T["family"] = T.rule.map(fam)
        T = T[T.family.isin(["EARLY", "CONF"])]
        T = CX.attach(T, tf)
        cc = [c for c in T.columns if c.startswith("c_") and not c.endswith("_KNOWN")]
        for f_, g in T.groupby("family"):
            x = CX.cond_lift(g, cc); x["tf"] = tf; x["family"] = f_; out.append(x)
    C = pd.concat(out, ignore_index=True); C.to_csv(R_ / "mod_condition_lift.csv", index=False)
    show = ["AT_DSUP", "AT_WSUP", "AT_MSUP", "MIDRANGE", "COUNTER", "TRANSITION", "UPTREND", "RVOL15", "VOLPCT90", "VCLIMAX_RECENT",
            "VEXHAUST", "LOWIMPACT_PROXY", "OI_H1_PDN_VUP_OIUP", "OI_H2_PDN_VUP_OIDN", "OI_H3_PDN_VDN_OIDN", "OI_H4_FLAT_VUNUSUAL",
            "OI_H5_PUP_VUP_OIUP", "OI_H6_PUP_VUP_OIDN", "GLB_UPDAY", "GLB_REV", "GLB_ABOVE5", "GLB_USDINR_UP", "GLB_GSR_FALL"]
    pv = C[C.condition.isin(show)].pivot_table(index=["condition"], columns=["family", "tf"], values="lift_positive_all3", aggfunc="first")
    print("condition lift positive in TRAIN, VAL and OOS (pooled 3R trades):\n", pv.to_string())


def absorption():
    """forward-only best-5 depth: descriptive statistics; no historical test possible."""
    try:
        files = subprocess.check_output(["git", "ls-tree", "-r", "--full-tree", "--name-only", "origin/ws-depth"], cwd=RN.PKG, text=True).split()
    except Exception:
        return
    rows = []
    for f in [x for x in files if x.endswith(".csv.gz")]:
        d = pd.read_csv(io.BytesIO(gzip.decompress(subprocess.check_output(["git", "show", f"origin/ws-depth:{f}"], cwd=RN.PKG))))
        rows.append(d[d.exch == "MCX"])
    d = pd.concat(rows)
    bq = d[[f"A{i}q" for i in range(1, 6)]].sum(axis=1); aq = d[[f"B{i}q" for i in range(1, 6)]].sum(axis=1)   # A* = bid side (see DQ)
    d["imb5"] = (bq - aq) / (bq + aq).replace(0, np.nan); d["tbq_tsq"] = (d.tbq - d.tsq) / (d.tbq + d.tsq).replace(0, np.nan)
    s = d.groupby("name").agg(snapshots=("imb5", "size"), imb5_mean=("imb5", "mean"), imb5_sd=("imb5", "std"),
                              total_bid_ask_imb_mean=("tbq_tsq", "mean"), first=("time", "min"), last=("time", "max")).round(3)
    s["status"] = "FORWARD ONLY – no historical depth; absorption / volume-delta / footprint not testable historically"
    s.to_csv(R_ / "mod_absorption_forward_depth.csv"); print(s.to_string())


def timeframes():
    rows = []
    for tf in RN.TFS:
        L = s1(tf); T = pd.read_parquet(D.CACHE / f"trades_stage1_{tf}.parquet", columns=["netR", "grossR", "rule"])
        rows.append(dict(tf=tf, tests=len(L), oos_pass=int(L.OOS_PASS.sum()), final_pass=int(L.FINAL_PASS.sum()),
                         avg_cost_R=round(float((T.grossR - T.netR).mean()), 3),
                         random_samestop_3R_OOS=L[(L.rule == "BASE_RANDOM_EVERY10_SAMESTOP") & (L.exit == "3R")].OOS_R.iloc[0],
                         random_highbo_3R_OOS=L[(L.rule == "BASE_RANDOM10_HIGHBO") & (L.exit == "3R")].OOS_R.iloc[0],
                         early_final=int(L[L.family == "EARLY"].FINAL_PASS.sum()), conf_final=int(L[L.family == "CONF"].FINAL_PASS.sum()),
                         early_tests=int((L.family == "EARLY").sum()), conf_tests=int((L.family == "CONF").sum())))
    X = pd.DataFrame(rows); X.to_csv(R_ / "mod_timeframes.csv", index=False); print(X.to_string(index=False))


def main():
    divergence()
    simple_module("B_rsi", "mod_rsi_oversold.csv"); simple_module("B_rsi_cont", "mod_rsi_continuation.csv")
    simple_module("B_candle", "mod_candles.csv"); simple_module("C_sweep", "mod_sweep_rules.csv")
    simple_module(["D_volume", "D_volume_oi"], "mod_volume_oi_rules.csv"); simple_module("F_structure", "mod_structure_rules.csv")
    sweeps(); cond_tables(); absorption(); timeframes()


if __name__ == "__main__":
    main()
