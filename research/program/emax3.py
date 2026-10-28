"""EMAX-003 (28-Oct-2026) – owner's follow-up: try many EMA pairs (not only 9/21) and take crossovers ONLY in trending
markets, skipping choppy sessions.

Pairs (14): 5/13, 5/20, 8/21, 9/21, 10/30, 12/26, 13/34, 13/48, 20/50, 21/55, 34/89, 50/100, 50/200, 100/200.
Trend / anti-chop filters, measured on the crossover candle (closed):
  none   – plain crossover
  A20    – ADX(14) ≥ 20
  A25    – ADX(14) ≥ 25
  A20R   – ADX(14) ≥ 20 and rising (above its value 3 candles earlier)
  CH50   – Choppiness Index(14) < 50
  CH45   – Choppiness Index(14) < 45 (stricter)
  TA20   – ADX ≥ 20 and price on the trade side of EMA200
Each filter with and without volume ≥ 1.5× (V). OI was dropped: EMAX-002 showed it does not help (stocks) or has no history (MCX).
Segments, exits, costs, periods and the PASS rule are the same as EMAX-002 (emax.py); stock 1-hour is skipped for run time
(stock 3-hour and daily are kept).
"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = EX.OUT
PAIRS = [(5, 13), (5, 20), (8, 21), (9, 21), (10, 30), (12, 26), (13, 34), (13, 48), (20, 50), (21, 55), (34, 89),
         (50, 100), (50, 200), (100, 200)]
FILTERS = ["none", "A20", "A25", "A20R", "CH50", "CH45", "TA20"]


def chop(f, n=14):
    tr = I.true_range(f)
    rng = f["high"].rolling(n).max() - f["low"].rolling(n).min()
    return (100 * np.log10(tr.rolling(n).sum() / rng.replace(0, np.nan)) / np.log10(n)).values


def one(job):
    rows = []
    try:
        fr = EX.frames(job)
    except Exception as e:
        print("skip", job[:2], e); return []
    name = job[1] if job[0] in ("mi", "nse", "proxy", "stk") else job[2]
    for seg, f, _od, cost in fr:
        if seg == "STOCKS 1h":
            continue
        f = f.reset_index(drop=True)
        if len(f) < 260:
            continue
        f["atr"] = I.atr(f, 14)
        v = f["volume"].astype(float); volx = (v / v.rolling(20).mean().shift(1)).values
        c = f["close"].values
        e200 = I.ema(f["close"], 200).values
        ax = I.adx(f, 14).values; ax3 = np.r_[np.full(3, np.nan), ax[:-3]]
        ch = chop(f)
        FL = {"none": np.ones(len(f), bool), "A20": ax >= 20, "A25": ax >= 25, "A20R": (ax >= 20) & (ax > ax3),
              "CH50": ch < 50, "CH45": ch < 45}
        for fa, sl in PAIRS:
            ef, es = I.ema(f["close"], fa).values, I.ema(f["close"], sl).values
            pf, ps = np.r_[np.nan, ef[:-1]], np.r_[np.nan, es[:-1]]
            up = (ef > es) & (pf <= ps)
            dn = (ef < es) & (pf >= ps)
            for side, base, opp in ((1, up, dn), (-1, dn, up)):
                tside = (c > e200) if side > 0 else (c < e200)
                for flt in FILTERS:
                    m = (FL["A20"] & tside) if flt == "TA20" else FL[flt]
                    for vol in (False, True):
                        sig = base & m & ((volx >= 1.5) if vol else True)
                        if not sig.any():
                            continue
                        for ex in EX.EXITS:
                            for (i, r1, r2, bars) in EX.sim(f, sig, side, ex, cost, opp):
                                rows.append((seg, name, f"{fa}/{sl}", "BUY" if side > 0 else "SELL",
                                             flt + ("+V" if vol else ""), ex, f["time"].iat[i], r1, r2, bars))
    return rows


def main():
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(one, EX.jobs(), chunksize=1) for r in x]
    T = pd.DataFrame(rows, columns=["seg", "name", "pair", "side", "conf", "exit", "time", "r1", "r2", "bars"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    long_hist = T["seg"].str.contains("NSE|proxy")
    a = np.where(long_hist, np.datetime64("2019-01-01"), np.datetime64("2024-07-01"))
    b = np.where(long_hist, np.datetime64("2022-01-01"), np.datetime64("2025-07-01"))
    T["split"] = np.where(T["time"].values < a, "1-train", np.where(T["time"].values < b, "2-valid", "3-test"))
    is15 = T["seg"].str.endswith("15m")
    if is15.any():
        mid = T.loc[is15, "time"].quantile(0.5)
        T.loc[is15, "split"] = np.where(T.loc[is15, "time"] < mid, "1-train", "3-test")
    T.to_csv(OUT / "emax3_trades.csv.gz", index=False)
    g = T.groupby(["seg", "pair", "side", "conf", "exit", "split"])
    st = g.agg(n=("r1", "size"), win=("r1", lambda x: (x > 0).mean() * 100), exp2=("r2", "mean"),
               gw=("r1", lambda x: x[x > 0].sum()), gl=("r1", lambda x: -x[x <= 0].sum())).reset_index()
    st["pf"] = st["gw"] / st["gl"].replace(0, np.nan)
    W = st.pivot_table(index=["seg", "pair", "side", "conf", "exit"], columns="split", values=["n", "win", "exp2", "pf"])
    W.columns = [f"{bb[2:]}_{aa}" for aa, bb in W.columns]
    W = W.reset_index()
    for col in ("valid_n", "valid_win", "valid_exp2", "valid_pf"):
        if col not in W:
            W[col] = np.nan

    def ok(r):
        sp = ("train", "test") if r["seg"].endswith("15m") else ("train", "valid", "test")
        nmin = dict(train=30, valid=15, test=15) if not r["seg"].endswith("15m") else dict(train=15, test=15)
        return all((r.get(f"{s}_n") or 0) >= nmin[s] and (r.get(f"{s}_exp2") or -1) > 0 and (r.get(f"{s}_pf") or 0) >= 1.2
                   for s in sp)
    W["pass"] = [ok(r) for r in W.to_dict("records")]
    pooled = T.groupby(["seg", "pair", "side", "conf", "exit"]).agg(
        all_n=("r1", "size"), all_win=("r1", lambda x: (x > 0).mean() * 100), all_exp2=("r2", "mean"),
        gw=("r1", lambda x: x[x > 0].sum()), gl=("r1", lambda x: -x[x <= 0].sum())).reset_index()
    pooled["all_pf"] = pooled["gw"] / pooled["gl"].replace(0, np.nan)
    W = W.merge(pooled.drop(columns=["gw", "gl"]), on=["seg", "pair", "side", "conf", "exit"])
    W.to_csv(OUT / "emax3_variants.csv", index=False)
    print("variants", len(W), "pass", int(W["pass"].sum()))


if __name__ == "__main__":
    main()
