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


def monthly_contracts(rows):
    """Keep one MONTHLY contract per expiry month (drops the illiquid weekly futures some indices had) and merge
    contracts whose expiry was re-labelled by the exchange (e.g. NIFTY Jun-2023: 29th -> 28th, holiday)."""
    rows = rows.copy()
    rows["ym"] = rows["expiry"].dt.to_period("M")
    keep = []
    for ym, g in rows.groupby("ym"):
        span = g.groupby("expiry")["date"].agg(["min", "max"])
        final = span.sort_values(["max"]).index[-1]                   # the label still trading last = the monthly
        days_final = set(g.loc[g.expiry == final, "date"])
        for e, (lo, hi) in span.iterrows():
            if e == final:
                keep.append(g[g.expiry == e]); continue
            ge = g[g.expiry == e]
            if not set(ge["date"]) & days_final and e.month == final.month and abs((e - final).days) <= 3:
                keep.append(ge.assign(expiry=final))                  # same contract, older label
    return pd.concat(keep).drop(columns="ym")


def build_nse(symbol, rows, roll_days=3):
    rows = _clean(rows[rows["symbol"] == symbol])
    if rows.empty:
        return None
    rows = monthly_contracts(rows)
    dates = np.array(sorted(rows["date"].unique()))
    pos = {d: i for i, d in enumerate(dates)}
    tot = rows.groupby("date").agg(volume=("contracts", "sum"), oi=("oi", "sum"))
    roll = {}
    for e, g in rows.groupby("expiry"):
        if pd.Timestamp(e) > pd.Timestamp(dates[-1]):                # still trading at the end of the data
            roll[e] = dates[-1]; continue
        last = g["date"].max()                                       # its last trading day
        roll[e] = dates[max(pos[last] - roll_days, 0)]
    exps = sorted(roll)
    by = {(pd.Timestamp(d), pd.Timestamp(e)): r for d, e, r in zip(rows["date"], rows["expiry"], rows.itertuples(index=False))}
    out, prev = [], None
    for d in map(pd.Timestamp, dates):
        cand = [e for e in exps if d <= roll[e] and (d, pd.Timestamp(e)) in by]
        if not cand:
            continue
        e = pd.Timestamp(cand[0]); r = by[(d, e)]
        out.append(dict(time=d, expiry=e, open=r.open, high=r.high, low=r.low, close=r.close, traded=r.contracts > 0,
                        contracts_front=r.contracts))
        prev = e
    df = pd.DataFrame(out)
    # roll at the close of the last day on the old contract: gap = new close - old close on that day
    df["roll"], df["roll_gap"] = False, 0.0
    nxt = df["expiry"].shift(-1)
    for i in np.where((nxt != df["expiry"]) & nxt.notna())[0]:
        d, old, new = df.at[i, "time"], df.at[i, "expiry"], nxt.iloc[i]
        rn = by.get((d, pd.Timestamp(new)))
        df.at[i, "roll"] = True
        df.at[i, "roll_gap"] = (rn.close - df.at[i, "close"]) if rn is not None else 0.0
    df = df.set_index("time").join(tot)
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
