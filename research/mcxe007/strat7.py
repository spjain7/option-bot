"""MCXE-007 daily signal functions (causal: everything at bar i uses bars <= i). fn(f, side, extra, **p) ->
dict(sig=bool array, level=price array (stop-entry level / reference level for the no-chase rule), stop=price array
(structural stop, nan = ATR stop), warm=int, entry='open'|'stop')."""
import numpy as np
import pandas as pd
from crude import indicators as I


def _ema(c, n):
    return c.ewm(span=n, adjust=False).mean()


def _px(f):
    return (f[x].astype(float) for x in ("open", "high", "low", "close", "volume"))


def filters(f, side, filt, extra):
    o, h, l, c, v = _px(f)
    n = len(f); ok = np.ones(n, bool)
    for fl in filt:
        if fl == "ema":
            e20, e50 = _ema(c, 20), _ema(c, 50)
            ok &= (((e20 > e50) & (c > e20)) if side > 0 else ((e20 < e50) & (c < e20))).values
        elif fl == "adx":
            ok &= I.adx(f, 14).values >= 20
        elif fl == "hhhl":                                      # structure: last 10 bars vs the 10 before
            h1, h0 = h.rolling(10).max(), h.shift(10).rolling(10).max()
            l1, l0 = l.rolling(10).min(), l.shift(10).rolling(10).min()
            ok &= (((h1 > h0) & (l1 > l0)) if side > 0 else ((h1 < h0) & (l1 < l0))).fillna(False).values
        elif fl in ("mkt", "rs"):
            N = extra["nifty"]
            d = f.time.dt.normalize()
            if fl == "mkt":
                ok &= (d.map(N.trend).values == side)
            else:
                r = (c / c.shift(20) - 1).values - d.map(N.ret20).values.astype(float)
                ok &= np.nan_to_num(r * side, nan=-1) > 0
        elif fl == "vol":
            ok &= (v > 1.5 * v.rolling(20).mean().shift(1)).fillna(False).values
        elif fl in ("oi_up", "oi_dn"):
            doi = f["doi"].values.astype(float) if "doi" in f else np.full(n, np.nan)
            ok &= (doi > 0) if fl == "oi_up" else (doi < 0)
        elif fl in ("nr7_prev", "inside_prev", "atrc_prev"):
            rng = h - l
            if fl == "nr7_prev":
                x = (rng <= rng.rolling(7).min())
            elif fl == "inside_prev":
                x = (h <= h.shift(1)) & (l >= l.shift(1))
            else:
                x = (I.atr(f, 5) / I.atr(f, 20)) < 0.75
            x = x.shift(1).rolling(3).max().fillna(0).astype(bool)        # compression within the 3 bars before
            ok &= x.values
        else:
            raise ValueError(fl)
    return ok


def dc(f, side, n=20, buf=0.0, mode="close", filt=(), swing=0, chase=0.0, extra=None):
    """Donchian breakout (side +1) / breakdown (side -1). mode close: first close beyond the prior n-bar extreme (+/- buf
    ATR), entry next open. mode breach: stop order at the n-bar extreme (+/- buf ATR) for the next session while price
    is still inside the range."""
    o, h, l, c, v = _px(f)
    a = f.atr
    if side > 0:
        lvl_prev = h.shift(1).rolling(n).max() + buf * a.shift(1)
        lvl_now = h.rolling(n).max() + buf * a
    else:
        lvl_prev = l.shift(1).rolling(n).min() - buf * a.shift(1)
        lvl_now = l.rolling(n).min() - buf * a
    if mode == "close":
        x = (side * (c - lvl_prev) > 0) & (side * (c.shift(1) - lvl_prev.shift(1)) <= 0)
        sig, level, entry = x.fillna(False).values.copy(), lvl_prev.values, "open"
    else:
        sig = (side * (c - lvl_now) < 0).fillna(False).values.copy()
        level, entry = lvl_now.values, "stop"
    sig &= filters(f, side, filt, extra)
    stop = np.full(len(f), np.nan)
    if swing:
        stop = (l.rolling(swing).min() - 0.1 * a).values if side > 0 else (h.rolling(swing).max() + 0.1 * a).values
    return dict(sig=sig, level=level, stop=stop, warm=max(n, 20) + 15, entry=entry, chase=chase)


def compress_brk(f, side, pat="nr7", filt=(), extra=None, struct_stop=False):
    """volatility contraction bar at i (NR7 / NR4 / inside day / ATR5<0.75 ATR20) -> stop order beyond that bar's
    high (BUY) / low (SELL) for the next session."""
    o, h, l, c, v = _px(f)
    rng = h - l
    if pat == "nr7":
        x = rng <= rng.rolling(7).min()
    elif pat == "nr4":
        x = rng <= rng.rolling(4).min()
    elif pat == "inside":
        x = (h <= h.shift(1)) & (l >= l.shift(1))
    else:
        x = (I.atr(f, 5) / I.atr(f, 20)) < 0.75
        x = x & (rng <= rng.rolling(5).min())
    sig = x.fillna(False).values.copy() & filters(f, side, filt, extra)
    level = h.values if side > 0 else l.values
    stop = (l.values if side > 0 else h.values) if struct_stop else np.full(len(f), np.nan)
    return dict(sig=sig, level=level, stop=stop, warm=35, entry="stop")


def retest(f, side, n=20, within=5, filt=(), extra=None):
    """breakout close beyond the n-bar level, then within `within` bars price returns to the level (low <= level +
    0.25 ATR for BUY) and closes back beyond it -> entry next open. One entry per breakout."""
    o, h, l, c, v = _px(f)
    a = f.atr
    lvl = h.shift(1).rolling(n).max() if side > 0 else l.shift(1).rolling(n).min()
    bo = pd.Series(((side * (c - lvl) > 0) & (side * (c.shift(1) - lvl.shift(1)) <= 0)).fillna(False).values)
    L = lvl.where(bo).ffill(limit=within)
    recent = bo.shift(1).rolling(within, min_periods=1).max().fillna(0).astype(bool)
    if side > 0:
        x = recent & (l <= L + 0.25 * a) & (c > L) & (c > o)
    else:
        x = recent & (h >= L - 0.25 * a) & (c < L) & (c < o)
    x = x.fillna(False).values
    out = x.copy(); last = -999
    for i in np.flatnonzero(x):
        if i - last <= within:
            out[i] = False
        else:
            last = i
    out &= filters(f, side, filt, extra)
    return dict(sig=out, level=L.values, warm=n + 15, entry="open")


def failed(f, side, n=20, within=3, filt=(), extra=None):
    """failed breakdown -> BUY (side +1): a close below the prior n-bar low, then within `within` bars a close back above
    that level. Failed breakout -> SELL (side -1) mirror."""
    o, h, l, c, v = _px(f)
    lvl = l.shift(1).rolling(n).min() if side > 0 else h.shift(1).rolling(n).max()
    brk = pd.Series(((-side * (c - lvl) > 0) & (-side * (c.shift(1) - lvl.shift(1)) <= 0)).fillna(False).values)
    L = lvl.where(brk).ffill(limit=within)
    recent = brk.shift(1).rolling(within, min_periods=1).max().fillna(0).astype(bool)
    x = (recent & (side * (c - L) > 0) & (side * (c.shift(1) - L) <= 0)).fillna(False).values.copy()
    x &= filters(f, side, filt, extra)
    return dict(sig=x, level=L.values, warm=n + 15, entry="open")


def gap_brk(f, side, n=20, gap=0.25, filt=(), extra=None):
    """breakaway gap (MCXE-008 N3): the session opens beyond the prior n-bar extreme by >= gap x ATR and closes beyond
    its own open (the gap holds) -> entry next open."""
    o, h, l, c, v = _px(f)
    a = f.atr.shift(1)
    if side > 0:
        lvl = h.shift(1).rolling(n).max(); x = (o >= lvl + gap * a) & (c > o)
    else:
        lvl = l.shift(1).rolling(n).min(); x = (o <= lvl - gap * a) & (c < o)
    sig = x.fillna(False).values.copy() & filters(f, side, filt, extra)
    return dict(sig=sig, level=lvl.values, warm=n + 15, entry="open")


REG = {"gap_brk": gap_brk, "dc": dc, "compress_brk": compress_brk, "retest": retest, "failed": failed}
