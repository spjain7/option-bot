"""MCXE-005 in-window frames. Every loader CLIPS the raw data to the approved MCXE-004 window BEFORE any indicator is
computed (no older bar is ever seen by an indicator). Columns: time, end, open, high, low, close, volume, day, m, seg,
atr, sig_ok, (intraday) vwap, dlast, datr, pdh, pdl, dopen; daily frames: roll (bool, contract switch / corporate action
on that day -> no holding across it), expiry (futures).
Cells: mcx_intraday(name, tf in 15/30) · mcx_positional(name, tf in 60/240/1440) · eq_intraday(sym, tf 15/60) ·
fut_intraday(sym) (60) · fut_daily() · eq_daily()"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe003 import bars as B  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402
from crude import indicators as I  # noqa: E402

MCX7 = B.MCX7


def _clip(d, key):
    w = W.get(key)
    return d[(d.time >= w["start"]) & (d.time < w["reference"] + pd.Timedelta(days=1))].reset_index(drop=True)


def _resample(d, tf, open_min):
    day = d.time.dt.normalize()
    k = ((d.time - day).dt.total_seconds() // 60 - open_min) // tf
    agg = dict(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
               volume=("volume", "sum"))
    if "switch" in d:
        agg["switch"] = ("switch", "max")
    return d.groupby([day, k], sort=True).agg(**agg).reset_index(drop=True)


def mcx_base(name):
    from research.program import liqtl_mcx5 as LM
    d = LM.load(name, "FIVE_MINUTE")
    d = _clip(d, "MCX")
    d["switch"] = d.switch.fillna(False).astype(bool)
    return d


def mcx_intraday(name, tf, base=None):
    d = base if base is not None else mcx_base(name)
    f = _resample(d, tf, 540)
    day = f.time.dt.normalize()
    swd = f.groupby(day).switch.transform("max").astype(bool)
    f["seg"] = (swd & (day != day.shift(1))).cumsum().values
    f = B._finish(f, tf)
    f["sig_ok"] = (~swd.values) & ((f.end.dt.hour * 60 + f.end.dt.minute) <= 22 * 60).values
    f["roll"] = swd.values
    f.attrs.update(market="MCX", name=name, tf=tf, cell="MCX intraday")
    return f


def mcx_positional(name, tf, base=None):
    d = base if base is not None else mcx_base(name)
    if tf == 1440:
        g = d.groupby(d.time.dt.normalize())
        f = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                  volume=("volume", "sum"), switch=("switch", "max")).reset_index().rename(columns={"time": "time"})
        f = f.rename(columns={f.columns[0]: "time"})
    else:
        f = _resample(d, tf, 540)
    day = f.time.dt.normalize()
    swd = f.groupby(day).switch.transform("max").astype(bool)
    f["seg"] = (swd & (day != day.shift(1))).cumsum().values
    f = B._finish(f, tf if tf < 1440 else 1440, intraday=tf < 1440) if tf < 1440 else _finish_daily(f)
    f["roll"] = swd.values
    f["sig_ok"] = ~f.roll.values
    f.attrs.update(market="MCX", name=name, tf=tf, cell="MCX positional")
    return f


def _finish_daily(f):
    f = f.reset_index(drop=True)
    f["end"] = f.time; f["day"] = f.time.dt.normalize(); f["m"] = 0
    f["atr"] = I.atr(f, 14).values
    if "seg" not in f:
        f["seg"] = 0
    return f


def eq_intraday(sym, tf):
    from research.program import eq_data as ED
    d = pd.read_csv(ED.EQ / f"{sym}_FIVE_MINUTE.csv.gz", parse_dates=["time"])
    d = _clip(d, "NSE_EQ_INTRADAY")
    mm = d.time.dt.hour * 60 + d.time.dt.minute
    d = d[(mm >= 555) & (mm < 930)].drop_duplicates("time").sort_values("time").reset_index(drop=True)
    if tf != 5:
        d = _resample(d, tf, 555)
    day = d.time.dt.normalize(); first = day != day.shift(1)
    gap = (d.open / d.close.shift(1)).where(first)
    ca = first & ((gap < 0.8) | (gap > 1.25))
    d["seg"] = ca.cumsum().values
    f = B._finish(d, tf)
    bad = f.day.isin(set(f.day[ca.values]))
    f["sig_ok"] = (~bad.values) & ((f.end.dt.hour * 60 + f.end.dt.minute) <= 14 * 60 + 45).values
    f["roll"] = bad.values
    f.attrs.update(market="NSE_EQ", name=sym, tf=tf, cell="NSE cash intraday")
    return f


def fut_intraday(sym):
    p = ROOT / "research/data/angel/NFO_STK" / f"{sym}_ONE_HOUR.csv"
    d = pd.read_csv(p, parse_dates=["time"]).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    d = _clip(d, "NSE_FUT_INTRADAY")
    if len(d) < 200:
        return None
    day = d.time.dt.normalize(); first = day != day.shift(1)
    gap = (d.open / d.close.shift(1)).where(first)
    ca = first & ((gap < 0.8) | (gap > 1.25))
    d["seg"] = ca.cumsum().values
    f = B._finish(d, 60)
    bad = f.day.isin(set(f.day[ca.values]))
    f["sig_ok"] = (~bad.values) & (f.m < 14 * 60).values
    f["roll"] = bad.values
    f.attrs.update(market="NSE_FUT", name=sym, tf=60, cell="NSE futures intraday")
    return f


def fut_daily():
    """point-in-time stock futures, front month, ratio back-adjusted at rolls – using ONLY in-window bhavcopy rows."""
    from research.adapters import nse_stkfut_pit as NF
    from research.mcxe003 import daily as DLY
    w = W.get("NSE_FUT")
    orig = NF.load
    NF.load = lambda kinds=("STK",): (lambda X: X[(X.date >= w["start"]) & (X.date <= w["reference"])])(orig(start=str(w["start"].date()), kinds=kinds))
    try:
        fr = DLY.fut_frames()
    finally:
        NF.load = orig
    # OI per day of the front contract (for S4) – re-read in-window rows
    D = orig(start=str(w["start"].date()), kinds=("STK",))
    D = D[(D.date >= w["start"]) & (D.date <= w["reference"])]
    out = []
    for sym, f, elig, bad in fr:
        f = f.copy()
        g = D[D.symbol == sym][["date", "expiry", "oi", "contracts"]]
        # keep the OI of the contract actually used that day (front by the frame's own roll rule)
        fr_exp = _front_expiry(D[D.symbol == sym])
        f["expiry"] = f.time.map(fr_exp)
        oi = g.set_index(["date", "expiry"]).oi
        f["oi"] = [oi.get((t, e), np.nan) for t, e in zip(f.time, f.expiry)]
        prev_same = f.expiry.eq(f.expiry.shift(1))
        f["doi"] = np.where(prev_same, f.oi / f.oi.shift(1) - 1, np.nan)
        f = _finish_daily(f)
        f["roll"] = bad; f["sig_ok"] = elig
        f.attrs.update(market="NSE_FUT", name=sym, tf=1440, cell="NSE futures daily")
        out.append(f)
    return out


def _front_expiry(g):
    days = np.sort(g.date.unique()); res = {}
    for d, gd in g.groupby("date"):
        ex = np.sort(gd.expiry.values[gd.expiry.values >= d])
        if not len(ex):
            continue
        e0 = ex[0]
        later = days[(days > d) & (days <= e0)]
        if len(later) <= 2 and len(ex) > 1:
            e0 = ex[1]
        res[d] = e0
    return res


def eq_daily():
    """point-in-time cash bhavcopy (exchange-adjusted), clipped to the window; liquid universe computed in-window."""
    from research.program import eq_bhav as EB, eq_data as ED
    w = W.get("NSE_EQ")
    A = EB.adjusted_cached()
    out = []
    for k, d in A.items():
        d = d[(d.time >= w["start"]) & (d.time <= w["reference"])].reset_index(drop=True)
        if len(d) < 120:
            continue
        val = pd.Series(d.value.values.astype(float))
        med = val.rolling(60, min_periods=40).median().shift(1)
        liq = ((med >= ED.MIN_TURNOVER) & (pd.Series(d.close.values).shift(1) >= ED.MIN_PRICE)).values
        if not liq.any():
            continue
        f = d[["time", "open", "high", "low", "close", "volume"]].copy()
        f["seg"] = 0
        f = _finish_daily(f)
        f["roll"] = (d.factor.values != 1.0)
        f["sig_ok"] = liq & ~f.roll.values
        f.attrs.update(market="NSE_EQ", name=str(d.symbol.iat[-1]), tf=1440, cell="NSE cash daily")
        out.append(f)
    return out
