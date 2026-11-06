"""MCX GOLD / SILVER intraday DAY-TREND CONTINUATION – SHADOW MODE (logged and tracked, never sent). Research MCXD-001/002
(exp/strategy-program-001, research/program/mcx_disc.py + mcx_dtc.py), 6-Nov-2026.

Rule: at the 13:00 and 17:00 checkpoints (the 15-minute candle that closes then), if
  * the 60-minute trend agrees (EMA20 > EMA50 and close > EMA50 on completed hourly candles; mirror for SELL),
  * price is beyond today's session VWAP, and
  * price is beyond today's 09:00 open by >= 0.3 x daily ATR(14, previous sessions),
then follow the move: entry at the current price, stop 0.5 x daily ATR, hold to the 23:00 square-off. BUY and SELL.
Evidence (5-min front-month data 2023-26, realistic MCX costs, 2 x stress): 542 trades, +0.18R per trade (+0.15R at 2 x
costs), DEV 2025-11…06 +0.13R, VALID 2026-07…11 +0.26R, older 2023-25 +0.19R, every year positive; 54 / 54 neighbouring
parameter sets positive in the older history. Does NOT transfer to CRUDEOIL / COPPER (≈ 0).
STATUS: SHADOW – the owner's rule: experimental strategies are never sent to Telegram before live shadow evidence.
Live differences vs research: VWAP from 15-minute candles (research: 5-minute), entry at the scan's live price.
"""
import numpy as np
import pandas as pd
from crude import indicators as I

NAMES = ("GOLD", "SILVER")
CHECKPOINTS = (13 * 60, 17 * 60)
K_OPEN, M_STOP = 0.3, 0.5
SQUARE_OFF = 23 * 60
LIVE = False                       # shadow only
VERSION = "mcx-dtc-0.1 (MCXD-002, shadow)"


def daily_atr(dd):
    """dd: completed daily candles BEFORE today (time, open, high, low, close)."""
    if dd is None or len(dd) < 15:
        return None
    h, l, c = dd["high"].values, dd["low"].values, dd["close"].values
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    return float(np.mean(tr[-14:]))


def trend60(h1, upto):
    """+1 / -1 / 0 from completed hourly candles that ended at or before `upto`."""
    if h1 is None or len(h1) < 60:
        return 0
    x = h1[pd.to_datetime(h1["time"]) + pd.Timedelta(minutes=60) <= upto]
    if len(x) < 60:
        return 0
    c = x["close"].astype(float)
    e20, e50 = c.ewm(span=20, adjust=False).mean().iat[-1], c.ewm(span=50, adjust=False).mean().iat[-1]
    if e20 > e50 and c.iat[-1] > e50:
        return 1
    if e20 < e50 and c.iat[-1] < e50:
        return -1
    return 0


def evaluate(c15, h1, dd, now):
    """-> dict(side, checkpoint, close, vwap, day_open, atr_d, stop_dist, why) or dict(side=None, why=...)."""
    if c15 is None or not len(c15):
        return dict(side=None, why="no 15m candles")
    t = pd.to_datetime(c15["time"])
    day = pd.Timestamp(now).normalize()
    today = c15[t.dt.normalize() == day]
    if today.empty:
        return dict(side=None, why="no candles today")
    last_t = pd.Timestamp(today["time"].iloc[-1])
    end_m = last_t.hour * 60 + last_t.minute + 15
    if end_m not in CHECKPOINTS:
        return dict(side=None, why="not a checkpoint candle")
    tp = (today["high"] + today["low"] + today["close"]) / 3
    v = today["volume"].astype(float)
    vwap = float((tp * v).sum() / v.sum()) if v.sum() > 0 else np.nan
    day_open = float(today["open"].iloc[0])
    close = float(today["close"].iloc[-1])
    a = daily_atr(dd)
    if not a or not vwap == vwap:
        return dict(side=None, why="ATR / VWAP unavailable")
    tr = trend60(h1, last_t + pd.Timedelta(minutes=15))
    for s in (1, -1):
        if tr == s and s * (close - vwap) > 0 and s * (close - day_open) >= K_OPEN * a:
            return dict(side="BUY" if s > 0 else "SELL", checkpoint=f"{end_m // 60}:{end_m % 60:02d}", close=close, vwap=vwap,
                        day_open=day_open, atr_d=a, stop_dist=M_STOP * a, trend=tr,
                        why=f"60m trend {'up' if s > 0 else 'down'}, price {'above' if s > 0 else 'below'} VWAP {vwap:.1f} and "
                            f"{abs(close - day_open) / a:.2f} x daily ATR from the open")
    return dict(side=None, why=f"conditions not met (trend {tr}, close {close:.1f}, VWAP {vwap:.1f}, open {day_open:.1f})")


def store(state):
    return state.setdefault("mcxdtc", dict(open=[], closed=[], seen=[]))


def run(state, msgs, name, c, c15, h1, dd, q, now):
    """Shadow: record a signal at a checkpoint, never send. Returns the evaluation dict."""
    from alerts import funnel as FN
    st = store(state)
    sig = evaluate(c15, h1, dd, now)
    if not sig.get("side"):
        return sig
    key = f"{name}|{pd.Timestamp(now).date()}|{sig['checkpoint']}"
    if key in st["seen"]:
        return dict(sig, note="already recorded")
    st["seen"] = (st["seen"] + [key])[-400:]
    FN.note(state, "MCX_DTC (shadow)", "signal", key=key, now=now)
    ltp = float((q or {}).get("ltp") or 0)
    if not ltp:
        FN.note(state, "MCX_DTC (shadow)", "rejected", "no live price", key=key, now=now)
        return dict(sig, note="no live price")
    s = 1 if sig["side"] == "BUY" else -1
    st["open"].append(dict(name=name, token=str(c["token"]), side=sig["side"], entry=ltp, stop=ltp - s * sig["stop_dist"],
                           risk=sig["stop_dist"], opened=str(now), day=str(pd.Timestamp(now).date()), key=key, why=sig["why"],
                           version=VERSION))
    FN.note(state, "MCX_DTC (shadow)", "shadow", key=key, now=now)
    print(f"[mcx-dtc] {name} {sig['side']} logged only (shadow): entry {ltp} stop {ltp - s * sig['stop_dist']:.1f} · {sig['why']}")
    return dict(sig, note="shadow recorded")


def track(state, name, q, now):
    """Every scan: stop on the live price, square-off at the first scan at / after 23:00 (or on a later day)."""
    st = store(state)
    ltp = float((q or {}).get("ltp") or 0)
    keep = []
    for r in st["open"]:
        if r["name"] != name:
            keep.append(r); continue
        s = 1 if r["side"] == "BUY" else -1
        hm = now.hour * 60 + now.minute
        why = px = None
        if ltp and s * (ltp - r["stop"]) <= 0:
            why, px = "stop", r["stop"]
        elif str(pd.Timestamp(now).date()) != r["day"] or hm >= SQUARE_OFF:
            why, px = "square-off", ltp or None
        if why and px:
            r.update(exit=px, exit_reason=why, closed=str(now), result_R=round(s * (px - r["entry"]) / r["risk"], 3))
            st["closed"] = (st["closed"] + [r])[-300:]
        else:
            keep.append(r)
    st["open"] = keep
