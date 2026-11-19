"""REV-MORE-001 (19-Nov-2026, owner: "but the number of TD9 calls decreases"). More calls from the 'above daily EMA200'
reversal SELL idea at 1:1 (stop 2 ATR, target 1R), same harness as rev_ind.py: indicators TD9P / TD9 / WPR20 / STOCH80 /
FISHER / CCI200 on 1d / 4h / 2h / 1h candles, context DT (daily trend down) or none, each with and without the EMA200
filter. Trades are saved so pools can be scored with duplicates (same stock, same day) removed.
python research/program/rev_more.py -> results/rev_more_trades.parquet"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.sell_exits import run  # noqa: E402
from research.program.rev_ind import tops  # noqa: E402

OUT = ROOT / "research/program/results"
INDS = ("TD9P", "TD9", "WPR20", "STOCH80", "FISHER", "CCI200")


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in fr}
    if "STOCKS 1h" not in seg or "STOCKS 1d" not in seg:
        return None
    f1, c1 = seg["STOCKS 1h"]; fd, cd = seg["STOCKS 1d"]
    c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(c1)), c1) if len(c1) != len(f1) else c1
    dtr = SA.daily_trend(fd)
    dcl = fd["close"].astype(float).reset_index(drop=True)
    a200 = pd.Series((dcl > dcl.ewm(span=200, adjust=False).mean()).values.astype(float),
                     index=pd.to_datetime(fd["time"]).dt.normalize().values).shift(1)
    a200 = a200[~a200.index.duplicated(keep="last")]
    frames = {"1d": (fd, cd), "1h": (f1, c1)}
    for hrs, tf in ((2, "2h"), (4, "4h")):
        C, first = anchored(f1, hrs); frames[tf] = (C, c1[first[:len(C)]])
    rows = []
    for tf, (C, cost) in frames.items():
        if len(C) < 300:
            continue
        cost = np.asarray(cost, float)
        if len(cost) != len(C):
            cost = np.interp(np.arange(len(C)), np.linspace(0, len(C) - 1, len(cost)), cost)
        f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
        o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values.astype(np.bool_)
        tt = pd.to_datetime(f["time"]); day = tt.dt.normalize()
        dt = (day.map(dtr) < 0).values; ab = (day.map(a200) > 0).values
        rsi = f["rsi"].values
        S = tops(C)
        maxh = 10 if tf == "1d" else SV.MAXH.get(tf, 40)
        for ind in INDS:
            for ctx, m0 in (("DT", S[ind].values & dt), ("none", S[ind].values)):
                for flt, m in (("all", m0), ("A200", m0 & ab)):
                    if m.sum() < 1:
                        continue
                    for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, m, 2.0, 1.0, maxh, cost, 0.0, 0.0, 0.0, H.CHASE):
                        rows.append((ind, tf, ctx, flt, job[1], tt.iat[i], rr, int(why), rsi[i]))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    rows = []
    with Pool(2) as p:
        for x in p.imap_unordered(one, J, chunksize=2):
            rows += x or []
    T = pd.DataFrame(rows, columns=["ind", "tf", "ctx", "flt", "sym", "t", "R", "why", "rsi"])
    T["period"] = np.where(T.t < SV.P1, "p1", np.where(T.t < SV.P2, "p2", "p3"))
    T.to_parquet(OUT / "rev_more_trades.parquet")
    print(len(T))


if __name__ == "__main__":
    main()
