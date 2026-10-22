"""STRAT-SEARCH-005 – robustness / improvement grid around the volume breakout (3h + daily).
Grid: channel N {10,20,40} × volume multiple {1.2,1.5,2.0} × confirm {none, obv(OBV at N-high), ema200 side, daily trend}
× stop {1.5,2,3} ATR × trail {2,3,4} ATR. Choose the CENTRE of the most stable region (neighbours positive), not the single best.
"""
import itertools, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research import instruments as INS  # noqa
from crude import indicators as I  # noqa
from research.search import strategy_search as SS, combo_search as C  # noqa
from alerts import stats as ST  # noqa


def run(f, sig, swd, nx, stop_k, trail_k, cost):
    o, h, l, c, a = f["o"], f["h"], f["l"], f["c"], f["atr"]
    out, pos = [], None
    for i in range(210, len(c) - 1):
        if pos is not None:
            s, e0, st, risk, k0, best = pos
            px = None
            if (o[i] <= st) if s > 0 else (o[i] >= st): px = o[i]
            elif (l[i] <= st) if s > 0 else (h[i] >= st): px = st
            elif nx[i] or i - k0 >= 40: px = c[i] if nx[i] else o[i + 1]
            if px is not None:
                out.append((f["t"][k0], s * (px - e0), cost[k0], risk)); pos = None
            else:
                best = max(best, c[i]) if s > 0 else min(best, c[i])
                ns = best - s * trail_k * a[i]
                if s * (ns - st) > 0: st = ns
                pos = (s, e0, st, risk, k0, best)
            continue
        s = int(sig[i])
        if s == 0 or swd[i] or nx[i] or not a[i] > 0: continue
        e0 = o[i + 1]
        pos = (s, e0, e0 - s * stop_k * a[i], stop_k * a[i], i + 1, e0)
    return out


def main():
    rows = []
    for exch, name in SS.NAMES:
        h = SS.load(exch, name, "ONE_HOUR"); sw = SS.switch_days(name, exch, h)
        for tf, df in (("3h", ST.three_hour_generic(h)), ("1d", SS.daily_from(h))):
            df = df.reset_index(drop=True); f = C.features(df, h)
            c, hi, lo, v = df["close"], df["high"], df["low"], df["volume"].astype(float)
            va = v.rolling(20).mean().shift(1)
            obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
            day = f["day"]; swd = np.array([pd.Timestamp(x) in sw for x in day]); nx = np.r_[swd[1:], False] & (day != np.r_[day[1:], day[-1]])
            cost = np.array([INS.cost_points(name, p, 1.0) for p in f["c"]])
            for N, vm, cf in itertools.product((10, 20, 40), (1.2, 1.5, 2.0), ("none", "obv", "ema200", "daily")):
                up = (c > hi.shift(1).rolling(N).max()) & (v > vm * va); dn = (c < lo.shift(1).rolling(N).min()) & (v > vm * va)
                if cf == "obv":
                    up &= obv >= obv.rolling(N).max(); dn &= obv <= obv.rolling(N).min()
                elif cf == "ema200":
                    up &= c > f["e200"]; dn &= c < f["e200"]
                elif cf == "daily":
                    up &= f["dtr"] == 1; dn &= f["dtr"] == -1
                sig = np.where(up, 1, np.where(dn, -1, 0))
                for sk, tk in itertools.product((1.5, 2.0, 3.0), (2.0, 3.0, 4.0)):
                    for t0, g, cp, r in run(f, sig, swd, nx, sk, tk, cost):
                        rows.append((name, tf, N, vm, cf, sk, tk, t0, g, cp, r))
        print(name, "done", flush=True)
    T = pd.DataFrame(rows, columns=["name", "tf", "N", "vm", "cf", "sk", "tk", "time", "g", "cp", "risk"])
    T["time"] = pd.to_datetime(T["time"]); T["r1"] = (T.g - T.cp) / T.risk; T["r2"] = (T.g - 2 * T.cp) / T.risk
    T["half"] = np.where(T.time < pd.Timestamp("2024-07-01"), "A", "B")
    k = ["tf", "N", "vm", "cf", "sk", "tk"]
    g = T.groupby(k + ["half"]).agg(n=("r1", "size"), e1=("r1", "mean"), e2=("r2", "mean"), win=("r1", lambda x: (x > 0).mean())).unstack()
    g.columns = [f"{a}_{b}" for a, b in g.columns]; g = g.dropna()
    g = g[(g.n_A >= 30) & (g.n_B >= 30)]
    g["worst_e2"] = g[["e2_A", "e2_B"]].min(axis=1)
    out = ROOT / "research/search/results_005"; out.mkdir(parents=True, exist_ok=True); g.round(3).to_csv(out / "grid.csv")
    print(f"combos {len(g)}, positive at 2x in both halves: {(g.worst_e2 > 0).sum()} ({(g.worst_e2 > 0).mean():.0%})")
    for tf in ("3h", "1d"):
        x = g.xs(tf)
        print(f"\n{tf}: share positive (2x, both halves) by setting")
        for col in ("N", "vm", "cf", "sk", "tk"):
            print(" ", col, x.groupby(level=col)["worst_e2"].agg(lambda s: f"{(s > 0).mean():.0%} pos, median {s.median():.3f}").to_dict())
        print(x.sort_values("worst_e2", ascending=False).head(8)[["n_A", "n_B", "win_A", "win_B", "e2_A", "e2_B"]].round(3).to_string())


if __name__ == "__main__":
    main()
