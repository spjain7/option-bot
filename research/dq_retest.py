"""DATA-AUDIT-001 re-test: do the LIVE MCX daily rules survive VERIFIED data?

Same rules, same period, two data sets:
  A  Angel vendor-stitched front month (raw, as the original research used)
  B  bhavcopy OI-leader continuous, exact roll gaps, back-adjusted (research/continuous_verified.py)
Rules (alerts/candle_setups.py MCX_HAMMER, frozen, incl. max stop 6 %): hammer (lower wick ≥ 2× body, upper wick ≤ 0.3× range) -> stop-buy
above the hammer high, valid 3 sessions, stop 0.05 ATR(14) below the hammer low, target 2R, exit at the 20th session
close. Gap through a level fills at the open; stop first if one bar touches both. Costs 0.04 % of the raw price.
Also BO_1d_BUY-like 20-day high breakout is NOT re-tested here (its rules live in alerts/engine.py with live filters).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import data_audit as DA, continuous_verified as CV  # noqa: E402
from alerts.candle_setups import hammer_shape  # noqa: E402
from crude import indicators as I  # noqa: E402

COST = 0.0004
START = pd.Timestamp("2022-07-15")


def hammer_bt(d, name, src):
    d = d.reset_index(drop=True)
    raw = d["raw_close"] if "raw_close" in d else d["close"]
    atr = I.atr(d, 14)
    sh = hammer_shape(d)
    o, h, l, c = (d[k].values for k in ("open", "high", "low", "close"))
    out, busy_until = [], -1
    for i in np.where(sh.values)[0]:
        if i <= busy_until or i < 20 or d.at[i, "time"] < START or not np.isfinite(atr.iloc[i]):
            continue
        trig, stop = h[i], l[i] - 0.05 * atr.iloc[i]
        ent = None
        for j in range(i + 1, min(i + 4, len(d))):
            if h[j] > trig:
                ent, ej = max(o[j], trig), j
                break
        if ent is None:
            continue
        R = ent - stop
        if R <= 0 or R / ent * 100 > 6.0:                      # P["max_stop_pct"]
            continue
        tgt = ent + 2 * R
        x, xj, why = None, None, None
        for k in range(ej, min(ej + 20, len(d))):
            if k > ej and o[k] <= stop:
                x, why = o[k], "stop"
            elif l[k] <= stop:
                x, why = stop, "stop"
            elif k > ej and o[k] >= tgt:
                x, why = o[k], "target"
            elif h[k] >= tgt:
                x, why = tgt, "target"
            if x is not None:
                xj = k; break
        if x is None:
            xj = min(ej + 19, len(d) - 1); x, why = c[xj], "time"
            if xj == len(d) - 1 and ej + 19 > len(d) - 1:
                continue                                        # still open
        r = (x - ent) / R - COST * float(raw.iloc[ej]) / R
        roll_inside = bool(d["roll"].iloc[ej:xj + 1].any()) if "roll" in d else None
        out.append(dict(name=name, src=src, signal=d.at[i, "time"].date(), entry_day=d.at[ej, "time"].date(),
                        R_pts=R, r=r, exit=why, roll_inside=roll_inside))
        busy_until = xj
    return out


def angel(name):
    a, _ = DA.load_angel(name, "ONE_DAY")
    a = a[["time", "open", "high", "low", "close", "volume"]].sort_values("time").drop_duplicates("time").reset_index(drop=True)
    sw = set(pd.to_datetime(pd.read_csv(DA.OUT / "rolls_true.csv").query("name == @name")["switch_day"]))
    a["roll"] = a["time"].isin(sw)
    return a[a["time"] <= pd.Timestamp("2026-10-21")]


def summ(t):
    if t.empty:
        return {}
    w, l = t[t.r > 0].r.sum(), -t[t.r <= 0].r.sum()
    return dict(n=len(t), win=round((t.r > 0).mean(), 3), avgR=round(t.r.mean(), 3), pf=round(w / l, 2) if l else None,
                t1=round((t.exit == "target").mean(), 3))


def main():
    rows = []
    for n in DA.NAMES:
        rows += hammer_bt(angel(n), n, "A_angel_raw")
        v = CV.build(n)
        rows += hammer_bt(v[v["time"] <= pd.Timestamp("2026-10-21")], n, "B_verified")
    t = pd.DataFrame(rows)
    t.to_csv(DA.OUT / "retest_hammer.csv", index=False)
    print("ALL", {s: summ(g) for s, g in t.groupby("src")})
    for n, g in t.groupby("name"):
        print(n, {s: summ(x) for s, x in g.groupby("src")})
    t["y"] = pd.to_datetime(t.signal).dt.year
    for y, g in t.groupby("y"):
        print(y, {s: summ(x) for s, x in g.groupby("src")})
    a = t[t.src == "A_angel_raw"]
    print("Angel trades with a roll inside:", summ(a[a.roll_inside == True]), "without:", summ(a[a.roll_inside == False]))  # noqa: E712
    ka, kb = set(zip(a.name, a.signal)), set(zip(t[t.src == "B_verified"].name, t[t.src == "B_verified"].signal))
    print(f"same signal day in both: {len(ka & kb)} · only Angel {len(ka - kb)} · only verified {len(kb - ka)}")
    return t


if __name__ == "__main__":
    main()
