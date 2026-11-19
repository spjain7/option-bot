"""CASH HIGH-WIN-RATE (owner 18-Nov-2026: "we need 79 % accuracy calls"): published mean-reversion setups (Larry Connors
RSI(2), cumulative RSI(2), Double 7, Bollinger %B, 3 down days, IBS) on official NSE bhavcopies 2005-26, point-in-time liquid
universe (₹25 cr, ≥ ₹50, ≥ 250 sessions), delisted stocks included, delivery costs 0.393 % per round trip. BUY only.
  trend     close > SMA200 (Connors) [+ optional market filter: top-100 index above its 200-day average]
  triggers  RSI2<5 · RSI2<10 · RSI2<10 for 2 days · CUM2 (RSI2 today + yesterday) < 10 · DOUBLE7 (close at a 7-day closing low)
            · PCTB (close below the lower Bollinger band 20,2 for 2 days) · DOWN3 (3 lower closes) · IBS (close in bottom 15 %
            of the range and a 5-day closing low)
  entry     at the signal day's close (buy in the last minutes; the price is known then) or the next open
  exits     close above SMA5 (Connors) · RSI2 > 70 · close above the prior day's high · 7-day closing high (Double 7);
            time cap 10 sessions; protective stop none / 10 % / 3 ATR
Periods DEV 2005-14 · VALID 2015-19 · OOS 2020-26 (+ 2024 / 2025 / 2026). Win = net of costs > 0.
python -m research.cashq.meanrev -> results/meanrev.csv"""
import gc
import itertools
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D, ind as I  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
COST = 0.00393


@njit(cache=True)
def sim(o, h, l, c, sig, ex, entry_close, stop_pct, stop_atr, atr, maxh):
    n = len(c); ei = np.empty(n, np.int64); xi = np.empty(n, np.int64); ret = np.empty(n); m = 0; t = 0
    while t < n - 1:
        if not sig[t]:
            t += 1; continue
        if entry_close:
            e = t; px = c[t]
        else:
            e = t + 1
            if not (h[e] > l[e]) or np.isnan(o[e]):
                t += 1; continue
            px = o[e]
        st = -1.0
        if stop_pct > 0:
            st = px * (1 - stop_pct)
        if stop_atr > 0 and atr[t] > 0:
            st = max(st, px - stop_atr * atr[t])
        j = e + 1; out = np.nan
        while j < n:
            if np.isnan(c[j]):
                j += 1; continue
            if st > 0 and l[j] <= st:
                out = min(o[j], st); break
            if ex[j] or j - e >= maxh:
                out = c[j]; break
            j += 1
        if np.isnan(out):
            j = n - 1
            while j > e and np.isnan(c[j]):
                j -= 1
            out = c[j]
        ei[m] = e; xi[m] = j; ret[m] = out / px - 1 - COST; m += 1
        t = j + 1
    return ei[:m], xi[:m], ret[:m]


def per(t):
    y = t.year
    return np.where(y <= 2014, "DEV", np.where(y <= 2019, "VALID", "OOS"))


def main():
    W = D.daily_panel()
    o, h, l, c = (W[x].astype("float64") for x in ("open", "high", "low", "close")); e = W["elig"].fillna(False)
    mk = W["market"]["close"]; mkt200 = (mk > mk.rolling(200).mean()).reindex(c.index).fillna(False)
    del W; gc.collect()
    r2 = I.rsi(c, 2); sma5 = c.rolling(5).mean(); sma200 = c.rolling(200).mean(); atr = I.atr(h, l, c, 14)
    m20 = c.rolling(20).mean(); sd = c.rolling(20).std(); pctb = (c - (m20 - 2 * sd)) / (4 * sd)
    up = c > sma200
    T = {"RSI2<5": r2 < 5, "RSI2<10": r2 < 10, "RSI2<10 x2": (r2 < 10) & (r2.shift(1) < 10), "CUM2<10": (r2 + r2.shift(1)) < 10,
         "DOUBLE7": c <= c.rolling(7).min(), "PCTB<0 x2": (pctb < 0) & (pctb.shift(1) < 0),
         "DOWN3": (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3)),
         "IBS": (((c - l) / (h - l).replace(0, np.nan)) < 0.15) & (c <= c.rolling(5).min())}
    EX = {"close>SMA5": c > sma5, "RSI2>70": r2 > 70, "close>prev high": c > h.shift(1), "7-day high": c >= c.rolling(7).max()}
    mkw = pd.DataFrame(np.repeat(mkt200.values[:, None], c.shape[1], 1), index=c.index, columns=c.columns)
    days = c.index; O, H, L, C, A = (x.values for x in (o, h, l, c, atr))
    rows = []
    for (tn, tr), mf in itertools.product(T.items(), (False, True)):
        M = (tr & up & e & (mkw if mf else True)).fillna(False).values
        nsig = int(M.sum())
        for (xn, xs), ec, (sp, sa) in itertools.product(EX.items(), (True, False), ((0, 0), (0.10, 0), (0, 3.0))):
            XS = xs.fillna(False).values; res = []
            for j in np.where(M.any(0))[0]:
                ei, xi, rt = sim(O[:, j], H[:, j], L[:, j], C[:, j], M[:, j], XS[:, j], ec, sp, sa, A[:, j], 10)
                if len(ei):
                    res.append(np.c_[ei, xi - ei, rt])
            X = np.vstack(res); ed = days[X[:, 0].astype(int)]; p = per(ed); rt = X[:, 2]
            row = dict(trigger=tn, market_filter=mf, exit=xn, entry="close" if ec else "next open",
                       stop="none" if not (sp or sa) else (f"{int(sp * 100)} %" if sp else f"{sa:g} ATR"), signals=nsig, trades=len(rt),
                       per_month_2025_26=round(float((ed >= "2025-01-01").sum() / 22.5), 1), win=round(100 * float((rt > 0).mean()), 1),
                       avg_pct=round(100 * float(rt.mean()), 2), med_hold=float(np.median(X[:, 1])), worst_pct=round(100 * float(rt.min()), 1),
                       p5_pct=round(100 * float(np.percentile(rt, 5)), 2))
            for pp in ("DEV", "VALID", "OOS"):
                x = rt[p == pp]; row[f"{pp}_n"] = len(x); row[f"{pp}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else None
                row[f"{pp}_avg"] = round(100 * float(x.mean()), 2) if len(x) else None
            for y in (2024, 2025, 2026):
                x = rt[ed.year == y]; row[f"y{y}_n"] = len(x); row[f"y{y}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else None
                row[f"y{y}_avg"] = round(100 * float(x.mean()), 2) if len(x) else None
            rows.append(row)
        print(tn, mf, nsig, flush=True)
    L_ = pd.DataFrame(rows); OUT.mkdir(exist_ok=True); L_.to_csv(OUT / "meanrev.csv", index=False)
    pd.set_option("display.width", 280); pd.set_option("display.max_rows", 200)
    ok = L_[(L_.DEV_win >= 70) & (L_.VALID_win >= 70) & (L_.OOS_win >= 70) & (L_.DEV_avg > 0) & (L_.VALID_avg > 0) & (L_.OOS_avg > 0)]
    print("\nWIN >= 70 % AND PROFITABLE IN ALL 3 PERIODS:", len(ok), "of", len(L_))
    cols = ["trigger", "market_filter", "exit", "entry", "stop", "trades", "per_month_2025_26", "win", "avg_pct", "med_hold", "p5_pct", "worst_pct",
            "DEV_win", "VALID_win", "OOS_win", "OOS_avg", "y2024_win", "y2024_avg", "y2025_win", "y2025_avg", "y2026_win", "y2026_avg"]
    print(ok.sort_values("OOS_avg", ascending=False)[cols].head(40).to_string(index=False))
    print("\nhighest win rates overall:"); print(L_.sort_values("win", ascending=False)[cols].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
