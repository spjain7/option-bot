"""Walk-forward test of the SELECTION PROCESS (not of one hand-picked rule).
Each calendar year Y: using only trades that ENTERED before Y, rank every stage-1 rule x exit (>= 30 trades, beats its matched
random baseline before Y) by mean net R and pick the top 5; record their mean R in year Y (frozen), and the matched baseline in Y.
If the process has skill, the picked rules beat the baseline in most out-of-sample years.
python -m research.mcx_institutional_buy.walk_forward.run -> reports/walk_forward.csv"""
import warnings
import numpy as np
import pandas as pd
from ..backtesting import runner as RN, data as D
from ..strategy_combinations import run as CB

warnings.filterwarnings("ignore")


def main():
    rows = []
    for tf in RN.TFS:
        T = pd.read_parquet(D.CACHE / f"trades_stage1_{tf}.parquet", columns=["rule", "exit", "netR", "entry"])
        T["y"] = pd.to_datetime(T.entry).dt.year
        y0 = 2010 if tf == "1d" else 2024
        for Y in range(y0, int(T.y.max()) + 1):
            past = T[T.y < Y]; now = T[T.y == Y]
            g = past.groupby(["rule", "exit"]).netR.agg(["mean", "size"])
            g = g[g["size"] >= 30]
            base = {k: v for k, v in g["mean"].items() if k[0].startswith("BASE")}
            g = g[[not r.startswith("BASE") for r, _ in g.index]]
            g["base"] = [base.get((CB.baseline_of(r), e), np.nan) for r, e in g.index]
            g = g[g["mean"] > g.base].sort_values("mean", ascending=False).head(5)
            nm = now.groupby(["rule", "exit"]).netR.agg(["mean", "size"])
            for (r, e), x in g.iterrows():
                b = nm["mean"].get((CB.baseline_of(r), e), np.nan)
                rows.append(dict(tf=tf, year=Y, rule=r, exit=e, past_R=round(x["mean"], 3), oos_year_R=round(nm["mean"].get((r, e), np.nan), 3),
                                 oos_year_n=int(nm["size"].get((r, e), 0)), oos_year_base_R=round(b, 3)))
    W = pd.DataFrame(rows)
    W["beats_base"] = W.oos_year_R > W.oos_year_base_R
    W.to_csv(RN.REPORTS / "walk_forward.csv", index=False)
    S = W.groupby(["tf", "year"]).agg(picked_R=("oos_year_R", "mean"), base_R=("oos_year_base_R", "mean"), beats=("beats_base", "mean"),
                                       n=("oos_year_n", "sum")).round(3)
    S.to_csv(RN.REPORTS / "walk_forward_summary.csv")
    print(S.to_string())
    print(W.groupby("tf").agg(mean_picked=("oos_year_R", "mean"), mean_base=("oos_year_base_R", "mean"), beat_share=("beats_base", "mean")).round(3))


if __name__ == "__main__":
    main()
