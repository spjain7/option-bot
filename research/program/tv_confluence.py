"""TV-CONFLUENCE-001 (19-Nov-2026, owner: "combine and find something"). Confluence of the 19 TradingView / Chartink SELL
scripts of tv_scripts.py: score = number of DIFFERENT scripts that fired on this candle or the 2 before. SELL when the score
first reaches K (K = 2..7), optionally only with the stock in a daily downtrend (DT). Same harness (sell_exits.run): next open,
0.5-ATR chase limit, 2x costs, never through a roll. Exits: stop 2 ATR x target 1 / 1.5 / 2 / 3R, and half at 1R + stop to cost.
python research/program/tv_confluence.py -> results/tv_confluence_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.sell_exits import run  # noqa: E402
from research.program.tv_scripts import signals  # noqa: E402

OUT = ROOT / "research/program/results"
KS = (2, 3, 4, 5, 6, 7)
EX_ = [("2ATR 1R", 2.0, 1.0, 0.0, 0.0), ("2ATR 1.5R", 2.0, 1.5, 0.0, 0.0), ("2ATR 2R", 2.0, 2.0, 0.0, 0.0), ("2ATR 3R", 2.0, 3.0, 0.0, 0.0),
       ("2ATR half1R+3R", 2.0, 3.0, 1.0, 1.0)]


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
    frames = {"1d": (fd, cd)}
    for hrs, tf in ((2, "2h"), (4, "4h")):
        C, first = anchored(f1, hrs); frames[tf] = (C, c1[first[:len(C)]])
    rows = []
    for tf, (C, cost) in frames.items():
        if len(C) < 300:
            continue
        f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
        o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values.astype(np.bool_); t = pd.to_datetime(f["time"]).values
        cost = np.asarray(cost, float)
        if len(cost) != len(c):
            cost = np.interp(np.arange(len(c)), np.linspace(0, len(c) - 1, len(cost)), cost)
        down = (pd.to_datetime(f["time"]).dt.normalize().map(dtr) < 0).values
        S = signals(C, tf != "1d"); S.pop("RANDOM", None)
        M = np.column_stack([s.values for s in S.values()]).astype(int)
        recent = pd.DataFrame(M).rolling(3, min_periods=1).max().values.sum(axis=1)       # scripts firing in the last 3 candles
        split = np.where(t < SV.P1, 0, np.where(t < SV.P2, 1, 2))
        maxh = 10 if tf == "1d" else SV.MAXH.get(tf, 40)
        for K in KS:
            hit = recent >= K
            sig = hit & ~np.r_[False, hit[:-1]]                                            # first candle reaching K
            for flt, m in (("none", sig), ("DT", sig & down)):
                if m.sum() < 2:
                    continue
                for en, k, r, half, be in EX_:
                    for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, m, k, r, maxh, cost, half, be, 0.0, H.CHASE):
                        rows.append((tf, K, flt, en, int(split[i]), rr))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    acc = {}
    with Pool(2) as p:
        for rows in p.imap_unordered(one, J, chunksize=2):
            for tf, K, fl, en, sp, rr in rows or []:
                a = acc.setdefault((tf, K, fl, en, sp), [0, 0.0, 0]); a[0] += 1; a[1] += rr; a[2] += rr > 0
    A = pd.DataFrame([(*k, *v) for k, v in acc.items()], columns=["tf", "K", "filt", "exit", "split", "n", "sumR", "wins"])
    W = A.pivot_table(index=["tf", "K", "filt", "exit"], columns="split", values=["n", "sumR", "wins"], aggfunc="sum").fillna(0)
    rows = []
    for key, x in W.iterrows():
        n = [x[("n", s)] for s in (0, 1, 2)]; sR = [x[("sumR", s)] for s in (0, 1, 2)]; w = [x[("wins", s)] for s in (0, 1, 2)]
        N = sum(n)
        if N < 30:
            continue
        rows.append(dict(zip(["tf", "K", "filt", "exit"], key), n=int(N), win=round(100 * sum(w) / N, 1), R=round(sum(sR) / N, 3),
                         **{f"p{s+1}_n": int(n[s]) for s in range(3)}, **{f"p{s+1}_win": round(100 * w[s] / n[s], 1) if n[s] else None for s in range(3)},
                         **{f"p{s+1}_R": round(sR[s] / n[s], 3) if n[s] else None for s in range(3)}))
    L = pd.DataFrame(rows); L["all3_pos"] = (L[["p1_R", "p2_R", "p3_R"]].min(axis=1) > 0) & (L[["p1_n", "p2_n", "p3_n"]].min(axis=1) >= 30)
    L.to_csv(OUT / "tv_confluence_summary.csv", index=False)
    pd.set_option("display.width", 240); pd.set_option("display.max_rows", 300)
    print(L.sort_values(["tf", "filt", "exit", "K"]).to_string(index=False))


if __name__ == "__main__":
    main()
