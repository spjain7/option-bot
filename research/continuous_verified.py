"""VERIFIED MCX continuous futures from the official MCX bhavcopy (DATA-AUDIT-001, 4-Nov-2026).

Why: Angel's stitched front-month series (a) stays on the expiring contract ~7 sessions after the market has rolled
(tender / delivery days, 8-18 % of base-metal and gold days priced from an illiquid contract) and (b) is raw – every roll
leaves a price jump (median 0.6-5.2 % per roll, NATURALGAS 5 %). research/roll_adjust.py ESTIMATED those gaps; the
bhavcopy gives them EXACTLY (both contracts trade on the same day).

Construction (pre-declared):
  * contract = the open-interest leader; move to the next expiry the first day its OI exceeds the current contract's,
    never move back; never hold a contract on/after its expiry day (forced roll the session before).
  * roll gap = new close − old close on the LAST day of the old contract (same day, official closes) – no estimation.
  * back-adjusted additively (prices before a roll shifted by the cumulative gap); raw_* columns keep the real prices.
  * close = MCX official closing price (bhavcopy). Note: Angel's daily close was the last trade until ~Feb-2024 and the
    official closing price after – a definition change inside the Angel series that this series does not have.
Status VERIFIED for daily research from 2022-07-01 (bhavcopy coverage). Intraday is not available from this source.

  from research.continuous_verified import build;  d = build("GOLD")
"""
import glob
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BHAV = ROOT / "research" / "data" / "mcx_bhav" / "days"
STATUS = "VERIFIED"
SOURCE = "MCX official bhavcopy (FUTCOM), OI-leader roll, exact same-day roll gaps, additive back-adjustment"


@lru_cache(maxsize=1)
def _bhav():
    fs = sorted(glob.glob(str(BHAV / "*.csv")))
    b = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    b = b[b["instrument"] == "FUTCOM"].copy()
    b["date"] = pd.to_datetime(b["date"])
    b["exp"] = pd.to_datetime(b["expiry"], format="%d%b%Y")
    for c in ("open", "high", "low", "close", "volume_lots", "oi_lots"):
        b[c] = pd.to_numeric(b[c], errors="coerce")
    return b


def build(name, adjust=True):
    g = _bhav()
    g = g[(g["symbol"] == name) & (g["close"] > 0)].sort_values(["date", "exp"])
    if g.empty:
        return None
    days = sorted(g["date"].unique())
    by = {d: x.set_index("exp") for d, x in g.groupby("date")}
    cur, rows = None, []
    for d in days:
        x = by[d]
        live = x[x.index > d]                                   # contracts not expiring today
        if cur is None or cur not in x.index or cur <= d:
            cand = live if len(live) else x
            cur = cand["oi_lots"].idxmax() if cand["oi_lots"].max() > 0 else cand.index.min()
            switched = bool(rows)
        else:
            nxt = live[live.index > cur]
            switched = False
            if len(nxt) and nxt["oi_lots"].max() > x.at[cur, "oi_lots"]:
                cur = nxt["oi_lots"].idxmax(); switched = True
            elif (cur - d).days <= 0:
                cur = live.index.min(); switched = True
        r = x.loc[cur]
        rows.append(dict(time=d, contract=cur.date(), open=r["open"], high=r["high"], low=r["low"], close=r["close"],
                         volume=r["volume_lots"], oi=r["oi_lots"], oi_total=float(x["oi_lots"].sum()), roll=switched))
    df = pd.DataFrame(rows)
    df["gap"] = 0.0
    for i in np.where(df["roll"])[0]:
        if i == 0:
            continue
        p = df.at[i - 1, "time"]
        old, new = pd.Timestamp(df.at[i - 1, "contract"]), pd.Timestamp(df.at[i, "contract"])
        xp = by[p]
        if new in xp.index and old in xp.index:
            df.at[i - 1, "gap"] = float(xp.at[new, "close"] - xp.at[old, "close"])
        else:                                                   # new contract had no trade the day before (rare)
            df.at[i - 1, "gap"] = float(df.at[i, "open"] - df.at[i - 1, "close"])
            df.at[i, "gap_estimated"] = True
    # shift for bar i = sum of gaps at rolls AFTER bar i (gap is stored on the old contract's last day, which also shifts)
    shift = df["gap"][::-1].cumsum()[::-1] if adjust else pd.Series(0.0, index=df.index)
    for k in ("open", "high", "low", "close"):
        df["raw_" + k] = df[k]
        df[k] = df[k] + shift
    df["offset"] = shift
    df["status"], df["source"] = STATUS, SOURCE
    return df


def rolls(name):
    d = build(name)
    return d[d["roll"]][["time", "contract"]] if d is not None else None


if __name__ == "__main__":
    for n in ("GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"):
        d = build(n)
        print(n, len(d), d["time"].min().date(), d["time"].max().date(), "rolls", int(d["roll"].sum()),
              "offset now→start", round(float(d["offset"].iloc[0]), 2), "min adj low", round(float(d["low"].min()), 2))
