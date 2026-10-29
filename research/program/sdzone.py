"""SDZONE-001 (29-Oct-2026) – owner's request: supply / demand zone trades.
Zone (classic definition): a BASE of 1-3 small candles (body ≤ 50 % of range) followed by a LEG-OUT candle with range
≥ 1.5 ATR and body ≥ 60 % of range.
  Demand zone (leg-out up):  proximal = highest body top of the base, distal = lowest low of the base.
  Supply zone (leg-out down): proximal = lowest body bottom of the base, distal = highest high of the base.
Trade: FIRST return to a fresh zone at least 3 candles after it formed (within 100 candles):
  BUY at the demand proximal line (limit order; a candle opening inside the zone fills at its open), stop 0.05 ATR below
  the distal line; SELL mirror at supply. Zones wider than 2 ATR are skipped. A candle opening beyond the stop cancels.
  Trades whose risk is under 0.3 ATR or whose round-trip cost exceeds 1/3 of the risk are skipped.
  Target 1R or 2R; time exit 20 candles. On the entry candle the stop counts (if touched) but the target does not
  (cautious – the order of the high and low inside the candle is unknown).
Filters: T trend (BUY only above EMA50, SELL below) · S strong leg-out (range ≥ 2.5 ATR) · V leg-out volume ≥ 1.5×
  · O OI on the leg-out day in the zone's direction (stocks / index: long buildup for demand, short buildup for supply)
  · N narrow zone (≤ 0.75 ATR).
Markets: MCX + index (1h, 3h, 1d) and 181 stock futures (1h, 3h, 1d), 2022-26. Costs 1× (2× reported).
Periods: train < Jul-24 ≤ valid < Jul-25 ≤ test.
"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"


def zones(f):
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    a = f["atr"].values
    rng = h - l; body = np.abs(c - o)
    small = (rng > 0) & (body <= 0.5 * rng)
    out = []
    for k in range(20, len(f)):
        if not (a[k - 1] > 0) or rng[k] < 1.5 * a[k - 1] or body[k] < 0.6 * rng[k]:
            continue
        side = 1 if c[k] > o[k] else -1
        nb = 0
        while nb < 3 and small[k - 1 - nb]:
            nb += 1
        if nb == 0:
            continue
        b = slice(k - nb, k)
        if side > 0:
            prox, dist = np.maximum(o[b], c[b]).max(), l[b].min()
        else:
            prox, dist = np.minimum(o[b], c[b]).min(), h[b].max()
        width = abs(prox - dist)
        if width <= 0 or width > 2 * a[k - 1]:
            continue
        out.append(dict(k=k, side=side, prox=prox, dist=dist, width_atr=width / a[k - 1], leg_atr=rng[k] / a[k - 1]))
    return out


def trade(f, z, tgt, cost):
    o, h, l, c, a, sw = (f[x].values for x in ("open", "high", "low", "close", "atr", "switch"))
    n, side, k = len(c), z["side"], z["k"]
    st = z["dist"] - side * 0.05 * a[k]
    j0 = e0 = None
    for j in range(k + 1, min(k + 101, n)):
        if sw[j]:
            return None                                       # zone of an old contract
        if j < k + 4:
            if (l[j] <= z["prox"]) if side > 0 else (h[j] >= z["prox"]):
                return None                                   # touched too early – not a fresh retest
            continue
        if (l[j] <= z["prox"]) if side > 0 else (h[j] >= z["prox"]):
            if side * (o[j] - st) <= 0:
                return None                                   # gapped through the stop
            e0 = min(o[j], z["prox"]) if side > 0 else max(o[j], z["prox"])
            j0 = j; break
    if j0 is None:
        return None
    R = side * (e0 - st)
    if not R > 0 or cost[k] / R > 1 / 3 or R < 0.3 * a[k]:
        return None                                           # risk too small for the costs / one tick of noise
    tp = e0 + side * tgt * R
    px = None; j = j0
    while j < n:
        if j > j0 and sw[j]:
            px, j = c[j - 1], j - 1; break
        if j > j0 and side * (o[j] - st) <= 0:
            px = o[j]; break
        if j > j0 and side * (o[j] - tp) >= 0:
            px = o[j]; break
        if (l[j] <= st) if side > 0 else (h[j] >= st):
            px = st; break
        if j > j0 and ((h[j] >= tp) if side > 0 else (l[j] <= tp)):
            px = tp; break
        if j - j0 >= 19:
            px = c[j]; break
        j += 1
    if px is None:
        return None
    g = side * (px - e0)
    return dict(j0=j0, R=R, r1=(g - cost[k]) / R, r2=(g - 2 * cost[k]) / R)


def run(job):
    try:
        fr = EX.frames(job)
    except Exception as e:
        print("skip", job[:2], e); return []
    rows = []
    for seg, f, od, cost in fr:
        if "NSE" in seg or "proxy" in seg:
            continue
        tf = seg.split()[-1]
        f = f.reset_index(drop=True)
        if len(f) < 150:
            continue
        f["atr"] = I.atr(f, 14)
        v = f["volume"].astype(float); vx = (v / v.rolling(20).mean().shift(1)).values
        e50 = I.ema(f["close"], 50).values
        c = f["close"].values
        for z in zones(f):
            k = z["k"]
            t1 = trade(f, z, 1.0, cost)
            if t1 is None:
                continue
            t2 = trade(f, z, 2.0, cost)
            j0 = t1["j0"]
            rows.append((seg.split()[0], tf, job[1], "BUY" if z["side"] > 0 else "SELL", f["time"].iat[j0],
                         bool((c[j0 - 1] > e50[j0 - 1]) if z["side"] > 0 else (c[j0 - 1] < e50[j0 - 1])),
                         bool(z["leg_atr"] >= 2.5), bool(vx[k] >= 1.5), bool(od[k] == z["side"]), bool(z["width_atr"] <= 0.75),
                         t1["r1"], t1["r2"], t2["r1"] if t2 else np.nan, t2["r2"] if t2 else np.nan, j0 - k))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] in ("mi", "stk")]
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(run, J, chunksize=1) for r in x]
    T = pd.DataFrame(rows, columns=["market", "tf", "name", "side", "time", "T", "S", "V", "O", "N", "r1R", "r1R_2x", "r2R", "r2R_2x", "age"])
    T["time"] = pd.to_datetime(T["time"], format="mixed", utc=True).dt.tz_localize(None)
    T["split"] = np.where(T["time"] < "2024-07-01", "train", np.where(T["time"] < "2025-07-01", "valid", "test"))
    T.to_csv(OUT / "sdzone_trades.csv.gz", index=False)
    rows = []
    for (mk, tf, sd), g in T.groupby(["market", "tf", "side"]):
        for cb in [(), ("T",), ("S",), ("V",), ("O",), ("N",), ("T", "V"), ("T", "S"), ("T", "O"), ("V", "O"), ("T", "V", "O")]:
            x = g
            for q in cb:
                x = x[x[q]]
            if len(x) < 40:
                continue
            for tg in ("r1R", "r2R"):
                sp = x.groupby("split")[tg].mean()
                rows.append(dict(market=mk, tf=tf, side=sd, filt="+".join(cb) or "none", tgt=tg[1:], n=len(x),
                                 win=round((x[tg] > 0).mean() * 100, 1), exp=round(x[tg].mean(), 3), exp2=round(x[tg + "_2x"].mean(), 3),
                                 tr=round(sp.get("train", np.nan), 3), va=round(sp.get("valid", np.nan), 3), te=round(sp.get("test", np.nan), 3),
                                 ntr=int((x.split == "train").sum()), nte=int((x.split == "test").sum())))
    R = pd.DataFrame(rows)
    R["ok"] = (R.tr > 0) & (R.va > 0) & (R.te > 0) & (R.exp2 > 0) & (R.ntr >= 30) & (R.nte >= 20)
    R.to_csv(OUT / "sdzone_variants.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    print("trades", len(T), "variants", len(R), "pass", int(R.ok.sum()))
    print(R[(R.filt == "none") & (R.tgt == "1R")].to_string(index=False))
    print(R[R.ok].sort_values("exp", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
