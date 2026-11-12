"""CASHQ-I – intraday experiments on NSE cash 5-minute candles (218 liquid stocks, 2024-10-14 … 2026-11-06), timeframes
5 / 15 / 30 / 60 minutes, LONG and SHORT (intraday MIS only; square-off at the close of the 15:15 bar; no entry after
14:30). Pre-registered signals below; stop = signal-bar extreme ± 0.1 ATR (bounded 0.5-2.5 ATR of that timeframe);
exits 0.5 / 1 / 1.5 / 2 / 3 R or square-off only. Costs 0.163 % round trip (Angel intraday schedule + 0.04 %/side).
python -m research.cashq.intra_run  -> results/intra_leaderboard.csv, intra_trades.csv.gz"""
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from . import data as D, ind as I, div as DV, engine as EN, validate as V

OUT = Path(__import__("os").getenv("CQ_OUT") or (Path(__file__).resolve().parent / "results"))
OUT.mkdir(exist_ok=True)
TFS = (5, 15, 30, 60)
EXITS = tuple(float(x) for x in __import__("os").getenv("CQ_EXITS", "0.5,1,1.5,2,3,0").split(","))


def market_since_open(frames):
    """EW average move since the day's open across all stocks at each bar close (point in time)."""
    parts = []
    for k, d in frames.items():
        day = d["time"].dt.normalize()
        op = d.groupby(day)["open"].transform("first")
        parts.append(pd.Series((d["close"] / op - 1).values, index=d["time"].values))
    M = pd.concat(parts, axis=1)
    return M.mean(axis=1)


def feats(d, tf, mkt):
    o, h, l, c, v = d["open"], d["high"], d["low"], d["close"], d["volume"]
    t = d["time"]; day = t.dt.normalize()
    f = pd.DataFrame(index=d.index)
    f["atr"] = I.atr(h, l, c, 14)
    f["rsi14"], f["rsi7"] = I.rsi(c, 14), I.rsi(c, 7)
    f["adx"] = I.adx(h, l, c, 14)
    f["ema20"], f["ema50"] = I.ema(c, 20), I.ema(c, 50)
    tp = (h + l + c) / 3
    f["vwap"] = (tp * v).groupby(day).cumsum() / v.groupby(day).cumsum().replace(0, np.nan)
    tod = t.dt.hour * 60 + t.dt.minute
    f["rvol"] = v / v.groupby(tod).transform(lambda x: x.rolling(20, min_periods=10).mean().shift(1))
    f["clv"] = I.clv(h, l, c)
    f["hammer"], f["star"] = I.hammer(o, h, l, c), I.shooting_star(o, h, l, c)
    f["beng"], f["seng"] = I.bull_engulf(o, h, l, c), I.bear_engulf(o, h, l, c)
    dh, dl, dc, do = h.groupby(day).max(), l.groupby(day).min(), c.groupby(day).last(), o.groupby(day).first()
    f["pdh"], f["pdl"], f["pdc"] = day.map(dh.shift(1)), day.map(dl.shift(1)), day.map(dc.shift(1))
    f["dopen"] = day.map(do)
    f["d_trend"] = day.map((dc > I.ema(dc, 20)).shift(1).astype(float))                  # prior day close vs daily EMA20
    first30 = tod < 9 * 60 + 45
    f["orh"] = h.where(first30).groupby(day).transform("max"); f["orl"] = l.where(first30).groupby(day).transform("min")
    f["after_or"] = tod >= 9 * 60 + 45
    f["mkt"] = mkt.reindex(t.values).values
    f["new_day"] = day != day.shift(1)
    return f


def side_signals(d, f, s):
    """dict name -> bool array for side s (+1 long / −1 short); every condition uses bar t or earlier only."""
    o, h, l, c = d["open"], d["high"], d["low"], d["close"]
    L = s > 0
    x_up = lambda r, a: (r > a) & (r.shift(1) <= a)
    x_dn = lambda r, a: (r < a) & (r.shift(1) >= a)
    rsi_x = lambda r, lo, hi: x_up(r, lo) if L else x_dn(r, hi)
    cand = (f["hammer"] | f["beng"]) if L else (f["star"] | f["seng"])
    brk3 = (c > h.shift(1).rolling(3).max()) if L else (c < l.shift(1).rolling(3).min())
    above = (c > f["vwap"]) if L else (c < f["vwap"])
    S = {}
    S["I1_RSI14_25_75"] = rsi_x(f["rsi14"], 25, 75)
    S["I2_RSI14_30_70_candle"] = rsi_x(f["rsi14"], 30, 70) & cand
    S["I3_RSI7_20_80_rvol_break"] = rsi_x(f["rsi7"], 20, 80) & (f["rvol"] >= 1.5) & brk3
    osc_r, osc_m = f["rsi14"].values.astype(float), I.macd_hist(c).values.astype(float)
    S["I4_RSIdiv_struct"] = pd.Series(DV.divergence(h.values, l.values, c.values, osc_r, s, False, 3, 40, 10)[0], index=d.index)
    S["I5_MACDdiv_rvol"] = pd.Series(DV.divergence(h.values, l.values, c.values, osc_m, s, False, 3, 40, 10)[0], index=d.index) & (f["rvol"] >= 1.5)
    side_prev = (c.shift(1) < f["vwap"].shift(1)) if L else (c.shift(1) > f["vwap"].shift(1))
    S["I6_VWAP_reclaim_adx_rvol"] = above & side_prev.rolling(6).min().fillna(0).astype(bool) & (f["rvol"] >= 1.5) & (f["adx"] > 20)
    tr = (f["ema20"] > f["ema50"]) if L else (f["ema20"] < f["ema50"])
    touch = (l <= f["vwap"]) if L else (h >= f["vwap"])
    S["I7_VWAP_pullback_trend"] = above.shift(1).fillna(False).astype(bool) & tr & touch & above & ((f["clv"] >= 0.6) if L else (f["clv"] <= 0.4))
    orb = (c > f["orh"]) if L else (c < f["orl"])
    S["I8_ORB30_mkt"] = f["after_or"] & orb & ~orb.shift(1).fillna(False).astype(bool) & ((f["mkt"] > 0) if L else (f["mkt"] < 0))
    pd_ = (c > f["pdh"]) if L else (c < f["pdl"])
    S["I9_PDH_PDL_break_rvol"] = pd_ & ~pd_.shift(1).fillna(False).astype(bool) & (f["rvol"] >= 1.5) & ~f["new_day"]
    sweep = ((l < f["pdl"]) & (c > f["pdl"]) & (f["clv"] >= 0.6)) if L else ((h > f["pdh"]) & (c < f["pdh"]) & (f["clv"] <= 0.4))
    S["I10_sweep_PD_reversal"] = sweep & ~f["new_day"]
    gap = f["dopen"] / f["pdc"] - 1
    S["I11a_gap_continuation"] = ((gap >= 0.01) if L else (gap <= -0.01)) & f["after_or"] & orb & ~orb.shift(1).fillna(False).astype(bool)
    back = (c > f["pdc"]) if L else (c < f["pdc"])
    S["I11b_gap_reversal"] = ((gap <= -0.01) if L else (gap >= 0.01)) & back & ~back.shift(1).fillna(False).astype(bool) & ~f["new_day"]
    dtr = (f["d_trend"] == 1) if L else (f["d_trend"] == 0)
    S["I12_daily_trend_pullback"] = dtr & above & rsi_x(f["rsi14"], 40, 60)
    full = dict(vwap=above, adx=f["adx"] > 20, rvol=f["rvol"] >= 1.5, mkt=(f["mkt"] > 0) if L else (f["mkt"] < 0), dtrend=dtr,
                bo=(c > h.shift(1).rolling(20).max()) if L else (c < l.shift(1).rolling(20).min()))
    S["I13_FULL"] = _all(full)
    for k in full:
        S[f"I13_FULL_minus_{k}"] = _all({a: b for a, b in full.items() if a != k})
    return {k: v.fillna(False).astype(bool).values for k, v in S.items()}


def _all(dct):
    out = None
    for v in dct.values():
        out = v if out is None else out & v
    return out


def rdist(d, f, s):
    a = f["atr"]
    k = float(__import__("os").getenv("CQ_STOPX", "0"))
    if k > 0:                                       # CQI-2 follow-up: fixed k x ATR stop (wider stop -> smaller cost in R)
        return (k * a).values
    r = (d["close"] - d["low"] + 0.1 * a) if s > 0 else (d["high"] - d["close"] + 0.1 * a)
    return r.clip(lower=0.5 * a, upper=2.5 * a).values


def main():
    t0 = time.time()
    import os
    syms = D.intraday_symbols()[: int(os.getenv("CQ_LIMIT", "100000"))]
    global TFS
    TFS = tuple(int(x) for x in os.getenv("CQ_TFS", ",".join(map(str, TFS))).split(","))
    base = {k: D.intraday(k) for k in syms}
    print(f"loaded {len(base)} stocks {time.time() - t0:.0f}s", flush=True)
    rows, ledgers = [], []
    for tf in TFS:
        fr = {k: D.resample(d, tf) for k, d in base.items()}
        mkt = market_since_open(fr)
        FE = {k: feats(d, tf, mkt) for k, d in fr.items()}
        for s in (1, -1):
            SG = {k: side_signals(fr[k], FE[k], s) for k in fr}
            RD = {k: rdist(fr[k], FE[k], s) for k in fr}
            names = next(iter(SG.values())).keys()
            for nm in names:
                sigs = {k: SG[k][nm] for k in fr}
                for R in EXITS:
                    T = EN.intraday_trades(fr, sigs, RD, s, R, last_entry=870 - tf, sq=915 - tf)   # entry bar starts <= 14:30; out by 15:15
                    if not len(T):
                        continue
                    T["strategy"], T["tf"], T["side"], T["R"] = nm, tf, s, R
                    fam = ("RSI" if nm[:3] in ("I1_", "I2_", "I3_") else "DIVERGENCE" if nm[:3] in ("I4_", "I5_") else
                           "COMBINED" if nm.startswith("I13") or nm.startswith("I12") else "PRICE_ACTION")
                    _k = __import__("os").getenv("CQ_STOPX", "")
                    row = dict(exp_id=f"CQI{'2-' + _k + 'ATR' if _k else ''}-{tf}m-{'L' if s > 0 else 'S'}-{nm}-{R:g}R", strategy=nm, family=fam, tf=f"{tf}m",
                               side="LONG" if s > 0 else "SHORT", R=R, params=f"{tf}-min, {'target ' + format(R, 'g') + 'R' if R else 'square-off only'}, stop signal-bar extreme ±0.1 ATR (0.5-2.5 ATR)")
                    for k_, t_ in V.split(T, V.INTRA_SPLITS).items():
                        for a, b in V.metrics(t_).items():
                            row[f"{k_}_{a}"] = b
                    o = T[T["entry_time"] >= V.INTRA_SPLITS["OOS"][0]]
                    if len(o) > 2:
                        dd = o.groupby(o["entry_time"].dt.normalize())["netR"].mean()
                        tt = dd.mean() / (dd.std(ddof=1) / np.sqrt(len(dd))) if dd.std(ddof=1) > 0 else 0
                        row["OOS_t"], row["OOS_p"] = round(float(tt), 2), float(stats.t.sf(tt, len(dd) - 1))
                    rows.append(row)
                    if R in (1.0, 2.0, 0.0) and not _k:
                        ledgers.append(T)
            print(f"  tf {tf} side {s}: {time.time() - t0:.0f}s, rows {len(rows)}", flush=True)
    Lb = pd.DataFrame(rows)
    sel = Lb.apply(V.verdict, axis=1) != "NOT_SELECTED"
    Lb["OOS_q"] = 1.0
    Lb.loc[sel, "OOS_q"] = V.bh(Lb.loc[sel, "OOS_p"].fillna(1).values)
    Lb["status"] = Lb.apply(V.verdict, axis=1)
    Lb.to_csv(OUT / "intra_leaderboard.csv", index=False)
    if ledgers:
        pd.concat(ledgers, ignore_index=True).to_csv(OUT / "intra_trades.csv.gz", index=False)
    json.dump(dict(variants=len(Lb), trades_saved=int(sum(len(x) for x in ledgers)), seconds=round(time.time() - t0)), open(OUT / "intra_run.json", "w"))
    print(Lb["status"].value_counts().to_dict(), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
