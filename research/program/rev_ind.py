"""REV-IND-001 (19-Nov-2026, owner: "find any top / bottom or reversal indicator"). Classic top / bottom tools on the 181 F&O
stock futures (research data 2022-26, front month, never through a roll, 2x costs, next-open entry, 0.5-ATR chase limit,
stop first – sell_exits.run). Each tool is written for TOPS (-> SELL); BOTTOMS (-> BUY) use the same code on the mirrored
price series (open/high/low/close negated, high <-> low), so both sides follow identical rules.
  TD9         DeMark setup: 9 closes in a row above the close 4 bars earlier (after a price flip)
  TD9P        TD9 "perfected": high of bar 8 or 9 >= the highs of bars 6 and 7
  TD13        DeMark countdown: after a TD9, 13 closes >= the high 2 bars earlier (paused, not reset; cancelled by an opposite 9)
  RSI_DIV     bearish RSI(14) divergence: pivot high (5/5) above the previous pivot high, RSI lower and > 60; signal when the
              pivot is confirmed (5 bars later, no look-ahead)
  MACD_DIV    the same with the MACD(12,26,9) histogram
  STOCH80     Stochastic (14,3,3) %K crosses below %D above 80
  CCI200      CCI(20) back below +100 after being above +200 within 5 bars
  FISHER      Fisher transform (10) crosses below its signal above +2
  BB_REJECT   previous close above the upper Bollinger band (20, 2), this candle red and back inside
  WPR20       Williams %R (14) crosses below -20
  VOL_CLIMAX  volume >= 3x its 20-candle average, 20-candle high, upper wick >= 50 % of the range
  SFP         swing failure: high above the prior 20-candle high, close back below it, red
  BAR3        3-bar reversal: middle candle the highest high, third closes below the middle candle's low
CONTEXT  none · UP (a real top: close > EMA50 + 1 ATR at the signal) · DT (the stock's daily trend already down - a top inside
         a downtrend; mirrored for BUY)
EXITS    stop 2 ATR x target 1 / 1.5 / 2 / 3R, and stop 1.5 ATR x 2R. Candles 1d / 4h / 2h / 1h.
PASS     R > 0 and > RANDOM (same side, context, exit) in p1, p2 and p3, >= 40 trades each.
python research/program/rev_ind.py -> results/rev_ind_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.sell_exits import run  # noqa: E402

OUT = ROOT / "research/program/results"
EXITS = [(2.0, 1.0), (2.0, 1.5), (2.0, 2.0), (2.0, 3.0), (1.5, 2.0)]


def rma(x, n):
    return x.ewm(alpha=1 / n, adjust=False).mean()


def rsi(c, n=14):
    d = c.diff()
    return 100 - 100 / (1 + rma(d.clip(lower=0), n) / rma(-d.clip(upper=0), n).replace(0, np.nan))


def td(c, h):
    C, Hh = c.values, h.values; n = len(C)
    up = np.zeros(n, int); dn = np.zeros(n, int)
    for i in range(4, n):
        up[i] = up[i - 1] + 1 if C[i] > C[i - 4] else 0
        dn[i] = dn[i - 1] + 1 if C[i] < C[i - 4] else 0
    s9 = np.zeros(n, bool); s9p = np.zeros(n, bool); s13 = np.zeros(n, bool)
    cd = -1
    for i in range(n):
        if up[i] == 9:
            s9[i] = True
            if max(Hh[i], Hh[i - 1]) >= max(Hh[i - 3], Hh[i - 2]):
                s9p[i] = True
            cd = 0                                                    # (re)start the countdown
        if dn[i] == 9:
            cd = -1                                                   # opposite setup cancels
        if cd >= 0 and i >= 2 and C[i] >= Hh[i - 2] and up[i] != 9:
            cd += 1
            if cd == 13:
                s13[i] = True; cd = -1
    idx = c.index
    return pd.Series(s9, idx), pd.Series(s9p, idx), pd.Series(s13, idx)


def pivot_div(h, osc, n=5, need=60.0):
    Hh, O = h.values, osc.values; L = len(Hh); out = np.zeros(L, bool)
    last_p = None
    for i in range(2 * n, L):
        j = i - n
        win = Hh[j - n:j + n + 1]
        if Hh[j] == win.max() and np.isfinite(O[j]):
            if last_p is not None and Hh[j] > Hh[last_p] and O[j] < O[last_p] and (need is None or O[j] > need):
                out[i] = True                                         # known only now, n candles after the pivot
            last_p = j
    return pd.Series(out, index=h.index)


def tops(C):
    o, h, l, c, v = (C[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
    S = {}
    s9, s9p, s13 = td(c, h); S["TD9"] = s9; S["TD9P"] = s9p; S["TD13"] = s13
    r = rsi(c, 14); S["RSI_DIV"] = pivot_div(h, r, 5, 60.0)
    e12, e26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean(); m = e12 - e26; hist = m - m.ewm(span=9, adjust=False).mean()
    S["MACD_DIV"] = pivot_div(h, hist, 5, 0.0)
    ll, hh = l.rolling(14).min(), h.rolling(14).max()
    k = (100 * (c - ll) / (hh - ll).replace(0, np.nan)).rolling(3).mean(); d = k.rolling(3).mean()
    S["STOCH80"] = (k < d) & (k.shift(1) >= d.shift(1)) & (k.shift(1) > 80)
    tp = (h + l + c) / 3; cci = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True))
    S["CCI200"] = (cci < 100) & (cci.shift(1) >= 100) & (cci.rolling(5).max() > 200)
    hl2 = (h + l) / 2; mx, mn = hl2.rolling(10).max(), hl2.rolling(10).min()
    val = (0.66 * ((hl2 - mn) / (mx - mn).replace(0, np.nan) - 0.5)).fillna(0).values; V = np.zeros(len(val)); F = np.zeros(len(val))
    for i in range(1, len(val)):
        V[i] = min(max(val[i] + 0.67 * V[i - 1], -0.999), 0.999); F[i] = 0.5 * np.log((1 + V[i]) / (1 - V[i])) + 0.5 * F[i - 1]
    fi = pd.Series(F, index=c.index); fs = fi.shift(1)
    S["FISHER"] = (fi < fs) & (fi.shift(1) >= fs.shift(1)) & (fi.shift(1) > 2)
    ub = c.rolling(20).mean() + 2 * c.rolling(20).std()
    S["BB_REJECT"] = (c.shift(1) > ub.shift(1)) & (c < ub) & (c < o)
    wpr = -100 * (hh - c) / (hh - ll).replace(0, np.nan)
    S["WPR20"] = (wpr < -20) & (wpr.shift(1) >= -20)
    rg = (h - l).replace(0, np.nan)
    S["VOL_CLIMAX"] = (v >= 3 * v.rolling(20).mean().shift(1)) & (h >= h.rolling(20).max()) & ((h - np.maximum(o, c)) >= 0.5 * rg)
    hi20 = h.shift(1).rolling(20).max()
    S["SFP"] = (h > hi20) & (c < hi20) & (c < o)
    S["BAR3"] = (h.shift(1) > h.shift(2)) & (h.shift(1) > h) & (c < l.shift(1))
    return {k_: x.fillna(False).astype(bool) for k_, x in S.items()}


def mirror(C):
    M = C.copy()
    M["open"], M["close"] = -C["open"], -C["close"]; M["high"], M["low"] = -C["low"], -C["high"]
    return M


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
    frames = {"1d": (fd, cd), "1h": (f1, c1)}
    for hrs, tf in ((2, "2h"), (4, "4h")):
        C, first = anchored(f1, hrs); frames[tf] = (C, c1[first[:len(C)]])
    rng = np.random.default_rng(sum(map(ord, job[1])))
    rows = []
    for tf, (C0, cost) in frames.items():
        if len(C0) < 300:
            continue
        cost = np.asarray(cost, float)
        if len(cost) != len(C0):
            cost = np.interp(np.arange(len(C0)), np.linspace(0, len(C0) - 1, len(cost)), cost)
        dser = pd.to_datetime(C0["time"]).dt.normalize().map(dtr).values
        t = pd.to_datetime(C0["time"]).values; split = np.where(t < SV.P1, 0, np.where(t < SV.P2, 1, 2))
        maxh = 10 if tf == "1d" else SV.MAXH.get(tf, 40)
        for side, C in (("SELL", C0), ("BUY", mirror(C0))):
            f = H.features(C); f["switch"] = C0["switch"].values if "switch" in C0 else np.zeros(len(C), bool)
            o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
            sw = f["switch"].values.astype(np.bool_)
            e50 = pd.Series(c).ewm(span=50, adjust=False).mean().values
            up = c > e50 + at                                        # extended up (mirrored: extended down)
            dt = (dser < 0) if side == "SELL" else (dser > 0)
            S = tops(C); S["RANDOM"] = pd.Series(rng.random(len(c)) < 0.03)
            for nm, s in S.items():
                s = s.values
                for ctx, m in (("none", s), ("UP", s & up), ("DT", s & dt)):
                    if m.sum() < 2:
                        continue
                    for k, r in EXITS:
                        for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, m, k, r, maxh, cost, 0.0, 0.0, 0.0, H.CHASE):
                            rows.append((tf, side, nm, ctx, k, r, int(split[i]), rr))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    acc = {}
    with Pool(2) as p:
        for rows in p.imap_unordered(one, J, chunksize=2):
            for tf, sd, nm, ctx, k, r, sp, rr in rows or []:
                a = acc.setdefault((tf, sd, nm, ctx, k, r, sp), [0, 0.0, 0]); a[0] += 1; a[1] += rr; a[2] += rr > 0
    A = pd.DataFrame([(*k_, *v) for k_, v in acc.items()], columns=["tf", "side", "ind", "ctx", "k", "r", "split", "n", "sumR", "wins"])
    W = A.pivot_table(index=["tf", "side", "ind", "ctx", "k", "r"], columns="split", values=["n", "sumR", "wins"], aggfunc="sum").fillna(0)
    rows = []
    for key, x in W.iterrows():
        n = [x[("n", s)] for s in (0, 1, 2)]; sR = [x[("sumR", s)] for s in (0, 1, 2)]; w = [x[("wins", s)] for s in (0, 1, 2)]
        N = sum(n)
        if N < 60:
            continue
        rows.append(dict(zip(["tf", "side", "ind", "ctx", "k", "r"], key), n=int(N), win=round(100 * sum(w) / N, 1), R=round(sum(sR) / N, 3),
                         **{f"p{s+1}_n": int(n[s]) for s in range(3)}, **{f"p{s+1}_win": round(100 * w[s] / n[s], 1) if n[s] else None for s in range(3)},
                         **{f"p{s+1}_R": round(sR[s] / n[s], 3) if n[s] else None for s in range(3)}))
    L = pd.DataFrame(rows)
    base = L[L.ind == "RANDOM"].set_index(["tf", "side", "ctx", "k", "r"])
    for s in (1, 2, 3):
        L[f"p{s}_rand"] = [base[f"p{s}_R"].get(kk, np.nan) for kk in zip(L.tf, L.side, L.ctx, L.k, L.r)]
    L["pass"] = np.all([(L[f"p{s}_n"] >= 40) & (L[f"p{s}_R"] > 0) & (L[f"p{s}_R"] > L[f"p{s}_rand"]) for s in (1, 2, 3)], axis=0) & (L.ind != "RANDOM")
    L["minR"] = L[["p1_R", "p2_R", "p3_R"]].min(axis=1); L["minwin"] = L[["p1_win", "p2_win", "p3_win"]].min(axis=1)
    L.to_csv(OUT / "rev_ind_summary.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200)
    c = ["tf", "side", "ind", "ctx", "k", "r", "n", "win", "R", "p1_win", "p2_win", "p3_win", "p1_R", "p2_R", "p3_R", "p1_rand", "p2_rand", "p3_rand"]
    print(f"combos {len(L)} · PASS {int(L['pass'].sum())} (SELL {int((L['pass'] & (L.side == 'SELL')).sum())}, BUY {int((L['pass'] & (L.side == 'BUY')).sum())})")
    print(L[L["pass"]].sort_values("minR", ascending=False).head(40)[c].to_string(index=False))
    print("\nhighest worst-period win among passes:"); print(L[L["pass"]].sort_values("minwin", ascending=False).head(10)[c].to_string(index=False))
    print("\nbest per indicator & side (by worst-period R):")
    print(L[L.ind != "RANDOM"].sort_values("minR", ascending=False).groupby(["ind", "side"]).head(1)[c + ["pass"]].to_string(index=False))


if __name__ == "__main__":
    main()
