"""Context tags at the event bar (MCXE-003), all from data up to and including bar i, expressed RELATIVE TO THE EVENT SIDE
(+1 = context agrees with the trade direction, -1 = against, 0 = neutral). Used for context / ablation analysis, never to
define the base cells.
  trend   sign of the EMA50 slope over the last 10 bars (tf)            ema     EMA20 > EMA50 > EMA200 stack (tf)
  dtrend  previous daily close vs its EMA20 (intraday frames: of earlier sessions)
  adx     ADX14 (tf) bucket 0 (<20) / 1 (20-30) / 2 (>30)                atr     ATR / 100-bar median ATR: 0 low (<0.8) /
                                                                                 1 normal / 2 high (>1.25)
  vwap    close vs session VWAP (intraday)                              day     day-trend: (close - day open) >= 0.3 daily ATR
                                                                                 and VWAP agree (the DTC condition)
  imp     prior 5-bar move in ATR: -1 (< -1 against), 0, +1 (> +1 with)  relvol  volume / median volume at the same time of
                                                                                 day over the previous 20 sessions: 0 (<0.8) /
                                                                                 1 / 2 (>1.5)
  sess    MCX 0 = 09:00-17:00, 1 = 17:00-20:00, 2 = 20:00-close ; NSE 0 = first hour, 1 = mid, 2 = after 13:30
"""
import numpy as np
import pandas as pd
from crude import indicators as I


def bar_context(f, intraday=True):
    c = f.close
    e20, e50, e200 = (c.ewm(span=k, adjust=False).mean() for k in (20, 50, 200))
    X = pd.DataFrame(index=f.index)
    X["trend"] = np.sign(e50 - e50.shift(10)).fillna(0).values
    X["ema"] = np.where((e20 > e50) & (e50 > e200), 1, np.where((e20 < e50) & (e50 < e200), -1, 0))
    adx = I.adx(f, 14)
    X["adx"] = np.select([adx < 20, adx <= 30], [0, 1], 2)
    ratio = f.atr / f.atr.rolling(100, min_periods=30).median()
    X["atr"] = np.select([ratio < 0.8, ratio <= 1.25], [0, 1], 2)
    mv = (c.shift(1) - c.shift(6)) / f.atr
    X["imp_raw"] = mv.values
    if intraday:
        d = f.groupby("day").close.last()
        de = d.ewm(span=20, adjust=False).mean()
        dtr = np.sign(d - de).shift(1)
        X["dtrend"] = f.day.map(dtr).fillna(0).values
        X["vwap"] = np.sign(c - f.vwap).fillna(0).values
        X["dmove"] = ((c - f.dopen) / f.datr).values
        med = f.groupby("m").volume.transform(lambda s: s.rolling(20, min_periods=5).median().shift(1))
        rv = f.volume / med
        X["relvol"] = np.select([rv < 0.8, rv <= 1.5], [0, 1], 2)
        X.loc[med.isna().values, "relvol"] = -9
        mkt = f.attrs.get("market")
        m = f.m
        X["sess"] = np.select([m < 17 * 60, m < 20 * 60], [0, 1], 2) if mkt == "MCX" else np.select([m < 615, m < 810], [0, 1], 2)
    else:
        X["dtrend"] = np.sign(c - c.ewm(span=20, adjust=False).mean()).values
        X["vwap"] = 0; X["dmove"] = np.nan; X["relvol"] = -9; X["sess"] = -9
    return X


def tag(E, X):
    """E: events (i, side). Returns side-relative context columns for each event."""
    x = X.iloc[E.i.values].reset_index(drop=True)
    sd = E.side.values
    out = pd.DataFrame(dict(
        c_trend=x.trend.values * sd, c_ema=x.ema.values * sd, c_dtrend=x.dtrend.values * sd, c_vwap=x.vwap.values * sd,
        c_adx=x.adx.values, c_atr=x.atr.values, c_relvol=x.relvol.values, c_sess=x.sess.values,
        c_imp=np.select([x.imp_raw.values * sd < -1, x.imp_raw.values * sd > 1], [-1, 1], 0),
        c_day=((x.dmove.values * sd >= 0.3) & (x.vwap.values * sd > 0)).astype(int)))
    return out
