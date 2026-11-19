"""Do the daily "stock lists" (new 52-week highs, volume spikes, breakouts, golden / death cross, near 52-week lows) point to
trades? (owner 18-Nov-2026). Event study on official NSE bhavcopies 2005-26, point-in-time liquid universe, delisted
included. Event at the day's close, bought at the next open, held 5 / 20 / 60 sessions, minus 0.393 % delivery costs.
EXCESS = the event stock's return minus the average return of all eligible stocks bought the same day and held as long
(so a rising market does not make a list look good).
  HI52        close at a new 252-day closing high
  VOLSPIKE    volume >= 10x the 20-day average (split: day up >= +2 % / day down <= -2 %); also >= 25x
  BREAKOUT    first close above the 50-day high in 5 sessions with volume >= 1.5x
  GOLDEN      50-day average crosses above the 200-day average     DEATH  crosses below
  NEAR52LOW   close within 2 % of the 252-day low
python -m research.cashq.screen_lists -> results/screen_lists.csv"""
import gc
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
COST = 0.00393


def main():
    W = D.daily_panel()
    o, h, l, c, v = (W[x].astype("float64") for x in ("open", "high", "low", "close", "volume")); e = W["elig"].fillna(False).astype(bool)
    del W; gc.collect()
    ret = c / c.shift(1) - 1; vx = v / v.rolling(20).mean().shift(1)
    s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
    hi50 = c > h.shift(1).rolling(50).max()
    EV = {"HI52 (new 52-week high)": c >= c.rolling(252, min_periods=240).max(),
          "VOLSPIKE >=10x, day up >=2%": (vx >= 10) & (ret >= 0.02), "VOLSPIKE >=10x, day down <=-2%": (vx >= 10) & (ret <= -0.02),
          "VOLSPIKE >=25x (any day)": vx >= 25,
          "BREAKOUT (50-day high + volume)": hi50 & ~hi50.shift(1).rolling(5, min_periods=1).max().fillna(0).astype(bool) & (vx >= 1.5),
          "GOLDEN CROSS": (s50 > s200) & (s50.shift(1) <= s200.shift(1)), "DEATH CROSS": (s50 < s200) & (s50.shift(1) >= s200.shift(1)),
          "NEAR 52-WEEK LOW (within 2%)": c <= c.rolling(252, min_periods=240).min() * 1.02}
    nxt = o.shift(-1)
    fwd = {H: (c.shift(-H) / nxt - 1 - COST) for H in (5, 20, 60)}
    base = {H: fwd[H].where(e).mean(axis=1) for H in (5, 20, 60)}
    days = c.index
    rows = []
    for name, m in EV.items():
        M = (m & e).fillna(False)
        for per, lo, hi in (("2005-14", 2005, 2014), ("2015-19", 2015, 2019), ("2020-26", 2020, 2026), ("2024", 2024, 2024), ("2025", 2025, 2025),
                            ("2026", 2026, 2026), ("ALL", 2005, 2026)):
            sel = (days.year >= lo) & (days.year <= hi)
            Mp = M[sel]
            row = dict(list=name, period=per, events=int(Mp.values.sum()))
            for H in (5, 20, 60):
                F = fwd[H][sel].where(Mp); X = F.sub(base[H][sel], axis=0).where(Mp)
                f = F.values[np.isfinite(F.values)]; x = X.values[np.isfinite(X.values)]
                row[f"d{H}_avg_pct"] = round(100 * float(f.mean()), 2) if len(f) else None
                row[f"d{H}_win_pct"] = round(100 * float((f > 0).mean()), 1) if len(f) else None
                row[f"d{H}_excess_pct"] = round(100 * float(x.mean()), 2) if len(x) else None
                row[f"d{H}_beat_avg_stock_pct"] = round(100 * float((x > 0).mean()), 1) if len(x) else None
            row["per_day_2025_26"] = None
            rows.append(row)
        print(name, int(M.values.sum()), flush=True)
    L = pd.DataFrame(rows)
    for name in EV:
        L.loc[(L.list == name) & (L.period == "ALL"), "per_day_2025_26"] = round(float((EV[name] & e).fillna(False)[days >= "2025-01-01"].values.sum())
                                                                                 / max((days >= "2025-01-01").sum(), 1), 1)
    OUT.mkdir(exist_ok=True); L.to_csv(OUT / "screen_lists.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 100)
    print(L[L.period.isin(["ALL", "2005-14", "2015-19", "2020-26", "2025", "2026"])][["list", "period", "events", "d5_excess_pct", "d20_avg_pct", "d20_win_pct", "d20_excess_pct",
                                                                                     "d20_beat_avg_stock_pct", "d60_avg_pct", "d60_excess_pct", "per_day_2025_26"]].to_string(index=False))


if __name__ == "__main__":
    main()
