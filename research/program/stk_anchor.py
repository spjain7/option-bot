"""STK-ANCHOR-001 (6-Nov-2026): stock 2h / 4h rules on DAY-ANCHORED candles (live-reproducible: 2h 09:15/11:15/13:15/15:15,
4h 09:15-13:15 / 13:15-15:30 like alerts/four_hour.py). Same families, exits, costs, splits and FDR as SEARCH-V2.
python research/program/stk_anchor.py"""
import sys
import time
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402

OUT = ROOT / "research/program/results"


def anchored(f1, hours):
    d = f1.reset_index(drop=True).copy()
    day = d["time"].dt.normalize()
    if hours == 4:
        k = (d["time"].dt.strftime("%H:%M") >= "13:15").astype(int)
    else:
        k = d.groupby(day).cumcount() // hours
    first = np.r_[0, np.flatnonzero(np.diff(day.values.astype("int64") * 10 + k.values) != 0) + 1]
    g = d.groupby([day, k], sort=True)
    C = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
              volume=("volume", "sum"), switch=("switch", "max")).reset_index(drop=True)
    return C, first


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    f1 = cost1 = fd = None
    for seg, f, od, cost in fr:
        if seg == "STOCKS 1h":
            f1, cost1 = f.reset_index(drop=True), np.asarray(cost, float)
        if seg == "STOCKS 1d":
            fd = f
    if f1 is None or fd is None:
        return None
    c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(cost1)), cost1) if len(cost1) != len(f1) else cost1
    rows = []
    for hours, tf in ((2, "2h"), (4, "4h")):
        C, first = anchored(f1, hours)
        if len(C) < 300:
            continue
        f = H.features(C); f["switch"] = C["switch"].values
        dtr = SA.daily_trend(fd)
        reg = SV.regimes(f, fd)
        cost = c1[first[:len(C)]]
        for fam, par, fn, sb, ss in SV.signal_sets(f, dtr, tf) + SA.signal_sets(f, dtr):
            for side, s in ((1, sb), (-1, ss)):
                sig = np.where(np.nan_to_num(np.asarray(s, float)) > 0, side, 0)
                if not sig.any():
                    continue
                for k, r in SA.EXITS:
                    for x in H.simulate(f, sig, side, k, r, SV.MAXH[tf], 0, cost, start=210):
                        if x["status"] == "trade":
                            rows.append(("STOCKS", tf, fam, par, fn, side, f"{k:g}ATR/{r:g}R", x["time"], x["r2"], reg[x["i"]]))
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=["mkt", "tf", "fam", "par", "filt", "side", "exit", "time", "r", "reg"])
    tv = pd.to_datetime(d["time"], format="mixed").values
    d["split"] = np.where(tv < SV.P1, "p1", np.where(tv < SV.P2, "p2", "p3"))
    d["r2_"] = d["r"] ** 2; d["w"] = (d["r"] > 0).astype(int)
    a = d.groupby(["mkt", "tf", "fam", "par", "filt", "side", "exit", "split", "reg"]).agg(
        n=("r", "size"), s=("r", "sum"), ss=("r2_", "sum"), w=("w", "sum")).reset_index()
    a["name"] = job[1]
    return a


def main():
    t0 = time.time()
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        parts = [x for x in p.imap_unordered(one, J, chunksize=2) if x is not None]
    A = pd.concat(parts, ignore_index=True)
    S = SV.summarise(A)
    S.to_csv(OUT / "stk_anchor_summary.csv", index=False)
    R = S[S.robust].sort_values("R", ascending=False)
    pd.set_option("display.width", 250)
    print(f"combinations {len(S)} · robust {len(R)} · {(time.time() - t0) / 60:.0f} min")
    c = ["tf", "fam", "par", "filt", "side", "exit", "n", "win", "R", "p1", "p2", "p3", "R_up", "R_down", "R_flat", "V_hiV", "V_loV", "names_pos", "q"]
    for (tf, sd), g in R.groupby(["tf", "side"]):
        print(f"\n=== {tf} {'BUY' if sd > 0 else 'SELL'}: {len(g)}"); print(g.head(10)[[x for x in c if x in g]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
