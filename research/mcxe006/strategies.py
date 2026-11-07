"""MCXE-006 hypothesis-driven signal functions. All causal (value at bar i uses bars <= i). Each returns
dict(side, dist [price], stop [price or nan], warm, optional xl/xs exit-signal arrays). `extra` carries cross-sectional
context (market breadth by date for NSE)."""
import numpy as np
import pandas as pd
from crude import indicators as I


def _ema(c, n):
    return c.ewm(span=n, adjust=False).mean()


def _rsi(c, n):
    return I.rsi(c, n)


def _xup(a, b):
    a = pd.Series(np.asarray(a, float)); b = pd.Series(np.asarray(b, float))
    return ((a > b) & (a.shift(1) <= b.shift(1))).fillna(False).values


def _ohlc(f):
    return (f[x].astype(float) for x in ("open", "high", "low", "close", "volume"))


def _side_filters(f, side, extra, trend=None, adx_min=0, adx_max=None, breadth=None, regime_vol=None, dtrend_f=False, rsi_conf=None):
    """common filters applied to a side array. trend: 'with' (only with EMA50>EMA_slow alignment) / 'ema' (close vs EMA)
    breadth: 'align' -> BUY only if market breadth > 0.5, SELL only if < 0.5 (NSE)."""
    o, h, l, c, v = _ohlc(f)
    s = side.copy()
    if trend:
        e_fast, e_slow = _ema(c, 50), _ema(c, trend if isinstance(trend, int) else 100)
        up = ((e_fast > e_slow) & (c > e_fast)).values; dn = ((e_fast < e_slow) & (c < e_fast)).values
        s = np.where((s > 0) & ~up, 0, s); s = np.where((s < 0) & ~dn, 0, s)
    if adx_min or adx_max:
        adx = I.adx(f, 14).values
        if adx_min:
            s = np.where(adx >= adx_min, s, 0)
        if adx_max:
            s = np.where(adx < adx_max, s, 0)
    if breadth and extra is not None and "breadth" in extra:
        b = f.time.dt.normalize().map(extra["breadth"]).values.astype(float)
        hi, lo = (0.5, 0.5) if breadth == "align" else breadth
        s = np.where((s > 0) & ~(b > hi), 0, s); s = np.where((s < 0) & ~(b < lo), 0, s)
    if rsi_conf:
        r = _rsi(c, 14).values
        s = np.where((s > 0) & ~(r > rsi_conf), 0, s); s = np.where((s < 0) & ~(r < 100 - rsi_conf), 0, s)
    if dtrend_f:
        t = _daily_trend(f)
        s = np.where(s * t > 0, s, 0)
    if regime_vol:
        a = f.atr
        r = (a / a.rolling(100, min_periods=30).median()).values
        s = np.where((r >= regime_vol[0]) & (r <= regime_vol[1]), s, 0)
    return s


# ─── H1 trend following ───
def donchian(f, n=20, k=2.0, extra=None, both=True, **flt):
    o, h, l, c, v = _ohlc(f)
    hh, ll = h.shift(1).rolling(n).max(), l.shift(1).rolling(n).min()
    side = np.where(_xup(c, hh), 1, np.where(_xup(-c, -ll), -1, 0))
    if not both:
        side = np.where(side > 0, 1, 0)
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, dist=k * f.atr.values, warm=n + 20)


def ema_pullback(f, fast=20, slow=50, k=2.0, confirm="prevhigh", extra=None, **flt):
    """trend (EMAfast > EMAslow, close > EMAslow); previous bar dipped to / below EMAfast; this bar resumes."""
    o, h, l, c, v = _ohlc(f)
    ef, es = _ema(c, fast), _ema(c, slow)
    up = (ef > es) & (c > es); dn = (ef < es) & (c < es)
    touch_up = (l.shift(1) <= ef.shift(1)); touch_dn = (h.shift(1) >= ef.shift(1))
    if confirm == "prevhigh":
        res_up, res_dn = c > h.shift(1), c < l.shift(1)
    else:
        res_up, res_dn = (c > ef) & (c > o), (c < ef) & (c < o)
    side = np.where((up & touch_up & res_up).values, 1, np.where((dn & touch_dn & res_dn).values, -1, 0))
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, dist=k * f.atr.values, warm=slow + 10)


def macd_trend_pullback(f, k=2.0, extra=None, **flt):
    """trend pullback + momentum confirmation: EMA20>EMA50, MACD histogram turns up from < 0 (pullback ending)."""
    o, h, l, c, v = _ohlc(f)
    e20, e50 = _ema(c, 20), _ema(c, 50)
    macd = _ema(c, 12) - _ema(c, 26); hist = macd - _ema(macd, 9)
    up = (e20 > e50) & (c > e50); dn = (e20 < e50) & (c < e50)
    turn_up = (hist > hist.shift(1)) & (hist.shift(1) <= hist.shift(2)) & (hist.shift(1) < 0)
    turn_dn = (hist < hist.shift(1)) & (hist.shift(1) >= hist.shift(2)) & (hist.shift(1) > 0)
    side = np.where((up & turn_up).values, 1, np.where((dn & turn_dn).values, -1, 0))
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, dist=k * f.atr.values, warm=60)


# ─── H2 / H7 intraday session breakouts (cost-aware structural stops) ───
def orb(f, mins=60, open_min=540, max_w=1.2, min_w=0.15, stop="other", k=0.5, last_entry=None, extra=None, **flt):
    """opening-range breakout: range of the first `mins` minutes; first close outside it after the range -> trade.
    stop: 'other' = other side of the range, 'mid' = range midpoint, 'datr' = k x daily ATR. Width filter in daily ATR."""
    o, h, l, c, v = _ohlc(f)
    day = f.day.values
    in_or = (f.m.values >= open_min) & (f.m.values < open_min + mins)
    orh = pd.Series(np.where(in_or, h, np.nan)).groupby(day).transform("max").values
    orl = pd.Series(np.where(in_or, l, np.nan)).groupby(day).transform("min").values
    after = f.m.values >= open_min + mins
    if last_entry is not None:
        after &= f.m.values <= last_entry
    w = (orh - orl) / f.datr.values
    okw = (w <= max_w) & (w >= min_w)
    bu = after & okw & (c.values > orh); bd = after & okw & (c.values < orl)
    # first breakout of the day only (either side)
    any_bo = pd.Series(bu | bd)
    first = (any_bo.groupby(day).cumsum() == 1).values & (bu | bd)
    side = np.where(first & bu, 1, np.where(first & bd, -1, 0))
    side = _side_filters(f, side, extra, **flt)
    if stop == "other":
        st = np.where(side > 0, orl, orh)
    elif stop == "mid":
        st = (orh + orl) / 2
    else:
        st = np.full(len(f), np.nan)
    return dict(side=side, stop=st, dist=k * f.datr.values, warm=5)


def pdhl(f, k=0.5, open_min=540, last_entry=None, extra=None, dtrend=False, **flt):
    """previous-day high / low breakout (first of the day); stop k x daily ATR."""
    o, h, l, c, v = _ohlc(f)
    day = f.day.values
    m = f.m.values >= open_min
    if last_entry is not None:
        m &= f.m.values <= last_entry
    bu = m & _xup(c, f.pdh.values); bd = m & _xup(-c, -f.pdl.values)
    any_bo = pd.Series(bu | bd)
    first = (any_bo.groupby(day).cumsum() == 1).values & (bu | bd)
    side = np.where(first & bu, 1, np.where(first & bd, -1, 0))
    if dtrend:
        t = _daily_trend(f)
        side = np.where(side * t > 0, side, 0)
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, dist=k * f.datr.values, warm=5)


def vwap_pullback(f, k=0.5, open_min=540, start_after=60, last_entry=None, extra=None, **flt):
    """daily trend up (previous sessions), price above VWAP, bar dips to VWAP and closes back above it -> BUY (mirror)."""
    o, h, l, c, v = _ohlc(f)
    t = _daily_trend(f)
    vw = f.vwap.values
    m = f.m.values >= open_min + start_after
    if last_entry is not None:
        m &= f.m.values <= last_entry
    bu = m & (t > 0) & (l.values <= vw) & (c.values > vw) & (c.values > o.values) & (f.dopen.values < c.values)
    bd = m & (t < 0) & (h.values >= vw) & (c.values < vw) & (c.values < o.values) & (f.dopen.values > c.values)
    side = np.where(bu, 1, np.where(bd, -1, 0))
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, dist=k * f.datr.values, warm=5)


def _daily_trend(f):
    d = f.groupby("day").close.last()
    e20, e50 = d.ewm(span=20, adjust=False).mean(), d.ewm(span=50, adjust=False).mean()
    t = pd.Series(np.where((e20 > e50) & (d > e20), 1, np.where((e20 < e50) & (d < e20), -1, 0)), index=d.index).shift(1).fillna(0)
    return f.day.map(t).values


# ─── H3 breakout + volume + OI (futures) ───
def bo_vol_oi(f, n=20, vol_x=1.5, oi_min=0.0, k=2.0, extra=None, **flt):
    o, h, l, c, v = _ohlc(f)
    hh, ll = h.shift(1).rolling(n).max(), l.shift(1).rolling(n).min()
    va = v.rolling(n).mean().shift(1)
    doi = f["doi"].values if "doi" in f else np.zeros(len(f))
    vol_ok = (v > vol_x * va).values
    oi_ok = doi > oi_min if oi_min is not None else np.ones(len(f), bool)
    side = np.where((c > hh).values & vol_ok & oi_ok, 1, np.where((c < ll).values & vol_ok & oi_ok, -1, 0))
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, dist=k * f.atr.values, warm=n + 10)


# ─── H4 mean reversion in trend ───
def rsi2_pullback(f, th=10, trend_n=50, exit_ema=5, k=2.5, both=False, extra=None, **flt):
    o, h, l, c, v = _ohlc(f)
    r2 = _rsi(c, 2); et = _ema(c, trend_n); ex = _ema(c, exit_ema)
    bu = ((r2 < th) & (c > et)).values
    bd = ((r2 > 100 - th) & (c < et)).values if both else np.zeros(len(f), bool)
    side = np.where(bu, 1, np.where(bd, -1, 0))
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, dist=k * f.atr.values, warm=trend_n + 10, xl=(c > ex).values, xs=(c < ex).values)


# ─── H5 RSI reversal / extremes ───
def rsi_rev(f, n=14, hi=75, lo=25, mode="cross_back", candle=False, trend=None, k=1.5, exit_mid=False, extra=None, **flt):
    """mode cross_back: BUY when RSI crosses back above `lo` (from the oversold zone); SELL when it crosses back below `hi`.
    mode momentum: BUY when RSI crosses above `hi` (stays extreme = strength); SELL when it crosses below `lo`.
    candle: require a reversal bar (bullish close > prev high for BUY). trend: 'with' (only BUY in an uptrend:
    close > EMA100) / 'against' / None. exit_mid: exit when RSI crosses 50 (mean-reversion target)."""
    o, h, l, c, v = _ohlc(f)
    r = _rsi(c, n)
    if mode == "cross_back":
        bu, bd = _xup(r, np.full(len(f), lo)), _xup(np.full(len(f), hi), r)
    else:
        bu, bd = _xup(r, np.full(len(f), hi)), _xup(np.full(len(f), lo), r)
    if candle:
        bu = bu & (c > o).values & (c > h.shift(1)).values
        bd = bd & (c < o).values & (c < l.shift(1)).values
    side = np.where(bu, 1, np.where(bd, -1, 0))
    if trend:
        e = _ema(c, 100).values
        up = c.values > e
        if trend == "with":
            side = np.where(((side > 0) & up) | ((side < 0) & ~up), side, 0)
        else:
            side = np.where(((side > 0) & ~up) | ((side < 0) & up), side, 0)
    side = _side_filters(f, side, extra, **flt)
    out = dict(side=side, dist=k * f.atr.values, warm=110 if trend else n + 10)
    if exit_mid:
        out["xl"] = (r > 50).values; out["xs"] = (r < 50).values
    return out


def rsi_div(f, k=1.5, extra=None, **flt):
    from research.mcxe005 import signals as SG5
    F = SG5.families(f)
    b, s = F["C_RSI_DIV"]
    side = np.where(b, 1, np.where(s, -1, 0))
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, dist=k * f.atr.values, warm=30)


# ─── H6 candle at support / resistance ───
def candle_sr(f, near=0.5, n=20, confirm=False, k_buf=0.1, pats=("hammer", "engulf"), extra=None, **flt):
    """bullish hammer / engulfing whose low is within `near` ATR of the prior n-bar low (support); SELL mirror at
    resistance. Stop = pattern extreme -/+ k_buf ATR (structural). confirm: enter one bar later only if that bar closes
    beyond the pattern high (low for SELL)."""
    o, h, l, c, v = _ohlc(f)
    a = f.atr
    rng = (h - l).replace(0, np.nan); body = (c - o).abs()
    lower = np.minimum(o, c) - l; upper = h - np.maximum(o, c)
    ham = (lower >= 2 * body) & (upper <= 0.3 * rng) & (rng >= 0.8 * a.shift(1))
    star = (upper >= 2 * body) & (lower <= 0.3 * rng) & (rng >= 0.8 * a.shift(1))
    beng = (c > o) & (c.shift(1) < o.shift(1)) & (c >= o.shift(1)) & (o <= c.shift(1)) & (body > body.shift(1))
    seng = (c < o) & (c.shift(1) > o.shift(1)) & (c <= o.shift(1)) & (o >= c.shift(1)) & (body > body.shift(1))
    bpat = (ham if "hammer" in pats else False) | (beng if "engulf" in pats else False)
    spat = (star if "hammer" in pats else False) | (seng if "engulf" in pats else False)
    sup = l.shift(1).rolling(n).min(); res = h.shift(1).rolling(n).max()
    pl = np.minimum(l, l.shift(1)); ph = np.maximum(h, h.shift(1))
    bu = bpat & ((pl - sup).abs() <= near * a)
    bd = spat & ((ph - res).abs() <= near * a)
    bu, bd = bu.fillna(False).values, bd.fillna(False).values
    stop_b = (pl - k_buf * a).values; stop_s = (ph + k_buf * a).values
    if confirm:
        cb = np.r_[False, bu[:-1]] & (c.values > np.r_[np.nan, h.values[:-1]])
        cs = np.r_[False, bd[:-1]] & (c.values < np.r_[np.nan, l.values[:-1]])
        stop_b = np.r_[np.nan, stop_b[:-1]]; stop_s = np.r_[np.nan, stop_s[:-1]]
        bu, bd = cb, cs
    side = np.where(bu, 1, np.where(bd, -1, 0))
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, stop=np.where(side > 0, stop_b, stop_s), dist=f.atr.values, warm=n + 10)


def retest(f, n=20, k=1.5, within=5, extra=None, **flt):
    """breakout + retest: a close above the n-bar high, then within `within` bars price comes back to the old high
    (low <= level + 0.2 ATR) and closes above it -> BUY. Mirror for SELL."""
    o, h, l, c, v = _ohlc(f)
    a = f.atr
    hh, ll = h.shift(1).rolling(n).max(), l.shift(1).rolling(n).min()
    bo_u = pd.Series(_xup(c, hh)); bo_d = pd.Series(_xup(-c, -ll))
    lvl_u = hh.where(bo_u).ffill(limit=within); lvl_d = ll.where(bo_d).ffill(limit=within)
    rec_u = bo_u.shift(1).rolling(within, min_periods=1).max().fillna(0).astype(bool)
    rec_d = bo_d.shift(1).rolling(within, min_periods=1).max().fillna(0).astype(bool)
    bu = rec_u & (l <= lvl_u + 0.2 * a) & (c > lvl_u) & (c > o)
    bd = rec_d & (h >= lvl_d - 0.2 * a) & (c < lvl_d) & (c < o)
    side = np.where(bu.fillna(False).values, 1, np.where(bd.fillna(False).values, -1, 0))
    # one retest entry per breakout
    side = _first_in_run(side, within)
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, dist=k * a.values, warm=n + 10)


def _first_in_run(side, gap):
    out = side.copy(); last = -10 ** 9
    for i in np.flatnonzero(side):
        if i - last <= gap:
            out[i] = 0
        else:
            last = i
    return out


# ─── H8 overnight close strength ───
def close_strength(f, top=0.1, vol_x=1.5, trend=False, extra=None, **flt):
    o, h, l, c, v = _ohlc(f)
    rng = (h - l).replace(0, np.nan)
    pos = (c - l) / rng
    va = v.rolling(20).mean().shift(1)
    vol_ok = (v > vol_x * va).values if vol_x else np.ones(len(f), bool)
    bu = (pos >= 1 - top).values & vol_ok; bd = (pos <= top).values & vol_ok
    side = np.where(bu, 1, np.where(bd, -1, 0))
    if trend:
        e = _ema(c, 50).values
        side = np.where(((side > 0) & (c.values > e)) | ((side < 0) & (c.values < e)), side, 0)
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, dist=f.atr.values, warm=60)




# ─── H10 cross-sectional (market-neutral) ───
def xs_rank(f, lookback=20, topn=10, mode="momentum", rebalance="W-FRI", k=3.0, extra=None, **flt):
    """rank all stock futures by `lookback`-day return at each rebalance close (only dates in extra['xs'] panel);
    momentum: BUY the top `topn`, SELL the bottom `topn`; reversal: the opposite. Exit by time (maxbars) or k-ATR stop."""
    P = extra["xs"][lookback]                      # DataFrame date x symbol of ranks (1 = best), NaN when not eligible
    name = f.attrs["name"]
    if name not in P.columns:
        return dict(side=np.zeros(len(f), int), dist=k * f.atr.values, warm=lookback + 5)
    d = f.time.dt.normalize()
    rk = d.map(P[name]).values.astype(float)
    nvalid = d.map(P.notna().sum(axis=1)).values.astype(float)
    reb = d.isin(extra["xs_dates"]).values
    top = reb & (rk <= topn); bot = reb & (rk > nvalid - topn)
    side = np.where(top, 1, np.where(bot, -1, 0))
    if mode == "reversal":
        side = -side
    side = _side_filters(f, side, extra, **flt)
    return dict(side=side, dist=k * f.atr.values, warm=lookback + 5)


REG = {k: v for k, v in globals().items() if callable(v) and not k.startswith("_") and k not in ("I",)}
