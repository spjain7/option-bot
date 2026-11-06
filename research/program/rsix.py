"""RSIX-001 (6-Nov-2026, owner: "RSI extreme reversal + candle-high/low breakout – prove or disprove each variation").
MCX first, each commodity separately, every timeframe with data: 15m / 30m (Angel 5-min front-month, Jul-2023 → Nov-2026),
1h / 2h / 4h (Angel 1-hour, Jul-2022 → Oct-2026), daily (stitched front month, 2006 → 2026). 5-minute: costs ≥ the edge
(see SEARCH-V2) – run only for the final candidates. Costs: 2x the MCX model on every trade.

SETUP on candle i (BUY; SELL is the exact mirror with 75/80/70 and bearish candles):
  extreme  E1 "touch"   RSI(n) ≤ L on i or one of the 2 candles before
           E2 "cross"   RSI crosses back above L on i
           E3 "stay"    RSI ≤ L for the last 3 candles (still extreme)
           E4 "div"     close-low at a 10-candle low with RSI higher than its prior 10-candle low by 5 (that low ≤ L + 5)
           L ∈ 20 / 25 / 30, RSI period n ∈ 14 (7 / 21 for the finalists)
  candle   none · bull (close > open, close in top half) · hammer (lower wick ≥ 2 body, ≥ 50 % range) · engulfing · any
ENTRY    MKT  next candle open
         BRK  stop order 1 tick above the setup candle's HIGH, valid 3 candles (cancelled if its LOW breaks first)
         BRKC a candle CLOSES above the setup high within 3 candles -> next open
         RET  after BRKC, a limit order back at the setup high, valid 5 candles
STOP     C  setup candle low − 0.1 ATR (candle stop)       A  entry − 1.5 ATR(14)
EXIT     1R / 2R / 3R target · TR 3-ATR chandelier trail (no target) · P50 half at 1R + stop to entry, rest at 3R
         time exit 40 candles (daily 20); stop first inside a candle; gaps fill at the open.
FILTERS  (stage 2, finalists only) higher-timeframe trend with / against, ADX < 20 / > 25, volume ≥ 1.5x, room to the nearest
         20-candle level ≥ 1R.
SELECTION walk-forward: rank on TRAIN (< 2024-07-01; daily < 2013), confirm VALID (to 2025-06-30; daily 2013-19),
report TEST (from 2025-07-01; daily 2020-26) = out of sample. Breadth of the search is printed (multiple-testing risk).
python research/program/rsix.py [stage1|stage2]"""
import sys
import time
from itertools import product
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX, liqtl_mcx5 as LM  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
NAMES = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]
EXTREMES = ("E1", "E2", "E3", "E4")
LEVELS = (20, 25, 30)
CANDLES = ("none", "bull", "hammer", "engulf", "any")
ENTRIES = ("MKT", "BRK", "BRKC", "RET")
STOPS = ("C", "A")
EXITS = ("1R", "2R", "3R", "TR", "P50")
EX_CODE = {"1R": 1, "2R": 2, "3R": 3, "TR": 0, "P50": -1}


# ── data ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def frames(name):
    out = []
    d5 = LM.load(name, "FIVE_MINUTE")
    if d5 is not None:
        for m, tf in ((15, "15m"), (30, "30m")):
            out.append((tf, LM.resample(d5, m).reset_index(drop=True)))
    fr = {s.split()[-1]: f for s, f, o, c in EX.frames(("mi", name, "MCX")) if s.startswith("MCX")}
    if "1h" in fr:
        f1 = fr["1h"].reset_index(drop=True)
        hr = f1["time"].dt.hour
        for n, tf in ((1, "1h"), (2, "2h"), (4, "4h")):
            if n == 1:
                out.append((tf, f1[["time", "open", "high", "low", "close", "volume", "switch"]].copy())); continue
            key = f1["time"].dt.normalize().astype("int64") // 10**9 * 10 + ((hr - 9).clip(lower=0) // n)
            g = f1.groupby(pd.factorize(key)[0], sort=True)
            out.append((tf, g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                  close=("close", "last"), volume=("volume", "sum"), switch=("switch", "max")).reset_index(drop=True)))
    d = daily_long(name); d["switch"] = False
    out.append(("1d", d))
    return out


def daily_long(name):
    """MCX front-month stitched daily 2006-26 (same loader as research/program/wkmo.py)."""
    D = ROOT / "research/data/angel"
    man = pd.read_csv(D / "manifest.csv")
    m = man[(man.exch == "MCX") & (man.name == name) & (man.interval == "ONE_DAY") & (man.front_stitched.astype(str) == "True")]
    d = pd.read_csv(D / "MCX" / f"{m.symbol.iat[0]}_ONE_DAY.csv", parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]]
    d = d.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    d["volume"] = d["volume"].clip(lower=0)
    return d


# ── setups ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def setup_masks(f, n=14):
    """-> dict[(side, extreme, level, candle)] = bool mask over candles."""
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    r = I.rsi(f["close"], n).values
    rng = np.where(h - l > 0, h - l, np.nan)
    body = np.abs(c - o); lw = np.minimum(o, c) - l; uw = h - np.maximum(o, c)
    pos = (c - l) / rng
    op, cp = np.r_[np.nan, o[:-1]], np.r_[np.nan, c[:-1]]
    cand = {
        1: dict(none=np.ones(len(c), bool), bull=(c > o) & (pos >= 0.5), hammer=(lw >= 2 * body) & (lw >= 0.5 * rng),
                engulf=(cp < op) & (c > o) & (o <= cp) & (c >= op)),
        -1: dict(none=np.ones(len(c), bool), bear=(c < o) & (pos <= 0.5), star=(uw >= 2 * body) & (uw >= 0.5 * rng),
                 engulf=(cp > op) & (c < o) & (o >= cp) & (c <= op))}
    cand[1]["any"] = cand[1]["bull"] | cand[1]["hammer"] | cand[1]["engulf"]
    cand[-1]["any"] = cand[-1]["bear"] | cand[-1]["star"] | cand[-1]["engulf"]
    rp = np.r_[np.nan, r[:-1]]
    rmin3 = pd.Series(r).rolling(3).min().values; rmax3 = pd.Series(r).rolling(3).max().values
    lo10 = pd.Series(l).rolling(10).min().values; hi10 = pd.Series(h).rolling(10).max().values
    rmin_prev = pd.Series(r).shift(1).rolling(10).min().values; rmax_prev = pd.Series(r).shift(1).rolling(10).max().values
    out = {}
    for L in LEVELS:
        U = 100 - L
        ext = {1: dict(E1=rmin3 <= L, E2=(rp < L) & (r >= L), E3=pd.Series(r <= L).rolling(3).sum().values == 3,
                       E4=(l <= lo10) & (r > rmin_prev + 5) & (rmin_prev <= L + 5)),
               -1: dict(E1=rmax3 >= U, E2=(rp > U) & (r <= U), E3=pd.Series(r >= U).rolling(3).sum().values == 3,
                        E4=(h >= hi10) & (r < rmax_prev - 5) & (rmax_prev >= U - 5))}
        for side in (1, -1):
            for e in EXTREMES:
                for cn in CANDLES:
                    ck = cn if side > 0 else {"bull": "bear", "hammer": "star"}.get(cn, cn)
                    out[(side, e, L, cn)] = np.nan_to_num(ext[side][e].astype(float)).astype(bool) & cand[side][ck]
    return out


# ── simulator (numba) ───────────────────────────────────────────────────────────────────────────────────────────────
@njit(cache=True)
def sim(o, h, l, c, atr, sw, idx, side, entry, stop, exitc, maxh, cost):
    """idx: setup candles. entry 0 MKT 1 BRK 2 BRKC 3 RET · stop 0 candle 1 ATR · exitc 1/2/3 = R target, 0 trail, -1 partial.
    Returns arrays (setup index, entry index, R after 2x costs, gross R)."""
    n = len(c)
    out_i = np.empty(len(idx), np.int64); out_j = np.empty(len(idx), np.int64)
    out_r = np.empty(len(idx)); out_g = np.empty(len(idx))
    k = 0
    busy = -1
    for ii in range(len(idx)):
        i = idx[ii]
        if i <= busy or i + 2 >= n or not atr[i] > 0:
            continue
        a = atr[i]
        lvl = h[i] if side > 0 else l[i]
        inv = l[i] if side > 0 else h[i]
        j = -1; e = 0.0
        if entry == 0:
            j = i + 1; e = o[j]
        elif entry == 1:
            for t in range(i + 1, min(i + 4, n)):
                if sw[t]:
                    break
                if side > 0:
                    if o[t] < inv or (l[t] < inv and not h[t] > lvl):
                        break
                    if h[t] > lvl:
                        j = t; e = max(lvl, o[t]); break
                else:
                    if o[t] > inv or (h[t] > inv and not l[t] < lvl):
                        break
                    if l[t] < lvl:
                        j = t; e = min(lvl, o[t]); break
        else:
            cb = -1
            for t in range(i + 1, min(i + 4, n)):
                if (side > 0 and c[t] < inv) or (side < 0 and c[t] > inv):
                    break
                if (side > 0 and c[t] > lvl) or (side < 0 and c[t] < lvl):
                    cb = t; break
            if cb < 0 or cb + 1 >= n:
                continue
            if entry == 2:
                j = cb + 1; e = o[j]
            else:
                for t in range(cb + 1, min(cb + 6, n)):
                    if (side > 0 and l[t] <= lvl) or (side < 0 and h[t] >= lvl):
                        j = t; e = min(lvl, o[t]) if side > 0 else max(lvl, o[t]); break
        if j < 0 or j >= n or sw[j]:
            continue
        if stop == 0:
            st = (l[i] - 0.1 * a) if side > 0 else (h[i] + 0.1 * a)
        else:
            st = e - side * 1.5 * a
        R = side * (e - st)
        if not R > 0.2 * a:
            continue
        tgt = e + side * (exitc if exitc > 0 else 3) * R if exitc != 0 else 1e18 * side
        one = e + side * R
        best = e
        half = False
        px = 0.0; t = j; got = False
        first_bar = True
        while t < n:
            if t > j and sw[t]:
                px = c[t - 1]; t -= 1; got = True; break
            ot, ht, lt, ct = o[t], h[t], l[t], c[t]
            if not first_bar or entry != 1:
                if t > j and ((side > 0 and ot <= st) or (side < 0 and ot >= st)):
                    px = ot; got = True; break
            if (side > 0 and lt <= st) or (side < 0 and ht >= st):
                px = st; got = True; break
            if exitc != 0 and t > j - (1 if entry != 1 else 0) and ((side > 0 and ht >= tgt) or (side < 0 and lt <= tgt)):
                if not (first_bar and entry == 1 and False):
                    px = tgt if not (t > j and ((side > 0 and ot >= tgt) or (side < 0 and ot <= tgt))) else ot
                    got = True; break
            if exitc == -1 and not half and ((side > 0 and ht >= one) or (side < 0 and lt <= one)):
                half = True; st = e
            if exitc == 0:
                best = max(best, ht) if side > 0 else min(best, lt)
                ns = best - side * 3.0 * atr[t]
                if (side > 0 and ns > st) or (side < 0 and ns < st):
                    st = ns
            if t - j >= maxh:
                px = ct; got = True; break
            first_bar = False
            t += 1
        if not got:
            px = c[n - 1]; t = n - 1
        g = side * (px - e)
        if exitc == -1 and half:
            g = 0.5 * R + 0.5 * g
        out_i[k] = i; out_j[k] = j; out_g[k] = g / R; out_r[k] = (g - 2 * cost[j]) / R
        k += 1
        busy = t
    return out_i[:k], out_j[:k], out_r[:k], out_g[:k]


def periods(tf):
    if tf == "1d":
        return np.datetime64("2013-01-01"), np.datetime64("2020-01-01")
    return np.datetime64("2024-07-01"), np.datetime64("2025-07-01")


FILTERS = ("ALL", "DTW", "DTA", "ADXL", "ADXH", "VOL")


def filter_masks(f, tf, name, side):
    """Stage-2 context filters evaluated on the setup candle (no look-ahead: daily trend = previous completed day)."""
    n = len(f)
    d = daily_long(name)
    e20 = d.close.ewm(span=20, adjust=False).mean(); e50 = d.close.ewm(span=50, adjust=False).mean()
    dt = np.where((e20 > e50) & (d.close > e50), 1, np.where((e20 < e50) & (d.close < e50), -1, 0))
    day = d.time.dt.normalize().values
    bar_day = pd.to_datetime(f["time"]).dt.normalize().values
    k = np.searchsorted(day, bar_day, side="left") - 1                      # previous completed day
    dtr = np.where(k >= 0, dt[np.clip(k, 0, None)], 0)
    adx = I.adx(f, 14).values if hasattr(I, "adx") else np.full(n, np.nan)
    v = f["volume"].astype(float).values
    va = pd.Series(v).rolling(20).mean().shift(1).values
    return dict(ALL=np.ones(n, bool), DTW=dtr == side, DTA=dtr == -side, ADXL=np.nan_to_num(adx, nan=99) < 20,
                ADXH=np.nan_to_num(adx) > 25, VOL=(va > 0) & (v >= 1.5 * np.nan_to_num(va, nan=np.inf)))


def run_name(args):
    name, rsi_n, only = args[:3]
    st2 = len(args) > 3 and args[3]
    rows = []
    for tf, f in frames(name):
        if only and tf not in only:
            continue
        f = f.reset_index(drop=True)
        if len(f) < 500:
            continue
        o, h, l, c = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
        atr = I.atr(f, 14).values.astype(np.float64)
        sw = f["switch"].fillna(False).values.astype(np.bool_) if "switch" in f else np.zeros(len(f), np.bool_)
        cost = np.array([INS.cost_points(name, p, 1.0) for p in c], np.float64)
        t = pd.to_datetime(f["time"]).values
        p1, p2 = periods(tf)
        maxh = 20 if tf == "1d" else 40
        M = setup_masks(f, rsi_n)
        FM = {s_: filter_masks(f, tf, name, s_) for s_ in (1, -1)} if st2 else None
        for (side, e, L, cn), m0 in M.items():
          for fl in (FILTERS if st2 else ("ALL",)):
            m = m0 & FM[side][fl] if st2 else m0
            idx = np.flatnonzero(m[200:]) + 200
            if len(idx) < 10:
                continue
            for en, stp, ex in product(range(4), range(2), ("2R", "3R", "TR") if st2 else EXITS):
                ii, jj, rr, gg = sim(o, h, l, c, atr, sw, idx.astype(np.int64), side, en, stp, EX_CODE[ex], maxh, cost)
                if not len(rr):
                    continue
                tt = t[ii]
                sp = np.where(tt < p1, 0, np.where(tt < p2, 1, 2))
                for s_ in range(3):
                    x = rr[sp == s_]
                    if len(x):
                        rows.append((name, tf, rsi_n, fl, side, e, L, cn, ENTRIES[en], STOPS[stp], ex, s_, len(x), x.sum(), (x ** 2).sum(),
                                     (x > 0).sum(), x[x > 0].sum(), -x[x <= 0].sum(), gg[sp == s_].sum()))
    return rows


COLS = ["name", "tf", "n_rsi", "filt", "side", "ext", "L", "candle", "entry", "stop", "exit", "split", "n", "s", "ss", "w", "gw", "gl", "gs"]


def aggregate(A, keys):
    g = A.groupby(keys + ["split"])[["n", "s", "ss", "w", "gw", "gl", "gs"]].sum()
    tot = g.groupby(level=list(range(len(keys)))).sum()
    S = pd.DataFrame(dict(n=tot.n, win=tot.w / tot.n * 100, R=tot.s / tot.n, gross=tot.gs / tot.n, PF=tot.gw / tot.gl.replace(0, np.nan)))
    for s_, nm in ((0, "train"), (1, "valid"), (2, "test")):
        x = g.xs(s_, level="split") if s_ in g.index.get_level_values("split") else None
        if x is not None:
            S[f"{nm}_n"] = x.n; S[f"{nm}_R"] = x.s / x.n; S[f"{nm}_win"] = x.w / x.n * 100
            S[f"{nm}_PF"] = x.gw / x.gl.replace(0, np.nan)
    return S


def main():
    stage = (sys.argv[1:] or ["stage1"])[0]
    t0 = time.time()
    st2 = stage == "stage2"
    args = [(n, rp, None, st2) for n in NAMES for rp in ((7, 14, 21) if st2 else (14,))]
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(run_name, args) for r in x]
    A = pd.DataFrame(rows, columns=COLS)
    tag = "rsix2" if st2 else "rsix"
    A.to_csv(OUT / f"{tag}_agg.csv.gz", index=False)
    print(f"[{(time.time() - t0) / 60:.1f} min] rows {len(A):,}")
    K = (["n_rsi", "filt"] if st2 else []) + ["tf", "side", "ext", "L", "candle", "entry", "stop", "exit"]
    S = aggregate(A, K).reset_index()                                    # all commodities pooled per timeframe
    S.to_csv(OUT / f"{tag}_pooled.csv", index=False)
    N = aggregate(A, ["name"] + K).reset_index()
    N.to_csv(OUT / f"{tag}_by_name.csv.gz", index=False)
    print(f"combinations pooled {len(S):,} · per commodity {len(N):,}")


if __name__ == "__main__":
    main()
