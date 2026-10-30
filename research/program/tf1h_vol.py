"""TF1H-VOL (30-Oct-2026, owner: "1-hour with volume 5×"): breakout family on 1h candles, volume > 3 / 4 / 5×,
lookback 5/10/20, (stop ATR, target R) (2,2) (2.5,2.5) (1.5,3); MCX + stock futures, 2× costs, Jul-2022 → Oct-2026 (stocks 2023→).
python research/program/tf2h_vol.py"""
import itertools, sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX  # noqa: E402
from research.program.tf_nh import nhour  # noqa: E402
from research.program.tf5h import T1, T2  # noqa: E402
V = list(itertools.product((5, 10, 20), (3.0, 4.0, 5.0), ((2.0, 2.0), (2.5, 2.5), (1.5, 3.0))))


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return []
    rows = []
    for seg, f0, od, cost in fr:
        market, tf0 = seg.split()[0], seg.split()[-1]
        if tf0 != "1h" or market == "INDEX":
            continue
        f_ = f0.sort_values("time").reset_index(drop=True)
        if len(f_) < 260:
            continue
        f = H.features(f_); f["switch"] = f_["switch"].values
        c_ = np.interp(np.arange(len(f)), np.linspace(0, len(f) - 1, len(cost)), cost)
        cap = 4.0 if market == "STOCKS" else 2.5
        for N, vx, (k, r) in V:
            hh = f.high.shift(1).rolling(N).max(); ll = f.low.shift(1).rolling(N).min()
            sig = np.where((f.close > hh) & (f.volx > vx) & (f.close > f.ema200), 1, np.where((f.close < ll) & (f.volx > vx) & (f.close < f.ema200), -1, 0))
            for side in (1, -1):
                for x in H.simulate(f, sig, side, k, r, 40, cap, c_):
                    if x["status"] == "trade":
                        rows.append((market, job[1], N, vx, f"{k:g}ATR/{r:g}R", "BUY" if side > 0 else "SELL", x["time"], x["r2"]))
    return rows


def main():
    J = [j for j in EX.jobs() if (j[0] == "mi" and j[2] == "MCX") or j[0] == "stk"]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(one, J, chunksize=2) for r in x]
    T = pd.DataFrame(rows, columns=["market", "name", "N", "vol", "exit", "side", "time", "r2"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T["split"] = np.where(T.time < T1, "train", np.where(T.time < T2, "valid", "test"))
    keys = ["market", "side", "vol", "N", "exit"]
    S = T.groupby(keys).r2.agg(n="size", R="mean", win=lambda s: (s > 0).mean() * 100).join(
        T.pivot_table(index=keys, columns="split", values="r2", aggfunc="mean")[["train", "valid", "test"]])
    S["all3"] = (S[["train", "valid", "test"]] > 0).all(axis=1)
    S = S.reset_index(); S.to_csv(ROOT / "research/program/results/tf1h_vol.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
    print("by volume level (9 variants each): variants positive in all 3 periods, median / best R, median trades")
    print(S.groupby(["market", "side", "vol"]).agg(all3=("all3", "sum"), median_R=("R", "median"), best_R=("R", "max"),
                                                   trades=("n", "median")).round(3).to_string())
    print("\nvolume 5× – every variant:")
    print(S[S.vol == 5.0].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
