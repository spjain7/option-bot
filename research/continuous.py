"""Continuous series for SIGNALS, kept separate from contract-level EXECUTION.

build_nse(symbol): from REAL bhavcopy contract rows
  - active contract: the front contract until `roll_days` trading days before its expiry; the roll happens at
    that day's close (old leg sold / bought back at its close, new leg opened at the new contract's close)
  - adjusted series: difference back-adjustment at exactly those roll closes, so trading the adjusted series
    gives the same point P&L as trading the actual contracts with those rolls
  - raw_* columns: the actual held contract's prices; offset = adj - raw (constant inside a contract segment)
  - volume / oi: totals over all expiries that day (what was known at that day's close)
load_proxy(name, '1d'|'1h'): Yahoo proxy as-is (offset 0, roll dates unknown -> no roll costs, flagged)
"""
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


def _clean(rows):
    """Untraded contracts are printed with zero OHLC: use the close/settle so no fake highs/lows are created."""
    rows = rows.copy()
    c = rows["close"].where(rows["close"] > 0, rows["settle"])
    rows["close"] = c
    for k in ("open", "high", "low"):
        rows[k] = rows[k].where(rows[k] > 0, c)
    rows["high"] = rows[["high", "open", "close"]].max(axis=1)
    rows["low"] = rows[["low", "open", "close"]].min(axis=1)
    return rows


def build_nse(symbol, rows, roll_days=3):
    rows = _clean(rows[rows["symbol"] == symbol])
    if rows.empty:
        return None
    dates = np.array(sorted(rows["date"].unique()))
    pos = {d: i for i, d in enumerate(dates)}
    tot = rows.groupby("date").agg(volume=("contracts", "sum"), oi=("oi", "sum"))
    # roll date of each contract = the trading day `roll_days` before its last trading day
    roll = {}
    for e in sorted(rows["expiry"].unique()):
        last = dates[dates <= e]
        if len(last):
            roll[e] = dates[max(pos[last[-1]] - roll_days, 0)]
    exps = sorted(roll)
    by = {(d, e): r for d, e, r in zip(rows["date"], rows["expiry"], rows.itertuples(index=False))}
    out, j = [], 0
    for d in dates:
        while j < len(exps) and roll[exps[j]] < d:          # past its roll date -> next contract
            j += 1
        if j >= len(exps):
            break
        e = exps[j]
        r = by.get((d, e))
        if r is None:                                       # held contract missing that day -> skip day
            continue
        nxt = by.get((d, exps[j + 1])) if (d == roll[e] and j + 1 < len(exps)) else None
        out.append(dict(time=d, expiry=e, open=r.open, high=r.high, low=r.low, close=r.close,
                        traded=r.contracts > 0, roll=nxt is not None,
                        roll_gap=(nxt.close - r.close) if nxt is not None else 0.0,
                        next_expiry=exps[j + 1] if nxt is not None else pd.NaT))
    df = pd.DataFrame(out).set_index("time").join(tot)
    # difference back-adjustment: everything before a roll is shifted by that roll's gap
    shift = df["roll_gap"][::-1].cumsum()[::-1]     # roll-day row is still the old contract -> includes its gap
    for k in ("open", "high", "low", "close"):
        df["raw_" + k] = df[k]
        df[k] = df[k] + shift
    df["offset"] = shift
    df["contract"] = symbol + df["expiry"].dt.strftime("%d%b%y").str.upper() + "FUT"
    return df.reset_index()


def load_nse(symbols=None, roll_days=3):
    from research.adapters.nse_bhavcopy import load
    rows = load(symbols)
    return {s: build_nse(s, rows, roll_days) for s in (symbols or sorted(rows["symbol"].unique()))}


def load_proxy(name, tf):
    f = DATA / "proxy" / f"{name}_{tf}.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f, parse_dates=["time"])
    for k in ("open", "high", "low", "close"):
        d["raw_" + k] = d[k]
    d["offset"], d["roll"], d["roll_gap"] = 0.0, False, 0.0
    d["contract"], d["oi"], d["traded"] = "PROXY", np.nan, True
    return d


def load_angel(name, interval):
    """Angel One vendor-stitched FRONT-MONTH series (REAL exchange prices, NOT back-adjusted; the vendor switches
    contract at expiry, so each roll shows up as a price jump). Returns None when not downloaded."""
    man = DATA / "angel" / "manifest.csv"
    if not man.exists():
        return None
    m = pd.read_csv(man)
    m = m[(m["name"] == name) & (m["interval"] == interval) & (m["bars"] > 0)]
    if "front_stitched" in m:
        m = m[m["front_stitched"]]
    if m.empty:
        return None
    r = m.sort_values("bars").iloc[-1]
    d = pd.read_csv(DATA / "angel" / r["exch"] / f"{r['symbol']}_{interval}.csv", parse_dates=["time"])
    d = d[(d["open"] > 0) & (d["close"] > 0)].reset_index(drop=True)
    for k in ("open", "high", "low", "close"):
        d["raw_" + k] = d[k]
    d["offset"], d["roll"], d["roll_gap"] = 0.0, False, 0.0
    d["contract"], d["oi"], d["traded"] = "ANGEL-FRONT", np.nan, d["volume"] > 0
    return d
