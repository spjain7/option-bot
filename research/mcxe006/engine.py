"""MCXE-006 engine: cached in-window frames, a numba trade simulator with partial profit-taking / breakeven / trailing /
time exits and MFE-MAE, OOS masking, and metrics. Research only – nothing here can send alerts or place orders.

Development mode (default): every signal in the OOS period is dropped and every exit is capped at the last non-OOS bar,
so OOS prices are never used. oos.py calls run(..., oos=True) once for the frozen list."""
import pickle
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe003 import cost_model as CM, bootstrap as BT  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402
from research.mcxe005 import frames as FR  # noqa: E402
from crude import indicators as I  # noqa: E402

CACHE = ROOT / "research/mcxe006/cache"
ETYPE = np.array(["time", "stop", "target", "trail", "gap", "breakeven", "overnight", "signal"])
WKEY = {"MCX": "MCX", "NSE_FUT_D": "NSE_FUT", "NSE_EQ_D": "NSE_EQ", "NSE_EQ_I": "NSE_EQ_INTRADAY", "NSE_FUT_I": "NSE_FUT_INTRADAY"}


# ───────────────────────────── frames (cached; all clipped to the window before indicators) ─────────────────────────────
def _cached(key, fn):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{key}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    x = fn()
    p.write_bytes(pickle.dumps(x))
    return x


def frames(universe, tf):
    """universe: MCX | NSE_FUT_D | NSE_EQ_D | NSE_EQ_I | NSE_FUT_I -> list of frames (attrs: market, name, tf, wkey)."""
    def build():
        if universe == "MCX":
            out = []
            for n in FR.MCX7:
                b = FR.mcx_base(n)
                f = FR.mcx_intraday(n, tf, b) if tf in (15, 30) else FR.mcx_positional(n, tf, b)
                out.append(f)
            return out
        if universe == "NSE_FUT_D":
            return FR.fut_daily()
        if universe == "NSE_EQ_D":
            return FR.eq_daily()
        if universe == "NSE_EQ_I":
            from research.mcxe003 import bars as B
            return [f for f in (FR.eq_intraday(s, tf) for s in B.nse_eq_symbols()) if f is not None and len(f) > 300]
        if universe == "NSE_FUT_I":
            return [f for f in (FR.fut_intraday(p.name.split("_ONE_HOUR")[0])
                                for p in sorted((ROOT / "research/data/angel/NFO_STK").glob("*_ONE_HOUR.csv"))) if f is not None]
        raise ValueError(universe)
    fs = _cached(f"{universe}_{tf}", build)
    for f in fs:
        f.attrs["wkey"] = WKEY[universe]; f.attrs["universe"] = universe
    return fs


def breadth(fs, n=50):
    """market breadth per date: share of instruments whose close > EMA(n) (causal, value known at that close)."""
    rows = []
    for f in fs:
        c = f.close.astype(float)
        rows.append(pd.Series((c > c.ewm(span=n, adjust=False).mean()).astype(float).values, index=f.time.dt.normalize().values))
    B = pd.concat(rows, axis=1)
    cnt = B.notna().sum(axis=1)
    return (B.mean(axis=1)).where(cnt >= 20)


# ───────────────────────────── simulator ─────────────────────────────
@njit(cache=True)
def _sim(o, h, l, c, i, side, stop_px, dist, iend, cost, atr, tgt1R, pfrac, be, tgtR, trail, xl, xs):
    nan = np.nan
    n = len(c)
    k0 = i + 1
    if k0 >= n or k0 > iend:
        return nan, nan, -1, -1, nan, nan, -1
    e = o[k0]
    if e != e:
        return nan, nan, -1, -1, nan, nan, -1
    st = stop_px if stop_px == stop_px else e - side * dist
    R = side * (e - st)
    if not R > 0:
        return nan, nan, -1, -1, nan, nan, -1
    st0 = st
    realized = 0.0; rem = 1.0; done1 = False; best = e; mae = 0.0; mfe = 0.0
    t1 = e + side * tgt1R * R if tgt1R > 0 else nan
    tg = e + side * tgtR * R if tgtR > 0 else nan
    px = nan; kx = iend; et = 0
    pend_be = False
    for k in range(k0, iend + 1):
        if pend_be:
            st = max(st, e) if side > 0 else min(st, e)
            pend_be = False
        if k > k0 and ((side > 0 and o[k] <= st) or (side < 0 and o[k] >= st)):
            px = o[k]; kx = k; et = 4; break
        if (side > 0 and l[k] <= st) or (side < 0 and h[k] >= st):
            px = st; kx = k
            if k == k0 and ((side > 0 and o[k] <= st) or (side < 0 and o[k] >= st)):
                px = o[k]
            if st == st0:
                et = 1
            elif (st - e) * side >= -1e-12 and (st - e) * side <= 1e-9 * abs(e):
                et = 5
            else:
                et = 3
            break
        fav = (h[k] - e) if side > 0 else (e - l[k])
        adv = (e - l[k]) if side > 0 else (h[k] - e)
        mfe = max(mfe, fav / R); mae = max(mae, adv / R)
        if k > k0 and tgt1R > 0 and not done1:
            if (side > 0 and h[k] >= t1) or (side < 0 and l[k] <= t1):
                p1 = max(t1, o[k]) if side > 0 else min(t1, o[k])
                realized += pfrac * side * (p1 - e) / R; rem = 1.0 - pfrac; done1 = True
                if be:
                    pend_be = True
        if k > k0 and tgtR > 0:
            if (side > 0 and h[k] >= tg) or (side < 0 and l[k] <= tg):
                px = max(tg, o[k]) if side > 0 else min(tg, o[k]); kx = k; et = 2; break
        if k < iend and ((side > 0 and xl[k]) or (side < 0 and xs[k])):
            px = c[k]; kx = k; et = 7; break
        if trail > 0 and atr > 0:
            if side > 0:
                best = max(best, c[k]); st = max(st, best - trail * atr)
            else:
                best = min(best, c[k]); st = min(st, best + trail * atr)
    if px != px:
        px = c[iend]; kx = iend; et = 0
    g = realized + rem * side * (px - e) / R
    return g - cost / R, g, kx, k0, mae, mfe, et


@njit(cache=True)
def _run(o, h, l, c, I, S, STOP, DIST, IEND, COST, ATR, tgt1R, pfrac, be, tgtR, trail, xl, xs):
    m = len(I)
    out = np.full((m, 8), np.nan)
    busy = -1
    for q in range(m):
        if I[q] <= busy:
            continue
        r = _sim(o, h, l, c, I[q], S[q], STOP[q], DIST[q], IEND[q], COST[q], ATR[q], tgt1R, pfrac, be, tgtR, trail, xl, xs)
        if r[2] < 0:
            continue
        out[q, 0] = r[0]; out[q, 1] = r[1]; out[q, 2] = r[2]; out[q, 3] = r[3]
        out[q, 4] = r[4]; out[q, 5] = r[5]; out[q, 6] = r[6]
        out[q, 7] = COST[q]
        busy = r[2]
    return out


def costs(f, idx, kind):
    m, name = f.attrs["market"], f.attrs["name"]
    px = f.close.values[idx].astype(float)
    if m == "MCX":
        return np.array([CM.cost_points("MCX", name, p) for p in px], float)
    if m == "NSE_EQ":
        return np.asarray(CM.cost_points("NSE_EQ", name, px, kind=kind), float)
    return np.asarray(CM.cost_points("NSE_FUT", name, px), float)


def iend_positional(f, maxbars):
    n = len(f)
    roll = np.asarray(f["roll"].values, bool)
    nxt = np.full(n, n, np.int64)
    j = n
    for i in range(n - 1, -1, -1):
        nxt[i] = j
        if roll[i]:
            j = i
    return np.minimum(np.minimum(np.arange(n) + maxbars, nxt - 1), n - 1).astype(np.int64)


def iend_session(f, squareoff_min=None):
    dl = f.dlast.values.astype(np.int64)
    if squareoff_min is None:
        return dl
    endm = (f.end.dt.hour * 60 + f.end.dt.minute).values
    idx = np.arange(len(f))
    last_ok = pd.Series(np.where(endm <= squareoff_min, idx, np.nan)).groupby(f.day.values).transform("max").values
    return np.where(np.isfinite(last_ok), last_ok, dl).astype(np.int64)


def run(fs, sigfn, params, exitp, horizon, oos=False, cost_kind=None, extra=None):
    """sigfn(f, **params, extra=extra) -> dict(side=int array, stop=price array (nan = use dist), dist=price array,
    warm=int bars). exitp: dict(tgt1R, pfrac, be, tgtR, trail (ATR mult), maxbars, squareoff (min), overnight 'open'/'close').
    Returns trades DataFrame."""
    rows = []
    kind = cost_kind or ("intraday" if horizon == "intraday" else "delivery")
    for f in fs:
        if f is None or len(f) < 80:
            continue
        s = sigfn(f, extra=extra, **params)
        side = np.asarray(s["side"], np.int64)
        n = len(f); idx = np.arange(n)
        per = np.asarray(W.period(f.time, f.attrs["wkey"]))
        a = f.atr.values.astype(float)
        ok = (side != 0) & f.sig_ok.values.astype(bool) & (idx >= s.get("warm", 60)) & np.isfinite(a) & (a > 0) & (idx < n - 1)
        if not oos:
            ok &= per != "OOS"
        if horizon == "intraday":
            IE = iend_session(f, exitp.get("squareoff"))
        elif horizon == "positional":
            IE = iend_positional(f, exitp.get("maxbars", 20))
        else:
            IE = idx + 1
            nr = np.r_[np.asarray(f["roll"].values, bool)[1:], True]
            ok &= ~nr
        if not oos:
            nonoos = np.flatnonzero(per != "OOS")
            last_dev = nonoos.max() if len(nonoos) else -1
            IE = np.minimum(IE, last_dev)
        ok &= IE > idx
        I_ = np.flatnonzero(ok).astype(np.int64)
        if not len(I_):
            continue
        o, h, l, c = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
        cst = costs(f, I_, kind)
        if horizon == "overnight":
            j = I_ + 1
            ex = o[j] if exitp.get("overnight", "open") == "open" else c[j]
            Rp = np.asarray(s["dist"], float)[I_]
            g = side[I_] * (ex - c[I_]) / Rp
            res = np.c_[g - cst / Rp, g, j, I_, np.full(len(I_), np.nan), np.full(len(I_), np.nan), np.full(len(I_), 6), cst]
            ent_px = c[I_]
        else:
            stop = np.asarray(s.get("stop", np.full(n, np.nan)), float)[I_]
            dist = np.asarray(s["dist"], float)[I_]
            res = _run(o, h, l, c, I_, side[I_], stop, dist, IE[I_], cst, a[I_],
                       float(exitp.get("tgt1R", 0)), float(exitp.get("pfrac", 0.5)), bool(exitp.get("be", False)),
                       float(exitp.get("tgtR", 0)), float(exitp.get("trail", 0)),
                       np.asarray(s.get("xl", np.zeros(n, bool)), np.bool_), np.asarray(s.get("xs", np.zeros(n, bool)), np.bool_))
            ent_px = None
        m = ~np.isnan(res[:, 0])
        if not m.any():
            continue
        r = res[m]; ii = I_[m]
        # R in price for cost-at-2x: net2 = net1 - cost/R
        R_px = (r[:, 1] - r[:, 0])
        cost_R = R_px  # = cost / R
        rows.append(pd.DataFrame(dict(
            inst=f.attrs["name"], tf=f.attrs["tf"], side=side[ii], date=f.time.values[ii], period=per[ii],
            r1=r[:, 0], r2=r[:, 0] - cost_R, gross=r[:, 1], cost_R=cost_R, mae=r[:, 4], mfe=r[:, 5],
            etype=ETYPE[r[:, 6].astype(int)], hold=(r[:, 2] - r[:, 3]).astype(int), sig_i=ii,
            regime=(extra or {}).get("regime_fn", _regime)(f)[ii])))
    if not rows:
        return pd.DataFrame(columns=["inst", "tf", "side", "date", "period", "r1", "r2", "gross", "cost_R", "mae", "mfe", "etype", "hold"])
    T = pd.concat(rows, ignore_index=True)
    T["date"] = pd.to_datetime(T.date)
    return T.sort_values("date").reset_index(drop=True)


def _regime(f):
    c = f.close.astype(float)
    adx = I.adx(f, 14).values
    e50 = c.ewm(span=50, adjust=False).mean().values
    return np.where(adx < 20, "range", np.where(c.values > e50, "up", "down"))


# ───────────────────────────── metrics ─────────────────────────────
def metrics(T, col="r1"):
    x = T[col].astype(float).values if len(T) else np.array([])
    if not len(x):
        return dict(n=0, dates=0)
    w, lo = x[x > 0], x[x <= 0]
    eq = np.cumsum(x); dd = float((np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max())
    d = pd.to_datetime(T.date).values
    ci = BT.block_ci(d, x, B=2000)["ci95_conservative"] if len(x) > 5 else [np.nan, np.nan]
    return dict(n=len(x), dates=int(pd.Series(d).dt.normalize().nunique()), win=round(100 * len(w) / len(x), 1),
                avg_win=round(float(w.mean()), 3) if len(w) else np.nan, avg_loss=round(float(lo.mean()), 3) if len(lo) else np.nan,
                exp=round(float(x.mean()), 4), pf=round(float(w.sum() / -lo.sum()), 3) if lo.sum() < 0 else np.nan,
                dd=round(dd, 2), net=round(float(x.sum()), 2),
                ci_lo=round(float(ci[0]), 3), ci_hi=round(float(ci[1]), 3))


def summary(T, periods=("DEV", "VALID")):
    out = {}
    for P in periods:
        x = T[T.period == P] if len(T) else T
        m1, m2 = metrics(x, "r1"), metrics(x, "r2")
        out[P] = dict(m1, exp2=m2.get("exp"), cost_R=round(float(x.cost_R.mean()), 3) if len(x) else np.nan,
                      gross=round(float(x.gross.mean()), 3) if len(x) else np.nan,
                      stop_pct=round(100 * x.etype.isin(["stop", "gap"]).mean(), 1) if len(x) else np.nan,
                      tgt_pct=round(100 * (x.etype == "target").mean(), 1) if len(x) else np.nan,
                      buy_exp2=round(float(x[x.side > 0].r2.mean()), 3) if (len(x) and (x.side > 0).any()) else np.nan,
                      sell_exp2=round(float(x[x.side < 0].r2.mean()), 3) if (len(x) and (x.side < 0).any()) else np.nan,
                      n_buy=int((x.side > 0).sum()) if len(x) else 0, n_sell=int((x.side < 0).sum()) if len(x) else 0)
    if len(periods) > 1:
        x = T[T.period.isin(periods)]
        m = metrics(x, "r1")
        out["DV"] = dict(n=m.get("n", 0), exp=m.get("exp"), ci_lo=m.get("ci_lo"), ci_hi=m.get("ci_hi"), dates=m.get("dates", 0))
    return out
