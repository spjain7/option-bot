"""TFNH-001 (30-Oct-2026, owner: "same settings for 4 hours?"): the TF5H-001 test on 2h / 4h / 5h / 6h candles.
MCX: day-anchored blocks from 09:00 (4h = 09-13 / 13-17 / 17-21 / 21-close); NSE: every n consecutive 1-hour bars.
Same 18 variants and the two proposed settings. python research/program/tf_nh.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX  # noqa: E402
from research.program.tf5h import VARIANTS, T1, T2  # noqa: E402
HOURS = (2, 4, 5, 6)


def nhour(f1, market, n):
    f1 = f1.sort_values("time").reset_index(drop=True)
    if market == "MCX":
        hr = f1["time"].dt.hour
        key = f1["time"].dt.normalize().astype("int64") // 10**9 * 10 + ((hr - 9).clip(lower=0) // n)
    else:
        key = np.arange(len(f1)) // n
    g = f1.groupby(key, sort=True)
    return g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                 volume=("volume", "sum"), switch=("switch", "max")).reset_index(drop=True)


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
        for n in HOURS:
            f_ = nhour(f0, market, n)
            if len(f_) < 260:
                continue
            f = H.features(f_); f["switch"] = f_["switch"].values
            c_ = np.interp(np.arange(len(f)), np.linspace(0, len(f) - 1, len(cost)), cost)
            cap = 4.0 if market == "STOCKS" else 2.5
            for N, vx, (k, r) in VARIANTS:
                hh = f.high.shift(1).rolling(N).max(); ll = f.low.shift(1).rolling(N).min()
                sig = np.where((f.close > hh) & (f.volx > vx) & (f.close > f.ema200), 1,
                               np.where((f.close < ll) & (f.volx > vx) & (f.close < f.ema200), -1, 0))
                for side in (1, -1):
                    for x in H.simulate(f, sig, side, k, r, 40, cap, c_):
                        if x["status"] == "trade":
                            rows.append((market, job[1], f"{n}h", N, vx, f"{k:g}ATR/{r:g}R", "BUY" if side > 0 else "SELL", x["time"], x["r2"]))
    return rows


def main():
    J = [j for j in EX.jobs() if (j[0] == "mi" and j[2] == "MCX") or j[0] == "stk"]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(one, J, chunksize=2) for r in x]
    T = pd.DataFrame(rows, columns=["market", "name", "tf", "N", "vol", "exit", "side", "time", "r2"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T["split"] = np.where(T.time < T1, "train", np.where(T.time < T2, "valid", "test"))
    keys = ["market", "tf", "side", "N", "vol", "exit"]
    S = T.groupby(keys).r2.agg(n="size", R="mean").join(T.pivot_table(index=keys, columns="split", values="r2", aggfunc="mean")[["train", "valid", "test"]])
    S["all3"] = (S[["train", "valid", "test"]] > 0).all(axis=1)
    S = S.reset_index(); S.to_csv(ROOT / "research/program/results/tf_nh_summary.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
    print("PROPOSED SETTINGS on every candle size:")
    m1 = (S.market == "MCX") & (S.side == "BUY") & (S.N == 5) & (S.vol == 1.5) & (S.exit == "2.5ATR/2.5R")
    m2 = (S.market == "STOCKS") & (S.side == "SELL") & (S.N == 10) & (S.vol == 2.0) & (S.exit == "2.5ATR/2.5R")
    print(S[m1 | m2].round(3).to_string(index=False))
    print("\nHOW ROBUST each candle size is: variants positive in all 3 periods (of 18), median R across variants")
    R = S[S.n >= 40].groupby(["market", "side", "tf"]).agg(variants=("R", "size"), all3_pos=("all3", "sum"), median_R=("R", "median"),
                                                          best_R=("R", "max")).round(3)
    print(R.to_string())
    print("\nbest robust (all 3 periods positive, n ≥ 60) per market/side/candle:")
    b = S[S.all3 & (S.n >= 60)].sort_values("R", ascending=False).groupby(["market", "side", "tf"]).head(1)
    print(b.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
