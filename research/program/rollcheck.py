"""ROLLCHECK-001 (6-Nov-2026): the 20-year MCX daily file is an UNADJUSTED front-month stitch with no contract labels;
earlier daily / weekly / monthly validations held trades through roll gaps (2-6x normal gaps). Re-validate every live MCX
daily+ rule three ways: as before (raw), exit at each roll (conservative), ratio back-adjusted series (realistic roll).
python research/program/rollcheck.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import rsix as RX, structx as SX  # noqa: E402
from research.program.missed import RB  # noqa: E402  (production rulebook code)
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

def adjust(d):
    d = d.copy()
    r = (d.close.shift(1) / d.open).where(d.switch, 1.0).fillna(1.0).values
    cum = np.r_[np.cumprod(r[::-1])[::-1][1:], 1.0]
    for c in ("open", "high", "low", "close"):
        d[c] = d[c] * cum
    return d

def resample(d, rule):
    k = d.time.dt.to_period(rule)
    return d.groupby(k).agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                            close=("close", "last"), volume=("volume", "sum"), switch=("switch", "max")).reset_index(drop=True)

def signals(f, rid):
    ff = RB.features(f); c, h, l = f.close.values, f.high.values, f.low.values; n = len(f)
    if rid == "BO_1d (20d high, ADX>=25)":
        m = (c > pd.Series(h).shift(1).rolling(20).max().values) & (np.nan_to_num(ff.adx.values) >= 25)
    elif rid == "BO_1w (20-week high)":
        m = c > pd.Series(h).shift(1).rolling(20).max().values
    elif rid == "BO_1M (month close > prev high)":
        m = c > np.r_[np.nan, h[:-1]]
    else:
        ru = RB.RULES[rid]; b, s = RB.raw(ff, ru["fam"], ru["par"]); m = b.copy()
        if ru["filt"].startswith("DT"):
            m &= SX.dtrend(f, None, "1d") == 1
    idx = np.flatnonzero(np.nan_to_num(m.astype(float)).astype(bool) & (np.arange(n) >= 60))
    return idx.astype(np.int64), h[idx], l[idx]

RULES = {"BO_1d (20d high, ADX>=25)": ("D", 0, 1.5, 2, 20), "RB_MCX_1d_BO55_BUY": ("D", 0, 2.0, 3, 20),
         "RB_MCX_1d_RETEST_BUY": ("D", 0, 2.0, 3, 20), "RB_MCX_1d_RSIX_BUY": ("D", 1, 1.5, 3, 20),
         "BO_1w (20-week high)": ("W", 0, 2.0, 3, 12), "BO_1M (month close > prev high)": ("M", 0, 2.0, 3, 12)}

if __name__ == "__main__":
    out = []
    for rid, (fr, en, k, r, mh) in RULES.items():
        for mode in ("raw", "roll_exit", "adjusted"):
            rows = []
            for name in RX.NAMES:
                d = RX.daily_long(name)
                if mode == "adjusted":
                    d = adjust(d)
                f = d if fr == "D" else resample(d, fr)
                sw = f.switch.values.astype(np.bool_) if mode == "roll_exit" else np.zeros(len(f), np.bool_)
                o, h, l, c = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
                atr = I.atr(f, 14).values.astype(np.float64)
                cost = np.array([INS.cost_points(name, p, 1.0) for p in c], np.float64)
                idx, lv, iv = signals(f, rid)
                oi, rr, gg = SX.sim(o, h, l, c, atr, sw, idx, lv, iv, 1, en, 1, r, mh, 3, cost, k)
                rows += [(name, f.time.iloc[i], x) for i, x in zip(oi, rr)]
            T = pd.DataFrame(rows, columns=["name", "time", "R"]).sort_values("time")
            p = np.where(T.time < "2013", 0, np.where(T.time < "2020", 1, 2))
            w, ls = T.R[T.R > 0], T.R[T.R <= 0]; eq = T.R.cumsum()
            out.append(dict(rule=rid, mode=mode, n=len(T), win=100 * (T.R > 0).mean(), R=T.R.mean(), PF=w.sum() / -ls.sum(),
                            maxDD=(eq.cummax() - eq).max(), p1=T.R[p == 0].mean(), p2=T.R[p == 1].mean(), p3=T.R[p == 2].mean(),
                            names_pos=int((T.groupby("name").R.mean() > 0).sum())))
    O = pd.DataFrame(out); O["all3"] = (O.p1 > 0) & (O.p2 > 0) & (O.p3 > 0)
    O.to_csv(ROOT / "research/program/results/rollcheck.csv", index=False)
    pd.set_option("display.width", 220); print(O.round(2).to_string(index=False))
