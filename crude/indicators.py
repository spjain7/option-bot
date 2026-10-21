"""Indicators on completed candles only (callers pass closed candles). Wilder smoothing for RSI/ATR/ADX."""
import numpy as np
import pandas as pd


def ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn
    out = 100 - 100 / (1 + rs)
    out[(dn == 0) & (up > 0)] = 100.0
    out[(dn == 0) & (up == 0)] = 50.0
    return out


def true_range(df):
    pc = df["close"].shift(1)
    return pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)


def atr(df, n=14):
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def adx(df, n=14):
    up = df["high"].diff(); dn = -df["low"].diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / tr
    mdi = 100 * mdm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def slot_volume_ratio(df, slots=10, min_slots=5):
    """Volume vs the average volume of the SAME time-of-day candle over the previous `slots` sessions.
    MCX volume has a strong intraday pattern (the US-hours evening is far busier), so a plain rolling mean would
    flag every evening candle as 'high volume'. Returns (ratio, n_used); ratio is NaN when < min_slots comparables."""
    key = df["time"].dt.strftime("%H:%M")
    vol = df["volume"].astype(float).where(df["volume"] > 0)
    prev = vol.groupby(key).transform(lambda s: s.shift(1).rolling(slots, min_periods=1).mean())
    n = vol.groupby(key).transform(lambda s: s.shift(1).rolling(slots, min_periods=1).count())
    ratio = (vol / prev).where(n >= min_slots)
    return ratio, n


def pivots(df, k=2):
    """Confirmed swing highs/lows: a pivot at i is known only at i+k (no look-ahead). Returns lists of (i, price)."""
    h, l = df["high"].values, df["low"].values
    hi, lo = [], []
    for i in range(k, len(df) - k):
        if h[i] == max(h[i - k:i + k + 1]) and h[i] > max(h[i - k:i]):
            hi.append((i, h[i]))
        if l[i] == min(l[i - k:i + k + 1]) and l[i] < min(l[i - k:i]):
            lo.append((i, l[i]))
    return hi, lo
