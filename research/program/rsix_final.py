"""RSIX-001 finalist – trade-level report (daily BUY: RSI(7) touch <= L, bullish candle, ADX(14) < 20, buy-stop above candle high).
python research/program/rsix_final.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import rsix as RX  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

def trades(name, L, cand="bull", filt="ADXL", stop=1, exitc=0, n_rsi=7):
    d = RX.daily_long(name)
    o, h, l, c = (d[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
    atr = I.atr(d, 14).values.astype(np.float64)
    m = RX.setup_masks(d, n_rsi)[(1, "E1", L, cand)] & RX.filter_masks(d, "1d", name, 1)[filt]
    idx = (np.flatnonzero(m[200:]) + 200).astype(np.int64)
    cost = np.array([INS.cost_points(name, p, 1.0) for p in c])
    ii, jj, rr, gg = RX.sim(o, h, l, c, atr, d.switch.values.astype(np.bool_), idx, 1, 1, stop, exitc, 20, cost)
    return pd.DataFrame(dict(name=name, time=d.time.values[ii], R=rr))

def report(L):
    T = pd.concat([trades(n, L) for n in RX.NAMES]).sort_values("time").reset_index(drop=True)
    eq = T.R.cumsum(); dd = (eq.cummax() - eq).max()
    w, ls = T.R[T.R > 0], T.R[T.R <= 0]
    T["per"] = np.where(T.time < "2013-01-01", "2006-12", np.where(T.time < "2020-01-01", "2013-19", "2020-26"))
    print(f"\n=== RSI(7) touch <= {L}, bullish candle, ADX<20, buy above candle high (3 days), SL 1.5 ATR, 3-ATR trailing exit")
    print(f"trades {len(T)}  win {100*(T.R>0).mean():.1f}%  expectancy {T.R.mean():+.2f}R  PF {w.sum()/-ls.sum():.2f}  "
          f"avg win {w.mean():+.2f}R  avg loss {ls.mean():+.2f}R  max DD {dd:.1f}R  per commodity/month {len(T)/7/245:.2f}")
    print(T.groupby("per").R.agg(["size", "mean", lambda x: (x > 0).mean() * 100]).round(2).rename(columns={"<lambda_0>": "win%"}))
    print(T.groupby("name").R.agg(["size", "mean"]).round(2).T)
    print("last 8 signals:\n", T.tail(8).round(2).to_string(index=False))
    return T

if __name__ == "__main__":
    for L in (25, 30):
        T = report(L)
    T.to_csv(ROOT / "research/program/results/rsix_final_trades.csv", index=False)
