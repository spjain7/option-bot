"""HIT80-001 (4-Nov-2026) – does ANY setup reach >= 80 % "favourable follow-through" out of sample?

Metric (owner's definition, fixed before running):
  signal on a completed candle -> entry at the NEXT candle's open -> stop = s x ATR(14) below/above the entry (s >= 1),
  R = entry-to-stop distance -> "win at kR" = price reaches entry + (k + 0.1) R before it touches the stop, i.e. the
  trader nets +kR after the 0.1R cost (the plain gross +0.5R touch rate is reported too).
  Conservative candle order: a candle that touches both stop and target counts as the stop; a gap through the stop
  fills at the open; no target within the max hold (or before a contract switch / split) = NOT a win (marked to the
  close, minus cost, for the expectancy). One position per instrument and rule (next signal only after the exit).
Split: TRAIN = up to 31-Dec-2024 (selection only), TEST = 1-Jan-2025 -> Oct-2026 (reported).
Universe: MCX 7 + NIFTY/BANKNIFTY futures (1h, 3h from 1h, daily; MCX/index daily also 2006-24 from the Angel daily
  stitched series), 181 stock futures (1h, 3h, daily built from 1h, Jul-2022 ->).
Grid: segment x timeframe x side x 8 entries x 6 filters x 5 stops; one rule per segment (pooled, not per instrument).
Multiple testing: (1) selection on TRAIN only, (2) every combo is compared with the RANDOM-ENTRY control of the same
  segment/timeframe/side/stop (the geometric base rate), BH-FDR on a one-sided binomial test, (3) Wilson 95 % bounds.

  python -m research.search.hit80_search        -> research/search/results_hit80/*
"""
import itertools, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa: E402
from alerts import stats as ST  # noqa: E402
from research.search import strategy_search as SS  # noqa: E402

OUT = ROOT / "research/search/results_hit80"
SPLIT = pd.Timestamp("2025-01-01")
COST = 0.1
KS = (0.5, 1.0, 2.0)
STOPS = ("1.0", "1.5", "2.0", "3.0", "swing")
ENTRIES = ("random", "pullback", "rsi2", "donchian", "adx_ema20", "nr7", "momo", "stretch")
FILTERS = ("none", "htf", "lowvol", "adx25", "vol15", "htf_lowvol")
MAXH = {"1h": 40, "3h": 30, "1d": 30}
RNG = np.random.default_rng(7)


# ─────────── data ───────────
def mark_switch(df, sw, split_gap=None):
    """Back-adjust the stitched front-month series at every contract switch (and, on stocks, at split/bonus gaps):
    prices before the switch bar are multiplied by open(switch bar) / close(previous bar), so no trade sees a roll
    jump (the genuine overnight move of that one bar is removed too - small, stated limitation). Trades are only
    blocked at data holes (> 7 calendar days without candles). Returns the 'switch' (hole) flags; prices in place."""
    d = df["time"].dt.normalize()
    first = (d != d.shift(1)).values
    k = d.isin(sw).values & first
    gap = (df["open"] / df["close"].shift(1) - 1).abs().values
    if split_gap is not None:
        k = k | (np.nan_to_num(gap) > split_gap)
    k[0] = False
    fac = np.ones(len(df))
    ratio = (df["open"].values / df["close"].shift(1).values)
    for i in np.flatnonzero(k):
        fac[:i] *= ratio[i]
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].values * fac
    hole = (df["time"].diff().dt.days > 7).fillna(False).values
    return hole


def datasets():
    for exch, name in SS.NAMES:
        seg = "IDX" if exch == "NFO" else "MCX"
        h = SS.load(exch, name, "ONE_HOUR")
        sw = SS.switch_days(name, exch, h)
        h["switch"] = mark_switch(h, sw)
        yield seg, "1h", name, h
        t3 = ST.three_hour_generic(h); t3["switch"] = mark_switch(t3, sw)
        yield seg, "3h", name, t3
        dd = SS.load(exch, name, "ONE_DAY")
        if dd is not None and len(dd) > 400:
            dd = dd[dd["time"] >= "2006-01-01"].reset_index(drop=True)
            try:
                swd = SS.switch_days(name, exch, dd)
            except Exception:
                swd = set()
            dd["switch"] = mark_switch(dd, swd, split_gap=0.08)   # unexplained daily jumps treated as rolls
            yield seg, "1d", name, dd
    man = pd.read_csv(SS.ROOT / "research/data/angel/NFO_STK/manifest_stocks.csv")
    for r in man.itertuples():
        f = SS.ROOT / f"research/data/angel/NFO_STK/{r.name}_ONE_HOUR.csv"
        if not f.exists():
            continue
        h = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]]
        h = h.sort_values("time").drop_duplicates("time").iloc[:-1].reset_index(drop=True)
        if len(h) < 1500:
            continue
        sw = SS.switch_days(r.name, "NFO", h)
        h["switch"] = mark_switch(h, sw, split_gap=0.12)
        yield "STK", "1h", r.name, h
        t3 = ST.three_hour_generic(h); t3["switch"] = mark_switch(t3, sw, split_gap=0.12)
        yield "STK", "3h", r.name, t3
        dd = SS.daily_from(h); dd["switch"] = mark_switch(dd, sw, split_gap=0.12)
        yield "STK", "1d", r.name, dd


# ─────────── features (all on the completed candle i) ───────────
def features(df, tf):
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    a = I.atr(df, 14)
    e20, e50, e200 = I.ema(c, 20), I.ema(c, 50), I.ema(c, 200)
    r2, r14 = I.rsi(c, 2), I.rsi(c, 14)
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0)).ewm(alpha=1 / 14, adjust=False).mean()
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0)).ewm(alpha=1 / 14, adjust=False).mean()
    adx = I.adx(df, 14)
    rng = h - l
    if tf == "1d":
        vr = df["volume"] / df["volume"].rolling(20).mean().shift(1)
        e100 = I.ema(c, 100)
        htf = np.where((c > e100) & (e100 > e100.shift(10)), 1, np.where((c < e100) & (e100 < e100.shift(10)), -1, 0))
    else:
        vr, _ = I.slot_volume_ratio(df)
        day = df["time"].dt.normalize()
        dly = df.groupby(day).agg(close=("close", "last"))
        de = I.ema(dly["close"], 50)
        t = pd.Series(np.where((dly["close"] > de) & (de > de.shift(5)), 1,
                               np.where((dly["close"] < de) & (de < de.shift(5)), -1, 0)), index=dly.index).shift(1)
        htf = day.map(t).fillna(0).values                  # previous completed day only
    atrp = a / c
    lowvol = (atrp < atrp.rolling(250, min_periods=100).median()).values
    hh20, ll20 = h.rolling(20).max().shift(1), l.rolling(20).min().shift(1)
    nr7 = (rng <= rng.rolling(7).min()).shift(1).fillna(False).astype(bool)
    pos = ((c - l) / rng.replace(0, np.nan)).fillna(0.5)
    z = (c - e20) / a
    L = {"random": np.ones(len(df), bool),
         "pullback": ((c > e50) & (e50 > e200) & (r14 < 40)).values,
         "rsi2": ((r2 < 5) & (c > e200)).values,
         "donchian": ((c > hh20) & (vr > 1.5)).values,
         "adx_ema20": ((adx > 30) & (pdm > mdm) & (l <= e20) & (c > e20)).values,
         "nr7": (nr7 & (c > h.shift(1)) & (c > e50)).values,
         "momo": ((rng > 2 * a) & (pos > 0.75)).values,
         "stretch": ((z < -2.5) & (c > e200)).values}
    S = {"random": L["random"],
         "pullback": ((c < e50) & (e50 < e200) & (r14 > 60)).values,
         "rsi2": ((r2 > 95) & (c < e200)).values,
         "donchian": ((c < ll20) & (vr > 1.5)).values,
         "adx_ema20": ((adx > 30) & (mdm > pdm) & (h >= e20) & (c < e20)).values,
         "nr7": (nr7 & (c < l.shift(1)) & (c < e50)).values,
         "momo": ((rng > 2 * a) & (pos < 0.25)).values,
         "stretch": ((z > 2.5) & (c < e200)).values}
    base = {"htf": None, "lowvol": lowvol, "adx25": (adx > 25).values, "vol15": (vr > 1.5).fillna(False).values}
    swing_lo = (c - l.rolling(10).min()) / a + 0.1
    swing_hi = (h.rolling(10).max() - c) / a + 0.1
    return dict(a=a.values, L=L, S=S, base=base, htf=np.asarray(htf), swl=swing_lo.values, swh=swing_hi.values)


def flt_mask(F, flt, side):
    if flt == "none":
        return np.ones(len(F["a"]), bool)
    if flt == "htf":
        return F["htf"] == side
    if flt == "htf_lowvol":
        return (F["htf"] == side) & F["base"]["lowvol"]
    return F["base"][flt]


# ─────────── outcomes for every possible entry bar (vectorised over bars) ───────────
def outcomes(df, F, side, stop, H):
    """For entry at open[i+1] after signal bar i: win flags for k in KS (net targets), gross 0.5R touch,
    exit index of the 0.5R trade and its net R. Arrays indexed by the signal bar i."""
    o, h, l, c = (df[x].values.astype(float) for x in ("open", "high", "low", "close"))
    sw = df["switch"].values
    n = len(o)
    a = F["a"]
    if stop == "swing":
        m = F["swl"] if side > 0 else F["swh"]
        mult = np.clip(np.nan_to_num(m, nan=1.0), 1.0, 4.0)
    else:
        mult = np.full(n, float(stop))
    e = np.r_[o[1:], np.nan]
    R = mult * a
    st = e - side * R
    tg = {k: e + side * (k + COST) * R for k in KS}
    tg["g05"] = e + side * 0.5 * R
    alive_stop = np.ones(n, bool)                      # neither stop nor this target yet
    res = {}
    for key in list(KS) + ["g05"]:
        res[key] = dict(win=np.zeros(n, bool), done=np.zeros(n, bool), ex=np.full(n, -1), r=np.full(n, np.nan))
    stopped = np.zeros(n, bool); stop_ex = np.full(n, -1); stop_r = np.full(n, np.nan)
    blocked = np.zeros(n, bool)                        # contract switch reached -> trade closed at previous close
    for j in range(1, H + 1):
        idx = np.arange(n) + j                          # bar index being examined
        ok = idx < n
        ii = np.where(ok, idx, n - 1)
        # contract switch on the bar being examined -> close at previous bar's close
        hit_sw = ok & sw[ii] & ~stopped & ~blocked
        newly_block = hit_sw
        prev_c = c[np.clip(ii - 1, 0, n - 1)]
        for key in res:
            rr = res[key]
            m = newly_block & ~rr["done"]
            rr["done"][m] = True; rr["ex"][m] = ii[m] - 1; rr["r"][m] = side * (prev_c[m] - e[m]) / R[m] - COST
        blocked |= newly_block
        act = ok & ~stopped & ~blocked
        gap = act & ((o[ii] <= st) if side > 0 else (o[ii] >= st)) & (j > 1)
        touch = act & ((l[ii] <= st) if side > 0 else (h[ii] >= st))
        sp = np.where(gap, o[ii], st)
        for key in res:
            rr = res[key]
            m = touch & ~rr["done"]
            rr["done"][m] = True; rr["ex"][m] = ii[m]; rr["r"][m] = side * (sp[m] - e[m]) / R[m] - COST
        stopped |= touch
        act2 = act & ~touch
        for key in res:
            rr = res[key]; t = tg[key]
            hit = act2 & ~rr["done"] & ((h[ii] >= t) if side > 0 else (l[ii] <= t))
            # a gap open beyond the target fills at the open (in the trader's favour, but realistic)
            fill = np.where(((o[ii] >= t) if side > 0 else (o[ii] <= t)) & (j > 1), o[ii], t)
            rr["done"][hit] = True; rr["win"][hit] = True; rr["ex"][hit] = ii[hit]
            rr["r"][hit] = side * (fill[hit] - e[hit]) / R[hit] - COST
        if j == H:
            for key in res:
                rr = res[key]
                m = ok & ~rr["done"]
                rr["done"][m] = True; rr["ex"][m] = ii[m]; rr["r"][m] = side * (c[ii][m] - e[m]) / R[m] - COST
    valid = np.isfinite(e) & (a > 0) & ~sw & (np.arange(n) + H < n) & np.isfinite(R)
    valid &= ~np.r_[sw[1:], False]                     # no entry on the bar before a switch either
    for key in res:
        res[key]["done"] &= valid
    return valid, res


def sequential(sig, ex):
    """One position at a time: take signal i, skip signals until the exit bar of that trade."""
    out, nxt = [], -1
    for i in np.flatnonzero(sig):
        if i > nxt:
            out.append(i); nxt = ex[i]
    return np.array(out, int)


# ─────────── run ───────────
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    agg = {}
    for seg, tf, name, df in datasets():
        df = df.reset_index(drop=True)
        if len(df) < 400:
            continue
        F = features(df, tf)
        years = df["time"].dt.year.values
        H = MAXH[tf]
        for side, stop in itertools.product((1, -1), STOPS):
            valid, res = outcomes(df, F, side, stop, H)
            ex = res[0.5]["ex"]
            for ent, flt in itertools.product(ENTRIES, FILTERS):
                if ent == "random" and flt != "none":
                    continue
                sig = (F["L"] if side > 0 else F["S"])[ent] & flt_mask(F, flt, side) & valid
                if ent == "random":                          # random control: ~1 entry per 10 bars, fixed seed
                    sig = sig & (RNG.random(len(sig)) < 0.1)
                ids = sequential(sig, ex)
                if len(ids) == 0:
                    continue
                yy = years[ids]
                cols = np.c_[np.ones(len(ids)), res[0.5]["win"][ids], res[1.0]["win"][ids], res[2.0]["win"][ids],
                             res["g05"]["win"][ids], res[0.5]["r"][ids], res[1.0]["r"][ids], res[2.0]["r"][ids],
                             res[0.5]["r"][ids] ** 2]
                for y in np.unique(yy):
                    k = (seg, tf, side, stop, ent, flt, int(y))
                    v = cols[yy == y].sum(0)
                    agg[k] = agg[k] + v if k in agg else v
        print(seg, tf, name, len(agg), flush=True)
    A = pd.DataFrame([(*k, *v) for k, v in agg.items()],
                     columns=["seg", "tf", "side", "stop", "entry", "filter", "year", "n", "w05", "w10", "w20", "g05",
                              "r05", "r10", "r20", "r05sq"])
    A.to_csv(OUT / "agg_by_year.csv.gz", index=False)
    analyse(A)


def _has_pq():
    try:
        import pyarrow  # noqa
        return True
    except Exception:
        return False


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n; d = 1 + z * z / n; cen = (p + z * z / (2 * n)) / d; hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return cen - hw, cen + hw


def binom_sf(k, n, p):
    """P(X >= k), X ~ Bin(n, p) (exact, log-space)."""
    if k <= 0:
        return 1.0
    from math import lgamma, log, exp
    lp, lq = log(p), log(1 - p)
    s = 0.0
    for x in range(k, n + 1):
        s += exp(lgamma(n + 1) - lgamma(x + 1) - lgamma(n - x + 1) + x * lp + (n - x) * lq)
    return min(1.0, s)


def analyse(A):
    key = ["seg", "tf", "side", "stop", "entry", "filter"]
    A = A.copy(); A["test"] = A["year"] >= SPLIT.year
    s = A.groupby(key + ["test"])[["n", "w05", "w10", "w20", "g05", "r05", "r10", "r20"]].sum()
    for c in ["w05", "w10", "w20", "g05", "r05", "r10", "r20"]:
        s[c] = s[c] / s["n"]
    g = s.unstack("test"); g.columns = [f"{a}_{'te' if b else 'tr'}" for a, b in g.columns]
    g = g.reset_index()
    for c in [x for x in g.columns if x.startswith("n_")]:
        g[c] = g[c].fillna(0).astype(int)
    # random-entry control rates (same seg/tf/side/stop) – the geometric base rate
    base = g[g["entry"] == "random"].set_index(["seg", "tf", "side", "stop"])
    g = g.join(base[["w05_tr", "w05_te"]].rename(columns={"w05_tr": "rnd_tr", "w05_te": "rnd_te"}), on=["seg", "tf", "side", "stop"])
    combos = g[g["entry"] != "random"].copy()
    n_tried = len(combos)
    # one-sided binomial p-value of the TEST win rate vs the random-entry test rate, BH-FDR across all combos
    p = []
    for r in combos.itertuples():
        n = r.n_te; k = int(round(r.w05_te * n)) if n else 0
        p.append(binom_sf(k, n, min(max(r.rnd_te, 1e-3), 0.999)) if n >= 30 and np.isfinite(r.rnd_te) else 1.0)
    combos["p_vs_rnd"] = p
    m = len(combos); order = np.argsort(combos["p_vs_rnd"].values); q = np.empty(m)
    ps = combos["p_vs_rnd"].values[order]; qq = np.minimum.accumulate((ps * m / np.arange(1, m + 1))[::-1])[::-1]
    q[order] = np.minimum(qq, 1); combos["q_bh"] = q
    combos["wil_lo_te"] = [wilson(int(round(w * n)), n)[0] if n else np.nan for w, n in zip(combos["w05_te"].fillna(0), combos["n_te"])]
    combos.round(4).to_csv(OUT / "combos.csv", index=False)
    g[g["entry"] == "random"].round(4).to_csv(OUT / "random_control.csv", index=False)

    elig = combos[(combos["n_tr"] >= 100) & (combos["n_te"] >= 30)]
    sel = elig[elig["w05_tr"] >= 0.80]                                   # chosen on TRAIN only
    hit_te = combos[(combos["n_te"] >= 30) & (combos["w05_te"] >= 0.80)]  # any combo at >= 80 % in TEST (data-mined)
    both = sel[sel["w05_te"] >= 0.80]
    cols = ["seg", "tf", "side", "stop", "entry", "filter", "n_tr", "n_te", "w05_tr", "w05_te", "rnd_te", "w10_te", "w20_te",
            "g05_te", "r05_tr", "r05_te", "r10_te", "r20_te", "wil_lo_te", "q_bh"]
    summary = dict(combos_tried=n_tried, eligible_n100_n30=len(elig), train_ge80=len(sel), train_and_test_ge80=len(both),
                   test_ge80_any=len(hit_te), test_ge80_and_q10=int((hit_te["q_bh"] < 0.10).sum()),
                   both_list=both[cols].round(3).to_dict("records"))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    pd.set_option("display.width", 250)
    print(json.dumps({k: v for k, v in summary.items() if k != "both_list"}, indent=1))
    print("\nRandom-entry control (geometric base rate), w05 train/test:")
    print(g[g["entry"] == "random"][["seg", "tf", "side", "stop", "n_tr", "n_te", "w05_tr", "w05_te", "g05_te", "r05_te"]].round(3).to_string(index=False))
    print("\nSelected on TRAIN (w05 >= 80 %, n_tr >= 100, n_te >= 30) -> TEST:")
    print(sel.sort_values("w05_te", ascending=False)[cols].round(3).head(40).to_string(index=False))
    print("\nTop TEST w05 (data-mined, n_te >= 30):")
    print(combos[combos["n_te"] >= 30].sort_values("w05_te", ascending=False)[cols].round(3).head(25).to_string(index=False))
    print("\nBest TEST expectancy at 0.5R among eligible with r05_tr > 0:")
    print(elig[elig["r05_tr"] > 0].sort_values("r05_te", ascending=False)[cols].round(3).head(15).to_string(index=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "analyse":
        analyse(pd.read_csv(OUT / "agg_by_year.csv.gz"))
    else:
        main()
