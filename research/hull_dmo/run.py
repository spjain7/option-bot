"""HULL-DMO – MCX intraday calls from the owner's two TradingView scripts (12-Nov-2026). Research only.

Indicators reproduced exactly from the Pine code:
  Hull Trend (v4): a = WMA(2*WMA(hl2, L/2) - WMA(hl2, L), round(sqrt(L)));  p = L/2;
                   b = WMA(WMA(close, p/3)*3 - WMA(close, p/2) - WMA(close, p), p)   (v4 integer division -> floor)
                   BUY  = b crosses above a (b > a and b[1] < a[1]);  SELL = a crosses above b.  Signal on the CLOSED bar.
  DMO (v5):        dmo = (close - close[n]) / (highest(high, n) - lowest(low, n)); optional linreg(dmo, 8, 0) smoothing;
                   threshold 0.3; upward momentum = dmo crosses above 0; OB signal = crosses above +0.3 (alternating with
                   OS = crosses below -0.3).
Combinations (BUY shown; SELL mirrored):
  C1 HULL        Hull BUY cross alone
  C2 HULL+DMO0   Hull BUY cross and DMO > 0 on the same bar
  C3 HULL+DMO.3  Hull BUY cross and DMO > +0.3
  C4 DMO0@HULL   DMO crosses above 0 while Hull is green (b > a)
  C5 BOTH<=3     Hull BUY cross and DMO zero-cross up within 3 bars of each other (signal on the later one)
  C6 OB@HULL     DMO OB signal (cross above +0.3, alternating) while Hull is green
Exits (both tested): X1 = opposite Hull cross (exit next open) with a 2-ATR protective stop; X2 = stop 5-bar low/high
 +/- 0.1 ATR (0.5–3 ATR) and a 2R target. ALL trades are intraday: entries 09:15–22:30, flat at the last bar before
23:30 (MCX session end); stop checked first; gaps fill at the open; never across a contract switch.
Grid: timeframes 5m / 15m / 30m / 1h x Hull length 12, 16, 20, 24, 30, 36, 40, 48, 60 x DMO (14), (14 smoothed), (10),
(20) x 6 combos x 2 exits x BUY / SELL = 3,456 tests on 7 commodities, real MCX fees + 1.5 ticks slippage per side.
Periods: DEV 2023–2024 · VALID 2025 · OOS 2026 (to 3-Nov). Gate: profit and PF >= 1.2 in each, >= 30 trades each,
>= 100 total; BH-FDR 10 % over all 3,456 tests; Hull-length stability (neighbouring lengths) reported.
python -m research.hull_dmo.run  ->  results/hull_dmo_grid.csv"""
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD  # noqa: E402
from research.mcxhw.search import bars  # noqa: E402
from research.rsidiv import engine as E  # noqa: E402
from research.cycle2 import common as C  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"; OUT.mkdir(parents=True, exist_ok=True)
TFS = {"5m": 5, "15m": 15, "30m": 30, "1h": 60}
HULL = (12, 16, 20, 24, 30, 36, 40, 48, 60)
DMOS = (("14", 14, False), ("14s", 14, True), ("10", 10, False), ("20", 20, False))
CUTS = [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")]


def wma(x, n):
    """Pine ta.wma: weights 1..n, most recent bar weight n; NaN until n valid values."""
    n = int(max(n, 1)); x = np.asarray(x, float); out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    w = np.arange(1, n + 1, dtype=float)
    ok = np.isfinite(x); start = np.argmax(ok) if ok.any() else len(x)
    y = x[start:]
    if len(y) >= n and np.isfinite(y).all():
        v = np.convolve(y, w[::-1], "valid") / w.sum()
        out[start + n - 1:] = v
    else:
        s = pd.Series(x)
        out = s.rolling(n).apply(lambda z: np.dot(z, w) / w.sum(), raw=True).values
    return out


def hull(h, l, c, L):
    src = (h + l) / 2
    a = wma(2 * wma(src, L // 2) - wma(src, L), int(round(np.sqrt(L))))
    p = L // 2
    b = wma(wma(c, p // 3) * 3 - wma(c, p // 2) - wma(c, p), p)
    return a, b


def linreg(x, n):
    """Pine ta.linreg(x, n, 0): least-squares line value at the latest bar."""
    s = pd.Series(x); t = np.arange(n, dtype=float); tm = t.mean(); den = ((t - tm) ** 2).sum()

    def f(z):
        zm = z.mean(); k = ((t - tm) * (z - zm)).sum() / den
        return zm + k * (n - 1 - tm)
    return s.rolling(n).apply(f, raw=True).values


def dmo(h, l, c, n, smooth):
    rng = pd.Series(h).rolling(n).max().values - pd.Series(l).rolling(n).min().values
    d = (c - pd.Series(c).shift(n).values) / np.where(rng > 0, rng, np.nan)
    return linreg(d, 8) if smooth else d


def cross_up(x, y):
    return (x > y) & (np.r_[np.nan, x[:-1]] < np.r_[np.nan, y[:-1]])


def barssince(ev):
    out = np.full(len(ev), 10 ** 9, float); last = -1
    for i, e in enumerate(ev):
        if e:
            last = i
        out[i] = i - last if last >= 0 else 10 ** 9
    return out


def ob_os(d, th=0.3):
    obc = cross_up(d, np.full(len(d), th)); osc = cross_up(np.full(len(d), -th), d)
    bo, bs = barssince(obc), barssince(osc)
    bo1, bs1 = np.r_[10 ** 9, bo[:-1]], np.r_[10 ** 9, bs[:-1]]
    return obc & (bo1 > bs1), osc & (bs1 > bo1)


def within(e1, e2, k=3):
    """signal on the later of two events within k bars of each other."""
    n = len(e1); z = np.zeros(n, bool)
    l1 = l2 = -10 ** 9
    for i in range(n):
        if e1[i]:
            l1 = i
        if e2[i]:
            l2 = i
        if (e1[i] or e2[i]) and l1 >= 0 and l2 >= 0 and abs(l1 - l2) <= k and max(l1, l2) == i:
            z[i] = True
    return z


@njit(cache=True)
def sim_x1(o, h, l, c, sig, opp, side, risk, grp, last, costf):
    """exit at the next open after the opposite Hull cross, protective stop (risk), flat at the session's last bar."""
    n = len(c); ei = np.empty(n, np.int64); xi = np.empty(n, np.int64); nr = np.empty(n); m = 0; t = 0
    while t < n - 2:
        if not sig[t] or risk[t] <= 0 or not np.isfinite(risk[t]) or grp[t + 1] != grp[t] or last[t]:
            t += 1; continue
        e = t + 1; px = o[e]; st = px - side * risk[t]; j = e; x = np.nan
        while j < n:
            if j > e and ((side > 0 and o[j] <= st) or (side < 0 and o[j] >= st)):
                x = o[j]; break
            if (side > 0 and l[j] <= st) or (side < 0 and h[j] >= st):
                x = st; break
            if last[j] or j == n - 1 or grp[j + 1] != grp[j]:
                x = c[j]; break
            if opp[j]:
                x = o[j + 1]; j = j + 1; break
            j += 1
        if np.isnan(x):
            break
        cost = costf[e] * px
        ei[m] = e; xi[m] = j; nr[m] = (side * (x - px) - cost) / risk[t]; m += 1
        t = j + 1
    return ei[:m], xi[:m], nr[:m]


def frames(tf):
    out = []
    for g, name in enumerate(MD.NAMES):
        d5 = MD.LM.load(name, "FIVE_MINUTE"); b = bars(d5, TFS[tf])
        hm = (b["time"].dt.hour * 60 + b["time"].dt.minute).values
        b = b[(hm >= 9 * 60) & (hm < 23 * 60 + 30)].reset_index(drop=True)
        hm = (b["time"].dt.hour * 60 + b["time"].dt.minute).values
        day = b["time"].dt.normalize().values
        nxt_day = np.r_[day[1:], np.datetime64("NaT")]
        last = (nxt_day != day)                                           # last bar of the session (flat here)
        cf = MD.real_cost(name, float(d5.close.iloc[-1])) / float(d5.close.iloc[-1])
        grp = g * 10 ** 7 + np.cumsum(b["sw"].fillna(False).astype(bool).values) * 10 ** 4 + pd.factorize(day)[0] % 10 ** 4
        ok_entry = (hm >= 9 * 60 + 15) & (hm <= 22 * 60 + 30)
        out.append(dict(b=b, last=last, ok=ok_entry, costf=np.full(len(b), cf), grp=grp.astype(np.int64), name=name))
    return out


def main():
    rows, t0 = [], time.time()
    for tf in TFS:
        F = frames(tf)
        cat = lambda k: np.concatenate([f[k] for f in F])
        o, h, l, c = (cat_f for cat_f in (np.concatenate([f["b"][x].astype(float).values for f in F]) for x in ("open", "high", "low", "close")))
        grp, last, costf = cat("grp"), cat("last"), cat("costf")
        tt = np.concatenate([f["b"]["time"].values for f in F]); nm = np.concatenate([np.full(len(f["b"]), f["name"]) for f in F])
        atr = np.concatenate([E.wilder(np.maximum(f["b"].high - f["b"].low, np.maximum((f["b"].high - f["b"].close.shift(1)).abs(),
                                                                                    (f["b"].low - f["b"].close.shift(1)).abs())).values, 14) for f in F])
        lo5 = np.concatenate([f["b"].low.rolling(5).min().values for f in F]); hi5 = np.concatenate([f["b"].high.rolling(5).max().values for f in F])
        rk = {1: np.clip(c - lo5 + 0.1 * atr, 0.5 * atr, 3 * atr), -1: np.clip(hi5 - c + 0.1 * atr, 0.5 * atr, 3 * atr)}
        rk2 = 2 * atr
        okE = cat("ok")
        D, OB, OS = {}, {}, {}
        for dn, n, sm in DMOS:
            per = [dmo(f["b"].high.values.astype(float), f["b"].low.values.astype(float), f["b"].close.values.astype(float), n, sm) for f in F]
            D[dn] = np.concatenate(per)
            oo = [ob_os(x) for x in per]
            OB[dn] = np.concatenate([x[0] for x in oo]); OS[dn] = np.concatenate([x[1] for x in oo])
        for L in HULL:
            ab = [hull(f["b"].high.values.astype(float), f["b"].low.values.astype(float), f["b"].close.values.astype(float), L) for f in F]
            a = np.concatenate([x[0] for x in ab]); b_ = np.concatenate([x[1] for x in ab])
            bu = cross_up(b_, a); sd_ = cross_up(a, b_)
            # a cross computed across an instrument boundary is not a signal
            first = np.r_[True, grp[1:] != grp[:-1]]; bu &= ~first; sd_ &= ~first
            green = b_ > a
            for dn in D:
                d = D[dn]; z = np.zeros(len(d)); d0u, d0d = cross_up(d, z) & ~first, cross_up(z, d) & ~first
                obs, oss = OB[dn], OS[dn]
                combos = {"C1 HULL": (bu, sd_), "C2 HULL+DMO0": (bu & (d > 0), sd_ & (d < 0)), "C3 HULL+DMO.3": (bu & (d > 0.3), sd_ & (d < -0.3)),
                          "C4 DMO0@HULL": (d0u & green, d0d & ~green), "C5 BOTH<=3": (within(bu, d0u), within(sd_, d0d)),
                          "C6 OB@HULL": (obs & green, oss & ~green)}
                for cn, (sb, ss) in combos.items():
                    for side, sig in ((1, sb), (-1, ss)):
                        sig = np.nan_to_num(sig).astype(bool) & okE
                        opp = sd_ if side > 0 else bu
                        for ex in ("X1 opposite cross", "X2 stop+2R"):
                            if ex.startswith("X1"):
                                ei, xi, nr = sim_x1(o, h, l, c, sig, opp, side, rk2, grp, last, costf)
                            else:
                                hold = 10 ** 6
                                ei, xi, nr, gr, cr = E.sim(o, h, l, c, sig & ~last, side, rk[side], 2.0, grp, hold, costf, np.zeros(len(c), np.int64))
                            T = pd.DataFrame(dict(name=nm[ei], entry=tt[ei], netR=nr))
                            rw = dict(tf=tf, hull=L, dmo=dn, combo=cn, side="BUY" if side > 0 else "SELL", exit=ex, n=len(T))
                            lab = E.periods(T.entry.values, CUTS) if len(T) else np.array([])
                            for p, _ in CUTS:
                                r = T.netR.values[lab == p] if len(T) else np.array([])
                                w = r > 0
                                rw[f"{p}_n"], rw[f"{p}_R"] = len(r), (round(float(r.mean()), 3) if len(r) else np.nan)
                                rw[f"{p}_win"] = round(100 * float(w.mean()), 1) if len(r) else np.nan
                                rw[f"{p}_PF"] = round(float(r[w].sum() / -r[~w].sum()), 2) if len(r) and (~w).any() else np.nan
                            if len(T) > 2:
                                dm = T.groupby(pd.to_datetime(T.entry).dt.normalize()).netR.mean()
                                rw["t_day"] = round(float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm)))), 2) if dm.std(ddof=1) > 0 else np.nan
                                rw["all_R"] = round(float(T.netR.mean()), 3); rw["all_win"] = round(100 * float((T.netR > 0).mean()), 1)
                                rw["metals_R"] = round(float(T.netR[T.name.isin(C.METALS)].mean()), 3) if T.name.isin(C.METALS).any() else np.nan
                                rw["energy_R"] = round(float(T.netR[~T.name.isin(C.METALS)].mean()), 3) if (~T.name.isin(C.METALS)).any() else np.nan
                                rw["per_commodity"] = "; ".join(f"{k}:{g_.netR.mean():+.2f}({len(g_)})" for k, g_ in T.groupby("name"))
                            rw["PASS"] = bool(rw["n"] >= 100 and all(rw[f"{p}_n"] >= 30 and rw[f"{p}_R"] > 0 and (rw[f"{p}_PF"] or 0) >= 1.2 for p, _ in CUTS))
                            rows.append(rw)
            print(tf, "hull", L, f"{time.time() - t0:.0f}s", flush=True)
        pd.DataFrame(rows).to_csv(OUT / "hull_dmo_grid.csv", index=False)
    Lr = pd.DataFrame(rows)
    p = E.pvals(Lr.t_day.fillna(0).values); Lr["p"] = np.where(Lr.t_day.notna(), p, np.nan); Lr["FDR10"] = C.bh(Lr.p.values)
    Lr.to_csv(OUT / "hull_dmo_grid.csv", index=False)
    print("tests", len(Lr), "PASS", int(Lr.PASS.sum()), "PASS+FDR", int((Lr.PASS & Lr.FDR10).sum()))


if __name__ == "__main__":
    main()
