"""Safety rule for the SELLING bot: never sell INTO a fresh bounce / drop (added 23 Oct 2026 after the Silver 201000 CE
sell at 10:58 came ~2,600 points above the day's low, as a short-covering rally started, and hit its stop).

Bearish view (sell CE) is blocked when, on today's 15-minute candles:
  * price is back ABOVE the day's VWAP, or
  * price is already >= BOUNCE_ATR_X x hourly ATR above the day's low AND rose over the last hour.
Bullish view (sell PE) is the mirror (below VWAP, or >= x ATR below the day's high AND falling over the last hour).
VWAP is skipped when the series has no volume (index spot). Pure function, no API calls.
"""
import numpy as np
import pandas as pd


def check(d15, ltp, bias, atr_x=0.5):
    """d15: today's 15-min candles (time, open, high, low, close, volume). Returns a reason string if blocked, else None."""
    if bias not in ("BULLISH", "BEARISH") or d15 is None or len(d15) < 4 or not ltp:
        return None
    d = d15.reset_index(drop=True)
    pc = d["close"].shift()
    tr = pd.concat([d["high"] - d["low"], (d["high"] - pc).abs(), (d["low"] - pc).abs()], axis=1).max(axis=1)
    atr_h = float(tr.tail(14).mean()) * 2.0                              # ~hourly ATR from 15-min candles
    lo, hi = min(float(d["low"].min()), ltp), max(float(d["high"].max()), ltp)
    ago = float(d["close"].iloc[-5]) if len(d) >= 5 else float(d["open"].iloc[0])
    vol = d["volume"].astype(float)
    vwap = float(((d["high"] + d["low"] + d["close"]) / 3 * vol).sum() / vol.sum()) if vol.sum() > 0 else None
    if bias == "BEARISH":
        if vwap and ltp > vwap:
            return f"price {ltp:,.1f} back above today's VWAP {vwap:,.1f} – not selling CE into a bounce"
        if atr_h > 0 and ltp - lo >= atr_x * atr_h and ltp > ago:
            return f"already {ltp - lo:,.1f} pts off today's low and rising – not selling CE into a bounce"
    else:
        if vwap and ltp < vwap:
            return f"price {ltp:,.1f} back below today's VWAP {vwap:,.1f} – not selling PE into a drop"
        if atr_h > 0 and hi - ltp >= atr_x * atr_h and ltp < ago:
            return f"already {hi - ltp:,.1f} pts off today's high and falling – not selling PE into a drop"
    return None
