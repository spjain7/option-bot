"""Data layer. Daily: official NSE cash bhavcopies 2005-01 … 2026-11 (research/data/nse_cm via eq_bhav.adjusted – exact
corporate-action back-adjustment from NSE's PREVCLOSE; delisted stocks included -> no survivorship bias; ETFs / fund
units excluded). RAW bhavcopy rows stay in research/data/nse_cm; ADJUSTED series only in memory / _adjusted.pkl.
Intraday: Angel NSE cash 5-minute candles (research/data/angel/NSE_EQ, 218 current liquid stocks, 2024-10-14 … 2026-11-06),
split / bonus adjusted with eq_data.adjust_splits (Angel cash prices are unadjusted). SURVIVORSHIP: intraday list = stocks
liquid today -> results there are biased upward (reported). Timestamps: IST bar START (09:15 = 09:15-09:20); a signal on a
bar is known only at its close; entries at the NEXT bar's open."""
import pickle
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import eq_bhav as EB, eq_data as ED  # noqa: E402

CM_PKL = ROOT / "research/data/nse_cm/_adjusted.pkl"
EQ5 = ROOT / "research/data/angel/NSE_EQ"
MIN_TURNOVER, MIN_PRICE, MIN_HIST = 25e7, 50.0, 250


def daily_panel():
    """-> dict of wide DataFrames (index = trading days, columns = security key) for the securities that are EVER in the
    point-in-time universe: open high low close volume value factor, 'symbol' and the eligibility mask 'elig'
    (eligibility itself is computed day by day, before the column restriction)."""
    A = pickle.loads(CM_PKL.read_bytes())
    idx = pd.DatetimeIndex(sorted({t for d in A.values() for t in d["time"]}))
    col = lambda f, ks: pd.DataFrame({k: pd.Series(A[k][f].values.astype("float32"), index=pd.DatetimeIndex(A[k]["time"])) for k in ks}).reindex(idx)
    keys = list(A)
    close, value = col("close", keys), col("value", keys)
    to60 = value.rolling(60, min_periods=40).median().shift(1)
    hist = close.notna().cumsum()
    elig = (to60 >= MIN_TURNOVER) & (close >= MIN_PRICE) & (hist >= MIN_HIST) & close.notna()
    keep = list(elig.columns[elig.any(axis=0)])
    W = dict(close=close[keep], value=value[keep], elig=elig[keep])
    del close, value, to60, hist, elig
    for f in ("open", "high", "low", "volume", "factor"):
        W[f] = col(f, keep)
    W["symbol"] = pd.Series({k: str(A[k]["symbol"].iloc[-1]) for k in keep})
    W["market"] = EB.market(A).set_index("time").reindex(idx)              # EW index of the 100 most-traded stocks (PIT)
    del A
    return W


def weekly(W):
    """Weekly bars (week ending Friday or the last session of the week) from the daily wide frames."""
    g = W["close"].index.to_period("W-FRI")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "value": "sum"}
    out = {f: W[f].groupby(g).agg(agg[f]) for f in agg}
    last_day = pd.Series(W["close"].index, index=W["close"].index).groupby(g).last()
    for f in out:
        out[f].index = pd.DatetimeIndex(last_day.values)
    out["factor"] = (W["factor"].fillna(1.0) != 1.0).groupby(g).max().set_axis(out["close"].index)
    out["elig"] = W["elig"].groupby(g).last().set_axis(out["close"].index).astype(bool)
    out["symbol"] = W["symbol"]
    return out


def intraday(sym, log=None):
    d = pd.read_csv(EQ5 / f"{sym}_FIVE_MINUTE.csv.gz")
    d["time"] = pd.to_datetime(d["time"])
    d = ED.clean(d, intraday=True)
    mins = d["time"].dt.hour * 60 + d["time"].dt.minute
    d = d[(mins >= 555) & (mins <= 925) & (d["time"].dt.weekday < 5)]        # regular session, weekdays (no Muhurat)
    d = ED.adjust_splits(d.reset_index(drop=True), log=log, sym=sym)
    return d.reset_index(drop=True)


def intraday_symbols():
    return sorted(p.name.split("_FIVE_MINUTE")[0] for p in EQ5.glob("*_FIVE_MINUTE.csv.gz"))


def resample(d, minutes):
    """5-min -> N-min bars anchored at 09:15 (bar start time), only complete bars (all 5-min parts present)."""
    if minutes == 5:
        return d.copy()
    t = d["time"]
    day = t.dt.normalize()
    k = ((t - day - pd.Timedelta(hours=9, minutes=15)).dt.total_seconds() // (minutes * 60)).astype(int)
    g = d.groupby([day, k])
    o = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
              volume=("volume", "sum"), n=("close", "size")).reset_index(drop=True)
    need = np.minimum(minutes // 5, 75)                       # last bar of the day can be shorter (15:15-15:30 for 30/60 min)
    o["start"] = day.groupby([day, k]).first().values if False else o["time"].dt.normalize() + pd.Timedelta(hours=9, minutes=15) + \
        pd.to_timedelta(((o["time"] - o["time"].dt.normalize() - pd.Timedelta(hours=9, minutes=15)).dt.total_seconds() // (minutes * 60)) * minutes, unit="m")
    end = o["start"] + pd.Timedelta(minutes=minutes)
    close_t = o["time"].dt.normalize() + pd.Timedelta(hours=15, minutes=30)
    exp = ((np.minimum(end, close_t) - o["start"]).dt.total_seconds() // 300).astype(int)
    o = o[o["n"] >= exp].copy()
    o["time"] = o["start"]
    return o[["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
