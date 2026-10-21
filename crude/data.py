"""Market data for the Crude Oil engine: sessions, contracts, closed candles, 3-hour candles, roll continuity, OI.

Facts verified against real Angel One responses (crude/probe.py, run 21-Oct-2026 21:14 IST):
  * getCandleData serves FIFTEEN_MINUTE and ONE_HOUR directly (bar time = bar START, IST). There is no 3-hour
    interval, so 3-hour candles are built here from completed 1-hour candles.
  * The latest candle returned is the one still FORMING -> only candles whose end time has passed are used.
  * The nearest contract's token returns a vendor-STITCHED history (older bars belong to the previous, expired
    contract). The next contract's token returns its own data. The jump at each switch is measured from the real
    overlap with the next contract (see `continuity`).
  * getOIData for MCX -> AB1012 "Invalid Bad Request": NO historical OI. The FULL quote carries `opnInterest`
    (current OI) and `tradeVolume` (today's cumulative volume). No buy/sell side split of volume exists.
"""
import datetime as dt
import numpy as np
import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, nearest_workday, USMartinLutherKingJr,
                                    USPresidentsDay, GoodFriday, USMemorialDay, USLaborDay, USThanksgivingDay)
from pandas.tseries.offsets import CustomBusinessDay
from crude import config as K


# ─────────────── sessions ───────────────
def _nth_sunday(y, m, n):
    d = pd.Timestamp(y, m, 1)
    d += pd.Timedelta(days=(6 - d.weekday()) % 7)
    return d + pd.Timedelta(weeks=n - 1)


def session_close(day):
    """23:30 IST while the US is on daylight time (2nd Sun Mar – 1st Sun Nov), else 23:55."""
    day = pd.Timestamp(day).normalize()
    us_dst = _nth_sunday(day.year, 3, 2) < day <= _nth_sunday(day.year, 11, 1)
    return day + pd.Timedelta(hours=23, minutes=30 if us_dst else 55)


def hm(day, s):
    h, m = map(int, s.split(":"))
    return pd.Timestamp(day).normalize() + pd.Timedelta(hours=h, minutes=m)


def session_status(now):
    if now.weekday() >= 5:
        return "CLOSED (weekend)"
    o, c = hm(now, K.SESSION_OPEN), session_close(now)
    if now < o:
        return "PRE-OPEN"
    if now > c:
        return "CLOSED (after hours)"
    return "OPEN"


def trading_days_between(a, b):
    return int(np.busday_count(pd.Timestamp(a).date(), pd.Timestamp(b).date()))


# ─────────────── contracts ───────────────
def futures(master, name):
    m = master[(master["name"] == name) & (master["exch_seg"] == "MCX") & (master["instrumenttype"] == "FUTCOM")]
    return m.sort_values("expiry_dt")


def resolve(master, now):
    """Front (nearest live) contract, the contract to trade (front, or next inside the roll window),
    the contract after it (needed to measure roll jumps), and the matching mini contract for paper fills."""
    f = futures(master, K.SIGNAL_NAME)
    f = f[f["expiry_dt"] >= now.normalize()]
    if len(f) < 2:
        raise DataError(f"{K.SIGNAL_NAME}: fewer than 2 live futures in the instrument master")
    front, nxt = f.iloc[0], f.iloc[1]
    days_left = trading_days_between(now.normalize(), front["expiry_dt"])
    rolled = days_left <= K.ROLL_TRADING_DAYS
    sig = nxt if rolled else front
    after = f.iloc[2] if rolled and len(f) > 2 else (nxt if not rolled else None)
    mini = futures(master, K.TRADE_NAME)
    mini = mini[mini["expiry_dt"].dt.to_period("M") == sig["expiry_dt"].to_period("M")]
    out = dict(front=_c(front), signal=_c(sig), after=_c(after) if after is not None else None,
               trade=_c(mini.iloc[0]) if len(mini) else None, rolled=rolled, front_days_left=days_left,
               signal_is_front=not rolled)
    out["signal"]["days_left"] = trading_days_between(now.normalize(), sig["expiry_dt"])
    issues = []
    for k, nm in (("signal", K.SIGNAL_NAME), ("trade", K.TRADE_NAME)):
        c = out[k]
        if c is None:
            issues.append(f"no {nm} contract for {sig['expiry_dt']:%b-%Y}")
            continue
        if c["lotsize"] != K.RS_PER_POINT[nm]:
            issues.append(f"{c['symbol']}: master lot size {c['lotsize']} ≠ configured ₹/pt {K.RS_PER_POINT[nm]}")
        if not c["tick"] or c["tick"] <= 0:
            issues.append(f"{c['symbol']}: tick size missing in master")
    out["issues"] = issues
    return out


def _c(r):
    tick = pd.to_numeric(r.get("tick_size"), errors="coerce")
    return dict(symbol=r["symbol"], token=str(r["token"]), expiry=str(pd.Timestamp(r["expiry_dt"]).date()),
                lotsize=float(r["lotsize"]), tick=None if pd.isna(tick) else float(tick) / 100.0)


class DataError(RuntimeError):
    pass


# ─────────────── candles ───────────────
def floor15(t):
    return pd.Timestamp(t).floor("15min")


def bar_end(t, minutes):
    """End of a candle that starts at t (capped at the session close for the last, shorter candle)."""
    return min(t + pd.Timedelta(minutes=minutes), session_close(t))


def closed(df, minutes, now, grace=K.CLOSE_GRACE_SEC):
    """Keep only candles that had fully closed `grace` seconds before `now` (drops the forming candle)."""
    if df is None or df.empty:
        return df
    ends = df["time"].map(lambda t: bar_end(t, minutes))
    return df[ends + pd.Timedelta(seconds=grace) <= now].reset_index(drop=True)


def htf_closed_by(h1, t_end):
    """Higher-timeframe (1-hour) candles that had CLOSED by t_end (the end of the entry candle) – no look-ahead."""
    if h1 is None or h1.empty:
        return h1
    return h1[h1["time"].map(lambda t: bar_end(t, 60)) <= t_end].reset_index(drop=True)


def three_hour(h1, now=None):
    """3-hour candles from COMPLETED 1-hour candles. Fixed session blocks 09-12, 12-15, 15-18, 18-21, 21-close.
    A block is emitted only when its end time has passed (when `now` is given) and it has at least 2 hourly bars;
    `bars` and `complete` columns record how many hourly candles it contains."""
    if h1 is None or h1.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume", "bars", "complete"])
    starts = [int(s[:2]) for s in K.POSITIONAL_BLOCKS]
    d = h1.copy()
    d["day"] = d["time"].dt.normalize()
    d["blk"] = d["time"].dt.hour.map(lambda h: max([s for s in starts if s <= h], default=starts[0]))
    g = d.groupby(["day", "blk"], sort=True)
    agg = dict(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
               volume=("volume", "sum"), bars=("close", "size"))
    if "offset" in d.columns:
        agg["offset"] = ("offset", "last")
    out = g.agg(**agg).reset_index()
    out["time"] = out["day"] + pd.to_timedelta(out["blk"], unit="h")
    nxt = {s: e for s, e in zip(starts, starts[1:] + [None])}
    out["end"] = [session_close(r.day) if nxt[r.blk] is None else r.day + pd.Timedelta(hours=nxt[r.blk]) for r in out.itertuples()]
    expect = np.array([np.ceil((r.end - r.time).total_seconds() / 3600) for r in out.itertuples()])
    out["complete"] = out["bars"].values >= expect
    if now is not None:
        out = out[out["end"] + pd.Timedelta(seconds=K.CLOSE_GRACE_SEC) <= now]
    out = out[out["bars"] >= 2]
    cols = ["time", "open", "high", "low", "close", "volume", "bars", "complete", "end"] + (["offset"] if "offset" in out else [])
    return out[cols].reset_index(drop=True)


# ─────────────── roll continuity ───────────────
class _NymexHolidays(AbstractHolidayCalendar):
    rules = [Holiday("NewYear", month=1, day=1, observance=nearest_workday), USMartinLutherKingJr, USPresidentsDay,
             GoodFriday, USMemorialDay, Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01",
             observance=nearest_workday), Holiday("July4", month=7, day=4, observance=nearest_workday), USLaborDay,
             USThanksgivingDay, Holiday("Christmas", month=12, day=25, observance=nearest_workday)]


def crude_expiry(year, month):
    """Estimated MCX CRUDEOIL expiry for the contract of (year, month): one business day before the NYMEX WTI
    last trading day (3 US business days before the 25th, or before the last business day preceding the 25th).
    Checked against every listed contract in the instrument master by the tests. Indian holidays are ignored."""
    hol = _NymexHolidays().holidays(pd.Timestamp(year - 1, 12, 1), pd.Timestamp(year + 1, 1, 31))
    bd = CustomBusinessDay(holidays=hol)
    d25 = pd.Timestamp(year, month, 25)
    ref = d25 if bd.is_on_offset(d25) else d25 - bd
    nymex_ltd = ref - 3 * bd
    return (nymex_ltd - pd.offsets.BDay(1)).normalize()


def previous_expiries(expiry, n=2):
    e = pd.Timestamp(expiry)
    out = []
    for k in range(1, n + 1):
        p = (e - pd.DateOffset(months=k))
        out.append(crude_expiry(p.year, p.month))
    return out


def detect_switches(front_h1, next_h1, expiry, months_back=3):
    """Where the stitched front series switched contracts: the first bar AFTER each previous contract's expiry day.
    The jump (old − new) is MEASURED from the real overlap with the next contract's own series:
    diff = next − front changes by exactly (old − new) at the switch. Median of the 3 bars before vs 3 after.
    Returns [(switch_time, old_minus_new, quality)]; quality 'measured' or 'unmeasured' (no overlap data)."""
    out = []
    for pe in previous_expiries(expiry, months_back):
        sw = front_h1[front_h1["time"] >= pe + pd.Timedelta(days=1)]["time"] if front_h1 is not None else pd.Series([], dtype="datetime64[ns]")
        if not len(sw):
            continue
        t = sw.iloc[0]
        step = None
        if next_h1 is not None and not next_h1.empty:
            m = front_h1[["time", "close"]].merge(next_h1[["time", "close"]], on="time", suffixes=("_f", "_n"))
            m["diff"] = m["close_n"] - m["close_f"]
            before, after = m[m["time"] < t].tail(3), m[m["time"] >= t].head(3)
            nv = next_h1.set_index("time")["volume"]
            liquid = len(before) == 3 and len(after) == 3 and (nv.reindex(pd.concat([before.time, after.time])) > 0).all()
            if liquid and before["time"].iloc[-1] >= pe and after["time"].iloc[0] == t:
                step = float(after["diff"].median() - before["diff"].median())
        out.append((t, step if step is not None else 0.0, "measured" if step is not None else "unmeasured"))
    return sorted(out)


def continuity(df, switches, horizon_start=None):
    """Back-adjust a stitched series (Panama): bars before each switch get (new − old) added, so differences inside
    the current contract are untouched and indicators see no artificial jump. Bars older than the earliest
    measured switch are DROPPED (cannot be verified). Adds column `offset`. Prices used for fills are never adjusted."""
    if df is None or df.empty:
        return df
    d = df.copy()
    d["offset"] = 0.0
    good = [(t, s) for t, s, q in switches if q == "measured"]
    weak = [t for t, s, q in switches if q != "measured"]
    for t, old_minus_new in good:
        d.loc[d["time"] < t, "offset"] += -old_minus_new
    for k in ("open", "high", "low", "close"):
        d[k] = d[k] + d["offset"]
    cuts = list(weak)                                     # bars before an unmeasurable switch can't be adjusted
    if good:                                              # ...nor bars before the switch preceding the earliest one
        cuts.append(min(t for t, _ in good) - pd.DateOffset(months=1) + pd.Timedelta(days=7))
    elif horizon_start is not None:
        cuts.append(horizon_start)
    cut = max(cuts) if cuts else None
    if cut is not None:
        d = d[d["time"] >= cut]
    return d.reset_index(drop=True)


# ─────────────── OI from live snapshots ───────────────
def oi_change(snaps, contract, now_snap):
    """Price/OI classification from two REAL snapshots of the same contract 10–40 min apart, same day.
    Returns dict(status, label, d_oi_pct, d_price, gap_min). status: OK / UNAVAILABLE (+reason)."""
    if now_snap is None or now_snap.get("oi") in (None, "", 0) or not isinstance(now_snap.get("oi"), (int, float)):
        return dict(status="UNAVAILABLE", reason="live quote has no OI value")
    lo, hi = K.OI_SNAPSHOT_GAP_MIN
    t_now = pd.Timestamp(now_snap["time"])
    prev = [s for s in snaps if s["contract"] == contract and s.get("oi") not in (None, 0)
            and lo <= (t_now - pd.Timestamp(s["time"])).total_seconds() / 60 <= hi
            and pd.Timestamp(s["time"]).normalize() == t_now.normalize()]
    if not prev:
        return dict(status="UNAVAILABLE", reason=f"no earlier OI snapshot {lo}-{hi} min ago for this contract today")
    p = max(prev, key=lambda s: s["time"])
    d_oi = (now_snap["oi"] - p["oi"]) / p["oi"] * 100
    d_px = now_snap["ltp"] - p["ltp"]
    gap = (t_now - pd.Timestamp(p["time"])).total_seconds() / 60
    if abs(d_oi) < K.OI_MIN_CHANGE_PCT or d_px == 0:
        label = "Flat / no clear OI signal"
    elif d_px > 0:
        label = "Long buildup" if d_oi > 0 else "Short covering"
    else:
        label = "Short buildup" if d_oi > 0 else "Long unwinding"
    return dict(status="OK", label=label, d_oi_pct=round(d_oi, 3), d_price=round(d_px, 2), gap_min=round(gap, 1),
                oi=now_snap["oi"], oi_prev=p["oi"])


def parse_feed_time(s):
    try:
        return pd.Timestamp(dt.datetime.strptime(s, "%d-%b-%Y %H:%M:%S"))
    except Exception:
        return None
