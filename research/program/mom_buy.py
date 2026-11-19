"""MOM-BUY-001 (19-Nov-2026, owner: "find more strategy and do depth" -> stock BUY via momentum). Momentum / breakout BUY
families for the 181 F&O stock futures (research data 2022-26, front month, never through a roll, 2x costs, next-open entry,
0.5-ATR chase limit, stop first; sell_exits.run on mirrored prices = BUY). New vs SEARCH-V2: relative strength vs NIFTY,
52-week high, OI long build-up, Darvas box, volatility contraction (VCP-style), gap-and-hold, pull-back in a leader,
first-hour high break, and MARKET REGIME filters (NIFTY trend, breadth) – the 2025-26 down-market killed every BUY so far.
Families (signal on the candle close):
  HI52     close above the 250-day high (daily) / the 52-week high from daily data (4h: daily level)
  BO20V    close above the 20-candle high, volume >= 1.5x
  RSLEAD   20-day return beats NIFTY's by >= 5 % and close above the 20-candle high
  DARVAS   10-candle range <= 2.5 ATR for 10 candles, then a close above it
  VCP      ATR(10) < 0.7 x ATR(50) and close above the 20-candle high
  GAPHOLD  opens >= 0.5 ATR above the prior high and closes above its open (daily)
  PBLEAD   leader (RS >= 5 %) pulls back to EMA20 (low <= EMA20 < close), daily trend up
  FHB      first-hour (09:15 candle) high broken by a later 1h close (2h / 1h frames)
  OILB     daily close up >= 1 % with OI up (long build-up) and close in the top 30 % of the candle
Filters: none · UT (stock daily trend up) · NUP (NIFTY daily trend up, previous day) · B50 (> 50 % stocks up) · UT+NUP ·
UT+B50. Exits: SL x target 1.5x2, 2x1.5, 2x2, 2x3 ATR/R, and E_TR (2 ATR, half at 1R + stop to cost, rest trails 2 ATR).
PASS = R > 0 and above RANDOM-BUY (same filter / exit) in 2022-24, 2024-25 and 2025-26 with >= 30 trades each.
python research/program/mom_buy.py -> results/mom_buy_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.sell_exits import run  # noqa: E402
from research.program.rev_ind import mirror  # noqa: E402

OUT = ROOT / "research/program/results"
EXITS = [("1.5x2", 1.5, 2.0, 0.0, 0.0, 0.0), ("2x1.5", 2.0, 1.5, 0.0, 0.0, 0.0), ("2x2", 2.0, 2.0, 0.0, 0.0, 0.0),
         ("2x3", 2.0, 3.0, 0.0, 0.0, 0.0), ("E_TR", 2.0, 99.0, 1.0, 1.0, 2.0)]
CTX = {}


def market():
    nf = [x for x in EX.frames(("nse", "NIFTY", None)) if "1d" in x[0]][0][1].reset_index(drop=True)
    c = nf["close"].astype(float); day = pd.to_datetime(nf["time"]).dt.normalize()
    ret20 = pd.Series((c / c.shift(20) - 1).values, index=day.values)
    tr = SA.daily_trend(nf)
    return ret20.shift(1), tr


def trend_only(job):
    try:
        for s, f, od, c in EX.frames(job):
            if s == "STOCKS 1d":
                return SA.daily_trend(f.reset_index(drop=True)).rename(job[1])
    except Exception:
        return None


def fam(C, tf, d_hi250, d_rs, od_day):
    o, h, l, c, v = (C[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    a14 = tr.ewm(alpha=1 / 14, adjust=False).mean(); a10 = tr.ewm(alpha=1 / 10, adjust=False).mean(); a50 = tr.ewm(alpha=1 / 50, adjust=False).mean()
    hh20 = h.shift(1).rolling(20).max(); vx = v / v.rolling(20).mean().shift(1)
    e20 = c.ewm(span=20, adjust=False).mean()
    rg = (h - l).replace(0, np.nan); pos = (c - l) / rg
    S = {}
    S["HI52"] = (c > d_hi250) & (c.shift(1) <= d_hi250.shift(1))
    S["BO20V"] = (c > hh20) & (vx >= 1.5)
    S["RSLEAD"] = (d_rs >= 0.05) & (c > hh20)
    box = h.shift(1).rolling(10).max() - l.shift(1).rolling(10).min()
    tight = box <= 2.5 * a14.shift(1)
    S["DARVAS"] = tight.rolling(10).min().astype(bool) & (c > h.shift(1).rolling(10).max())
    S["VCP"] = (a10 < 0.7 * a50) & (c > hh20)
    S["PBLEAD"] = (d_rs >= 0.05) & (l <= e20) & (c > e20) & (c > o)
    if tf == "1d":
        S["GAPHOLD"] = (o >= h.shift(1) + 0.5 * a14.shift(1)) & (c > o)
        S["OILB"] = (od_day == 1) & (c >= c.shift(1) * 1.01) & (pos >= 0.7)
    else:
        t = pd.to_datetime(C["time"]); day = t.dt.normalize()
        fh = h.where(t.dt.strftime("%H:%M") == "09:15").groupby(day).transform("max") if tf == "1h" else None
        if fh is not None:
            S["FHB"] = (t.dt.strftime("%H:%M") > "09:15") & (c > fh) & ~((c.shift(1) > fh) & (day == day.shift(1)))
    return {k: x.fillna(False).astype(bool).values for k, x in S.items()}


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float), od) for s, f, od, c in fr}
    if "STOCKS 1h" not in seg or "STOCKS 1d" not in seg:
        return None
    f1, c1, _ = seg["STOCKS 1h"]; fd, cd, odd = seg["STOCKS 1d"]
    c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(c1)), c1) if len(c1) != len(f1) else c1
    dtr = SA.daily_trend(fd)
    dday = pd.to_datetime(fd["time"]).dt.normalize()
    dc = fd["close"].astype(float).reset_index(drop=True)
    hi250 = pd.Series(fd["high"].astype(float).shift(1).rolling(250, min_periods=200).max().values, index=dday.values)
    rs = pd.Series((dc / dc.shift(20) - 1).values, index=dday.values) - CTX["nret20"].reindex(dday.values).ffill().values
    rs_prev, hi_prev = rs.shift(1), hi250
    od_s = pd.Series(np.asarray(odd), index=dday.values)
    frames = {"1d": (fd, cd), "1h": (f1, c1)}
    for hrs, tf in ((2, "2h"), (4, "4h")):
        C, first = anchored(f1, hrs); frames[tf] = (C, c1[first[:len(C)]])
    acc = {}
    rng = np.random.default_rng(sum(map(ord, job[1])) + 11)
    for tf, (C, cost) in frames.items():
        if len(C) < 300:
            continue
        cost = np.asarray(cost, float)
        if len(cost) != len(C):
            cost = np.interp(np.arange(len(C)), np.linspace(0, len(C) - 1, len(cost)), cost)
        tt = pd.to_datetime(C["time"]); day = tt.dt.normalize()
        if tf == "1d":
            d_hi = pd.Series(hi250.values, index=C.index); d_rs = pd.Series(rs_prev.values, index=C.index); od_day = pd.Series(od_s.values, index=C.index)
        else:
            d_hi = pd.Series(day.map(hi_prev.groupby(level=0).last()).values, index=C.index)
            d_rs = pd.Series(day.map(rs_prev.groupby(level=0).last()).values, index=C.index); od_day = None
        S = fam(C, tf, d_hi, d_rs, od_day)
        S["RANDOM"] = rng.random(len(C)) < 0.03
        M = mirror(C)
        f = H.features(M); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(M), bool)
        o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values.astype(np.bool_)
        ut = (day.map(dtr) > 0).values; nup = (day.map(CTX["ntr"]) > 0).values; b50 = (day.map(CTX["breadth"]) > 0.5).values
        split = np.where(tt.values < SV.P1, 0, np.where(tt.values < SV.P2, 1, 2))
        maxh = 10 if tf == "1d" else SV.MAXH.get(tf, 40)
        for nm, s in S.items():
            for flt, m in (("none", s), ("UT", s & ut), ("NUP", s & nup), ("B50", s & b50), ("UT+NUP", s & ut & nup), ("UT+B50", s & ut & b50)):
                if m.sum() < 1:
                    continue
                for en, k, r, half, be, trail in EXITS:
                    for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, m, k, r, maxh if en != "E_TR" else 2 * maxh, cost, half, be, trail, H.CHASE):
                        a = acc.setdefault((nm, tf, flt, en, int(split[i])), [0, 0.0, 0, 0]); a[0] += 1; a[1] += rr; a[2] += rr > 0; a[3] += why == 1
    return acc


def summarise(acc, keys, path):
    A = pd.DataFrame([(*k_, *v) for k_, v in acc.items()], columns=keys + ["split", "n", "sumR", "wins", "sl"])
    W = A.pivot_table(index=keys, columns="split", values=["n", "sumR", "wins", "sl"], aggfunc="sum").fillna(0)
    rows = []
    for key, x in W.iterrows():
        n = [x.get(("n", s), 0) for s in (0, 1, 2)]; sR = [x.get(("sumR", s), 0) for s in (0, 1, 2)]; w = [x.get(("wins", s), 0) for s in (0, 1, 2)]
        N = sum(n)
        if N < 30:
            continue
        rows.append(dict(zip(keys, key), n=int(N), win=round(100 * sum(w) / N, 1), sl=round(100 * sum(x.get(("sl", s), 0) for s in (0, 1, 2)) / N, 1),
                         R=round(sum(sR) / N, 3), **{f"p{s+1}_n": int(n[s]) for s in range(3)},
                         **{f"p{s+1}_win": round(100 * w[s] / n[s], 1) if n[s] else None for s in range(3)},
                         **{f"p{s+1}_R": round(sR[s] / n[s], 3) if n[s] else None for s in range(3)}))
    L = pd.DataFrame(rows)
    rk = [k for k in keys if k != keys[0]]
    base = L[L[keys[0]] == "RANDOM"].set_index(rk)
    for s in (1, 2, 3):
        L[f"p{s}_rand"] = [base[f"p{s}_R"].get(kk, np.nan) for kk in zip(*[L[k] for k in rk])]
    L["pass"] = np.all([(L[f"p{s}_R"] > 0) & (L[f"p{s}_R"] > L[f"p{s}_rand"].fillna(-9)) & (L[f"p{s}_n"] >= 30) for s in (1, 2, 3)], axis=0) & (L[keys[0]] != "RANDOM")
    L["minR"] = L[["p1_R", "p2_R", "p3_R"]].min(axis=1)
    L.to_csv(path, index=False)
    return L


def main():
    ret20, ntr = market()
    CTX["nret20"], CTX["ntr"] = ret20, ntr
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        tr = [x for x in p.imap_unordered(trend_only, J, chunksize=4) if x is not None]
    B = pd.concat(tr, axis=1); CTX["breadth"] = (B > 0).sum(axis=1) / B.notna().sum(axis=1)
    acc = {}
    with Pool(2) as p:
        for a in p.imap_unordered(one, J, chunksize=2):
            for k_, v in (a or {}).items():
                x = acc.setdefault(k_, [0, 0.0, 0, 0])
                for q in range(4):
                    x[q] += v[q]
    L = summarise(acc, ["fam", "tf", "flt", "exit"], OUT / "mom_buy_summary.csv")
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200)
    c = ["fam", "tf", "flt", "exit", "n", "win", "sl", "R", "p1_R", "p2_R", "p3_R", "p1_rand", "p2_rand", "p3_rand", "pass"]
    print("PASSED:", int(L["pass"].sum()), "of", len(L))
    print(L[L["pass"]].sort_values("R", ascending=False)[c].head(40).to_string(index=False))
    print(L[L.fam != "RANDOM"].sort_values("minR", ascending=False)[c].head(30).to_string(index=False))


if __name__ == "__main__":
    main()
