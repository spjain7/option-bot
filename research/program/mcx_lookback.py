"""MCX-LOOKBACK-001 (30-Oct-2026, owner): live MCX breakout rule with a 3 / 5 / 10 / 15 / 20-candle lookback instead of 20.
Everything else as live: close beyond the N-candle high/low, volume > 1.5× the 20-candle average, EMA200 side;
3h: stop 2 ATR, target 2R, max 40 candles, stop cap 2.5 % · daily: stop 1.5 ATR, target 3R, max 40, cap 4 %.
Angel MCX futures Jul-2022 → Oct-2026 (7 commodities), harness execution (next open, chase rule, stop first, gaps), 2× costs.
python research/program/mcx_lookback.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H  # noqa: E402
from research.search import strategy_search as SS  # noqa: E402

T1, T2 = pd.Timestamp("2024-07-01"), pd.Timestamp("2025-07-01")
LIVE = {"3h": (2.0, 2.0, 40, 2.5), "1d": (1.5, 3.0, 40, 4.0)}
rows = []
for ex, name in SS.NAMES:
    if ex != "MCX":
        continue
    fr = H.angel(name, ex)
    for tf, df in fr.items():
        f = H.features(df.reset_index(drop=True)); f["switch"] = df["switch"].values
        cost = H.cost_series(name, f, "angel")
        k, r, mx, cap = LIVE[tf]
        for N in (3, 5, 10, 15, 20):
            f["hh"] = f["high"].shift(1).rolling(N).max(); f["ll"] = f["low"].shift(1).rolling(N).min()
            sig = H.bo_signal(f)
            for side in (1, -1):
                for t in H.simulate(f, sig, side, k, r, mx, cap, cost):
                    if t["status"] == "trade":
                        rows.append(dict(name=name, tf=tf, N=N, side="BUY" if side > 0 else "SELL", time=t["time"], exit=t["exit"],
                                         r1=t["r1"], r2=t["r2"]))
T = pd.DataFrame(rows)
T["split"] = np.where(T.time < T1, "train", np.where(T.time < T2, "valid", "test"))
T.to_csv(ROOT / "research/program/results/mcx_lookback_trades.csv", index=False)


def summ(g):
    return pd.Series(dict(n=len(g), win=(g.r2 > 0).mean() * 100, R=g.r2.mean(),
                          R_train=g[g.split == "train"].r2.mean(), R_valid=g[g.split == "valid"].r2.mean(), R_test=g[g.split == "test"].r2.mean(),
                          trades_per_month=len(g) / 51))


pd.set_option("display.width", 200); pd.set_option("display.max_rows", 300)
A = T.groupby(["tf", "side", "N"]).apply(summ).round(3)
print("ALL 7 COMMODITIES (R per trade after 2× costs):"); print(A.to_string())
B = T.groupby(["tf", "side", "name", "N"]).apply(summ).round(2)
B.to_csv(ROOT / "research/program/results/mcx_lookback_by_name.csv")
print("\nPER COMMODITY – R per trade (all years) by lookback N:")
P = T.groupby(["tf", "side", "name", "N"]).r2.mean().unstack("N").round(2)
C = T.groupby(["tf", "side", "name", "N"]).r2.size().unstack("N")
print(P.astype(str).add(" (").add(C.astype(str)).add(")").to_string())
