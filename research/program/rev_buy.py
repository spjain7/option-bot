"""REV-BUY-001 (19-Nov-2026, owner: "check what is winning for buy and sell w.r.t. reversal strategy"). Reversal BUY
(bottom) signals at 1:1 (stop 2 ATR, target 1R), same harness as rev_ind.py (BUY = mirrored prices). Contexts:
  none · UT (daily trend up: a dip in an uptrend) · DT (daily trend down: catching a falling stock)
Filters: all · A200 (stock above daily EMA200) · B200 (below daily EMA200). Indicators: all 13 of rev_ind.tops.
python research/program/rev_buy.py -> results/rev_buy_trades.parquet, results/rev_buy_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.sell_exits import run  # noqa: E402
from research.program.rev_ind import tops, mirror  # noqa: E402

OUT = ROOT / "research/program/results"


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
    frames = {"1d": (fd, cd)}
    for hrs, tf in ((2, "2h"), (4, "4h")):
        C, first = anchored(f1, hrs); frames[tf] = (C, c1[first[:len(C)]])
    rows = []
    for tf, (C0, cost) in frames.items():
        if len(C0) < 300:
            continue
        cost = np.asarray(cost, float)
        if len(cost) != len(C0):
            cost = np.interp(np.arange(len(C0)), np.linspace(0, len(C0) - 1, len(cost)), cost)
        C = mirror(C0)
        f = H.features(C); f["switch"] = C0["switch"].values if "switch" in C0 else np.zeros(len(C), bool)
        o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values.astype(np.bool_)
        tt = pd.to_datetime(C0["time"]); day = tt.dt.normalize()
        d = day.map(dtr).values; ab = (day.map(a200) > 0).values; bl = (day.map(a200) == 0).values
        S = tops(C)
        maxh = 10 if tf == "1d" else SV.MAXH.get(tf, 40)
        for ind, s in S.items():
            s = s.values
            for ctx, m0 in (("none", s), ("UT", s & (d > 0)), ("DT", s & (d < 0))):
                for flt, m in (("all", m0), ("A200", m0 & ab), ("B200", m0 & bl)):
                    if m.sum() < 1:
                        continue
                    for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, m, 2.0, 1.0, maxh, cost, 0.0, 0.0, 0.0, H.CHASE):
                        rows.append((ind, tf, ctx, flt, job[1], tt.iat[i], rr, int(why), mfe))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    rows = []
    with Pool(2) as p:
        for x in p.imap_unordered(one, J, chunksize=2):
            rows += x or []
    T = pd.DataFrame(rows, columns=["ind", "tf", "ctx", "flt", "sym", "t", "R", "why", "mfe"])
    T["period"] = np.where(T.t < SV.P1, "p1", np.where(T.t < SV.P2, "p2", "p3"))
    T.to_parquet(OUT / "rev_buy_trades.parquet")
    out = []
    for k, g in T.groupby(["ind", "tf", "ctx", "flt"]):
        r = dict(zip(["ind", "tf", "ctx", "flt"], k), n=len(g), win=round(100 * (g.R > 0).mean(), 1), sl=round(100 * (g.why == 1).mean(), 1), R=round(g.R.mean(), 3))
        for p in ("p1", "p2", "p3"):
            h_ = g[g.period == p]
            r.update({f"{p}n": len(h_), f"{p}w": round(100 * (h_.R > 0).mean(), 1) if len(h_) else None, f"{p}R": round(h_.R.mean(), 3) if len(h_) else None})
        out.append(r)
    L = pd.DataFrame(out)
    L["ok"] = (L[["p1R", "p2R", "p3R"]].min(axis=1) > 0) & (L[["p1n", "p2n", "p3n"]].min(axis=1) >= 20)
    L.to_csv(OUT / "rev_buy_summary.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(L[L.ok].sort_values("R", ascending=False).to_string(index=False))
    print(L[L.n >= 100].sort_values("win", ascending=False).head(25).to_string(index=False))


if __name__ == "__main__":
    main()
