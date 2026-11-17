"""STAGE 5 – score models with interaction effects, per timeframe and family (EARLY / CONF), BUY only.
Data: TRAIN trades of the TRAIN-selected anchors (their TRAIN-best exit), every signal-bar condition as a 0/1 feature,
anchor dummies, and pairwise products of the 8 TRAIN-best conditions (interactions).
Models: L2 logistic regression (target: net R > 0) and a shallow gradient-boosted tree (target: net R), fixed seeds.
Threshold: top 20 % / 10 % of TRAIN scores; applied unchanged to VALID and OOS.
python -m research.mcx_institutional_buy.strategy_combinations.score -> reports/score.csv"""
import itertools
import sys
import warnings
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingRegressor
from ..backtesting import runner as RN, context as CX, metrics as M, data as D

warnings.filterwarnings("ignore")


def main(tfs):
    rows = []
    for tf in tfs:
        A = pd.read_csv(RN.REPORTS / f"anchors_{tf}.csv")
        lift = pd.read_csv(RN.REPORTS / f"cond_lift_{tf}.csv")
        top = lift[(lift.TRAIN_n_with >= 30)].sort_values("TRAIN_lift", ascending=False).condition.head(8).tolist()
        tr = pd.read_parquet(D.CACHE / f"trades_stage1_{tf}.parquet")
        for fam, Af in A.groupby("family"):
            key = set(zip(Af.rule, Af.exit))
            T = tr[[k in key for k in zip(tr.rule, tr.exit)]]
            if len(T) < 200:
                continue
            T = CX.attach(T, tf).reset_index(drop=True)
            cc = [c for c in T.columns if c.startswith("c_") and not c.endswith("_KNOWN")]
            X = T[cc].astype(float).fillna(0)
            for a, b in itertools.combinations(top, 2):
                X[f"x_{a}*{b}"] = X[f"c_{a}"] * X[f"c_{b}"]
            X = pd.concat([X, pd.get_dummies(T.rule, prefix="r").astype(float)], axis=1)
            tri = (T.period == "TRAIN").values
            if tri.sum() < 200:
                continue
            lr = LogisticRegression(C=0.3, max_iter=3000).fit(X[tri], (T.netR[tri] > 0).values)
            gb = HistGradientBoostingRegressor(max_depth=3, max_iter=150, learning_rate=0.05, random_state=7).fit(X[tri], T.netR[tri].clip(-3, 8))
            for mname, sc in (("LOGIT", lr.predict_proba(X)[:, 1]), ("GBT", gb.predict(X))):
                for keep in (1.0, 0.2, 0.1):
                    thr = np.quantile(sc[tri], 1 - keep) if keep < 1 else -np.inf
                    sel = sc >= thr
                    r = dict(tf=tf, family=fam, model=mname, keep_top=keep)
                    for p in ("TRAIN", "VAL", "OOS"):
                        s = M.summary(T[sel & (T.period == p).values])
                        for k_ in ("n", "win", "R", "PF"):
                            r[f"{p}_{k_}"] = s.get(k_, np.nan)
                    r["PASS"] = all((r[f"{p}_n"] >= 30) and (r[f"{p}_R"] > 0) and (r[f"{p}_PF"] >= 1.2) for p in ("TRAIN", "VAL", "OOS"))
                    r["gain_vs_unfiltered_OOS"] = np.nan
                    rows.append(r)
            print(tf, fam, "trades", len(T), flush=True)
    R = pd.DataFrame(rows)
    for (tf, fam, m), g in R.groupby(["tf", "family", "model"]):
        base = g[g.keep_top == 1.0].OOS_R.values[0]
        R.loc[g.index, "gain_vs_unfiltered_OOS"] = (g.OOS_R - base).round(3)
    R.to_csv(RN.REPORTS / "score.csv", index=False)
    RN.experiment_record("MCXIB-SCORE", "strategy_combinations.score", ",".join(tfs), dict(models=["LOGIT", "GBT"], keep=[0.2, 0.1]),
                         R.assign(TRAIN_PASS=R.PASS, VAL_PASS=R.PASS, OOS_PASS=R.PASS))
    pd.set_option("display.width", 220)
    print(R.to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1:] or RN.TFS)
