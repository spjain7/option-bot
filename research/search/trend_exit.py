"""TREND-EXIT-001 – see REGISTRY_TREXIT.md."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research import instruments as INS  # noqa
from crude import indicators as I  # noqa
from research.search import strategy_search as SS, combo_search as C  # noqa
from research.search.exit_test import run  # noqa
from alerts import stats as ST  # noqa

BASE = {"3h": (2.0, 3.0, True, True), "1d": (1.5, 3.0, False, False)}


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
            e20, e50 = I.ema(c, 20).values, I.ema(c, 50).values
            f["e20"] = f["e20_s"] = e20; f["e50"] = f["e50_s"] = e50
            f["ch10"] = lo.rolling(10).min().shift(1).values; f["ch10_s"] = hi.rolling(10).max().shift(1).values
            up = (c > hi.shift(1).rolling(20).max()) & (v > 1.5 * va) & (c > f["e200"])
            dn = (c < lo.shift(1).rolling(20).min()) & (v > 1.5 * va) & (c < f["e200"])
            sig = np.where(up, 1, np.where(dn, -1, 0))
            sk, tk, be, half = BASE[tf]
            for tx in (None, "e20", "e50", "ch10"):
                for t0, g, cp, r in run(f, sig, swd, nx, sk, tk, be, half, cost, tx):
                    rows.append((name, tf, tx or "base", t0, (g - cp) * mult, (g - 2 * cp) * mult))
        print(name, flush=True)
    T = pd.DataFrame(rows, columns=["name", "tf", "x", "time", "rs", "rs2"])
    T["per"] = np.where(pd.to_datetime(T.time) < pd.Timestamp("2024-07-01"), "design", "holdout")
    g = T.groupby(["tf", "x", "per"]).agg(n=("rs", "size"), win=("rs", lambda x: round((x > 0).mean() * 100, 1)),
                                         avg=("rs", "mean"), avg2x=("rs2", "mean"), worst=("rs", "min")).round(0)
    print(g.to_string())


if __name__ == "__main__":
    main()
