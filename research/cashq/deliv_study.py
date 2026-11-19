"""DELIVERY % study (owner 18-Nov-2026: "find the delivery data"). NSE security-wise delivery position 2005-26
(research/data/nse_deliv via research/cashq/deliv_fetch.py) joined to the official bhavcopy panel (₹5 cr+ PIT universe, delisted
included, delivery costs 0.393 %). Split-safe measures (no share counts):
  DP       delivery % of traded quantity that day                     DPX   DP / its 20-day average (the candle before)
  DVX      delivered VALUE (DP x traded value) / its 20-day average   weekly: the same on the week's totals
PART 1  event study: buy at the next open, hold 5 / 20 / 60 sessions; EXCESS = minus the average eligible stock bought the
        same day (so a rising market does not flatter). Events: delivery-value spike >= 3x on an up day >= 2 %, high DP
        (>= 70 %) on volume >= 2x and an up day, low DP (<= 20 %) volume spike (speculative), DP quintiles on 50-day breakouts.
PART 2  delivery as a FILTER on the cash_combo.py entries (same exits, same pass rule: average R > 0 and above random
        entries in 2005-14, 2015-19 and 2020-26).  Filters: DPX>=1.2 (delivery % above normal), DVX>=2 (delivered value
        >= 2x), DP>=50, and each with MKT+RS80.
python -m research.cashq.deliv_study [cm_pickle] -> results/deliv_events.csv, results/deliv_combo.csv"""
import gc
import itertools
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D  # noqa: E402

D.MIN_TURNOVER = 5e7
if len(sys.argv) > 1:
    D.CM_PKL = Path(sys.argv[1])
from research.cashq import nse_bo_tf as T, cash_combo as CC  # noqa: E402

S = T.S; COST = T.COST; OUT = T.OUT; PER = CC.PER
DDIR = ROOT / "research/data/nse_deliv"


def deliv_panel(W):
    X = pd.concat([pd.read_parquet(p) for p in sorted(DDIR.glob("*.parquet"))])
    sym = W["symbol"]; k_of = {}
    for k, s in sym.items():
        k_of.setdefault(s, k)
    X = X[X.symbol.isin(k_of)]
    X["key"] = X.symbol.map(k_of)
    dp = X.pivot_table(index="date", columns="key", values="deliv_pct", aggfunc="last")
    dp = dp.reindex(index=W["close"].index, columns=W["close"].columns)
    return dp.clip(0, 100)


def main():
    W = D.daily_panel(); mk = W["market"]["close"]; mkt = mk > mk.rolling(200).mean()
    dp = deliv_panel(W)
    c, o, v = W["close"].astype("float64"), W["open"].astype("float64"), W["volume"].astype("float64")
    val = W["value"].astype("float64"); e = W["elig"].fillna(False).astype(bool)
    print("delivery coverage on eligible days:", round(float(dp.where(e).notna().sum().sum() / e.values.sum()), 3), flush=True)
    dval = dp / 100 * val
    DPX = dp / dp.rolling(20, min_periods=15).mean().shift(1); DVX = dval / dval.rolling(20, min_periods=15).mean().shift(1)
    ret = c / c.shift(1) - 1; vx = v / v.rolling(20).mean().shift(1)
    # ---------- PART 1 event study
    nxt = o.shift(-1); fwd = {H: c.shift(-H) / nxt - 1 - COST for H in (5, 20, 60)}
    base = {H: fwd[H].where(e).mean(axis=1) for H in fwd}
    bo50 = CC.first(c > W["high"].astype("float64").shift(1).rolling(50).max())
    EV = {"delivered value >=3x, up day >=2%": (DVX >= 3) & (ret >= .02), "DP >=70% + volume >=2x + up day": (dp >= 70) & (vx >= 2) & (ret > 0),
          "DP <=20% + volume >=3x (speculative)": (dp <= 20) & (vx >= 3), "DP rising (DPX>=1.5) + up day >=2%": (DPX >= 1.5) & (ret >= .02),
          "delivered value >=3x, DOWN day <=-2%": (DVX >= 3) & (ret <= -.02)}
    q = dp.where(bo50 & e).stack()
    edges = q.quantile([.2, .4, .6, .8]).values
    for i, (lo, hi) in enumerate(zip([-1, *edges], [*edges, 101])):
        EV[f"50-day breakout, DP quintile {i + 1} ({lo:.0f}-{hi:.0f}%)"] = bo50 & (dp > lo) & (dp <= hi)
    days = c.index; rows = []
    for name, m in EV.items():
        M = (m & e).fillna(False)
        for per, lo, hi in (("2005-14", 2005, 2014), ("2015-19", 2015, 2019), ("2020-26", 2020, 2026), ("ALL", 2005, 2026)):
            sel = (days.year >= lo) & (days.year <= hi); Mp = M[sel]
            row = dict(event=name, period=per, events=int(Mp.values.sum()))
            for H in fwd:
                F = fwd[H][sel].where(Mp); X = F.sub(base[H][sel], axis=0).where(Mp)
                f, x = F.values[np.isfinite(F.values)], X.values[np.isfinite(X.values)]
                row[f"d{H}_avg"] = round(100 * float(f.mean()), 2) if len(f) else None
                row[f"d{H}_win"] = round(100 * float((f > 0).mean()), 1) if len(f) else None
                row[f"d{H}_excess"] = round(100 * float(x.mean()), 2) if len(x) else None
            rows.append(row)
    E1 = pd.DataFrame(rows); E1.to_csv(OUT / "deliv_events.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 300)
    print(E1.to_string(index=False), flush=True)
    del fwd, base; gc.collect()
    # ---------- PART 2 delivery as a filter on the combo entries
    rows = []
    for tf in ("1d", "1w"):
        if tf == "1d":
            P = W; dpp, dpx, dvx = dp, DPX, DVX
        else:
            P = D.weekly(W); g = W["close"].index.to_period("W-FRI")
            dvw = dval.groupby(g).sum(min_count=1).set_axis(P["close"].index); vw = val.groupby(g).sum(min_count=1).set_axis(P["close"].index)
            dpp = 100 * dvw / vw.replace(0, np.nan); dpx = dpp / dpp.rolling(10, min_periods=8).mean().shift(1)
            dvx = dvw / dvw.rolling(10, min_periods=8).mean().shift(1)
        rows += run(P, tf, mkt, dpp, dpx, dvx)
        gc.collect()
    L = pd.DataFrame(rows)
    L["pass"] = np.all([(L[f"{p}_R"] > L[f"{p}_rand"]) & (L[f"{p}_R"] > 0) & (L[f"{p}_n"] >= 30) for p in PER], axis=0)
    L["min_R"] = L[[f"{p}_R" for p in PER]].min(axis=1)
    L.to_csv(OUT / "deliv_combo.csv", index=False)
    cols = ["tf", "entry", "filt", "exit", "trades", "per_month_2025_26", "win", "R", "avg_pct", "DEV_R", "VALID_R", "OOS_R", "DEV_pct", "VALID_pct", "OOS_pct", "pass"]
    print(f"\nPASS {int(L['pass'].sum())} of {len(L)}")
    for (tf, en, ex), G in L.groupby(["tf", "entry", "exit"]):
        if ex in ("2ATR trail3ATR", "3ATR 3R", "2ATR half1R+3R"):
            print(G[cols].to_string(index=False, header=False))


def run(P, tf, mkt, dpp, dpx, dvx):
    E, X = CC.entries(P, tf); o, h, l, c, atr = X["o"], X["h"], X["l"], X["c"], X["atr"]
    E = {k: E[k] for k in (("BO50", "HI52", "RETEST", "PULLBACK") if tf == "1d" else ("BO20", "HI52", "RETEST", "PULLBACK"))}
    e = P["elig"].reindex_like(c).fillna(False).astype(bool); days = c.index
    mk = mkt.reindex(days, method="ffill").fillna(False).values
    MK = pd.DataFrame(np.repeat(mk[:, None], c.shape[1], 1), index=days, columns=c.columns)
    rs = (c / c.shift(26 if tf == "1w" else 126) - 1).where(e).rank(axis=1, pct=True)
    MR = MK & (rs >= .8)
    F = {"none": None, "MKT+RS80": MR, "DPX>=1.2": dpx >= 1.2, "DVX>=2": dvx >= 2, "DP>=50": dpp >= 50,
         "DPX>=1.2+MKT+RS80": (dpx >= 1.2) & MR, "DVX>=2+MKT+RS80": (dvx >= 2) & MR, "DP>=50+MKT+RS80": (dpp >= 50) & MR,
         "DP<30+MKT+RS80 (low delivery)": (dpp < 30) & MR}
    keep = c.notna().values.T.ravel()
    flat = lambda df: np.asarray(df.values, float).T.ravel()[keep]
    flatb = lambda df: np.asarray(df.fillna(False).values, bool).T.ravel()[keep]
    seg = np.repeat(np.arange(c.shape[1]), c.shape[0])[keep].astype(np.int64); tix = np.tile(np.arange(c.shape[0]), c.shape[1])[keep]
    O_, H_, L_, C_, A = flat(o), flat(h), flat(l), flat(c), flat(atr); E_ = flatb(e)
    cf = np.full(len(C_), COST); nan = np.full(len(C_), np.nan); ed_all = days[tix]
    mx, lng, tn = (26, 104, 8) if tf == "1w" else (60, 250, 20)
    EXITS = [("3ATR 3R", 3., 3., 0, mx), ("2ATR half1R+3R", 2., 3., 4, mx), ("2ATR trail3ATR", 2., 0., 2, lng)]
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
            si, ei, xi, g, nr, *_ = S.simulate(O_, H_, L_, C_, A, seg, cf, M, C_ - k * A, nan, nan, kind, r, mh, tn, 3.0, 3, 0.25, 6.0, 1.0)
            if len(nr) < 90:
                continue
            ed = ed_all[ei]; p = T.per(ed); pct = nr * k * A[si] / O_[ei] * 100
            row = dict(tf=tf, entry=en, filt=fn, exit=name, trades=len(nr), per_month_2025_26=round(float((ed >= "2025-01-01").sum() / 22.5), 1),
                       win=round(100 * float((nr > 0).mean()), 1), R=round(float(nr.mean()), 3), avg_pct=round(float(pct.mean()), 2))
            for pp in PER:
                x = nr[p == pp]; row[f"{pp}_n"] = len(x); row[f"{pp}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else None
                row[f"{pp}_R"] = round(float(x.mean()), 3) if len(x) else None; row[f"{pp}_rand"] = round(rand[name][pp], 3)
                row[f"{pp}_pct"] = round(float(pct[p == pp].mean()), 2) if len(x) else None
            rows.append(row)
        print(tf, en, fn, len(rows), flush=True)
    return rows


if __name__ == "__main__":
    main()
