"""MULTI-YEAR BREAKOUT (owner 18-Nov-2026: "where is the multi-year breakout setup"). NSE cash, official bhavcopies 2005-26,
point-in-time liquid universe, delisted included, delivery costs 0.393 %. BUY only.
  monthly  MY24 / MY36 / MY60: close above the highest high of the previous 24 / 36 / 60 months, and that high was made at least
           12 months earlier (the stock was stuck below it for a year or more = a multi-year base)
  weekly   MY104W / MY156W / MY260W: the same on weekly candles (2 / 3 / 5 years), high made >= 52 weeks earlier
  filters  none / VOL (volume >= 1.5x its 20-candle average) / MKT (top-100 index above its 200-day average) / VOL+MKT
  exits    SL 2 / 3 ATR x target 3R, or SL 2 ATR + 3 ATR trail · max 12 monthly / 26 weekly candles
Compared with random entries (same exit) and with the all-time-high setup. Periods 2005-14 / 2015-19 / 2020-26.
python -m research.cashq.multiyear_bo -> results/multiyear_bo.csv"""
import gc
import itertools
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D, ind as I  # noqa: E402
from research.cashq import nse_bo_tf as T  # noqa: E402

S = T.S
EXITS = [(2.0, 3.0, 0), (3.0, 3.0, 0), (2.0, 0.0, 2)]


def age_of_max(h, N):
    """bars since the highest high of the previous N candles was made (prior window, excluding the current candle)."""
    a = h.shift(1).rolling(N, min_periods=N).apply(lambda x: len(x) - 1 - np.nanargmax(x) if np.isfinite(x).any() else np.nan, raw=True)
    return a


def run(P, tf, mkt):
    o, h, l, c, v = (P[x].astype("float64") for x in ("open", "high", "low", "close", "volume")); e = P["elig"].reindex_like(c).fillna(False).astype(bool)
    keep = c.notna().values.T.ravel()
    flat = lambda df: np.asarray(df.values, float).T.ravel()[keep]
    flatb = lambda df: np.asarray(df.fillna(False).values, bool).T.ravel()[keep]
    seg = np.repeat(np.arange(c.shape[1]), c.shape[0])[keep].astype(np.int64); tix = np.tile(np.arange(c.shape[0]), c.shape[1])[keep]
    days = c.index; atr = I.atr(h, l, c, 14); vx = v / v.rolling(20).mean().shift(1)
    mk = mkt.reindex(days, method="ffill").fillna(False).values
    MK = pd.DataFrame(np.repeat(mk[:, None], c.shape[1], 1), index=days, columns=c.columns)
    O_, H_, L_, C_, A = flat(o), flat(h), flat(l), flat(c), flat(atr); E_ = flatb(e); cf = np.full(len(C_), T.COST); nan = np.full(len(C_), np.nan)
    ed_all = days[tix]
    Ns = (24, 36, 60) if tf == "1M" else (104, 156, 260); base_min = 12 if tf == "1M" else 52
    SIG = {}
    for N in Ns:
        ph = h.shift(1).rolling(N, min_periods=N).max(); ag = age_of_max(h, N)
        s = (c > ph) & (ag >= base_min)
        s = s & ~s.shift(1).rolling(3, min_periods=1).max().fillna(0).astype(bool)
        SIG[f"MY{N}{'' if tf == '1M' else 'W'}"] = s
        print(tf, N, int((s & e).values.sum()), flush=True)
    ath = (c >= c.cummax()) & (c.notna().cumsum() >= (24 if tf == "1M" else 104))
    SIG["ATH (reference)"] = ath & ~ath.shift(1).rolling(3, min_periods=1).max().fillna(0).astype(bool)
    FL = {"none": None, "VOL": vx >= 1.5, "MKT": MK, "VOL+MKT": (vx >= 1.5) & MK}
    rng = np.random.default_rng(5); rows = []
    rand = {}
    for k, r, kind in EXITS:
        acc = []
        for _ in range(5):
            out = S.simulate(O_, H_, L_, C_, A, seg, cf, E_ & (rng.random(len(C_)) < 0.02), C_ - k * A, nan, nan, kind, r, T.MAXH[tf], T.MAXH[tf], 3.0, 3, 0.25, 6.0, 1.0)
            pe = T.per(ed_all[out[1]]); acc.append({p: float(np.nanmean(out[4][pe == p])) for p in ("DEV", "VALID", "OOS")})
        rand[(k, r, kind)] = {p: np.mean([a[p] for a in acc]) for p in ("DEV", "VALID", "OOS")}
    for (sn, s0), (fn, fm) in itertools.product(SIG.items(), FL.items()):
        M = flatb(s0 if fm is None else (s0 & fm)) & E_
        if M.sum() < 20:
            continue
        for k, r, kind in EXITS:
            si, ei, xi, g, nr, mfe, mae, why, rej = S.simulate(O_, H_, L_, C_, A, seg, cf, M, C_ - k * A, nan, nan, kind, r, T.MAXH[tf], T.MAXH[tf], 3.0, 3, 0.25, 6.0, 1.0)
            if len(nr) < 20:
                continue
            ed = ed_all[ei]; p = T.per(ed); pct = nr * k * A[si] / O_[ei] * 100
            row = dict(tf=tf, setup=sn, filt=fn, sl_atr=k, exit="trail 3 ATR" if kind == 2 else "3R", trades=len(nr),
                       per_month_2025_26=round(float((ed >= "2025-01-01").sum() / 22.5), 1), win=round(100 * float((nr > 0).mean()), 1),
                       R=round(float(nr.mean()), 3), avg_pct=round(float(pct.mean()), 2), med_hold=int(np.median(xi - ei + 1)))
            for pp in ("DEV", "VALID", "OOS"):
                x = nr[p == pp]; row[f"{pp}_n"] = len(x); row[f"{pp}_R"] = round(float(x.mean()), 3) if len(x) else None
                row[f"{pp}_rand"] = round(rand[(k, r, kind)][pp], 3)
            for y in (2024, 2025, 2026):
                x = nr[ed.year == y]; row[f"y{y}_n"] = len(x); row[f"y{y}_R"] = round(float(x.mean()), 3) if len(x) else None
            rows.append(row)
    return rows


def main():
    W = D.daily_panel(); mk = W["market"]["close"]; mkt = mk > mk.rolling(200).mean()
    rows = run(T.monthly(W), "1M", mkt)
    rows += run(D.weekly(W), "1w", mkt)
    L = pd.DataFrame(rows); L.to_csv(T.OUT / "multiyear_bo.csv", index=False)
    L["all3"] = (L.DEV_R > L.DEV_rand) & (L.VALID_R > L.VALID_rand) & (L.OOS_R > L.OOS_rand) & (L.DEV_R > 0) & (L.VALID_R > 0) & (L.OOS_R > 0)
    pd.set_option("display.width", 270); pd.set_option("display.max_rows", 200)
    cols = ["tf", "setup", "filt", "sl_atr", "exit", "trades", "per_month_2025_26", "win", "R", "avg_pct", "med_hold", "DEV_R", "VALID_R", "OOS_R", "OOS_rand",
            "y2024_R", "y2025_R", "y2026_R", "all3"]
    print(L.sort_values(["tf", "R"], ascending=[True, False])[cols].to_string(index=False))


if __name__ == "__main__":
    main()
