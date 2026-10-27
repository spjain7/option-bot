"""ONE-TARGET-001: one stop + one target (full exit), no trailing, vs the current live exits. Measured in ₹/lot."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research import instruments as INS  # noqa
from crude import indicators as I  # noqa
from research.search import strategy_search as SS, combo_search as C  # noqa
from research.search.exit_test import run  # noqa
from alerts import stats as ST  # noqa

V = {"3h": {"live": (2.0, 3.0, True, True, None, None), "T1.0": (2.0, 0, False, False, None, 1.0), "T1.5": (2.0, 0, False, False, None, 1.5),
            "T2.0": (2.0, 0, False, False, None, 2.0), "T3.0": (2.0, 0, False, False, None, 3.0)},
     "1d": {"live": (1.5, 3.0, False, False, "e20", None), "T1.0": (1.5, 0, False, False, "e20", 1.0), "T1.5": (1.5, 0, False, False, "e20", 1.5),
            "T2.0": (1.5, 0, False, False, "e20", 2.0), "T3.0": (1.5, 0, False, False, "e20", 3.0)}}


def main():
    rows = []
    for exch, name in SS.NAMES:
        h = SS.load(exch, name, "ONE_HOUR"); sw = SS.switch_days(name, exch, h); mult = INS.REGISTRY[name]["mult"]
        for tf, df in (("3h", ST.three_hour_generic(h)), ("1d", SS.daily_from(h))):
            df = df.reset_index(drop=True); f = C.features(df, h)
            c, hi, lo, v = df["close"], df["high"], df["low"], df["volume"].astype(float)
            va = v.rolling(20).mean().shift(1)
            day = f["day"]; swd = np.array([pd.Timestamp(x) in sw for x in day]); nx = np.r_[swd[1:], False] & (day != np.r_[day[1:], day[-1]])
            cost = np.array([INS.cost_points(name, p, 1.0) for p in f["c"]])
            f["e20"] = f["e20_s"] = I.ema(c, 20).values
            sig = np.where((c > hi.shift(1).rolling(20).max()) & (v > 1.5 * va) & (c > f["e200"]), 1,
                           np.where((c < lo.shift(1).rolling(20).min()) & (v > 1.5 * va) & (c < f["e200"]), -1, 0))
            for vn, (sk, tk, be, half, tx, tg) in V[tf].items():
                for t0, g, cp, r in run(f, sig, swd, nx, sk, tk, be, half, cost, tx, tg):
                    rows.append((name, tf, vn, t0, (g - cp) * mult, (g - 2 * cp) * mult))
        print(name, flush=True)
    T = pd.DataFrame(rows, columns=["name", "tf", "v", "time", "rs", "rs2"])
    T["per"] = np.where(pd.to_datetime(T.time) < pd.Timestamp("2024-07-01"), "design", "holdout")
    g = T.groupby(["tf", "v", "per"]).agg(n=("rs", "size"), win=("rs", lambda x: round((x > 0).mean() * 100, 1)),
                                         avg=("rs", "mean"), avg2x=("rs2", "mean")).round(0)
    pos = T[T.per == "holdout"].groupby(["tf", "v", "name"]).rs.mean().gt(0).groupby(level=[0, 1]).sum()
    print(g.to_string()); print("\ninstruments positive (hold-out):\n", pos.to_string())


if __name__ == "__main__":
    main()
