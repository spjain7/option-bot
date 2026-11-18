"""CASH SWING – setups that catch the 10-20 % movers (owner 18-Nov-2026: "only one cash call while many stocks move 10/20 %").
Official NSE bhavcopies 2005-26 (back-adjusted, delisted included), point-in-time liquid universe (₹25 cr median turnover,
≥ ₹50, ≥ 250 sessions). Signal at the close, entry next open (skipped if the next day is locked), delivery costs 0.393 %.
Setups (BUY only):
  MOMBURST  day +4 % or more, volume > yesterday and >= 1.5x 20-day avg, close in the top 30 % of the range, not extended
            (5-day return before the day < 8 %), above EMA50                         (momentum burst)
  VOLBO20   first close above the 20-day high in 5 days with volume >= 2x             (volume breakout)
  HI52VOL   252-day closing high with volume >= 1.5x
  TIGHTBO   ATR10/ATR50 <= 0.8 yesterday (tight base) + close above the 20-day high + volume >= 1.5x
  GAPGO     open >= 3 % above yesterday's close, close >= open, top 40 % of range, volume >= 2x
  RSPB      relative strength top 10 % (126 d), above EMA50, low touches EMA20 and close back above it, green day
  NR7BO     yesterday NR7 (narrowest range of 7), today close above yesterday's high, RS top 20 %
  BO50SC    the live scored 50-day breakout at a lower score (>= 50 / >= 60) for comparison with the live >= 70
Filters: none / MKT (top-100 index above its 100-day average) / RS70 (RS top 30 %) / MKT+RS70
Exits: SL 1.5 / 2 ATR · (a) T1 1R book half + stop to cost + rest at 2R, (b) single 2R, (c) trailing 10-day low · max 20 sessions
Periods: DEV 2005-14 · VALID 2015-19 · OOS 2020-26 (also 2024-26 separately). Coverage: share of the "big movers" (stocks
whose high within the next 10 sessions is >= 15 % above the next open) that the setup flagged that day.
python -m research.cashq.swing_movers -> results/swing_movers.csv"""
import gc
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D, ind as I  # noqa: E402
from research.cashq.daily_run import features, first_in  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
COST = 0.00393


@njit(cache=True)
def sim(o, h, l, c, sig, risk, kind, R, maxh, trail):
    """one stock. kind 0 single target R, 1 half at 1R + stop to cost + rest at R, 2 trailing (close < trail -> next open).
    Returns entry idx, exit idx, net-of-nothing R, entry px."""
    n = len(c); ei = np.empty(n, np.int64); xi = np.empty(n, np.int64); gr = np.empty(n); ep = np.empty(n); m = 0; t = 0
    while t < n - 1:
        if not sig[t] or not (risk[t] > 0):
            t += 1; continue
        e = t + 1
        if not (h[e] > l[e]) or np.isnan(o[e]):
            t += 1; continue
        px = o[e]; rk = risk[t]; st = px - rk; tg = px + R * rk; half = False; bank = 0.0
        j = e; out = np.nan
        while j < n and j - e < maxh:
            if np.isnan(c[j]):
                j += 1; continue
            if l[j] <= st:
                out = min(o[j], st) if j > e else st; break
            if kind == 1 and not half and h[j] >= px + rk:
                half = True; bank = 0.5; st = px
                if l[j] <= st:            # same bar: assume target half filled, rest at cost
                    out = px; break
            if kind != 2 and h[j] >= tg:
                out = max(o[j], tg) if j > e else tg; break
            if kind == 2 and c[j] < trail[j] and j + 1 < n:
                j += 1; out = o[j]; break
            j += 1
        if np.isnan(out):
            j = min(j, n - 1)
            while j > e and np.isnan(c[j]):
                j -= 1
            out = c[j]
        g = (out - px) / rk
        if kind == 1 and half:
            g = bank + 0.5 * g
        ei[m] = e; xi[m] = j; gr[m] = g; ep[m] = px; m += 1
        t = j + 1
    return ei[:m], xi[:m], gr[:m], ep[:m]


def per(t):
    y = t.year
    return np.where(y <= 2014, "DEV", np.where(y <= 2019, "VALID", "OOS"))


def main():
    W = D.daily_panel(); F = features(W); del W; gc.collect()
    o, h, l, c, v = (F[x] for x in ("open", "high", "low", "close", "volume")); e = F["elig"].fillna(False)
    pc = c.shift(1); ret = c / pc - 1; rng = (h - l); clv = (c - l) / rng.replace(0, np.nan)
    v20 = v.rolling(20).mean().shift(1); vx = v / v20
    S = {}
    S["MOMBURST"] = (ret >= 0.04) & (v > v.shift(1)) & (vx >= 1.5) & (clv >= 0.7) & (pc / c.shift(6) - 1 < 0.08) & (c > F["ema50"])
    S["VOLBO20"] = first_in(F["hi20"], 5) & (vx >= 2)
    S["HI52VOL"] = F["hi252"] & (vx >= 1.5)
    S["TIGHTBO"] = (F["atr10_50"].shift(1) <= 0.8) & F["hi20"] & (vx >= 1.5)
    S["GAPGO"] = (o >= pc * 1.03) & (c >= o) & (clv >= 0.6) & (vx >= 2)
    S["RSPB"] = (F["rs_rank"] >= 0.9) & (c > F["ema50"]) & (l <= F["ema20"]) & (c > F["ema20"]) & (c > o)
    nr = rng.shift(1) <= rng.shift(1).rolling(7).min()
    S["NR7BO"] = nr & (c > h.shift(1)) & (F["rs_rank"] >= 0.8)
    # live scored 50-day breakout (cashstock/breakout.py rules) at lower thresholds
    from cashstock import breakout as B
    BF = B.features(dict(open=o, high=h, low=l, close=c, volume=v, symbol=pd.Series(dict(zip(c.columns, c.columns)))))
    rsr, adx, tight, clv2, br = BF["rs126"], BF["adx"], BF["tight"], BF["clv"], BF["breadth50"]
    sc = (np.where(rsr >= .85, 35, np.where(rsr >= .70, 22, np.where(rsr >= .50, 10, 0))) + np.where(adx >= 30, 25, np.where(adx >= 22, 15, np.where(adx >= 16, 6, 0)))
          + np.where(tight <= .85, 20, np.where(tight <= 1.0, 10, 0)) + np.where(clv2 < .85, 10, 0)
          + np.where(br.values[:, None] >= .55, 10, np.where(br.values[:, None] >= .40, 5, 0)))
    sc = pd.DataFrame(sc, index=c.index, columns=c.columns)
    for th in (50, 60, 70):
        S[f"BO50SC{th}"] = BF["signal"] & (sc >= th)
    del BF; gc.collect()
    mk = F["mkt_w"].astype(bool); rs = F["rs_rank"] >= 0.7
    FL = {"none": None, "MKT": mk, "RS70": rs, "MKT+RS70": mk & rs}
    atr = F["atr"]; low10 = l.rolling(10).min().shift(1)
    # big movers: high within the next 10 sessions >= 15 % above the next open
    nxt = o.shift(-1); fh = h[::-1].rolling(10, min_periods=1).max()[::-1].shift(-1)
    big = e & (fh >= nxt * 1.15)
    days = c.index
    rows = []
    cols = list(c.columns)
    O, H, L, C, A, T = (x.values for x in (o, h, l, c, atr, low10))
    E = e.values
    for sn, s0 in S.items():
        for fn, fm in FL.items():
            m = (s0 & e) if fm is None else (s0 & e & fm)
            M = m.fillna(False).values
            cov = float((M & big.values).sum() / max(big.values.sum(), 1))
            nsig = int(M.sum())
            for k in (1.5, 2.0):
                for ex, kind, R in (("T1 half + 2R", 1, 2.0), ("2R", 0, 2.0), ("trail 10-day low", 2, 0.0)):
                    res = []
                    for j in range(len(cols)):
                        if not M[:, j].any():
                            continue
                        rk = k * A[:, j]
                        ei, xi, g, ep = sim(O[:, j], H[:, j], L[:, j], C[:, j], M[:, j], rk, kind, R, 20, T[:, j])
                        if len(ei):
                            net = g - COST * ep / np.where(rk[ei - 1] > 0, rk[ei - 1], np.nan)
                            res.append(np.c_[ei, xi, net, g, (ep * 0 + j)])
                    if not res:
                        continue
                    X = np.vstack(res); ed = days[X[:, 0].astype(int)]; p = per(ed); nr_ = X[:, 2]
                    pct = nr_ * (k * A[X[:, 0].astype(int) - 1, X[:, 4].astype(int)]) / O[X[:, 0].astype(int), X[:, 4].astype(int)] * 100
                    row = dict(setup=sn, filt=fn, sl_atr=k, exit=ex, signals=nsig, coverage_pct=round(100 * cov, 1), trades=len(nr_),
                               win=round(100 * float((nr_ > 0).mean()), 1), R=round(float(np.nanmean(nr_)), 3), avg_pct=round(float(np.nanmean(pct)), 2),
                               per_month_2025_26=round(float(((ed >= "2025-01-01")).sum() / 22.5), 1))
                    for pp in ("DEV", "VALID", "OOS"):
                        x = nr_[p == pp]; row[f"{pp}_n"] = len(x); row[f"{pp}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else None
                        row[f"{pp}_R"] = round(float(np.nanmean(x)), 3) if len(x) else None
                    x = nr_[ed >= "2024-01-01"]; row["y2024_26_n"] = len(x); row["y2024_26_R"] = round(float(np.nanmean(x)), 3) if len(x) else None
                    row["y2024_26_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else None
                    rows.append(row)
            print(sn, fn, nsig, flush=True)
    L_ = pd.DataFrame(rows); OUT.mkdir(exist_ok=True); L_.to_csv(OUT / "swing_movers.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 300)
    ok = L_[(L_.DEV_R > 0) & (L_.VALID_R > 0) & (L_.OOS_R > 0)]
    print("\nPOSITIVE IN ALL 3 PERIODS:", len(ok), "of", len(L_))
    print(ok.sort_values("OOS_R", ascending=False)[["setup", "filt", "sl_atr", "exit", "trades", "per_month_2025_26", "coverage_pct", "win", "R",
                                                     "avg_pct", "DEV_R", "VALID_R", "OOS_R", "y2024_26_n", "y2024_26_win", "y2024_26_R"]].head(40).to_string(index=False))


if __name__ == "__main__":
    main()
