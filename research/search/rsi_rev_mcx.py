"""RSIREV-001 (4-Nov-2026) – owner's rule, every MCX commodity, 1-hour candles:
  SELL: RSI(14) >= 75 (on the signal candle or touched within the last W candles) AND a bearish trigger
  BUY : RSI(14) <= 25 (same)                                                        AND a bullish trigger
  triggers: "brk"  = candle CLOSES below the previous candle's low (BUY: above previous high)
            "rev"  = reversal candle: engulfing, or shooting star / hammer (wick >= 2 x body, close in the far 40 %)
            "any"  = brk OR rev (the owner's wording)
Entry next candle open; stop = swing (10-candle high/low + 0.1 ATR, 1-4 ATR) or 1 / 2 ATR; targets 1R / 2R; costs 0.1R; max 40 h;
one trade at a time per commodity. Roll-adjusted stitched front month (Jul-2022 -> Oct-2026).
TRAIN = up to 31-Dec-2024 (choose), TEST = 2025-26 (report). The owner's exact rule (75/25, W=3, any, swing) is reported for every
commodity without any choosing.

  python -m research.search.rsi_rev_mcx    -> research/search/results_rsirev/*
"""
import itertools, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.search import hit80_search as H  # noqa: E402

OUT = ROOT / "research/search/results_rsirev"
SPLIT = pd.Timestamp("2025-01-01")
LEVELS = ((75, 25), (80, 20), (70, 30))
WINDOWS = (1, 3, 5)
TRIGS = ("brk", "rev", "any")
STOPS = ("swing", "1.0", "2.0")
TGTS = (1.0, 2.0)


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def signals(df):
    o, h, l, c = (df[k] for k in ("open", "high", "low", "close"))
    r = rsi(c)
    body = (c - o).abs(); rng = (h - l).replace(0, np.nan)
    pos = (c - l) / rng
    up_w, lo_w = h - np.maximum(o, c), np.minimum(o, c) - l
    bear_eng = (c < o) & (c.shift() > o.shift()) & (c <= o.shift()) & (o >= c.shift())
    bull_eng = (c > o) & (c.shift() < o.shift()) & (c >= o.shift()) & (o <= c.shift())
    star = (up_w >= 2 * body) & (pos <= 0.4)
    hammer = (lo_w >= 2 * body) & (pos >= 0.6)
    trig = {"brk": (c < l.shift(), c > h.shift()), "rev": (bear_eng | star, bull_eng | hammer)}
    trig["any"] = (trig["brk"][0] | trig["rev"][0], trig["brk"][1] | trig["rev"][1])
    out = {}
    for (hi, lo), w, t in itertools.product(LEVELS, WINDOWS, TRIGS):
        ob = (r.rolling(w).max() >= hi); os_ = (r.rolling(w).min() <= lo)
        out[(hi, w, t, -1)] = (ob & trig[t][0]).fillna(False).values
        out[(hi, w, t, 1)] = (os_ & trig[t][1]).fillna(False).values
    return out


def stats(r):
    r = np.asarray(r, float)
    if len(r) == 0:
        return dict(n=0, win=np.nan, avgR=np.nan, pf=np.nan)
    g, ls = r[r > 0].sum(), -r[r < 0].sum()
    return dict(n=len(r), win=round((r > 0).mean(), 3), avgR=round(r.mean(), 3), pf=round(g / ls, 2) if ls else np.nan)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for seg, tf, name, df in H.datasets():
        if seg == "STK":
            break
        if seg != "MCX" or tf != "1h":
            continue
        df = df.reset_index(drop=True)
        F = H.features(df, "1h")
        S = signals(df)
        tt = df["time"].values
        for stop in STOPS:
            for side in (1, -1):
                valid, res = H.outcomes(df, F, side, stop, 40)
                for key, sig in S.items():
                    if key[3] != side:
                        continue
                    for tg in TGTS:
                        rr = res[tg]
                        idx = H.sequential(sig & valid, rr["ex"])
                        for i in idx:
                            rows.append((name, key[0], key[1], key[2], "BUY" if side > 0 else "SELL", stop, tg,
                                         tt[i], rr["r"][i]))
        print(name, "done", flush=True)
    t = pd.DataFrame(rows, columns=["name", "lvl", "win", "trig", "side", "stop", "tgt", "time", "R"])
    t["period"] = np.where(pd.to_datetime(t.time) < SPLIT, "train", "test")
    t.to_csv(OUT / "trades.csv.gz", index=False)
    keys = ["name", "side", "lvl", "win", "trig", "stop", "tgt"]
    agg = []
    for k, g in t.groupby(keys):
        a = dict(zip(keys, k))
        for p in ("train", "test"):
            for kk, v in stats(g.R[g.period == p]).items():
                a[f"{p}_{kk}"] = v
        agg.append(a)
    A = pd.DataFrame(agg)
    A.to_csv(OUT / "combos.csv", index=False)
    pd.set_option("display.width", 220)
    own = A[(A.lvl == 75) & (A.win == 3) & (A.trig == "any") & (A.stop == "swing")]
    print("\n=== OWNER RULE (75/25, touched in last 3 h, breakdown OR reversal candle, swing stop) ===")
    print(own.to_string(index=False))
    # choose per commodity+side on TRAIN only (n>=30, best avgR), report TEST
    pick = (A[A.train_n >= 30].sort_values("train_avgR", ascending=False).groupby(["name", "side"]).head(1))
    print("\n=== BEST ON TRAIN (2022-24) -> TEST (2025-26) ===")
    print(pick[keys + ["train_n", "train_win", "train_avgR", "test_n", "test_win", "test_avgR", "test_pf"]].to_string(index=False))
    n_combo = len(A)
    print("\ncombos tested:", n_combo, " test avgR>0 among train-picked:", int((pick.test_avgR > 0).sum()), "/", len(pick))
    pick.to_csv(OUT / "picked.csv", index=False); own.to_csv(OUT / "owner_rule.csv", index=False)


if __name__ == "__main__":
    main()
