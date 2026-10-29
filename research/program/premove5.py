"""PREMOVE-002 (30-Oct-2026, owner): EVERY ≥ 1.5 % intraday move (no 'quiet first' rule), 5-min futures with OI, 218 stocks,
27-Jul → 29-Oct-2026. Move start = bar i whose close is followed, within 60 min (same day), by a ≥ 1.5 % run in one direction
before a 0.5 % move the other way, and the bar before was not already such a start (first bar of the run).
Hints measured in the 30 / 60 min BEFORE the start (bars i-6..i, i-12..i): volume vs the same time on the previous 10 days,
futures OI change (expiry roll days excluded), range squeeze, VWAP position, near day high / low, small drift, time of day.
Compared with all other moments 09:45-14:30. Then: when a hint shows, how often a move follows and which way.
python research/program/premove5.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/program/results"


def prep(p):
    d = pd.read_csv(p, parse_dates=["time"]).sort_values("time").drop_duplicates("time")
    d = d[(d["time"].dt.strftime("%H:%M") >= "09:15") & (d["time"].dt.strftime("%H:%M") < "15:30")].reset_index(drop=True)
    if len(d) < 1500:
        return None
    d["day"] = d["time"].dt.normalize(); d["slot"] = d["time"].dt.strftime("%H:%M")
    tp = (d.high + d.low + d.close) / 3
    d["vwap"] = (tp * d.volume).groupby(d.day).cumsum() / d.volume.groupby(d.day).cumsum().replace(0, np.nan)
    dr = d.groupby("day").agg(h=("high", "max"), l=("low", "min"), c=("close", "last"))
    d["adr"] = d.day.map((dr.h - dr.l).rolling(10, min_periods=5).mean().shift(1))
    d["dhi"] = d.groupby("day").high.cummax(); d["dlo"] = d.groupby("day").low.cummin()
    sa = d.groupby("slot").volume.transform(lambda v: v.shift(1).rolling(10, min_periods=5).mean())
    d["vol30"] = d.volume.rolling(6).sum() / sa.rolling(6).sum()
    d["vol60"] = d.volume.rolling(12).sum() / sa.rolling(12).sum()
    d["vol5"] = d.volume / sa
    first = d.day != d.day.shift()
    oij = (d.oi / d.oi.shift() - 1).abs()
    bad = (first & (oij > 0.15)).groupby(d.day).transform("max")          # contract switch day in the stitched series
    d["oi30"] = (d.oi / d.oi.shift(6) - 1).where(~bad)
    d["oi60"] = (d.oi / d.oi.shift(12) - 1).where(~bad)
    d["squeeze"] = (d.high.rolling(12).max() - d.low.rolling(12).min()) / d.adr
    d["vwap_pos"] = (d.close - d.vwap) / d.adr
    d["near_hi"] = ((d.dhi - d.close) / d.adr <= 0.2).astype(int)
    d["near_lo"] = ((d.close - d.dlo) / d.adr <= 0.2).astype(int)
    d["drift30"] = (d.close - d.close.shift(6)) / d.adr
    d["day_move"] = (d.close / d.day.map(dr.c.shift(1)) - 1)                # vs previous close
    c, h, l, same = d.close.values, d.high.values, d.low.values, d.day.values
    lab = np.zeros(len(d), int)
    for i in range(len(d) - 1):
        uh = c[i] * 1.015; dl_ = c[i] * 0.985; ux = c[i] * 1.005; dx = c[i] * 0.995
        up = dn = False; bu = bd = False
        for j in range(i + 1, min(i + 13, len(d))):
            if same[j] != same[i]:
                break
            if not up and not bu:
                if l[j] <= dx: bu = True
                elif h[j] >= uh: up = True
            if not dn and not bd:
                if h[j] >= ux: bd = True
                elif l[j] <= dl_: dn = True
            if (up or bu) and (dn or bd):
                break
        lab[i] = 1 if up and not dn else (-1 if dn and not up else 0)
    prev = np.r_[0, lab[:-1]]
    d["start"] = np.where((lab != 0) & (lab != prev), lab, 0)          # first bar of a run
    d["inrun"] = (lab != 0) & (lab == prev)                            # later bars of the same run (excluded)
    keep = (d.slot >= "09:45") & (d.slot <= "14:30") & d.adr.notna() & ~d.inrun
    return d[keep]


def main():
    src = sorted((ROOT / "research/data/m5").glob("fut_*.csv"))
    parts = []
    for p in src:
        try:
            x = prep(p)
        except Exception as e:
            print("skip", p.name, e); continue
        if x is not None:
            x["name"] = p.stem[4:]; parts.append(x)
    X = pd.concat(parts, ignore_index=True)
    ev = X.start
    bu, bd = (ev == 1).mean(), (ev == -1).mean()
    print(f"{X.name.nunique()} stocks · {X.day.nunique()} sessions · {len(X):,} moments 09:45-14:30 · "
          f"move starts: UP {int((ev == 1).sum()):,} ({bu * 100:.2f} %), DOWN {int((ev == -1).sum()):,} ({bd * 100:.2f} %)")
    F = ["vol5", "vol30", "vol60", "oi30", "oi60", "squeeze", "vwap_pos", "near_hi", "near_lo", "drift30", "day_move"]
    print("\nMEDIAN in the 30-60 min BEFORE:   UP-move starts | DOWN-move starts | all other moments")
    for f in F:
        print(f"  {f:9s} {X.loc[ev == 1, f].median():10.4f} | {X.loc[ev == -1, f].median():10.4f} | {X.loc[ev == 0, f].median():10.4f}")
    print("\nshare of starts by time of day (UP / DOWN / normal moments):")
    tb = pd.cut(X.slot.str[:2].astype(int) * 60 + X.slot.str[3:].astype(int), [0, 600, 660, 720, 780, 870, 999],
                labels=["9:45-10:00", "10-11", "11-12", "12-13", "13-14:30", "x"])
    t = pd.crosstab(tb, ev, normalize="columns").round(3) * 100
    print(t.to_string())
    combos = {
        "volume ≥ 2× (last 30 min)": X.vol30 >= 2, "volume ≥ 3×": X.vol30 >= 3, "this 5-min bar volume ≥ 3×": X.vol5 >= 3,
        "OI up ≥ 1 % (30 min)": X.oi30 >= 0.01, "OI down ≥ 1 % (30 min)": X.oi30 <= -0.01,
        "OI up ≥ 1 % + volume ≥ 2×": (X.oi30 >= 0.01) & (X.vol30 >= 2), "OI down ≥ 1 % + volume ≥ 2×": (X.oi30 <= -0.01) & (X.vol30 >= 2),
        "tight 60-min range (≤ 0.2 day range)": X["squeeze"] <= 0.2, "tight range + volume ≥ 2×": (X["squeeze"] <= 0.2) & (X.vol30 >= 2),
        "near day high + above VWAP + vol ≥ 2×": (X.near_hi == 1) & (X.vwap_pos > 0) & (X.vol30 >= 2),
        "near day low + below VWAP + vol ≥ 2×": (X.near_lo == 1) & (X.vwap_pos < 0) & (X.vol30 >= 2),
        "near high + VWAP + vol ≥ 2× + OI up": (X.near_hi == 1) & (X.vwap_pos > 0) & (X.vol30 >= 2) & (X.oi30 > 0),
        "near low + VWAP + vol ≥ 2× + OI up": (X.near_lo == 1) & (X.vwap_pos < 0) & (X.vol30 >= 2) & (X.oi30 > 0),
        "day already +1.5 % + near high + vol ≥ 2×": (X.day_move >= 0.015) & (X.near_hi == 1) & (X.vol30 >= 2),
        "day already −1.5 % + near low + vol ≥ 2×": (X.day_move <= -0.015) & (X.near_lo == 1) & (X.vol30 >= 2),
    }
    base_any = (ev != 0).mean()
    print(f"\nWHEN THE HINT SHOWS -> a ≥ 1.5 % move starts within the next 5 min bar's close (normal {base_any * 100:.2f} %)")
    rows = []
    for k, m in combos.items():
        g = ev[m.fillna(False)]
        if len(g) < 50:
            print(f"  {k:44s} too few ({len(g)})"); continue
        up, dn = (g == 1).mean() * 100, (g == -1).mean() * 100
        print(f"  {k:44s} n {len(g):7,d}  UP {up:5.2f} %  DOWN {dn:5.2f} %  any {(g != 0).mean() * 100:5.2f} % "
              f"({(g != 0).mean() / base_any:3.1f}× normal)  of moves UP {(g == 1).sum() / max((g != 0).sum(), 1) * 100:3.0f} %")
        rows.append(dict(hint=k, n=len(g), up=up, down=dn, lift=(g != 0).mean() / base_any))
    # month-by-month stability of the best directional hints
    X["month"] = X.time.dt.to_period("M").astype(str)
    for k in ("near day high + above VWAP + vol ≥ 2×", "near day low + below VWAP + vol ≥ 2×", "OI down ≥ 1 % + volume ≥ 2×"):
        m = combos[k].fillna(False)
        g = X[m].groupby("month").start.agg(n="size", up=lambda s: (s == 1).mean() * 100, down=lambda s: (s == -1).mean() * 100)
        print(f"\n{k} by month:\n{g.round(2).to_string()}")
    pd.DataFrame(rows).to_csv(OUT / "premove5_hints.csv", index=False)
    X[X.start != 0][["name", "time", "start", "close", "vol5", "vol30", "oi30", "squeeze", "vwap_pos", "near_hi", "near_lo", "day_move"]] \
        .to_csv(OUT / "premove5_starts.csv.gz", index=False)


if __name__ == "__main__":
    main()
