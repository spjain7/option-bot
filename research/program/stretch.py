"""STRETCH-001 (6-Nov-2026, owner: "gold failed – analyse what works"). Live GOLD calls sold AFTER a −2.8 % day (daily RSI 28.7,
price ~5 % under EMA20) and bought AGAINST the daily downtrend after a +4.5 % bounce. Test on 4 years, live MCX breakout rules
(3h and 1d; BUY N=10/5, SELL N=20, vol 1.5x, EMA200, 2ATR/2R 3h · 1.5ATR/3R 1d, 2x costs, 7 commodities):
  stretch = (close − daily EMA20) / daily ATR14 at the signal (previous completed day for 3h) · daily RSI14 · daily trend (EMA20 vs 50)
python research/program/stretch.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX  # noqa: E402
from research.program.tf5h import T1, T2  # noqa: E402
from crude import indicators as I  # noqa: E402

NAMES = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]
RULE = {"3h": dict(nb=10, ns=20, k=2.0, r=2.0, mh=40), "1d": dict(nb=5, ns=20, k=1.5, r=3.0, mh=20)}
rows = []
for nm in NAMES:
    fr = {s.split()[-1]: (f, c) for s, f, o, c in EX.frames(("mi", nm, "MCX")) if s.startswith("MCX")}
    fd = fr["1d"][0].reset_index(drop=True).copy()
    dd = pd.DataFrame(dict(day=fd.time.dt.normalize(), ema20=I.ema(fd.close, 20), ema50=I.ema(fd.close, 50), atr=I.atr(fd, 14),
                           rsi=I.rsi(fd.close, 14), close=fd.close))
    dd["stretch"] = (dd.close - dd.ema20) / dd.atr
    for tf in ("3h", "1d"):
        f0, cost = fr[tf]
        f = H.features(f0.reset_index(drop=True)); f["switch"] = f0["switch"].values
        R_ = RULE[tf]
        for side, n in ((1, R_["nb"]), (-1, R_["ns"])):
            lvl = f.high.shift(1).rolling(n).max() if side > 0 else f.low.shift(1).rolling(n).min()
            ok = (side * (f.close - lvl) > 0) & (f.volx > 1.5) & (side * (f.close - f.ema200) > 0)
            sig = np.where(ok.values, side, 0)
            for x in H.simulate(f, sig, side, R_["k"], R_["r"], R_["mh"], 2.5, cost, start=210):
                if x["status"] != "trade":
                    continue
                t = pd.Timestamp(x["time"]); day = t.normalize()
                ref = dd[dd.day < day] if tf == "3h" else dd[dd.day <= day]
                if ref.empty:
                    continue
                q = ref.iloc[-1]
                rows.append(dict(name=nm, tf=tf, side="BUY" if side > 0 else "SELL", time=t, r=x["r2"], stretch=q.stretch * side,
                                 rsi=q.rsi, trend_with=bool((q.ema20 > q.ema50) == (side > 0))))
T = pd.DataFrame(rows)
T["split"] = np.where(T.time < T1, "p1", np.where(T.time < T2, "p2", "p3"))
T["stretch_b"] = pd.cut(T.stretch, [-99, 0, 1, 2, 3, 99], labels=["against", "0-1 ATR", "1-2 ATR", "2-3 ATR", ">3 ATR"])
T["rsi_x"] = np.where(T.side == "BUY", T.rsi > 70, T.rsi < 30)
pd.set_option("display.width", 200)
def tab(g):
    a = g.agg(n=("r", "size"), win=("r", lambda s: (s > 0).mean() * 100), R=("r", "mean"))
    return a.join(g["r"].apply(lambda s: None).rename("x")).drop(columns="x")
for keys in (["tf", "side", "stretch_b"], ["tf", "side", "rsi_x"], ["tf", "side", "trend_with"]):
    g = T.groupby(keys, observed=True)
    a = g.agg(n=("r", "size"), win=("r", lambda s: (s > 0).mean() * 100), R=("r", "mean"))
    a = a.join(T.pivot_table(index=keys, columns="split", values="r", aggfunc="mean", observed=True))
    print(a.round(3).to_string(), "\n")
base = T; filt = T[(T.stretch <= 2) & (~T.rsi_x) & T.trend_with]
for nm_, x in (("ALL live-rule trades", base), ("skip stretched >2 ATR, RSI extreme, against daily trend", filt)):
    a = x.groupby(["tf", "side"]).agg(n=("r", "size"), win=("r", lambda s: (s > 0).mean() * 100), R=("r", "mean"))
    a = a.join(x.pivot_table(index=["tf", "side"], columns="split", values="r", aggfunc="mean"))
    print(nm_); print(a.round(3).to_string(), "\n")
g = T[T.name == "GOLD"]
print("GOLD only:", g.groupby(["side"]).r.agg(["size", "mean"]).round(3).to_string(), "| filtered:",
      filt[filt.name == "GOLD"].groupby("side").r.agg(["size", "mean"]).round(3).to_string())
T.to_csv(ROOT / "research/program/results/stretch_trades.csv.gz", index=False)
