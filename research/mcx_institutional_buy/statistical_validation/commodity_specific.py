"""Do commodity-specific parameters beat one pooled setting? (section 2: 'commodity-specific parameters')
For each candidate FAMILY (all its parameter variants x exits), choose on TRAIN:
  POOLED    the single variant with the best pooled TRAIN R, used for every commodity
  PER-COMMODITY  each commodity's own best TRAIN variant (>= 15 TRAIN trades for that commodity, else the pooled choice)
then compare VALID and OOS R. python -m research.mcx_institutional_buy.statistical_validation.commodity_specific"""
import re
import warnings
import numpy as np
import pandas as pd
from ..backtesting import runner as RN, data as D

warnings.filterwarnings("ignore")
FAMILIES = {"4h": [r"^RSI(7|9|14|21)_CROSS75$", r"^DIV_MACD_HID_R(2|3|5)$", r"^SWEEP_[A-Z]+_LHBREAK_RETEST$", r"^DIV_[A-Z0-9]+_REG_R2$"],
            "1d": [r"^RSI(7|9|14|21)_CROSS75$", r"^RSI(7|9|14|21)_BELOW25X3_CROSSUP$", r"^SWEEP_[A-Z]+_HIGHBO$"],
            "1h": [r"^SWEEP_[A-Z_]+_HIGHBO$", r"^MS_[A-Z_]+$"]}


def main():
    rows = []
    for tf, fams in FAMILIES.items():
        T = pd.read_parquet(D.CACHE / f"trades_stage1_{tf}.parquet", columns=["rule", "exit", "name", "netR", "period"])
        for pat in fams:
            G = T[T.rule.str.match(pat)]
            if not len(G):
                continue
            tr = G[G.period == "TRAIN"].groupby(["rule", "exit"]).netR.agg(["mean", "size"])
            tr = tr[tr["size"] >= 30]
            if not len(tr):
                continue
            pooled = tr["mean"].idxmax()
            per = {}
            for nm, g in G[G.period == "TRAIN"].groupby("name"):
                x = g.groupby(["rule", "exit"]).netR.agg(["mean", "size"]); x = x[x["size"] >= 15]
                per[nm] = x["mean"].idxmax() if len(x) else pooled
            for p in ("VAL", "OOS"):
                Gp = G[G.period == p]
                a = Gp[(Gp.rule == pooled[0]) & (Gp.exit == pooled[1])].netR
                b = pd.concat([Gp[(Gp.name == nm) & (Gp.rule == k[0]) & (Gp.exit == k[1])].netR for nm, k in per.items()])
                rows.append(dict(tf=tf, family=pat, period=p, pooled_choice=f"{pooled[0]}|{pooled[1]}", pooled_n=len(a), pooled_R=round(a.mean(), 3),
                                 per_commodity_n=len(b), per_commodity_R=round(b.mean(), 3),
                                 per_commodity_choices="; ".join(f"{k}:{v[0]}|{v[1]}" for k, v in per.items())))
    R = pd.DataFrame(rows); R.to_csv(RN.REPORTS / "commodity_specific.csv", index=False)
    pd.set_option("display.width", 200)
    print(R.drop(columns="per_commodity_choices").to_string(index=False))
    print("per-commodity better in", int((R.per_commodity_R > R.pooled_R).sum()), "of", len(R), "family-period cells")


if __name__ == "__main__":
    main()
