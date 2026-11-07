"""MCXE-003 – daily-bar horizons: BTST / STBT (overnight) and positional, three markets, same detectors as intraday.

Markets / data (DATA_AUDIT.md):
  NSE_EQ   official cash bhavcopy 2005-26, POINT-IN-TIME, corporate-action adjusted (eq_bhav.adjusted_cached); events only
           on days the stock is in the liquid universe (60-day median traded value >= ₹25 cr, price >= ₹50, >= 250
           sessions). BUY only (cash STBT / overnight cash shorts are not executable -> blocked).
  NSE_FUT  official F&O bhavcopy 2018-26, POINT-IN-TIME (nse_fut_pit), continuous front month per symbol: nearest
           expiry, rolled 2 sessions before expiry, RATIO BACK-ADJUSTED (fut_frames); no holding period crosses a roll.
  MCX      Angel daily front-month stitch 2005-26, ratio back-adjusted at switch days (mcx_frames); no signal on a switch
           day, no holding period across one. Both sides.
  (7-Nov fix, before any daily result was used: the first version reset every pattern at each monthly roll, which left
   ~20-bar segments in which no daily swing / S-R / 20-bar pattern could form.)
Measures per event (ATR(14) daily units, side-signed):
  btst     close[i] -> close[i+1]     (entry in the pre-close minutes at ~ the close, exit next session) PRIMARY overnight
  gap      close[i] -> open[i+1]      (exit at the next open)
  pos5     open[i+1] -> close[i+5]    PRIMARY positional ; pos10 / pos20 descriptive
  mfe/mae  10 sessions from open[i+1]
  Measures are NaN if the horizon leaves the segment, or (cash) an adjustment factor != 1 occurs inside it.
Control: NSE_EQ / NSE_FUT = cross-sectional mean of the same measure over all eligible instruments that day (market-day
matched); MCX = same commodity, same research period mean (long-run drift; Addendum C). excess = side * (measure - control).
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
    """-> list of (key, frame[time open high low close volume seg], eligible mask, bad mask = adjustment day)"""
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
        f = d[["time", "open", "high", "low", "close", "volume"]].copy(); f["seg"] = 0
        out.append((k, f, liq, d.factor.values != 1.0))
    return out


def _back_adjust(f, ratio_at):
    """ratio_at[k] = new/old price ratio applied at roll day k (1 elsewhere): all bars BEFORE k are multiplied by the
    product of later ratios, so returns inside each contract are unchanged and the roll basis is removed."""
    r = np.asarray(ratio_at, float)
    cum = np.r_[np.cumprod(r[::-1])[::-1][1:], 1.0]
    for c in ("open", "high", "low", "close"):
        f[c] = f[c].values * cum
    return f


def fut_frames():
    """continuous front month per symbol from the point-in-time F&O bhavcopy; nearest expiry, rolled to the next expiry
    when <= 2 sessions remain; ratio back-adjusted with both contracts' closes on the day BEFORE the switch (fallback:
    the switch-day open / previous close); roll days flagged (no holding period may cross them). A > 20 % unexplained gap
    (stock split: futures are not adjusted) starts a new segment."""
    from research.adapters import nse_stkfut_pit as NF
    D = NF.load(kinds=("STK",))
    D = D[(D.contracts > 0) & (D.close > 0)]
    out = []
    for sym, g in D.groupby("symbol"):
        days = np.sort(g.date.unique())
        if len(days) < 120:
            continue
        px = g.set_index(["date", "expiry"]).close
        rows = []
        for d, gd in g.groupby("date"):
            ex = np.sort(gd.expiry.values[gd.expiry.values >= d])
            if not len(ex):
                continue
            e0 = ex[0]
            later = days[(days > d) & (days <= e0)]
            if len(later) <= 2 and len(ex) > 1:
                e0 = ex[1]
            r = gd[gd.expiry == e0].iloc[0]
            rows.append((d, e0, r.open, r.high, r.low, r.close, r.contracts))
        f = pd.DataFrame(rows, columns=["time", "expiry", "open", "high", "low", "close", "volume"])
        if len(f) < 120:
            continue
        roll = np.array(f.expiry != f.expiry.shift(1), dtype=bool); roll[0] = False
        ratio = np.ones(len(f))
        for k in np.where(roll)[0]:
            dp, eo, en = f.time.iat[k - 1], f.expiry.iat[k - 1], f.expiry.iat[k]
            a, b = px.get((dp, en)), px.get((dp, eo))
            ratio[k] = (a / b) if (a is not None and b is not None and b > 0) else f.open.iat[k] / f.close.iat[k - 1]
        f = _back_adjust(f, ratio)
        gap = (f.open / f.close.shift(1)).values
        split = ((gap < 0.8) | (gap > 1.25)) & ~roll
        f["seg"] = np.cumsum(split)
        out.append((sym, f[["time", "open", "high", "low", "close", "volume", "seg"]], ~roll, roll | split))
    return out


def mcx_frames():
    """Angel daily front-month stitch, ratio back-adjusted at each switch day using the switch-day open / previous close
    (only one contract price exists per day in this file, so the switch day's own overnight gap is removed with the roll
    basis – one day per month, documented); switch days are flagged: no signal on them, no holding period across them."""
    from research.program import liqtl_mcx5 as LM
    out = []
    for nm in ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]:
        d = LM.load(nm, "ONE_DAY")
        sw = d.switch.fillna(False).astype(bool).values
        ratio = np.where(sw, d.open.values / d.close.shift(1).values, 1.0); ratio[0] = 1.0
        f = _back_adjust(d[["time", "open", "high", "low", "close", "volume"]].copy(), np.nan_to_num(ratio, nan=1.0))
        f["seg"] = 0
        out.append((nm, f, ~sw, sw))
    return out


def run_one(args):
    market, key, d, elig, bad = args
    f = finish(d.copy())
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
        for k, (E, S) in enumerate(P.imap_unordered(run_one, [(market, k_, d, e, b) for k_, d, e, b in frames], chunksize=4), 1):
            parts.append(E)
            sums = S if sums is None else sums.add(S, fill_value=0)
            if k % 200 == 0:
                print(k, f"{time.time() - t0:.0f}s", flush=True)
    E = pd.concat(parts, ignore_index=True)
    E["side"] = E.side.astype(np.int64)
    if market == "MCX":
        q = np.where(E.day < V0, "DEV", np.where(E.day < O0, "VALID", "OOS"))
        # MCX control: same commodity & quarter mean over ALL non-roll bars (not only event bars)
        ctl = {}
        for nm, d, elig, bad in frames:
            f = finish(d.copy())
            tt = f.time[elig]
            Mb = measures(f, bad)[elig].assign(q=np.where(tt < V0, "DEV", np.where(tt < O0, "VALID", "OOS")))
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
