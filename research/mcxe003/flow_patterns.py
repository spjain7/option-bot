"""Families H (trend continuation / pull-back), I (volatility & regime transitions), J (session / time-of-day) and the
plain N-bar breakout baseline. All causal: computed from bars <= i.

H  EMA_PB      EMA20 > EMA50 and close > EMA50 (mirror for SELL); the bar's low touches EMA20 (<= 0.1 ATR above it) after
               the close was >= 1 ATR above EMA20 within the last 10 bars; close back above EMA20 and above open -> BUY;
               inv = low
   VWAP_PB     (intraday) close above VWAP for the previous 6 bars, low touches VWAP (<= 0.1 ATR), close above VWAP -> BUY
   EXPANSION_PB  within 10 bars after a range-expansion bar (rng >= 2 ATR, close in its outer 25 %), the first bar that
               closes beyond the previous bar's extreme in the expansion direction after a pull-back of >= 1 bar -> with
I  ATRC_BRK    ATR(5)/ATR(50) <= 0.6 on one of the last 3 bars, then a close beyond the 20-bar range -> with the break
   EXPAND      range-expansion bar (rng >= 2 ATR, close in the outer 25 %) -> with the bar (continuation)
   EXPAND_FAIL within 3 bars after EXPAND, a close beyond the expansion bar's midpoint against it -> fade
   RANGE2TREND 20-bar range <= 3 ATR, then a close beyond it by >= 0.5 ATR -> with
   EXHAUST     three consecutive bars each rng >= 1.5 ATR closing in the same direction -> fade; inv = extreme
   NBAR_BRK    close beyond the previous 20-bar high / low (plain breakout baseline, the most-tested idea)
J  (intraday only; MCX times IST, NSE times IST)
   ORB30 / ORB60    close beyond the first 30 / 60-minute range, before 13:00 (MCX) / 12:00 (NSE) -> with
   FIRSTHOUR   at the first bar starting >= 10:00 (MCX) / 10:15 (NSE): |close - day open| >= 0.5 daily ATR -> with that move
   AFTERNOON   at the first bar starting >= 15:00 (MCX) / 13:30 (NSE): |close - day open| >= 0.3 daily ATR and close on the same
               side of VWAP -> with
   USOPEN      MCX only: at the first bar starting >= US cash open + 30 min (19:30 IST during US daylight saving, else 20:30;
               calendar rule), direction of the last 30 minutes if >= 0.3 ATR(tf) -> with
   LATE_BRK    close above the session high (below the low) so far, after 20:00 (MCX) / 14:00 (NSE) -> with
g1/g2/g3 per event: see code (move sizes in ATR).
"""
import numpy as np
import pandas as pd
from research.mcxe003.events import Sink


def us_dst(days):
    """US daylight saving (calendar rule, known in advance): 2nd Sunday of March .. 1st Sunday of November."""
    d = pd.to_datetime(pd.Series(days).values)
    y = d.year
    mar = pd.to_datetime(pd.Series(y).astype(str) + "-03-01"); nov = pd.to_datetime(pd.Series(y).astype(str) + "-11-01")
    s = mar + pd.to_timedelta((6 - mar.dt.weekday) % 7 + 7, "D"); e = nov + pd.to_timedelta((6 - nov.dt.weekday) % 7, "D")
    return ((d >= s.values) & (d < e.values))


def detect(f, intraday=True):
    o, h, l, c, a, seg = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr", "seg"))
    n = len(c); s = Sink()
    cs = pd.Series(c)
    e20 = cs.ewm(span=20, adjust=False).mean().values; e50 = cs.ewm(span=50, adjust=False).mean().values
    rng = h - l
    tr = pd.Series(np.maximum(rng, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1)))))
    a5 = tr.rolling(5).mean().values; a50 = tr.rolling(50).mean().values
    hh20 = pd.Series(h).rolling(20).max().shift(1).values; ll20 = pd.Series(l).rolling(20).min().shift(1).values
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = np.where(rng > 0, (c - l) / rng, 0.5)
        comp = a5 / a50
    segstart = np.r_[True, seg[1:] != seg[:-1]]
    sbar = np.maximum.accumulate(np.where(segstart, np.arange(n), 0))     # first bar of the segment
    if intraday:
        vw, m, day, dopen, datr = f.vwap.values, f.m.values, f.day.values, f.dopen.values, f.datr.values
        mcx = f.attrs.get("market") == "MCX"
        tf = f.attrs.get("tf", 15)
        d0 = 540 if mcx else 555
        us_open = np.where(us_dst(f.day), 19 * 60, 20 * 60)               # US cash open 09:30 ET = 19:00 / 20:00 IST
    exp_bar = -100; exp_dir = 0; exp_mid = 0.0; pb_seen = False
    dh = dl = np.nan; orr = {30: [np.nan, np.nan, False], 60: [np.nan, np.nan, False]}; fired = set()
    for i in range(1, n):
        A = a[i]
        newday = intraday and day[i] != day[i - 1]
        if newday:
            dh = dl = np.nan; orr = {30: [np.nan, np.nan, False], 60: [np.nan, np.nan, False]}; fired = set()
        if not A > 0 or i - sbar[i] < 50:
            if intraday:
                dh = h[i] if dh != dh else max(dh, h[i]); dl = l[i] if dl != dl else min(dl, l[i])
            continue
        # ---- H
        if e20[i] > e50[i] and c[i] > e50[i] and l[i] <= e20[i] + 0.1 * A and c[i] > e20[i] and c[i] > o[i] and (c[i - 10:i] - e20[i - 10:i]).max() >= A:
            s.add(i, 1, "H", "EMA_PB", e20[i], l[i], (c[i] - e50[i]) / A)
        if e20[i] < e50[i] and c[i] < e50[i] and h[i] >= e20[i] - 0.1 * A and c[i] < e20[i] and c[i] < o[i] and (e20[i - 10:i] - c[i - 10:i]).max() >= A:
            s.add(i, -1, "H", "EMA_PB", e20[i], h[i], (e50[i] - c[i]) / A)
        if intraday and i >= 7 and day[i - 6] == day[i]:
            if (c[i - 6:i] > vw[i - 6:i]).all() and l[i] <= vw[i] + 0.1 * A and c[i] > vw[i]:
                s.add(i, 1, "H", "VWAP_PB", vw[i], l[i], (c[i] - dopen[i]) / datr[i] if datr[i] > 0 else np.nan)
            if (c[i - 6:i] < vw[i - 6:i]).all() and h[i] >= vw[i] - 0.1 * A and c[i] < vw[i]:
                s.add(i, -1, "H", "VWAP_PB", vw[i], h[i], (dopen[i] - c[i]) / datr[i] if datr[i] > 0 else np.nan)
        if 0 < i - exp_bar <= 10:
            if exp_dir > 0:
                if c[i] < c[i - 1]:
                    pb_seen = True
                elif pb_seen and c[i] > h[i - 1]:
                    s.add(i, 1, "H", "EXPANSION_PB", h[i - 1], l[exp_bar:i + 1].min(), i - exp_bar); exp_bar = -100
            else:
                if c[i] > c[i - 1]:
                    pb_seen = True
                elif pb_seen and c[i] < l[i - 1]:
                    s.add(i, -1, "H", "EXPANSION_PB", l[i - 1], h[exp_bar:i + 1].max(), i - exp_bar); exp_bar = -100
            if 0 < i - exp_bar <= 3 and exp_bar >= 0:
                if (exp_dir > 0 and c[i] < exp_mid) or (exp_dir < 0 and c[i] > exp_mid):
                    s.add(i, -exp_dir, "I", "EXPAND_FAIL", exp_mid, h[exp_bar:i + 1].max() if exp_dir < 0 else l[exp_bar:i + 1].min(), i - exp_bar)
                    exp_bar = -100
        # ---- I
        if rng[i] >= 2 * A and (pos[i] >= 0.75 or pos[i] <= 0.25):
            sd = 1 if pos[i] >= 0.75 else -1
            s.add(i, sd, "I", "EXPAND", c[i], l[i] if sd > 0 else h[i], rng[i] / A)
            exp_bar, exp_dir, exp_mid, pb_seen = i, sd, (h[i] + l[i]) / 2, False
        if np.nanmin(comp[i - 3:i]) <= 0.6:
            if c[i] > hh20[i]:
                s.add(i, 1, "I", "ATRC_BRK", hh20[i], ll20[i], np.nanmin(comp[i - 3:i]))
            elif c[i] < ll20[i]:
                s.add(i, -1, "I", "ATRC_BRK", ll20[i], hh20[i], np.nanmin(comp[i - 3:i]))
        if hh20[i] - ll20[i] <= 3 * A:
            if c[i] >= hh20[i] + 0.5 * A and c[i - 1] < hh20[i] + 0.5 * A:
                s.add(i, 1, "I", "RANGE2TREND", hh20[i], ll20[i], (hh20[i] - ll20[i]) / A)
            elif c[i] <= ll20[i] - 0.5 * A and c[i - 1] > ll20[i] - 0.5 * A:
                s.add(i, -1, "I", "RANGE2TREND", ll20[i], hh20[i], (hh20[i] - ll20[i]) / A)
        if i >= 3 and segstart[i - 2:i + 1].sum() == 0 and (rng[i - 2:i + 1] >= 1.5 * a[i - 2:i + 1]).all():
            dirs = np.sign(c[i - 2:i + 1] - o[i - 2:i + 1])
            if (dirs == 1).all():
                s.add(i, -1, "I", "EXHAUST", c[i], h[i], (c[i] - o[i - 2]) / A)
            elif (dirs == -1).all():
                s.add(i, 1, "I", "EXHAUST", c[i], l[i], (o[i - 2] - c[i]) / A)
        if c[i] > hh20[i] and c[i - 1] <= hh20[i]:
            s.add(i, 1, "I", "NBAR_BRK", hh20[i], l[i - 2:i + 1].min(), (c[i] - hh20[i]) / A)
        elif c[i] < ll20[i] and c[i - 1] >= ll20[i]:
            s.add(i, -1, "I", "NBAR_BRK", ll20[i], h[i - 2:i + 1].max(), (ll20[i] - c[i]) / A)
        # ---- J
        if intraday:
            mm = m[i]
            for w, R in orr.items():
                if mm < d0 + w:
                    R[0] = h[i] if R[0] != R[0] else max(R[0], h[i]); R[1] = l[i] if R[1] != R[1] else min(R[1], l[i])
                elif R[0] == R[0] and not R[2] and mm < (13 * 60 if mcx else 12 * 60):
                    if c[i] > R[0]:
                        s.add(i, 1, "J", f"ORB{w}", R[0], R[1], (R[0] - R[1]) / A); R[2] = True
                    elif c[i] < R[1]:
                        s.add(i, -1, "J", f"ORB{w}", R[1], R[0], (R[0] - R[1]) / A); R[2] = True
            dA = datr[i]
            if dA > 0:
                mv = c[i] - dopen[i]
                if "FH" not in fired and mm >= (600 if mcx else 615):
                    fired.add("FH")
                    if abs(mv) >= 0.5 * dA:
                        sd = 1 if mv > 0 else -1
                        s.add(i, sd, "J", "FIRSTHOUR", dopen[i], dl if sd > 0 else dh, mv / dA)
                if "AF" not in fired and mm >= (900 if mcx else 810):
                    fired.add("AF")
                    if abs(mv) >= 0.3 * dA and (c[i] - vw[i]) * mv > 0:
                        sd = 1 if mv > 0 else -1
                        s.add(i, sd, "J", "AFTERNOON", dopen[i], dl if sd > 0 else dh, mv / dA)
                if mcx and "US" not in fired and mm >= us_open[i] + 30:
                    fired.add("US")
                    k0 = i - max(1, 30 // tf)
                    if k0 >= 0 and day[k0] == day[i]:
                        mv30 = c[i] - c[k0]
                        if abs(mv30) >= 0.3 * A:
                            sd = 1 if mv30 > 0 else -1
                            s.add(i, sd, "J", "USOPEN", c[k0], l[k0:i + 1].min() if sd > 0 else h[k0:i + 1].max(), mv30 / A)
            if dh == dh and mm >= (20 * 60 if mcx else 14 * 60):
                if c[i] > dh and "LU" not in fired:
                    fired.add("LU"); s.add(i, 1, "J", "LATE_BRK", dh, l[i], (c[i] - dh) / A)
                elif c[i] < dl and "LD" not in fired:
                    fired.add("LD"); s.add(i, -1, "J", "LATE_BRK", dl, h[i], (dl - c[i]) / A)
            dh = h[i] if dh != dh else max(dh, h[i]); dl = l[i] if dl != dl else min(dl, l[i])
    return s.frame()
