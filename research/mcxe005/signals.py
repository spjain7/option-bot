"""MCXE-005 signal families (A trend / momentum, B breakout, C reversal, D patterns) and filters (E), all causal: the
value at bar i uses bars <= i only (indicators: pandas ewm / rolling on past values; patterns: MCXE-003 detectors, which
pass the no-look-ahead prefix test). Every function returns (buy, sell) boolean arrays aligned with the frame.
families(f) -> dict name -> (buy, sell)        filters(f, daily_trend) -> dict name -> (buy_ok, sell_ok)"""
import numpy as np
import pandas as pd
from crude import indicators as I
from research.mcxe003 import (swing_detection as SWD, candlestick_patterns as CDL, chart_patterns as CP,  # noqa: E402
                              trendlines as TL)


def _xup(a, b):
    a, b = pd.Series(a), pd.Series(b)
    return ((a > b) & (a.shift(1) <= b.shift(1))).fillna(False).values


def supertrend(f, n=10, m=3.0):
    h, l, c = f.high.values, f.low.values, f.close.values
    a = I.atr(f, n).values
    mid = (h + l) / 2
    ub, lb = mid + m * a, mid - m * a
    fu, fl = ub.copy(), lb.copy()
    d = np.ones(len(c))
    for i in range(1, len(c)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        d[i] = 1 if c[i] > fu[i - 1] else (-1 if c[i] < fl[i - 1] else d[i - 1])
        if not np.isfinite(a[i]):
            d[i] = d[i - 1]
    return d


def _events_to_bool(E, n, name_prefix):
    b = np.zeros(n, bool); s = np.zeros(n, bool)
    x = E[E.name.str.startswith(name_prefix)] if len(E) else E
    for i, sd in zip(x.i.values, x.side.values):
        if sd > 0:
            b[i] = True
        else:
            s[i] = True
    return b, s


def families(f):
    o, h, l, c, v = (f[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
    a = f.atr
    n = len(f)
    F = {}
    e9, e21, e20, e50 = (c.ewm(span=k, adjust=False).mean() for k in (9, 21, 20, 50))
    F["A_EMA9_21"] = (_xup(e9, e21), _xup(e21, e9))
    F["A_EMA20_50"] = (_xup(e20, e50), _xup(e50, e20))
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean(); sig = macd.ewm(span=9, adjust=False).mean()
    F["A_MACD_SIG"] = (_xup(macd, sig), _xup(sig, macd))
    F["A_MACD_ZERO"] = (_xup(macd, 0 * macd), _xup(0 * macd, macd))
    rsi = I.rsi(c, 14)
    F["A_RSI50"] = (_xup(rsi, 0 * rsi + 50), _xup(0 * rsi + 50, rsi))
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0)); ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0))
    tr = I.true_range(f).ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean().values / tr.values
    ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False).mean().values / tr.values
    adx = I.adx(f, 14).values
    F["A_DMI_ADX20"] = (_xup(pdi, ndi) & (adx >= 20), _xup(ndi, pdi) & (adx >= 20))
    st = supertrend(f)
    F["A_SUPERTREND"] = ((st == 1) & (np.r_[1, st[:-1]] == -1), (st == -1) & (np.r_[-1, st[:-1]] == 1))
    sl = e50 - e50.shift(5)
    F["A_EMA50_SLOPE"] = (_xup(sl, 0 * sl), _xup(0 * sl, sl))
    hh20, ll20 = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
    va = v.rolling(20).mean().shift(1)
    F["B_BO20"] = (_xup(c, hh20), _xup(ll20, c))
    F["B_BO20_VOL"] = (_xup(c, hh20) & (v > 1.5 * va).values, _xup(ll20, c) & (v > 1.5 * va).values)
    F["B_ATR_BO"] = ((c >= c.shift(1) + a.shift(1)).values, (c <= c.shift(1) - a.shift(1)).values)
    rng = h - l
    F["B_RANGE_EXP"] = (((rng >= 2 * a.shift(1)) & ((c - l) >= 0.75 * rng)).values, ((rng >= 2 * a.shift(1)) & ((h - c) >= 0.75 * rng)).values)
    # failed 20-bar breakout: a close back inside within 3 bars of a breakout close -> fade
    bo_up = pd.Series(_xup(c, hh20)); bo_dn = pd.Series(_xup(ll20, c))
    lvl_up = hh20.where(bo_up).ffill(limit=3); lvl_dn = ll20.where(bo_dn).ffill(limit=3)
    rec_up = bo_up.rolling(4, min_periods=1).max().shift(1).fillna(0).astype(bool)
    rec_dn = bo_dn.rolling(4, min_periods=1).max().shift(1).fillna(0).astype(bool)
    F["B_FAIL_BO"] = ((rec_dn & (c > lvl_dn)).values & (c.shift(1) <= lvl_dn).values,
                      (rec_up & (c < lvl_up)).values & (c.shift(1) >= lvl_up).values)
    F["C_RSI_REV"] = (_xup(rsi, 0 * rsi + 30), _xup(0 * rsi + 70, rsi))
    # RSI divergence: new 10-bar low with RSI above its value at the previous 10-bar low, then a bullish reversal bar
    ll10 = l.rolling(10).min(); hh10 = h.rolling(10).max()
    newlo = (l <= ll10); newhi = (h >= hh10)
    prev_lo_rsi = rsi.where(newlo).shift(1).ffill(); prev_hi_rsi = rsi.where(newhi).shift(1).ffill()
    bull_div = (newlo.shift(1).fillna(False) & (rsi.shift(1) > prev_lo_rsi.shift(1) + 2) & (c > h.shift(1))).values
    bear_div = (newhi.shift(1).fillna(False) & (rsi.shift(1) < prev_hi_rsi.shift(1) - 2) & (c < l.shift(1))).values
    F["C_RSI_DIV"] = (bull_div, bear_div)
    big = (rng >= 1.5 * a.shift(1))
    up3 = big & (c > o) & big.shift(1) & (c.shift(1) > o.shift(1)) & big.shift(2) & (c.shift(2) > o.shift(2))
    dn3 = big & (c < o) & big.shift(1) & (c.shift(1) < o.shift(1)) & big.shift(2) & (c.shift(2) < o.shift(2))
    F["C_EXHAUST"] = (dn3.fillna(False).values, up3.fillna(False).values)
    # D patterns via MCXE-003 causal detectors (swing f3)
    E = CDL.detect(f)
    for nm, pref in (("D_ENGULF", "ENGULF"), ("D_INSIDE_BRK", "INSIDE_BRK"), ("D_NR7_BRK", "NR7_BRK"), ("B_COMPRESS_BRK", "COMPRESS_BRK")):
        F[nm] = _events_to_bool(E, n, pref)
    hb, _ = _events_to_bool(E, n, "HAMMER"); _, ss = _events_to_bool(E, n, "SHOOTSTAR")
    F["D_HAMMER_STAR"] = (hb, ss)
    sw = SWD.swings(f, "f3")
    Ec = CP.detect(f, sw)
    F["D_DOUBLE"] = (_events_to_bool(Ec, n, "DBOT")[0], _events_to_bool(Ec, n, "DTOP")[1])
    F["D_HS"] = (_events_to_bool(Ec, n, "IHS")[0], _events_to_bool(Ec, n, "HS")[1])
    Et = TL.detect(f, sw)
    F["D_TL_BRK3"] = _events_to_bool(Et, n, "TL_BRK_t3")
    return {k: (np.asarray(b, bool), np.asarray(s, bool)) for k, (b, s) in F.items()}


def filters(f, dtrend=None):
    """dtrend: optional array (+1 / -1 / 0) of the previous session's daily trend for intraday frames."""
    c, v = f.close.astype(float), f.volume.astype(float)
    e50, e200 = c.ewm(span=50, adjust=False).mean(), c.ewm(span=200, adjust=False).mean()
    if dtrend is None:
        tb = ((e50 > e200) & (c > e50)).values; ts = ((e50 < e200) & (c < e50)).values
    else:
        tb, ts = dtrend > 0, dtrend < 0
    adx = I.adx(f, 14).values >= 20
    vol = (v > 1.5 * v.rolling(20).mean().shift(1)).values
    vr = (f.atr >= 0.8 * f.atr.rolling(100, min_periods=30).median()).values
    one = np.ones(len(f), bool)
    return {"none": (one, one), "trend": (tb, ts), "adx20": (adx, adx), "vol15": (vol, vol), "volreg": (vr, vr),
            "trend+vol": (tb & vol, ts & vol)}


def daily_trend_for_intraday(f):
    """previous session's daily trend (EMA20 vs EMA50 of daily closes, close vs EMA50), known before today's open."""
    d = f.groupby("day").close.last()
    e20, e50 = d.ewm(span=20, adjust=False).mean(), d.ewm(span=50, adjust=False).mean()
    t = np.where((e20 > e50) & (d > e50), 1, np.where((e20 < e50) & (d < e50), -1, 0))
    t = pd.Series(t, index=d.index).shift(1).fillna(0)
    return f.day.map(t).values


def regime(f):
    """per-bar regime label (for reporting only): trend up / down / range (ADX < 20) x volatility high / low."""
    c = f.close.astype(float)
    adx = I.adx(f, 14).values
    e50 = c.ewm(span=50, adjust=False).mean().values
    vol = np.where(f.atr.values >= f.atr.rolling(100, min_periods=30).median().values, "highvol", "lowvol")
    tr = np.where(adx < 20, "range", np.where(c.values > e50, "up", "down"))
    return np.char.add(np.char.add(tr.astype(str), "/"), vol.astype(str))
