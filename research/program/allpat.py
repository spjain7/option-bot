"""ALLPAT-001 (1-Nov-2026, owner: "check how much this successful" – the 'Price Action RoadMap' list of 20 candlestick patterns).
Every pattern on that chart, DAILY candles, real futures data: stocks + MCX + index (Angel 2022-26) and NSE index 2011-26.
Context: bullish patterns only after a downtrend (EMA20 < EMA50 and previous close < EMA50), bearish only after an uptrend.
Entry = DCP-001 E2 (the textbook way): break of the last pattern candle's high (BUY) / low (SELL) within 3 days.
Stop 0.05 ATR beyond the pattern's extreme (all pattern candles). Target 1R and 2R; exit after 20 days. Costs 1x (r1) and 2x (r2).
'Success' = target reached before the stop.   python research/program/allpat.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX, daily_candles as DC  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"


def sh(x, k):
    return np.r_[np.full(k, np.nan), x[:-k]]


def patterns(f):
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    a = I.atr(f, 14).values
    body, rng = np.abs(c - o), h - l
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    g, r = c > o, c < o
    long_ = body >= 0.5 * sh(a, 1)
    small = body <= 0.3 * rng
    doji = (rng > 0) & (body <= 0.1 * rng)
    O1, H1, L1, C1, B1, G1, R1, LG1 = sh(o, 1), sh(h, 1), sh(l, 1), sh(c, 1), sh(body, 1), sh(g, 1) == 1, sh(r, 1) == 1, sh(long_, 1) == 1
    O2, H2, L2, C2, B2, G2, R2, LG2 = sh(o, 2), sh(h, 2), sh(l, 2), sh(c, 2), sh(body, 2), sh(g, 2) == 1, sh(r, 2) == 1, sh(long_, 2) == 1
    D1, S1 = sh(doji, 1) == 1, sh(body, 1) <= 0.3 * B2
    lo2, hi2 = np.fmin(l, L1), np.fmax(h, H1)
    lo3, hi3 = np.fmin(lo2, L2), np.fmax(hi2, H2)
    bull_eng = R1 & g & (o <= C1) & (c >= O1)
    bear_eng = G1 & r & (o >= C1) & (c <= O1)
    P = {
        # BUY (bullish)  -> (shape, stop ref = pattern low, trigger = last candle high)
        ("Hammer", 1): ((rng > 0) & (lw >= 2 * body) & (uw <= 0.3 * rng), l, h),
        ("Bullish Engulfing", 1): (bull_eng, lo2, h),
        ("Morning Star", 1): (R2 & LG2 & S1 & g & (c >= (O2 + C2) / 2), lo3, h),
        ("Morning Doji Star", 1): (R2 & LG2 & D1 & g & (c >= (O2 + C2) / 2), lo3, h),
        ("Three Inside Up", 1): (R2 & LG2 & G1 & (O1 >= C2) & (C1 <= O2) & (c > O2), lo3, h),
        ("Three Outside Up", 1): ((sh(bull_eng, 1) == 1) & g & (c > C1), lo3, h),
        ("Piercing Line", 1): (R1 & LG1 & g & (o < C1) & (c > (O1 + C1) / 2) & (c < O1), lo2, h),
        ("Dragonfly Doji", 1): (doji & (uw <= 0.1 * rng) & (lw >= 0.7 * rng), l, h),
        ("Inverted Hammer", 1): ((rng > 0) & (uw >= 2 * body) & (lw <= 0.3 * rng), l, h),
        ("Tweezer Bottom", 1): (R1 & g & (np.abs(l - L1) <= 0.05 * sh(a, 1)), lo2, h),
        ("Three White Soldiers", 1): (g & G1 & G2 & (c > C1) & (C1 > C2) & (o > O1) & (o <= C1) & (O1 > O2) & (O1 <= C2)
                                      & (body >= 0.5 * rng) & (B1 >= 0.5 * (H1 - L1)) & (B2 >= 0.5 * (H2 - L2)), lo3, h),
        # SELL (bearish) -> (shape, stop ref = pattern high, trigger = last candle low)
        ("Hanging Man", -1): ((rng > 0) & (lw >= 2 * body) & (uw <= 0.3 * rng), h, l),
        ("Bearish Engulfing", -1): (bear_eng, hi2, l),
        ("Evening Star", -1): (G2 & LG2 & S1 & r & (c <= (O2 + C2) / 2), hi3, l),
        ("Evening Doji Star", -1): (G2 & LG2 & D1 & r & (c <= (O2 + C2) / 2), hi3, l),
        ("Shooting Star", -1): ((rng > 0) & (uw >= 2 * body) & (lw <= 0.3 * rng), h, l),
        ("Tweezer Top", -1): (G1 & r & (np.abs(h - H1) <= 0.05 * sh(a, 1)), hi2, l),
        ("Three Inside Down", -1): (G2 & LG2 & R1 & (O1 <= C2) & (C1 >= O2) & (c < O2), hi3, l),
        ("Three Outside Down", -1): ((sh(bear_eng, 1) == 1) & r & (c < C1), hi3, l),
        ("Gravestone Doji", -1): (doji & (lw <= 0.1 * rng) & (uw >= 0.7 * rng), h, l),
    }
    e20, e50 = I.ema(f["close"], 20).values, I.ema(f["close"], 50).values
    down, up = (e20 < e50) & (C1 < sh(e50, 1)), (e20 > e50) & (C1 > sh(e50, 1))
    return P, {1: down, -1: up}


def run(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return []
    rows = []
    for seg, f, _od, cost in fr:
        if not seg.endswith(("1d", "2011-26")) or "proxy" in seg:
            continue
        f = f.reset_index(drop=True)
        if len(f) < 120:
            continue
        f["atr"] = I.atr(f, 14)
        P, TR = patterns(f)
        tm = f["time"].values
        market = "NSE index 2011-26" if "NSE" in seg else seg.split()[0]
        for (pat, side), (shape, sref, trig) in P.items():
            sig = np.nan_to_num(shape.astype(float)).astype(bool) & TR[side]
            for tg in (1.0, 2.0):
                busy = -1
                for i in np.flatnonzero(sig):
                    if i < 60 or i <= busy or i >= len(f) - 2 or f["switch"].iat[i] or not f["atr"].iat[i] > 0:
                        continue
                    t = DC.trade(f, i, side, sref[i], trig[i], "E2", tg, cost)
                    if t is None:
                        continue
                    busy = t["j"]
                    rows.append((market, job[1], pat, "BUY" if side > 0 else "SELL", f"{tg:g}R", tm[i], t["r1"], t["r2"],
                                 t["why"].startswith("target")))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] in ("mi", "nse", "stk")]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(run, J, chunksize=2) for r in x]
    T = pd.DataFrame(rows, columns=["market", "name", "pattern", "side", "target", "time", "r1", "r2", "hit"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    lh = T["market"].str.contains("NSE")
    a = np.where(lh, np.datetime64("2019-01-01"), np.datetime64("2024-07-01"))
    b = np.where(lh, np.datetime64("2022-01-01"), np.datetime64("2025-07-01"))
    T["split"] = np.where(T["time"].values < a, "train", np.where(T["time"].values < b, "valid", "test"))
    T.to_csv(OUT / "allpat_trades.csv.gz", index=False)
    K = ["market", "pattern", "side", "target"]
    S = T.groupby(K).agg(n=("r1", "size"), success=("hit", "mean"), win=("r1", lambda s: (s > 0).mean()), R=("r1", "mean"),
                         R2x=("r2", "mean")).join(T.pivot_table(index=K, columns="split", values="r1", aggfunc="mean")[["train", "valid", "test"]])
    S["all3"] = (S[["train", "valid", "test"]] > 0).all(axis=1)
    S = S.reset_index()
    S.to_csv(OUT / "allpat_summary.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
    for m in S.market.unique():
        x = S[(S.market == m)].pivot_table(index=["side", "pattern"], columns="target", values=["n", "success", "R", "all3"], aggfunc="first")
        x.columns = [f"{t}_{v}" for v, t in x.columns]
        x = x[["1R_n", "1R_success", "1R_R", "2R_success", "2R_R", "2R_all3"]]
        print(f"\n=== {m} ===")
        print(x.round(3).to_string())


if __name__ == "__main__":
    main()
