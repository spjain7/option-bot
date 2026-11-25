"""GOLD-LVL-001 (25-Nov-2026, owner's 'AI Quant-X' XAUUSD screenshots: Golden Reversal / Liquidity Sweep / Mid-Reversal
levels, panel STRUCT BEAR · FLOW BEAR · DAY TRAP · INTENT BEAR -> SELL). The indicator's levels are proprietary, so the
price story in the screenshot is turned into testable rules on public day-start levels:
  levels  PDH / PDL (previous MCX session high / low) and MR (09:00-12:00 morning range high / low, usable after 12:00)
  SWEEP   price pierces a level by >= 0.1 ATR and closes back inside within 3 candles -> fade it (the first bounce in the
          screenshot). Stop beyond the sweep extreme + 0.1 ATR.
  RETEST  a 5-min close through a level, then within 2 hours a candle comes back to it and closes on the breakout side
          -> go with the break. Stop beyond the retest candle / level + 0.2 ATR.
  TRAP    a SWEEP of a level failed: after the reclaim, price closes beyond the sweep extreme ('trapped' fade traders)
          -> go with the break (the screenshot's big fall). Stop beyond the highest high / lowest low of the last 6 candles + 0.1 ATR.
  filters none · ALIGN = FLOW (close vs the day's VWAP) and STRUCT (EMA60 vs EMA150 on 5-min ≈ EMA20/50 on 15-min) on the trade side
  exits   1R · 2R · NEXT (next level on the ladder PDH+½range, PDH, PDC, PDL, PDL-½range, MR high/low, >= 0.5R away) ·
          all close by 23:15. Stop checked first. Costs 0.05 % round trip. Entries 10:00-22:00. First signal per setup,
          side and filter per day.
Data: MCX GOLD / SILVER Dec-26 5-min (Jul-2023 .. Nov-2026, Angel).   python research/program/gold_levels.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
OUT = ROOT / "research/program/results"
COST = 0.0005


def load(sym):
    d = pd.read_csv(ROOT / f"research/data/{sym}04DEC26FUT_5m.csv", parse_dates=["time"])
    d = d[d.time.dt.time >= pd.Timestamp("09:00").time()].reset_index(drop=True)
    tr = pd.concat([d.high - d.low, (d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / 20, adjust=False).mean()
    d["e60"], d["e150"] = d.close.ewm(span=60, adjust=False).mean(), d.close.ewm(span=150, adjust=False).mean()
    d["day"] = d.time.dt.normalize()
    tp = (d.high + d.low + d.close) / 3; v = d.volume.clip(lower=1)
    d["vwap"] = (tp * v).groupby(d.day).cumsum() / v.groupby(d.day).cumsum()
    return d


def sim(g, j0, side, stop, tg):
    o, h, l, c, tm = g._o, g._h, g._l, g._c, g._tm
    n = len(c)
    if j0 >= n:
        return None
    e = o[j0]; R = side * (e - stop)
    if not R > 0:
        return None
    out = {}
    for name, T in tg.items():
        if T is None:
            continue
        px = None
        for j in range(j0, n):
            if j > j0 and side * (o[j] - stop) <= 0:
                px = o[j]; break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                px = stop; break
            if T != "EOD" and ((h[j] >= e + side * T * R) if side > 0 else (l[j] <= e - T * R)):
                px = e + side * T * R; break
            if tm[j] >= pd.Timestamp("23:15").time():
                px = c[j]; break
        if px is None:
            px = c[n - 1]
        out[name] = side * (px - e) / R - COST * e / R
    return out, R / g._a[j0 - 1], COST * e / R


def day_signals(g, lv, sym, day):
    o, h, l, c, a = g._o, g._h, g._l, g._c, g._a
    tm = g._tm; n = len(c)
    rows = []; done = set()
    mr_end = pd.Timestamp("12:00").time(); t0, t1 = pd.Timestamp("10:00").time(), pd.Timestamp("22:00").time()
    ladder = sorted(v for v in lv["ladder"] if np.isfinite(v))
    state = {}

    def fire(setup, lvname, side, j, stop):
        for flt in ("none", "ALIGN"):
            if flt == "ALIGN" and not (side * (c[j] - g._vw[j]) > 0 and side * (g._e60[j] - g._e150[j]) > 0):
                continue
            key = (setup, side, flt)
            if key in done:
                continue
            e = o[j + 1] if j + 1 < n else None
            if e is None:
                return
            risk = side * (e - stop)
            if not (0.3 * a[j] <= risk <= 6 * a[j]):
                continue
            nx = [x for x in ladder if side * (x - e) >= 0.5 * risk]
            nxt = (min(nx) if side > 0 else max(nx)) if nx else None
            tg = {"1R": 1.0, "2R": 2.0, "NEXT": (side * (nxt - e) / risk) if nxt is not None else None, "EOD": "EOD"}
            r = sim(g, j + 1, side, stop, tg)
            if r:
                res, ra, cR = r
                for k, v in res.items():
                    rows.append((sym, day, setup, lvname, side, flt, k, v, ra, tg["NEXT"] if k == "NEXT" else None, cR))
            done.add(key)

    for j in range(1, n - 1):
        if tm[j] < t0 or tm[j] > t1:
            continue
        for lvname in ("PD", "MR"):
            if lvname == "MR" and tm[j] < mr_end:
                continue
            for side_lv, L in ((1, lv[lvname + "H"]), (-1, lv[lvname + "L"])):     # side_lv +1 = upper level
                if not np.isfinite(L):
                    continue
                st = state.setdefault((lvname, side_lv), dict(pierce=None, ext=None, brk=None, trap=None))
                tol = 0.1 * a[j]
                # pierce beyond the level
                if (h[j] > L + tol) if side_lv > 0 else (l[j] < L - tol):
                    if st["pierce"] is None:
                        st["pierce"] = j
                    st["ext"] = max(st["ext"] or -np.inf, h[j]) if side_lv > 0 else min(st["ext"] or np.inf, l[j])
                # SWEEP: closes back inside within 3 candles of the first pierce
                if st["pierce"] is not None and j - st["pierce"] <= 3 and st["trap"] is None:
                    inside = c[j] < L if side_lv > 0 else c[j] > L
                    broke_close = any((c[k] > L) if side_lv > 0 else (c[k] < L) for k in range(st["pierce"], j))
                    if inside and not broke_close:
                        fire("SWEEP", lvname, -side_lv, j, st["ext"] + side_lv * tol)
                        st["trap"] = st["ext"]                       # sweep extreme: a close beyond it = TRAP
                # TRAP: the swept extreme is broken on a close
                if st["trap"] is not None and ((c[j] > st["trap"]) if side_lv > 0 else (c[j] < st["trap"])):
                    w = slice(max(0, j - 5), j + 1)
                    stop = (l[w].min() - tol) if side_lv > 0 else (h[w].max() + tol)
                    fire("TRAP", lvname, side_lv, j, stop)
                    st["trap"] = np.nan                               # once per level per day
                # RETEST: close through the level, later back to it and holds
                if ((c[j] > L) if side_lv > 0 else (c[j] < L)) and ((c[j - 1] <= L) if side_lv > 0 else (c[j - 1] >= L)):
                    st["brk"] = j
                elif st["brk"] is not None and 0 < j - st["brk"] <= 24:
                    touch = (l[j] <= L + tol) if side_lv > 0 else (h[j] >= L - tol)
                    holds = (c[j] > L) if side_lv > 0 else (c[j] < L)
                    if touch and holds:
                        stop = (min(l[j], L) - 2 * tol) if side_lv > 0 else (max(h[j], L) + 2 * tol)
                        fire("RETEST", lvname, side_lv, j, stop)
                        st["brk"] = None
    return rows


def run(sym):
    d = load(sym)
    D = d.groupby("day").agg(h=("high", "max"), l=("low", "min"), c=("close", "last"))
    rows = []
    days = D.index
    for k in range(1, len(days)):
        g = d[d.day == days[k]]
        if len(g) < 100:
            continue
        p = D.iloc[k - 1]; rg = p.h - p.l
        if abs(g.open.iat[0] / p.c - 1) > 0.06:
            continue
        mr = g[g.time.dt.time < pd.Timestamp("12:00").time()]
        lv = dict(PDH=p.h, PDL=p.l, MRH=mr.high.max(), MRL=mr.low.min())
        lv["ladder"] = [p.h + 0.5 * rg, p.h, p.c, p.l, p.l - 0.5 * rg, lv["MRH"], lv["MRL"]]
        g = g.reset_index(drop=True)
        g._o, g._h, g._l, g._c, g._a = (g[x].values for x in ("open", "high", "low", "close", "atr"))
        g._vw, g._e60, g._e150, g._tm = g.vwap.values, g.e60.values, g.e150.values, g.time.dt.time.values
        rows += day_signals(g, lv, sym, days[k])
    return rows


def main():
    import warnings; warnings.filterwarnings("ignore")
    rows = run("GOLD") + run("SILVER")
    T = pd.DataFrame(rows, columns=["sym", "day", "setup", "lvl", "side", "flt", "tgt", "R", "risk_atr", "nextR", "costR"])
    T["gross"] = T.R + T.costR; T["R02"] = T.gross - 0.4 * T.costR   # R at 0.02 % round trip
    T["per"] = np.where(T.day < "2025-01-01", "23-24", np.where(T.day < "2026-01-01", "2025", "2026"))
    T.to_parquet(OUT / "gold_levels_trades.parquet")
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 300)
    S = T.groupby(["setup", "side", "flt", "tgt"]).apply(lambda x: pd.Series(dict(
        n=len(x), win=round(100 * (x.R > 0).mean()), R=round(x.R.mean(), 3), gross=round(x.gross.mean(), 3), R02=round(x.R02.mean(), 3), riskATR=round(x.risk_atr.median(), 2), costR=round(x.costR.median(), 2), GOLD=round(x[x.sym == "GOLD"].R.mean(), 3),
        SILVER=round(x[x.sym == "SILVER"].R.mean(), 3), **{p: round(x[x.per == p].R.mean(), 3) for p in ("23-24", "2025", "2026")})))
    print(S.to_string())
    S.to_csv(OUT / "gold_levels_summary.csv")


if __name__ == "__main__":
    main()
