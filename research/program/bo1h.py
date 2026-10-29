"""BO1H-001 (29-Oct-2026, owner request) – HOURLY volume breakout for futures, same rule family as the live 3h call:
close beyond the 20-candle high/low · volume > 1.5× the 20-candle average · EMA200 side · OI confirms · no nearby resistance.
Markets: MCX (7) + index (NIFTY/BANKNIFTY) Angel 1h futures, stock futures 1h (Angel, ~180 names), Jul-2022 → Oct-2026.
OI: previous completed day's label (+1 long buildup / −1 short buildup / 0 other) – index & stocks only (MCX has none).
Resistance: older level = highest high (lowest low) of bars 21-120 back; "room" = distance to it in ATR (none = open sky).
Execution: harness.simulate (entry next bar open, 0.5-ATR chase rule, stop k·ATR, target R, stop first in a bar, gaps fill at
the open, roll exit, max 40 bars, stop-width cap 2.5 %), costs 1× and 2×. Split: train < 2024-07 ≤ valid < 2025-07 ≤ test.
python research/program/bo1h.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX  # noqa: E402

OUT = ROOT / "research/program/results"
T1, T2 = pd.Timestamp("2024-07-01"), pd.Timestamp("2025-07-01")
EXITS = {"stop2·2R": (2.0, 2.0), "stop2·1R": (2.0, 1.0), "stop1.5·2R": (1.5, 2.0)}


def run(job):
    try:
        fr = EX.frames(job)
    except Exception as e:
        print("skip", job[:2], e); return []
    rows = []
    for seg, f0, od, cost in fr:
        if not seg.endswith("1h") or len(f0) < 400:
            continue
        mkt = seg.split()[0]
        f = H.features(f0.reset_index(drop=True))
        f["switch"] = f0["switch"].values
        sig = H.bo_signal(f)
        hm = f["time"].dt.strftime("%H:%M").values
        for k_name, (k, r) in EXITS.items():
            for side in (1, -1):
                for t in H.simulate(f, sig, side, k, r, 40, 2.5, cost):
                    if t["status"] != "trade":
                        continue
                    i = t["i"]
                    a = f["atr"].iat[i]
                    lvl = f["hi120"].iat[i] if side > 0 else f["lo120"].iat[i]
                    room = side * (lvl - f["close"].iat[i]) / a if np.isfinite(lvl) else np.inf
                    rows.append((mkt, job[1], k_name, "BUY" if side > 0 else "SELL", t["time"], hm[i], int(od[i]),
                                 float(room), float(f["volx"].iat[i]), t["exit"], t["r1"], t["r2"]))
    return rows


def split(t):
    return np.where(t < T1, "train", np.where(t < T2, "valid", "test"))


def summ(g):
    r = g["r1"].values
    w = r[r > 0]; l_ = r[r <= 0]
    return pd.Series(dict(n=len(r), win=(r > 0).mean() * 100, exp1=r.mean(), exp2=g["r2"].mean(),
                          pf=w.sum() / -l_.sum() if l_.sum() < 0 else np.nan))


def main():
    J = [j for j in EX.jobs() if j[0] in ("mi", "stk")]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(run, J, chunksize=2) for r in x]
    T = pd.DataFrame(rows, columns=["market", "name", "exit", "side", "time", "hm", "oi", "room", "volx", "why", "r1", "r2"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T["split"] = split(T["time"])
    T.to_csv(OUT / "bo1h_trades.csv.gz", index=False)
    s = np.where(T["side"] == "BUY", 1, -1)
    T["oi_ok"] = np.where(T["market"] == "MCX", True, T["oi"] != -s)          # OI not against the call
    T["oi_conf"] = np.where(T["market"] == "MCX", True, T["oi"] == s)         # OI confirms (long / short buildup)
    tgt_atr = T["exit"].map({"stop2·2R": 4.0, "stop2·1R": 2.0, "stop1.5·2R": 3.0})
    T["room_ok"] = (T["room"] >= tgt_atr) | (T["room"] < 0)                   # no older level before the target
    T["late"] = (T["market"] != "MCX") & T["hm"].isin(["14:15", "15:15"])
    V = {"base": T["exit"] != "", "+OI not against": T["oi_ok"], "+OI confirms": T["oi_conf"], "+no resistance before target": T["room_ok"],
         "+OI not against +room": T["oi_ok"] & T["room_ok"], "+OI confirms +room": T["oi_conf"] & T["room_ok"],
         "+OI not against +room, no 14:15/15:15": T["oi_ok"] & T["room_ok"] & ~T["late"]}
    out = []
    for vn, m in V.items():
        g = T[m]
        for keys, gg in g.groupby(["market", "side", "exit", "split"]):
            out.append(dict(variant=vn, market=keys[0], side=keys[1], exit=keys[2], split=keys[3], **summ(gg)))
        for keys, gg in g.groupby(["market", "side", "exit"]):
            out.append(dict(variant=vn, market=keys[0], side=keys[1], exit=keys[2], split="ALL", **summ(gg)))
    S = pd.DataFrame(out)
    S.to_csv(OUT / "bo1h_summary.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    P = S.pivot_table(index=["variant", "market", "side", "exit"], columns="split", values="exp2").round(3)
    N = S.pivot_table(index=["variant", "market", "side", "exit"], columns="split", values="n")
    print(P.join(N[["ALL"]].rename(columns={"ALL": "n"})).to_string())


if __name__ == "__main__":
    main()
