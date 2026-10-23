"""Pure signal rules for the Telegram trading-call engine (no I/O, easy to test).

INTRADAY (1-hour candles, closed bars only) – same rules as the earlier MCX hourly engine plus the user's RSI rule:
  BUY : close > EMA20 > EMA50, close > EMA200, ADX >= 20, close breaks the previous 5-hour high,
        RSI between 55 and 70 (RSI > 70 blocks a fresh BUY), volume >= 1.2x the same hour's average over 10 sessions (when volume exists)
  SELL: mirror (RSI between 30 and 45; RSI < 30 blocks a fresh SELL)
  Plan: entry = live price; SL beyond the 5-hour swing, kept between 1 and 2 ATR; T1 = 1R (book half, SL to cost),
        T2 = 2R; square off at the session cut-off.
POSITIONAL (daily candles, closed bars only):
  BUY : close > highest high of the previous 55 days AND close > 200-day average; RSI > 70 blocks
  SELL: close < lowest low of the previous 55 days AND close < 200-day average;  RSI < 30 blocks
  Plan: entry at the next session open if it is not more than 0.5 ATR beyond the signal close; SL = 2 x ATR(20);
        exit when the close crosses the opposite 20-day channel (next open).
A blocked signal is never reversed into the opposite direction.
"""
import numpy as np
import pandas as pd

INTRA = dict(ema=(20, 50, 200), min_adx=20, brk=5, rsi_buy=(55, 70), rsi_sell=(30, 45), vol_x=1.2,
             sl_atr=(1.0, 2.0), t1_r=1.0, t2_r=2.0, spike_atr=2.5, chase_atr=0.5)
POS = dict(entry_n=55, exit_n=20, trend_n=200, atr_n=20, stop_atr=2.0, rsi_max_buy=70, rsi_min_sell=30,
           chase_atr=0.5, watch_atr=0.5)


def _rsi(c, n=14):
    d = c.diff()
    u = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    v = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + u / v.replace(0, 1e-9))


def _tr(d):
    return pd.concat([d.high - d.low, (d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()], axis=1).max(axis=1)


def _adx(d, n=14):
    up, dn = d.high.diff(), -d.low.diff()
    pdm, ndm = up.where((up > dn) & (up > 0), 0.0), dn.where((dn > up) & (dn > 0), 0.0)
    atr = _tr(d).ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False).mean() / atr
    ndi = 100 * ndm.ewm(alpha=1 / n, adjust=False).mean() / atr
    return (100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)).ewm(alpha=1 / n, adjust=False).mean()


def rel_volume(df):
    """Last candle's volume vs the SAME hour on the previous 10 sessions (MCX evenings trade far more than mornings, so a
    plain 20-hour average made every morning candle look like "0.4x volume"); 20-hour average if fewer than 5 days."""
    vol = df["volume"].astype(float)
    hr = pd.to_datetime(df["time"]).dt.strftime("%H:%M").values
    same = vol[hr == hr[-1]].iloc[:-1].tail(10)
    avg = float(same.mean()) if len(same) >= 5 else float(vol.iloc[-21:-1].mean())
    return float(vol.iloc[-1]) / avg if avg > 0 else None


# ─────────────── intraday ───────────────
def intraday(df, p=INTRA):
    """df: closed 1-hour candles (oldest first). Returns (signal dict or None, reason)."""
    if df is None or len(df) < p["ema"][2] + 5:
        return None, f"only {0 if df is None else len(df)} hourly candles (need {p['ema'][2] + 5})"
    c = df["close"]
    e1, e2, e3 = (c.ewm(span=n, adjust=False).mean().iloc[-1] for n in p["ema"])
    atr = float(_tr(df).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1])
    adx = float(_adx(df).iloc[-1]); rsi = float(_rsi(c).iloc[-1]); last = float(c.iloc[-1])
    prev = df.iloc[-1 - p["brk"]:-1]
    hh, ll = float(prev.high.max()), float(prev.low.min())
    vx = rel_volume(df)
    info = dict(close=last, ema20=float(e1), ema50=float(e2), ema200=float(e3), adx=round(adx, 1), rsi=round(rsi, 1),
                atr=atr, level_hi=hh, level_lo=ll, vol_x=None if vx is None else round(vx, 2),
                swing_low=float(df.low.iloc[-p["brk"]:].min()), swing_high=float(df.high.iloc[-p["brk"]:].max()),
                candle=str(df["time"].iloc[-1]))
    if adx < p["min_adx"]:
        return None, f"ADX {adx:.0f} < {p['min_adx']} (no trend)"
    if float(df.high.iloc[-1] - df.low.iloc[-1]) > p["spike_atr"] * atr:
        return None, "signal candle too big (spike)"
    if vx is not None and vx < p["vol_x"]:
        return None, f"volume only {vx:.1f}x average"
    up = last > e1 > e2 and last > e3 and last > hh
    dn = last < e1 < e2 and last < e3 and last < ll
    if up:
        if rsi > p["rsi_buy"][1]:
            return dict(info, side="BUY", blocked=f"RSI {rsi:.0f} > {p['rsi_buy'][1]} blocks a fresh BUY"), "blocked"
        if rsi >= p["rsi_buy"][0]:
            return dict(info, side="BUY"), "ok"
        return None, f"BUY breakout but RSI {rsi:.0f} < {p['rsi_buy'][0]} (weak momentum)"
    if dn:
        if rsi < p["rsi_sell"][0]:
            return dict(info, side="SELL", blocked=f"RSI {rsi:.0f} < {p['rsi_sell'][0]} blocks a fresh SELL"), "blocked"
        if rsi <= p["rsi_sell"][1]:
            return dict(info, side="SELL"), "ok"
        return None, f"SELL breakdown but RSI {rsi:.0f} > {p['rsi_sell'][1]} (weak momentum)"
    return None, "no breakout in the trend direction"


def intraday_plan(sig, entry, p=INTRA):
    a, s = sig["atr"], 1 if sig["side"] == "BUY" else -1
    swing = sig["swing_low"] - 0.2 * a if s > 0 else sig["swing_high"] + 0.2 * a
    R = min(max(abs(entry - swing), p["sl_atr"][0] * a), p["sl_atr"][1] * a)
    return dict(entry=entry, sl=entry - s * R, t1=entry + s * p["t1_r"] * R, t2=entry + s * p["t2_r"] * R, R=R)


# ─────────────── positional ───────────────
def positional_frame(df, p=POS):
    d = df.copy().reset_index(drop=True)
    d["atr"] = _tr(d).rolling(p["atr_n"]).mean()
    d["sma"] = d.close.rolling(p["trend_n"]).mean()
    d["rsi"] = _rsi(d.close)
    d["hi_in"] = d.high.shift(1).rolling(p["entry_n"]).max(); d["lo_in"] = d.low.shift(1).rolling(p["entry_n"]).min()
    d["hi_out"] = d.high.shift(1).rolling(p["exit_n"]).max(); d["lo_out"] = d.low.shift(1).rolling(p["exit_n"]).min()
    return d


def positional(df, p=POS):
    """df: closed daily candles. Returns (state, info) with state in CALL / BLOCKED / WATCH / None for the last bar."""
    if df is None or len(df) < p["trend_n"] + 5:
        return None, dict(reason=f"only {0 if df is None else len(df)} daily candles (need {p['trend_n'] + 5})")
    d = positional_frame(df, p); b = d.iloc[-1]
    info = dict(close=float(b.close), sma=float(b.sma), rsi=round(float(b.rsi), 1), atr=float(b.atr), hi=float(b.hi_in),
                lo=float(b.lo_in), exit_long=float(b.lo_out), exit_short=float(b.hi_out), candle=str(b.time)[:10])
    for side, lvl, trend_ok in (("BUY", b.hi_in, b.close > b.sma), ("SELL", b.lo_in, b.close < b.sma)):
        if not trend_ok:
            continue
        s = 1 if side == "BUY" else -1
        if s * (b.close - lvl) > 0:
            if side == "BUY" and b.rsi > p["rsi_max_buy"]:
                return "BLOCKED", dict(info, side=side, level=float(lvl), why=f"RSI {b.rsi:.0f} > {p['rsi_max_buy']} blocks a fresh BUY")
            if side == "SELL" and b.rsi < p["rsi_min_sell"]:
                return "BLOCKED", dict(info, side=side, level=float(lvl), why=f"RSI {b.rsi:.0f} < {p['rsi_min_sell']} blocks a fresh SELL")
            return "CALL", dict(info, side=side, level=float(lvl), stop=float(b.close - s * p["stop_atr"] * b.atr))
        dist = s * (lvl - b.close) / b.atr
        if 0 <= dist <= p["watch_atr"]:
            return "WATCH", dict(info, side=side, level=float(lvl), distance_atr=round(float(dist), 2))
    return None, dict(info, reason="no setup")


def positional_exit(df, side, p=POS):
    """True when the last CLOSED daily candle crossed the opposite 20-day channel."""
    d = positional_frame(df, p); b = d.iloc[-1]
    return bool(b.close < b.lo_out) if side == "BUY" else bool(b.close > b.hi_out)
