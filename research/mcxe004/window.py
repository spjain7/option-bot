"""MCXE-004 1-year window enforcement. Every MCXE-004 script must load data through clip(): it drops every row older than
the market's window start (windows.json) and raises if a caller asks for an earlier date. Indicator warm-up is NOT allowed
to use older bars either: the first bars of the window are warm-up and produce no signals (WARMUP_BARS).
"""
import json
from pathlib import Path
import pandas as pd

W = json.loads((Path(__file__).resolve().parent / "windows.json").read_text())
# one reference per market (primary dataset): MCX 5-min, NSE cash bhavcopy / 5-min, NSE F&O bhavcopy
PRIMARY = {"MCX": "Angel front-month FIVE_MINUTE", "NSE_EQ": "official cash bhavcopy (point-in-time)",
           "NSE_EQ_INTRADAY": "Angel 5-min (today's 218 liquid names)", "NSE_FUT": "official F&O bhavcopy (point-in-time)",
           "NSE_FUT_INTRADAY": "Angel 1-hour (today's list)"}
WARMUP_BARS = 60


def get(market):
    name = PRIMARY[market]
    r = next(x for x in W if x["dataset"] == name)
    return {k: pd.Timestamp(r[k]) for k in ("start", "valid_from", "oos_from", "reference")}


def clip(df, market, col="time"):
    w = get(market)
    end = w["reference"] + pd.Timedelta(days=1)
    out = df[(df[col] >= w["start"]) & (df[col] < end)].reset_index(drop=True)
    out.attrs["window"] = {k: str(v.date()) for k, v in w.items()}
    return out


def period(ts, market):
    """DEV / VALID / OOS label for each timestamp (positional, never index-aligned). Raises on any pre-window date.
    (7-Nov fix: the first version built a pandas Series and used .mask with the caller's Series, which aligned on the
    caller's index; with a non-0..n-1 index the labels were wrong. Caught by tests/test_mcxe004.test_window_no_leakage.)"""
    import numpy as np
    w = get(market); t = np.asarray(pd.to_datetime(pd.Series(ts)).values)
    if (t < np.datetime64(w["start"])).any():
        raise ValueError("date before the 1-year window start – forbidden by the MCXE-004 rule")
    return np.where(t < np.datetime64(w["valid_from"]), "DEV", np.where(t < np.datetime64(w["oos_from"]), "VALID", "OOS"))
