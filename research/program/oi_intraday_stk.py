"""OI-INTRA-002 (26-Nov-2026, owner: "check for intraday if any strategy works on 15 or 30 min with OI support").
Data: research-m5 (Angel getOIData): 218 F&O stock futures, 5-min price + OI, 27-Jul .. 29-Oct-2026 (~65 sessions).
Angel's OI series is the FRONT-month OI (it drops into each expiry as positions roll), so expiry days and the 2 sessions
before (25-Aug, 29-Sep, 27-Oct) are skipped. No intraday OI history exists for indices or MCX (Angel AB1012).
Candles 15 / 30 min (09:15 anchored). Price signals (first per stock per day, 09:45-14:30):
  ORB     close beyond the first candle's (09:15) high / low
  BO4     close beyond the high / low of the previous 4 candles
  VWAP    close crosses VWAP (day) in the direction of the day's move (close vs open)
  MOMO    candle range >= 1.5 ATR, close in the outer 25 % of the candle
  OISPIKE OI jumps >= 1.0 % (15 min) / 1.5 % (30 min) in one candle with a >= 0.5 ATR candle body -> trade the body's side
OI conditions at the signal candle: none · BAR (OI up in the signal candle = build-up on the trade side) · DAY (OI up >= 1 %
since the day's first candle AND price on the trade side since the open) · AGAINST (OI down in the signal candle).
Trade: next candle's open; stop = signal candle's far end (min 0.5 ATR); exits 1R, 2R, EOD (15:15). Stop checked first.
Costs 0.05 % round trip (gross also shown). Periods: Aug / Sep / Oct.   python research/program/oi_intraday_stk.py"""
import sys
import warnings
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
M5 = Path("/home/claude/rd/m5/research/data/m5")
OUT = ROOT / "research/program/results"
COST = 0.0005
SKIP = {pd.Timestamp(x) for x in ("2026-08-21", "2026-08-24", "2026-08-25", "2026-09-25", "2026-09-28", "2026-09-29",
                                    "2026-10-23", "2026-10-26", "2026-10-27")}


def bars(f, mins):
    d = pd.read_csv(f, parse_dates=["time"])
    d = d[(d.time.dt.time >= pd.Timestamp("09:15").time()) & (d.time.dt.time < pd.Timestamp("15:30").time())]
    day = d.time.dt.normalize()
    k = day + pd.Timedelta("9h15min") + ((d.time - day - pd.Timedelta("9h15min")) // pd.Timedelta(f"{mins}min")) * pd.Timedelta(f"{mins}min")
    b = d.groupby(k).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                         volume=("volume", "sum"), oi=("oi", "last")).reset_index().rename(columns={"index": "time"})
    b.columns = ["time", "open", "high", "low", "close", "volume", "oi"]
    b["day"] = b.time.dt.normalize()
    tr = pd.concat([b.high - b.low, (b.high - b.close.shift()).abs(), (b.low - b.close.shift()).abs()], axis=1).max(axis=1)
    b["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)          # known before the candle
    tp = (b.high + b.low + b.close) / 3; v = b.volume.clip(lower=1)
    b["vwap"] = (tp * v).groupby(b.day).cumsum() / v.groupby(b.day).cumsum()
    return b


def one(job):
    f, mins = job
    try:
        b = bars(f, mins)
    except Exception:
        return []
    rows = []
    spike = 0.010 if mins == 15 else 0.015
    for day, g in b.groupby("day"):
        if day in SKIP or len(g) < 8:
            continue
        o, h, l, c, a, oi, vw = (g[x].values for x in ("open", "high", "low", "close", "atr", "oi", "vwap"))
        tm = g.time.dt.time.values; n = len(c)
        if not np.isfinite(oi).all() or (oi <= 0).any():
            continue
        doi_bar = np.r_[np.nan, oi[1:] / oi[:-1] - 1]
        doi_day = oi / oi[0] - 1
        done = set()
        for j in range(1, n - 1):
            if tm[j] < pd.Timestamp("09:45").time() or tm[j] > pd.Timestamp("14:30").time() or not a[j] > 0:
                continue
            sigs = []
            for sd in (1, -1):
                if sd * (c[j] - (h[0] if sd > 0 else l[0])) > 0 and sd * (c[j - 1] - (h[0] if sd > 0 else l[0])) <= 0:
                    sigs.append(("ORB", sd))
                if j >= 4:
                    lv = h[j - 4:j].max() if sd > 0 else l[j - 4:j].min()
                    if sd * (c[j] - lv) > 0:
                        sigs.append(("BO4", sd))
                if sd * (c[j] - vw[j]) > 0 and sd * (c[j - 1] - vw[j - 1]) <= 0 and sd * (c[j] - o[0]) > 0:
                    sigs.append(("VWAP", sd))
                rg = h[j] - l[j]
                if rg >= 1.5 * a[j] and (((c[j] - l[j]) / rg >= 0.75) if sd > 0 else ((h[j] - c[j]) / rg >= 0.75)):
                    sigs.append(("MOMO", sd))
                if doi_bar[j] >= spike and sd * (c[j] - o[j]) >= 0.5 * a[j]:
                    sigs.append(("OISPIKE", sd))
            for nm, sd in sigs:
                conds = {"none": True, "BAR": doi_bar[j] > 0, "DAY": doi_day[j] >= 0.01 and sd * (c[j] - o[0]) > 0, "AGAINST": doi_bar[j] < 0}
                stop = (min(l[j], c[j] - 0.5 * a[j])) if sd > 0 else (max(h[j], c[j] + 0.5 * a[j]))
                e = o[j + 1]; R = sd * (e - stop)
                if not R > 0 or R > 4 * a[j]:
                    continue
                res = {}
                for tg in ("1R", "2R", "EOD"):
                    T = e + sd * (1 if tg == "1R" else 2) * R if tg != "EOD" else None
                    px = None
                    for k in range(j + 1, n):
                        if k > j + 1 and sd * (o[k] - stop) <= 0:
                            px = o[k]; break
                        if (l[k] <= stop) if sd > 0 else (h[k] >= stop):
                            px = stop; break
                        if T is not None and ((h[k] >= T) if sd > 0 else (l[k] <= T)):
                            px = T; break
                        if tm[k] >= pd.Timestamp("15:00" if mins == 30 else "15:15").time():
                            px = c[k]; break
                    if px is None:
                        px = c[n - 1]
                    res[tg] = sd * (px - e) / R
                for cn, ok in conds.items():
                    if not ok or (nm, sd, cn) in done:
                        continue
                    done.add((nm, sd, cn))
                    for tg, r in res.items():
                        rows.append((mins, f.stem[4:], day, nm, sd, cn, tg, r - COST * e / R, r, COST * e / R))
    return rows


def main():
    J = [(f, m) for f in sorted(M5.glob("fut_*.csv")) for m in (15, 30)]
    rows = []
    with Pool(2) as p:
        for r in p.imap_unordered(one, J, chunksize=8):
            rows += r
    T = pd.DataFrame(rows, columns=["tf", "sym", "day", "sig", "side", "oi", "tgt", "R", "gross", "costR"])
    T["mon"] = T.day.dt.strftime("%b")
    T.to_parquet(OUT / "oi_intraday_stk_trades.parquet")
    st = lambda g: pd.Series(dict(n=len(g), win=round(100 * (g.R > 0).mean()), R=round(g.R.mean(), 3), gross=round(g.gross.mean(), 3),  # noqa: E731
                                  costR=round(g.costR.median(), 2), dayavg=round(g.groupby("day").R.mean().mean(), 3),
                                  **{m: round(g[g.mon == m].R.mean(), 3) for m in ("Aug", "Sep", "Oct")}))
    S = T.groupby(["tf", "sig", "side", "oi", "tgt"]).apply(st).reset_index()
    S["PASS"] = (S[["Aug", "Sep", "Oct"]].min(axis=1) > 0) & (S.dayavg > 0) & (S.n >= 150)
    S.to_csv(OUT / "oi_intraday_stk_summary.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 400)
    print(S[S.tgt == "EOD"].to_string(index=False))
    print("\nPASS\n", S[S.PASS].sort_values("R", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
