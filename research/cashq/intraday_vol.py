"""CASH INTRADAY on UNUSUAL VOLUME (owner 18-Nov-2026: "catch unusual volume intraday, find a winning strategy").
Data: Angel 5-minute NSE cash candles, 218 liquid stocks, 2024-10 .. 2026-11 (SURVIVORSHIP: list = stocks liquid today, so
results are biased upward). Bar times = bar START (09:15 = 09:15-09:20). Costs 0.08 % of price per round trip (intraday
brokerage, STT on sell, exchange, GST, stamp, slippage); also reported at 0.15 %.
A) STOCKS-IN-PLAY ORB (Zarattini, Barbon & Aziz 2024, "A profitable day trading strategy for the U.S. equity market"):
   RVOL = first-k-minute volume / its average over the previous 14 days. The first candle's colour sets the side (green ->
   long only, red -> short only). Stop order at the opening-range high (low); stop = s x 14-day daily ATR from the fill;
   exit at the target (1R / 2R / 3R) or the 15:10 bar's close (EOD). Entries until 14:00. Same-bar fill + stop counted as
   a stop (conservative). Stocks ranked each day by RVOL: top N (5 / 10 / 20) with RVOL >= 1 / 2 / 3.
B) VOLUME-SPIKE BREAKOUT: after 09:45 and up to 14:00, the first 5-minute bar with volume >= X x the average volume of that
   same time slot over the previous 14 days that closes at a new high of the day above VWAP -> long at the next bar's open
   (mirror for short). Stop = spike bar's low (high) or 0.5 ATR; exit target 1R / 2R / EOD.
Split: H1 2024-10 .. 2025-10 vs H2 2025-11 .. 2026-11. Pass = positive net average in both halves AND above a random-side baseline.
python -m research.cashq.intraday_vol -> results/intraday_vol_trades.parquet, results/intraday_vol.csv"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
COSTS = (0.0008, 0.0015)
SPLIT = pd.Timestamp("2025-11-01")
SQ, LAST = 910, 840                     # square-off bar start 15:10 (exit at its close), last entry bar 14:00
TG = (0.0, 1.0, 2.0, 3.0)               # 0 = EOD


@njit(cache=True)
def run(o, h, l, c, mi, a, b, side, level, stopd, tg, from_stop_order):
    """bars a..b-1 of one day. from_stop_order: fill when price crosses `level` (stop order); else fill at o[a].
    Returns entry, exit, filled flag, mfe (in R)."""
    px = np.nan; j0 = -1
    if from_stop_order:
        for j in range(a, b):
            if mi[j] > LAST:
                break
            if side > 0 and h[j] >= level:
                px = max(o[j], level); j0 = j; break
            if side < 0 and l[j] <= level:
                px = min(o[j], level); j0 = j; break
    else:
        if a < b and mi[a] <= LAST + 5:
            px = o[a]; j0 = a
    if j0 < 0:
        return np.nan, np.nan, 0, 0.0
    st = px - side * stopd; tp = px + side * tg * stopd if tg > 0 else np.nan
    mfe = 0.0
    for j in range(j0, b):
        if side > 0:
            if l[j] <= st:
                return px, (st if j > j0 or o[j] > st else o[j]), 1, mfe
            mfe = max(mfe, (h[j] - px) / stopd)
            if tg > 0 and h[j] >= tp and (j > j0 or c[j] >= tp):
                return px, max(o[j], tp) if j > j0 else tp, 1, mfe
        else:
            if h[j] >= st:
                return px, (st if j > j0 or o[j] < st else o[j]), 1, mfe
            mfe = max(mfe, (px - l[j]) / stopd)
            if tg > 0 and l[j] <= tp and (j > j0 or c[j] <= tp):
                return px, min(o[j], tp) if j > j0 else tp, 1, mfe
        if mi[j] >= SQ:
            return px, c[j], 1, mfe
    return px, c[b - 1], 1, mfe


def stock_rows(sym):
    d = D.intraday(sym)
    if len(d) < 5000:
        return []
    t = d["time"]; day = t.dt.normalize().values; mi = (t.dt.hour * 60 + t.dt.minute).values.astype(np.int64)
    o, h, l, c, v = (d[x].values.astype(np.float64) for x in ("open", "high", "low", "close", "volume"))
    dd = d.assign(day=day).groupby("day").agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
    tr = pd.concat([dd.h - dd.l, (dd.h - dd.c.shift()).abs(), (dd.l - dd.c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().shift(1)
    tp_ = (h + l + c) / 3; g = pd.Series(day)
    vwap = (pd.Series(tp_ * v).groupby(g).cumsum() / pd.Series(v).groupby(g).cumsum().replace(0, np.nan)).to_numpy(copy=True)
    dhi = pd.Series(h).groupby(g).cummax().shift(1).to_numpy(copy=True); dlo = pd.Series(l).groupby(g).cummin().shift(1).to_numpy(copy=True)
    first = pd.Series(day).ne(pd.Series(day).shift()).values
    dhi[first] = np.nan; dlo[first] = np.nan
    # same-slot average volume over the previous 14 days
    slot = pd.DataFrame({"day": day, "mi": mi, "v": v}).pivot_table(index="day", columns="mi", values="v", aggfunc="sum")
    slot_avg = slot.rolling(14, min_periods=10).mean().shift(1)
    sa = slot_avg.stack().rename("sa"); key = pd.MultiIndex.from_arrays([day, mi])
    savg = sa.reindex(key).to_numpy(copy=True)
    bounds = np.flatnonzero(first).tolist() + [len(d)]
    days = dd.index
    orv = {k: slot[[m for m in slot.columns if 555 <= m < 555 + k]].sum(axis=1) for k in (5, 15)}
    orv_avg = {k: orv[k].rolling(14, min_periods=10).mean().shift(1) for k in (5, 15)}
    rows = []
    for di in range(len(bounds) - 1):
        a, b = bounds[di], bounds[di + 1]
        dday = pd.Timestamp(day[a]); A = atr.get(dday, np.nan)
        if not A > 0 or mi[a] != 555 or o[a] < 50:
            continue
        base = dict(symbol=sym, date=dday, atr_pct=A / o[a])
        # A) ORB
        for k in (5, 15):
            nb = k // 5; orb = slice(a, a + nb)
            if b - a <= nb or mi[a + nb - 1] != 555 + k - 5:
                continue
            rv = orv[k].get(dday, np.nan) / orv_avg[k].get(dday, np.nan)
            co, cc = o[a], c[a + nb - 1]
            if not np.isfinite(rv) or co == cc:
                continue
            side = 1 if cc > co else -1
            lev = h[orb].max() if side > 0 else l[orb].min()
            for s in (0.10, 0.25, 0.50):
                for tg in TG:
                    px, ex, f, mfe = run(o, h, l, c, mi, a + nb, b, side, lev, s * A, tg, True)
                    if f:
                        rows.append(dict(base, setup=f"ORB{k}", side=side, rvol=rv, stop_atr=s, tg=tg, entry=px, exit=ex, stopd=s * A, mfe=mfe))
        # B) volume spike breakout
        for j in range(a + 6, b - 1):
            if mi[j] > LAST:
                break
            if not savg[j] > 0:
                continue
            x = v[j] / savg[j]
            if x < 4:
                continue
            up = c[j] > dhi[j] and c[j] > vwap[j] and c[j] > o[j]; dn = c[j] < dlo[j] and c[j] < vwap[j] and c[j] < o[j]
            if not (up or dn):
                continue
            side = 1 if up else -1
            for sname, sd in (("bar", (o[j + 1] - l[j]) if up else (h[j] - o[j + 1])), ("0.5ATR", 0.5 * A)):
                sd = max(sd, 0.1 * A)
                for tg in (0.0, 1.0, 2.0):
                    px, ex, f, mfe = run(o, h, l, c, mi, j + 1, b, side, 0.0, sd, tg, False)
                    if f:
                        rows.append(dict(base, setup="VSPIKE", side=side, rvol=x, stop_atr=sname, tg=tg, entry=px, exit=ex, stopd=sd, mfe=mfe,
                                         spike_min=int(mi[j])))
            break
    return rows


def main():
    syms = D.intraday_symbols(); rows = []
    for i, s in enumerate(syms):
        try:
            rows += stock_rows(s)
        except Exception as e:  # noqa: BLE001
            print("skip", s, e, flush=True)
        if i % 25 == 0:
            print(i, s, len(rows), flush=True)
    R = pd.DataFrame(rows); R["stop_atr"] = R.stop_atr.astype(str)
    R["gross"] = R.side * (R.exit / R.entry - 1)
    R.to_parquet(OUT / "intraday_vol_trades.parquet")
    print("rows", len(R))


if __name__ == "__main__":
    main()
