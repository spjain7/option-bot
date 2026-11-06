"""SEARCH-ALL-001 (6-Nov-2026, owner: "do in background many trial & error, find a profitable strategy").
Systematic walk-forward search. Every rule is decided on completed candles; entry at the next open (skipped when the open is
> 0.5 ATR away); costs 2x; one trade at a time per instrument; contract-roll days skipped.
Markets / timeframes:  MCX 7 commodities + NIFTY/BANKNIFTY futures (Angel 2022-26): 1h, 3h, 4h, 1d
                        NSE NIFTY/BANKNIFTY index 2011-26: 1d       ·      181 stock futures (2022-26): 3h, 4h, 1d
Families (both sides):
  BO   close beyond the N-candle high/low · N 5/10/20/55 · volume ≥ 0 / 1.5 / 2x · filter none / EMA200 / daily trend / ADX ≥ 25
  PB   pull-back in trend: EMA fast > slow (20/50 or 10/30), low touches EMA fast, closes back above it, up candle
  RSI2 Connors mean reversion: RSI(2) < 10 (or < 5) above EMA200 (BUY), mirror SELL
  NR7  narrowest range of 7 candles, then a close beyond its high/low · filter none / EMA200 / daily trend
  SQZ  Bollinger squeeze (20, 2): band width near its 100-candle low within 5 candles, then a close outside the band
  LT   StratifyTrade liquidity-trendline signals · filter none / daily trend / daily trend + volume 1.5x
  SWP  stop-hunt: low below the 20-candle low, close back above in the top third, volume ≥ 1.5x (mirror SELL)
Exits: stop 1 ATR / 1R · 1.5 ATR / 2R · 2 ATR / 3R · 3 ATR / 6R (trend), max 60 (1h) / 40 (3h, 4h) / 20 (1d) candles.
Periods p1 < 2024-07-01 ≤ p2 < 2025-07-01 ≤ p3. ROBUST = mean R (2x costs) > 0 in all three periods, enough trades,
and Benjamini-Hochberg q < 0.10 on the one-sided t-test across every combination tried.
python research/program/search_all.py   (writes results/search_all_summary.csv and results/search_all_robust.csv)"""
import sys
import time
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, touch as TC, liqtl as LT  # noqa: E402
from research.program.tf5h import T1, T2  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
EXITS = ((1.0, 1.0), (1.5, 2.0), (2.0, 3.0), (3.0, 6.0))
MAXH = {"1h": 60, "3h": 40, "4h": 40, "1d": 20}
P1, P2 = np.datetime64(T1), np.datetime64(T2)


def daily_trend(fd):
    """previous day's daily trend per date: +1 up, -1 down, 0 none."""
    c = fd["close"].reset_index(drop=True)
    e20, e50 = I.ema(c, 20), I.ema(c, 50)
    t = np.where((e20 > e50) & (c > e50), 1, np.where((e20 < e50) & (c < e50), -1, 0))
    s = pd.Series(t, index=pd.to_datetime(fd["time"]).dt.normalize().values).shift(1)
    return s[~s.index.duplicated(keep="last")]


def signal_sets(f, dtr):
    """-> list of (family, params, filter, buy_mask, sell_mask)."""
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    v = f["volume"].values.astype(float)
    ema200, adx, volx = f["ema200"].values, f["adx"].values, f["volx"].values
    day = pd.to_datetime(f["time"]).dt.normalize()
    dt = day.map(dtr).fillna(0).values
    filt = {"none": (np.ones(len(c), bool),) * 2, "EMA200": (c > ema200, c < ema200), "DT": (dt > 0, dt < 0),
            "ADX25": (adx >= 25, adx >= 25)}
    out = []
    hs, ls = pd.Series(h), pd.Series(l)
    for N in (5, 10, 20, 55):
        hh, ll = hs.shift(1).rolling(N).max().values, ls.shift(1).rolling(N).min().values
        for vx in (0.0, 1.5, 2.0):
            vb = volx >= vx if vx else np.ones(len(c), bool)
            for fn in ("none", "EMA200", "DT", "ADX25"):
                fb, fs = filt[fn]
                out.append(("BO", f"N{N} vol{vx:g}", fn, (c > hh) & vb & fb, (c < ll) & vb & fs))
    cs = pd.Series(c)
    for a, b in ((20, 50), (10, 30)):
        ef, es = I.ema(cs, a).values, I.ema(cs, b).values
        pb_b = (ef > es) & (l <= ef) & (c > ef) & (c > o)
        pb_s = (ef < es) & (h >= ef) & (c < ef) & (c < o)
        for fn in ("none", "DT"):
            fb, fs = filt[fn]
            out.append(("PB", f"EMA{a}/{b}", fn, pb_b & fb, pb_s & fs))
    r2 = I.rsi(cs, 2).values
    for th in (10, 5):
        out.append(("RSI2", f"<{th}", "EMA200", (r2 < th) & (c > ema200), (r2 > 100 - th) & (c < ema200)))
    rng = h - l
    nr7 = rng <= pd.Series(rng).rolling(7).min().values
    nr7p = np.r_[False, nr7[:-1]]
    hp, lp = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
    for fn in ("none", "EMA200", "DT"):
        fb, fs = filt[fn]
        out.append(("NR7", "break", fn, nr7p & (c > hp) & fb, nr7p & (c < lp) & fs))
    mid = cs.rolling(20).mean(); sd = cs.rolling(20).std()
    up, dn = (mid + 2 * sd).values, (mid - 2 * sd).values
    w = (up - dn) / mid.values
    sq = pd.Series(w <= pd.Series(w).rolling(100).min().values * 1.1).rolling(5).max().fillna(0).values.astype(bool)
    for fn in ("none", "DT"):
        fb, fs = filt[fn]
        out.append(("SQZ", "BB20", fn, sq & (c > up) & fb, sq & (c < dn) & fs))
    try:
        lb, lsl = LT.signals(f[["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True))
        out += [("LT", "p5", "none", lb, lsl), ("LT", "p5", "DT", lb & filt["DT"][0], lsl & filt["DT"][1]),
                ("LT", "p5", "DT+VOL1.5", lb & filt["DT"][0] & (volx >= 1.5), lsl & filt["DT"][1] & (volx >= 1.5))]
    except Exception:
        pass
    pos = (c - l) / np.where(rng > 0, rng, np.nan)
    ll20, hh20 = ls.shift(1).rolling(20).min().values, hs.shift(1).rolling(20).max().values
    swb = (l < ll20) & (c > ll20) & (pos >= 2 / 3) & (volx >= 1.5)
    sws = (h > hh20) & (c < hh20) & (pos <= 1 / 3) & (volx >= 1.5)
    for fn in ("none", "DT"):
        fb, fs = filt[fn]
        out.append(("SWP", "20", fn, swb & fb, sws & fs))
    return out


def frames_for(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return []
    got = {}
    for seg, f, od, cost in fr:
        if "proxy" in seg:
            continue
        mk = seg.split()[0]
        tf = "1d" if seg.endswith(("1d", "2011-26")) else seg.split()[-1]
        if "2011-26" in seg:
            mk = "NSEIDX"
        c_ = np.interp(np.arange(len(f)), np.linspace(0, len(f) - 1, len(cost)), cost) if len(cost) != len(f) else np.asarray(cost)
        got[(mk, tf)] = (f.reset_index(drop=True).copy(), c_)
    res = []
    for (mk, tf), (f, c_) in got.items():
        if mk == "STOCKS" and tf == "1h":
            continue
        res.append((mk, tf, f, c_))
    if ("MCX", "1h") in got or ("STOCKS", "1h") in got or ("INDEX", "1h") in got:
        for mk in ("MCX", "STOCKS", "INDEX"):
            if (mk, "1h") in got:
                f1, c1 = got[(mk, "1h")]
                C, cid = TC.blocks(f1, "MCX" if mk == "MCX" else "STOCKS", 4)
                first = np.r_[0, np.flatnonzero(np.diff(cid)) + 1]
                res.append((mk, "4h", C, c1[first]))
    daily = {mk: f for (mk, tf), (f, c_) in got.items() if tf == "1d"}
    return [(mk, tf, f, c_, daily.get(mk)) for mk, tf, f, c_ in res]


def one(job):
    rows = []
    for mk, tf, f0, cost, fd in frames_for(job):
        if len(f0) < 300:
            continue
        f = H.features(f0)
        f["switch"] = f0["switch"].values if "switch" in f0 else np.zeros(len(f0), bool)
        dtr = daily_trend(fd) if fd is not None else pd.Series(dtype=float)
        cost = np.asarray(cost, float)
        for fam, par, fn, sb, ss in signal_sets(f, dtr):
            for side, s in ((1, sb), (-1, ss)):
                sig = np.where(np.nan_to_num(np.asarray(s, float)) > 0, side, 0)
                if not sig.any():
                    continue
                for k, r in EXITS:
                    for x in H.simulate(f, sig, side, k, r, MAXH[tf], 0, cost, start=210):
                        if x["status"] == "trade":
                            rows.append((mk, tf, fam, par, fn, side, f"{k:g}ATR/{r:g}R", x["time"], x["r2"]))
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=["mkt", "tf", "fam", "par", "filt", "side", "exit", "time", "r"])
    tv = pd.to_datetime(d["time"], format="mixed").values
    d["split"] = np.where(tv < P1, "p1", np.where(tv < P2, "p2", "p3"))
    d["r2_"] = d["r"] ** 2; d["w"] = (d["r"] > 0).astype(int)
    a = d.groupby(["mkt", "tf", "fam", "par", "filt", "side", "exit", "split"]).agg(n=("r", "size"), s=("r", "sum"), ss=("r2_", "sum"),
                                                                                   w=("w", "sum")).reset_index()
    a["name"] = job[1]
    return a


def main():
    t0 = time.time()
    J = [j for j in EX.jobs() if j[0] in ("mi", "nse", "stk")]
    parts = []
    with Pool(2) as p:
        for i, x in enumerate(p.imap_unordered(one, J, chunksize=1)):
            if x is not None:
                parts.append(x)
            if i % 20 == 0:
                print(f"[{time.time() - t0:5.0f}s] {i + 1}/{len(J)} instruments", flush=True)
    A = pd.concat(parts, ignore_index=True)
    A.to_csv(OUT / "search_all_agg.csv.gz", index=False)
    K = ["mkt", "tf", "fam", "par", "filt", "side", "exit"]
    g = A.groupby(K)[["n", "s", "ss", "w"]].sum()
    S = pd.DataFrame(dict(n=g["n"], R=g["s"] / g["n"], win=g["w"] / g["n"] * 100))
    S["sd"] = np.sqrt(np.maximum(g["ss"] / g["n"] - S["R"] ** 2, 1e-12) * g["n"] / np.maximum(g["n"] - 1, 1))
    sp = A.groupby(K + ["split"])[["n", "s"]].sum()
    sp = (sp["s"] / sp["n"]).unstack("split")
    S = S.join(sp)
    pn = A.groupby(K + ["name"])[["n", "s"]].sum()
    pn = (pn["s"] > 0).groupby(level=list(range(len(K)))).agg(["mean", "size"])
    S["names_pos"], S["names"] = pn["mean"], pn["size"]
    from scipy import stats
    S["t"] = S["R"] / (S["sd"] / np.sqrt(S["n"]))
    S["p"] = 1 - stats.t.cdf(S["t"], np.maximum(S["n"] - 1, 1))
    m = len(S); rank = S["p"].rank(method="first")
    S["q"] = (S["p"] * m / rank).sort_values(ascending=False).cummin().reindex(S.index).clip(upper=1)
    min_n = np.where(S.index.get_level_values("mkt") == "STOCKS", 200, 60)
    S["robust"] = (S[["p1", "p2", "p3"]] > 0).all(axis=1) & (S["n"] >= min_n) & (S["q"] < 0.10)
    S = S.reset_index()
    S.to_csv(OUT / "search_all_summary.csv", index=False)
    R = S[S.robust].sort_values(["mkt", "R"], ascending=[True, False])
    R.to_csv(OUT / "search_all_robust.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    print(f"\ncombinations {len(S):,} · trades {int(S.n.sum()):,} · robust {len(R)} · {(time.time() - t0) / 60:.0f} min")
    for mk, g2 in R.groupby("mkt"):
        print(f"\n=== {mk}: {len(g2)} robust – top 15")
        print(g2.head(15)[K + ["n", "win", "R", "p1", "p2", "p3", "names_pos", "q"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
