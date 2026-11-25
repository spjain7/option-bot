"""WK-SELL-SR-001 (25-Nov-2026, owner: "weekly breakdown SELL – correct the too-far SL/target with proper support /
resistance and make it live"). MCX daily bhav Jul-2022..Nov-2026 (ratio back-adjusted front month, mcx_pos.series), weekly
candles from it. Signal = the live rule (breakout.evaluate_weekly): weekly close below the prior 20-week low. Entry next
week's open, stop first on daily candles, max 26 weeks, 0.10 % costs. Stop / target variants:
  PWHcap  the signal week's high + 0.1 wATR, but at most 2 daily ATR      SUP2  next support if >= 2R away, else 3R
  SL  W2ATR  2 weekly ATR (live today)       D1.5 / D2 / D3  1.5 / 2 / 3 daily ATR       PWH  signal week's high + 0.1 weekly ATR       SW4  4-week swing high + 0.1 wATR
  TG  2R / 3R  ·  SUP  next support = the lowest weekly low of the prior 52 weeks below the 20-week low (>= 1R away, else 2R)
python research/program/wk_sell_sr.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import mcx_pos as M  # noqa: E402

D = M.load(); rows = []
for sym in M.COMS:
    d = M.series(D, sym)
    d["wk"] = d.time.dt.to_period("W")
    w = d.groupby("wk").agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")).reset_index()
    tr = pd.concat([w.high - w.low, (w.high - w.close.shift(1)).abs(), (w.low - w.close.shift(1)).abs()], axis=1).max(axis=1)
    watr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    ll20 = w.low.shift(1).rolling(20).min()
    sig = (w.close < ll20)
    for i in np.flatnonzero(sig.values):
        if i < 25 or i + 1 >= len(w):
            continue
        wk_next = w.wk.iat[i + 1]
        dd = d[d.wk >= wk_next].reset_index(drop=True)
        if dd.empty:
            continue
        e = float(dd.open.iat[0]); a = float(watr.iat[i])
        dtr = pd.concat([d.high - d.low, (d.high - d.close.shift(1)).abs(), (d.low - d.close.shift(1)).abs()], axis=1).max(axis=1)
        da = float(dtr.ewm(alpha=1 / 14, adjust=False).mean()[d.wk < wk_next].iat[-1])
        stops = {"W2ATR": e + 2 * a, "D1.5": e + 1.5 * da, "D2": e + 2 * da, "D3": e + 3 * da, "PWH": float(w.high.iat[i]) + 0.1 * a, "SW4": float(w.high.iloc[i - 3:i + 1].max()) + 0.1 * a,
                 "PWHcap": min(float(w.high.iat[i]) + 0.1 * a, e + 2 * da)}
        sup_lv = w.low.iloc[max(0, i - 52):i].min()
        for sn, stp in stops.items():
            R = stp - e
            if R <= 0:
                continue
            sup = sup_lv if (e - sup_lv) >= R else e - 2 * R
            sup2 = sup_lv if (e - sup_lv) >= 2 * R else e - 3 * R
            for tn, tg in (("2R", e - 2 * R), ("3R", e - 3 * R), ("SUP", sup), ("SUP2", sup2)):
                px = None; why = "time"
                end = dd[dd.time < dd.time.iat[0] + pd.Timedelta(weeks=26)]
                for j in range(len(end)):
                    if end.high.iat[j] >= stp:
                        px = max(end.open.iat[j], stp) if j else stp; why = "stop"; break
                    if end.low.iat[j] <= tg:
                        px = min(end.open.iat[j], tg) if j else tg; why = "target"; break
                if px is None:
                    px = end.close.iat[-1]
                rows.append(dict(sym=sym, t=w.time.iat[i], sl=sn, tg=tn, sl_pct=100 * R / e, tg_pct=100 * (e - tg) / e,
                                 R=(e - px) / R - 0.001 * e / R, why=why, days=j + 1))
T = pd.DataFrame(rows); T["y"] = T.t.dt.year
pd.set_option("display.width", 200)
g = T.groupby(["sl", "tg"]).apply(lambda x: pd.Series(dict(n=len(x), win=round(100 * (x.R > 0).mean()), R=round(x.R.mean(), 2),
                                                             sl_pct=round(x.sl_pct.median(), 1), tg_pct=round(x.tg_pct.median(), 1),
                                                             days=round(x.days.median())))).reset_index()
print(g.to_string(index=False))
print(T[(T.sl == "PWH") & (T.tg == "2R")].groupby("y").R.agg(["size", "mean"]).round(2).T.to_string())
print(T[(T.sl == "W2ATR") & (T.tg == "3R")].groupby("y").R.agg(["size", "mean"]).round(2).T.to_string())
T.to_csv(ROOT / "research/program/results/wk_sell_sr_trades.csv", index=False)
