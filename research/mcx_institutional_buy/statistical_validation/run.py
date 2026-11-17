"""Statistical validation of every candidate that passed TRAIN + VALID + OOS and beat its matched baseline in all three.
python -m research.mcx_institutional_buy.statistical_validation.run -> reports/validation.csv, reports/candidate_trades.parquet
Checks
  BH-FDR 10 %         OOS day-clustered t-test p-values, over every rule that reached OOS (passed TRAIN + VALID) in that timeframe
  excess bootstrap    OOS mean R minus the matched baseline's OOS mean R, 95 % bootstrap CI (trades resampled)
  walk-forward        calendar-year R of the frozen rule; share of positive years; worst year
  PBO (CSCV)          probability of backtest overfitting over all rules x exits of that timeframe (monthly R matrix, 10 blocks)
  DSR                 deflated Sharpe ratio (Bailey & Lopez de Prado) with N = number of tests in that timeframe
  stability           neighbouring parameters (pivot width, RSI length, exit) – share with positive OOS R
  concentration       best commodity's share of total profit; number of commodities with positive R
Labels
  SHADOW CANDIDATE    OOS validated + stability >= 2/3 + no commodity > 50 % of profit + positive years >= 60 % + DSR >= 0.90
  OOS VALIDATED       FINAL pass + BH-FDR significant on OOS + excess CI lower bound > 0
  PROMISING           FINAL pass (all periods positive, beats baseline) but not significant
  INCONCLUSIVE        passed TRAIN + VALID but OOS sample < 30 or mixed
  FAILED              everything else"""
import itertools
import re
import sys
import warnings
import numpy as np
import pandas as pd
from scipy import stats as SS
from ..backtesting import runner as RN, metrics as M, data as D
from ..strategy_combinations import run as CB

warnings.filterwarnings("ignore")
P3 = ("TRAIN", "VAL", "OOS")


def parse(rule):
    core = rule.split("|", 1)[1] if "|" in rule else rule
    parts = core.split("&")
    return parts[0], parts[1:]


def trades_for(tf, rule, ex):
    if "@" in rule:
        from ..strategy_combinations import mtf as MT
        return MT.trades(tf, rule, ex)
    anchor, conds = parse(rule)
    if not conds:
        T = pd.read_parquet(D.CACHE / f"trades_stage1_{tf}.parquet", filters=[("rule", "==", rule), ("exit", "==", ex)])
        return T
    _, T = CB.run_combos(tf, [(rule, anchor, ex, conds)], "VAL")
    return T


def dsr(r, n_trials, sr_var):
    """deflated Sharpe ratio probability for per-trade returns r, given the variance of Sharpe ratios across trials."""
    r = np.asarray(r, float); n = len(r)
    if n < 10 or r.std(ddof=1) == 0:
        return np.nan
    sr = r.mean() / r.std(ddof=1); g3 = SS.skew(r); g4 = SS.kurtosis(r, fisher=False)
    emc = 0.5772156649
    sr0 = np.sqrt(max(sr_var, 1e-12)) * ((1 - emc) * SS.norm.ppf(1 - 1 / n_trials) + emc * SS.norm.ppf(1 - 1 / (n_trials * np.e)))
    z = (sr - sr0) * np.sqrt(n - 1) / np.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    return float(SS.norm.cdf(z))


def pbo(M_):
    """CSCV: M_ is (T periods x N strategies). Returns probability the in-sample best is below the OOS median."""
    M_ = M_.dropna(axis=1, how="all").fillna(0.0).values
    T_, N = M_.shape
    if N < 4 or T_ < 20:
        return np.nan
    S = 10; blocks = np.array_split(np.arange(T_), S); lam = []
    for comb in itertools.combinations(range(S), S // 2):
        ins = np.concatenate([blocks[i] for i in comb]); oos = np.concatenate([blocks[i] for i in range(S) if i not in comb])
        a = M_[ins].mean(0); b = M_[oos].mean(0)
        best = int(np.argmax(a)); rank = SS.rankdata(b)[best] / (N + 1)
        lam.append(np.log(rank / (1 - rank)))
    return float(np.mean(np.array(lam) <= 0))


def neighbours(rule, ex, S1):
    a, conds = parse(rule)
    alts = set()
    a = a.split("@")[0]
    m = re.match(r"(DIV_[A-Z0-9]+_(?:REG|HID))_R(\d)", a)
    if m:
        alts |= {f"{m.group(1)}_R{k}" for k in (2, 3, 5)}
    m = re.match(r"RSI(\d+)_(.*)", a)
    if m:
        alts |= {f"RSI{k}_{m.group(2)}" for k in (7, 9, 14, 21)}
    alts.add(a)
    rows = S1[S1.rule.isin(alts)]
    rows = rows[~((rows.rule == a) & (rows.exit == ex))]
    same_exit = rows[rows.exit == ex] if len(rows[rows.exit == ex]) >= 1 else rows
    other_exit = S1[(S1.rule == a) & (S1.exit != ex)]
    nb = pd.concat([same_exit, other_exit]).drop_duplicates(["rule", "exit"])
    nb = nb[nb.OOS_n >= 15]
    return (float((nb.OOS_R > 0).mean()) if len(nb) else np.nan), int(len(nb))


def main():
    out = []; keep = []
    for tf in RN.TFS:
        S1 = pd.read_csv(RN.REPORTS / f"stage1_{tf}.csv")
        S1x = CB.add_excess(S1.assign(anchor=S1.rule), S1)
        try:
            CO = pd.read_csv(RN.REPORTS / f"combos_{tf}.csv")
        except FileNotFoundError:
            CO = pd.DataFrame(columns=S1x.columns)
        MTF = pd.read_csv(RN.REPORTS / "mtf.csv")
        MTF = MTF[(MTF.tf == tf) & (MTF.context != "NONE")].assign(stage="MTF")
        ALL = pd.concat([S1x.assign(stage="S1"), CO[CO.stage != "S1_anchor"], MTF], ignore_index=True)
        reached = ALL[ALL.VAL_PASS.fillna(False).astype(bool)].copy()
        reached["p_oos"] = [M.p_from_t(x) for x in reached.OOS_t_day]
        reached["FDR10_oos"] = M.bh(reached.p_oos.values, 0.10)
        n_trials = len(ALL)
        # Sharpe variance across all S1 tests (per-trade Sharpe on ALL period)
        tr = pd.read_parquet(D.CACHE / f"trades_stage1_{tf}.parquet", columns=["rule", "exit", "netR", "entry", "name", "period"])
        g = tr.groupby(["rule", "exit"]).netR
        srs = (g.mean() / g.std())[g.size() >= 30].replace([np.inf, -np.inf], np.nan).dropna()   # rules with >= 30 trades
        sr_var = float(srs.var())
        tr["month"] = pd.to_datetime(tr.entry).dt.to_period("M")
        Mx = tr.groupby(["month", "rule", "exit"]).netR.sum().unstack([1, 2])
        pbo_tf = pbo(Mx[[c for c in Mx.columns if not str(c[0]).startswith("BASE")]])
        cand = reached[reached.FINAL_PASS.fillna(False).astype(bool)]
        print(tf, "tests", n_trials, "reached OOS", len(reached), "FINAL", len(cand), "PBO(timeframe)", pbo_tf, flush=True)
        base = {}
        for _, r in cand.iterrows():
            T = trades_for(tf, r.rule, r.exit)
            if not len(T):
                continue
            T["period"] = RN.period_of(tf, T.entry)
            bname = CB.baseline_of(parse(r.rule)[0])
            if bname not in base:
                base[bname] = {e: tr[(tr.rule == bname) & (tr.exit == e) & (tr.period == "OOS")].netR.values for e in RN.EXITS}
            bo = base[bname][r.exit]; ro = T[T.period == "OOS"].netR.values
            rng = np.random.default_rng(11)
            diff = [rng.choice(ro, len(ro)).mean() - rng.choice(bo, len(bo)).mean() for _ in range(2000)] if len(ro) > 5 and len(bo) > 5 else [np.nan]
            ex_lo, ex_hi = np.nanpercentile(diff, 2.5), np.nanpercentile(diff, 97.5)
            yr = T.groupby(pd.to_datetime(T.entry).dt.year).netR.mean()
            pc = T.groupby("name").netR.agg(["sum", "mean", "size"])
            share = float(pc["sum"].max() / pc["sum"].sum()) if pc["sum"].sum() > 0 else np.nan
            stab, nnb = neighbours(r.rule, r.exit, S1)
            d = dsr(T.netR.values, n_trials, sr_var)
            ci = M.bootstrap_ci(ro)
            row = dict(tf=tf, rule=r.rule, exit=r.exit, stage=r.get("stage", "S1"), family=parse(r.rule)[0],
                       **{f"{p}_{a}": r[f"{p}_{a}"] for p in P3 for a in ("n", "win", "R", "PF")},
                       **{f"{p}_excess": round(r[f"{p}_excess"], 3) for p in P3},
                       p_oos=r.p_oos, FDR10_oos=bool(r.FDR10_oos), oos_ci_lo=ci[0], oos_ci_hi=ci[1],
                       excess_ci_lo=round(ex_lo, 3), excess_ci_hi=round(ex_hi, 3),
                       pos_years=round(float((yr > 0).mean()), 2), worst_year_R=round(float(yr.min()), 3), years=int(len(yr)),
                       commodities_positive=f"{int((pc['mean'] > 0).sum())}/{len(pc)}", best_commodity_share=round(share, 2),
                       stability=stab, n_neighbours=nnb, DSR=round(d, 3) if d == d else np.nan, PBO_timeframe=pbo_tf,
                       maxDD_R=M.summary(T)["maxDD_R"], max_consec_loss=M.summary(T)["max_consec_loss"],
                       hold_bars=M.summary(T)["hold"], mfe=M.summary(T)["mfe"], mae=M.summary(T)["mae"],
                       per_commodity="; ".join(f"{i}:{x['mean']:+.2f}({int(x['size'])})" for i, x in pc.iterrows()),
                       per_year="; ".join(f"{i}:{v:+.2f}" for i, v in yr.items()))
            oosv = row["FDR10_oos"] and (row["excess_ci_lo"] > 0)
            shadow = oosv and (stab or 0) >= 2 / 3 and (share == share and share <= 0.5) and row["pos_years"] >= 0.6 and (row["DSR"] or 0) >= 0.9
            row["label"] = "SHADOW CANDIDATE" if shadow else ("OOS VALIDATED" if oosv else "PROMISING RESEARCH CANDIDATE")
            out.append(row); T["tf"] = tf; T["cand"] = f"{tf}|{r.rule}|{r.exit}"; keep.append(T)
        # rules that reached OOS but failed there
        for _, r in reached[~reached.FINAL_PASS.fillna(False).astype(bool)].iterrows():
            lab = "INCONCLUSIVE" if (r.OOS_n < 30) else "FAILED"
            out.append(dict(tf=tf, rule=r.rule, exit=r.exit, stage=r.get("stage", "S1"), family=parse(r.rule)[0],
                            **{f"{p}_{a}": r[f"{p}_{a}"] for p in P3 for a in ("n", "win", "R", "PF")},
                            **{f"{p}_excess": r[f"{p}_excess"] for p in P3}, p_oos=r.p_oos, label=lab))
    V = pd.DataFrame(out)
    V.to_csv(RN.REPORTS / "validation.csv", index=False)
    if keep:
        pd.concat(keep, ignore_index=True).to_parquet(D.CACHE / "candidate_trades.parquet", index=False)
    print(V.label.value_counts().to_dict())
    pd.set_option("display.width", 250)
    print(V[V.label.isin(["SHADOW CANDIDATE", "OOS VALIDATED"])][["tf", "rule", "exit", "OOS_n", "OOS_win", "OOS_R", "OOS_excess",
                                                                    "excess_ci_lo", "p_oos", "stability", "best_commodity_share",
                                                                    "pos_years", "DSR", "label"]].to_string(index=False))


if __name__ == "__main__":
    main()
