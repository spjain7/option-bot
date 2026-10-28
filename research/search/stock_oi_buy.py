"""STOCK-OI-BUY-001 (28-Oct-2026): improving the live stock-futures OI BUY rule (alerts/stocks.py, CFG + evaluate).

EXPLORATORY: every date here (Nov-2023 → Oct-2026) has been examined before (LIVE-AUDIT-001, OOS-VALIDATE-001). Nothing
in this file is independent validation. Prospective evidence starts with forward paper calls from 29-Oct-2026.

Pre-declared candidates (fixed before running; not tuned afterwards)
  E1  OI band            doi ≥ 2 % (baseline) · 2–3 % · 2–4 % · 2–5 %   (bounds inclusive)
  E2  breakout extension ext = (close − previous 20-day high) / ATR14 at the signal close; max ext 0.25 · 0.5 · 0.75 · 1.0
  E3  entry              baseline: next session open
                         confirmation: buy-stop at the signal-day high + 1 tick, valid for the next session only; fill =
                         max(bar open, trigger) on the first hourly bar that trades through it, plus 0.05 % extra stop-order
                         slippage; not reached = missed trade. If the fill bar's low also reaches the stop, the trade is
                         counted as stopped (order inside an hourly bar is unknown).
Live execution kept for every variant: stop 2 ATR from the entry, trailing 3 ATR on daily closes (moved only when it
gains > 0.25 ATR, as live), max 40 sessions, exit at the close of the contract's expiry day, no signal inside the
rollover window (3 sessions before .. 2 after expiry), gap through the stop fills at the open.

Data corrections (both affect the live data too – see the report):
  * corporate actions (splits / bonus / demergers) were not adjusted in the stored futures prices: prices before the
    ex-date are multiplied by the ratio, volume and OI divided by it; the ex-date's OI change is invalid.
  * OI ticks: Angel daily OI has isolated bad values (−99 % then +7,000 %). An OI change is valid only if both days are
    > 0, neither is a corporate-action day, and each day's OI is within ×0.5–×2 of the median of the 5 sessions before it
    (past data only). Invalid / missing OI = no confirmation (never treated as a pass).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa

CANON = (0.1, 0.2, 0.25, 1 / 3, 0.5, 2 / 3)            # common split / bonus ratios
TICK = 0.05
STOP_SLIP = 0.0005
OI_BANDS = {"E1-base ≥2%": (0.02, None), "E1 2–3%": (0.02, 0.03), "E1 2–4%": (0.02, 0.04), "E1 2–5%": (0.02, 0.05)}
EXT_MAX = (0.25, 0.5, 0.75, 1.0)
CFG = dict(N=20, vol_x=1.5, oi_up=0.02, ema=200, stop_atr=2.0, trail_atr=3.0, trail_step=0.25, max_days=40)


# ─────────────── data ───────────────
def corporate_actions(d, lo=0.72, hi=1.35):
    """-> list of (day, factor). factor = price ratio new/old (canonical when within 3 %). Daily bars (open vs previous close)."""
    r = (d["open"] / d["close"].shift(1)).values
    out = []
    for i in np.flatnonzero((r < lo) | (r > hi)):
        f = r[i]
        near = [c for c in CANON if abs(f / c - 1) < 0.03]
        out.append((pd.Timestamp(d["time"].iat[i]).normalize(), near[0] if near else float(f)))
    return out


def adjust(df, events, cols=("open", "high", "low", "close")):
    """Back-adjust a price frame (hourly or daily) for corporate actions: rows before each ex-date × factor, volume ÷ factor."""
    df = df.copy()
    for c in (*cols, "volume"):
        if c in df:
            df[c] = df[c].astype(float)
    day = df["time"].dt.normalize()
    for ex, f in events:
        m = day < ex
        for c in cols:
            df.loc[m, c] = df.loc[m, c] * f
        if "volume" in df:
            df.loc[m, "volume"] = df.loc[m, "volume"] / f
    return df


def oi_series(oi_raw, days, events):
    """Daily OI aligned to the price days (OI of day t = end of day t, same day as the completed daily candle).
    -> (oi aligned, doi with NaN where invalid, reasons Series)."""
    o = oi_raw.copy()
    o["day"] = pd.to_datetime(o["time"].astype(str).str[:10])
    o = o.groupby("day")["oi"].last().astype(float)
    for ex, f in events:                                   # OI in shares: more shares after a split
        o[o.index < ex] = o[o.index < ex] / f
    a = o.reindex(days).values
    n = len(a)
    doi = np.full(n, np.nan)
    why = np.array(["ok"] * n, dtype=object)
    ev_days = {e for e, _ in events}
    med = pd.Series(a).rolling(5, min_periods=3).median().shift(1).values      # median of the 5 sessions BEFORE t
    for t in range(n):
        if t == 0 or not (np.isfinite(a[t]) and np.isfinite(a[t - 1])):
            why[t] = "missing"; continue
        if a[t] <= 0 or a[t - 1] <= 0:
            why[t] = "zero"; continue
        if pd.Timestamp(days[t]) in ev_days:
            why[t] = "corporate action"; continue
        bad = False
        for k in (t, t - 1):
            if np.isfinite(med[k]) and med[k] > 0 and not (0.5 <= a[k] / med[k] <= 2.0):
                bad = True
        if bad:
            why[t] = "outlier"; continue
        doi[t] = a[t] / a[t - 1] - 1
    return a, doi, pd.Series(why)


def features(d, doi):
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"].astype(float)
    f = pd.DataFrame(dict(time=d["time"], open=d["open"], high=h, low=l, close=c))
    f["hh"] = h.shift(1).rolling(CFG["N"]).max()
    f["ll"] = l.shift(1).rolling(CFG["N"]).min()
    f["va"] = v.rolling(20).mean().shift(1)
    f["volx"] = v / f["va"]
    f["ema"] = I.ema(c, CFG["ema"])
    f["atr"] = I.atr(d, 14)
    f["dp"] = c.pct_change()
    f["doi"] = doi
    f["ext"] = (c - f["hh"]) / f["atr"]                    # known at the signal close – no look-ahead
    return f


def base_buy(f, rollover):
    """Exact live BUY rule (alerts/stocks.evaluate) with invalid OI = no signal."""
    ok = f["doi"].notna() & ~rollover
    return (ok & (f["close"] > f["hh"]) & (f["volx"] > CFG["vol_x"]) & (f["dp"] > 0) & (f["doi"] >= CFG["oi_up"])
            & (f["close"] > f["ema"])).fillna(False).values


def base_sell(f, rollover):
    ok = f["doi"].notna() & ~rollover
    return (ok & (f["close"] < f["ll"]) & (f["volx"] > CFG["vol_x"]) & (f["dp"] < 0) & (f["doi"] >= CFG["oi_up"])
            & (f["close"] < f["ema"])).fillna(False).values


def oi_band(f, lo, hi):
    x = f["doi"]
    return ((x >= lo) & ((x <= hi) if hi is not None else True)).fillna(False).values


def ext_cap(f, mx, side=1):
    return ((side * (f["close"] - (f["hh"] if side > 0 else f["ll"])) / f["atr"]) <= mx).fillna(False).values


# ─────────────── execution ───────────────
def open_zone_ok(f, i, side=1, max_atr=0.5):
    """Live pending check (alerts/stocks.validate_pending): the next session's open must be within ±0.5 ATR of the signal
    close, otherwise the call is cancelled. Uses the signal-day ATR (known before the open)."""
    if i + 1 >= len(f):
        return False
    mv = side * (f["open"].iat[i + 1] - f["close"].iat[i]) / f["atr"].iat[i]
    return bool(-max_atr <= mv <= max_atr)


def last_before_window(roll):
    """Exit flag one session before the rollover window starts (the OOS-VALIDATE-001 exit model, not live)."""
    r = np.asarray(roll, bool)
    start = np.zeros(len(r), bool); start[1:] = r[1:] & ~r[:-1]
    out = np.zeros(len(r), bool); out[:-1] = start[1:]
    return out


def confirm_fill(bars, trigger, side=1):
    """First hourly bar of the next session trading through the trigger. -> (bar index, fill price) or (None, None)."""
    for k, b in enumerate(bars.itertuples()):
        if (b.high >= trigger) if side > 0 else (b.low <= trigger):
            px = max(b.open, trigger) if side > 0 else min(b.open, trigger)
            return k, px * (1 + side * STOP_SLIP)
    return None, None


def simulate(f, i, last_day, hourly, cost_fn, mode="open", side=1):
    """One trade from signal day i. -> dict or dict(missed=True). last_day[j] = True on the contract's expiry session."""
    o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
    if i + 1 >= len(c) or not a[i] > 0:
        return None
    j = i + 1
    R = CFG["stop_atr"] * a[i]
    if mode == "open":
        e0 = o[j]; st = e0 - side * R; start_intraday = None
    else:
        trig = (h[i] + TICK) if side > 0 else (l[i] - TICK)
        day = pd.Timestamp(f["time"].iat[j]).normalize()
        bars = hourly.get(day)
        if bars is None or bars.empty:
            return dict(missed=True, why="no hourly data")
        k, e0 = confirm_fill(bars, trig, side)
        if k is None:
            return dict(missed=True, why="trigger not reached")
        st = e0 - side * R
        start_intraday = (bars, k)
    best = e0; px = why = None; held = 0
    while j < len(c):
        if start_intraday is not None and j == i + 1:      # entry day, hourly order after the fill
            bars, k = start_intraday
            for kk, b in enumerate(bars.iloc[k:].itertuples()):
                if kk > 0 and ((b.open <= st) if side > 0 else (b.open >= st)):
                    px, why = b.open, "stop-gap"; break
                if (b.low <= st) if side > 0 else (b.high >= st):
                    px, why = st, "stop"; break
            if px is not None:
                break
        else:
            if j > i + 1 and ((o[j] <= st) if side > 0 else (o[j] >= st)):
                px, why = o[j], "stop-gap"; break
            if (l[j] <= st) if side > 0 else (h[j] >= st):
                px, why = st, "stop"; break
        held += 1
        if last_day[j]:
            px, why = c[j], "expiry"; break
        if held >= CFG["max_days"]:
            px, why = c[j], "time"; break
        best = max(best, c[j]) if side > 0 else min(best, c[j])
        ns = best - side * CFG["trail_atr"] * a[j]
        if side * (ns - st) > CFG["trail_step"] * a[j]:
            st = ns
        j += 1
    if px is None:
        px, why = c[-1], "open-at-end"
    risk = side * (e0 - (e0 - side * R))
    cst = cost_fn(e0)
    return dict(time=f["time"].iat[i], entry=e0, exit=px, why=why, held=j - i, risk=risk, cost_r=cst / risk,
                r1=(side * (px - e0) - cst) / risk, r2=(side * (px - e0) - 2 * cst) / risk, missed=False,
                gap_atr=(o[i + 1] - c[i]) / a[i])
