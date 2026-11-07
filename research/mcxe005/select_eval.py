"""MCXE-005 selection and evaluation (PREREGISTRATION.md).
  python research/mcxe005/select_eval.py freeze   – reads ONLY DEV + VALID trades (OOS rows are dropped at load), writes
                                                   STRATEGY_EXPERIMENT_REGISTER.csv (every cell, DEV/VALID metrics,
                                                   selection outcome + failure reason), results/frozen_survivors.csv,
                                                   results/ablation_filters.csv. Commit before running `oos`.
  python research/mcxe005/select_eval.py oos      – reads the frozen list, evaluates OOS ONCE, matched random-entry
                                                   controls, register.classify -> results/oos_survivors.csv (+ register update)
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe004 import register as RG  # noqa: E402

D = ROOT / "research/mcxe005"
RES = D / "results"
CELLS = ["mcx_intraday", "mcx_positional", "eq_intraday", "eq_daily", "fut_intraday", "fut_daily"]
KEY = ["cell", "horizon", "tf", "fam", "side", "filt", "exit"]
LABEL = {"mcx_intraday": "MCX intraday", "mcx_positional": "MCX positional / overnight", "eq_intraday": "NSE cash intraday",
         "eq_daily": "NSE cash BTST / positional", "fut_intraday": "NSE futures intraday", "fut_daily": "NSE futures BTST / STBT / positional"}


def load(cell, keep_oos=False):
    p = RES / f"trades_{cell}.parquet"
    if not p.exists():
        return None
    T = pd.read_parquet(p)
    if not keep_oos:
        T = T[T.period.astype(str) != "OOS"]
    T["day"] = pd.to_datetime(T.date).dt.normalize()
    for c in ("cell", "horizon", "fam", "filt", "exit", "period", "etype", "inst", "market", "regime"):
        if c in T:
            T[c] = T[c].astype(str)
    return T


def clustered(T, keys, val):
    d = T.groupby(keys + ["day"], observed=True)[val].agg(["sum", "count"]).reset_index()
    g = d.groupby(keys, observed=True)
    S = pd.DataFrame(dict(nd=g.size(), s=g["sum"].sum(), n=g["count"].sum()))
    S["m"] = S.s / S.n
    d = d.join(S.m, on=keys)
    d["r2_"] = (d["sum"] - d["count"] * d["m"]) ** 2
    v = d.groupby(keys, observed=True).r2_.sum()
    S["se"] = np.sqrt(v * S.nd / np.maximum(S.nd - 1, 1)) / S.n
    S["t"] = S.m / S.se
    return S


def bh(p):
    p = np.asarray(p, float); n = len(p)
    if not n:
        return p
    o = np.argsort(p); q = np.empty(n); q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def describe(x):
    """per-cell metrics block (one period)."""
    r = x.r1.values
    w, l = r[r > 0], r[r <= 0]
    return dict(trades=len(r), dates=int(x.day.nunique()), win_pct=round(100 * len(w) / len(r), 1) if len(r) else None,
                avg_win=round(w.mean(), 3) if len(w) else None, avg_loss=round(l.mean(), 3) if len(l) else None,
                exp_1x=round(r.mean(), 4) if len(r) else None, exp_2x=round(x.r2.mean(), 4) if len(r) else None,
                pf=round(w.sum() / -l.sum(), 3) if len(l) and l.sum() < 0 else None,
                stop_pct=round(100 * (x.etype == "stop").mean(), 1) if len(r) else None,
                target_pct=round(100 * (x.etype == "target").mean(), 1) if len(r) else None)


def freeze():
    regs, abl = [], []
    for cell in CELLS:
        T = load(cell)
        if T is None or not len(T):
            regs.append(pd.DataFrame([dict(cell=cell, outcome="NOT_RUN", reason="no trades file")])); continue
        S = pd.read_csv(RES / f"signals_{cell}.csv.gz")
        for hz, X in T.groupby("horizon"):
            agg = []
            for P in ("DEV", "VALID"):
                Y = X[X.period == P]
                c2 = clustered(Y, KEY, "r2").add_suffix(f"_{P}")
                m1 = Y.groupby(KEY, observed=True).agg(**{f"exp1_{P}": ("r1", "mean"), f"win_{P}": ("r1", lambda s: 100 * (s > 0).mean()),
                                                          f"stop_{P}": ("etype", lambda s: 100 * (s == "stop").mean()),
                                                          f"target_{P}": ("etype", lambda s: 100 * (s == "target").mean()),
                                                          f"pf_{P}": ("r1", lambda s: s[s > 0].sum() / -s[s <= 0].sum() if (s <= 0).any() and s[s <= 0].sum() < 0 else np.nan)})
                agg.append(c2.join(m1))
            R = agg[0].join(agg[1], how="outer").reset_index()
            for c in ("n_DEV", "nd_DEV", "n_VALID", "nd_VALID"):
                R[c] = R[c].fillna(0).astype(int)
            test = (R.n_DEV >= 40) & (R.nd_DEV >= 25)
            R["p_DEV"] = np.where(test, stats.t.sf(R.t_DEV.fillna(0), np.maximum(R.nd_DEV - 1, 1)), np.nan)
            R["q_DEV"] = np.nan
            R.loc[test, "q_DEV"] = bh(R.loc[test, "p_DEV"].values)
            out, why = [], []
            for r in R.itertuples():
                if not (r.n_DEV >= 40 and r.nd_DEV >= 25):
                    out.append("INSUFFICIENT_DATA"); why.append(f"DEV {r.n_DEV} trades / {r.nd_DEV} dates < 40 / 25")
                elif not r.m_DEV > 0:
                    out.append("FAILED_DEV"); why.append(f"DEV expectancy at 2x cost {r.m_DEV:+.3f}R <= 0")
                elif not r.q_DEV < 0.10:
                    out.append("FAILED_DEV"); why.append(f"DEV not significant after BH (t {r.t_DEV:.2f}, q {r.q_DEV:.2f})")
                elif not (r.n_VALID >= 15):
                    out.append("INSUFFICIENT_DATA"); why.append(f"VALID {r.n_VALID} trades < 15")
                elif not (r.exp1_VALID > 0 and r.m_VALID > 0):
                    out.append("FAILED_VALID"); why.append(f"VALID expectancy 1x {r.exp1_VALID:+.3f} / 2x {r.m_VALID:+.3f}")
                else:
                    out.append("FROZEN_FOR_OOS"); why.append("passed DEV (BH q < 0.10, 2x > 0) and VALID (1x, 2x > 0)")
            R["outcome"] = out; R["reason"] = why
            sig = S.groupby(["tf", "fam", "side", "filt"]).agg(signals_DEV=("sig_DEV", "sum"), signals_VALID=("sig_VALID", "sum")).reset_index()
            R = R.merge(sig, on=["tf", "fam", "side", "filt"], how="left")
            R["n_instruments_DEV"] = R.merge(X[X.period == "DEV"].groupby(KEY, observed=True).inst.nunique().rename("ni").reset_index(), on=KEY, how="left").ni.values
            regs.append(R)
            # ablation: filter vs base (none), same family / side / exit, DEV + VALID, paired on days
            DV = X.copy()
            for (tf, fam, side, ex), G in DV.groupby(["tf", "fam", "side", "exit"], observed=True):
                base = G[G.filt == "none"]
                if len(base) < 30:
                    continue
                bd = base.groupby("day").r2.sum()
                for flt, F in G[G.filt != "none"].groupby("filt"):
                    if not len(F):
                        continue
                    fd = F.groupby("day").r2.sum()
                    # day-level paired difference of mean R per trade is not additive; use per-day sums scaled per base trade
                    dd = (fd.reindex(bd.index, fill_value=0) - bd)
                    nb = len(base); nf = len(F)
                    diff = F.r2.mean() - base.r2.mean()
                    # bootstrap over days of the difference in mean R
                    days = bd.index.values; rng = np.random.default_rng(7)
                    bcnt = base.groupby("day").size().reindex(days, fill_value=0).values; bsum = bd.reindex(days).values
                    fcnt = F.groupby("day").size().reindex(days, fill_value=0).values; fsum = fd.reindex(days, fill_value=0).values
                    bs = []
                    for _ in range(1000):
                        k = rng.integers(0, len(days), len(days))
                        if fcnt[k].sum() == 0:
                            continue
                        bs.append(fsum[k].sum() / fcnt[k].sum() - bsum[k].sum() / bcnt[k].sum())
                    lo, hi = (np.percentile(bs, [2.5, 97.5]) if bs else (np.nan, np.nan))
                    abl.append(dict(cell=cell, horizon=hz, tf=tf, fam=fam, side=side, exit=ex, filt=flt, base_trades=nb, filt_trades=nf,
                                    retention=round(nf / nb, 3), base_exp2=round(base.r2.mean(), 4), filt_exp2=round(F.r2.mean(), 4),
                                    d_exp2=round(diff, 4), d_ci_lo=round(lo, 4), d_ci_hi=round(hi, 4),
                                    base_win=round(100 * (base.r1 > 0).mean(), 1), filt_win=round(100 * (F.r1 > 0).mean(), 1),
                                    helps=bool(lo > 0 and nf / nb >= 0.3)))
    REG = pd.concat(regs, ignore_index=True)
    REG.to_csv(D / "STRATEGY_EXPERIMENT_REGISTER.csv", index=False)
    A = pd.DataFrame(abl); A.to_csv(RES / "ablation_filters.csv", index=False)
    F = REG[REG.outcome == "FROZEN_FOR_OOS"]
    F.to_csv(RES / "frozen_survivors.csv", index=False)
    print(REG.groupby(["cell", "outcome"]).size().to_string())
    print("frozen", len(F))
    print(F[KEY + ["n_DEV", "m_DEV", "t_DEV", "q_DEV", "n_VALID", "m_VALID"]].to_string() if len(F) else "")
    if len(A):
        print("filters that help:", int(A.helps.sum()), "of", len(A))


def oos():
    F = pd.read_csv(RES / "frozen_survivors.csv")
    rows = []
    for cell, G in F.groupby("cell"):
        T = load(cell, keep_oos=True)
        for r in G.itertuples():
            m = (T.horizon == r.horizon) & (T.tf == r.tf) & (T.fam == r.fam) & (T.side == r.side) & (T.filt == r.filt) & (T.exit == r.exit)
            X = T[m]
            per = {P: describe(X[X.period == P]) for P in ("DEV", "VALID", "OOS")}
            O = X[X.period == "OOS"]
            m1 = RG.metrics(O.rename(columns={"day": "dte"}).assign(date=O.day), "r1")
            m2 = RG.metrics(O.assign(date=O.day), "r2")
            # matched control: same cell / horizon / tf / side / exit, trades of ALL families with filter 'none' in the
            # same OOS period and instruments – an "any signal" baseline (random-like entries in the same market state)
            C = T[(T.horizon == r.horizon) & (T.tf == r.tf) & (T.side == r.side) & (T.exit == r.exit) & (T.filt == "none") &
                  (T.period == "OOS") & T.inst.isin(set(O.inst))]
            ctl = float(C.r1.mean()) if len(C) else np.nan
            hz = "intraday" if r.horizon == "intraday" else ("btst" if r.horizon == "overnight" else "positional")
            st, why = RG.classify(m1, m2, hz, selection_overlaps_window=False, controls_run=True)
            if st == "VALIDATED_CANDIDATE" and not (m1["expectancy_R"] > ctl):
                st, why = "PAPER_ONLY", f"passes OOS checks but does not beat the all-signal OOS baseline ({ctl:+.3f}R)"
            rows.append(dict(cell=cell, horizon=r.horizon, tf=r.tf, fam=r.fam, side=r.side, filt=r.filt, exit=r.exit, status=st, reason=why,
                             oos_trades=m1["trades"], oos_dates=m1["unique_dates"], oos_win=m1["win_rate"], oos_exp1=m1["expectancy_R"],
                             oos_exp2=m2["expectancy_R"], oos_pf=m1["profit_factor"], oos_maxdd=m1["max_drawdown_R"], oos_ci=m1["ci95"],
                             control_exp1=round(ctl, 4) if ctl == ctl else None, control_n=int(len(C)),
                             dev=json.dumps(per["DEV"]), valid=json.dumps(per["VALID"]), oos=json.dumps(per["OOS"]),
                             by_inst_oos=json.dumps(O.groupby("inst").r1.agg(["size", "mean"]).round(3).reset_index().values.tolist()),
                             by_regime_oos=json.dumps(O.groupby("regime").r1.agg(["size", "mean"]).round(3).reset_index().values.tolist())))
            with RG.Execution(script_id="MCXE005-select_eval-oos", strategy_name=f"{r.fam} {'BUY' if r.side > 0 else 'SELL'} {r.filt} {r.exit}",
                              market=LABEL.get(cell, cell), instrument=f"{O.inst.nunique()} instruments", timeframe=str(r.tf)) as ex:
                ex.finish("INSUFFICIENT_DATA" if st == "INSUFFICIENT_DATA" else "COMPLETED", executed_backtest_trades=m1["trades"],
                          win_rate=m1["win_rate"], net_expectancy_R=m1["expectancy_R"], profit_factor=m1["profit_factor"],
                          max_drawdown={"OOS_R": m1["max_drawdown_R"]}, confidence_interval={"OOS_1x": m1["ci95"]},
                          sample_dates={"OOS": m1["unique_dates"]}, validation_status=st, conclusion=why,
                          artifact_paths=["research/mcxe005/results/oos_survivors.csv"])
    O = pd.DataFrame(rows)
    O.to_csv(RES / "oos_survivors.csv", index=False)
    print(O[["cell", "tf", "fam", "side", "filt", "exit", "status", "oos_trades", "oos_dates", "oos_win", "oos_exp1", "oos_exp2", "oos_ci", "control_exp1"]].to_string() if len(O) else "no survivors")


if __name__ == "__main__":
    {"freeze": freeze, "oos": oos}[sys.argv[1]]()
