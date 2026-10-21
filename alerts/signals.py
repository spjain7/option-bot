"""RSI-extreme REVERSAL alerts with candlestick confirmation. Pure functions on CLOSED candles. Alert-only (no orders).

Rule (same on 15-min, 1-hour and positional candles):
  SELL alert: RSI(14) > 75 on the signal candle or one of the 2 before it (overbought)
              AND the signal candle is a bearish reversal pattern
              (bearish engulfing, shooting star, dark cloud cover, evening star).
  BUY alert : RSI(14) < 25 on the signal candle or one of the 2 before it (oversold)
              AND the signal candle is a bullish reversal pattern
              (bullish engulfing, hammer, piercing line, morning star).
  WATCH     : RSI first crosses beyond 75 / 25 without a reversal candle yet -> "watch" message so a setup is
              never missed silently; the BUY/SELL alert follows only when a reversal candle confirms.
Plan: entry = signal close; SL beyond the pattern's extreme + 0.2 ATR (at least 1 ATR); T1 = 1R, T2 = 2R.
These rules have NOT been shown to be profitable (see crude/BACKTEST.md style tests) – alerts carry that warning.
"""
import numpy as np
import pandas as pd
from crude import indicators as I

RSI_SELL, RSI_BUY, LOOKBACK = 75.0, 25.0, 3
MIN_RANGE_ATR = 0.6          # pattern candle must be a real candle, not noise
SL_BUF_ATR, SL_MIN_ATR, SL_MAX_ATR = 0.2, 1.0, 3.0


def _parts(c):
    o, h, l, cl = c.open, c.high, c.low, c.close
    body = abs(cl - o)
    rng = max(h - l, 1e-9)
    return o, h, l, cl, body, rng, h - max(o, cl), min(o, cl) - l


def patterns(df, atr):
    """Reversal patterns on the LAST candle of df (needs ≥ 3 candles). Returns (bullish list, bearish list)."""
    c, p, pp = df.iloc[-1], df.iloc[-2], df.iloc[-3]
    o, h, l, cl, body, rng, up, lo = _parts(c)
    po, ph, pl, pc, pbody, prng, _, _ = _parts(p)
    qo, qh, ql, qc, qbody, qrng, _, _ = _parts(pp)
    bull, bear = [], []
    if rng < MIN_RANGE_ATR * atr:
        return bull, bear
    green, red, pgreen, pred = cl > o, cl < o, pc > po, pc < po
    # engulfing: current body covers the previous opposite-coloured body
    if green and pred and cl >= po and o <= pc and body > pbody:
        bull.append("Bullish engulfing")
    if red and pgreen and cl <= po and o >= pc and body > pbody:
        bear.append("Bearish engulfing")
    # hammer / shooting star: long rejection wick ≥ 2× body, small opposite wick, body in the outer third
    if lo >= 2 * max(body, 0.05 * rng) and up <= 0.35 * rng and min(o, cl) >= l + 0.6 * rng:
        bull.append("Hammer (long lower wick – buyers rejected lower prices)")
    if up >= 2 * max(body, 0.05 * rng) and lo <= 0.35 * rng and max(o, cl) <= h - 0.6 * rng:
        bear.append("Shooting star (long upper wick – sellers rejected higher prices)")
    # piercing / dark cloud: after a big opposite candle, opens beyond it and closes past its midpoint
    if pred and pbody >= 0.5 * prng and green and o <= pc and cl > (po + pc) / 2 and cl < po:
        bull.append("Piercing line")
    if pgreen and pbody >= 0.5 * prng and red and o >= pc and cl < (po + pc) / 2 and cl > po:
        bear.append("Dark cloud cover")
    # morning / evening star: big candle, small-body candle, strong opposite candle closing past first's midpoint
    if qc < qo and qbody >= 0.5 * qrng and pbody <= 0.35 * prng and green and cl > (qo + qc) / 2:
        bull.append("Morning star (3-candle reversal)")
    if qc > qo and qbody >= 0.5 * qrng and pbody <= 0.35 * prng and red and cl < (qo + qc) / 2:
        bear.append("Evening star (3-candle reversal)")
    return bull, bear


def levels(df, h1, price, atr):
    """Support / resistance from REAL completed candles:
       previous session high/low/close + classic pivots (P, R1, R2, S1, S2) from the 1-hour candles,
       and confirmed swing highs/lows (3 candles each side) of this timeframe. Nearest 2 each side of price."""
    lv = []
    if h1 is not None and len(h1):
        days = h1["time"].dt.normalize()
        prev = h1[days < days.iloc[-1]]
        if len(prev):
            pd_ = prev[prev["time"].dt.normalize() == prev["time"].dt.normalize().iloc[-1]]
            H, L, C = float(pd_["high"].max()), float(pd_["low"].min()), float(pd_["close"].iloc[-1])
            P = (H + L + C) / 3
            lv += [(H, "prev-day high"), (L, "prev-day low"), (P, "pivot P"), (2 * P - L, "pivot R1"), (2 * P - H, "pivot S1"),
                   (P + (H - L), "pivot R2"), (P - (H - L), "pivot S2")]
    hi, lo = I.pivots(df.iloc[-150:].reset_index(drop=True), 3)
    lv += [(float(v), "swing high") for _, v in hi[-6:]] + [(float(v), "swing low") for _, v in lo[-6:]]
    gap = 0.15 * atr
    sup = sorted([x for x in lv if x[0] < price - gap], key=lambda x: -x[0])
    res = sorted([x for x in lv if x[0] > price + gap], key=lambda x: x[0])
    def dedupe(xs):
        out = []
        for v, n in xs:
            if not out or abs(v - out[-1][0]) > 0.3 * atr:
                out.append((round(v, 2), n))
        return out[:2]
    return dict(support=dedupe(sup), resistance=dedupe(res))


def context(df):
    c = df["close"]
    e20, e50 = I.ema(c, 20).iloc[-1], I.ema(c, 50).iloc[-1]
    e200 = I.ema(c, 200).iloc[-1] if len(df) >= 250 else None
    adx = I.adx(df).iloc[-1]
    x = c.iloc[-1]
    trend = "UP" if x > e20 > e50 else "DOWN" if x < e20 < e50 else "SIDEWAYS"
    return dict(trend=trend, ema20=float(e20), ema50=float(e50), ema200=None if e200 is None or pd.isna(e200) else float(e200),
                adx=None if pd.isna(adx) else float(adx))


def evaluate(df, label, h1=None):
    """df: closed candles, oldest first (≥ 60). Returns dict(kind=BUY|SELL|WATCH_BUY|WATCH_SELL|None, ...)."""
    if df is None or len(df) < 60:
        return dict(kind=None, why=f"only {0 if df is None else len(df)} candles")
    r = I.rsi(df["close"], 14)
    atr = float(I.atr(df, 14).iloc[-1])
    rr = r.iloc[-LOOKBACK:]
    bull, bear = patterns(df, atr)
    x = df.iloc[-1]
    base = dict(tf=label, candle=str(x.time), close=float(x.close), rsi=round(float(r.iloc[-1]), 1),
                rsi_min=round(float(rr.min()), 1), rsi_max=round(float(rr.max()), 1), atr=atr, **context(df))
    vr, _ = I.slot_volume_ratio(df) if (df["volume"] > 0).mean() > 0.9 else (pd.Series([np.nan]), None)
    base["vol_x"] = None if pd.isna(vr.iloc[-1]) else round(float(vr.iloc[-1]), 2)
    base["candle_volume"] = float(x.volume)
    base["levels"] = levels(df, h1, float(x.close), atr)
    base["last_high"], base["last_low"] = float(x.high), float(x.low)
    w3 = df.iloc[-3:]
    base["swing_low3"], base["swing_high3"] = float(w3["low"].min()), float(w3["high"].max())
    for side, extreme, pats in (("SELL", rr.max() > RSI_SELL, bear), ("BUY", rr.min() < RSI_BUY, bull)):
        if extreme and pats:
            s = 1 if side == "BUY" else -1
            w = df.iloc[-3:]
            ext = w["low"].min() if s > 0 else w["high"].max()
            stop = ext - s * SL_BUF_ATR * atr
            dist = max(s * (x.close - stop), SL_MIN_ATR * atr)
            if dist > SL_MAX_ATR * atr:
                return dict(base, kind=None, why=f"{side} pattern but stop {dist / atr:.1f} ATR away – too wide")
            return dict(base, kind=side, patterns=pats, entry=float(x.close), sl=round(float(x.close - s * dist), 2),
                        t1=round(float(x.close + s * dist), 2), t2=round(float(x.close + 2 * s * dist), 2), risk=round(float(dist), 2))
    if r.iloc[-1] > RSI_SELL and r.iloc[-2] <= RSI_SELL:
        return dict(base, kind="WATCH_SELL", why="RSI crossed above 75 – waiting for a bearish reversal candle")
    if r.iloc[-1] < RSI_BUY and r.iloc[-2] >= RSI_BUY:
        return dict(base, kind="WATCH_BUY", why="RSI crossed below 25 – waiting for a bullish reversal candle")
    return dict(base, kind=None, why="no RSI extreme with a reversal candle")
