"""ZONES-001 (25-Nov-2026, owner's video 'AI Quant-X'). The indicator's zones (Demand / Supply / FI / XI) are proprietary
(volume footprint + 'AI'), so they cannot be reproduced. This tests the VIDEO'S TRADING RULES with a public stand-in for
the zones: static levels fixed at the open from the previous day (floor pivots) – XI = R2, Supply = R1, Demand = S1,
FI = S2; R3 / S3 serve only as the 'next zone' target beyond the outer zones.
Rules (15-minute candles, first signal per rule per day, entries until 14:30 stocks / 22:00 MCX, exit at the day's end):
  RETEST  a candle closes through a zone; a later candle comes back to the zone and closes on the breakout side ->
          enter next open; stop below the zone / retest candle low (- 0.1 ATR15); target = next zone.
  REVERSE price comes down to a zone (up to it for SELL), the candle closes back above it in the top half of its range ->
          stop order above that candle's high (3 candles); stop below its low / the zone (- 0.1 ATR15); target = next zone.
Costs 0.10 % stocks, 0.05 % MCX round trip. Data: NSE cash 5-min (218 F&O stocks, Oct-2024 .. Nov-2026), MCX GOLD / SILVER
5-min (2024 .. Nov-2026).   python research/program/zones_proxy.py"""
import os
import sys
import warnings
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
EQ = Path("/home/claude/rd/research/data/angel/NSE_EQ")
OUT = ROOT / "research/program/results"
BUF = float(os.environ.get("ZBUF", "0.1"))       # stop buffer beyond the zone, x ATR15 (sensitivity run: 0.5)


def load(job):
    seg, sym = job
    if seg == "STK":
        d = pd.read_csv(EQ / f"{sym}_FIVE_MINUTE.csv.gz", parse_dates=["time"])
        d = d[(d.time.dt.time >= pd.Timestamp("09:15").time()) & (d.time.dt.time < pd.Timestamp("15:30").time())]
        cost, last_entry, base = 0.001, "14:30", "9h15min"
    else:
        d = pd.read_csv(ROOT / f"research/data/{sym}04DEC26FUT_5m.csv", parse_dates=["time"])
        d = d[(d.time >= "2024-01-01") & (d.time.dt.time >= pd.Timestamp("09:00").time())]
        cost, last_entry, base = 0.0005, "22:00", "9h"
    day = d.time.dt.normalize()
    k = day + pd.Timedelta(base) + ((d.time - day - pd.Timedelta(base)) // pd.Timedelta("15min")) * pd.Timedelta("15min")
    m = d.groupby(k).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")).reset_index()
    m.columns = ["time", "open", "high", "low", "close"]
    m["day"] = m.time.dt.normalize()
    return m, cost, pd.Timestamp(last_entry).time()


def one(job):
    try:
        m, cost, le = load(job)
    except Exception as ex:
        print("skip", job, ex); return []
    D = m.groupby("day").agg(h=("high", "max"), l=("low", "min"), c=("close", "last"))
    D = D[(D.h > D.l)]
    tr = pd.concat([m.high - m.low, (m.high - m.close.shift()).abs(), (m.low - m.close.shift()).abs()], axis=1).max(axis=1)
    m["atr"] = tr.ewm(alpha=1 / 20, adjust=False).mean()
    rows = []
    days = D.index
    for di in range(1, len(days)):
        pv = D.iloc[di - 1]; P = (pv.h + pv.l + pv.c) / 3
        if abs(m.loc[m.day == days[di], "open"].iloc[0] / pv.c - 1) > 0.15:
            continue                                     # corporate action / bad data
        r1, s1 = 2 * P - pv.l, 2 * P - pv.h; r2, s2 = P + pv.h - pv.l, P - (pv.h - pv.l)
        r3, s3 = pv.h + 2 * (P - pv.l), pv.l - 2 * (pv.h - P)
        zones = [s2, s1, r1, r2]; ladder = [s3, s2, s1, r1, r2, r3]
        g = m[m.day == days[di]]
        o, h, l, c, a = (g[x].values for x in ("open", "high", "low", "close", "atr"))
        tm = g.time.dt.time.values; n = len(c)
        if n < 8:
            continue

        def nxt(z, side):
            k = ladder.index(z) + side
            return ladder[k]

        def trade(j0, e, side, stop, tgt):
            R = side * (e - stop)
            if not R > 0 or side * (tgt - e) <= 0:
                return None
            for j in range(j0, n):
                if j > j0 and side * (o[j] - stop) <= 0:
                    return side * (o[j] - e) / R - cost * e / R, side * (o[j] - e) / R, side * (tgt - e) / R
                if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                    return side * (stop - e) / R - cost * e / R, -1.0, side * (tgt - e) / R
                if (h[j] >= tgt) if side > 0 else (l[j] <= tgt):
                    return side * (tgt - e) / R - cost * e / R, side * (tgt - e) / R, side * (tgt - e) / R
            return side * (c[n - 1] - e) / R - cost * e / R, side * (c[n - 1] - e) / R, side * (tgt - e) / R

        done = set()
        broke = {}                                          # zone -> (side, bar) of the breakout close
        for j in range(1, n - 1):
            if tm[j] > le:
                break
            tol = 0.1 * a[j]
            for z in zones:
                for side in (1, -1):
                    # breakout close
                    if side * (c[j] - z) > 0 and side * (c[j - 1] - z) <= 0:
                        broke[(z, side)] = j
                    # RETEST
                    b = broke.get((z, side))
                    if ("RETEST", side) not in done and b is not None and j > b:
                        touch = (l[j] <= z + tol) if side > 0 else (h[j] >= z - tol)
                        if touch and side * (c[j] - z) > 0:
                            stop = (min(l[j], z) - BUF * a[j]) if side > 0 else (max(h[j], z) + BUF * a[j])
                            r = trade(j + 1, o[j + 1], side, stop, nxt(z, side))
                            if r:
                                rows.append((job[0], job[1], days[di], "RETEST", side, *r))
                            done.add(("RETEST", side))
                    # REVERSE (BUY: comes down to the zone from above, closes back above in the top half)
                    if ("REVERSE", side) not in done:
                        came = side * (c[j - 1] - z) > 0
                        hit = (l[j] <= z) if side > 0 else (h[j] >= z)
                        rg = h[j] - l[j]
                        strong = rg > 0 and ((c[j] - l[j]) / rg >= 0.5 if side > 0 else (h[j] - c[j]) / rg >= 0.5)
                        if came and hit and side * (c[j] - z) > 0 and strong:
                            lev = h[j] if side > 0 else l[j]
                            stop = (min(l[j], z) - BUF * a[j]) if side > 0 else (max(h[j], z) + BUF * a[j])
                            for k in range(j + 1, min(n, j + 4)):
                                if (l[k] <= stop) if side > 0 else (h[k] >= stop):
                                    break
                                if (h[k] >= lev) if side > 0 else (l[k] <= lev):
                                    e = max(o[k], lev) if side > 0 else min(o[k], lev)
                                    r = trade(k, e, side, stop, nxt(z, side))
                                    if r:
                                        rows.append((job[0], job[1], days[di], "REVERSE", side, *r))
                                    break
                            done.add(("REVERSE", side))
    return rows


def main():
    U = pd.read_csv(EQ / "universe.csv")
    J = [("STK", s) for s in U[U.fno == True].symbol if (EQ / f"{s}_FIVE_MINUTE.csv.gz").exists()]   # noqa: E712
    J += [("MCX", "GOLD"), ("MCX", "SILVER")]
    rows = []
    with Pool(2) as p:
        for r in p.imap_unordered(one, J, chunksize=4):
            rows += r
    T = pd.DataFrame(rows, columns=["seg", "sym", "day", "rule", "side", "R", "gross", "tgtR"])
    T.to_parquet(OUT / f"zones_proxy_trades_buf{BUF}.parquet")
    pd.set_option("display.width", 200)
    print(T.groupby(["seg", "rule", "side"]).agg(n=("R", "size"), win=("R", lambda x: round(100 * (x > 0).mean())),
                                                 R=("R", "mean"), gross=("gross", "mean"), tgtR=("tgtR", "median")).round(2).to_string())


if __name__ == "__main__":
    main()
