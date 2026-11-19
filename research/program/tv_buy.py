"""TV-BUY-001 (19-Nov-2026, owner: "find from TradingView all script best BUY reversal setup and check"). BUY versions of the
most-used TradingView reversal / bottom scripts, written from their published logic, on the 181 F&O stock futures
(research data 2022-26, front month, never through a roll, 2x costs, next-open entry, 0.5-ATR chase limit, stop first –
sell_exits.run on mirrored prices = a BUY).
Bottom / oversold scripts (raw prices):
  CM_Williams_Vix_Fix (ChrisMoody) – VIX-fix spike ends + green candle · WaveTrend cross up below -53 (LazyBear, Market
  Cipher green dot) · Stoch RSI 3/3/14/14 cross up below 20 · Laguerre RSI (0.5) cross above 0.2 (Ehlers) · MFI(14) cross
  above 20 · Bollinger close back above the lower band (TV built-in BB strategy) · RSI bullish divergence (TV built-in
  Divergence, pivot 5) · Squeeze Momentum turns up below zero (LazyBear) · Hammer / Bullish engulfing / Morning star at a
  20-candle low · Heikin-Ashi first green after 3 red · CCI cross above -100 · Williams %R cross above -80
Trend-reversal scripts (the 14 scripts of tv_scripts.py, BUY side by mirroring): SuperTrend, UT Bot, HalfTrend, Chandelier,
  SSL, QQE MOD, MACD cross, EMA 20/50, ADX/DI, Squeeze release, SMC break of structure, S/R break with volume, ...
Filters: none · UT (stock's daily trend up) · A200 (above daily EMA200) · UT+A200 · B50 (> 50 % of F&O stocks in a daily
uptrend) · UT+B50. Exits SL x target: 2x1, 2x1.5, 2x2, 1.5x2, 2x3 ATR/R. Candles 1d / 4h / 2h. RANDOM BUY = benchmark.
PASS = R > 0 and above RANDOM in each of 2022-24 / 2024-25 / 2025-26 with >= 30 trades each.
python research/program/tv_buy.py -> results/tv_buy_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.sell_exits import run  # noqa: E402
from research.program.tv_scripts import signals as tv_sell, rma  # noqa: E402
from research.program.rev_ind import mirror  # noqa: E402

OUT = ROOT / "research/program/results"
EXITS = [(2.0, 1.0), (2.0, 1.5), (2.0, 2.0), (1.5, 2.0), (2.0, 3.0)]
BREADTH = None


def rsi(c, n):
    d = c.diff()
    return 100 - 100 / (1 + rma(d.clip(lower=0), n) / rma(-d.clip(upper=0), n).replace(0, np.nan))


def bottoms(C):
    o, h, l, c, v = (C[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
    S = {}
    hc = c.rolling(22).max(); wvf = (hc - l) / hc * 100
    ubw = wvf.rolling(20).mean() + 2 * wvf.rolling(20).std(); rh = wvf.rolling(50).max() * 0.85
    spike = (wvf >= ubw) | (wvf >= rh)
    S["CM Williams Vix Fix: spike ends + green candle"] = spike.shift(1).fillna(False) & ~spike & (c > o)
    ap = (h + l + c) / 3; esa = ap.ewm(span=10, adjust=False).mean(); dd = (ap - esa).abs().ewm(span=10, adjust=False).mean()
    wt1 = ((ap - esa) / (0.015 * dd)).ewm(span=21, adjust=False).mean(); wt2 = wt1.rolling(4).mean()
    S["WaveTrend cross up below -53 (Market Cipher green dot)"] = (wt1 > wt2) & (wt1.shift(1) <= wt2.shift(1)) & (wt1 < -53)
    r14 = rsi(c, 14); sr = (r14 - r14.rolling(14).min()) / (r14.rolling(14).max() - r14.rolling(14).min()).replace(0, np.nan) * 100
    k = sr.rolling(3).mean(); d = k.rolling(3).mean()
    S["Stoch RSI cross up below 20"] = (k > d) & (k.shift(1) <= d.shift(1)) & (k < 20)
    g = 0.5; C_ = c.values; L0 = np.zeros(len(C_)); L1 = np.zeros(len(C_)); L2 = np.zeros(len(C_)); L3 = np.zeros(len(C_))
    for i in range(len(C_)):
        p = (L0[i - 1], L1[i - 1], L2[i - 1], L3[i - 1]) if i else (C_[0],) * 4
        L0[i] = (1 - g) * C_[i] + g * p[0]; L1[i] = -g * L0[i] + p[0] + g * p[1]
        L2[i] = -g * L1[i] + p[1] + g * p[2]; L3[i] = -g * L2[i] + p[2] + g * p[3]
    cu = np.maximum(L0 - L1, 0) + np.maximum(L1 - L2, 0) + np.maximum(L2 - L3, 0)
    cd = np.maximum(L1 - L0, 0) + np.maximum(L2 - L1, 0) + np.maximum(L3 - L2, 0)
    lrsi = pd.Series(np.where(cu + cd > 0, cu / np.where(cu + cd > 0, cu + cd, 1), 0), index=c.index)
    S["Laguerre RSI cross above 0.2 (Ehlers)"] = (lrsi > 0.2) & (lrsi.shift(1) <= 0.2)
    tp = (h + l + c) / 3; mf = tp * v
    pos = mf.where(tp > tp.shift(1), 0).rolling(14).sum(); neg = mf.where(tp < tp.shift(1), 0).rolling(14).sum()
    mfi = 100 - 100 / (1 + pos / neg.replace(0, np.nan))
    S["MFI(14) cross above 20"] = (mfi > 20) & (mfi.shift(1) <= 20)
    bm, bs = c.rolling(20).mean(), c.rolling(20).std(); lb = bm - 2 * bs
    S["Bollinger: close back above lower band (TV BB strategy)"] = (c > lb) & (c.shift(1) <= lb.shift(1))
    n = 5; Lv, R = l.values, r14.values; out = np.zeros(len(Lv), bool); last = None
    for i in range(2 * n, len(Lv)):
        j = i - n
        if Lv[j] == Lv[j - n:j + n + 1].min() and np.isfinite(R[j]):
            if last is not None and Lv[j] < Lv[last] and R[j] > R[last] and R[j] < 40:
                out[i] = True
            last = j
    S["RSI bullish divergence (TV Divergence, pivot 5)"] = pd.Series(out, index=c.index)
    tr = rma(pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1), 20)
    mid = (h.rolling(20).max() + l.rolling(20).min()) / 2; x = c - (mid + c.rolling(20).mean()) / 2
    t_ = np.arange(20); tm = t_.mean()
    mom = x.rolling(20).apply(lambda y: ((t_ - tm) * (y - y.mean())).sum() / ((t_ - tm) ** 2).sum() * (19 - tm) + y.mean(), raw=True)
    S["Squeeze Momentum turns up below zero (LazyBear)"] = (mom < 0) & (mom > mom.shift(1)) & (mom.shift(1) <= mom.shift(2))
    rg = (h - l).replace(0, np.nan); body = (c - o).abs(); lw = np.minimum(o, c) - l; uw = h - np.maximum(o, c)
    low20 = l <= l.shift(1).rolling(20).min()
    S["Hammer at a 20-candle low"] = low20 & (lw >= 2 * body) & (uw <= 0.3 * rg) & (body > 0)
    S["Bullish engulfing at a 20-candle low"] = (l.rolling(2).min() <= l.shift(2).rolling(20).min()) & (c.shift(1) < o.shift(1)) & (c > o) & (c >= o.shift(1)) & (o <= c.shift(1))
    S["Morning star at a 20-candle low"] = (l.shift(1) <= l.shift(2).rolling(20).min()) & (c.shift(2) < o.shift(2)) & ((c.shift(1) - o.shift(1)).abs() <= 0.3 * (h.shift(1) - l.shift(1))) & (c > o) & (c > (o.shift(2) + c.shift(2)) / 2)
    hac = (o + h + l + c) / 4; hao = np.zeros(len(c)); O_, HC = o.values, hac.values
    hao[0] = (O_[0] + c.values[0]) / 2
    for i in range(1, len(c)):
        hao[i] = (hao[i - 1] + HC[i - 1]) / 2
    green = pd.Series(HC > hao, index=c.index)
    S["Heikin-Ashi first green after 3 red"] = green & ~green.shift(1).fillna(True) & ~green.shift(2).fillna(True) & ~green.shift(3).fillna(True)
    cci = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).apply(lambda z: np.abs(z - z.mean()).mean(), raw=True))
    S["CCI(20) cross above -100"] = (cci > -100) & (cci.shift(1) <= -100)
    hh, ll = h.rolling(14).max(), l.rolling(14).min(); wpr = -100 * (hh - c) / (hh - ll).replace(0, np.nan)
    S["Williams %R cross above -80"] = (wpr > -80) & (wpr.shift(1) <= -80)
    return {k_: x.fillna(False).astype(bool) for k_, x in S.items()}


def trend_only(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    for s, f, od, c in fr:
        if s == "STOCKS 1d":
            return SA.daily_trend(f.reset_index(drop=True)).rename(job[1])
    return None


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
    acc = {}
    rng = np.random.default_rng(sum(map(ord, job[1])) + 7)
    for tf, (C0, cost) in frames.items():
        if len(C0) < 300:
            continue
        cost = np.asarray(cost, float)
        if len(cost) != len(C0):
            cost = np.interp(np.arange(len(C0)), np.linspace(0, len(C0) - 1, len(cost)), cost)
        M = mirror(C0)
        f = H.features(M); f["switch"] = C0["switch"].values if "switch" in C0 else np.zeros(len(M), bool)
        o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values.astype(np.bool_)
        tt = pd.to_datetime(C0["time"]); day = tt.dt.normalize()
        ut = (day.map(dtr) > 0).values; ab = (day.map(a200) > 0).values
        b50 = (day.map(BREADTH) > 0.5).values if BREADTH is not None else np.zeros(len(tt), bool)
        split = np.where(tt.values < SV.P1, 0, np.where(tt.values < SV.P2, 1, 2))
        S = bottoms(C0)
        for k_, s in tv_sell(M, tf != "1d").items():
            if k_ == "RANDOM":
                continue
            S["TV-trend BUY: " + k_.replace(" down", " up").replace(" sell", " buy").replace("turns red", "turns green")] = s.values if hasattr(s, "values") else s
        S["RANDOM"] = rng.random(len(tt)) < 0.03
        maxh = 10 if tf == "1d" else SV.MAXH.get(tf, 40)
        for nm, s in S.items():
            s = np.asarray(s, bool)
            for flt, m in (("none", s), ("UT", s & ut), ("A200", s & ab), ("UT+A200", s & ut & ab), ("B50", s & b50), ("UT+B50", s & ut & b50)):
                if m.sum() < 1:
                    continue
                for k, r in EXITS:
                    for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, m, k, r, maxh, cost, 0.0, 0.0, 0.0, H.CHASE):
                        a = acc.setdefault((nm, tf, flt, k, r, int(split[i])), [0, 0.0, 0, 0]); a[0] += 1; a[1] += rr; a[2] += rr > 0; a[3] += why == 1
    return acc


def main():
    global BREADTH
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        tr = [x for x in p.imap_unordered(trend_only, J, chunksize=4) if x is not None]
    B = pd.concat(tr, axis=1); BREADTH = (B > 0).sum(axis=1) / B.notna().sum(axis=1)
    acc = {}
    with Pool(2) as p:
        for a in p.imap_unordered(one, J, chunksize=2):
            for k_, v in (a or {}).items():
                x = acc.setdefault(k_, [0, 0.0, 0, 0])
                for q in range(4):
                    x[q] += v[q]
    A = pd.DataFrame([(*k_, *v) for k_, v in acc.items()], columns=["sig", "tf", "flt", "k", "r", "split", "n", "sumR", "wins", "sl"])
    W = A.pivot_table(index=["sig", "tf", "flt", "k", "r"], columns="split", values=["n", "sumR", "wins", "sl"], aggfunc="sum").fillna(0)
    rows = []
    for key, x in W.iterrows():
        n = [x[("n", s)] for s in (0, 1, 2)]; sR = [x[("sumR", s)] for s in (0, 1, 2)]; w = [x[("wins", s)] for s in (0, 1, 2)]
        N = sum(n)
        if N < 30:
            continue
        rows.append(dict(zip(["sig", "tf", "flt", "k", "r"], key), n=int(N), win=round(100 * sum(w) / N, 1),
                         sl=round(100 * sum(x[("sl", s)] for s in (0, 1, 2)) / N, 1), R=round(sum(sR) / N, 3),
                         **{f"p{s+1}_n": int(n[s]) for s in range(3)}, **{f"p{s+1}_win": round(100 * w[s] / n[s], 1) if n[s] else None for s in range(3)},
                         **{f"p{s+1}_R": round(sR[s] / n[s], 3) if n[s] else None for s in range(3)}))
    L = pd.DataFrame(rows)
    base = L[L.sig == "RANDOM"].set_index(["tf", "flt", "k", "r"])
    for s in (1, 2, 3):
        L[f"p{s}_rand"] = [base[f"p{s}_R"].get(kk, np.nan) for kk in zip(L.tf, L.flt, L.k, L.r)]
    L["pass"] = np.all([(L[f"p{s}_R"] > 0) & (L[f"p{s}_R"] > L[f"p{s}_rand"]) & (L[f"p{s}_n"] >= 30) for s in (1, 2, 3)], axis=0) & (L.sig != "RANDOM")
    L["minR"] = L[["p1_R", "p2_R", "p3_R"]].min(axis=1)
    L.to_csv(OUT / "tv_buy_summary.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200); pd.set_option("display.max_colwidth", 60)
    c = ["sig", "tf", "flt", "k", "r", "n", "win", "sl", "R", "p1_R", "p2_R", "p3_R", "p1_rand", "p2_rand", "p3_rand", "pass"]
    print("PASSED:", int(L["pass"].sum()), "of", len(L))
    print(L[L["pass"]].sort_values("R", ascending=False)[c].head(40).to_string(index=False))
    print(L[(L.sig != "RANDOM")].sort_values("minR", ascending=False).groupby("sig").head(1)[c].head(40).to_string(index=False))


if __name__ == "__main__":
    main()
