"""STOCK-PAT-001 – see REGISTRY_STKPAT.md."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research.search import stock_search as SR, stock_check as SC, combo_search as C  # noqa
from research.search.exit_test import run  # noqa
from research.search.inst_patterns import signals  # noqa
from alerts import stats as ST  # noqa
from alerts.stocks import in_rollover_window  # noqa


def main():
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    rows = []
    for r in man.itertuples():
        f1 = SR.DATA / f"{r.name}_ONE_HOUR.csv"
        if not f1.exists():
            continue
        h = pd.read_csv(f1, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
        df = ST.three_hour_generic(h).reset_index(drop=True)
        if len(df) < 300:
            continue
        f = C.features(df, h)
        day = f["day"]
        swd = np.array([in_rollover_window(pd.Timestamp(x)) for x in day]); nx = np.r_[swd[1:], False] & (day != np.r_[day[1:], day[-1]])
        cost = np.array([SC.cost_frac(p, r.lot) for p in f["c"]])
        c, hi, lo, v = df["close"], df["high"], df["low"], df["volume"].astype(float)
        va = v.rolling(20).mean().shift(1)
        S = signals(df, f)
        bo = np.where((c > hi.shift(1).rolling(20).max()) & (v > 1.5 * va) & (c > f["e200"]), 1,
                      np.where((c < lo.shift(1).rolling(20).min()) & (v > 1.5 * va) & (c < f["e200"]), -1, 0))
        rules = {"flag": S["flag"], "hs": S["hs"], "breakout": bo, "double": S["double"], "squeeze": S["squeeze"]}
        for rn, sg in rules.items():
            for t0, g, cp, rk in run(f, sg, swd, nx, 2.0, 3.0, True, True, cost, None):
                rows.append((r.name, rn, t0, (g - cp) * r.lot, (g - 2 * cp) * r.lot))
        print(r.name, flush=True)
    T = pd.DataFrame(rows, columns=["name", "rule", "time", "rs", "rs2"])
    T["per"] = np.where(pd.to_datetime(T.time) < pd.Timestamp("2024-07-01"), "design", "holdout")
    out = []
    for rn, g in T.groupby("rule"):
        D, H = g[g.per == "design"], g[g.per == "holdout"]
        ps = H.groupby("name").rs.mean()
        share = (ps > 0).mean() * 100
        ok = len(D) >= 100 and len(H) >= 100 and D.rs2.mean() > 0 and H.rs2.mean() > 0 and share >= 55
        out.append(dict(rule=rn, n_d=len(D), win_d=round((D.rs > 0).mean() * 100, 1), rs_d=round(D.rs.mean()), rs2_d=round(D.rs2.mean()),
                        n_h=len(H), win_h=round((H.rs > 0).mean() * 100, 1), rs_h=round(H.rs.mean()), rs2_h=round(H.rs2.mean()),
                        stocks_pos_h=f"{share:.0f}%", PASS=ok))
    R = pd.DataFrame(out)
    d = ROOT / "research/search/results_stkpat"; d.mkdir(parents=True, exist_ok=True); R.to_csv(d / "summary.csv", index=False)
    print(R.to_string(index=False))


if __name__ == "__main__":
    main()
