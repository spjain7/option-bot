"""ROUND 4 (owner 17-Nov-2026): "find the perfect combo 3h / 4h / daily / weekly / monthly breakout & breakdown, and a separate
strategy for every commodity if required". Research only.
  candles   3h, 4h (Jul-2022 ->)  ·  daily, weekly, monthly (2006 ->; weekly / monthly built from daily, back-adjusted,
            held across contract rolls; costs x2 weekly, x3 monthly to cover the rolls)
  signals   BUY breakout / SELL breakdown of the last 10 / 20 / 55 candles, of the previous week's / month's high (low),
            strong-candle (body >= 80 % of range, range >= 1.2 ATR) 20-candle breakout
  filters   none / volume > 1.5x / higher-timeframe trend (HT1 = next timeframe up, HT2 = two up: 3h,4h -> daily, weekly;
            daily -> weekly, monthly; weekly -> monthly; monthly -> own 12-month EMA) and combinations
            trend = previous COMPLETED higher candle: close > EMA20 > EMA50 (mirror for SELL)
  exits     stop 1.5 / 2 / 3 ATR x target 0.75 / 1 / 2 / 3 R, and a 3 ATR trailing stop (stop 2 ATR)
  periods   intraday TRAIN 2022-07..2024-06 / VALID ..2025-06 / OOS ..2026-10;  daily+ TRAIN 2006-16 / VALID 2017-21 / OOS 2022-26
  choice    POOLED: same rule on all 7, chosen on TRAIN + VALID.   PER COMMODITY: each commodity's own rule, chosen on
            TRAIN + VALID with a robustness score (worse of the two periods, shrunk by trade count, neighbours must agree).
            OOS shown unchanged for both, so the two approaches are compared on data neither saw.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round4 -> reports/mcx_round4*.csv / .json"""
import itertools
import json
import warnings
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import data as D, costs as K, sim as S, runner as RN
from research.mcx_institutional_buy.feature_engineering import ind as I
from research.mcx_institutional_buy.stock_rules_on_mcx.run import frames

warnings.filterwarnings("ignore")
TFS = ["3h", "4h", "1d", "1w", "1M"]
ORD = ["1h", "2h", "3h", "4h", "1d", "1w", "1M"]
HT = {"1h": ("1d", "1w"), "2h": ("1d", "1w"), "3h": ("1d", "1w"), "4h": ("1d", "1w"), "1d": ("1w", "1M"), "1w": ("1M", None), "1M": (None, None)}
FAMS = ["BO10", "BO20", "BO55", "PWK", "PMO", "MARU20"]
FILTS = [(), ("VOL",), ("HT1",), ("HT2",), ("HT1", "HT2"), ("VOL", "HT1"), ("VOL", "HT1", "HT2")]
EXITS = [(k, r, 0) for k in (1.5, 2.0, 3.0) for r in (0.75, 1.0, 2.0, 3.0)] + [(2.0, 0.0, 2)]
MAXH = {"3h": 40, "4h": 40, "1d": 40, "1w": 26, "1M": 12}
CMUL = {"3h": 1, "4h": 1, "1d": 1, "1w": 2, "1M": 3}
MULT = {k: v["mult"] for k, v in K.CFG["contracts"].items()}
NAN = {}


def resample(dd, rule):
    d = dd.copy(); d["time"] = pd.to_datetime(d["time"])
    g = d.set_index("time").resample(rule, label="left")
    out = pd.DataFrame(dict(open=g.open.first(), high=g.high.max(), low=g.low.min(), close=g.close.last(), volume=g.volume.sum(),
                            raw_close=g.raw_close.last(), first=g.open.apply(lambda x: x.index.min()))).dropna(subset=["close"])
    out["time"] = out["first"]
    return out.reset_index(drop=True)[["time", "open", "high", "low", "close", "volume", "raw_close"]]


def feats(f):
    f = f.reset_index(drop=True).copy()
    f["atr"] = I.atr(f["high"].values, f["low"].values, f["close"].values, 14)
    f["volx"] = f["volume"] / f["volume"].rolling(20).mean().shift(1)
    return f


def trend_map(f, t_lo, period_end_known):
    """for each lower-timeframe time, the trend of the last COMPLETED higher candle (+1 / -1 / 0)."""
    c = f["close"]; e20, e50 = I.ema(c, 20), I.ema(c, 50)
    tr = np.where((c > e20) & (e20 > e50), 1, np.where((c < e20) & (e20 < e50), -1, 0))
    s = pd.Series(tr, index=period_end_known)           # time from which this candle's trend is known
    s = s[~s.index.duplicated(keep="last")].sort_index()
    idx = np.searchsorted(s.index.values, np.asarray(t_lo, "datetime64[ns]"), side="right") - 1
    out = np.where(idx >= 0, s.values[np.clip(idx, 0, None)], 0)
    return out


def prev_level(f_hi, t_lo, known_from, col):
    s = pd.Series(f_hi[col].values, index=known_from)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    idx = np.searchsorted(s.index.values, np.asarray(t_lo, "datetime64[ns]"), side="right") - 1
    return np.where(idx >= 0, s.values[np.clip(idx, 0, None)], np.nan)


def build(name, tfs=None):
    F, dd = frames(name)
    dd = dd.reset_index(drop=True)
    w = resample(dd, "W-MON") if False else resample(dd, "W")
    m = resample(dd, "MS")
    fr = {"1h": F["1h"].reset_index(drop=True), "2h": F["2h"].reset_index(drop=True), "3h": F["3h"].reset_index(drop=True), "4h": F["4h"].reset_index(drop=True), "1d": feats(dd), "1w": feats(w), "1M": feats(m)}
    for k in ("1h", "2h", "3h", "4h"):
        fr[k]["atr"] = fr[k]["atr"].values
    # gap segments only for weekly / monthly (positions are rolled; costs raised instead)
    for k in ("1w", "1M"):
        gap = pd.to_datetime(fr[k]["time"]).diff().dt.days.fillna(0) > (45 if k == "1w" else 70)
        fr[k]["seg"] = np.cumsum(gap.values)
    # when each higher candle is complete (known): next day / next week / next month start
    known = {"1d": pd.to_datetime(fr["1d"]["time"]).dt.normalize() + pd.Timedelta(days=1),
             "1w": pd.to_datetime(fr["1w"]["time"]) + pd.Timedelta(days=7),
             "1M": pd.to_datetime(fr["1M"]["time"]) + pd.offsets.MonthBegin(1)}
    out = {}
    for tf in (tfs or TFS):
        f = fr[tf]; t = pd.to_datetime(f["time"]).values
        if tf in ("1d",):
            t_eval = (pd.to_datetime(f["time"]).dt.normalize() + pd.Timedelta(hours=23, minutes=59)).values   # decided at the close
        elif tf == "1w":
            t_eval = (pd.to_datetime(f["time"]) + pd.Timedelta(days=6, hours=23)).values
        elif tf == "1M":
            t_eval = (pd.to_datetime(f["time"]) + pd.offsets.MonthBegin(1) - pd.Timedelta(minutes=1)).values
        else:
            t_eval = (pd.to_datetime(f["time"]) + pd.Timedelta(hours=int(tf[0]))).values
        h1, h2 = HT[tf]
        ht = {}
        for lab, hk in (("HT1", h1), ("HT2", h2)):
            if hk is None:
                c = f["close"]; e = I.ema(c, 12)                              # monthly: own 12-candle EMA, previous candle
                ht[lab] = np.r_[0, np.sign((c - e).values[:-1])]
            else:
                ht[lab] = trend_map(fr[hk], t_eval, known[hk].values)
        lv = {}
        for lab, hk in (("PWK", "1w"), ("PMO", "1M")):
            if ORD.index(tf) >= ORD.index(hk):
                lv[lab] = None
            else:
                lv[lab] = (prev_level(fr[hk], t_eval, known[hk].values, "high"), prev_level(fr[hk], t_eval, known[hk].values, "low"))
        out[tf] = dict(f=f, ht=ht, lv=lv, per=RN.period_of("1h" if tf in ("1h", "2h", "3h", "4h") else "1d", pd.to_datetime(f["time"])))
    return out


def signals(d, side):
    f = d["f"]
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    if side < 0:
        o, h, l, c = -o, -l, -h, -c
    a = f["atr"].values.astype(float)
    rng_ = h - l; body = np.abs(c - o)
    P = {}
    for N in (10, 20, 55):
        P[f"BO{N}"] = c > pd.Series(h).shift(1).rolling(N).max().values
    for lab in ("PWK", "PMO"):
        if d["lv"][lab] is not None:
            hi, lo = d["lv"][lab]
            lvl = hi if side > 0 else -lo
            P[lab] = (c > lvl) & (np.r_[np.nan, c[:-1]] <= lvl)
    P["MARU20"] = P["BO20"] & (c > o) & (body >= 0.8 * rng_) & (rng_ >= 1.2 * a)
    cond = {"VOL": f["volx"].values > 1.5, "HT1": d["ht"]["HT1"] == side, "HT2": d["ht"]["HT2"] == side}
    arr = dict(o=o, h=h, l=l, c=c, a=a)
    return P, cond, arr


def run(arr, d, sig, side, k, r, kind, tf, name):
    f = d["f"]; n = len(arr["c"])
    NAN.setdefault(n, np.full(n, np.nan))
    costf = K.cost_frac(name, f["raw_close"].values, pd.to_datetime(f["time"])) * side * CMUL[tf]
    si, ei, xi, g, nr, mfe, mae, why, rej = S.simulate(arr["o"], arr["h"], arr["l"], arr["c"], arr["a"],
                                                       f["seg"].values.astype(np.int64), costf, np.nan_to_num(sig).astype(bool),
                                                       arr["c"] - k * arr["a"], NAN[n], NAN[n], kind, float(r), MAXH[tf], MAXH[tf],
                                                       3.0, 3, 0.25, 6.0, 1.5)
    return si, ei, xi, g, nr, mfe, mae, why


def pstats(nr, per):
    o = {}
    for p in ("TRAIN", "VAL", "OOS"):
        x = nr[per == p]; o[f"{p}_n"] = len(x)
        o[f"{p}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else np.nan
        o[f"{p}_R"] = round(float(x.mean()), 3) if len(x) else np.nan
    return o


def main():
    B = {n: build(n) for n in D.INTRA}
    print("built", flush=True)
    rows = []
    for name in D.INTRA:
        for tf in TFS:
            d = B[name][tf]
            for side in (1, -1):
                P, cond, arr = signals(d, side)
                for fam, base in P.items():
                    for flt in FILTS:
                        m = base.copy()
                        for c_ in flt:
                            m &= cond[c_]
                        if m.sum() < 5:
                            continue
                        for k, r, kind in EXITS:
                            si, ei, xi, g, nr, mfe, mae, why = run(arr, d, m, side, k, r, kind, tf, name)
                            if not len(nr):
                                continue
                            pe = d["per"][ei]
                            rows.append(dict(name=name, tf=tf, side="BUY" if side > 0 else "SELL", fam=fam, filt="+".join(flt) or "none",
                                             k=k, r=r, exit="trail 3ATR" if kind == 2 else f"{r}R", **pstats(nr, pe),
                                             sum_TRAIN=float(nr[pe == "TRAIN"].sum()), sum_VAL=float(nr[pe == "VAL"].sum()),
                                             sum_OOS=float(nr[pe == "OOS"].sum()),
                                             win_TRAIN=int((nr[pe == "TRAIN"] > 0).sum()), win_VAL=int((nr[pe == "VAL"] > 0).sum()),
                                             win_OOS=int((nr[pe == "OOS"] > 0).sum())))
            print(name, tf, len(rows), flush=True)
    L = pd.DataFrame(rows)
    L.to_csv(RN.REPORTS / "mcx_round4.csv", index=False)
    print("tested", len(L))


if __name__ == "__main__":
    main()
