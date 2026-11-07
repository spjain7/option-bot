"""RESEARCH-ONLY copy of the live S4 stock-futures OI breakout (alerts/stocks.py on main @ bc3153e: CFG, nfo_expiry,
in_rollover_window, evaluate). The decision logic is copied verbatim; production is never imported or modified.
Parity with production is checked by tests/test_preservation.py (same decisions on the PETRONET / GLENMARK / TITAN
fixtures, on perturbations and on a sample of in-window daily frames).

Plan simulated as in production: entry = signal close; the call becomes ACTIVE at the next open only if that open is
within 0.5 ATR past the entry and not 0.5 ATR against it and not beyond the stop (otherwise CANCELLED); fill = next open;
SL 2 ATR from the signal close; 3-ATR trailing stop on daily closes (moves only by > 0.25 ATR, as production); exit on the
contract's expiry day close or after 40 sessions; stop checked on daily lows (gap through the stop fills at the open).
"""
import numpy as np
import pandas as pd
from crude import indicators as I

CFG = dict(N=20, vol_x=1.5, oi_up=0.02, ema=200, stop_atr=2.0, trail_atr=3.0, max_days=40)
MAX_CHASE_ATR = 0.5
MAX_AGAINST_ATR = 0.5


def nfo_expiry(y, m):
    last = pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)
    wd = 3 if pd.Timestamp(y, m, 1) < pd.Timestamp("2025-09-01") else 1
    while last.weekday() != wd:
        last -= pd.Timedelta(days=1)
    return last


def in_rollover_window(day):
    d = pd.Timestamp(day).normalize()
    for k in (-1, 0, 1):
        m = d + pd.DateOffset(months=k)
        e = nfo_expiry(m.year, m.month)
        if e - pd.offsets.BDay(3) <= d <= e + pd.offsets.BDay(2):
            return True
    return False


def evaluate(d):
    """verbatim copy of alerts.stocks.evaluate (main @ bc3153e)."""
    if d is None or len(d) < CFG["ema"] + 5:
        return dict(side=None, why="not enough daily history")
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"].astype(float)
    x = d.iloc[-1]
    hh, ll = h.shift(1).rolling(CFG["N"]).max().iloc[-1], l.shift(1).rolling(CFG["N"]).min().iloc[-1]
    va = v.rolling(20).mean().shift(1).iloc[-1]
    e = I.ema(c, CFG["ema"]).iloc[-1]
    a = float(I.atr(d, 14).iloc[-1])
    dp = c.pct_change().iloc[-1]
    if "doi" in d:
        doi = d["doi"].iloc[-1]
        oi_why = d["oi_reason"].iloc[-1] if "oi_reason" in d else None
    else:
        doi = d["oi"].pct_change().iloc[-1] if d["oi"].notna().iloc[-2:].all() else np.nan
        oi_why = None
    out = dict(candle=str(x.time), close=float(x.close), hh=float(hh), ll=float(ll), ema200=float(e), atr=a,
               vol_x=float(x.volume / va) if va else None, dp=float(dp), doi=None if pd.isna(doi) else float(doi),
               adx=float(I.adx(d).iloc[-1]), rsi=float(I.rsi(c, 14).iloc[-1]))
    vok = out["vol_x"] is not None and out["vol_x"] > CFG["vol_x"]
    if in_rollover_window(x.time):
        return dict(out, side=None, why="OI change not usable (rollover window)")
    if pd.isna(doi):
        bo = (x.close > hh and vok and dp > 0 and x.close > e) or (x.close < ll and vok and dp < 0 and x.close < e)
        return dict(out, side=None, why=f"OI change not usable ({oi_why or 'missing'})", oi_blocked=bool(bo))
    if x.close > hh and vok and dp > 0 and doi >= CFG["oi_up"] and x.close > e:
        return dict(out, side="BUY")
    if x.close < ll and vok and dp < 0 and doi >= CFG["oi_up"] and x.close < e:
        return dict(out, side="SELL")
    return dict(out, side=None, why="no OI-confirmed breakout")


def signals_vectorised(d, ema_n=CFG["ema"]):
    """same conditions as evaluate() for every bar at once (research speed). parity checked in tests.
    ema_n can be lowered ONLY for in-window research (the 1-year window cannot warm up an EMA200 on daily bars)."""
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"].astype(float)
    hh, ll = h.shift(1).rolling(CFG["N"]).max(), l.shift(1).rolling(CFG["N"]).min()
    va = v.rolling(20).mean().shift(1)
    e = I.ema(c, ema_n)
    dp = c.pct_change()
    doi = d["doi"] if "doi" in d else d["oi"].pct_change()
    vok = (v / va) > CFG["vol_x"]
    roll = np.array([in_rollover_window(t) for t in d["time"]])
    ok = (np.arange(len(d)) >= ema_n + 4) & ~roll & doi.notna().values
    buy = ok & (c > hh) & vok & (dp > 0) & (doi >= CFG["oi_up"]) & (c > e)
    sell = ok & (c < ll) & vok & (dp < 0) & (doi >= CFG["oi_up"]) & (c < e)
    return np.where(buy, 1, np.where(sell, -1, 0)), dict(hh=hh, ll=ll, vol_x=v / va, dp=dp, doi=doi, ema=e,
                                                          atr=I.atr(d, 14), adx=I.adx(d), rsi=I.rsi(c, 14))


def simulate(d, sig, cost_frac, expiry=None, entry_check=True):
    """S4 plan on daily bars. Returns list of trades (dict) incl. cancelled signals."""
    o, h, l, c = (d[x].values.astype(float) for x in ("open", "high", "low", "close"))
    a = I.atr(d, 14).values
    t = d["time"].values
    exp = expiry if expiry is not None else np.full(len(d), np.datetime64("NaT"))
    out, busy = [], -1
    for i in np.flatnonzero(sig != 0):
        if i <= busy or i + 1 >= len(c):
            continue
        s = int(sig[i]); e = c[i]; A = a[i]; risk = CFG["stop_atr"] * A; st = e - s * risk
        rec = dict(i=int(i), date=t[i], side=s, signal_close=e, atr=A)
        mv = s * (o[i + 1] - e) / A
        if entry_check and (s * (o[i + 1] - st) <= 0 or mv > MAX_CHASE_ATR or mv < -MAX_AGAINST_ATR):
            out.append(dict(rec, status="cancelled", why=("opened beyond the stop" if s * (o[i + 1] - st) <= 0 else
                                                          "opened > 0.5 ATR past the entry" if mv > MAX_CHASE_ATR else
                                                          "opened > 0.5 ATR against the entry"), open_move_atr=mv))
            continue
        fill = o[i + 1]; best = fill; px = None; why = None; n = 0
        for j in range(i + 1, len(c)):
            if j > i + 1 and s * (o[j] - st) <= 0:
                px, why = o[j], "stop-gap"; break
            if s * (l[j] - st) <= 0 if s > 0 else s * (h[j] - st) <= 0:
                px, why = st, "stop"; break
            n += 1
            best = max(best, c[j]) if s > 0 else min(best, c[j])
            ns = best - s * CFG["trail_atr"] * a[j]
            if s * (ns - st) > 0.25 * a[j]:
                st = ns
            if (not pd.isna(exp[i]) and t[j] >= exp[i]) or n >= CFG["max_days"]:
                px, why = c[j], "expiry/time exit"; break
        if px is None:
            px, why, j = c[-1], "open at window end", len(c) - 1
        R = risk
        g = s * (px - fill) / R
        cost = cost_frac * (fill + px) / 2 / R
        out.append(dict(rec, status="trade", fill=fill, exit=px, exit_date=t[j], why=why, bars=j - i, grossR=g,
                        r1=g - cost, r2=g - 2 * cost, cost_r=cost, open_move_atr=mv))
        busy = j
    return out
