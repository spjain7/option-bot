"""STRUCTX-001 – structure-based setups with explicit trigger levels (owner directive 6-Nov "Stop endless testing").

PRE-REGISTERED HYPOTHESES (written before running):
 H1  Entry mechanism. Problem: validated 2h/4h BUY rules enter at the next open after a close-confirmed signal, often late.
     Different: same signals, entry = stop above the signal candle's high (cancel if its low breaks) vs next open vs
     close-confirmed break vs retest. Promotion: stop-entry beats next-open on the SAME signals in all 3 periods.
 H2  V-reversal = market-structure shift (MSS), not an oscillator. Why RSI failed: RSI extremes fire all through a decline
     (falling knife); a reversal is only real when price stops making lower lows AND takes out the last lower high.
     Setup: >= 4 ATR decline into a 15-candle low, a higher low, BUY-STOP above the last swing high before the low,
     stop under the low (structure) or 1.5 ATR. Lifecycle: early warning (new low after the decline) -> confirmed (higher low,
     trigger known) -> actionable (trigger traded) -> invalidated (low broken / 6 candles).
 H3-H6 MCX SELL by structure, not momentum oscillators. Why SELL failed: commodity drift is up and down-moves are fast and
     mean-reverting at the start, so selling a crossover or an oversold close sells into the bounce.
     A failed recovery after a 20-candle support break (lower high, bearish rejection) – sell below the rejection low.
     B retest of the broken support from below with rejection – sell below the rejection low.
     C momentum breakdown candle (body >= 1.5 ATR, close in the bottom 20 %, close < 20-candle low, volume >= 1.5x).
     D trend continuation: daily trend down, pull-back to EMA20 with a lower high, bearish candle – sell below its low.
 Promotion bar (all): positive in all three periods, Benjamini-Hochberg q < 0.10 over EVERY combination run here,
 n >= 60, >= 4 of 7 commodities positive, after 2x costs.
Grid per setup: filter {none, with daily trend, against} x entry {MKT, STOP, CLOSE-BRK, RETEST} x stop {structure, 1.5 ATR}
x exit {2R, 3R, 3-ATR trail}. 1d 2006-26 (periods 2006-12 / 13-19 / 20-26), 4h + 2h 2022-26 (to 2024-07 / 2025-07 / later).
python research/program/structx.py"""
import sys
import time
from itertools import product
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit
from scipy import stats
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import rsix as RX  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
TFS = ("2h", "4h", "1d")
ENTRIES = ("MKT", "STOP", "CBRK", "RET")
STOPS = ("STR", "ATR")
EXITS = {"2R": 2, "3R": 3, "TR": 0}
FILTS = ("none", "with", "against")


@njit(cache=True)
def sim(o, h, l, c, atr, sw, idx, lvl, inv, side, entry, stop, exitc, maxh, win, cost, km=1.5):
    """Setup i with trigger level lvl[k] and invalidation inv[k]. entry 0 next open, 1 stop at lvl within `win` candles
    (cancel if inv breaks first), 2 close beyond lvl then next open, 3 after 2, limit back at lvl within 5 candles.
    stop 0 structure (inv -/+ 0.1 ATR, risk 0.2-3 ATR), 1 = 1.5 ATR. exitc 2/3 R target, 0 3-ATR trail. -> (i, R net, gross)"""
    n = len(c)
    oi = np.empty(len(idx), np.int64); orr = np.empty(len(idx)); og = np.empty(len(idx))
    k = 0; busy = -1
    for q in range(len(idx)):
        i = idx[q]
        if i <= busy or i + 2 >= n or not atr[i] > 0:
            continue
        a = atr[i]; L = lvl[q]; V = inv[q]
        j = -1; e = 0.0
        if entry == 0:
            j = i + 1; e = o[j]
        elif entry == 1:
            for t in range(i + 1, min(i + 1 + win, n)):
                if sw[t]:
                    break
                if side > 0:
                    if o[t] < V or (l[t] < V and not h[t] > L):
                        break
                    if h[t] > L:
                        j = t; e = max(L, o[t]); break
                else:
                    if o[t] > V or (h[t] > V and not l[t] < L):
                        break
                    if l[t] < L:
                        j = t; e = min(L, o[t]); break
        else:
            cb = -1
            for t in range(i + 1, min(i + 1 + win, n)):
                if (side > 0 and c[t] < V) or (side < 0 and c[t] > V):
                    break
                if (side > 0 and c[t] > L) or (side < 0 and c[t] < L):
                    cb = t; break
            if cb < 0 or cb + 1 >= n:
                continue
            if entry == 2:
                j = cb + 1; e = o[j]
            else:
                for t in range(cb + 1, min(cb + 6, n)):
                    if (side > 0 and l[t] <= L) or (side < 0 and h[t] >= L):
                        j = t; e = min(L, o[t]) if side > 0 else max(L, o[t]); break
        if j < 0 or j >= n or sw[j]:
            continue
        if side * (e - L) > 0.5 * a and entry != 0:                      # never chase > 0.5 ATR beyond the trigger
            continue
        st = (V - side * 0.1 * a) if stop == 0 else (e - side * km * a)
        R = side * (e - st)
        if not (R > 0.2 * a and R < max(3.0, km + 0.01) * a):
            continue
        tgt = e + side * exitc * R if exitc > 0 else 1e18 * side
        best = e; px = 0.0; t = j; got = False
        while t < n:
            if t > j and sw[t]:
                px = c[t - 1]; t -= 1; got = True; break
            if t > j and ((side > 0 and o[t] <= st) or (side < 0 and o[t] >= st)):
                px = o[t]; got = True; break
            if (side > 0 and l[t] <= st) or (side < 0 and h[t] >= st):
                px = st; got = True; break
            if exitc > 0 and (t > j or entry != 1) and ((side > 0 and h[t] >= tgt) or (side < 0 and l[t] <= tgt)):
                px = tgt if not (t > j and ((side > 0 and o[t] >= tgt) or (side < 0 and o[t] <= tgt))) else o[t]
                got = True; break
            if exitc == 0:
                best = max(best, h[t]) if side > 0 else min(best, l[t])
                ns = best - side * 3.0 * atr[t]
                if (side > 0 and ns > st) or (side < 0 and ns < st):
                    st = ns
            if t - j >= maxh:
                px = c[t]; got = True; break
            t += 1
        if not got:
            px = c[n - 1]; t = n - 1
        g = side * (px - e)
        oi[k] = i; orr[k] = (g - 2 * cost[j]) / R; og[k] = g / R; k += 1
        busy = t
    return oi[:k], orr[:k], og[:k]


def dtrend(f, name, tf):
    if tf == "1d":                                             # daily candles: own EMA20/50 state of the previous day
        c = f.close; e20, e50 = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
        t = np.where((e20 > e50) & (c > e50), 1, np.where((e20 < e50) & (c < e50), -1, 0))
        return np.r_[0, t[:-1]]
    d = RX.daily_long(name)
    e20, e50 = d.close.ewm(span=20, adjust=False).mean(), d.close.ewm(span=50, adjust=False).mean()
    t = np.where((e20 > e50) & (d.close > e50), 1, np.where((e20 < e50) & (d.close < e50), -1, 0))
    k = np.searchsorted(d.time.dt.normalize().values, pd.to_datetime(f.time).dt.normalize().values, side="left") - 1
    return np.where(k >= 0, t[np.clip(k, 0, None)], 0)


def setups(f, tf):
    """-> {setup: (side, idx, lvl, inv)}"""
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    v = f.volume.astype(float).values
    a = I.atr(f, 14).values
    n = len(c)
    rng = np.where(h - l > 0, h - l, np.nan); pos = (c - l) / rng; body = np.abs(c - o)
    uw = h - np.maximum(o, c); lw = np.minimum(o, c) - l
    ll20 = pd.Series(l).shift(1).rolling(20).min().values; hh20 = pd.Series(h).shift(1).rolling(20).max().values
    volx = v / pd.Series(v).rolling(20).mean().shift(1).values
    e20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
    bear = (c < o) & (pos <= 0.4) | ((uw >= 0.5 * rng) & (pos <= 0.5))
    out = {}
    # ── BUY: existing validated rule families, signal candle high = trigger (H1)
    cs = pd.Series(c)
    def xup(x, y):
        return (x > y) & (np.r_[np.nan, x[:-1]] <= np.r_[np.nan, y[:-1]])
    e13, e48 = cs.ewm(span=13, adjust=False).mean().values, cs.ewm(span=48, adjust=False).mean().values
    e9, e21 = cs.ewm(span=9, adjust=False).mean().values, cs.ewm(span=21, adjust=False).mean().values
    macd = cs.ewm(span=12, adjust=False).mean().values - cs.ewm(span=26, adjust=False).mean().values
    fam = {"B_EMA1348": xup(e13, e48), "B_EMA921": xup(e9, e21), "B_MACD0": xup(macd, np.zeros(n)),
           "B_MOMO": (body >= 1.5 * a) & (c > o) & (pos >= 0.8)}
    for k_, m in fam.items():
        idx = np.flatnonzero(np.nan_to_num(m.astype(float)).astype(bool) & (np.arange(n) >= 200))
        out[k_] = (1, idx, h[idx], l[idx])
    # ── BUY: market-structure shift after a >= 4 ATR decline (H2)
    I_, Lv, Iv = [], [], []
    last_m = -1
    for i in range(220, n):
        w0 = i - 14
        m = w0 + int(np.argmin(l[w0:i + 1]))
        if m == last_m or not (2 <= i - m <= 8) or not a[i] > 0:
            continue
        pre = h[max(0, m - 20):m]
        if len(pre) < 5 or pre.max() - l[m] < 4 * a[m]:
            continue
        sh = h[max(0, m - 5):m].max()                           # last swing high before the low = structure trigger
        if l[i] > l[m] and c[i] < sh and c[i] > o[i]:           # higher low formed, bullish candle, trigger not yet taken
            I_.append(i); Lv.append(sh); Iv.append(l[m]); last_m = m
    out["B_MSS"] = (1, np.array(I_, np.int64), np.array(Lv), np.array(Iv))
    # ── SELL A failed recovery / B retest (H3, H4): find the latest 20-candle support break within 15 candles
    brk = np.flatnonzero((c < ll20))
    A_, B_ = ([], [], []), ([], [], [])
    for i in range(220, n):
        if not bear[i] or not a[i] > 0:
            continue
        p = np.searchsorted(brk, i) - 1
        if p < 0:
            continue
        b = brk[p]
        # the break must be the first close below the level after >= 3 candles above it (a genuine breakdown)
        while p > 0 and brk[p - 1] >= b - 1:
            p -= 1; b = brk[p]
        age = i - b
        lvl = ll20[b]
        if not (2 <= age <= 15) or c[i] >= lvl:
            continue
        lo_since = l[b:i + 1].min(); hi_since = h[b + 1:i + 1].max() if i > b else h[i]
        if age >= 3 and hi_since - lo_since >= 1.0 * a[i] and h[i] >= h[i - 2:i].max() and h[i] < lvl + 0.5 * a[i]:
            A_[0].append(i); A_[1].append(l[i]); A_[2].append(max(h[i], h[i - 1]))
        if h[i] >= lvl - 0.3 * a[i] and h[i] <= lvl + 0.7 * a[i]:
            B_[0].append(i); B_[1].append(l[i]); B_[2].append(h[i])
    out["S_A_FAILREC"] = (-1, np.array(A_[0], np.int64), np.array(A_[1]), np.array(A_[2]))
    out["S_B_RETEST"] = (-1, np.array(B_[0], np.int64), np.array(B_[1]), np.array(B_[2]))
    # ── SELL C momentum breakdown (H5)
    m = (body >= 1.5 * a) & (c < o) & (pos <= 0.2) & (c < ll20) & (np.nan_to_num(volx) >= 1.5)
    idx = np.flatnonzero(m & (np.arange(n) >= 220))
    out["S_C_MOMO"] = (-1, idx, l[idx], h[idx])
    # ── SELL D pull-back continuation with a lower high (H6) – the daily-trend condition is the 'with' filter
    hh10 = pd.Series(h).shift(3).rolling(10).max().values
    m = (pd.Series(h >= e20).rolling(3).max().values == 1) & (c < e20) & bear & (h < hh10)
    idx = np.flatnonzero(np.nan_to_num(m.astype(float)).astype(bool) & (np.arange(n) >= 220))
    out["S_D_PBCONT"] = (-1, idx, l[idx], np.maximum(h[idx], pd.Series(h).rolling(3).max().values[idx]))
    return out


def run_name(name):
    rows = []
    for tf, f in RX.frames(name):
        if tf not in TFS:
            continue
        f = f.reset_index(drop=True)
        o, h, l, c = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
        atr = I.atr(f, 14).values.astype(np.float64)
        sw = f["switch"].fillna(False).values.astype(np.bool_) if "switch" in f else np.zeros(len(f), np.bool_)
        cost = np.array([INS.cost_points(name, p, 1.0) for p in c], np.float64)
        t = pd.to_datetime(f.time).values
        p1, p2 = (np.datetime64("2013-01-01"), np.datetime64("2020-01-01")) if tf == "1d" else (np.datetime64("2024-07-01"), np.datetime64("2025-07-01"))
        maxh, win = (20, 3) if tf == "1d" else (40, 6)
        dt = dtrend(f, name, tf)
        for su, (side, idx, lv, iv) in setups(f, tf).items():
            for fl in FILTS:
                keep = np.ones(len(idx), bool) if fl == "none" else (dt[idx] == side if fl == "with" else dt[idx] == -side)
                ii, L, V = idx[keep].astype(np.int64), np.asarray(lv, float)[keep], np.asarray(iv, float)[keep]
                if len(ii) < 5:
                    continue
                for en, sp, ex in product(range(4), range(2), EXITS):
                    oi, rr, gg = sim(o, h, l, c, atr, sw, ii, L, V, side, en, sp, EXITS[ex], maxh, win, cost)
                    sp_ = np.where(t[oi] < p1, 0, np.where(t[oi] < p2, 1, 2))
                    for s_ in range(3):
                        x = rr[sp_ == s_]
                        if len(x):
                            rows.append((name, tf, su, fl, ENTRIES[en], STOPS[sp], ex, s_, len(x), x.sum(), (x ** 2).sum(),
                                         (x > 0).sum(), x[x > 0].sum(), -x[x <= 0].sum()))
    return rows


COLS = ["name", "tf", "setup", "filt", "entry", "stop", "exit", "split", "n", "s", "ss", "w", "gw", "gl"]


def summarise(A):
    K = ["tf", "setup", "filt", "entry", "stop", "exit"]
    g = A.groupby(K + ["split"])[["n", "s", "ss", "w", "gw", "gl"]].sum()
    tot = g.groupby(level=list(range(len(K)))).sum()
    S = pd.DataFrame(dict(n=tot.n, win=100 * tot.w / tot.n, R=tot.s / tot.n, PF=tot.gw / tot.gl.replace(0, np.nan)))
    sd = np.sqrt(np.maximum(tot.ss / tot.n - S.R ** 2, 1e-9))
    S["t"] = S.R / (sd / np.sqrt(tot.n)); S["p"] = stats.t.sf(S.t, np.maximum(tot.n - 1, 1))
    for s_, nm in ((0, "p1"), (1, "p2"), (2, "p3")):
        x = g.xs(s_, level="split")
        S[f"{nm}_n"] = x.n; S[f"{nm}_R"] = x.s / x.n
    S = S.reset_index()
    nm = A.groupby(K + ["name"])[["n", "s"]].sum().reset_index()
    nm = nm.assign(pos=nm.s > 0).groupby(K).pos.sum().rename("names_pos").reset_index()
    S = S.merge(nm, on=K, how="left")
    S = S.sort_values("p").reset_index(drop=True)
    m = len(S); S["q"] = (S.p * m / (np.arange(m) + 1))[::-1].cummin()[::-1].clip(upper=1)
    S["all3"] = (S.p1_R > 0) & (S.p2_R > 0) & (S.p3_R > 0)
    S["PASS"] = S.all3 & (S.q < 0.10) & (S.n >= 60) & (S.names_pos >= 4)
    return S


def main():
    t0 = time.time()
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(run_name, RX.NAMES) for r in x]
    A = pd.DataFrame(rows, columns=COLS)
    A.to_csv(OUT / "structx_agg.csv.gz", index=False)
    S = summarise(A)
    S.to_csv(OUT / "structx_summary.csv", index=False)
    print(f"[{(time.time() - t0) / 60:.1f} min] combinations {len(S)} · PASS {int(S.PASS.sum())}")


if __name__ == "__main__":
    main()
