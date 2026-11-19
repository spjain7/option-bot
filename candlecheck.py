"""Shared candle validation (4-Nov-2026, P1) – used by angel.Angel.candles, so every engine gets checked bars.

Removed from the series (cannot be trusted for any calculation):
  * rows with a missing / unparseable time, duplicate times (the last copy is kept), non-finite prices,
    OHLC that is inconsistent (high < max(open, close), low > min(open, close), low > high, price <= 0),
  * bars that START in the future (time > reference clock + 60 s).
Flagged only (kept, reported – a strategy that needs them checks the report or the values itself):
  * missing / negative volume (negative volume is set to NaN, never to 0), all-zero volume,
  * gaps larger than 3 intervals inside one session day, out-of-order rows (sorted back),
  * price jumps: |close / previous close − 1| > JUMP_PCT % (rolls and corporate actions are handled elsewhere).
Returns (clean_df, report). report["ok"] is False only when nothing usable is left.
"""
import math
import numpy as np
import pandas as pd

JUMP_PCT = 8.0
FUTURE_SLACK_S = 60


def validate(df, now=None, interval_min=None, label=""):
    rep = dict(label=label, rows_in=0, removed={}, flags={}, ok=True)
    if df is None:
        rep.update(ok=False, note="no data"); return None, rep
    d = df.copy()
    rep["rows_in"] = len(d)
    if len(d) == 0:
        rep.update(ok=False, note="empty"); return d, rep

    def drop(mask, why):
        n = int(mask.sum())
        if n:
            rep["removed"][why] = rep["removed"].get(why, 0) + n
        return d[~mask]

    d["time"] = pd.to_datetime(d["time"], errors="coerce")
    d = drop(d["time"].isna(), "bad time")
    if not d["time"].is_monotonic_increasing:
        rep["flags"]["out of order (sorted)"] = 1
        d = d.sort_values("time", kind="stable")
    d = drop(d["time"].duplicated(keep="last"), "duplicate time")
    px = d[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    d[["open", "high", "low", "close"]] = px
    d = drop(~np.isfinite(px.loc[d.index].to_numpy(float)).all(axis=1), "non-finite price")
    o, h, l, c = (d[k] for k in ("open", "high", "low", "close"))
    tol = 1e-9 * c.abs().clip(lower=1)
    bad = (h + tol < np.maximum(o, c)) | (l - tol > np.minimum(o, c)) | (l > h + tol) | (c <= 0) | (l <= 0)
    d = drop(bad, "inconsistent OHLC")
    if now is not None and len(d):
        ref = pd.Timestamp(now)
        if ref.tzinfo is not None:
            ref = ref.tz_convert("Asia/Kolkata").tz_localize(None)
        tt = d["time"]
        if getattr(tt.dt, "tz", None) is not None:
            tt = tt.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
        d = drop(tt > ref + pd.Timedelta(seconds=FUTURE_SLACK_S), "bar starts in the future")
    if "volume" in d:
        v = pd.to_numeric(d["volume"], errors="coerce")
        neg = v < 0
        if neg.any():
            rep["flags"]["negative volume (set to missing)"] = int(neg.sum())
            v = v.mask(neg)
        d["volume"] = v
        if v.isna().any():
            rep["flags"]["missing volume"] = int(v.isna().sum())
        if len(v) and (v.fillna(0) == 0).all():
            rep["flags"]["volume all zero / missing"] = len(v)
    if interval_min and len(d) > 1:
        gap = d["time"].diff().dt.total_seconds() / 60
        same_day = d["time"].dt.normalize() == d["time"].dt.normalize().shift()
        n_gap = int(((gap > 3 * interval_min) & same_day).sum())
        if n_gap:
            rep["flags"]["intraday gaps > 3 intervals"] = n_gap
    if len(d) > 1:
        r = (d["close"] / d["close"].shift() - 1).abs() * 100
        n_j = int((r > JUMP_PCT).sum())
        if n_j:
            rep["flags"][f"price jumps > {JUMP_PCT:g} %"] = n_j
    d = d.reset_index(drop=True)
    rep["rows_out"] = len(d)
    if len(d) == 0:
        rep["ok"] = False
    return d, rep


def summary(rep):
    """One log line, or '' when nothing was removed or flagged."""
    if not rep or (not rep.get("removed") and not rep.get("flags")):
        return ""
    parts = [f"removed {k}: {v}" for k, v in rep["removed"].items()] + [f"{k}: {v}" for k, v in rep["flags"].items()]
    return f"[dq] {rep.get('label', '')} " + " · ".join(parts)
