"""CANDLE-ALL-001 (19-Nov-2026, owner: "find only candlestick based setups"). Every TA-Lib candlestick pattern (61 CDL
functions) on the 181 F&O stock futures (research data 2022-26, front month, never held through a roll, 2x costs).
Bearish patterns -> SELL, bullish -> BUY (TA-Lib's own sign). Candles: daily, 4-hour (day-anchored 09:15 / 13:15) and 1-hour.
ENTRY  NEXT   next candle's open                       BREAK  stop order beyond the pattern candle's low (SELL) / high (BUY)
                                                              within the next 2 candles (confirmation)
STOP   beyond the pattern candle's high (SELL) / low (BUY) + 0.1 ATR; risk must be 0.25-3 ATR
TARGET 1R / 1.5R / 2R; time exit after 10 daily / 20 intraday candles; stop checked first inside a candle
CONTEXT  none · TREND (SELL below EMA50 / BUY above) · TOP (SELL: pattern candle made a 20-candle high / BUY: 20-candle low)
BASE   RANDOM candles (3 %) of the same side with the same stop / target rules
Periods p1 / p2 / p3 as SEARCH-V2. PASS = average R > 0 and > RANDOM in all three periods, >= 40 trades each.
python research/program/candle_all.py -> results/candle_all_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
import talib
from numba import njit
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402

OUT = ROOT / "research/program/results"
PATS = talib.get_function_groups()["Pattern Recognition"]
TGT = np.array([1.0, 1.5, 2.0])


@njit(cache=True)
def sim(o, h, l, c, atr, sw, idx, side, mode, maxh, cost, tgt):
    n = len(c); out = np.full((len(idx), len(tgt)), np.nan)
    for q in range(len(idx)):
        i = idx[q]; s = side[q]
        if i + 2 >= n or not atr[i] > 0:
            continue
        stop = h[i] + 0.1 * atr[i] if s < 0 else l[i] - 0.1 * atr[i]
        e = -1; px = 0.0
        if mode == 0:
            e = i + 1; px = o[i + 1]
        else:
            lev = l[i] if s < 0 else h[i]
            for j in range(i + 1, min(n, i + 3)):
                if sw[j]:
                    break
                if s < 0 and l[j] <= lev:
                    e = j; px = min(o[j], lev); break
                if s > 0 and h[j] >= lev:
                    e = j; px = max(o[j], lev); break
        if e < 0:
            continue
        risk = s * (px - stop)
        if not (0.25 * atr[i] <= risk <= 3.0 * atr[i]):
            continue
        for t in range(len(tgt)):
            tp = px + s * tgt[t] * risk; ex = np.nan
            last = min(n - 1, e + maxh)
            for j in range(e, last + 1):
                if j > e and sw[j]:
                    ex = c[j - 1]; break
                oj = o[j] if j > e else px
                if s < 0:
                    if j > e and oj >= stop:
                        ex = oj; break
                    if h[j] >= stop:
                        ex = stop; break
                    if j > e and oj <= tp:
                        ex = oj; break
                    if l[j] <= tp:
                        ex = tp; break
                else:
                    if j > e and oj <= stop:
                        ex = oj; break
                    if l[j] <= stop:
                        ex = stop; break
                    if j > e and oj >= tp:
                        ex = oj; break
                    if h[j] >= tp:
                        ex = tp; break
                if j == last:
                    ex = c[j]
            out[q, t] = (s * (ex - px) - 2 * cost[i]) / risk
    return out


def frames_of(job):
    fr = EX.frames(job)
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in fr}
    res = {}
    if "STOCKS 1d" in seg:
        res["1d"] = seg["STOCKS 1d"]
    if "STOCKS 1h" in seg:
        f1, c1 = seg["STOCKS 1h"]
        c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(c1)), c1) if len(c1) != len(f1) else c1
        res["1h"] = (f1, c1)
        C, first = anchored(f1, 4); res["4h"] = (C, c1[first[:len(C)]])
    return res


def one(job):
    try:
        fr = frames_of(job)
    except Exception:
        return None
    parts = []
    rng = np.random.default_rng(sum(map(ord, job[1])))
    for tf, (C, cost) in fr.items():
        if len(C) < 300:
            continue
        if len(cost) != len(C):
            cost = np.interp(np.arange(len(C)), np.linspace(0, len(C) - 1, len(cost)), cost)
        o, h, l, c = (C[x].values.astype(float) for x in ("open", "high", "low", "close"))
        f = H.features(C); atr = f["atr"].values.astype(float)
        sw = (C["switch"].values if "switch" in C else np.zeros(len(C), bool)).astype(np.bool_)
        e50 = pd.Series(c).ewm(span=50, adjust=False, min_periods=50).mean().values
        hi20 = pd.Series(h).rolling(20).max().values; lo20 = pd.Series(l).rolling(20).min().values
        t = pd.to_datetime(C["time"]).values
        split = np.where(t < SV.P1, 0, np.where(t < SV.P2, 1, 2))
        maxh = 10 if tf == "1d" else 20
        sigs = {p: getattr(talib, p)(o, h, l, c) for p in PATS}
        r = rng.random(len(c)) < 0.03
        sigs["RANDOM"] = np.where(r, np.where(rng.random(len(c)) < 0.5, 100, -100), 0)
        for p, v in sigs.items():
            idx = np.flatnonzero((v != 0) & (np.arange(len(c)) >= 210))
            if not len(idx):
                continue
            side = np.sign(v[idx]).astype(np.int64)
            trend = np.where(side < 0, c[idx] < e50[idx], c[idx] > e50[idx])
            top = np.where(side < 0, h[idx] >= hi20[idx], l[idx] <= lo20[idx])
            for mode in (0, 1):
                R = sim(o, h, l, c, atr, sw, idx.astype(np.int64), side, mode, maxh, cost, TGT)
                for ti, tg in enumerate(TGT):
                    x = R[:, ti]; ok = np.isfinite(x)
                    for ctx, m in (("none", ok), ("TREND", ok & trend), ("TOP", ok & top)):
                        for sd in (-1, 1):
                            for sp in (0, 1, 2):
                                mm = m & (side == sd) & (split[idx] == sp)
                                if mm.any():
                                    y = x[mm]
                                    parts.append((tf, p, sd, mode, tg, ctx, sp, len(y), float(y.sum()), int((y > 0).sum())))
    return parts


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        A = pd.DataFrame([r for x in p.imap_unordered(one, J, chunksize=2) if x for r in x],
                         columns=["tf", "pat", "side", "entry", "tgt", "ctx", "split", "n", "sumR", "wins"])
    A = A.groupby(["tf", "pat", "side", "entry", "tgt", "ctx", "split"], as_index=False)[["n", "sumR", "wins"]].sum()
    W = A.pivot_table(index=["tf", "pat", "side", "entry", "tgt", "ctx"], columns="split", values=["n", "sumR", "wins"], aggfunc="sum").fillna(0)
    rows = []
    for key, x in W.iterrows():
        tf, pat, sd, en, tg, ctx = key
        n = [x[("n", s)] for s in (0, 1, 2)]; sR = [x[("sumR", s)] for s in (0, 1, 2)]; w = [x[("wins", s)] for s in (0, 1, 2)]
        N = sum(n)
        if N < 60:
            continue
        rows.append(dict(tf=tf, pattern=pat.replace("CDL", ""), side="SELL" if sd < 0 else "BUY", entry="NEXT" if en == 0 else "BREAK", target_R=tg, ctx=ctx,
                         n=int(N), win=round(100 * sum(w) / N, 1), R=round(sum(sR) / N, 3),
                         **{f"p{s+1}_n": int(n[s]) for s in range(3)}, **{f"p{s+1}_R": round(sR[s] / n[s], 3) if n[s] else None for s in range(3)},
                         **{f"p{s+1}_win": round(100 * w[s] / n[s], 1) if n[s] else None for s in range(3)}))
    L = pd.DataFrame(rows)
    base = L[L.pattern == "RANDOM"].set_index(["tf", "side", "entry", "target_R", "ctx"])
    for s in (1, 2, 3):
        L[f"p{s}_rand"] = [base[f"p{s}_R"].get((a, b, c_, d, e), np.nan) for a, b, c_, d, e in zip(L.tf, L.side, L.entry, L.target_R, L.ctx)]
    L["pass"] = np.all([(L[f"p{s}_n"] >= 40) & (L[f"p{s}_R"] > 0) & (L[f"p{s}_R"] > L[f"p{s}_rand"]) for s in (1, 2, 3)], axis=0) & (L.pattern != "RANDOM")
    L["min_win"] = L[["p1_win", "p2_win", "p3_win"]].min(axis=1)
    L.to_csv(OUT / "candle_all_summary.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200)
    c = ["tf", "pattern", "side", "entry", "target_R", "ctx", "n", "win", "R", "p1_win", "p2_win", "p3_win", "p1_R", "p2_R", "p3_R", "p1_rand", "p2_rand", "p3_rand"]
    print(f"combos {len(L)} · PASS {int(L['pass'].sum())} (SELL {int((L['pass'] & (L.side == 'SELL')).sum())})")
    print("\nSELL passes, by worst-period win %:"); print(L[L["pass"] & (L.side == "SELL")].sort_values("min_win", ascending=False).head(30)[c].to_string(index=False))
    print("\nBUY passes:"); print(L[L["pass"] & (L.side == "BUY")].sort_values("min_win", ascending=False).head(15)[c].to_string(index=False))
    print("\nRANDOM baselines:"); print(L[L.pattern == "RANDOM"].head(18)[c].to_string(index=False))


if __name__ == "__main__":
    main()
