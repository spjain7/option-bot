"""STRUCTX-001 H1 on the LIVE rules with their exact parameters: next-open entry (production) vs stop above the signal
candle's high (cancel if its low breaks, 6 candles, no chase > 0.5 ATR). Daily-trend filter as live. 2x costs.
python research/program/structx_live.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import rsix as RX, structx as SX  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

LIVE = {"RB_MCX_4h_EMA1348_BUY": ("4h", "B_EMA1348", 2.0, 3, 40), "RB_MCX_4h_MACD0_BUY": ("4h", "B_MACD0", 1.5, 2, 40),
        "RB_MCX_2h_MOMO_BUY": ("2h", "B_MOMO", 2.0, 3, 50), "RB_MCX_2h_EMA921_BUY": ("2h", "B_EMA921", 3.0, 6, 50)}
P1, P2 = np.datetime64("2024-07-01"), np.datetime64("2025-07-01")

def trades():
    rows = []
    for name in RX.NAMES:
        fr = dict(RX.frames(name))
        for rid, (tf, su, k, r, mh) in LIVE.items():
            f = fr[tf].reset_index(drop=True)
            o, h, l, c = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
            atr = I.atr(f, 14).values.astype(np.float64)
            sw = f["switch"].fillna(False).values.astype(np.bool_)
            cost = np.array([INS.cost_points(name, p, 1.0) for p in c], np.float64)
            dt = SX.dtrend(f, name, tf)
            side, idx, lv, iv = SX.setups(f, tf)[su]
            keep = dt[idx] == 1
            ii, L, V = idx[keep].astype(np.int64), np.asarray(lv, float)[keep], np.asarray(iv, float)[keep]
            t = pd.to_datetime(f.time).values
            for en, nm in ((0, "NEXT_OPEN"), (1, "STOP_ABOVE_HIGH"), (2, "CLOSE_ABOVE_HIGH")):
                oi, rr, gg = SX.sim(o, h, l, c, atr, sw, ii, L, V, 1, en, 1, r, mh, 6, cost, k)
                for a_, b_ in zip(t[oi], rr):
                    rows.append((rid, name, nm, a_, b_))
    return pd.DataFrame(rows, columns=["rule", "name", "entry", "time", "R"])

def stats(x):
    w, ls = x[x > 0], x[x <= 0]
    eq = x.cumsum(); dd = (eq.cummax() - eq).max() if len(x) else 0
    return pd.Series(dict(n=len(x), win=100 * (x > 0).mean(), R=x.mean(), PF=w.sum() / max(1e-9, -ls.sum()), maxDD=dd))

if __name__ == "__main__":
    T = trades().sort_values("time")
    T["per"] = np.where(T.time < P1, "p1", np.where(T.time < P2, "p2", "p3"))
    T.to_csv(ROOT / "research/program/results/structx_live_trades.csv", index=False)
    pd.set_option("display.width", 200)
    print(T.groupby(["rule", "entry"]).R.apply(stats).unstack().round(2))
    print(T.pivot_table(index=["rule", "entry"], columns="per", values="R", aggfunc="mean").round(2))
    print("\nALL FOUR RULES (portfolio, one trade at a time per rule & commodity):")
    print(T.groupby("entry").R.apply(stats).unstack().round(2))
    print(T.pivot_table(index="entry", columns="per", values="R", aggfunc="mean").round(3))
    print((T.groupby(["entry", "name"]).R.mean().unstack() > 0).sum(axis=1).rename("commodities positive"))
