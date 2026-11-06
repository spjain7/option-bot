"""SEARCH-V2 (6-Nov-2026, owner mission: more high-quality calls on every timeframe). Same discipline as SEARCH-ALL-001:
completed candles only, next-open entry (skipped > 0.5 ATR away), stop first inside a candle, 2x costs, one trade at a time per
instrument, contract-roll days skipped, periods p1 < 2024-07-01 ≤ p2 < 2025-07-01 ≤ p3, Benjamini-Hochberg across EVERY
combination tried, plus a regime split of each trade (daily trend up / down / flat × daily volatility high / low).
Timeframes: MCX 15m / 30m (Angel 5-min front-month, 2023-26), MCX + index futures 1h / 2h / 3h / 4h / 1d (2022-26),
stocks 2h / 3h / 4h / 1d (181 futures, 2022-26).
New families (both sides, each with none / daily-trend filter where it makes sense):
  RSIREV  RSI14 crosses back inside 30/70, 25/75, 20/80, 15/85          RSICONT RSI14 crosses beyond 70/30, 75/25, 80/20
  RSIDIV  10-candle low/high with RSI higher/lower than at the previous extreme, reversal candle
  MACD    MACD(12,26,9) signal cross (EMA200 side) and zero cross       ST      Supertrend(10, 3) flip
  EMAX    EMA 9/21, 13/48, 20/50, 50/200 cross                         DMI     +DI/−DI cross with ADX ≥ 20
  INSIDE  inside bar, then close beyond the mother bar                  PIN     pin bar (wick ≥ 2 body, ≥ 60 % range) at a 20-candle extreme
  MOMO    momentum candle: body ≥ 1.5 ATR, close in the top/bottom 20 %  FAIL    failed 20-candle breakout: close back inside -> reverse
  RETEST  breakout of the 20-candle high within 5 candles, pull-back to ≤ 0.3 ATR of the level, close back above
  ORB     (15m / 30m) close beyond the day's first candle before 12:00   BO      20-candle breakout + volume 1.5x + daily trend (baseline)
python research/program/search_v2.py"""
import sys
import time
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, touch as TC, search_all as SA  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
EXITS = SA.EXITS
MAXH = {"15m": 40, "30m": 30, "1h": 60, "2h": 50, "3h": 40, "4h": 40, "1d": 20}
P1, P2 = SA.P1, SA.P2


def cross_up(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return (a > b) & (np.r_[np.nan, a[:-1]] <= np.r_[np.nan, b[:-1]])


def supertrend(f, n=10, m=3.0):
    h, l, c = f["high"].values, f["low"].values, f["close"].values
    a = I.atr(f, n).values
    hl2 = (h + l) / 2
    ub, lb = hl2 + m * a, hl2 - m * a
    fu, fl = ub.copy(), lb.copy()
    d = np.ones(len(c))
    for i in range(1, len(c)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        d[i] = 1 if c[i] > fu[i - 1] else (-1 if c[i] < fl[i - 1] else d[i - 1])
    return d


def dmi(f, n=14):
    h, l = f["high"], f["low"]
    up, dn = h.diff(), -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = I.atr(f, n)
    pdi = 100 * pd.Series(pdm).ewm(alpha=1 / n, adjust=False).mean().values / a.values
    mdi = 100 * pd.Series(mdm).ewm(alpha=1 / n, adjust=False).mean().values / a.values
    return pdi, mdi


def signal_sets(f, dtr, tf):
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    cs, hs, ls = f["close"].astype(float), f["high"].astype(float), f["low"].astype(float)
    ema200, adx, volx, atr = f["ema200"].values, f["adx"].values, f["volx"].values, f["atr"].values
    day = pd.to_datetime(f["time"]).dt.normalize()
    dt = day.map(dtr).fillna(0).values
    F = {"none": (np.ones(len(c), bool),) * 2, "DT": (dt > 0, dt < 0), "EMA200": (c > ema200, c < ema200)}
    out = []

    def add(fam, par, b, s, filts=("none", "DT")):
        for fn in filts:
            fb, fs = F[fn]
            out.append((fam, par, fn, b & fb, s & fs))
    rsi = f["rsi"].values
    for L, U in ((30, 70), (25, 75), (20, 80), (15, 85)):
        add("RSIREV", f"{L}/{U}", cross_up(rsi, np.full(len(c), L)), cross_up(-rsi, np.full(len(c), -U)), ("none", "DT", "EMA200"))
    for U, L in ((70, 30), (75, 25), (80, 20)):
        add("RSICONT", f"{U}/{L}", cross_up(rsi, np.full(len(c), U)), cross_up(-rsi, np.full(len(c), -L)))
    lo10, hi10 = ls.rolling(10).min().values, hs.rolling(10).max().values
    rmin_prev = pd.Series(rsi).shift(1).rolling(10).min().values; rmax_prev = pd.Series(rsi).shift(1).rolling(10).max().values
    add("RSIDIV", "10", (l <= lo10) & (rsi > rmin_prev + 5) & (rsi < 40) & (c > o), (h >= hi10) & (rsi < rmax_prev - 5) & (rsi > 60) & (c < o))
    e12, e26 = I.ema(cs, 12).values, I.ema(cs, 26).values
    macd = e12 - e26; sig = pd.Series(macd).ewm(span=9, adjust=False).mean().values
    add("MACD", "signal", cross_up(macd, sig) & (c > ema200), cross_up(sig, macd) & (c < ema200), ("none", "DT"))
    add("MACD", "zero", cross_up(macd, np.zeros(len(c))), cross_up(-macd, np.zeros(len(c))))
    st = supertrend(f)
    stp = np.r_[st[0], st[:-1]]
    add("ST", "10/3", (st > 0) & (stp < 0), (st < 0) & (stp > 0))
    for a_, b_ in ((9, 21), (13, 48), (20, 50), (50, 200)):
        ea, eb = I.ema(cs, a_).values, I.ema(cs, b_).values
        add("EMAX", f"{a_}/{b_}", cross_up(ea, eb), cross_up(eb, ea))
    pdi, mdi = dmi(f)
    add("DMI", "14/20", cross_up(pdi, mdi) & (adx >= 20), cross_up(mdi, pdi) & (adx >= 20))
    hp, lp = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
    hp2, lp2 = np.r_[np.nan, np.nan, h[:-2]], np.r_[np.nan, np.nan, l[:-2]]
    inside_prev = (hp <= hp2) & (lp >= lp2)
    add("INSIDE", "mother", inside_prev & (c > hp2), inside_prev & (c < lp2))
    rng = h - l; body = np.abs(c - o)
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    lo20, hi20 = ls.rolling(20).min().values, hs.rolling(20).max().values
    add("PIN", "20", (lw >= 2 * body) & (lw >= 0.6 * rng) & (l <= lo20), (uw >= 2 * body) & (uw >= 0.6 * rng) & (h >= hi20))
    pos = (c - l) / np.where(rng > 0, rng, np.nan)
    add("MOMO", "1.5ATR", (body >= 1.5 * atr) & (c > o) & (pos >= 0.8), (body >= 1.5 * atr) & (c < o) & (pos <= 0.2))
    hh20, ll20 = hs.shift(1).rolling(20).max().values, ls.shift(1).rolling(20).min().values
    hh20p, ll20p = np.r_[np.nan, hh20[:-1]], np.r_[np.nan, ll20[:-1]]
    cp = np.r_[np.nan, c[:-1]]
    add("FAIL", "20", (cp < ll20p) & (c > ll20p), (cp > hh20p) & (c < hh20p))
    brk_up = pd.Series(c > hh20).rolling(5).max().shift(1).fillna(0).values.astype(bool)
    brk_dn = pd.Series(c < ll20).rolling(5).max().shift(1).fillna(0).values.astype(bool)
    lvl_u = pd.Series(np.where(c > hh20, hh20, np.nan)).ffill().values
    lvl_d = pd.Series(np.where(c < ll20, ll20, np.nan)).ffill().values
    add("RETEST", "20/5", brk_up & (l <= lvl_u + 0.3 * atr) & (c > lvl_u), brk_dn & (h >= lvl_d - 0.3 * atr) & (c < lvl_d))
    if tf in ("15m", "30m"):
        g = day.values
        first = np.r_[True, g[1:] != g[:-1]]
        fh = pd.Series(np.where(first, h, np.nan)).groupby(g).transform("first").values
        fl = pd.Series(np.where(first, l, np.nan)).groupby(g).transform("first").values
        hm = (pd.to_datetime(f["time"]).dt.hour * 100 + pd.to_datetime(f["time"]).dt.minute).values
        early = (hm < 1200) & ~first
        bo_ = (c > fh) & early; bs_ = (c < fl) & early
        # first break of the day only
        fb_ = pd.Series(bo_).groupby(g).cumsum().values == 1; fs_ = pd.Series(bs_).groupby(g).cumsum().values == 1
        add("ORB", "first", bo_ & fb_, bs_ & fs_)
    add("BO", "N20 vol1.5", (c > hh20) & (volx >= 1.5), (c < ll20) & (volx >= 1.5), ("DT",))
    return out


def regimes(f, fd):
    """per candle: regime label from the previous completed day: trend up/down/flat × vol high/low."""
    if fd is None or len(fd) < 120:
        return np.array(["na"] * len(f))
    d = fd.reset_index(drop=True)
    c = d["close"]
    e20, e50 = I.ema(c, 20), I.ema(c, 50)
    tr = np.where((e20 > e50) & (c > e50), "up", np.where((e20 < e50) & (c < e50), "down", "flat"))
    ap = I.atr(d, 14) / c
    vol = np.where(ap > ap.rolling(250, min_periods=60).median(), "hiV", "loV")
    lab = pd.Series([f"{a}-{b}" for a, b in zip(tr, vol)], index=pd.to_datetime(d["time"]).dt.normalize().values).shift(1)
    lab = lab[~lab.index.duplicated(keep="last")]
    return pd.to_datetime(f["time"]).dt.normalize().map(lab).fillna("na").values


def mcx_intraday(name):
    from research.program import liqtl_mcx5 as LM
    d = LM.load(name, "FIVE_MINUTE")
    if d is None:
        return []
    out = []
    for m, tf in ((15, "15m"), (30, "30m")):
        f = LM.resample(d, m).reset_index(drop=True)
        cost = np.array([INS.cost_points(name, p, 1.0) for p in f["close"].values])
        out.append(("MCX", tf, f, cost))
    return out


def frames_for(job):
    res = SA.frames_for(job)
    out = []
    for mk, tf, f, c_, fd in res:
        out.append((mk, tf, f, c_, fd))
        if tf == "3h":
            continue
    # 2h from 1h
    try:
        fr = EX.frames(job)
    except Exception:
        fr = []
    for seg, f1, od, cost in fr:
        if not seg.endswith("1h") or "proxy" in seg:
            continue
        mk = seg.split()[0]
        f1 = f1.reset_index(drop=True)
        C, cid = TC.blocks(f1, "MCX" if mk == "MCX" else "STOCKS", 2)
        first = np.r_[0, np.flatnonzero(np.diff(cid)) + 1]
        c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(cost)), cost) if len(cost) != len(f1) else np.asarray(cost)
        fd = next((x[4] for x in res if x[0] == mk), None)
        out.append((mk, "2h", C, c1[first], fd))
    if job[0] == "mi" and job[2] == "MCX":
        fd = next((x[4] for x in res if x[0] == "MCX"), None)
        out += [(mk, tf, f, c_, fd) for mk, tf, f, c_ in mcx_intraday(job[1])]
    return out


def one(job):
    rows = []
    for mk, tf, f0, cost, fd in frames_for(job):
        if len(f0) < 300:
            continue
        f = H.features(f0)
        f["switch"] = f0["switch"].values if "switch" in f0 else np.zeros(len(f0), bool)
        dtr = SA.daily_trend(fd) if fd is not None else pd.Series(dtype=float)
        reg = regimes(f, fd)
        cost = np.asarray(cost, float)
        for fam, par, fn, sb, ss in signal_sets(f, dtr, tf):
            for side, s in ((1, sb), (-1, ss)):
                sig = np.where(np.nan_to_num(np.asarray(s, float)) > 0, side, 0)
                if not sig.any():
                    continue
                for k, r in EXITS:
                    for x in H.simulate(f, sig, side, k, r, MAXH[tf], 0, cost, start=210):
                        if x["status"] == "trade":
                            rows.append((mk, tf, fam, par, fn, side, f"{k:g}ATR/{r:g}R", x["time"], x["r2"], reg[x["i"]]))
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=["mkt", "tf", "fam", "par", "filt", "side", "exit", "time", "r", "reg"])
    tv = pd.to_datetime(d["time"], format="mixed").values
    d["split"] = np.where(tv < P1, "p1", np.where(tv < P2, "p2", "p3"))
    d["r2_"] = d["r"] ** 2; d["w"] = (d["r"] > 0).astype(int)
    a = d.groupby(["mkt", "tf", "fam", "par", "filt", "side", "exit", "split", "reg"]).agg(
        n=("r", "size"), s=("r", "sum"), ss=("r2_", "sum"), w=("w", "sum")).reset_index()
    a["name"] = job[1]
    return a


def summarise(A):
    from scipy import stats
    K = ["mkt", "tf", "fam", "par", "filt", "side", "exit"]
    g = A.groupby(K)[["n", "s", "ss", "w"]].sum()
    S = pd.DataFrame(dict(n=g["n"], R=g["s"] / g["n"], win=g["w"] / g["n"] * 100))
    S["sd"] = np.sqrt(np.maximum(g["ss"] / g["n"] - S["R"] ** 2, 1e-12) * g["n"] / np.maximum(g["n"] - 1, 1))
    sp = A.groupby(K + ["split"])[["n", "s"]].sum(); S = S.join((sp["s"] / sp["n"]).unstack("split"))
    rg = A.assign(tr=A["reg"].str.split("-").str[0]).groupby(K + ["tr"])[["n", "s"]].sum()
    S = S.join((rg["s"] / rg["n"]).unstack("tr").add_prefix("R_").drop(columns=["R_na"], errors="ignore"))
    vg = A.assign(v=A["reg"].str.split("-").str[-1]).groupby(K + ["v"])[["n", "s"]].sum()
    S = S.join((vg["s"] / vg["n"]).unstack("v").add_prefix("V_").drop(columns=["V_na"], errors="ignore"))
    pn = A.groupby(K + ["name"])[["n", "s"]].sum()
    pn = (pn["s"] > 0).groupby(level=list(range(len(K)))).agg(["mean", "size"])
    S["names_pos"], S["names"] = pn["mean"], pn["size"]
    S["t"] = S["R"] / (S["sd"] / np.sqrt(S["n"]))
    S["p"] = 1 - stats.t.cdf(S["t"], np.maximum(S["n"] - 1, 1))
    m = len(S); rank = S["p"].rank(method="first")
    S["q"] = (S["p"] * m / rank).sort_values(ascending=False).cummin().reindex(S.index).clip(upper=1)
    min_n = np.where(S.index.get_level_values("mkt") == "STOCKS", 200, 60)
    S["robust"] = (S[["p1", "p2", "p3"]] > 0).all(axis=1) & (S["n"] >= min_n) & (S["q"] < 0.10) & (S["names_pos"] >= 0.55)
    return S.reset_index()


def main():
    t0 = time.time()
    J = [j for j in EX.jobs() if j[0] in ("mi", "stk")]
    parts = []
    with Pool(2) as p:
        for i, x in enumerate(p.imap_unordered(one, J, chunksize=1)):
            if x is not None:
                parts.append(x)
            if i % 20 == 0:
                print(f"[{time.time() - t0:5.0f}s] {i + 1}/{len(J)}", flush=True)
    A = pd.concat(parts, ignore_index=True)
    A.to_csv(OUT / "search_v2_agg.csv.gz", index=False)
    S = summarise(A)
    S.to_csv(OUT / "search_v2_summary.csv", index=False)
    R = S[S.robust].sort_values(["mkt", "R"], ascending=[True, False])
    R.to_csv(OUT / "search_v2_robust.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 400)
    print(f"\ncombinations {len(S):,} · trades {int(S.n.sum()):,} · robust {len(R)} · {(time.time() - t0) / 60:.0f} min")
    cols = ["mkt", "tf", "fam", "par", "filt", "side", "exit", "n", "win", "R", "p1", "p2", "p3", "R_up", "R_down", "R_flat",
            "V_hiV", "V_loV", "names_pos", "q"]
    for (mk, tf), g in R.groupby(["mkt", "tf"]):
        print(f"\n=== {mk} {tf}: {len(g)} robust – top 8")
        print(g.head(8)[[c for c in cols if c in g]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
