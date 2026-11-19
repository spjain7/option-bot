"""WIDE COMBO SEARCH for NSE cash-stock BUY setups (owner 18-Nov-2026: "apply many combos, find a more profitable strategy
for cash stocks"). Official NSE bhavcopies 2005-26, back-adjusted, delisted included, point-in-time universe ₹5 cr+ 60-day median
turnover, >= ₹50, >= 250 sessions. Delivery costs 0.393 % per round trip. Signal at the candle close, entry next open.
ENTRIES (daily 1d / weekly 1w)
  BO20 / BO50        close above the prior 20 / 50-candle high                 HI52   52-week closing high
  RETEST             a 50-day (1d) / 20-week (1w) breakout in the last 2-15 candles, price dips back to within 2 % of the
                     breakout level, holds above it and closes green (buy the retest)
  VCP                trend template (close > SMA50 > SMA150 > SMA200, SMA200 rising, within 25 % of the 52-wk high, 30 %+ above
                     the 52-wk low; weekly: SMA10 > SMA30 > SMA40) + volatility contraction (ATR10 / ATR50 <= 0.75 the candle
                     before) + close above the prior 20-candle high on volume >= 1.5x
  TIGHT              prior 20 days (8 weeks) high-low range <= 12 % (15 %) of price, close above it on volume >= 1.5x
  PULLBACK           trend template, the candle's low touches EMA20 (EMA10 weekly), closes above it and above the prior high
  PPIVOT             pocket pivot: up candle whose volume beats every down-candle volume of the last 10, close > SMA50 and > EMA10
  NR7                trend template, prior candle the narrowest of 7, close above the prior high (1d only)
FILTERS  none / MKT (top-100 EW index above its 200-day average) / RS80 (6-month return in the top 20 % of the universe) /
         VOL (volume >= 1.5x) / TT (trend template) / MKT+RS80
EXITS    SL 2 ATR + 2R / 2 ATR + 3R / 3 ATR + 3R / 2 ATR, half at 1R then 3R (stop to cost) / 2 ATR + 3 ATR trailing stop, held up
         to 250 days / 104 weeks / 3 ATR stop + time exit after 20 days / 8 weeks.   Max hold otherwise 60 days / 26 weeks.
PASS     average R > 0 AND above random entries (same exit) in all of 2005-14, 2015-19 and 2020-26, >= 30 calls in each.
Also: cash-only (no F&O, 2018+) results of each combo in 2020-26.
MOMENTUM ROTATION (NSE momentum-index style): each month-end buy the top 20 / 30 stocks by 12-1 / 6-month return, equal
weight, hold one month; optionally only when the market is above its 200-day average. Compared with all eligible stocks.
python -m research.cashq.cash_combo [cm_pickle] -> results/cash_combo.csv, results/cash_momentum.csv"""
import gc
import itertools
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D, ind as I  # noqa: E402

D.MIN_TURNOVER = 5e7
if len(sys.argv) > 1:
    D.CM_PKL = Path(sys.argv[1])
from research.cashq import nse_bo_tf as T  # noqa: E402
from research.cashq.nse_bo_cash import fo_by_month  # noqa: E402

S = T.S; COST = T.COST; OUT = T.OUT
PER = ("DEV", "VALID", "OOS")


def first(x, n=3):
    x = x.fillna(False).astype(bool)
    return x & ~x.shift(1).rolling(n, min_periods=1).max().fillna(0).astype(bool)


def entries(P, tf):
    o, h, l, c, v = (P[x].astype("float64") for x in ("open", "high", "low", "close", "volume"))
    atr = I.atr(h, l, c, 14); vx = v / v.rolling(20).mean().shift(1)
    wk = tf == "1w"
    s50, s150, s200 = (c.rolling(n).mean() for n in ((10, 30, 40) if wk else (50, 150, 200)))
    n52 = 52 if wk else 252
    hi52, lo52 = c.rolling(n52, min_periods=int(n52 * .9)).max(), c.rolling(n52, min_periods=int(n52 * .9)).min()
    TT = (c > s50) & (s50 > s150) & (s150 > s200) & (s200 > s200.shift(4 if wk else 20)) & (c >= .75 * hi52) & (c >= 1.3 * lo52)
    ema_pb = c.ewm(span=10 if wk else 20, adjust=False).mean()
    E = {}
    E["BO20"] = first(c > h.shift(1).rolling(20).max())
    if not wk:
        E["BO50"] = first(c > h.shift(1).rolling(50).max())
    E["HI52"] = first(c >= hi52)
    nb = 20 if wk else 50
    lvl_at = h.shift(1).rolling(nb).max(); bo = first(c > lvl_at)
    lvl = lvl_at.where(bo).ffill(limit=15)
    recent = bo.shift(2).rolling(14, min_periods=1).max().fillna(0).astype(bool)
    E["RETEST"] = first(recent & (l <= lvl * 1.02) & (c > lvl) & (c > o), 5)
    a10, a50 = I.atr(h, l, c, 10), I.atr(h, l, c, 50)
    E["VCP"] = first(TT & ((a10 / a50).shift(1) <= .75) & (c > h.shift(1).rolling(20).max()) & (vx >= 1.5))
    nt, cap = (8, .15) if wk else (20, .12)
    rg = (h.shift(1).rolling(nt).max() - l.shift(1).rolling(nt).min()) / c.shift(1)
    E["TIGHT"] = first((rg <= cap) & (c > h.shift(1).rolling(nt).max()) & (vx >= 1.5))
    E["PULLBACK"] = first(TT & (l <= ema_pb) & (c > ema_pb) & (c > h.shift(1)), 5)
    dv = v.where(c < c.shift(1)); mxd = dv.shift(1).rolling(10, min_periods=1).max().fillna(0)
    E["PPIVOT"] = first((c > c.shift(1)) & (v > mxd) & (c > s50 if not wk else c > s50) & (c > c.ewm(span=10, adjust=False).mean()))
    if not wk:
        r = h - l; nr7 = r.shift(1) <= r.shift(1).rolling(7).min()
        E["NR7"] = first(TT & nr7 & (c > h.shift(1)))
    return E, dict(o=o, h=h, l=l, c=c, atr=atr, vx=vx, TT=TT)


def run_tf(P, tf, mkt, fo, sym):
    E, X = entries(P, tf); o, h, l, c, atr = X["o"], X["h"], X["l"], X["c"], X["atr"]
    e = P["elig"].reindex_like(c).fillna(False).astype(bool)
    days = c.index
    mk = mkt.reindex(days, method="ffill").fillna(False).values
    MK = pd.DataFrame(np.repeat(mk[:, None], c.shape[1], 1), index=days, columns=c.columns)
    rs = (c / c.shift(26 if tf == "1w" else 126) - 1).where(e).rank(axis=1, pct=True)
    F = {"none": None, "MKT": MK, "RS80": rs >= .8, "VOL": X["vx"] >= 1.5, "TT": X["TT"], "MKT+RS80": MK & (rs >= .8)}
    keep = c.notna().values.T.ravel()
    flat = lambda df: np.asarray(df.values, float).T.ravel()[keep]
    flatb = lambda df: np.asarray(df.fillna(False).values, bool).T.ravel()[keep]
    seg = np.repeat(np.arange(c.shape[1]), c.shape[0])[keep].astype(np.int64); tix = np.tile(np.arange(c.shape[0]), c.shape[1])[keep]
    O_, H_, L_, C_, A = flat(o), flat(h), flat(l), flat(c), flat(atr); E_ = flatb(e)
    cf = np.full(len(C_), COST); nan = np.full(len(C_), np.nan); ed_all = days[tix]
    symcol = np.array([sym[k] for k in c.columns])
    mx, lng, tn = (26, 104, 8) if tf == "1w" else (60, 250, 20)
    EXITS = [("2ATR 2R", 2., 2., 0, mx), ("2ATR 3R", 2., 3., 0, mx), ("3ATR 3R", 3., 3., 0, mx), ("2ATR half1R+3R", 2., 3., 4, mx),
             ("2ATR trail3ATR", 2., 0., 2, lng), (f"3ATR time{tn}", 3., 0., 3, mx)]
    fm = sorted(fo); mon = np.array([str(d)[:7] for d in days])
    FOP = np.zeros(c.shape, bool); KN = mon >= fm[0]
    for i, mm in enumerate(mon):
        if KN[i]:
            st = fo.get(mm) or fo[max(x for x in fm if x <= mm)]
            FOP[i] = np.isin(symcol, list(st))
    FOf = FOP.T.ravel()[keep]; KNf = np.tile(KN, c.shape[1])[keep]
    def is_fo(si):
        return FOf[si], KNf[si]
    rng = np.random.default_rng(7); rand = {}
    for name, k, r, kind, mh in EXITS:
        acc = []
        for _ in range(4):
            out = S.simulate(O_, H_, L_, C_, A, seg, cf, E_ & (rng.random(len(C_)) < 0.01), C_ - k * A, nan, nan, kind, r, mh, tn, 3.0, 3, 0.25, 6.0, 1.0)
            pe = T.per(ed_all[out[1]]); acc.append({p: float(np.nanmean(out[4][pe == p])) for p in PER})
        rand[name] = {p: np.mean([x[p] for x in acc]) for p in PER}
    rows = []
    for (en, sg), (fn, fm_) in itertools.product(E.items(), F.items()):
        M = flatb(sg if fm_ is None else (sg & fm_)) & E_
        if M.sum() < 90:
            continue
        for name, k, r, kind, mh in EXITS:
            si, ei, xi, g, nr, mfe, mae, why, rej = S.simulate(O_, H_, L_, C_, A, seg, cf, M, C_ - k * A, nan, nan, kind, r, mh, tn, 3.0, 3, 0.25, 6.0, 1.0)
            if len(nr) < 90:
                continue
            ed = ed_all[ei]; p = T.per(ed); pct = nr * k * A[si] / O_[ei] * 100
            row = dict(tf=tf, entry=en, filt=fn, exit=name, trades=len(nr), per_month_2025_26=round(float((ed >= "2025-01-01").sum() / 22.5), 1),
                       win=round(100 * float((nr > 0).mean()), 1), R=round(float(nr.mean()), 3), avg_pct=round(float(pct.mean()), 2),
                       med_hold=int(np.median(xi - ei + 1)))
            for pp in PER:
                x = nr[p == pp]; row[f"{pp}_n"] = len(x); row[f"{pp}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else None
                row[f"{pp}_R"] = round(float(x.mean()), 3) if len(x) else None; row[f"{pp}_rand"] = round(rand[name][pp], 3)
                row[f"{pp}_pct"] = round(float(pct[p == pp].mean()), 2) if len(x) else None
            isf, known = is_fo(si); oos = p == "OOS"
            for lab, m in (("oos_cash", oos & known & ~isf), ("oos_fo", oos & known & isf)):
                row[f"{lab}_n"] = int(m.sum()); row[f"{lab}_win"] = round(100 * float((nr[m] > 0).mean()), 1) if m.any() else None
                row[f"{lab}_pct"] = round(float(pct[m].mean()), 2) if m.any() else None
            rows.append(row)
        print(tf, en, fn, len(rows), flush=True)
    return rows


def momentum(W, mkt):
    c = W["close"].astype("float64"); e = W["elig"].fillna(False).astype(bool)
    me = c.index.to_series().groupby(c.index.to_period("M")).last().values
    C = c.loc[me]; Ee = e.loc[me]; mk = mkt.reindex(me).fillna(False).values
    fwd = C.shift(-1) / C - 1
    ew = fwd.where(Ee).mean(axis=1)
    rows = []; curves = {}
    for look, n, mf in itertools.product(("12-1", "6"), (20, 30), (False, True)):
        sc = (C.shift(1) / C.shift(12) - 1) if look == "12-1" else (C / C.shift(6) - 1)
        sc = sc.where(Ee & C.shift(12).notna())
        prev = set(); ret = []
        for i in range(len(me) - 1):
            if mf and not mk[i]:
                ret.append(-COST / 2 * (len(prev) > 0)); prev = set(); continue
            top = set(sc.iloc[i].dropna().nlargest(n).index)
            if len(top) < n:
                ret.append(0.0); prev = set(); continue
            turn = 1 - len(top & prev) / n if prev else 1.0
            ret.append(float(fwd.iloc[i][list(top)].fillna(-0.0).mean()) - turn * COST)
            prev = top
        r = pd.Series(ret, index=pd.DatetimeIndex(me[:-1]))
        key = f"MOM {look}m top{n}{' +MKT' if mf else ''}"; curves[key] = r
        rows.append(stats_m(key, r))
    rows.append(stats_m("All eligible stocks (equal weight)", ew.iloc[:-1]))
    return rows


def stats_m(key, r):
    r = r.dropna(); eq = (1 + r).cumprod(); dd = float((eq / eq.cummax() - 1).min())
    row = dict(strategy=key, months=len(r), CAGR_pct=round(100 * (eq.iloc[-1] ** (12 / len(r)) - 1), 1), maxDD_pct=round(100 * dd, 1),
               month_win_pct=round(100 * float((r > 0).mean()), 1))
    for p, lo, hi in (("2005-14", 2005, 2014), ("2015-19", 2015, 2019), ("2020-26", 2020, 2026), ("2024", 2024, 2024), ("2025", 2025, 2025), ("2026", 2026, 2026)):
        x = r[(r.index.year >= lo) & (r.index.year <= hi)]
        row[f"{p}_CAGR"] = round(100 * (float((1 + x).prod()) ** (12 / max(len(x), 1)) - 1), 1) if len(x) else None
    return row


def main():
    W = D.daily_panel(); mk = W["market"]["close"]; mkt = mk > mk.rolling(200).mean(); sym = W["symbol"]
    fo = fo_by_month()
    M = pd.DataFrame(momentum(W, mkt)); M.to_csv(OUT / "cash_momentum.csv", index=False)
    pd.set_option("display.width", 280); pd.set_option("display.max_rows", 300)
    print(M.to_string(index=False), flush=True)
    rows = run_tf(W, "1d", mkt, fo, sym); gc.collect()
    Wk = D.weekly(W); del W; gc.collect()
    rows += run_tf(Wk, "1w", mkt, fo, sym)
    L = pd.DataFrame(rows)
    L["pass"] = np.all([(L[f"{p}_R"] > L[f"{p}_rand"]) & (L[f"{p}_R"] > 0) & (L[f"{p}_n"] >= 30) for p in PER], axis=0)
    L["min_R"] = L[[f"{p}_R" for p in PER]].min(axis=1)
    L.to_csv(OUT / "cash_combo.csv", index=False)
    cols = ["tf", "entry", "filt", "exit", "trades", "per_month_2025_26", "win", "R", "avg_pct", "med_hold", "DEV_R", "VALID_R", "OOS_R", "OOS_rand",
            "DEV_win", "VALID_win", "OOS_win", "OOS_pct", "oos_cash_n", "oos_cash_win", "oos_cash_pct"]
    print(f"\nPASS {int(L['pass'].sum())} of {len(L)}")
    print(L[L["pass"]].sort_values("min_R", ascending=False).head(40)[cols].to_string(index=False))
    print("\n-- highest win rate among passes:")
    print(L[L["pass"]].sort_values("win", ascending=False).head(15)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
