"""RSIDIV – one engine for RSI 75 / 25 events and multi-indicator divergence, used for NSE stock futures, NSE index
futures and NSE cash (owner 11-Nov priorities 2-4). Same signal definitions as the MCX study (research/mcxhw/rsi_div.py),
so results are comparable across markets; parameters are NOT tuned per instrument (owner rule 7).

Signals (all known at the bar's close, traded at the NEXT bar's open):
  RSI(14) at the 75 side (mirrored at 25): cross_in, stay5, cross_out, cross70, candle, vol_exhaust, near_level, break5,
  ema20, rsi_div – each traded as REVERSAL and as CONTINUATION (BUY and SELL kept apart).
  Divergence: RSI, MACD, MACD hist, stochastic, stoch RSI, CCI, MFI, OBV, ROC, momentum, Williams %R, volume (+ OI where
  verified OI exists) – regular and hidden, plus multi3 / multi5. Pivots need K bars on each side, so a divergence is
  known only K bars after the swing (no repainting; delay = K bars, recorded in the registry).
  Contexts: none · rsi_extreme · volume_1.5x · reversal_candle · plus market-specific ones passed in (OI, basis,
  volatility, trend, liquidity, relative strength, sector trend).
Trade: stop beyond the 5-bar extreme by 0.1 ATR (0.5–3 ATR), targets 1R / 2R / 3R, max hold, stop checked first,
gaps fill at the open, one trade at a time per instrument, never across instruments; a futures trade that crosses an
expiry pays one extra round trip (roll). Costs are a fraction of price per bar (date-dependent STT)."""
import numpy as np
import pandas as pd
from numba import njit

K_BY_TF = {"1h": 3, "3h": 3, "1d": 3, "1w": 2}
RS = (1.0, 2.0, 3.0)
BASE_CTX = ("none", "rsi_extreme", "volume_1.5x", "reversal_candle")


def wilder(x, n):
    return pd.Series(x).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().values


def rsi_of(x, n=14):
    d = x.diff()
    g = pd.Series(wilder(d.clip(lower=0).values, n), index=x.index)
    ls = pd.Series(wilder((-d).clip(lower=0).values, n), index=x.index)
    r = 100 - 100 / (1 + g / ls.replace(0, np.nan))
    return r.where(~((ls == 0) & (g > 0)), 100.0)             # no losses yet -> 100 (was NaN; found by the 11-Nov test)


def indicators(h, l, c, v, oi=None):
    I = {"rsi": rsi_of(c)}
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    I["macd"] = macd; I["macd_hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    ll, hh = l.rolling(14).min(), h.rolling(14).max()
    I["stoch"] = (100 * (c - ll) / (hh - ll).replace(0, np.nan)).rolling(3).mean()
    r = I["rsi"]; rl, rh = r.rolling(14).min(), r.rolling(14).max()
    I["stoch_rsi"] = (100 * (r - rl) / (rh - rl).replace(0, np.nan)).rolling(3).mean()
    tp = (h + l + c) / 3; sma = tp.rolling(20).mean()
    I["cci"] = (tp - sma) / (0.015 * (tp - sma).abs().rolling(20).mean().replace(0, np.nan))
    mf = tp * v; up = tp > tp.shift(1)
    I["mfi"] = 100 - 100 / (1 + mf.where(up, 0).rolling(14).sum() / mf.where(~up, 0).rolling(14).sum().replace(0, np.nan))
    I["obv"] = (np.sign(c.diff()).fillna(0) * v).cumsum()
    I["roc"] = 100 * (c / c.shift(10) - 1); I["mom"] = c - c.shift(10)
    I["willr"] = -100 * (hh - c) / (hh - ll).replace(0, np.nan)
    I["volume"] = v.rolling(3).mean()
    if oi is not None:
        I["oi"] = oi
    return I


def divergences(h, l, I, K):
    n = len(l); out = {}; w = 2 * K + 1
    pl = np.where((l == l.rolling(w, center=True).min()).values)[0]
    ph = np.where((h == h.rolling(w, center=True).max()).values)[0]
    r = I["rsi"].values
    for side, piv, px in ((1, pl, l.values), (-1, ph, h.values)):
        cnt = np.zeros(n, np.int16)
        e_now, e_prev = np.full(n, np.nan), np.full(n, np.nan)
        if len(piv) >= 2:
            p0, p1 = piv[:-1], piv[1:]
            ok = (p1 - p0 >= 5) & (p1 - p0 <= 60) & (p1 + K < n)
            p0, p1 = p0[ok], p1[ok]
            lower = px[p1] < px[p0] if side > 0 else px[p1] > px[p0]
            for name, s in I.items():
                x = s.values; a, b = x[p0], x[p1]
                fin = np.isfinite(a) & np.isfinite(b)
                better = (b > a) if side > 0 else (b < a)
                for kind, m in (("regular", lower & better & fin), ("hidden", ~lower & ~better & fin & (a != b))):
                    z = np.zeros(n, bool); z[p1[m] + K] = True
                    out[name, kind, side] = z
                if name not in ("oi", "volume"):
                    cnt[p1[lower & better & fin] + K] += 1
            e_now[p1 + K] = r[p1]; e_prev[p1 + K] = r[p0]
        else:
            for name in I:
                for kind in ("regular", "hidden"):
                    out[name, kind, side] = np.zeros(n, bool)
        out["multi3", "regular", side] = cnt >= 3
        out["multi5", "regular", side] = cnt >= 5
        out["_rsi_at_pivot", side] = e_now; out["_rsi_at_prev", side] = e_prev
    return out


def study(b, K, extra=None, oi=None, sides=(1, -1)):
    """b: DataFrame open high low close volume (one instrument, time order). extra: {name: bool array} contexts.
    -> S {(family, event, context, side): bool array}, risk {side: price distance}."""
    o, h, l, c, v = (b[x].astype(float).reset_index(drop=True) for x in ("open", "high", "low", "close", "volume"))
    n = len(c); pc = c.shift(1)
    atr = pd.Series(wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14))
    I = indicators(h, l, c, v, None if oi is None else pd.Series(np.asarray(oi, float)))
    r = I["rsi"]
    body, rng = (c - o).abs(), (h - l).replace(0, np.nan)
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    bull = ((c > o) & (c.shift(1) < o.shift(1)) & (c >= o.shift(1)) & (o <= c.shift(1))) | ((lw >= 2 * body) & (uw <= 0.3 * rng))
    bear = ((c < o) & (c.shift(1) > o.shift(1)) & (c <= o.shift(1)) & (o >= c.shift(1))) | ((uw >= 2 * body) & (lw <= 0.3 * rng))
    rv = v / v.rolling(20).mean().shift(1)
    e20 = c.ewm(span=20, adjust=False).mean()
    hh20, ll20 = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
    hh50, ll50 = h.shift(5).rolling(50).max(), l.shift(5).rolling(50).min()
    D = divergences(h, l, I, K)
    extra = {k: np.asarray(x, bool) for k, x in (extra or {}).items()}
    S = {}
    for zone in (75, 25):
        hi = zone == 75; z = 1 if hi else -1
        beyond = (r >= 75) if hi else (r <= 25)
        bs = beyond.shift(1, fill_value=False)
        ev = {"cross_in": beyond & ~bs,
              "stay5": (beyond.rolling(5).sum() == 5) & ~(bs.rolling(5).sum() == 5),
              "cross_out": ~beyond & bs}
        was = beyond.rolling(20).max().shift(1) > 0
        ev["cross70"] = was & (((r < 70) & (r.shift(1) >= 70)) if hi else ((r > 30) & (r.shift(1) <= 30)))
        ev["candle"] = (beyond.rolling(3).max() > 0) & (bear if hi else bull)
        ev["vol_exhaust"] = beyond & ((h > hh20) if hi else (l < ll20)) & (rv < 0.7)
        ev["near_level"] = beyond & ~bs & (((h - hh50).abs() <= 0.25 * atr) if hi else ((l - ll50).abs() <= 0.25 * atr))
        was10 = beyond.rolling(10).max() > 0
        ev["break5"] = was10 & ((c < l.shift(1).rolling(5).min()) if hi else (c > h.shift(1).rolling(5).max()))
        ev["ema20"] = was10 & (((c < e20) & (c.shift(1) >= e20.shift(1))) if hi else ((c > e20) & (c.shift(1) <= e20.shift(1))))
        prev = D["_rsi_at_prev", -z]
        ev["rsi_div"] = pd.Series(D["rsi", "regular", -z] & ((prev >= 75) if hi else (prev <= 25)))
        for name, e in ev.items():
            e = e.fillna(False).astype(bool).values
            for sd in (-z, z):                                           # -z reversal, z continuation
                if sd not in sides:
                    continue
                S["RSI", f"{name}:{'reversal' if sd == -z else 'continuation'}", f"zone{zone}", sd] = e
                for cn, cm in extra.items():
                    S["RSI", f"{name}:{'reversal' if sd == -z else 'continuation'}", f"zone{zone}|{cn}", sd] = e & cm
    for key, e in D.items():
        if key[0].startswith("_") or key[2] not in sides:
            continue
        ind, kind, side = key
        rp = D["_rsi_at_pivot", side]
        cand = (bull if side > 0 else bear).rolling(K).max().fillna(0).astype(bool).values
        ctx = {"none": np.ones(n, bool), "rsi_extreme": (rp <= 30) if side > 0 else (rp >= 70),
               "volume_1.5x": (rv >= 1.5).fillna(False).values, "reversal_candle": cand}
        ctx.update(extra)
        for cn, cm in ctx.items():
            S["DIV", f"{ind}:{kind}", cn, side] = e & cm
    lo5, hi5 = l.rolling(5).min(), h.rolling(5).max()
    risk = {1: (c - lo5 + 0.1 * atr).clip(lower=0.5 * atr, upper=3 * atr).values,
            -1: (hi5 - c + 0.1 * atr).clip(lower=0.5 * atr, upper=3 * atr).values}
    return S, risk


@njit(cache=True)
def sim(o, h, l, c, sig, side, risk, R, grp, hold, costf, expid):
    """-> entry idx, exit idx, net R, gross R, cost R. One open trade per grp at a time; costf = round-trip cost as a
    fraction of the entry price; a trade whose exit contract id differs from the entry's pays costf once more (roll)."""
    n = len(c)
    ei = np.empty(n, np.int64); xi = np.empty(n, np.int64); nr = np.empty(n); gr = np.empty(n); cr = np.empty(n)
    m = 0; t = 0
    while t < n - 2:
        if not sig[t] or not np.isfinite(risk[t]) or risk[t] <= 0 or grp[t + 1] != grp[t]:
            t += 1; continue
        e = t + 1; px = o[e]; rk = risk[t]
        st = px - side * rk; tp = px + side * R * rk
        j = e; x = np.nan
        while j < n:
            if grp[j] != grp[e]:
                j -= 1; x = c[j]; break
            if j > e and ((side > 0 and o[j] <= st) or (side < 0 and o[j] >= st)):
                x = o[j]; break
            if j > e and ((side > 0 and o[j] >= tp) or (side < 0 and o[j] <= tp)):
                x = o[j]; break
            if (side > 0 and l[j] <= st) or (side < 0 and h[j] >= st):
                x = st; break
            if (side > 0 and h[j] >= tp) or (side < 0 and l[j] <= tp):
                x = tp; break
            if j - e + 1 >= hold or j == n - 1 or grp[j + 1] != grp[j]:
                x = c[j]; break
            j += 1
        if np.isnan(x):
            break
        cost = costf[e] * px * (2.0 if expid[j] != expid[e] else 1.0)
        g = side * (x - px)
        ei[m] = e; xi[m] = j; gr[m] = g / rk; cr[m] = cost / rk; nr[m] = (g - cost) / rk
        m += 1
        t = j + 1
    return ei[:m], xi[:m], nr[:m], gr[:m], cr[:m]


class Pool:
    """Concatenates instruments; keeps, per signal key, the global indices where it fires."""

    def __init__(self):
        self.parts, self.idx, self.n, self.risk = [], {}, 0, {1: [], -1: []}

    def add(self, b, S, risk, gid, costf, expid, name):
        m = len(b)
        self.parts.append(pd.DataFrame(dict(time=b["time"].values, open=b["open"].values, high=b["high"].values, low=b["low"].values,
                                            close=b["close"].values, grp=gid, costf=costf, expid=expid, name=name)))
        for s in (1, -1):
            self.risk[s].append(risk[s])
        for k, e in S.items():
            w = np.where(e)[0]
            if len(w):
                self.idx.setdefault(k, []).append(w + self.n)
        self.n += m

    def freeze(self):
        P = pd.concat(self.parts, ignore_index=True); self.parts = None
        self.o, self.h, self.l, self.c = (P[x].values.astype(float) for x in ("open", "high", "low", "close"))
        self.grp = P["grp"].values.astype(np.int64); self.costf = P["costf"].values.astype(float)
        self.expid = P["expid"].values.astype(np.int64); self.t = P["time"].values; self.name = P["name"].values
        self.rk = {s: np.concatenate(self.risk[s]).astype(float) for s in (1, -1)}
        self.idx = {k: np.concatenate(v) for k, v in self.idx.items()}
        return self

    def run(self, key, R, hold, mask=None):
        sd = key[-1]
        sig = np.zeros(self.n, np.bool_); sig[self.idx[key]] = True
        if mask is not None:
            sig &= mask
        ei, xi, nr, gr, cr = sim(self.o, self.h, self.l, self.c, sig, sd, self.rk[sd], R, self.grp, hold, self.costf, self.expid)
        return pd.DataFrame(dict(i=ei, name=self.name[ei], entry=self.t[ei], exit=self.t[xi], bars=xi - ei + 1, netR=nr, grossR=gr, costR=cr,
                                 ret=nr * self.rk[sd][ei - 1] / np.where(self.o[ei] > 0, self.o[ei], np.nan)))


def periods(t, cuts):
    """cuts: [(label, start)] ascending -> label per time."""
    lab = np.full(len(t), cuts[0][0], dtype=object)
    for name, start in cuts[1:]:
        lab[t >= np.datetime64(start)] = name
    return lab


def stats(r):
    if not len(r):
        return dict(n=0, win=np.nan, R=np.nan, PF=np.nan)
    w = r > 0; gp, gl = r[w].sum(), -r[~w].sum()
    return dict(n=len(r), win=round(100 * w.mean(), 1), R=round(float(r.mean()), 3), PF=round(min(gp / gl, 99), 2) if gl > 0 else 99.0)


def row(key, T, cuts, min_each=30, min_total=100):
    fam, ev, ctx, sd = key
    out = dict(family=fam, event=ev, context=ctx, side="BUY" if sd > 0 else "SELL")
    lab = periods(T.entry.values, cuts)
    for p, _ in cuts:
        out.update({f"{p}_{k}": v for k, v in stats(T.netR.values[lab == p]).items()})
    out.update({f"all_{k}": v for k, v in stats(T.netR.values).items()})
    out["costR"] = round(float(T.costR.mean()), 3) if len(T) else np.nan
    out["avg_ret_pct"] = round(100 * float(T.ret.mean()), 3) if len(T) else np.nan
    # entries on the same day are not independent: t-statistic on the mean R per ENTRY DAY
    if len(T) > 2:
        dm = T.groupby(pd.to_datetime(T.entry).dt.normalize()).netR.mean()
        sd_ = dm.std(ddof=1)
        out["t_day"] = round(dm.mean() / (sd_ / np.sqrt(len(dm))), 2) if sd_ > 0 and len(dm) > 2 else np.nan
        out["days"] = len(dm)
    else:
        out["t_day"], out["days"] = np.nan, len(T)
    out["names"] = T.name.nunique() if len(T) else 0
    out["names_pos"] = int((T.groupby("name").netR.mean() > 0).sum()) if len(T) else 0
    out["PASS"] = bool(len(T) >= min_total and all(out[f"{p}_n"] >= min_each and out[f"{p}_R"] > 0 and out[f"{p}_PF"] >= 1.2 for p, _ in cuts))
    return out


def pvals(t):
    from math import erf, sqrt
    return np.array([1 - 0.5 * (1 + erf(x / sqrt(2))) if np.isfinite(x) else 1.0 for x in t])


def bh(p, q=0.10):
    p = np.asarray(p); m = len(p); o = np.argsort(p)
    ok = p[o] <= q * np.arange(1, m + 1) / m
    kmax = np.where(ok)[0].max() + 1 if ok.any() else 0
    f = np.zeros(m, bool); f[o[:kmax]] = True
    return f


def holm(p, a=0.05):
    p = np.asarray(p); m = len(p); o = np.argsort(p); f = np.zeros(m, bool)
    for i, j in enumerate(o):
        if p[j] <= a / (m - i):
            f[j] = True
        else:
            break
    return f


def evaluate(pool, keys, cuts, holds, tf, market, keep_top=25):
    """run every key x target; multiple-testing flags; re-runs the PASS and the best keep_top variants to keep their trades."""
    rows = []
    for key in keys:
        for R in RS:
            T = pool.run(key, R, holds)
            if len(T) < 10:
                continue
            rw = row(key, T, cuts); rw.update(market=market, tf=tf, target_R=R, delay_bars=K_BY_TF[tf] if key[0] == "DIV" else 0)
            rows.append(rw)
    L = pd.DataFrame(rows)
    if not len(L):
        return L, pd.DataFrame()
    p = pvals(L.t_day.values)
    L["p_day"] = p; L["FDR10"] = bh(p, 0.10); L["HOLM5"] = holm(p, 0.05)
    L["exp_max_t_null"] = round(float(np.sqrt(2 * np.log(len(L)))), 2)
    want = pd.concat([L.sort_values("t_day", ascending=False).head(keep_top), L[L.PASS]]).drop_duplicates(["family", "event", "context", "side", "target_R"])
    trades = []
    for r in want.itertuples():
        key = (r.family, r.event, r.context, 1 if r.side == "BUY" else -1)
        trades.append(pool.run(key, r.target_R, holds).assign(market=market, tf=tf, family=r.family, event=r.event, context=r.context,
                                                              side=r.side, target_R=r.target_R))
    return L, pd.concat(trades, ignore_index=True)


def baselines(pool, cuts, holds, tf, market, sides=(1, -1), every=10):
    """same stop / targets, entry every `every` bars – what the market drift alone gives."""
    out = []
    every_sig = np.zeros(pool.n, np.bool_); every_sig[::every] = True
    for sd in sides:
        key = ("BASE", f"every_{every}th_bar", "none", sd)
        pool.idx[key] = np.where(every_sig)[0]
        for R in RS:
            T = pool.run(key, R, holds)
            rw = row(key, T, cuts); rw.update(market=market, tf=tf, target_R=R, delay_bars=0); out.append(rw)
    return pd.DataFrame(out)
