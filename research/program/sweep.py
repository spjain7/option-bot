"""SWEEP-001 (29-Oct-2026) – owner's request: liquidity-sweep (stop-hunt) reversal accuracy.
Sweep candle (closed): its high goes ABOVE a liquidity level but it CLOSES BACK BELOW it -> SELL (mirror -> BUY).
Levels: PD  previous-day high / low (intraday candles only)
        SW  highest high / lowest low of the previous 20 candles
        EQ  equal highs / lows: two pivot highs (lows) in the previous 40 candles within 0.1 ATR of each other
Entry: break of the sweep candle's low (SELL) / high (BUY) within 3 candles (stop order; gap -> open).
Stop: 0.05 ATR beyond the sweep candle's extreme. Target 1R or 2R. Time exit 20 candles. Costs 1× (2× reported).
Filters: V volume ≥ 1.5× · C strong rejection (close in the lower / upper third of the candle) · T counter-trend only
(SELL when close > EMA50 – sweep above highs in a rise; BUY mirror).
Markets: MCX + NIFTY/BANKNIFTY futures (1h, 3h, 1d) and 181 stock futures (1h, 3h, 1d), 2022-26.
Periods: train < Jul-24 ≤ valid < Jul-25 ≤ test.
"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX, daily_candles as DC  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"


def levels(f, tf):
    h, l = f["high"], f["low"]
    sw_h, sw_l = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
    out = {"SW": (sw_h.values, sw_l.values)}
    if tf != "1d":
        day = pd.to_datetime(f["time"]).dt.normalize()
        g = f.groupby(day)
        pdh = day.map(g["high"].max().shift(1)); pdl = day.map(g["low"].min().shift(1))
        out["PD"] = (pdh.values, pdl.values)
    a = f["atr"].values
    ph = (h > h.shift(1)) & (h > h.shift(-1)); pl = (l < l.shift(1)) & (l < l.shift(-1))
    ph = ph.shift(1).fillna(False).values; pl = pl.shift(1).fillna(False).values   # pivot known one candle later
    hv, lv = h.values, l.values
    eqh, eql = np.full(len(f), np.nan), np.full(len(f), np.nan)
    for i in range(45, len(f)):
        idx = [k - 1 for k in range(i - 40, i) if ph[k]]
        for x, y in itertools.combinations(idx[-6:], 2):
            if abs(hv[x] - hv[y]) <= 0.1 * a[i] and max(hv[x], hv[y]) >= hv[min(x, y):i].max() - 1e-9:
                eqh[i] = max(hv[x], hv[y])
        idx = [k - 1 for k in range(i - 40, i) if pl[k]]
        for x, y in itertools.combinations(idx[-6:], 2):
            if abs(lv[x] - lv[y]) <= 0.1 * a[i] and min(lv[x], lv[y]) <= lv[min(x, y):i].min() + 1e-9:
                eql[i] = min(lv[x], lv[y])
    out["EQ"] = (eqh, eql)
    return out


def run(job):
    try:
        fr = EX.frames(job)
    except Exception as e:
        print("skip", job[:2], e); return []
    rows = []
    for seg, f, _od, cost in fr:
        if "NSE" in seg or "proxy" in seg:
            continue
        tf = seg.split()[-1]
        f = f.reset_index(drop=True)
        if len(f) < 120:
            continue
        f["atr"] = I.atr(f, 14)
        o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
        v = f["volume"].astype(float); vx = (v / v.rolling(20).mean().shift(1)).values
        e50 = I.ema(f["close"], 50).values
        rng = np.where(h - l > 0, h - l, np.nan); pos = (c - l) / rng
        tm = f["time"].values
        for lvname, (hi_lv, lo_lv) in levels(f, tf).items():
            for side in (1, -1):
                lv = lo_lv if side > 0 else hi_lv
                sweep = (l < lv) & (c > lv) if side > 0 else (h > lv) & (c < lv)
                busy = -1
                for i in np.flatnonzero(np.nan_to_num(sweep, nan=0).astype(bool)):
                    if i < 60 or i <= busy or i >= len(f) - 2 or f["switch"].iat[i] or not f["atr"].iat[i] > 0:
                        continue
                    t1 = DC.trade(f, i, side, l[i] if side > 0 else h[i], h[i] if side > 0 else l[i], "E2", 1.0, cost)
                    if t1 is None:
                        continue
                    t2 = DC.trade(f, i, side, l[i] if side > 0 else h[i], h[i] if side > 0 else l[i], "E2", 2.0, cost)
                    busy = t1["j"]
                    rows.append((seg.split()[0], tf, job[1], lvname, "BUY" if side > 0 else "SELL", tm[i],
                                 bool(vx[i] >= 1.5), bool((pos[i] >= 2 / 3) if side > 0 else (pos[i] <= 1 / 3)),
                                 bool(c[i] < e50[i]) if side > 0 else bool(c[i] > e50[i]),
                                 t1["r1"], t1["r2"], t2["r1"] if t2 else np.nan, t2["r2"] if t2 else np.nan))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] in ("mi", "stk")]
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(run, J, chunksize=1) for r in x]
    T = pd.DataFrame(rows, columns=["market", "tf", "name", "level", "side", "time", "V", "C", "T",
                                    "r1R", "r1R_2x", "r2R", "r2R_2x"])
    T["time"] = pd.to_datetime(T["time"], format="mixed", utc=True).dt.tz_localize(None)
    T["split"] = np.where(T["time"] < "2024-07-01", "train", np.where(T["time"] < "2025-07-01", "valid", "test"))
    T.to_csv(OUT / "sweep_trades.csv.gz", index=False)
    print(len(T))


if __name__ == "__main__":
    main()
