"""REV5-001 (30-Oct-2026): trade the clearest 5-min footprint from PREMOVE-002 – stretched day + at the day's extreme + volume.
BUY : stock already ≥ 1.5 % down on the day, price within 0.2 day-range of the day's low, below VWAP, 30-min volume ≥ 2×
SELL: mirror (≥ 1.5 % up, near the day's high, above VWAP, volume ≥ 2×). 09:45-14:30, one trade per stock per side per day.
Entry next 5-min open · stop: beyond the day's extreme ± 0.1 day-range · target 1R or 2R · exit 15:15 · futures, real lot sizes,
costs 2× (as live). 218 stocks, 27-Jul → 29-Oct-2026, months reported separately. python research/program/rev5.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program.premove5 import prep  # noqa: E402
from research.search.stock_check import cost_frac  # noqa: E402
from research.search import stock_search as SR  # noqa: E402

lots = pd.read_csv(SR.DATA / "manifest_stocks.csv").set_index("name")["lot"].to_dict()
rows = []
for p in sorted((ROOT / "research/data/m5").glob("fut_*.csv")):
    nm = p.stem[4:]
    full = pd.read_csv(p, parse_dates=["time"]).sort_values("time").drop_duplicates("time")
    full = full[(full.time.dt.strftime("%H:%M") >= "09:15") & (full.time.dt.strftime("%H:%M") < "15:30")].reset_index(drop=True)
    x = prep(p)
    if x is None or nm not in lots:
        continue
    lot = int(lots[nm])
    pos = {t: k for k, t in enumerate(full.time)}
    for side in (1, -1):
        m = ((x.day_move <= -0.015) & (x.near_lo == 1) & (x.vwap_pos < 0) if side > 0 else
             (x.day_move >= 0.015) & (x.near_hi == 1) & (x.vwap_pos > 0)) & (x.vol30 >= 2)
        done = set()
        for r in x[m.fillna(False)].itertuples():
            if r.day in done:
                continue
            k = pos.get(r.time)
            if k is None or k + 1 >= len(full) or full.day.iat[k + 1] != r.day if "day" in full else False:
                continue
            done.add(r.day)
            e0 = full.open.iat[k + 1]
            ext = r.dlo if side > 0 else r.dhi
            st = ext - side * 0.1 * r.adr
            R = side * (e0 - st)
            if not R > 0:
                continue
            day = full.time.dt.normalize().iat[k + 1]
            js = [j for j in range(k + 1, min(k + 80, len(full))) if full.time.iat[j].normalize() == day and full.time.iat[j].strftime("%H:%M") <= "15:15"]
            cf = cost_frac(e0, lot) * 2
            res = {}
            for tg in (1.0, 2.0):
                tp = e0 + side * tg * R; px = None
                for j in js:
                    if (full.low.iat[j] <= st) if side > 0 else (full.high.iat[j] >= st):
                        px = st; break
                    if (full.high.iat[j] >= tp) if side > 0 else (full.low.iat[j] <= tp):
                        px = tp; break
                if px is None:
                    px = full.close.iat[js[-1]] if js else e0
                res[tg] = (side * (px - e0) - cf)
            rows.append(dict(name=nm, time=r.time, side="BUY" if side > 0 else "SELL", lot=lot, entry=e0, stop=st, R=R,
                             r1=res[1.0] / R, r2=res[2.0] / R, rs1=res[1.0] * lot, rs2=res[2.0] * lot, risk_rs=R * lot))
T = pd.DataFrame(rows)
T["month"] = T.time.dt.to_period("M").astype(str)
T.to_csv(ROOT / "research/program/results/rev5_trades.csv", index=False)
for k, g in T.groupby("side"):
    print(f"\n{k}: {len(g)} trades · win 1R {(g.r1 > 0).mean() * 100:.0f} % · avg {g.r1.mean():+.3f}R · ₹/lot avg {g.rs1.mean():+,.0f} total {g.rs1.sum():+,.0f}"
          f" | 2R: win {(g.r2 > 0).mean() * 100:.0f} % · avg {g.r2.mean():+.3f}R · ₹ total {g.rs2.sum():+,.0f} · median risk ₹{g.risk_rs.median():,.0f}/lot")
    print(g.groupby("month").agg(n=("r1", "size"), win1=("r1", lambda s: (s > 0).mean() * 100), R1=("r1", "mean"), rs1=("rs1", "sum"),
                                 R2=("r2", "mean"), rs2=("rs2", "sum")).round(2).to_string())
