"""TF5H-001 (30-Oct-2026, owner: "5-hour candles – nobody uses them, try"). 5-hour futures candles from 1-hour bars:
  MCX     day-anchored blocks 09-14 / 14-19 / 19-close (3 per session)
  NSE     continuous: every 5 consecutive 1-hour bars across days (NSE session is only 6.25 h)
Rule family = the live breakout: close beyond the N-candle high/low, volume > X× the 20-candle average, EMA200 side;
stop k ATR, target R, max 40 candles, stop cap 2.5 % (stocks 4 %). Variants: N 5/10/20 · volume 1.5/2.0 · (k, R) (2,2) (2.5,2.5) (1.5,3).
Compared with the same rule on 3-hour and daily candles. 2× costs, splits train < 2024-07 ≤ valid < 2025-07 ≤ test.
python research/program/tf5h.py"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX  # noqa: E402

T1, T2 = pd.Timestamp("2024-07-01"), pd.Timestamp("2025-07-01")
VARIANTS = list(itertools.product((5, 10, 20), (1.5, 2.0), ((2.0, 2.0), (2.5, 2.5), (1.5, 3.0))))


def five_hour(f1, market):
    f1 = f1.sort_values("time").reset_index(drop=True)
    if market == "MCX":
        hr = f1["time"].dt.hour
        blk = np.where(hr < 14, 0, np.where(hr < 19, 1, 2))
        key = f1["time"].dt.normalize().astype("int64") // 10**9 * 10 + blk
    else:
        key = np.arange(len(f1)) // 5
    g = f1.groupby(key, sort=True)
    out = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum"), switch=("switch", "max")).reset_index(drop=True)
    return out


def one(job):
    try:
        fr = EX.frames(job)
    except Exception as e:
        return []
    rows = []
    for seg, f0, od, cost in fr:
        market, tf = seg.split()[0], seg.split()[-1]
        if tf not in ("1h", "3h", "1d"):
            continue
        frames = {"5h": five_hour(f0, market)} if tf == "1h" else {tf: f0.reset_index(drop=True)}
        for name_tf, f_ in frames.items():
            if len(f_) < 260:
                continue
            f = H.features(f_); f["switch"] = f_["switch"].values
            c_ = np.interp(np.arange(len(f)), np.linspace(0, len(f) - 1, len(cost)), cost) if len(cost) != len(f) else cost
            cap = 4.0 if market == "STOCKS" else (4.0 if name_tf == "1d" else 2.5)
            for N, vx, (k, r) in VARIANTS:
                hh = f["high"].shift(1).rolling(N).max(); ll = f["low"].shift(1).rolling(N).min()
                sig = np.where((f.close > hh) & (f.volx > vx) & (f.close > f.ema200), 1,
                               np.where((f.close < ll) & (f.volx > vx) & (f.close < f.ema200), -1, 0))
                for side in (1, -1):
                    for x in H.simulate(f, sig, side, k, r, 40, cap, c_):
                        if x["status"] == "trade":
                            rows.append((market, job[1], name_tf, N, vx, f"{k:g}ATR/{r:g}R", "BUY" if side > 0 else "SELL", x["time"], x["r2"]))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] in ("mi", "stk")]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(one, J, chunksize=2) for r in x]
    T = pd.DataFrame(rows, columns=["market", "name", "tf", "N", "vol", "exit", "side", "time", "r2"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T["split"] = np.where(T.time < T1, "train", np.where(T.time < T2, "valid", "test"))
    T.to_csv(ROOT / "research/program/results/tf5h_trades.csv.gz", index=False)
    g = T.groupby(["market", "tf", "side", "N", "vol", "exit"])
    S = g.r2.agg(n="size", R="mean").join(T.pivot_table(index=["market", "tf", "side", "N", "vol", "exit"], columns="split",
                                                          values="r2", aggfunc="mean")[["train", "valid", "test"]])
    S["all3_pos"] = (S[["train", "valid", "test"]] > 0).all(axis=1)
    S = S.reset_index()
    S.to_csv(ROOT / "research/program/results/tf5h_summary.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 400)
    print("LIVE-LIKE setting (N 20, volume 1.5, 2ATR/2R) on every timeframe:")
    print(S[(S.N == 20) & (S.vol == 1.5) & (S.exit == "2ATR/2R")].round(3).to_string(index=False))
    print("\n5-HOUR: settings positive in all three periods (n ≥ 60):")
    print(S[(S.tf == "5h") & S.all3_pos & (S.n >= 60)].sort_values("R", ascending=False).round(3).head(25).to_string(index=False))
    for m in ("MCX", "INDEX", "STOCKS"):
        b = S[(S.market == m) & S.all3_pos & (S.n >= 60)].sort_values("R", ascending=False).head(3)
        print(f"\nbest robust settings, {m} (any timeframe):"); print(b.round(3).to_string(index=False) if len(b) else "none")


if __name__ == "__main__":
    main()
