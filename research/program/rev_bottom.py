"""REV-BOTTOM-001 (19-Nov-2026, owner: "find bottom catcher strategy and test"). Dip-buying / bottom setups for NSE stock
futures BUY, built for bottoms (the 13 classic reversal indicators all failed as BUY, rev_buy.py):
  RSI2_10   RSI(2) < 10 and close above EMA200 (Connors)            RSI2_5    RSI(2) < 5 and close above EMA200
  IBS20     close in the bottom 20 % of the candle, 3 lower closes, above EMA200
  LOW7      close = 7-candle low, above EMA200 (Connors double-7 entry)
  CAPIT     close at a 20-candle low area, volume >= 2x, close in the top 40 % of the candle (capitulation / hammer)
  KEYREV    3 lower lows, then a close above the previous candle's high (key reversal), above EMA200
  GAPREV    gaps down >= 1 ATR at the open, closes above the open (gap-down reversal)
Exits (entry next open, 0.5-ATR chase limit, stop checked first, 2x costs, never held through a roll, one trade at a time):
  SL2_1R    stop 2 ATR, target 1R                 SMA5      stop 2 ATR, exit at the first close above SMA(5) (Connors)
  PREVHI    stop 2 ATR, exit at the first close above the previous candle's high
Max hold 10 candles. Candles: daily, 4-hour. Filters: all, UT (daily trend up), B50 (> 50 % of F&O stocks in a daily uptrend).
python research/program/rev_bottom.py -> results/rev_bottom_trades.parquet, results/rev_bottom_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402

OUT = ROOT / "research/program/results"
MAXH = 10


def rsi(c, n):
    d = c.diff(); a = 1 / n
    return 100 - 100 / (1 + d.clip(lower=0).ewm(alpha=a, adjust=False).mean() / (-d.clip(upper=0)).ewm(alpha=a, adjust=False).mean().replace(0, np.nan))


def signals(f):
    o, h, l, c, v = (f[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
    at = f["atr"].astype(float); e200 = c.ewm(span=200, adjust=False).mean(); above = c > e200
    rg = (h - l).replace(0, np.nan); ibs = (c - l) / rg
    r2 = rsi(c, 2)
    S = {"RSI2_10": (r2 < 10) & above, "RSI2_5": (r2 < 5) & above,
         "IBS20": (ibs < 0.2) & (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3)) & above,
         "LOW7": (c <= c.rolling(7).min()) & above,
         "CAPIT": (l <= l.shift(1).rolling(20).min()) & (v >= 2 * v.rolling(20).mean().shift(1)) & (ibs >= 0.6),
         "KEYREV": (l.shift(1) < l.shift(2)) & (l.shift(2) < l.shift(3)) & (l.shift(3) < l.shift(4)) & (c > h.shift(1)) & above,
         "GAPREV": (o <= c.shift(1) - at.shift(1)) & (c > o)}
    first = {k: (s.fillna(False) & ~s.fillna(False).shift(1, fill_value=False)).values for k, s in S.items()}   # first candle of a run
    return first


def sim(f, sig, mode, cost, sw):
    o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
    sma5 = pd.Series(c).rolling(5).mean().values
    n = len(c); out = []; i = 210
    while i < n - 2:
        if not sig[i] or not np.isfinite(at[i]) or at[i] <= 0:
            i += 1; continue
        e = o[i + 1]
        if e > c[i] + 0.5 * at[i] or sw[i + 1]:
            i += 1; continue
        R = 2.0 * at[i]; stop = e - R; tgt = e + R
        px = None; why = 3; j = i + 1
        for j in range(i + 1, min(n, i + 1 + MAXH)):
            if j > i + 1 and sw[j]:
                px, why = c[j - 1], 4; j -= 1; break
            if l[j] <= stop:
                px, why = min(o[j], stop) if j > i + 1 else stop, 1; break
            if mode == "SL2_1R" and h[j] >= tgt:
                px, why = max(o[j], tgt) if j > i + 1 else tgt, 2; break
            if mode == "SMA5" and c[j] > sma5[j]:
                px, why = c[j], 2; break
            if mode == "PREVHI" and j > i + 1 and c[j] > h[j - 1]:
                px, why = c[j], 2; break
        if px is None:
            px = c[j]
        out.append((i, j, (px - e) / R - 2 * cost[i] / R, why))
        i = j + 1
    return out


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
    C4, first = anchored(f1, 4); frames["4h"] = (C4, c1[first[:len(C4)]])
    rows = []
    for tf, (C, cost) in frames.items():
        if len(C) < 300:
            continue
        cost = np.asarray(cost, float)
        if len(cost) != len(C):
            cost = np.interp(np.arange(len(C)), np.linspace(0, len(C) - 1, len(cost)), cost)
        f = H.features(C)
        sw = (C["switch"].values if "switch" in C else np.zeros(len(C), bool)).astype(bool)
        tt = pd.to_datetime(f["time"]); ut = (tt.dt.normalize().map(dtr) > 0).values
        for nm, s in signals(f).items():
            for mode in ("SL2_1R", "SMA5", "PREVHI"):
                for i, j, rr, why in sim(f, s, mode, cost, sw):
                    rows.append((nm, tf, mode, job[1], tt.iat[i], bool(ut[i]), rr, why, j - i))
    return rows, dtr.rename(job[1])


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    rows, trends = [], []
    with Pool(2) as p:
        for x in p.imap_unordered(one, J, chunksize=2):
            if x:
                rows += x[0]; trends.append(x[1])
    T = pd.DataFrame(rows, columns=["sig", "tf", "exit", "sym", "t", "ut", "R", "why", "bars"])
    B = pd.concat(trends, axis=1); breadth = (B > 0).sum(axis=1) / B.notna().sum(axis=1)
    T["breadth_up"] = pd.to_datetime(T.t).dt.normalize().map(breadth)
    T["period"] = np.where(T.t < SV.P1, "p1", np.where(T.t < SV.P2, "p2", "p3"))
    T.to_parquet(OUT / "rev_bottom_trades.parquet")
    out = []
    for flt, m in (("all", T.R.notna()), ("UT", T.ut), ("B50", T.breadth_up > 0.5), ("UT+B50", T.ut & (T.breadth_up > 0.5))):
        for k, g in T[m].groupby(["sig", "tf", "exit"]):
            r = dict(zip(["sig", "tf", "exit"], k), flt=flt, n=len(g), win=round(100 * (g.R > 0).mean(), 1), sl=round(100 * (g.why == 1).mean(), 1),
                     R=round(g.R.mean(), 3), bars=round(g.bars.mean(), 1))
            for p in ("p1", "p2", "p3"):
                h_ = g[g.period == p]
                r.update({f"{p}n": len(h_), f"{p}w": round(100 * (h_.R > 0).mean(), 1) if len(h_) else None, f"{p}R": round(h_.R.mean(), 3) if len(h_) else None})
            out.append(r)
    L = pd.DataFrame(out)
    L["ok"] = (L[["p1R", "p2R", "p3R"]].min(axis=1) > 0) & (L[["p1n", "p2n", "p3n"]].min(axis=1) >= 20)
    L.to_csv(OUT / "rev_bottom_summary.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    print(L[L.ok].sort_values("R", ascending=False).to_string(index=False))
    print(L[L.n >= 100].sort_values("win", ascending=False).head(30).to_string(index=False))


if __name__ == "__main__":
    main()
