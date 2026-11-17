"""ROUND 3b: WEIGHTED SCORE (owner 17-Nov-2026: "combine by giving weightage").
For each candle size / side / exit: take every candle where at least one trigger fired, trade it, and on TRAIN ONLY measure each
of the 12 parts' lift = (avg R of trades where the part was present) - (avg R of all trades); weight = max(lift, 0).
Score = sum of weights of the parts present. Trade only candles whose score is in the TRAIN top 10 / 20 / 30 %.
Weights and cut-offs are frozen from TRAIN, then VALID and OOS are shown unchanged, pooled over the 7 commodities.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.wscore -> reports/mcx_wscore.csv, mcx_wscore_weights.json"""
import itertools
import json
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import data as D, runner as RN
from research.mcx_institutional_buy.stock_rules_on_mcx import patterns as PT

ALLP = PT.TRIG + PT.COND


def main():
    data = PT.load()
    for d in data.values():
        PT.NAN.setdefault(len(d["c"]), np.full(len(d["c"]), np.nan))
    names = list(D.INTRA); rows = []; W = {}
    for tf in PT.TFS:
        for side in (1, -1):
            for k, r in itertools.product(PT.KS, PT.RS):
                # step 1: all trigger candles, traded, TRAIN lift per part
                recs = []
                for n in names:
                    d = data[(n, tf, side)]; P = d["P"]
                    anyt = np.zeros(len(d["c"]), bool)
                    for t in PT.TRIG:
                        anyt |= P[t]
                    si, ei, xi, nr, why = PT.sim(d, anyt, k, r)
                    X = np.stack([P[p][si] for p in ALLP], 1)
                    recs.append((X, nr, d["per"][ei]))
                X = np.concatenate([a[0] for a in recs]); nr = np.concatenate([a[1] for a in recs]); pe = np.concatenate([a[2] for a in recs])
                tr = pe == "TRAIN"
                if tr.sum() < 100:
                    continue
                base = nr[tr].mean()
                w = np.array([max(nr[tr & X[:, i]].mean() - base, 0) if (tr & X[:, i]).sum() >= 20 else 0 for i in range(len(ALLP))])
                if w.sum() == 0:
                    continue
                sc_tr = (X[tr] * w).sum(1)
                for q in (70, 80, 90):
                    thr = float(np.percentile(sc_tr, q))
                    if thr <= 0:
                        continue
                    nrs, pers = [], []
                    for n in names:
                        d = data[(n, tf, side)]; P = d["P"]
                        anyt = np.zeros(len(d["c"]), bool)
                        for t in PT.TRIG:
                            anyt |= P[t]
                        sc = sum(w[i] * P[p] for i, p in enumerate(ALLP))
                        si, ei, xi, nr2, why = PT.sim(d, anyt & (sc >= thr), k, r)
                        nrs.append(nr2); pers.append(d["per"][ei])
                    nr2 = np.concatenate(nrs); pe2 = np.concatenate(pers)
                    key = f"{tf}|{'BUY' if side > 0 else 'SELL'}|{k}|{r}|top{100 - q}"
                    W[key] = dict(zip(ALLP, np.round(w, 3).tolist())) | {"threshold": round(thr, 3)}
                    rows.append(dict(tf=tf, side="BUY" if side > 0 else "SELL", signal=f"WSCORE top {100 - q}%", k=k, r=r,
                                     **PT.stats(nr2, pe2)))
            print(tf, side, len(rows), flush=True)
    pd.DataFrame(rows).to_csv(RN.REPORTS / "mcx_wscore.csv", index=False)
    (RN.REPORTS / "mcx_wscore_weights.json").write_text(json.dumps(W))


if __name__ == "__main__":
    main()
