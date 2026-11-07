"""MCXE-003 stage 1 – event study over all families, intraday markets (pre-registered in PREREGISTRATION.md).

python research/mcxe003/run_discovery.py mcx        MCX 7 commodities x 15/30/60 min, swing methods f2 f3 f5 z15 z3
python research/mcxe003/run_discovery.py nse_eq     NSE cash 218 stocks x 15/60 min, swing methods f3 z3
python research/mcxe003/run_discovery.py nse_fut    NSE stock futures 1-hour (16 months), swing methods f3 z3
Writes results/events/<market>/<inst>_<tf>.parquet: one row per event with side-signed forward measures, excess vs the time-of-day x
quarter matched control, cost in ATR, context tags, geometry, period (DEV / VALID / OOS).
"""
import sys
import time
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe003 import (bars as B, swing_detection as SWD, trendlines as TL, market_structure as MS,  # noqa: E402
                              liquidity_sweeps as SWP, support_resistance as SR, chart_patterns as CP,
                              candlestick_patterns as CDL, flow_patterns as FL, events as EV, controls as CT,
                              pattern_context as PC, cost_model as CM)

OUT = ROOT / "research/mcxe003/results"
PERIODS = {"MCX": ("2025-04-01", "2026-01-01"), "NSE_EQ": ("2025-07-01", "2026-01-01"), "NSE_FUT": ("2024-07-01", "2025-07-01")}
KEEP = ["side", "fam", "name", "sw", "level", "inv", "g1", "g2", "g3", "fe1", "fe3", "fe6", "fe12", "feEOD", "fd6",
        "x_fe1", "x_fe3", "x_fe6", "x_fe12", "x_feEOD", "x_fd6", "mfe", "mae", "c_trend", "c_ema", "c_dtrend", "c_vwap",
        "c_adx", "c_atr", "c_relvol", "c_sess", "c_imp", "c_day", "cost_atr", "time", "day", "period", "market", "inst", "tf"]
BRK_NAMES = ("TL_BRK", "SR_BRK", "BOS", "CHOCH", "BRKN", "DTOP", "DBOT", "HS", "IHS", "TRI_", "WEDGE_", "RECT", "FLAG",
             "PENNANT", "NBAR_BRK", "ORB", "ATRC_BRK", "RANGE2TREND", "INSIDE_BRK", "NR4_BRK", "NR7_BRK", "COMPRESS_BRK")


def all_events(f, methods):
    parts = []
    E = CDL.detect(f); E["sw"] = "-"; parts.append(E)
    E = FL.detect(f, intraday=True); E["sw"] = "-"; parts.append(E)
    for mth in methods:
        sw = SWD.swings(f, mth)
        for mod in (TL, MS, SR, CP):
            E = mod.detect(f, sw); E["sw"] = mth; parts.append(E)
        E = SWP.detect(f, sw, intraday=True); E["sw"] = mth; parts.append(E)
    E = pd.concat(parts, ignore_index=True)
    brk = E[E.name.str.startswith(BRK_NAMES) & ~E.name.str.endswith("_RET")]
    G = []
    for sw_, g in brk.groupby("sw"):
        x = EV.fails(g, f); x["sw"] = sw_; G.append(x)
    if G:
        E = pd.concat([E] + G, ignore_index=True)
    return E


def run_one(job):
    market, name, tf, methods = job
    t0 = time.time()
    try:
        if market == "MCX":
            f = B.mcx_intraday(name, tf)
        elif market == "NSE_EQ":
            f = B.nse_eq_intraday(name, tf)
        else:
            f = B.nse_fut_hourly(name)
    except Exception as e:                                      # noqa: BLE001
        return None, f"{market} {name} {tf}: load error {e}"
    if len(f) < 500:
        return None, f"{market} {name} {tf}: too short"
    E = all_events(f, methods)
    E = E[f.sig_ok.values[E.i.values]].reset_index(drop=True)
    F = CT.forward(f)
    key, G = CT.control_means(f, F)
    M = CT.event_measures(f, E, F, key, G)
    X = PC.bar_context(f, intraday=True)
    Cx = PC.tag(E, X)
    px = f.close.values[E.i.values]
    cost = np.array([CM.cost_points(market, name, p) for p in px]) if market == "MCX" else CM.cost_points(market, name, px)
    E = pd.concat([E, M, Cx], axis=1)
    E["cost_atr"] = cost / f.atr.values[E.i.values]
    E["time"] = f.end.values[E.i.values]
    E["day"] = f.day.values[E.i.values]
    v0, o0 = PERIODS[market]
    E["period"] = np.where(E.day < pd.Timestamp(v0), "DEV", np.where(E.day < pd.Timestamp(o0), "VALID", "OOS"))
    E["market"] = market; E["inst"] = name; E["tf"] = tf
    E = E[KEEP]
    for col in E.select_dtypes("float64").columns:
        E[col] = E[col].astype("float32")
    for col in [c for c in E.columns if c.startswith("c_")] + ["side"]:
        E[col] = E[col].astype("int8")
    d = OUT / "events" / market; d.mkdir(parents=True, exist_ok=True)
    E.to_parquet(d / f"{name}_{tf}.parquet", index=False)
    return len(E), f"{market} {name} {tf}: {len(f)} bars, {len(E)} events, {time.time() - t0:.0f}s"


def main(which):
    OUT.mkdir(parents=True, exist_ok=True)
    if which == "mcx":
        jobs = [("MCX", n, tf, ("f2", "f3", "f5", "z15", "z3")) for n in B.MCX7 for tf in (15, 30, 60)]
        tag = "mcx"
    elif which == "nse_eq":
        jobs = [("NSE_EQ", s, tf, ("f3", "z3")) for s in B.nse_eq_symbols() for tf in (15, 60)]
        tag = "nse_eq"
    else:
        syms = sorted(p.name.split("_ONE_HOUR")[0] for p in (ROOT / "research/data/angel/NFO_STK").glob("*_ONE_HOUR.csv"))
        jobs = [("NSE_FUT", s, 60, ("f3", "z3")) for s in syms]
        tag = "nse_fut"
    tot = 0
    with Pool(2) as P:
        for k, msg in P.imap_unordered(run_one, jobs):
            print(msg, flush=True)
            tot += k or 0
    print(tag, "events", tot, "->", OUT / "events")


if __name__ == "__main__":
    main((sys.argv[1:] or ["mcx"])[0])
