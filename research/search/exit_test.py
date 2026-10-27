"""EXIT-001 – see REGISTRY_EXIT.md.  python -m research.search.exit_test"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research import instruments as INS  # noqa
from research.search import strategy_search as SS, combo_search as C  # noqa
from alerts import stats as ST  # noqa

VARS = {"V0": (2.0, 3.0, False, False), "V1": (1.5, 3.0, False, False), "V2": (2.0, 3.0, True, False),
        "V3": (2.0, 3.0, True, True), "V4": (1.5, 3.0, True, True), "V5": (2.0, 2.0, False, False)}


def run(f, sig, swd, nx, sk, tk, be, half, cost, tx=None, tg=None):
    o, h, l, c, a = f["o"], f["h"], f["l"], f["c"], f["atr"]
    out, pos = [], None
    for i in range(210, len(c) - 1):
        if pos is not None:
            s, e0, st, risk, k0, best, booked, bank = pos
            px = None
            # conservative candle order: the CURRENT stop is checked first (a candle touching both the stop and T1 = stop)
            if (o[i] <= st) if s > 0 else (o[i] >= st): px = o[i]
            elif (l[i] <= st) if s > 0 else (h[i] >= st): px = st
            if px is None and not booked and (half or be) and ((h[i] >= e0 + risk) if s > 0 else (l[i] <= e0 - risk)):
                if half: bank += 0.5 * risk
                booked = True
                st = e0 if s * (e0 - st) > 0 else st
                if (l[i] <= st) if s > 0 else (h[i] >= st): px = st     # back to entry inside the same candle
            if px is None and tg and ((h[i] >= e0 + tg * risk) if s > 0 else (l[i] <= e0 - tg * risk)):
                px = e0 + s * tg * risk                                   # single target: full exit
            if px is not None: pass
            elif nx[i] or i - k0 >= 40: px = c[i] if nx[i] else o[i + 1]
            elif tx and ((c[i] < f[tx][i]) if s > 0 else (c[i] > f[tx + "_s"][i])): px = c[i]
            if px is not None:
                rest = 0.5 if (half and booked) else 1.0
                out.append((f["t"][k0], bank + rest * s * (px - e0), cost[k0] * (1.25 if half and booked else 1.0), risk))
                pos = None
            else:
                best = max(best, c[i]) if s > 0 else min(best, c[i])
                ns = best - s * tk * a[i] if tk else st
                if s * (ns - st) > 0: st = ns
                pos = (s, e0, st, risk, k0, best, booked, bank)
            continue
        s = int(sig[i])
        if s == 0 or swd[i] or nx[i] or not a[i] > 0: continue
        e0 = o[i + 1]
        pos = (s, e0, e0 - s * sk * a[i], sk * a[i], i + 1, e0, False, 0.0)
    return out


def main():
    rows = []
    for exch, name in SS.NAMES:
        h = SS.load(exch, name, "ONE_HOUR"); sw = SS.switch_days(name, exch, h)
        mult = INS.REGISTRY[name]["mult"]
        for tf, df in (("3h", ST.three_hour_generic(h)), ("1d", SS.daily_from(h))):
            df = df.reset_index(drop=True); f = C.features(df, h)
            c, hi, lo, v = df["close"], df["high"], df["low"], df["volume"].astype(float)
            va = v.rolling(20).mean().shift(1)
            day = f["day"]; swd = np.array([pd.Timestamp(x) in sw for x in day]); nx = np.r_[swd[1:], False] & (day != np.r_[day[1:], day[-1]])
            cost = np.array([INS.cost_points(name, p, 1.0) for p in f["c"]])
            up = (c > hi.shift(1).rolling(20).max()) & (v > 1.5 * va) & (c > f["e200"])
            dn = (c < lo.shift(1).rolling(20).min()) & (v > 1.5 * va) & (c < f["e200"])
            sig = np.where(up, 1, np.where(dn, -1, 0))
            for vn, (sk, tk, be, half) in VARS.items():
                for t0, g, cp, r in run(f, sig, swd, nx, sk, tk, be, half, cost):
                    rows.append((name, tf, vn, t0, (g - cp) * mult, (g - 2 * cp) * mult, r * mult))
        print(name, flush=True)
    T = pd.DataFrame(rows, columns=["name", "tf", "v", "time", "rs", "rs2", "risk_rs"])
    T["per"] = np.where(pd.to_datetime(T.time) < pd.Timestamp("2024-07-01"), "design", "holdout")
    g = T.groupby(["tf", "v", "per"]).agg(n=("rs", "size"), win=("rs", lambda x: round((x > 0).mean() * 100, 1)),
                                         avg=("rs", "mean"), avg2x=("rs2", "mean"), worst=("rs", "min"),
                                         stop_rs=("risk_rs", "median")).round(0)
    out = ROOT / "research/search/results_exit"; out.mkdir(parents=True, exist_ok=True)
    g.to_csv(out / "summary.csv")
    print(g.to_string())
    print("\nper instrument, hold-out avg ₹/lot (3h):")
    print(T[(T.per == "holdout") & (T.tf == "3h")].pivot_table(index="name", columns="v", values="rs", aggfunc="mean").round(0).to_string())


if __name__ == "__main__":
    main()
