"""MCXE-003 – daily-bar horizons: BTST / STBT (overnight) and positional, three markets, same detectors as intraday.

Markets / data (DATA_AUDIT.md):
  NSE_EQ   official cash bhavcopy 2005-26, POINT-IN-TIME, corporate-action adjusted (eq_bhav.adjusted_cached); events only
           on days the stock is in the liquid universe (60-day median traded value >= ₹25 cr, price >= ₹50, >= 250
           sessions). BUY only (cash STBT / overnight cash shorts are not executable -> blocked).
  NSE_FUT  official F&O bhavcopy 2018-26, POINT-IN-TIME (nse_fut_pit), continuous front month built per symbol:
           nearest expiry, rolled to the next expiry 2 sessions before expiry; every roll starts a new segment (no level,
           swing or holding period crosses it). Both sides.
  MCX      Angel daily front-month stitch 2005-26, roll ('switch') days start a new segment. Both sides.
Measures per event (ATR(14) daily units, side-signed):
  btst     close[i] -> close[i+1]     (entry in the pre-close minutes at ~ the close, exit next session) PRIMARY overnight
  gap      close[i] -> open[i+1]      (exit at the next open)
  pos5     open[i+1] -> close[i+5]    PRIMARY positional ; pos10 / pos20 descriptive
  mfe/mae  10 sessions from open[i+1]
  Measures are NaN if the horizon leaves the segment, or (cash) an adjustment factor != 1 occurs inside it.
Control: NSE_EQ / NSE_FUT = cross-sectional mean of the same measure over all eligible instruments that day (market-day
matched); MCX = same commodity, same calendar quarter mean (drift). excess = side * (measure - control).
Costs (round trip, ATR units): NSE_EQ delivery 0.393 %; NSE_FUT fees + 0.05 %/side; MCX fees + 1.5 ticks/side.
Periods: DEV < 2023-01-01 <= VALID < 2025-01-01 <= OOS.
python research/mcxe003/daily.py nse_eq|nse_fut|mcx
"""
import sys
import time
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa: E402
from research.mcxe003 import (swing_detection as SWD, trendlines as TL, market_structure as MS, liquidity_sweeps as SWP,  # noqa: E402
                              support_resistance as SR, chart_patterns as CP, candlestick_patterns as CDL,
                              flow_patterns as FL, events as EV, cost_model as CM)
from research.mcxe003.run_discovery import BRK_NAMES  # noqa: E402

OUT = ROOT / "research/mcxe003/results"
V0, O0 = pd.Timestamp("2023-01-01"), pd.Timestamp("2025-01-01")
MEAS = ["btst", "gap", "pos5", "pos10", "pos20"]
METHODS = ("f3", "z3")


def measures(f, bad=None):
    o, h, l, c, a, seg = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr", "seg"))
    n = len(c); idx = np.arange(n)
    badc = np.zeros(n + 1) if bad is None else np.r_[0, np.cumsum(bad)]

    def ok(hz):
        j = np.minimum(idx + hz, n - 1)
        good = (idx + hz < n) & (seg[j] == seg)
        if bad is not None:
            good &= (badc[j + 1] - badc[idx + 1]) == 0                    # no adjustment in (i, i+hz]
        return j, good
    M = {}
    j, g = ok(1)
    M["btst"] = np.where(g, (c[j] - c) / a, np.nan); M["gap"] = np.where(g, (o[j] - c) / a, np.nan)
    ent = np.where(g, o[j], np.nan)
    for hz in (5, 10, 20):
        jj, gg = ok(hz)
        M[f"pos{hz}"] = np.where(gg & g, (c[jj] - ent) / a, np.nan)
    hi = pd.Series(h[::-1]).rolling(10, min_periods=1).max().values[::-1]
    lo = pd.Series(l[::-1]).rolling(10, min_periods=1).min().values[::-1]
    jj, gg = ok(10)
    M["mfe"] = np.where(gg & g, (hi[j] - ent) / a, np.nan); M["mae"] = np.where(gg & g, (lo[j] - ent) / a, np.nan)
    return pd.DataFrame(M)


def events(f):
    parts = [CDL.detect(f).assign(sw="-"), FL.detect(f, intraday=False).assign(sw="-")]
    for mth in METHODS:
        sw = SWD.swings(f, mth)
        for mod in (TL, MS, SR, CP):
            parts.append(mod.detect(f, sw).assign(sw=mth))
        parts.append(SWP.detect(f, sw, intraday=False).assign(sw=mth))
    E = pd.concat(parts, ignore_index=True)
    E["side"] = E.side.astype(np.int64)
    brk = E[E.name.str.startswith(BRK_NAMES) & ~E.name.str.endswith("_RET")]
    G = [EV.fails(g, f).assign(sw=s) for s, g in brk.groupby("sw")]
    return pd.concat([E] + G, ignore_index=True)


def finish(f):
    f = f.reset_index(drop=True)
    f["atr"] = I.atr(f, 14).values
    f["day"] = f.time
    return f


# ── per-market frame builders ───────────────────────────────────────────────────────────────────────────────────────
def eq_frames():
    from research.program import eq_bhav as EB, eq_data as ED
    A = EB.adjusted_cached()
    out = []
    for k, d in A.items():
        if len(d) < 300:
            continue
        val = pd.Series(d.value.values.astype(float))
        med = val.rolling(60, min_periods=40).median().shift(1)
        liq = ((med >= ED.MIN_TURNOVER) & (pd.Series(d.close.values).shift(1) >= ED.MIN_PRICE) & (np.arange(len(d)) >= 250)).values
        if not liq.any():
            continue
        out.append((k, d, liq))
    return out


def fut_frames():
    from research.adapters import nse_stkfut_pit as NF
    D = NF.load(kinds=("STK",))
    D = D[(D.contracts > 0) & (D.close > 0)]
    out = []
    for sym, g in D.groupby("symbol"):
        g = g.sort_values(["date", "expiry"])
        days = np.sort(g.date.unique())
        if len(days) < 120:
            continue
        pos = {d: i for i, d in enumerate(days)}
        exps = np.sort(g.expiry.unique())
        rows = []
        cur = None
        for d, gd in g.groupby("date"):
            ex = gd.expiry.values
            # front = nearest expiry >= d ; roll to the next when <= 2 sessions remain (expiry day index - today index <= 2)
            cand = np.sort(ex[ex >= d])
            if not len(cand):
                continue
            e0 = cand[0]
            di = pos[d]
            later = days[(days > d) & (days <= e0)]
            if len(later) <= 2 and len(cand) > 1:
                e0 = cand[1]
            r = gd[gd.expiry == e0].iloc[0]
            rows.append((d, e0, r.open, r.high, r.low, r.close, r.contracts))
        f = pd.DataFrame(rows, columns=["time", "expiry", "open", "high", "low", "close", "volume"])
        if len(f) < 120:
            continue
        gap = f.open / f.close.shift(1)
        f["seg"] = ((f.expiry != f.expiry.shift(1)) | (gap < 0.8) | (gap > 1.25)).cumsum()
        out.append((sym, f, np.ones(len(f), bool)))
    return out


def mcx_frames():
    from research.program import liqtl_mcx5 as LM
    out = []
    for nm in ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]:
        d = LM.load(nm, "ONE_DAY")
        d["seg"] = d.switch.fillna(False).astype(bool).cumsum()
        out.append((nm, d, ~d.switch.fillna(False).astype(bool).values))
    return out


def run_one(args):
    market, key, d, elig = args
    f = finish(d[["time", "open", "high", "low", "close", "volume", "seg"]].copy()) if "seg" in d else None
    if f is None:
        f = d[["time", "open", "high", "low", "close", "volume"]].copy()
        fac = d.factor.values
        f["seg"] = 0
        f = finish(f)
        bad = fac != 1.0
    else:
        bad = None
    f.attrs.update(market=market, name=key)
    M = measures(f, bad)
    E = events(f)
    E["i"] = E.i.astype(np.int64); E["side"] = E.side.astype(np.int64)
    E = E[elig[E.i.values]].reset_index(drop=True)
    if market == "NSE_EQ":
        E = E[E.side == 1].reset_index(drop=True)
    R = M.iloc[E.i.values].reset_index(drop=True)
    px = f.close.values[E.i.values]
    if market == "MCX":
        cost = np.array([CM.cost_points("MCX", key, p) for p in px])
    else:
        cost = CM.cost_points(market, key, px, kind="delivery")
    E = pd.concat([E, R], axis=1)
    E["cost_atr"] = cost / f.atr.values[E.i.values]
    E["day"] = f.time.values[E.i.values]
    E["inst"] = key
    # bar-level sums for the control (eligible bars only)
    Mb = M[elig].assign(day=f.time.values[elig])
    S = Mb.groupby("day")[MEAS].agg(["sum", "count"])
    E = E.drop(columns=["i"])
    for col in E.select_dtypes("float64").columns:
        E[col] = E[col].astype("float32")
    return E, S


def main(which):
    t0 = time.time()
    market = {"nse_eq": "NSE_EQ", "nse_fut": "NSE_FUT", "mcx": "MCX"}[which]
    frames = {"NSE_EQ": eq_frames, "NSE_FUT": fut_frames, "MCX": mcx_frames}[market]()
    print(market, "instruments", len(frames), f"{time.time() - t0:.0f}s", flush=True)
    parts, sums = [], None
    with Pool(2) as P:
        for k, (E, S) in enumerate(P.imap_unordered(run_one, [(market, k_, d, e) for k_, d, e in frames], chunksize=4), 1):
            parts.append(E)
            sums = S if sums is None else sums.add(S, fill_value=0)
            if k % 200 == 0:
                print(k, f"{time.time() - t0:.0f}s", flush=True)
    E = pd.concat(parts, ignore_index=True)
    E["side"] = E.side.astype(np.int64)
    if market == "MCX":
        q = pd.PeriodIndex(E.day, freq="Q").astype(str)
        # MCX control: same commodity & quarter mean over ALL non-roll bars (not only event bars)
        ctl = {}
        for nm, d, elig in frames:
            f = finish(d[["time", "open", "high", "low", "close", "volume", "seg"]].copy())
            Mb = measures(f)[elig].assign(q=pd.PeriodIndex(f.time[elig], freq="Q").astype(str).values)
            ctl[nm] = Mb.groupby("q")[MEAS].mean()
        for m in MEAS:
            E["ctl_" + m] = [ctl[i].at[qq, m] if qq in ctl[i].index else np.nan for i, qq in zip(E.inst, q)]
    else:
        for m in MEAS:
            mean = sums[(m, "sum")] / sums[(m, "count")].replace(0, np.nan)
            E["ctl_" + m] = E.day.map(mean).values
    for m in MEAS:
        E[m] = E[m] * E.side
        E["x_" + m] = E[m] - E.side * E["ctl_" + m]
        E = E.drop(columns="ctl_" + m)
    sd = E.side.values
    mfe = np.where(sd > 0, E.mfe, -E.mae); mae = np.where(sd > 0, E.mae, -E.mfe)
    E["mfe"], E["mae"] = mfe, mae
    E["period"] = np.where(E.day < V0, "DEV", np.where(E.day < O0, "VALID", "OOS"))
    E["market"] = market
    for c in ("fam", "name", "sw", "period", "inst", "market"):
        E[c] = E[c].astype("category")
    d = OUT / "events" / "daily"; d.mkdir(parents=True, exist_ok=True)
    E.to_parquet(d / f"{market}.parquet", index=False)
    print(market, "events", len(E), f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main((sys.argv[1:] or ["mcx"])[0])
