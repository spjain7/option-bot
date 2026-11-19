"""Indicators. Every function works on a Series (one stock) or a wide DataFrame (columns = stocks) and uses only data
up to and including bar t (no look-ahead). Wilder smoothing = ewm(alpha=1/n)."""
import numpy as np
import pandas as pd


def _w(x, n):
    return x.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def rsi(c, n=14):
    d = c.diff()
    up, dn = _w(d.clip(lower=0), n), _w((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(h, l, c, n=14):
    pc = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs()))
    return _w(tr, n)


def adx(h, l, c, n=14):
    up, dn = h.diff(), -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    mdm = dn.where((dn > up) & (dn > 0), 0.0)
    a = atr(h, l, c, n)
    pdi, mdi = 100 * _w(pdm, n) / a, 100 * _w(mdm, n) / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return _w(dx, n)


def ema(x, n):
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def macd_hist(c, f=12, s=26, sig=9):
    m = ema(c, f) - ema(c, s)
    return m - ema(m, sig)


def stoch(h, l, c, n=14, k=3):
    lo, hi = l.rolling(n).min(), h.rolling(n).max()
    return (100 * (c - lo) / (hi - lo).replace(0, np.nan)).rolling(k).mean()


def willr(h, l, c, n=14):
    lo, hi = l.rolling(n).min(), h.rolling(n).max()
    return -100 * (hi - c) / (hi - lo).replace(0, np.nan)


def cci(h, l, c, n=20):
    tp = (h + l + c) / 3
    ma = tp.rolling(n).mean()
    md = (tp - ma).abs().rolling(n).mean()
    return (tp - ma) / (0.015 * md.replace(0, np.nan))


def mfi(h, l, c, v, n=14):
    tp = (h + l + c) / 3
    mf = tp * v
    pos = mf.where(tp > tp.shift(1), 0.0).rolling(n).sum()
    neg = mf.where(tp < tp.shift(1), 0.0).rolling(n).sum()
    return 100 - 100 / (1 + pos / neg.replace(0, np.nan))


def obv(c, v):
    return (np.sign(c.diff()).fillna(0) * v).cumsum()


def cmf(h, l, c, v, n=20):
    mfm = ((c - l) - (h - c)) / (h - l).replace(0, np.nan)
    return (mfm * v).rolling(n).sum() / v.rolling(n).sum().replace(0, np.nan)


def rvol(v, n=20):
    """volume / average of the previous n bars (bar t excluded from the average)."""
    return v / v.rolling(n, min_periods=max(5, n // 2)).mean().shift(1)


def clv(h, l, c):
    return (c - l) / (h - l).replace(0, np.nan)


def hammer(o, h, l, c):
    """bullish reversal candle: lower wick >= 2x body, close in the top 40 % of the range."""
    body = (c - o).abs()
    lw = np.minimum(o, c) - l
    return (lw >= 2 * body) & (clv(h, l, c) >= 0.6) & (h > l)


def shooting_star(o, h, l, c):
    body = (c - o).abs()
    uw = h - np.maximum(o, c)
    return (uw >= 2 * body) & (clv(h, l, c) <= 0.4) & (h > l)


def bull_engulf(o, h, l, c):
    return (c > o) & (o.shift(1) > c.shift(1)) & (c >= o.shift(1)) & (o <= c.shift(1))


def bear_engulf(o, h, l, c):
    return (c < o) & (o.shift(1) < c.shift(1)) & (c <= o.shift(1)) & (o >= c.shift(1))


OSC = {   # oscillator families for divergence; GROUP: correlated indicators share a group (counted once)
    "RSI": ("momentum", lambda o, h, l, c, v: rsi(c, 14)),
    "STOCH": ("momentum", lambda o, h, l, c, v: stoch(h, l, c, 14)),
    "WILLR": ("momentum", lambda o, h, l, c, v: willr(h, l, c, 14)),
    "CCI": ("momentum", lambda o, h, l, c, v: cci(h, l, c, 20)),
    "MACDH": ("trend", lambda o, h, l, c, v: macd_hist(c)),
    "MFI": ("volume", lambda o, h, l, c, v: mfi(h, l, c, v, 14)),
    "OBV": ("volume", lambda o, h, l, c, v: obv(c, v)),
    "CMF": ("volume", lambda o, h, l, c, v: cmf(h, l, c, v, 20)),
}
