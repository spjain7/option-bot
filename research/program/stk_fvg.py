"""STK-FVG-001 (19-Nov-2026): the "S/R breakout + Fair Value Gap retracement" idea from github.com/ajxv/edge
(strategies/sr_fvg_breakout.py, their own verdict: research in progress, marginal) tested SELL-side on our stock futures
(181 F&O stocks 2022-26, 1-hour and 3-hour candles, 2x costs, next-open entry, stop first, SEARCH-V2 harness and periods).
  bearish FVG at bar i: low[i-2] > high[i], gap >= 0.25 ATR, zone = [high[i], low[i-2]]
  SELL signal: within 15 bars of an unfilled FVG (no close above its top since), the candle trades up INTO the zone and
  closes back below the zone top, red candle; filters: close < EMA200 (their trend filter) and close below the previous
  day's low (their "territory"), each on / off
  exits: stop 1 / 1.5 / 2 ATR x target 2 / 3R, max 40 candles
python research/program/stk_fvg.py -> results/stk_fvg_summary.csv"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_v2 as SV  # noqa: E402

OUT = ROOT / "research/program/results"


def fvg_sell(f, fd):
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    atr = f["atr"].values; n = len(c)
    e200 = pd.Series(c).ewm(span=200, adjust=False, min_periods=200).mean().values
    day = pd.to_datetime(f["time"]).dt.normalize().values
    dd = fd.assign(d=pd.to_datetime(fd["time"]).dt.normalize()).set_index("d")["low"]
    pdl = pd.Series(day).map(dd.shift(1)).values                     # previous session's low
    sig = np.zeros(n, bool); zones = []
    for i in range(2, n):
        zones = [(top, bot, k) for top, bot, k in zones if i - k <= 15 and c[i - 1] <= top]
        if zones and c[i] < o[i]:
            for top, bot, k in zones:
                if h[i] >= bot and c[i] < top and i > k:
                    sig[i] = True; break
        if l[i - 2] > h[i] and atr[i] > 0 and (l[i - 2] - h[i]) >= 0.25 * atr[i]:
            zones.append((l[i - 2], h[i], i))
    return sig, c < e200, c < pdl


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in fr}
    if "STOCKS 1d" not in seg:
        return None
    fd = seg["STOCKS 1d"][0]; rows = []
    for tf in ("1h", "3h"):
        if f"STOCKS {tf}" not in seg:
            continue
        C, cost = seg[f"STOCKS {tf}"]
        if len(C) < 300:
            continue
        f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
        if len(cost) != len(f):
            cost = np.interp(np.arange(len(f)), np.linspace(0, len(f) - 1, len(cost)), cost)
        s0, ema, pdl = fvg_sell(f, fd)
        t = pd.to_datetime(f["time"]).values
        for (fe, fp), k, r in itertools.product(((0, 0), (1, 0), (0, 1), (1, 1)), (1.0, 1.5, 2.0), (2.0, 3.0)):
            s = s0 & (ema if fe else True) & (pdl if fp else True)
            for x in H.simulate(f, np.where(s, -1, 0), -1, k, r, 40, 0, cost, start=210):
                if x["status"] == "trade":
                    rows.append((tf, f"{'EMA200 ' if fe else ''}{'PDL' if fp else ''}".strip() or "none", k, r, job[1], t[x["i"]], x["r2"]))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        T = pd.DataFrame([r for x in p.imap_unordered(one, J, chunksize=2) if x for r in x], columns=["tf", "filt", "k", "r", "name", "t_in", "R"])
    tv = pd.to_datetime(T.t_in).values; T["split"] = np.where(tv < SV.P1, "p1", np.where(tv < SV.P2, "p2", "p3"))
    out = []
    for key, g in T.groupby(["tf", "filt", "k", "r"]):
        row = dict(zip(["tf", "filt", "k", "r"], key), n=len(g), win=round(100 * (g.R > 0).mean(), 1), R=round(g.R.mean(), 3),
                   stocks_pos=round(g.groupby("name").R.sum().gt(0).mean(), 2))
        for sp in ("p1", "p2", "p3"):
            x = g[g.split == sp].R; row[f"{sp}_n"] = len(x); row[f"{sp}_win"] = round(100 * (x > 0).mean(), 1); row[f"{sp}_R"] = round(x.mean(), 3)
        row["all3_pos"] = all(row[f"{sp}_R"] > 0 for sp in ("p1", "p2", "p3"))
        out.append(row)
    L = pd.DataFrame(out).sort_values("R", ascending=False); L.to_csv(OUT / "stk_fvg_summary.csv", index=False)
    pd.set_option("display.width", 230); pd.set_option("display.max_rows", 100)
    print(f"combos {len(L)} · positive in all 3 periods {int(L.all3_pos.sum())}")
    print(L.to_string(index=False))


if __name__ == "__main__":
    main()
