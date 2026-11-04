"""GAP-001 (4-Nov-2026) – opening-gap statistics and a gap-fade trade, every script (MCX 7, NIFTY/BANKNIFTY, 181 stock futures).

Gap = day's first open vs previous day's last close (1-hour candles, roll-adjusted; roll / split days skipped).
  fill rate : % of days the price touches the previous close the same day, by gap size bucket and direction.
Trade (fade the gap at the open): entry = open, target = previous close, SL = open +/- 1 x gap (1:1),
  exit at the day's close if neither is hit. An hourly candle touching both counts as SL (conservative).
  costs: 0.04 % (MCX / index) or 0.06 % (stocks) of price, taken off the result in R.
Periods 2022-24 and 2025-26 reported separately.

  python -m research.search.gapfill    -> research/search/results_gap/*
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.search import hit80_search as H  # noqa: E402

OUT = ROOT / "research/search/results_gap"
BUCKETS = [0.1, 0.3, 0.5, 1.0, 2.0, 99]
COST = {"MCX": 0.04, "IDX": 0.04, "STK": 0.06}


def days(seg, name, h):
    h = h.copy(); h["d"] = h["time"].dt.normalize()
    rows = []
    g = list(h.groupby("d"))
    for (d0, a), (d1, b) in zip(g[:-1], g[1:]):
        if b["switch"].any() or (d1 - d0).days > 5:
            continue
        pc, op = a["close"].iat[-1], b["open"].iat[0]
        gap = (op / pc - 1) * 100
        if abs(gap) < 0.1:
            continue
        s = -1 if gap > 0 else 1                       # fade direction
        filled = (b["low"].min() <= pc) if gap > 0 else (b["high"].max() >= pc)
        R = abs(op - pc); sl = op - s * R; res = None
        for hi, lo, cl in zip(b["high"].values, b["low"].values, b["close"].values):
            hit_sl = (hi >= sl) if s < 0 else (lo <= sl)
            hit_tg = (lo <= pc) if s < 0 else (hi >= pc)
            if hit_sl:
                res = -1.0; break
            if hit_tg:
                res = 1.0; break
        if res is None:
            res = s * (b["close"].iat[-1] - op) / R
        res -= COST[seg] / 100 * op / R
        rows.append(dict(seg=seg, name=name, date=d1, gap=gap, dir="UP" if gap > 0 else "DOWN", filled=bool(filled), R=res))
    return rows


def pf(x):
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return round(g / l, 2) if l else np.nan


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for seg, tf, name, df in H.datasets():
        if tf != "1h":
            continue
        rows += days(seg, name, df.reset_index(drop=True))
    t = pd.DataFrame(rows)
    t["size"] = pd.cut(t.gap.abs(), BUCKETS, labels=["0.1-0.3%", "0.3-0.5%", "0.5-1%", "1-2%", ">2%"])
    t["period"] = np.where(t.date < "2025-01-01", "2022-24", "2025-26")
    t.to_csv(OUT / "gaps.csv.gz", index=False)
    agg = lambda g: pd.Series(dict(days=len(g), fill=round(g.filled.mean(), 3), trade_win=round((g.R > 0).mean(), 3),
                                   avgR=round(g.R.mean(), 3), pf=pf(g.R)))
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 500)
    A = t.groupby(["seg", "size", "period"], observed=True).apply(agg)
    B = t[t.seg != "STK"].groupby(["name", "size", "period"], observed=True).apply(agg)
    S = t[t.seg == "STK"].groupby(["name", "period"]).apply(agg)
    A.to_csv(OUT / "by_segment.csv"); B.to_csv(OUT / "by_script_mcx_index.csv"); S.to_csv(OUT / "by_stock.csv")
    print(A.to_string()); print(B.to_string())
    # stocks that pass in BOTH periods (fill and trade), small-gap buckets pooled
    w = S.reset_index().pivot(index="name", columns="period", values=["fill", "trade_win", "pf", "days"])
    ok = w[(w[("pf", "2022-24")] > 1.2) & (w[("pf", "2025-26")] > 1.2) & (w[("days", "2025-26")] >= 30)]
    print("\nstocks with gap-fade PF > 1.2 in both periods:", len(ok), "of", len(w))
    print(ok.round(2).to_string())


if __name__ == "__main__":
    main()
