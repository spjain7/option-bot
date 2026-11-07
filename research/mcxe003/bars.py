"""Bar preparation for MCXE-003 (all markets). Every frame has:
time (bar START), end (bar END = when the bar is complete), open high low close volume, day (session date), m (minute of
day of the bar start), seg (segment id: changes at a contract roll / stock change / corporate-action gap -> no swing, level
or line may connect across it), sig_ok (signals allowed on this bar: not a roll day, inside trading hours), atr (ATR14 of
this timeframe, Wilder, past bars only), plus intraday: vwap (session VWAP at the bar END), dlast (index of the session's last
bar), datr (previous sessions' daily ATR14).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa: E402

MCX7 = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]


def _finish(f, tf_min, intraday=True):
    f = f.reset_index(drop=True)
    f["end"] = f.time + pd.Timedelta(minutes=tf_min) if intraday else f.time
    f["day"] = f.time.dt.normalize()
    f["m"] = f.time.dt.hour * 60 + f.time.dt.minute
    f["atr"] = I.atr(f, 14).values
    if intraday:
        last = f.groupby("day").cumcount(ascending=False) == 0
        idx = np.arange(len(f)); dl = pd.Series(np.where(last, idx, np.nan)).bfill().values
        f["dlast"] = dl.astype(np.int64)
        tp = (f.high + f.low + f.close) / 3
        cv = f.volume.groupby(f.day).cumsum().replace(0, np.nan)
        f["vwap"] = ((tp * f.volume).groupby(f.day).cumsum() / cv).values
        d = f.groupby("day").agg(h=("high", "max"), l=("low", "min"), c=("close", "last"), o=("open", "first"))
        tr = np.maximum(d.h - d.l, np.maximum((d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()))
        d["datr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=10).mean().shift(1)
        d["pdh"], d["pdl"], d["pdc"] = d.h.shift(1), d.l.shift(1), d.c.shift(1)
        for k in ("datr", "pdh", "pdl", "pdc"):
            f[k] = f.day.map(d[k]).values
        f["dopen"] = f.day.map(d.o).values
    return f


# ── MCX intraday (Angel front-month 5-min, stitched) ────────────────────────────────────────────────────────────────
def mcx_intraday(name, tf):
    from research.program import liqtl_mcx5 as LM
    d = LM.load(name, "FIVE_MINUTE")
    d["switch"] = d.switch.fillna(False).astype(bool)
    f = d if tf == 5 else LM.resample(d, tf)
    f["switch"] = f.switch.astype(bool)
    day = f.time.dt.normalize()
    sw_day = f.groupby(day).switch.transform("max").astype(bool)
    f["seg"] = (sw_day & (day != day.shift(1))).cumsum().values
    f = _finish(f, tf)
    f["sig_ok"] = (~sw_day.values) & (f.m >= 9 * 60).values & ((f.end.dt.hour * 60 + f.end.dt.minute) <= 22 * 60).values
    f.attrs.update(market="MCX", name=name, tf=tf)
    return f


def mcx_base5(name):
    """5-minute execution frame for MCX."""
    return mcx_intraday(name, 5)


# ── NSE cash intraday (Angel 5-min, 218 liquid stocks, today's list -> survivorship caveat) ─────────────────────────
def nse_eq_symbols():
    from research.program import eq_data as ED
    return sorted(p.name.split("_FIVE_MINUTE")[0] for p in ED.EQ.glob("*_FIVE_MINUTE.csv.gz"))


def nse_eq_intraday(sym, tf):
    from research.program import eq_data as ED
    d = pd.read_csv(ED.EQ / f"{sym}_FIVE_MINUTE.csv.gz", parse_dates=["time"])
    d = d[(d.time.dt.hour * 60 + d.time.dt.minute >= 555) & (d.time.dt.hour * 60 + d.time.dt.minute < 930)]
    d = d.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    if tf != 5:
        day = d.time.dt.normalize()
        k = ((d.time - day).dt.total_seconds() // 60 - 555) // tf
        d = d.groupby([day, k], sort=True).agg(time=("time", "first"), open=("open", "first"), high=("high", "max"),
                                                low=("low", "min"), close=("close", "last"), volume=("volume", "sum")).reset_index(drop=True)
    day = d.time.dt.normalize()
    first = day != day.shift(1)
    gap = (d.open / d.close.shift(1)).where(first)
    ca = first & ((gap < 0.8) | (gap > 1.25))                     # corporate action / circuit gap -> new segment, day skipped
    d["seg"] = ca.cumsum().values
    f = _finish(d, tf)
    bad_day = f.day.isin(set(f.day[ca.values]))
    end_m = f.end.dt.hour * 60 + f.end.dt.minute
    f["sig_ok"] = (~bad_day.values) & (end_m <= 14 * 60 + 45).values
    f.attrs.update(market="NSE_EQ", name=sym, tf=tf)
    return f


def nse_eq_base5(sym):
    return nse_eq_intraday(sym, 5)


# ── NSE stock futures 1-hour (Angel, 16 months, today's list) ───────────────────────────────────────────────────────
def nse_fut_hourly(sym):
    p = ROOT / "research/data/angel/NFO_STK" / f"{sym}_ONE_HOUR.csv"
    d = pd.read_csv(p, parse_dates=["time"]).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    day = d.time.dt.normalize(); first = day != day.shift(1)
    gap = (d.open / d.close.shift(1)).where(first)
    ca = first & ((gap < 0.8) | (gap > 1.25))
    d["seg"] = ca.cumsum().values
    f = _finish(d, 60)
    f["sig_ok"] = (~f.day.isin(set(f.day[ca.values]))).values & (f.m < 14 * 60).values
    f.attrs.update(market="NSE_FUT", name=sym, tf=60)
    return f
