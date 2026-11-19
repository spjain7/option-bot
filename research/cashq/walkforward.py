"""Walk-forward (anchored, yearly re-selection) from the saved trade ledgers: for each family and each test year Y, pick
the variant (strategy × exit) with the best mean net R on trades that ENTERED before Y (n >= 100), then book that variant's
trades of year Y. No variant ever sees its own test year.  python -m research.cashq.walkforward"""
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "results"
FAM = lambda s: ("RSI" if s[:1] == "A" else "DIVERGENCE" if s[:2] == "B_" else "VOLUME" if s[:1] == "C" else
                 "PRICE_ACTION" if s[:1] == "E" else "COMBINED" if s[:1] == "X" else "POSITIONAL" if s[:1] in "FW" else
                 "OPEN_INTEREST" if s.startswith("OI_") else "INTRA")


def run(T, years, label):
    T = T.copy(); T["v"] = T["strategy"] + "|" + T["R"].astype(str); T["y"] = T["entry_time"].dt.year
    T["fam"] = T["strategy"].map(FAM)
    rows = []
    for fam, g in T.groupby("fam"):
        for Y in years:
            past = g[g["y"] < Y].groupby("v")["netR"].agg(["mean", "size"])
            past = past[past["size"] >= 100]
            if past.empty:
                continue
            best = past["mean"].idxmax()
            cur = g[(g["y"] == Y) & (g["v"] == best)]
            rows.append(dict(source=label, family=fam, year=Y, picked=best, past_R=round(past.loc[best, "mean"], 3), n=len(cur),
                             R=round(cur["netR"].mean(), 3) if len(cur) else np.nan))
    return pd.DataFrame(rows)


def main():
    out = []
    for f, label, years in (("daily_trades.csv.gz", "daily", range(2012, 2027)), ("oi_trades.csv.gz", "oi", range(2015, 2027)),
                            ("weekly_trades.csv.gz", "weekly", range(2012, 2027))):
        p = OUT / f
        if p.exists():
            T = pd.read_csv(p, parse_dates=["entry_time"])
            out.append(run(T, years, label))
    W = pd.concat(out, ignore_index=True)
    W.to_csv(OUT / "walkforward.csv", index=False)
    s = W.groupby(["source", "family"]).agg(years=("year", "size"), pos_years=("R", lambda x: int((x > 0).sum())), mean_R=("R", "mean"),
                                            trades=("n", "sum")).reset_index()
    s.to_csv(OUT / "walkforward_summary.csv", index=False)
    print(s.to_string(index=False))


if __name__ == "__main__":
    main()
