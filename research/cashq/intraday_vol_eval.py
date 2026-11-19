"""Scores research/cashq/intraday_vol.py trades: every rule variant x RVOL threshold x top-N x sides, net of costs, by half.
python -m research.cashq.intraday_vol_eval -> results/intraday_vol.csv"""
import itertools
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq.intraday_vol import OUT, SPLIT, COSTS  # noqa: E402


def stats(S, cost, base_avg=None):
    n = S.gross - cost
    h1, h2 = n[S.date < SPLIT], n[S.date >= SPLIT]
    r = n * S.entry / S.stopd
    daily = n.groupby(S.date).mean()
    return dict(trades=len(S), per_day=round(len(S) / max(S.date.nunique(), 1), 1), win=round(100 * (n > 0).mean(), 1),
                avg_pct=round(100 * n.mean(), 3), avg_R=round(r.mean(), 3), H1_avg=round(100 * h1.mean(), 3), H2_avg=round(100 * h2.mean(), 3),
                H1_win=round(100 * (h1 > 0).mean(), 1), H2_win=round(100 * (h2 > 0).mean(), 1), H1_n=len(h1), H2_n=len(h2),
                day_sharpe=round(float(daily.mean() / daily.std() * np.sqrt(250)), 2) if daily.std() > 0 else None,
                avg_vs_base=round(100 * (n.mean() - base_avg), 3) if base_avg is not None else None)


def main():
    R = pd.read_parquet(OUT / "intraday_vol_trades.parquet")
    out = []
    for cost in COSTS:
        O = R[R.setup.str.startswith("ORB")]
        for (k, s, tg), G in O.groupby(["setup", "stop_atr", "tg"]):
            base = (G.gross - cost).mean()
            for th, top, sides in itertools.product((0.0, 1.0, 2.0, 3.0), (5, 10, 20, 999), ("both", "long")):
                S = G[G.rvol >= th]
                if sides == "long":
                    S = S[S.side > 0]
                S = S.sort_values("rvol", ascending=False).groupby("date").head(top)
                if len(S) < 200:
                    continue
                out.append(dict(cost=cost, setup=k, stop=s, target="EOD" if tg == 0 else f"{tg:g}R", min_rvol=th, top_n=top, sides=sides,
                                **stats(S, cost, base)))
        V = R[R.setup == "VSPIKE"]
        for (s, tg), G in V.groupby(["stop_atr", "tg"]):
            base = (G.gross - cost).mean()
            for th, sides, tw in itertools.product((4, 6, 10), ("both", "long"), ("all", "<=11:00", ">11:00")):
                S = G[G.rvol >= th]
                if sides == "long":
                    S = S[S.side > 0]
                if tw != "all":
                    S = S[(S.spike_min <= 660) if tw == "<=11:00" else (S.spike_min > 660)]
                if len(S) < 200:
                    continue
                out.append(dict(cost=cost, setup=f"VSPIKE {tw}", stop=s, target="EOD" if tg == 0 else f"{tg:g}R", min_rvol=th, top_n=999, sides=sides,
                                **stats(S, cost, base)))
    L = pd.DataFrame(out); L.to_csv(OUT / "intraday_vol.csv", index=False)
    L["pass"] = (L.H1_avg > 0) & (L.H2_avg > 0) & (L.avg_vs_base > 0)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200)
    cols = ["setup", "stop", "target", "min_rvol", "top_n", "sides", "trades", "per_day", "win", "avg_pct", "avg_R", "H1_avg", "H2_avg", "H1_win", "H2_win", "day_sharpe", "avg_vs_base"]
    for cost in COSTS:
        X = L[L.cost == cost]
        print(f"\n=== cost {cost:.2%}: {int(X['pass'].sum())} of {len(X)} pass (positive both halves and above no-RVOL baseline)")
        X = X.assign(mn=X[["H1_avg", "H2_avg"]].min(axis=1)).sort_values("mn", ascending=False)
        print(X.head(25)[cols].to_string(index=False))
        print("-- highest win rate with positive both halves:")
        print(X[(X.H1_avg > 0) & (X.H2_avg > 0)].sort_values("win", ascending=False).head(10)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
