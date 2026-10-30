"""PARAM-SWEEP-001 (30-Oct-2026, owner: "do this type of analysis yourself and find a way"): one-at-a-time sensitivity of the
LIVE futures breakout rule, per market (MCX 6 commodities / NIFTY + BANKNIFTY), timeframe (3h / daily) and side.
Live baseline: lookback 20 (MCX BUY: 10 on 3h, 5 daily), volume > 1.5×, EMA200 side, 3h stop 2 ATR 2R · daily 1.5 ATR 3R,
max 40 candles, stop cap 3h 2.5 % / daily 4 %. Each variant changes ONE setting:
  lookback 5/10/15/20/30 · volume 1.0/1.2/1.5/2.0/2.5 · trend EMA none/50/100/200 · stop ATR 1.0/1.5/2.0/2.5/3.0 ·
  target R 1/1.5/2/3/4 · max hold 10/20/40/60 candles
A variant is "better" only if exp2 (2× costs) beats the baseline in ALL three periods (train < 2024-07 ≤ valid < 2025-07 ≤ test),
is positive in all three, and keeps ≥ 60 % of the baseline's trades per period. python research/program/param_sweep.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H  # noqa: E402
from research.search import strategy_search as SS  # noqa: E402
from crude import indicators as I  # noqa: E402

T1, T2 = pd.Timestamp("2024-07-01"), pd.Timestamp("2025-07-01")
BASE = {"3h": dict(N=20, vol=1.5, ema=200, k=2.0, r=2.0, maxh=40, cap=2.5), "1d": dict(N=20, vol=1.5, ema=200, k=1.5, r=3.0, maxh=40, cap=4.0)}
MCX_BUY_N = {"3h": 10, "1d": 5}
GRID = dict(N=[5, 10, 15, 20, 30], vol=[1.0, 1.2, 1.5, 2.0, 2.5], ema=[0, 50, 100, 200], k=[1.0, 1.5, 2.0, 2.5, 3.0],
            r=[1.0, 1.5, 2.0, 3.0, 4.0], maxh=[10, 20, 40, 60])
DATA = {}


def frames():
    for ex, name in SS.NAMES:
        mkt = "MCX" if ex == "MCX" else "INDEX"
        for tf, df in H.angel(name, ex).items():
            f = H.features(df.reset_index(drop=True)); f["switch"] = df["switch"].values
            for n in (50, 100):
                f[f"ema{n}"] = I.ema(f["close"], n)
            DATA[(mkt, name, tf)] = (f, H.cost_series(name, f, "angel"))


def run(mkt, tf, side, p):
    out = []
    for (m, name, t), (f, cost) in DATA.items():
        if m != mkt or t != tf:
            continue
        hh = f["high"].shift(1).rolling(p["N"]).max(); ll = f["low"].shift(1).rolling(p["N"]).min()
        e = f[f"ema{p['ema']}"] if p["ema"] in (50, 100) else f["ema200"]
        tr_up = (f["close"] > e) if p["ema"] else True
        tr_dn = (f["close"] < e) if p["ema"] else True
        sig = np.where((f["close"] > hh) & (f["volx"] > p["vol"]) & tr_up, 1,
                       np.where((f["close"] < ll) & (f["volx"] > p["vol"]) & tr_dn, -1, 0))
        for x in H.simulate(f, sig, side, p["k"], p["r"], p["maxh"], p["cap"], cost):
            if x["status"] == "trade":
                out.append((x["time"], x["r2"]))
    if not out:
        return None
    T = pd.DataFrame(out, columns=["time", "r2"])
    sp = np.where(T.time < T1, "train", np.where(T.time < T2, "valid", "test"))
    return {s: (T.r2[sp == s].mean(), int((sp == s).sum())) for s in ("train", "valid", "test")} | {"all": (T.r2.mean(), len(T))}


def main():
    frames()
    rows = []
    for mkt in ("MCX", "INDEX"):
        for tf in ("3h", "1d"):
            for side in (1, -1):
                base = dict(BASE[tf])
                if mkt == "MCX" and side > 0:
                    base["N"] = MCX_BUY_N[tf]
                b = run(mkt, tf, side, base)
                if b is None:
                    continue
                rows.append(dict(mkt=mkt, tf=tf, side="BUY" if side > 0 else "SELL", change="LIVE", **{f"{s}": round(b[s][0], 3) for s in b},
                                 **{f"n_{s}": b[s][1] for s in b}, better=""))
                for key, vals in GRID.items():
                    for v in vals:
                        if v == base[key]:
                            continue
                        p = dict(base, **{key: v})
                        x = run(mkt, tf, side, p)
                        if x is None:
                            continue
                        good = all(x[s][0] > b[s][0] and x[s][0] > 0 and x[s][1] >= 0.6 * b[s][1] for s in ("train", "valid", "test"))
                        rows.append(dict(mkt=mkt, tf=tf, side="BUY" if side > 0 else "SELL", change=f"{key}={v}",
                                         **{f"{s}": round(x[s][0], 3) for s in x}, **{f"n_{s}": x[s][1] for s in x}, better="YES" if good else ""))
                print(f"done {mkt} {tf} {'BUY' if side > 0 else 'SELL'}", flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(ROOT / "research/program/results/param_sweep.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 400)
    cols = ["mkt", "tf", "side", "change", "train", "valid", "test", "all", "n_all", "better"]
    print(R[R.change == "LIVE"][cols].to_string(index=False))
    print("\nBETTER THAN LIVE IN ALL 3 PERIODS (and positive in all 3):")
    print(R[R.better == "YES"][cols].to_string(index=False) if (R.better == "YES").any() else "none")


if __name__ == "__main__":
    main()
