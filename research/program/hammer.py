"""HAM-001 (28-Oct-2026) – owner's request: on 1-hour candles, BUY a HAMMER after a downtrend (stop below the hammer's low)
and SELL a HANGING MAN after an uptrend (stop above its high). Stock futures, index futures (NIFTY / BANKNIFTY), MCX futures.

Candle (bar i, closed): lower wick ≥ 2× body, upper wick ≤ 0.3× range, range > 0 (same shape for both; the trend decides
the name: after a fall = hammer, after a rise = hanging man).
Prior trend (before the candle):
  T1 EMA   – BUY: EMA20 < EMA50 and close of bar i-1 < EMA50 · SELL: EMA20 > EMA50 and close i-1 > EMA50
  T2 swing – BUY: the candle's low is the lowest low of the last 20 bars and close i-1 < close i-6 (5-bar fall)
             SELL: the candle's high is the highest high of the last 20 bars and close i-1 > close i-6
  T3 both
Entry:  E1 next candle's open · E2 confirmation: next candle(s) within 3 bars trade beyond the pattern candle's high (BUY) /
        low (SELL) → fill at that level (or the open if it gaps beyond); cancelled if the stop is hit first.
Stop:   BUY 0.05 ATR below the candle's low · SELL 0.05 ATR above the candle's high (owner's rule; small tick buffer).
Target: 1R, 2R, 3R · time exit after 20 candles · stop checked before target in a candle · gap through stop fills at the open ·
        exit before a contract switch · costs at 1× and 2×.
Options: V volume ≥ 1.5× 20-bar average on the pattern candle · S pattern range ≥ 1 ATR (meaningful candle).
Periods: train < Jul-24 ≤ valid < Jul-25 ≤ test. PASS = expectancy at 2× costs > 0 and PF ≥ 1.2 in each period, n ≥ 30/15/15.
"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import reversal as RV  # noqa: E402
from research.search import strategy_search as SS, stock_search as SR  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
TGT = (1.0, 2.0, 3.0)
MAXB = 20


def feats(f):
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    body = np.abs(c - o); rng = h - l
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    shape = (rng > 0) & (lw >= 2 * body) & (uw <= 0.3 * rng)
    e20, e50 = f["ema20"].values, I.ema(f["close"], 50).values
    c1 = np.r_[np.nan, c[:-1]]; c6 = np.r_[np.full(6, np.nan), c[:-6]]
    e50p = np.r_[np.nan, e50[:-1]]
    ll20 = pd.Series(l).rolling(20).min().values; hh20 = pd.Series(h).rolling(20).max().values
    T = {1: {"T1": (e20 < e50) & (c1 < e50p), "T2": (l <= ll20) & (c1 < c6)},
         -1: {"T1": (e20 > e50) & (c1 > e50p), "T2": (h >= hh20) & (c1 > c6)}}
    for s in (1, -1):
        T[s]["T3"] = T[s]["T1"] & T[s]["T2"]
    vx = f["volx"].values
    return shape, T, {"V": vx >= 1.5, "S": rng >= f["atr"].values}


def sim(f, sig, side, entry, tgt, cost):
    o, h, l, c, a, sw = (f[x].values for x in ("open", "high", "low", "close", "atr", "switch"))
    out, busy, n = [], -1, len(c)
    for i in np.flatnonzero(sig):
        if i < 210 or i <= busy or i >= n - 3 or sw[i] or not a[i] > 0:
            continue
        st = l[i] - 0.05 * a[i] if side > 0 else h[i] + 0.05 * a[i]
        if entry == "E1":
            j0 = i + 1
            if sw[j0]:
                continue
            e0 = o[j0]
        else:
            lvl = h[i] if side > 0 else l[i]
            j0 = None
            for j in range(i + 1, min(i + 4, n)):
                if sw[j]:
                    break
                if (side > 0 and o[j] > lvl) or (side < 0 and o[j] < lvl):
                    j0, e0 = j, o[j]; break
                if (l[j] <= st) if side > 0 else (h[j] >= st):
                    break
                if (h[j] > lvl) if side > 0 else (l[j] < lvl):
                    j0, e0 = j, lvl; break
            if j0 is None:
                continue
        R = side * (e0 - st)
        if not R > 0:
            continue
        tp = e0 + side * tgt * R
        px = None; j = j0
        while j < n:
            if j > j0 and sw[j]:
                px, j = c[j - 1], j - 1; break
            if j > j0 and side * (o[j] - st) <= 0:
                px = o[j]; break
            if (l[j] <= st) if side > 0 else (h[j] >= st):
                px = st; break
            if (h[j] >= tp) if side > 0 else (l[j] <= tp):
                px = tp if not (j > j0 and side * (o[j] - tp) > 0) else o[j]; break
            if j - j0 >= MAXB - 1:
                px = c[j]; break
            j += 1
        if px is None:
            break
        out.append((i, (side * (px - e0) - cost[i]) / R, (side * (px - e0) - 2 * cost[i]) / R, R / a[i], j - j0 + 1))
        busy = j
    return out


def one(job):
    kind, a, b = job
    try:
        d = RV.mcx_index_1h(a, b) if kind == "mi" else RV.stock_1h(a, b)
    except Exception as e:
        print("skip", job, e); return []
    if d is None:
        return []
    seg, f, cost, _cap = d
    shape, T, X = feats(f)
    rows = []
    for side in (1, -1):
        for tr in ("T1", "T2", "T3"):
            for opts in ((), ("V",), ("S",), ("V", "S")):
                sig = shape & T[side][tr]
                for k in opts:
                    sig = sig & X[k]
                if not sig.any():
                    continue
                for en in ("E1", "E2"):
                    for tg in TGT:
                        for (i, r1, r2, ratr, bars) in sim(f, sig, side, en, tg, cost):
                            rows.append((seg, a, "BUY hammer" if side > 0 else "SELL hanging man", tr, "+".join(opts) or "none",
                                         en, f"{tg:g}R", f["time"].iat[i], r1, r2, ratr, bars))
    return rows


def jobs():
    J = [("mi", n, ex) for ex, n in SS.NAMES]
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    return J + [("stk", n, int(l)) for n, l in zip(man["name"], man["lot"])]


def main():
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(one, jobs(), chunksize=1) for r in x]
    T = pd.DataFrame(rows, columns=["seg", "name", "setup", "trend", "opt", "entry", "target", "time", "r1", "r2", "risk_atr", "bars"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    tz = T["time"].dt.tz
    cut1, cut2 = pd.Timestamp("2024-07-01", tz=tz), pd.Timestamp("2025-07-01", tz=tz)
    T["split"] = np.where(T["time"] < cut1, "1-train", np.where(T["time"] < cut2, "2-valid", "3-test"))
    T.to_csv(OUT / "ham_trades.csv.gz", index=False)
    K = ["seg", "setup", "trend", "opt", "entry", "target"]
    g = T.groupby(K + ["split"])
    st = g.agg(n=("r1", "size"), win=("r1", lambda x: (x > 0).mean() * 100), exp2=("r2", "mean"),
               gw=("r1", lambda x: x[x > 0].sum()), gl=("r1", lambda x: -x[x <= 0].sum())).reset_index()
    st["pf"] = st["gw"] / st["gl"].replace(0, np.nan)
    W = st.pivot_table(index=K, columns="split", values=["n", "win", "exp2", "pf"])
    W.columns = [f"{bb[2:]}_{aa}" for aa, bb in W.columns]
    W = W.reset_index()
    nmin = dict(train=30, valid=15, test=15)
    W["pass"] = [all((r.get(f"{s}_n") or 0) >= nmin[s] and (r.get(f"{s}_exp2") or -1) > 0 and (r.get(f"{s}_pf") or 0) >= 1.2
                     for s in nmin) for r in W.to_dict("records")]
    P = T.groupby(K).agg(all_n=("r1", "size"), all_win=("r1", lambda x: (x > 0).mean() * 100), all_exp1=("r1", "mean"),
                         all_exp2=("r2", "mean"), gw=("r1", lambda x: x[x > 0].sum()), gl=("r1", lambda x: -x[x <= 0].sum()),
                         risk_atr=("risk_atr", "median"), bars=("bars", "mean")).reset_index()
    P["all_pf"] = P["gw"] / P["gl"].replace(0, np.nan)
    W = W.merge(P.drop(columns=["gw", "gl"]), on=K)
    W.to_csv(OUT / "ham_variants.csv", index=False)
    print("variants", len(W), "pass", int(W["pass"].sum()))


if __name__ == "__main__":
    main()
