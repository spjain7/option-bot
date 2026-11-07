"""MCXE-007 daily trade engine (research only). One side per run; one position per instrument; OOS masked unless oos=True.
Entry modes: 'open'  – close-confirmed signal at bar i, market entry at the open of bar i+1.
             'stop'  – stop order at LEVEL[i] valid only during bar i+1: fills at the open if the bar opens through the
                       level (gap-through), else at the level if the bar's range reaches it, else cancelled. If the
                       protective stop also lies inside that bar's range the trade is assumed stopped (worst case).
chase: cancel if the fill is beyond the reference level by more than chase x ATR (no-chase rule), level = LEVEL[i].
Stops: dist (k x ATR from the fill) or a structural price STOP[i] (swing stop). Exits: target R, ATR trail on closes,
partial at tgt1R (+ breakeven), time cap (iend: maxbars or the bar before the next roll)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe003 import cost_model as CM, bootstrap as BT  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402
from crude import indicators as I  # noqa: E402

ETYPE = np.array(["time", "stop", "target", "trail", "gap", "breakeven", "stop_fillbar"])


@njit(cache=True)
def _sim(o, h, l, c, i, side, mode, level, chase, stop_px, dist, iend, cost, atr, tgt1R, pfrac, be, tgtR, trail):
    nan = np.nan
    k0 = i + 1
    if k0 > iend or k0 >= len(c) or o[k0] != o[k0]:
        return nan, nan, -1.0, -1.0, nan, nan, -1.0, nan, nan
    if mode == 0:
        e = o[k0]
    else:
        if side > 0:
            if o[k0] >= level:
                e = o[k0]
            elif h[k0] >= level:
                e = level
            else:
                return nan, nan, -2.0, -1.0, nan, nan, -1.0, nan, nan       # not triggered
        else:
            if o[k0] <= level:
                e = o[k0]
            elif l[k0] <= level:
                e = level
            else:
                return nan, nan, -2.0, -1.0, nan, nan, -1.0, nan, nan
    if chase > 0 and level == level and side * (e - level) > chase * atr:
        return nan, nan, -3.0, -1.0, nan, nan, -1.0, nan, nan               # chased gap -> cancelled
    st = stop_px if stop_px == stop_px else e - side * dist
    R = side * (e - st)
    if not R > 0:
        return nan, nan, -4.0, -1.0, nan, nan, -1.0, nan, nan               # opened beyond the stop
    st0 = st; realized = 0.0; rem = 1.0; done1 = False; best = e; mae = 0.0; mfe = 0.0
    t1 = e + side * tgt1R * R; tg = e + side * tgtR * R
    px = nan; kx = iend; et = 0; pend_be = False
    for k in range(k0, iend + 1):
        if pend_be:
            st = max(st, e) if side > 0 else min(st, e)
            pend_be = False
        if k > k0 and ((side > 0 and o[k] <= st) or (side < 0 and o[k] >= st)):
            px = o[k]; kx = k; et = 4; break
        if (side > 0 and l[k] <= st) or (side < 0 and h[k] >= st):
            px = st; kx = k
            if k == k0:
                et = 6 if mode == 1 else 1
                if mode == 0 and ((side > 0 and o[k] <= st) or (side < 0 and o[k] >= st)):
                    px = o[k]
            elif st == st0:
                et = 1
            elif abs(st - e) <= 1e-9 * abs(e):
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
        if trail > 0 and atr > 0:
            if side > 0:
                best = max(best, c[k]); st = max(st, best - trail * atr)
            else:
                best = min(best, c[k]); st = min(st, best + trail * atr)
    if px != px:
        px = c[iend]; kx = iend; et = 0
    g = realized + rem * side * (px - e) / R
    return g - cost / R, g, float(kx), float(k0), mae, mfe, float(et), e, R


@njit(cache=True)
def _run(o, h, l, c, I, side, mode, LV, chase, STOP, DIST, IEND, COST, ATR, tgt1R, pfrac, be, tgtR, trail):
    m = len(I)
    out = np.full((m, 10), np.nan)
    busy = -1
    for q in range(m):
        i = I[q]
        if i <= busy:
            out[q, 9] = -5.0                                                 # position open
            continue
        r = _sim(o, h, l, c, i, side, mode, LV[q], chase, STOP[q], DIST[q], IEND[q], COST[q], ATR[q], tgt1R, pfrac, be, tgtR, trail)
        if r[2] < 0:
            out[q, 9] = r[2]
            continue
        for j in range(9):
            out[q, j] = r[j]
        out[q, 9] = 0.0
        busy = int(r[2])
    return out


def iend_positional(f, maxbars):
    n = len(f); roll = np.asarray(f["roll"].values, bool)
    nxt = np.full(n, n, np.int64); j = n
    for i in range(n - 1, -1, -1):
        nxt[i] = j
        if roll[i]:
            j = i
    return np.minimum(np.minimum(np.arange(n) + maxbars, nxt - 1), n - 1).astype(np.int64)


def costs(f, px):
    k = f.attrs.get("kind")
    if k == "MCX":
        from research.program import mcx_disc as MD
        return np.array([MD.real_cost(f.attrs["name"], p) for p in px])
    if k == "IDX":
        from research import instruments as INS
        return np.array([INS.cost_points(f.attrs["name"], p) for p in px])
    return px * CM.FUT_FRAC


def regime(f):
    c = f.close.astype(float)
    adx = I.adx(f, 14).values
    e20 = c.ewm(span=20, adjust=False).mean().values
    return np.where(adx < 20, "range", np.where(c.values > e20, "up", "down"))


STATUS = {-2: "not_triggered", -3: "cancelled_chase", -4: "opened_beyond_stop", -5: "position_open", -1: "no_entry_bar"}


def run(fs, sigfn, params, exitp, side, oos=False, extra=None, entry="open", chase=0.0, log_signals=False):
    rows, sigs = [], []
    for f in fs:
        if f is None or len(f) < 60:
            continue
        s = sigfn(f, side=side, extra=extra, **params)
        sig = np.asarray(s["sig"], bool)
        n = len(f); idx = np.arange(n)
        per = np.asarray(W.period(f.time, f.attrs["wkey"]))
        a = f.atr.values.astype(float)
        ok = sig & f.sig_ok.values.astype(bool) & (idx >= s.get("warm", 30)) & np.isfinite(a) & (a > 0) & (idx < n - 1)
        if not oos:
            ok &= per != "OOS"
        IE = iend_positional(f, exitp.get("maxbars", 40))
        if not oos:
            last = np.flatnonzero(per != "OOS").max()
            IE = np.minimum(IE, last)
        ok &= IE > idx
        I_ = np.flatnonzero(ok).astype(np.int64)
        if not len(I_):
            continue
        o, h, l, c = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
        lv = np.asarray(s.get("level", np.full(n, np.nan)), float)[I_]
        stp = np.asarray(s.get("stop", np.full(n, np.nan)), float)[I_]
        dist = exitp.get("k", 2.0) * a[I_]
        cst = costs(f, c[I_])
        res = _run(o, h, l, c, I_, int(side), 1 if (s.get("entry", entry) == "stop") else 0, lv, float(s.get("chase", chase)), stp, dist,
                   IE[I_], cst, a[I_], float(exitp.get("tgt1R", 0)), float(exitp.get("pfrac", 0.5)), bool(exitp.get("be", False)),
                   float(exitp.get("tgtR", 0)), float(exitp.get("trail", 0)))
        if log_signals:
            sigs.append(pd.DataFrame(dict(inst=f.attrs["name"], date=f.time.values[I_], period=per[I_],
                                          status=[("trade" if x == 0 else STATUS.get(int(x), "?")) for x in res[:, 9]])))
        m = res[:, 9] == 0
        if not m.any():
            continue
        r = res[m]; ii = I_[m]
        k0 = r[:, 3].astype(int); kx = r[:, 2].astype(int)
        e, R = r[:, 7], r[:, 8]
        cost_R = r[:, 1] - r[:, 0]
        raw_e = f.raw_close.values[ii] * (e / c[ii]) if "raw_close" in f else e    # raw (unadjusted) entry price
        risk_pct = R / e
        if f.attrs.get("kind") == "MCX":
            rs_per_R = R * f.attrs["mult"]
        else:
            lot = f.attrs.get("lot") or np.nan
            rs_per_R = risk_pct * raw_e * lot
        reg = regime(f)
        rows.append(pd.DataFrame(dict(
            market=f.attrs.get("kind"), inst=f.attrs["name"], side=int(side), date=f.time.values[ii], entry_date=f.time.values[k0],
            exit_date=f.time.values[kx], period=per[ii], r1=r[:, 0], r2=r[:, 0] - cost_R, gross=r[:, 1], cost_R=cost_R,
            mae=r[:, 4], mfe=r[:, 5], etype=ETYPE[r[:, 6].astype(int)], hold=kx - k0, regime=reg[ii],
            entry_px=e, risk_pts=R, risk_pct=risk_pct, rs_per_R=rs_per_R, rs_net_1x=r[:, 0] * rs_per_R)))
    T = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["inst", "date", "period", "r1", "r2", "side"])
    if len(T):
        for col in ("date", "entry_date", "exit_date"):
            T[col] = pd.to_datetime(T[col])
        T = T.sort_values("date").reset_index(drop=True)
    S = pd.concat(sigs, ignore_index=True) if sigs else None
    return (T, S) if log_signals else T


# ───── metrics ─────
def metrics(T, col="r1", B=2000):
    x = T[col].astype(float).values if len(T) else np.array([])
    if not len(x):
        return dict(n=0, dates=0)
    w, lo = x[x > 0], x[x <= 0]
    eq = np.cumsum(x); dd = float((np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max())
    d = pd.to_datetime(T.date).values
    ci = BT.block_ci(d, x, B=B)["ci95_conservative"] if len(x) > 5 else [np.nan, np.nan]
    s = np.sort(x)
    return dict(n=len(x), dates=int(pd.Series(d).dt.normalize().nunique()), win=round(100 * len(w) / len(x), 1),
                avg_win=round(float(w.mean()), 3) if len(w) else np.nan, avg_loss=round(float(lo.mean()), 3) if len(lo) else np.nan,
                exp=round(float(x.mean()), 4), pf=round(float(w.sum() / -lo.sum()), 3) if lo.sum() < 0 else np.nan,
                dd=round(dd, 2), net=round(float(x.sum()), 2), ci_lo=round(float(ci[0]), 3), ci_hi=round(float(ci[1]), 3),
                wo_top1=round(float(s[:-1].mean()), 4) if len(s) > 1 else np.nan,
                wo_top3=round(float(s[:-3].mean()), 4) if len(s) > 3 else np.nan,
                wo_top5=round(float(s[:-5].mean()), 4) if len(s) > 5 else np.nan)


def concentration(T, col="r2"):
    if not len(T) or T[col].sum() <= 0:
        return dict(max_inst_share=np.nan, top_inst=None, max_month_share=np.nan)
    tot = T[col].sum()
    bi = T.groupby("inst")[col].sum(); bm = T.groupby(T.date.dt.to_period("M"))[col].sum()
    return dict(max_inst_share=round(float(bi.max() / tot), 3), top_inst=bi.idxmax(), max_month_share=round(float(bm.max() / tot), 3))
