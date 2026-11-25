"""BOOK-PAT-001 (25-Nov-2026, owner: "understand strategy and chart pattern, apply and backtest" – the e-book
'15 Candlestick Patterns / 17 Chart Patterns'). Every pattern coded with the BOOK'S OWN entry and stop rules.

Data
  STK 1d   NSE cash daily, F&O stocks (218), 2012-2026 (price series broken at corporate-action gaps > 25 %)
  STK 1h   NSE cash 5-min -> 1-hour candles (09:15 anchored), 218 F&O stocks, Oct-2024 .. Nov-2026
  MCX 1d   MCX bhavcopy, 9 commodities, Jul-2022 .. Nov-2026 (ratio back-adjusted, contract switches respected)
Candlesticks (book entry / stop; book gives no target -> 1R and 2R tested). Context as the book says: bullish patterns
  after a downtrend (EMA20 < EMA50 and close before the pattern < EMA50), bearish after an uptrend. 'any' = no context.
  Entry = stop order beyond the book's level, live for the next 3 candles, cancelled if the stop trades first.
Chart patterns (pivots = 3-candle fractals, known 3 candles later – no look-ahead). Entry = first CLOSE beyond the
  pattern line, filled at the next open. Stop and target = the book's ('book'); 1R and 2R also shown.
Every trade: stop checked before target in a candle, gaps fill at the open, time exit 20 candles (daily) / 35 (1h),
  costs 0.10 % round trip stocks, 0.05 % MCX. One trade per instrument at a time per pattern.
Baseline: random candles (4 %) with a 1.5-ATR stop, same side, same targets.
python research/program/book_patterns.py -> results/book_patterns_trades.parquet"""
import sys
from multiprocessing import Pool
from pathlib import Path
import warnings
import numpy as np
warnings.filterwarnings("ignore")
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
EQ = Path("/home/claude/rd/research/data/angel/NSE_EQ")
OUT = ROOT / "research/program/results"
K = 3                       # fractal pivot half-width


# ---------------------------------------------------------------- data
def prep(f, cost):
    f = f.reset_index(drop=True).copy()
    o, h, l, c = (f[x].astype(float) for x in ("open", "high", "low", "close"))
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    f["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    f["e20"] = c.ewm(span=20, adjust=False).mean(); f["e50"] = c.ewm(span=50, adjust=False).mean()
    if "switch" not in f:
        f["switch"] = False
    f["cost"] = cost
    return f


def stk_daily(sym):
    d = pd.read_csv(EQ / f"{sym}_ONE_DAY.csv.gz", parse_dates=["time"])
    d = d[d.time >= "2011-06-01"].reset_index(drop=True)
    g = (d.open / d.close.shift() - 1).abs()
    d["switch"] = (g > 0.25).fillna(False)
    return prep(d, 0.001)


def stk_1h(sym):
    p = EQ / f"{sym}_FIVE_MINUTE.csv.gz"
    if not p.exists():
        return None
    d = pd.read_csv(p, parse_dates=["time"])
    d = d[(d.time.dt.time >= pd.Timestamp("09:15").time()) & (d.time.dt.time < pd.Timestamp("15:30").time())]
    k = d.time.dt.normalize() + pd.to_timedelta(((d.time - d.time.dt.normalize() - pd.Timedelta("9h15min")) // pd.Timedelta("1h")) * 60 + 555, unit="min")
    a = d.groupby(k).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    a = a.reset_index().rename(columns={"index": "time", "time": "time"})
    a.columns = ["time", "open", "high", "low", "close", "volume"]
    g = (a.open / a.close.shift() - 1).abs(); a["switch"] = (g > 0.25).fillna(False)
    return prep(a, 0.001)


def mcx_daily(sym):
    f = pd.read_parquet(f"/home/claude/rd/mcx_{sym}.parquet")   # cached mcx_pos.series (ratio back-adjusted)
    return prep(f, 0.0005)


# ---------------------------------------------------------------- trade simulation
def run_trade(f, i, side, mode, level, stop, tgt_pts, maxh):
    """mode 'stop': stop order at level, valid 3 candles after i. mode 'next': fill at open i+1.
    tgt_pts: dict name -> target distance in points. Returns dict name -> (R, bars) or None."""
    o, h, l, c, sw, cst = f._o, f._h, f._l, f._c, f._sw, f._cost
    n = len(c)
    if i + 2 >= n:
        return None, i
    if mode == "next":
        if sw[i + 1]:
            return None, i
        e, j0 = o[i + 1], i + 1
    else:
        e = None
        for j in range(i + 1, min(n, i + 4)):
            if sw[j]:
                return None, i
            if side * (o[j] - stop) <= 0:            # opens beyond the stop -> cancelled
                return None, j
            if side * (o[j] - level) >= 0:
                e, j0 = o[j], j; break
            if (h[j] >= level) if side > 0 else (l[j] <= level):
                e, j0 = level, j; break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                return None, j
        if e is None:
            return None, min(n - 1, i + 3)
    R = side * (e - stop)
    if not R > 0:
        return None, j0
    res = {}; last = j0
    for name, tp in tgt_pts.items():
        T = e + side * tp; px = None; j = j0
        while j < n:
            if j > j0:
                if sw[j]:
                    px, j = c[j - 1], j - 1; break
                if side * (o[j] - stop) <= 0:
                    px = o[j]; break
                if side * (o[j] - T) >= 0:
                    px = o[j]; break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                px = stop; break
            if (h[j] >= T) if side > 0 else (l[j] <= T):
                px = T; break
            if j - j0 >= maxh:
                px = c[j]; break
            j += 1
        if px is None:
            px, j = c[n - 1], n - 1
        res[name] = (side * (px - e) / R - cst * e / R, j - j0 + 1)
        last = max(last, j)
    res["_risk_atr"] = R / f._a[i]
    return res, last


# ---------------------------------------------------------------- candlestick patterns (book)
def candles(f):
    o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
    e20, e50 = f.e20.values, f.e50.values
    rg = np.maximum(h - l, 1e-9); body = np.abs(c - o); up = h - np.maximum(o, c); lo = np.minimum(o, c) - l
    S = lambda x, k: np.r_[np.full(k, np.nan), x[:-k]]  # noqa: E731
    dn = lambda k: (S(e20, k) < S(e50, k)) & (S(c, k) < S(e50, k))   # noqa: E731  trend before a k-candle pattern
    upt = lambda k: (S(e20, k) > S(e50, k)) & (S(c, k) > S(e50, k))  # noqa: E731
    green, red = c > o, c < o
    big = body >= 0.6 * a
    P = []   # (name, side, mask, ctx_mask, level_arr, stop_arr)

    def add(nm, side, m, ctx, lev, st):
        P.append((nm, side, np.nan_to_num(m).astype(bool), np.nan_to_num(ctx).astype(bool), lev, st))
    doji = body <= 0.1 * rg
    add("Gravestone doji", -1, doji & (up >= 0.7 * rg) & (rg >= 0.5 * a), upt(1), l, h)
    add("Dragonfly doji", 1, doji & (lo >= 0.7 * rg) & (rg >= 0.5 * a), dn(1), h, l)
    ll = doji & (up >= 0.3 * rg) & (lo >= 0.3 * rg) & (rg >= 0.8 * a)
    add("Long-legged doji (after fall)", 1, ll, dn(1), h, l)
    add("Long-legged doji (after rise)", -1, ll, upt(1), l, h)
    ham = (lo >= 2 * body) & (up <= 0.3 * rg) & (rg >= 0.5 * a)
    inv = (up >= 2 * body) & (lo <= 0.15 * rg) & (rg >= 0.5 * a)
    add("Hammer", 1, ham, dn(1), h, l)
    add("Inverted hammer", 1, inv, dn(1), h, l)
    add("Hanging man", -1, ham, upt(1), l, h)
    add("Shooting star", -1, inv, upt(1), l, h)
    o1, h1, l1, c1, b1 = S(o, 1), S(h, 1), S(l, 1), S(c, 1), S(body, 1)
    add("Bullish engulfing", 1, (c1 < o1) & green & (o <= c1) & (c >= o1) & (body > b1), dn(2), h, l)
    add("Bearish engulfing", -1, (c1 > o1) & red & (o >= c1) & (c <= o1) & (body > b1), upt(2), l, h)
    add("Bullish harami", 1, (c1 < o1) & (b1 >= 0.6 * a) & green & (o > c1) & (c < o1) & (body <= 0.6 * b1), dn(2), h, l1)
    add("Bearish harami", -1, (c1 > o1) & (b1 >= 0.6 * a) & red & (o < c1) & (c > o1) & (body <= 0.6 * b1), upt(2), l, h1)
    o2, c2, h2, l2, b2 = S(o, 2), S(c, 2), S(h, 2), S(l, 2), S(body, 2)
    mid2 = (o2 + c2) / 2
    star_small = b1 <= 0.35 * b2
    add("Morning star", 1, (c2 < o2) & (b2 >= 0.6 * a) & star_small & green & (c > mid2) & (o > np.minimum(o1, c1) - 0.1 * a), dn(3), h, l1)
    add("Evening star", -1, (c2 > o2) & (b2 >= 0.6 * a) & star_small & red & (c < mid2) & (o < np.maximum(o1, c1) + 0.1 * a), upt(3), l, h1)
    # rising / falling three: candle i-4 long, i-3..i-1 small inside its range, i long beyond candle i-4's close
    o4, c4, h4, l4, b4 = S(o, 4), S(c, 4), S(h, 4), S(l, 4), S(body, 4)
    mids = [(S(o, k), S(c, k), S(h, k), S(l, k), S(body, k)) for k in (1, 2, 3)]
    inside = np.ones(len(c), bool); nred = np.zeros(len(c)); ngrn = np.zeros(len(c))
    for (ok, ck, hk, lk, bk) in mids:
        inside &= np.nan_to_num((hk <= h4) & (lk >= l4) & (bk <= 0.6 * b4)).astype(bool)
        nred += np.nan_to_num(ck < ok); ngrn += np.nan_to_num(ck > ok)
    add("Rising three", 1, (c4 > o4) & (b4 >= 0.8 * a) & inside & (nred >= 2) & green & big & (c > c4), upt(5), h, l4)
    add("Falling three", -1, (c4 < o4) & (b4 >= 0.8 * a) & inside & (ngrn >= 2) & red & big & (c < c4), dn(5), l, h4)
    add("Tweezer top", -1, (c1 > o1) & red & (np.abs(h - h1) <= 0.1 * a), upt(2), l, np.fmax(h, h1))
    add("Tweezer bottom", 1, (c1 < o1) & green & (np.abs(l - l1) <= 0.1 * a), dn(2), h, np.fmin(l, l1))
    return P


# ---------------------------------------------------------------- chart patterns (book)
def pivots(f):
    h, l = f.high.values, f.low.values; n = len(h)
    ph, pl = np.zeros(n, bool), np.zeros(n, bool)
    for i in range(K, n - K):
        w = slice(i - K, i + K + 1)
        ph[i] = h[i] == h[w].max() and h[i] > h[i - 1]
        pl[i] = l[i] == l[w].min() and l[i] < l[i - 1]
    return ph, pl


def line(p1, p2, t):
    (i1, y1), (i2, y2) = p1, p2
    return y1 + (y2 - y1) * (t - i1) / (i2 - i1)


def chart(f):
    """yields (name, side, t, stop, target_pts) – signal at the close of t, entry next open."""
    o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
    e20, e50, sw = f.e20.values, f.e50.values, f.switch.values
    ph, pl = pivots(f); n = len(c)
    H, L = [], []          # confirmed pivots (index, price)
    used = set(); out = []
    seg0 = 0

    def emit(key, nm, side, t, stop, tp):
        if key in used:
            return
        if side * (c[t] - stop) <= 0:
            return
        used.add(key); out.append((nm, side, t, stop, tp))

    for t in range(60, n - 1):
        if sw[t]:
            H, L, seg0 = [], [], t
            continue
        j = t - K
        if j > seg0:
            if ph[j]: H.append((j, h[j]))
            if pl[j]: L.append((j, l[j]))
        H, L = H[-6:], L[-6:]
        at = a[t]
        if not at > 0:
            continue
        tol = 0.5 * at
        up_tr = lambda i: e20[i] > e50[i]   # noqa: E731
        brk_up = lambda lev, lev_prev: c[t] > lev and c[t - 1] <= lev_prev   # noqa: E731
        brk_dn = lambda lev, lev_prev: c[t] < lev and c[t - 1] >= lev_prev   # noqa: E731
        # ---------- double top / bottom
        if len(H) >= 2:
            (i1, y1), (i2, y2) = H[-2], H[-1]
            if 5 <= i2 - i1 <= 60 and abs(y1 - y2) <= tol and t - i2 <= 20:
                nk = l[i1:i2 + 1].min(); top = max(y1, y2)
                if top - nk >= 1.5 * at and up_tr(i1) and h[i2 + 1:t + 1].max() <= top and brk_dn(nk, nk):
                    st = top + 0.1 * at
                    emit(("DT", i1, i2), "Double top", -1, t, st, dict(book=st - c[t], height=top - nk))
        if len(L) >= 2:
            (i1, y1), (i2, y2) = L[-2], L[-1]
            if 5 <= i2 - i1 <= 60 and abs(y1 - y2) <= tol and t - i2 <= 20:
                nk = h[i1:i2 + 1].max(); bot = min(y1, y2)
                if nk - bot >= 1.5 * at and not up_tr(i1) and l[i2 + 1:t + 1].min() >= bot and brk_up(nk, nk):
                    st = bot - 0.1 * at
                    emit(("DB", i1, i2), "Double bottom", 1, t, st, dict(book=c[t] - st, height=nk - bot))
        # ---------- head & shoulders / inverse
        if len(H) >= 3:
            (ia, ya), (ib, yb), (ic, yc) = H[-3], H[-2], H[-1]
            if yb - max(ya, yc) >= 0.5 * at and abs(ya - yc) <= 1.0 * at and ic - ia <= 80 and t - ic <= 20:
                t1 = ia + int(np.argmin(l[ia:ib + 1])); t2 = ib + int(np.argmin(l[ib:ic + 1]))
                nk_t, nk_p = line((t1, l[t1]), (t2, l[t2]), t), line((t1, l[t1]), (t2, l[t2]), t - 1)
                if up_tr(ia) and brk_dn(nk_t, nk_p) and h[ic + 1:t + 1].max() <= yc:
                    st = yc + 0.1 * at
                    emit(("HS", ia, ib, ic), "Head & shoulders", -1, t, st, dict(book=yb - line((t1, l[t1]), (t2, l[t2]), ib)))
        if len(L) >= 3:
            (ia, ya), (ib, yb), (ic, yc) = L[-3], L[-2], L[-1]
            if min(ya, yc) - yb >= 0.5 * at and abs(ya - yc) <= 1.0 * at and ic - ia <= 80 and t - ic <= 20:
                t1 = ia + int(np.argmax(h[ia:ib + 1])); t2 = ib + int(np.argmax(h[ib:ic + 1]))
                nk_t, nk_p = line((t1, h[t1]), (t2, h[t2]), t), line((t1, h[t1]), (t2, h[t2]), t - 1)
                if not up_tr(ia) and brk_up(nk_t, nk_p) and l[ic + 1:t + 1].min() >= yc:
                    st = yc - 0.1 * at
                    emit(("IHS", ia, ib, ic), "Inverse head & shoulders", 1, t, st, dict(book=line((t1, h[t1]), (t2, h[t2]), ib) - yb))
        # ---------- two-high / two-low structures (triangles, rectangles, channels, wedges)
        if len(H) >= 2 and len(L) >= 2:
            h1, h2 = H[-2], H[-1]; l1, l2 = L[-2], L[-1]
            first = min(h1[0], l1[0]); last = max(h2[0], l2[0])
            ok = last - first <= 70 and t - last <= 15 and h1[0] < h2[0] and l1[0] < l2[0]
            if ok:
                dh, dl = h2[1] - h1[1], l2[1] - l1[1]
                width0 = h1[1] - l1[1]
                ut = up_tr(first)
                sH = dh / (h2[0] - h1[0]); sL = dl / (l2[0] - l1[0])
                upL, upP = line(h1, h2, t), line(h1, h2, t - 1)
                loL, loP = line(l1, l2, t), line(l1, l2, t - 1)
                key = (h1[0], h2[0], l1[0], l2[0])
                flatH, flatL = abs(dh) <= tol, abs(dl) <= tol
                if width0 >= 1.5 * at:
                    res, sup = max(h1[1], h2[1]), min(l1[1], l2[1])
                    # ascending triangle: flat top, rising lows, uptrend
                    if flatH and dl >= 0.25 * at and ut and brk_up(res, res):
                        emit(key + ("AT",), "Ascending triangle", 1, t, l2[1], dict(book=res - l1[1]))
                    if flatL and dh <= -0.25 * at and not ut and brk_dn(sup, sup):
                        emit(key + ("DT",), "Descending triangle", -1, t, h2[1], dict(book=h1[1] - sup))
                    if dh <= -0.25 * at and dl >= 0.25 * at:
                        if brk_up(upL, upP):
                            emit(key + ("STU",), "Symmetric triangle (break up)", 1, t, l2[1], dict(book=width0))
                        elif brk_dn(loL, loP):
                            emit(key + ("STD",), "Symmetric triangle (break down)", -1, t, h2[1], dict(book=width0))
                    if flatH and flatL:
                        w = res - sup
                        if brk_up(res, res):
                            emit(key + ("RU",), "Bullish rectangle" if ut else "Horizontal channel (break up, no trend)", 1, t, sup - 0.1 * at, dict(book=w))
                        elif brk_dn(sup, sup):
                            emit(key + ("RD",), "Bearish rectangle" if not ut else "Horizontal channel (break down, no trend)", -1, t, res + 0.1 * at, dict(book=w))
                    rising = dh >= 0.25 * at and dl >= 0.25 * at
                    falling = dh <= -0.25 * at and dl <= -0.25 * at
                    if (rising or falling) and sH * sL > 0:
                        ratio = sH / sL
                        wnow = upL - loL
                        if wnow > 0.5 * at:
                            if 0.67 <= ratio <= 1.5:            # parallel = channel
                                if rising and brk_up(upL, upP):
                                    emit(key + ("ACU",), "Ascending channel (break up)", 1, t, l2[1], dict(book=wnow))
                                if falling and brk_dn(loL, loP):
                                    emit(key + ("DCD",), "Descending channel (break down)", -1, t, h2[1], dict(book=wnow))
                            elif rising and ratio < 0.67:       # lows rise faster -> rising wedge
                                if brk_dn(loL, loP):
                                    emit(key + ("RWD",), "Rising wedge (break down)", -1, t, h2[1], dict(book=width0))
                                elif brk_up(upL, upP):
                                    emit(key + ("RWU",), "Rising wedge (break up)", 1, t, l2[1], dict(book=width0))
                            elif falling and ratio > 1.5:       # highs fall faster -> falling wedge
                                if brk_up(upL, upP):
                                    emit(key + ("FWU",), "Falling wedge (break up)", 1, t, l2[1], dict(book=width0))
                                elif brk_dn(loL, loP):
                                    emit(key + ("FWD",), "Falling wedge (break down)", -1, t, h2[1], dict(book=width0))
        # ---------- flag / pennant (pole >= 4 ATR within 10 candles, then 3-15 candle consolidation)
        for side in (1, -1):
            lo_, hi_ = t - 16, t - 4
            if lo_ < seg0 + 12:
                continue
            seg = h[lo_:hi_ + 1] if side > 0 else -l[lo_:hi_ + 1]
            P = lo_ + int(np.argmax(seg))
            if sw[P:t + 1].any():
                continue
            if side > 0:
                base = l[P - 10:P].min(); pole = h[P] - base
                fl_h, fl_l = h[P + 1:t].max(), l[P + 1:t].min()
                good = pole >= 4 * at and fl_l >= h[P] - 0.5 * pole and fl_h <= h[P] and c[t] > fl_h and c[t - 1] <= fl_h
                stop = fl_l
            else:
                base = h[P - 10:P].max(); pole = base - l[P]
                fl_h, fl_l = h[P + 1:t].max(), l[P + 1:t].min()
                good = pole >= 4 * at and fl_h <= l[P] + 0.5 * pole and fl_l >= l[P] and c[t] < fl_l and c[t - 1] >= fl_l
                stop = fl_h
            if good:
                m = (P + 1 + t) // 2
                r1 = h[P + 1:m].max() - l[P + 1:m].min() if m > P + 1 else 0
                r2 = h[m:t].max() - l[m:t].min() if t > m else 0
                pen = r2 < 0.7 * r1
                nm = ("Pennant (up)" if side > 0 else "Pennant (down)") if pen else ("Bull flag" if side > 0 else "Bear flag")
                emit(("FL", side, P), nm, side, t, stop, dict(book=pole))
        # ---------- cup & handle / inverse (rims = pivots, depth >= 3 ATR, handle < 1/3 depth)
        if len(H) >= 2:
            (ia, ya), (ib, yb) = H[-2], H[-1]
            if 15 <= ib - ia <= 120 and 3 <= t - ib <= 20:
                ix = ia + int(np.argmin(l[ia:ib + 1])); D = min(ya, yb) - l[ix]
                rim = max(ya, yb)
                if D >= 3 * at and abs(ya - yb) <= 0.15 * D and 0.25 <= (ix - ia) / (ib - ia) <= 0.75:
                    hl = l[ib + 1:t + 1].min()
                    if hl >= yb - D / 3 and h[ib + 1:t].max() <= rim and brk_up(rim, rim):
                        emit(("CH", ia, ib), "Cup & handle", 1, t, hl, dict(book=D))
        if len(L) >= 2:
            (ia, ya), (ib, yb) = L[-2], L[-1]
            if 15 <= ib - ia <= 120 and 3 <= t - ib <= 20:
                ix = ia + int(np.argmax(h[ia:ib + 1])); D = h[ix] - max(ya, yb)
                rim = min(ya, yb)
                if D >= 3 * at and abs(ya - yb) <= 0.15 * D and 0.25 <= (ix - ia) / (ib - ia) <= 0.75:
                    hh = h[ib + 1:t + 1].max()
                    if hh <= yb + D / 3 and l[ib + 1:t].min() >= rim and brk_dn(rim, rim):
                        emit(("ICH", ia, ib), "Inverse cup & handle", -1, t, hh, dict(book=D))
    return out


# ---------------------------------------------------------------- driver
def one(job):
    seg, sym = job
    try:
        f = {"STK 1d": stk_daily, "STK 1h": stk_1h, "MCX 1d": mcx_daily}[seg](sym)
    except Exception as ex:
        print("skip", job, ex); return []
    if f is None or len(f) < 200:
        return []
    f._o, f._h, f._l, f._c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    f._sw, f._a, f._cost = f.switch.values.astype(bool), f.atr.values, float(f.cost.iat[0])
    maxh = 35 if seg.endswith("1h") else 20
    tt = f.time.values; rows = []
    a = f._a

    def keep(nm, kind, ctx, side, i, res):
        for tg, v in res.items():
            if tg.startswith("_"):
                continue
            r, b = v
            rows.append((seg, sym, kind, nm, ctx, side, tt[i], tg, np.float32(r), np.int16(b), np.float32(res["_risk_atr"])))
    # candlesticks
    for nm, side, m, ctx, lev, st in candles(f):
        for cx in ("book", "any"):
            busy = -1
            for i in np.flatnonzero(m & ctx if cx == "book" else m):
                if i < 60 or i <= busy or f._sw[i] or not a[i] > 0:
                    continue
                stop = st[i] - side * 0.05 * a[i]
                risk = side * (lev[i] - stop)
                if not (0.2 * a[i] <= risk <= 4 * a[i]):
                    continue
                res, last = run_trade(f, i, side, "stop", lev[i], stop, {"1R": risk, "2R": 2 * risk}, maxh)
                if res:
                    res = {k: v for k, v in res.items()}
                    keep(nm, "candle", cx, side, i, res); busy = last
    # chart patterns
    busy = {}
    for nm, side, t, stop, tp in chart(f):
        if t <= busy.get(nm, -1):
            continue
        risk = side * (f._c[t] - stop)
        if not (0.2 * a[t] <= risk <= 5 * a[t]) or not tp["book"] > 0:
            continue
        tg = {"book": tp["book"], "1R": risk, "2R": 2 * risk}
        res, last = run_trade(f, t, side, "next", None, stop, tg, maxh)
        if res:
            keep(nm, "chart", "book", side, t, res); busy[nm] = last
    # random baseline
    rng = np.random.default_rng(hash(sym) % 2**32)
    for i in np.flatnonzero(rng.random(len(f)) < 0.04):
        if i < 60 or f._sw[i] or not a[i] > 0:
            continue
        for side in (1, -1):
            stop = f._c[i] - side * 1.5 * a[i]
            res, _ = run_trade(f, i, side, "next", None, stop, {"1R": 1.5 * a[i], "2R": 3 * a[i]}, maxh)
            if res:
                keep("RANDOM " + ("BUY" if side > 0 else "SELL"), "base", "any", side, i, res)
    return rows


def jobs():
    U = pd.read_csv(EQ / "universe.csv"); fno = U[U.fno == True].symbol.tolist()   # noqa: E712
    J = [("STK 1d", s) for s in fno if (EQ / f"{s}_ONE_DAY.csv.gz").exists()]
    J += [("STK 1h", s) for s in fno if (EQ / f"{s}_FIVE_MINUTE.csv.gz").exists()]
    J += [("MCX 1d", s) for s in ("GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM", "LEAD", "NICKEL")]
    return J


def main():
    J = jobs(); rows = []
    with Pool(2) as p:
        for k, r in enumerate(p.imap_unordered(one, J, chunksize=4)):
            rows += r
            if k % 100 == 0:
                print(k, len(J), len(rows), flush=True)
    rows = [x for x in rows]
    T = pd.DataFrame(rows, columns=["seg", "sym", "kind", "pat", "ctx", "side", "t", "tgt", "R", "bars", "risk_atr"])
    T.to_parquet(OUT / "book_patterns_trades.parquet")
    print(len(T))


if __name__ == "__main__":
    main()
