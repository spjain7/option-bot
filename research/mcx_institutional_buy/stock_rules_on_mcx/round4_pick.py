"""ROUND 4 selection: pooled (same rule on all 7) and per-commodity picks, chosen on TRAIN + VALID only; OOS shown unchanged.
robust score = min(TRAIN_R * sqrt(TRAIN_n), VALID_R * sqrt(VALID_n))   (a t-like score: needs edge AND trades in both periods)
neighbours   = share of the other exits of the same entry (same candle / side / signal / filter) positive in TRAIN and VALID;
               a pick needs >= 50 % (no knife-edge exit).
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round4_pick -> reports/mcx_round4_pooled.csv, mcx_round4_percommodity.csv"""
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import runner as RN

KEY = ["tf", "side", "fam", "filt", "k", "r", "exit"]
ENTRY = ["tf", "side", "fam", "filt"]
MIN = {"3h": (15, 8), "4h": (15, 8), "1d": (15, 8), "1w": (10, 5), "1M": (6, 3)}


def score(df):
    return np.minimum(df.TRAIN_R * np.sqrt(df.TRAIN_n), df.VAL_R * np.sqrt(df.VAL_n))


def neighbours(df, by):
    ok = (df.TRAIN_R > 0) & (df.VAL_R > 0)
    return df.assign(_ok=ok).groupby(by)["_ok"].transform("mean")


def main():
    L = pd.read_csv(RN.REPORTS / "mcx_round4.csv")
    # ---- pooled ----
    agg = L.groupby(KEY).agg(**{f"{p}_n": (f"{p}_n", "sum") for p in ("TRAIN", "VAL", "OOS")},
                             **{f"s_{p}": (f"sum_{p}", "sum") for p in ("TRAIN", "VAL", "OOS")},
                             **{f"w_{p}": (f"win_{p}", "sum") for p in ("TRAIN", "VAL", "OOS")},
                             names=("name", "nunique")).reset_index()
    for p in ("TRAIN", "VAL", "OOS"):
        agg[f"{p}_R"] = (agg[f"s_{p}"] / agg[f"{p}_n"].clip(lower=1)).round(3)
        agg[f"{p}_win"] = (100 * agg[f"w_{p}"] / agg[f"{p}_n"].clip(lower=1)).round(1)
    # commodities positive on TRAIN+VALID combined
    pc = L.assign(tv=(L.sum_TRAIN + L.sum_VAL) > 0).groupby(KEY).tv.sum().rename("commod_pos_TV").reset_index()
    agg = agg.merge(pc, on=KEY)
    agg["nb"] = neighbours(agg, ENTRY)
    agg["score"] = score(agg)
    mins = agg.tf.map(lambda t: MIN[t][0] * 3); minv = agg.tf.map(lambda t: MIN[t][1] * 3)
    q = agg[(agg.TRAIN_n >= mins) & (agg.VAL_n >= minv) & (agg.TRAIN_R > 0) & (agg.VAL_R > 0) & (agg.nb >= 0.5)]
    q = q.sort_values("score", ascending=False)
    q.to_csv(RN.REPORTS / "mcx_round4_pooled.csv", index=False)
    print("POOLED picks per candle size (chosen on TRAIN+VALID):")
    cols = KEY + ["TRAIN_n", "TRAIN_win", "TRAIN_R", "VAL_n", "VAL_win", "VAL_R", "OOS_n", "OOS_win", "OOS_R", "commod_pos_TV", "nb"]
    print(q.groupby(["tf", "side"]).head(3)[cols].to_string(index=False))
    print("\nhow the top-20 pooled picks did on OOS:", (q.head(20).OOS_R > 0).mean(), "median OOS R", q.head(20).OOS_R.median())
    # ---- per commodity ----
    L["nb"] = neighbours(L, ["name"] + ENTRY)
    L["score"] = score(L)
    mn = L.tf.map(lambda t: MIN[t][0]); mv = L.tf.map(lambda t: MIN[t][1])
    c = L[(L.TRAIN_n >= mn) & (L.VAL_n >= mv) & (L.TRAIN_R > 0) & (L.VAL_R > 0) & (L.nb >= 0.5)].sort_values("score", ascending=False)
    best = c.groupby("name").head(1)
    best_tf = c.groupby(["name", "tf"]).head(1)
    c.to_csv(RN.REPORTS / "mcx_round4_percommodity_candidates.csv", index=False)
    best_tf.to_csv(RN.REPORTS / "mcx_round4_percommodity.csv", index=False)
    pcols = ["name"] + KEY + ["TRAIN_n", "TRAIN_win", "TRAIN_R", "VAL_n", "VAL_win", "VAL_R", "OOS_n", "OOS_win", "OOS_R", "nb"]
    print("\nPER-COMMODITY best (any candle size):"); print(best[pcols].to_string(index=False))
    print("\nPER-COMMODITY best per candle size:"); print(best_tf.sort_values(["name", "tf"])[pcols].to_string(index=False))
    # honesty: top-5 per commodity, how many positive OOS
    t5 = c.groupby("name").head(5)
    print("\nper-commodity top-5 picks positive on OOS:", round((t5.OOS_R > 0).mean(), 2), " median OOS R", t5.OOS_R.median())
    # pooled #1 per tf applied to each commodity, for comparison
    print("\nPooled #1 of each candle size, per commodity OOS:")
    for (tf, side), g in q.groupby(["tf", "side"]):
        top = g.iloc[0]
        m = L[(L.tf == tf) & (L.side == side) & (L.fam == top.fam) & (L.filt == top.filt) & (L.k == top.k) & (L.r == top.r) & (L.exit == top.exit)]
        print(tf, side, top.fam, top.filt, top.k, top.exit, " OOS R by commodity:", dict(zip(m.name, m.OOS_R)))


if __name__ == "__main__":
    main()
