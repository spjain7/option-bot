"""Causal indicators, pivots, divergences, candles and levels. Every value at bar t uses bars <= t only.
Pivot lows / highs: bar p is a pivot if it is the extreme of [p-L, p+R]; it becomes KNOWN at bar p+R (detection delay R bars).
All price inputs are the back-adjusted series (a_open ...); volume is the raw traded volume."""
import numpy as np
import pandas as pd
from numba import njit


@njit(cache=True)
def wilder(x, n):
    out = np.full(len(x), np.nan); s = np.nan; k = 0; acc = 0.0
    for i in range(len(x)):
        v = x[i]
        if np.isnan(v):
            out[i] = s; continue
        if k < n:
            acc += v; k += 1
            if k == n:
                s = acc / n
        else:
            s = (s * (n - 1) + v) / n
        out[i] = s
    return out


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False, min_periods=n).mean().to_numpy(copy=True)


def sma(x, n):
    return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy(copy=True)


def atr(h, l, c, n=14):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    return wilder(tr, n)


def rsi(c, n=14):
    d = np.diff(c, prepend=np.nan)
    up = wilder(np.where(d > 0, d, 0.0), n); dn = wilder(np.where(d < 0, -d, 0.0), n)
    r = np.where(dn > 0, 100 - 100 / (1 + up / np.where(dn > 0, dn, 1.0)), 100.0)
    r[np.isnan(up)] = np.nan
    return r


def macd(c):
    m = ema(c, 12) - ema(c, 26); s = ema(np.nan_to_num(m, nan=0.0), 9); s[np.isnan(m)] = np.nan
    return m, m - s


def stoch(h, l, c, n=14, k=3):
    lo = pd.Series(l).rolling(n).min().values; hi = pd.Series(h).rolling(n).max().values
    raw = 100 * (c - lo) / np.where(hi - lo > 0, hi - lo, np.nan)
    return sma(raw, k)


def stochrsi(r, n=14, k=3):
    s = pd.Series(r); lo = s.rolling(n).min().values; hi = s.rolling(n).max().values
    return sma(100 * (r - lo) / np.where(hi - lo > 0, hi - lo, np.nan), k)


def cci(h, l, c, n=20):
    tp = (h + l + c) / 3; m = pd.Series(tp).rolling(n).mean()
    md = pd.Series(tp).rolling(n).apply(lambda z: np.mean(np.abs(z - z.mean())), raw=True)
    return ((tp - m) / (0.015 * md.replace(0, np.nan))).values


def mfi(h, l, c, v, n=14):
    tp = (h + l + c) / 3; mf = tp * v; d = np.diff(tp, prepend=np.nan)
    pos = pd.Series(np.where(d > 0, mf, 0.0)).rolling(n).sum().values; neg = pd.Series(np.where(d < 0, mf, 0.0)).rolling(n).sum().values
    return np.where(neg > 0, 100 - 100 / (1 + pos / np.where(neg > 0, neg, 1.0)), 100.0)


def obv(c, v):
    return np.cumsum(np.sign(np.nan_to_num(np.diff(c, prepend=np.nan))) * v)


def willr(h, l, c, n=14):
    lo = pd.Series(l).rolling(n).min().values; hi = pd.Series(h).rolling(n).max().values
    return -100 * (hi - c) / np.where(hi - lo > 0, hi - lo, np.nan)


def lag(x, k):
    x = np.asarray(x, float)
    return np.r_[np.full(k, np.nan), x[:-k]] if k > 0 else x


@njit(cache=True)
def pivots(lo, hi, L, R):
    """pl[p] / ph[p] True if p is a pivot low / high over [p-L, p+R] (uses future bars: only usable from bar p+R)."""
    n = len(lo); pl = np.zeros(n, np.bool_); ph = np.zeros(n, np.bool_)
    for p in range(L, n - R):
        a = lo[p]; b = hi[p]; okl = True; okh = True
        for j in range(p - L, p + R + 1):
            if j == p:
                continue
            if lo[j] < a or (j < p and lo[j] == a):
                okl = False
            if hi[j] > b or (j < p and hi[j] == b):
                okh = False
        pl[p] = okl; ph[p] = okh
    return pl, ph


@njit(cache=True)
def known_levels(piv, price, R, depth):
    """for each bar t, the prices of the last `depth` pivots KNOWN at t (pivot p known from p+R), most recent first,
    and their bar indices. Shape (n, depth)."""
    n = len(piv); lv = np.full((n, depth), np.nan); ix = np.full((n, depth), -1, np.int64)
    buf = np.full(depth, np.nan); bix = np.full(depth, -1, np.int64)
    for t in range(n):
        p = t - R
        if p >= 0 and piv[p]:
            for k in range(depth - 1, 0, -1):
                buf[k] = buf[k - 1]; bix[k] = bix[k - 1]
            buf[0] = price[p]; bix[0] = p
        for k in range(depth):
            lv[t, k] = buf[k]; ix[t, k] = bix[k]
    return lv, ix


@njit(cache=True)
def divergence(lo, ind, pl, R, minlb, maxlb, hidden):
    """bullish divergence known at t = p2 + R, where p2 is a pivot low and p1 the previous pivot low in [p2-maxlb, p2-minlb].
    regular: lo[p2] < lo[p1] and ind[p2] > ind[p1].  hidden: lo[p2] > lo[p1] and ind[p2] < ind[p1].
    returns signal (at t) and p2 index (for the stop)."""
    n = len(lo); sig = np.zeros(n, np.bool_); p2x = np.full(n, -1, np.int64)
    last = -1
    for p in range(n):
        if not pl[p]:
            continue
        if last >= 0 and minlb <= p - last <= maxlb and not np.isnan(ind[p]) and not np.isnan(ind[last]):
            if hidden:
                ok = lo[p] > lo[last] and ind[p] < ind[last]
            else:
                ok = lo[p] < lo[last] and ind[p] > ind[last]
            t = p + R
            if ok and t < n:
                sig[t] = True; p2x[t] = p
        last = p
    return sig, p2x


def first(x):
    """True only on the first bar of each run of True."""
    x = np.asarray(x, bool)
    return x & ~np.r_[False, x[:-1]]


def cross_up(x, lvl):
    x = np.asarray(x, float)
    return (x > lvl) & (lag(x, 1) <= lvl)


def run_len(x):
    x = np.asarray(x, bool); out = np.zeros(len(x), np.int64); k = 0
    for i, v in enumerate(x):
        k = k + 1 if v else 0; out[i] = k
    return out
