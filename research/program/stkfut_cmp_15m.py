"""STKFUT-CMP-001 – 15-minute check of the intraday setups at their native resolution (exploratory: only 40 stock
futures, Aug–Oct 2026). Same simulator, costs and 1:1 exits as stkfut_cmp.py.
ORB15 (kite-algo-bot orb.py: 15-min range, RVOL ≥ 1.5, stop = range end or 1 ATR), ORB30 (backtest-platform orb_breakout:
30-min range, volume ≥ 1.5× today's average, stop = opposite end), VWAPPB (kite-algo-bot vwap_pullback), IBFAIL
(nse-algo system 7/8 on the first 15-min candle). Entries until 14:00, exit at the last candle of the day."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import reversal as RV, stkfut_cmp as SC  # noqa: E402
from research.search import stock_search as SR  # noqa: E402

def prep15(f):
    f = f.copy().reset_index(drop=True)
    f["day"] = f["time"].dt.normalize(); f["hhmm"] = f["time"].dt.strftime("%H:%M")
    g = f.groupby("day")
    d = g.agg(h=("high", "max"), l=("low", "min"))
    f["pdh"] = f["day"].map(d["h"].shift(1)); f["pdl"] = f["day"].map(d["l"].shift(1))
    f["bar"] = g.cumcount(); f["rollday"] = False
    f["dvol"] = g["volume"].transform(lambda v: v.expanding().mean().shift(1))
    return f

def setups(f):
    hh, bar = f["hhmm"].values, f["bar"].values
    o, h, l, c, v = (f[x].values for x in ("open", "high", "low", "close", "volume"))
    vw, e20, atr, rv = f["vwap"].values, f["ema20"].values, f["atr"].values, f["volx"].values
    day = f["day"].values
    done = {}
    for i in range(len(f)):
        if not np.isfinite(atr[i]) or hh[i] > "14:00":
            continue
        dk = day[i]; first = np.flatnonzero(day == dk)
        for name, nb in (("ORB15", 1), ("ORB30", 2)):
            if bar[i] >= nb and not done.get((name, dk)):
                rh, rl = h[first[:nb]].max(), l[first[:nb]].min()
                volok = (rv[i] >= 1.5) if name == "ORB15" else (v[i] >= 1.5 * f["dvol"].iat[i])
                if c[i] > rh and volok:
                    done[(name, dk)] = True
                    yield (name, i, 1, min(rl, c[i] - atr[i]) if name == "ORB15" else rl, "next_open", None)
                elif c[i] < rl and volok:
                    done[(name, dk)] = True
                    yield (name, i, -1, max(rh, c[i] + atr[i]) if name == "ORB15" else rh, "next_open", None)
        if bar[i] >= 2 and np.isfinite(vw[i]) and atr[i] > 0:
            dist = abs(c[i] - vw[i]) / atr[i]
            if c[i] > e20[i] and vw[i] < c[i] and dist <= 0.5 and l[i - 1] <= vw[i - 1] and c[i] > vw[i]:
                yield ("VWAPPB15", i, 1, vw[i] - 1.2 * atr[i], "next_open", None)
            elif c[i] < e20[i] and vw[i] > c[i] and dist <= 0.5 and h[i - 1] >= vw[i - 1] and c[i] < vw[i]:
                yield ("VWAPPB15", i, -1, vw[i] + 1.2 * atr[i], "next_open", None)
        if bar[i] == 0 and np.isfinite(f["pdh"].iat[i]):
            if o[i] > f["pdh"].iat[i] and c[i] < f["pdh"].iat[i]:
                yield ("IBFAIL15", i, -1, h[i], "stop", l[i])
            elif o[i] < f["pdl"].iat[i] and c[i] > f["pdl"].iat[i]:
                yield ("IBFAIL15", i, 1, l[i], "stop", h[i])

def main():
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv").set_index("name")
    rows = []
    for p in sorted((ROOT / "research/data/obuy").glob("fut_*.csv")):
        nm = p.stem[4:]
        if nm not in man.index:
            continue
        lot = int(man.loc[nm, "lot"])
        f = prep15(RV.m15(p, nm, "stock")[1])
        busy = {}
        for st, i, side, stop, em, trig in setups(f):
            if i <= busy.get(st, -1):
                continue
            t = SC.simulate(f, i, side, stop, em, trig, True, 1, lot)
            if t is None:
                continue
            busy[st] = t["j"]
            rows.append(dict(setup=st, name=nm, time=f["time"].iat[i], side=side, **{k: t[k] for k in ("why", "gross_R", "net_R", "net2_R", "cost_R", "rs")}))
    T = pd.DataFrame(rows); T.to_csv(ROOT / "research/program/results/stkfut_cmp_15m_trades.csv", index=False)
    mid = T["time"].quantile(0.5)
    def s(x):
        r = x["net_R"]; gw, gl = r[r > 0].sum(), -r[r <= 0].sum()
        return pd.Series(dict(n=len(x), win=round((r > 0).mean() * 100, 1), gross=round(x["gross_R"].mean(), 3), net=round(r.mean(), 3),
                              cost=round(x["cost_R"].mean(), 3), pf=round(gw / gl, 2) if gl else np.nan,
                              first_half=round(x[x["time"] < mid]["net_R"].mean(), 3), second_half=round(x[x["time"] >= mid]["net_R"].mean(), 3),
                              rs_per_lot=round(x["rs"].mean())))
    T["side"] = np.where(T["side"] > 0, "BUY", "SELL")
    print(T["time"].min(), T["time"].max(), T["name"].nunique(), "stocks")
    print(T.groupby(["setup", "side"]).apply(s).to_string())

if __name__ == "__main__":
    main()
