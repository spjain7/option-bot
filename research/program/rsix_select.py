"""RSIX-001 selection – walk-forward, no peeking at the test period.
1. Rank every pooled (all-commodity) variant per timeframe and side by TRAIN expectancy (min trades per period).
2. Keep only variants that are also positive in VALID.
3. Report the untouched TEST period (out of sample) for the survivors: win %, PF, expectancy, trades / commodity / month.
4. Per commodity: the same three-step selection inside each commodity (small samples – flagged).
python research/program/rsix_select.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/program/results"
MIN_N = {"15m": 120, "30m": 90, "1h": 60, "2h": 45, "4h": 30, "1d": 30}       # per split, pooled
MONTHS = {"15m": 40, "30m": 40, "1h": 51, "2h": 51, "4h": 51, "1d": 245}       # data length per commodity (months)
K = ["tf", "side", "ext", "L", "candle", "entry", "stop", "exit"]


def select(S, min_n, top=15, by=K):
    x = S[(S.train_n >= min_n) & (S.valid_n >= min_n * 0.5) & (S.test_n >= min_n * 0.5)].copy()
    x = x[(x.train_R > 0)].sort_values("train_R", ascending=False)
    breadth = len(x)
    x = x[x.valid_R > 0]
    return x.head(top), breadth


def main():
    S = pd.read_csv(OUT / "rsix_pooled.csv")
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 300)
    cols = K + ["train_n", "train_R", "valid_R", "test_n", "test_win", "test_R", "test_PF", "n", "win", "R", "PF", "gross"]
    print(f"variants tested (pooled): {len(S):,}  ·  per side × timeframe the best are chosen on TRAIN only\n")
    best = []
    for tf in ["15m", "30m", "1h", "2h", "4h", "1d"]:
        for side in (1, -1):
            g = S[(S.tf == tf) & (S.side == side)]
            sel, breadth = select(g, MIN_N[tf])
            pos_train = int((g[g.train_n >= MIN_N[tf]].train_R > 0).sum()); tot = int((g.train_n >= MIN_N[tf]).sum())
            print(f"=== {tf} {'BUY' if side > 0 else 'SELL'}: {tot} adequately sampled variants, {pos_train} positive in train, "
                  f"{len(sel)} of the top also positive in valid")
            if len(sel):
                sel = sel.assign(per_month=sel.n / 7 / MONTHS[tf])
                print(sel.head(6)[cols + ["per_month"]].round(2).to_string(index=False))
                best.append(sel.head(6))
            print()
    B = pd.concat(best) if best else pd.DataFrame()
    B.to_csv(OUT / "rsix_selected.csv", index=False)
    # out-of-sample verdict for the single best (train-ranked) survivor per tf/side
    if len(B):
        print("OUT-OF-SAMPLE (TEST) of the #1 train-ranked survivor per timeframe / side:")
        top1 = B.groupby(["tf", "side"]).head(1)
        print(top1[cols].round(2).to_string(index=False))
    # per commodity
    N = pd.read_csv(OUT / "rsix_by_name.csv")
    rows = []
    for (nm, tf, side), g in N.groupby(["name", "tf", "side"]):
        mn = max(10, MIN_N[tf] // 7 * 2)
        sel, breadth = select(g, mn, top=1)
        if len(sel):
            r = sel.iloc[0].to_dict(); r["breadth"] = breadth; rows.append(r)
    P = pd.DataFrame(rows)
    if len(P):
        P.to_csv(OUT / "rsix_per_commodity.csv", index=False)
        P = P.sort_values("test_R", ascending=False)
        print("\nPER COMMODITY: best train-ranked variant that is also positive in valid -> its TEST result (small samples!)")
        print(P[["name"] + cols + ["breadth"]].round(2).head(40).to_string(index=False))
        print(f"\nper-commodity survivors positive in TEST: {(P.test_R > 0).sum()} of {len(P)} "
              f"(chance ≈ half if there is no edge)")


if __name__ == "__main__":
    main()
