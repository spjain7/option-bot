"""MCXE-007 daily frames (in-window only), cached. MCX: front-stitched 5-minute bars → daily (MCXE-005 mcx_positional 1440).
Stock futures: MCXE-005 fut_daily (point-in-time FUTSTK, all symbols incl. expired contracts, ratio back-adjusted, rolls
flagged). Index futures: the same builder on FUTIDX rows. Adds raw front-contract close (for rupee accounting), the 1-lot
size (current Angel scrip master – approximate for past dates) and NIFTY benchmark series."""
import json
import pickle
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe005 import frames as FR  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402

CACHE = ROOT / "research/mcxe007/cache"
WKEY = {"MCX": "MCX", "STK": "NSE_FUT", "IDX": "NSE_FUT"}


def _lots():
    m = json.load(open(ROOT / "research/data/ref/angel_master.json"))
    out = {}
    for r in m:
        if r.get("exch_seg") == "NFO" and r.get("instrumenttype") in ("FUTSTK", "FUTIDX"):
            out.setdefault(r["name"], int(float(r["lotsize"])))
    return out


def _nse(kinds):
    from research.adapters import nse_stkfut_pit as NF
    from research.mcxe003 import daily as DLY
    w = W.get("NSE_FUT")
    orig = NF.load
    raw = orig(start=str(w["start"].date()), kinds=kinds)
    raw = raw[(raw.date >= w["start"]) & (raw.date <= w["reference"])]
    NF.load = lambda kinds=None: raw
    try:
        fr = DLY.fut_frames()
    finally:
        NF.load = orig
    lots = _lots()
    out = []
    for sym, f, elig, bad in fr:
        f = f.copy()
        g = raw[raw.symbol == sym]
        fe = FR._front_expiry(g)
        f["expiry"] = f.time.map(fe)
        px = g.set_index(["date", "expiry"])
        f["raw_close"] = [px.close.get((t, e), np.nan) for t, e in zip(f.time, f.expiry)]
        oi = px.oi
        f["oi"] = [oi.get((t, e), np.nan) for t, e in zip(f.time, f.expiry)]
        same = f.expiry.eq(f.expiry.shift(1))
        f["doi"] = np.where(same, f.oi / f.oi.shift(1) - 1, np.nan)
        f = FR._finish_daily(f)
        f["roll"] = bad; f["sig_ok"] = elig
        f.attrs.update(market="NSE_FUT", kind=kinds[0], name=sym, tf=1440, wkey="NSE_FUT", lot=lots.get(sym))
        out.append(f)
    return out


def _mcx():
    from research.program import mcx_disc as MD
    out = []
    for n in FR.MCX7:
        f = FR.mcx_positional(n, 1440, FR.mcx_base(n))
        f["raw_close"] = f.close
        f.attrs.update(market="MCX", kind="MCX", wkey="MCX", mult=MD.REG[n]["mult"])
        out.append(f)
    return out


def frames(kind):
    """kind: MCX | STK | IDX"""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"daily_{kind}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    fs = _mcx() if kind == "MCX" else _nse((kind,))
    p.write_bytes(pickle.dumps(fs))
    return fs


def nifty():
    """NIFTY index-futures daily frame (benchmark for market trend / relative strength), by date."""
    f = [x for x in frames("IDX") if x.attrs["name"] == "NIFTY"][0]
    c = f.set_index(f.time.dt.normalize()).close.astype(float)
    e20, e50 = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    return pd.DataFrame(dict(close=c, trend=np.where((e20 > e50) & (c > e20), 1, np.where((e20 < e50) & (c < e20), -1, 0)),
                             ret20=c / c.shift(20) - 1))
