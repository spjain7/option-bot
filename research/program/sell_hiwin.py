"""SELL-HIWIN-001 (19-Nov-2026, owner: "we need a 70/80 % winning strategy, specially for the SELL side").
Stock futures, 181 F&O stocks, daily candles 2022-26 (research data, front-month, roll-aware costs x2). SELL only.
Signal at the daily close, entry next open, stop checked FIRST when stop and target fall in the same candle.
ENTRIES
  RSI2_OB     RSI(2) > 90 while close < EMA200 (fade a bounce in a downtrend)
  BB_UP       close above the upper Bollinger band (20, 2) while close < EMA200
  GAP_FADE    opened >= 1 % above yesterday's close, closed in the bottom 25 % of the day's range, red candle
  BULL_TRAP   high above the prior 20-day high but close back below it, red candle (failed breakout)
  EMA20_REJ   high touched EMA20, close below it, EMA20 < EMA50 < EMA200 (pullback sell in a downtrend)
  BEAR_ENG    bearish engulfing candle, close < EMA50
  SHOOT_STAR  upper wick >= 2x body and >= 60 % of the range, close < EMA50
  LH_BREAK    NR7 day before, close below the prior day's low, close < EMA50
FILTERS  none / MKT (>= 55 % of the 181 stocks below their EMA50 the previous session) / SB (signal day short build-up:
         price down + OI up) / VOL (volume >= 1.5x 20-day) / MKT+SB
EXITS    target T x ATR in {0.25, 0.5, 0.75, 1.0} · stop S x ATR in {1, 1.5, 2, 3} · max hold H in {1, 3, 5, 10} days
PASS     win >= 70 % AND average R > 0 after 2x costs in ALL THREE periods (p1 / p2 / p3 as SEARCH-V2), >= 50 calls each, AND
         better average R than RANDOM SELL entries with the same exit in every period (a tiny target with a wide stop wins
         often by geometry alone – that must not count).
python research/program/sell_hiwin.py -> results/sell_hiwin_summary.csv"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX, search_v2 as SV  # noqa: E402

OUT = ROOT / "research/program/results"
TG, SLS, HD = (0.25, 0.5, 0.75, 1.0), (1.0, 1.5, 2.0, 3.0), (1, 3, 5, 10)
EXITS = list(itertools.product(TG, SLS, HD))
FAMS = ["RSI2_OB", "BB_UP", "GAP_FADE", "BULL_TRAP", "EMA20_REJ", "BEAR_ENG", "SHOOT_STAR", "LH_BREAK", "RANDOM"]


def ema(x, n):
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(c, n):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    seg = {s: (f.reset_index(drop=True), od, np.asarray(c, float)) for s, f, od, c in fr}
    if "STOCKS 1d" not in seg:
        return None
    d, od, cost = seg["STOCKS 1d"]
    if len(d) < 260:
        return None
    o, h, l, c, v = (d[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
    pc = c.shift(1)
    atr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1).ewm(alpha=1 / 14, adjust=False).mean()
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    m, sd = c.rolling(20).mean(), c.rolling(20).std()
    rg = (h - l).replace(0, np.nan); body = (c - o).abs()
    pos = (c - l) / rg; va = v.rolling(20).mean().shift(1)
    nr7 = ((h - l) <= (h - l).rolling(7).min()).shift(1).fillna(False).astype(bool)
    hi20 = h.shift(1).rolling(20).max()
    rng = np.random.default_rng(abs(hash(job[1])) % 2**32)
    E = {"RSI2_OB": (rsi(c, 2) > 90) & (c < e200), "BB_UP": (c > m + 2 * sd) & (c < e200),
         "GAP_FADE": (o >= pc * 1.01) & (pos <= 0.25) & (c < o), "BULL_TRAP": (h > hi20) & (c < hi20) & (c < o),
         "EMA20_REJ": (h >= e20) & (c < e20) & (e20 < e50) & (e50 < e200),
         "BEAR_ENG": (c < o) & (o >= c.shift(1)) & (c <= o.shift(1)) & (c.shift(1) > o.shift(1)) & (c < e50),
         "SHOOT_STAR": ((h - np.maximum(o, c)) >= 2 * body) & ((h - np.maximum(o, c)) >= 0.6 * rg) & (c < e50),
         "LH_BREAK": nr7 & (c < l.shift(1)) & (c < e50), "RANDOM": pd.Series(rng.random(len(c)) < 0.03)}
    sw = d["switch"].values if "switch" in d else np.zeros(len(d), bool)
    O, Hh, L, C, A = o.values, h.values, l.values, c.values, atr.values
    t = pd.to_datetime(d["time"]).dt.normalize().values
    volok = (v > 1.5 * va).values; sb = (np.asarray(od) == -1)
    rows = []
    n = len(C)
    for fam, s in E.items():
        idx = np.flatnonzero(s.fillna(False).values)
        for i in idx:
            if i < 210 or i + 1 >= n or not A[i] > 0:
                continue
            e = O[i + 1]
            if not e > 0:
                continue
            # roll: stop the path at a contract switch (never hold through a roll)
            end = min(n - 1, i + 10)
            for j in range(i + 2, end + 1):
                if sw[j]:
                    end = j - 1; break
            res = []
            for T, S, Hd in EXITS:
                tp, st = e - T * A[i], e + S * A[i]; out = None
                last = min(end, i + Hd)
                for j in range(i + 1, last + 1):
                    oj = O[j] if j > i + 1 else e
                    if oj >= st:
                        out = oj; break
                    if oj <= tp and j > i + 1:
                        out = oj; break
                    if Hh[j] >= st:
                        out = st; break
                    if L[j] <= tp:
                        out = tp; break
                if out is None:
                    out = C[last]
                res.append((e - out - 2 * cost[i]) / (S * A[i]))
            rows.append((fam, job[1], t[i], bool(volok[i]), bool(sb[i]), *res))
    return rows, pd.Series((C < e50.values), index=t, name=job[1])


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        parts = [x for x in p.imap_unordered(one, J, chunksize=2) if x]
    cols = ["fam", "name", "day", "vol", "sb"] + [f"r{k}" for k in range(len(EXITS))]
    T = pd.DataFrame([r for rows, _ in parts for r in rows], columns=cols)
    B = pd.concat([b for _, b in parts], axis=1).sort_index()
    br = B.mean(axis=1).shift(1); T["mkt"] = T.day.map(br >= 0.55).fillna(False).astype(bool)
    tv = T.day.values.astype("datetime64[ns]")
    T["split"] = np.where(tv < SV.P1, "p1", np.where(tv < SV.P2, "p2", "p3"))
    print("signals", T.groupby("fam").size().to_dict(), flush=True)
    FIL = {"none": None, "MKT": "mkt", "SB": "sb", "VOL": "vol", "MKT+SB": ("mkt", "sb")}
    rand = {}
    R0 = T[T.fam == "RANDOM"]
    for k in range(len(EXITS)):
        rand[k] = {sp: R0[R0.split == sp][f"r{k}"].mean() for sp in ("p1", "p2", "p3")}
    out = []
    for fam in FAMS[:-1]:
        G0 = T[T.fam == fam]
        for fn, fl in FIL.items():
            G = G0
            if fl:
                for x in (fl if isinstance(fl, tuple) else (fl,)):
                    G = G[G[x]]
            if len(G) < 150:
                continue
            for k, (Tt, S, Hd) in enumerate(EXITS):
                r = G[f"r{k}"]
                row = dict(fam=fam, filt=fn, target_atr=Tt, stop_atr=S, hold=Hd, n=len(r), win=round(100 * (r > 0).mean(), 1), R=round(r.mean(), 3),
                           pct_per_call=None)
                ok = True
                for sp in ("p1", "p2", "p3"):
                    x = r[G.split == sp]
                    row[f"{sp}_n"] = len(x); row[f"{sp}_win"] = round(100 * (x > 0).mean(), 1) if len(x) else None
                    row[f"{sp}_R"] = round(x.mean(), 3) if len(x) else None; row[f"{sp}_rand"] = round(rand[k][sp], 3)
                    ok &= len(x) >= 50 and (x > 0).mean() >= 0.70 and x.mean() > 0 and x.mean() > rand[k][sp]
                row["pass"] = bool(ok)
                row["win70_all"] = all((row[f"{sp}_win"] or 0) >= 70 for sp in ("p1", "p2", "p3"))
                out.append(row)
    L = pd.DataFrame(out); L.to_csv(OUT / "sell_hiwin_summary.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 120)
    c = ["fam", "filt", "target_atr", "stop_atr", "hold", "n", "win", "R", "p1_win", "p2_win", "p3_win", "p1_R", "p2_R", "p3_R", "p1_rand", "p2_rand", "p3_rand"]
    print(f"combos {len(L)} · win >= 70 % in all 3 periods {int(L.win70_all.sum())} · PASS (also profitable + beats random) {int(L['pass'].sum())}")
    W = L[L.win70_all].copy(); W["minR"] = W[["p1_R", "p2_R", "p3_R"]].min(axis=1)
    print("\nwin >= 70 % in all periods, best worst-period R:"); print(W.sort_values("minR", ascending=False).head(25)[c].to_string(index=False))
    if L["pass"].any():
        print("\nPASS:"); print(L[L["pass"]].sort_values("R", ascending=False).head(30)[c].to_string(index=False))
    P = L.copy(); P["minR"] = P[["p1_R", "p2_R", "p3_R"]].min(axis=1); P["edge"] = P.minR - P[["p1_rand", "p2_rand", "p3_rand"]].max(axis=1)
    print("\nbest SELL combos by worst-period R (any win rate):"); print(P.sort_values("minR", ascending=False).head(15)[c].to_string(index=False))


if __name__ == "__main__":
    main()
