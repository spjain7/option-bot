"""MCX round-trip cost as a FRACTION of price, per bar (applied at the entry bar's raw price).
Fees (MCX non-agri futures): brokerage Rs 20/order x 2, exchange transaction charge 0.0021 % (both legs), SEBI Rs 10/crore,
GST 18 % on (brokerage + exchange + SEBI), stamp duty 0.002 % buy side, CTT 0.01 % sell side from 1-Jul-2013 (0 before).
Spread + slippage per side: config slip_ticks_per_side = max(1.5 ticks, live median half-spread + 0.5 tick), measured from the
MCX best-5 sample (data_quality). Contract multipliers / ticks from config (same values as research/instruments.py).
Historical exchange-fee revisions (small, < 0.001 % of notional) are not modelled; CTT history is."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

CFG = json.loads((Path(__file__).resolve().parents[1] / "config/config.json").read_text())


def spec(name):
    return CFG["contracts"][name]


def cost_pts(name, price, when=None):
    s = spec(name); m = s["mult"]; f = CFG["fees"]
    tb = ts = np.asarray(price, float) * m
    exch = (tb + ts) * f["exch"]; sebi = (tb + ts) * f["sebi"]; brk = 2 * f["brokerage"]
    ctt = ts * f["ctt_sell"]
    if when is not None:
        ctt = np.where(pd.to_datetime(when) >= pd.Timestamp(f["ctt_from"]), ctt, 0.0)
    fees = brk + exch + sebi + f["gst"] * (brk + exch + sebi) + ctt + tb * f["stamp_buy"]
    return fees / m + 2 * s["slip_ticks_per_side"] * s["tick"]


def cost_frac(name, price, when=None):
    p = np.asarray(price, float)
    return cost_pts(name, p, when) / np.where(p > 0, p, np.nan)
