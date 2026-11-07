"""Family B – candlestick patterns, objective definitions, event at the CLOSE of the last pattern candle (causal).

Shape terms (bar k): rng = high-low, body = |close-open|, uw / lw = upper / lower wick, pos = (close-low)/rng.
Prior move: mv = (close[i-1] - close[i-6]) / ATR ; down if mv <= -1, up if mv >= +1.
  HAMMER        lw >= 0.6 rng, pos >= 0.7, after down                           BUY   inv low
  HANGMAN       same shape after up                                             SELL  inv high
  SHOOTSTAR     uw >= 0.6 rng, pos <= 0.3, after up                             SELL  inv high
  INVHAMMER     same shape after down                                           BUY   inv low
  ENGULF        body engulfs previous opposite body, body >= 0.5 ATR             with candle colour; inv extreme of 2 bars
  MSTAR / ESTAR 3 bars: big opposite body (>= 0.6 ATR), small body (<= 0.3 ATR), close beyond the midpoint of bar 1
  PIERCE / DARKCLOUD  2 bars: previous bar a big opposite body (>= 0.5 ATR); the event bar opens at/beyond the previous
                close (intraday bars rarely gap, so not beyond the previous extreme) and closes beyond the previous body
                midpoint but inside its body
  INSIDE_BRK    within 3 bars after an inside bar, close beyond the mother bar  with the break; inv other side of mother
  OUTSIDE       range engulfs previous range, close in the outer 25 %          with close; inv other extreme
  PIN           wick >= 2/3 rng at a 20-bar extreme (new 20-bar low/high)       against the wick; inv wick end
  DOJI          body <= 0.1 rng, after up -> SELL / after down -> BUY            inv bar extreme
  REV3          bar1 one way, bar2 makes a new extreme, bar3 closes beyond bar1's opposite extreme -> reversal
  STRONGBODY    body >= 0.7 rng and rng >= 1.5 ATR, close beyond the previous 10-bar extreme  with candle; inv low/high
  WICKREJ       wick >= 0.5 rng pierces the previous 10-bar extreme and close back inside -> against the wick
  COMPRESS_BRK  three bars each rng < 0.6 ATR, then a close beyond their combined range within 3 bars  with break
  NR4_BRK / NR7_BRK  narrowest range of 4 / 7 bars, close beyond it within 3 bars  with break; inv other side
g1 = body/rng of the event bar, g2 = rng/ATR, g3 = prior move mv (ATR).
"""
import numpy as np
import pandas as pd
from research.mcxe003.events import Sink


def detect(f):
    o, h, l, c, a, seg = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr", "seg"))
    n = len(c); s = Sink()
    rng = h - l; body = np.abs(c - o); uw = h - np.maximum(o, c); lw = np.minimum(o, c) - l
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = np.where(rng > 0, (c - l) / rng, 0.5)
    mv = np.full(n, np.nan); mv[6:] = (c[5:-1] - c[:-6]) / a[6:]
    hh10 = pd.Series(h).rolling(10).max().shift(1).values; ll10 = pd.Series(l).rolling(10).min().shift(1).values
    hh20 = pd.Series(h).rolling(20).max().shift(1).values; ll20 = pd.Series(l).rolling(20).min().shift(1).values
    rmin4 = pd.Series(rng).rolling(4).min().values; rmin7 = pd.Series(rng).rolling(7).min().values
    up, dn = mv >= 1, mv <= -1
    pend = []                                           # (kind, start bar, hi, lo, name)

    def g(i):
        return (body[i] / rng[i] if rng[i] > 0 else np.nan, rng[i] / a[i], mv[i])

    for i in range(7, n):
        A = a[i]
        if not A > 0 or seg[i - 6] != seg[i] or not rng[i] > 0:
            pend = [p for p in pend if seg[p[1]] == seg[i]]
            continue
        G = g(i)
        if lw[i] >= 0.6 * rng[i] and pos[i] >= 0.7:
            if dn[i]:
                s.add(i, 1, "B", "HAMMER", h[i], l[i], *G)
            elif up[i]:
                s.add(i, -1, "B", "HANGMAN", l[i], h[i], *G)
        if uw[i] >= 0.6 * rng[i] and pos[i] <= 0.3:
            if up[i]:
                s.add(i, -1, "B", "SHOOTSTAR", l[i], h[i], *G)
            elif dn[i]:
                s.add(i, 1, "B", "INVHAMMER", h[i], l[i], *G)
        p = i - 1
        if body[i] >= 0.5 * A and (c[i] - o[i]) * (c[p] - o[p]) < 0 and max(o[i], c[i]) >= max(o[p], c[p]) and min(o[i], c[i]) <= min(o[p], c[p]):
            sd = 1 if c[i] > o[i] else -1
            s.add(i, sd, "B", "ENGULF", c[i], min(l[i], l[p]) if sd > 0 else max(h[i], h[p]), *G)
        q = i - 2
        if body[q] >= 0.6 * A and body[p] <= 0.3 * A:
            mid = (o[q] + c[q]) / 2
            if c[q] < o[q] and c[i] > o[i] and c[i] > mid:
                s.add(i, 1, "B", "MSTAR", c[i], min(l[q], l[p], l[i]), *G)
            if c[q] > o[q] and c[i] < o[i] and c[i] < mid:
                s.add(i, -1, "B", "ESTAR", c[i], max(h[q], h[p], h[i]), *G)
        midp = (o[p] + c[p]) / 2
        if c[p] < o[p] and body[p] >= 0.5 * A and o[i] <= c[p] and c[i] > midp and c[i] < o[p]:
            s.add(i, 1, "B", "PIERCE", c[i], min(l[p], l[i]), *G)
        if c[p] > o[p] and body[p] >= 0.5 * A and o[i] >= c[p] and c[i] < midp and c[i] > o[p]:
            s.add(i, -1, "B", "DARKCLOUD", c[i], max(h[p], h[i]), *G)
        if h[i] >= h[p] and l[i] <= l[p] and (h[i] > h[p] or l[i] < l[p]):
            if pos[i] >= 0.75:
                s.add(i, 1, "B", "OUTSIDE", c[i], l[i], *G)
            elif pos[i] <= 0.25:
                s.add(i, -1, "B", "OUTSIDE", c[i], h[i], *G)
        if lw[i] >= 2 / 3 * rng[i] and l[i] < ll20[i]:
            s.add(i, 1, "B", "PIN", c[i], l[i], *G)
        if uw[i] >= 2 / 3 * rng[i] and h[i] > hh20[i]:
            s.add(i, -1, "B", "PIN", c[i], h[i], *G)
        if body[i] <= 0.1 * rng[i] and rng[i] >= 0.5 * A:
            if up[i]:
                s.add(i, -1, "B", "DOJI", l[i], h[i], *G)
            elif dn[i]:
                s.add(i, 1, "B", "DOJI", h[i], l[i], *G)
        if c[q] < o[q] and l[p] < l[q] and c[i] > h[q]:
            s.add(i, 1, "B", "REV3", h[q], min(l[p], l[i]), *G)
        if c[q] > o[q] and h[p] > h[q] and c[i] < l[q]:
            s.add(i, -1, "B", "REV3", l[q], max(h[p], h[i]), *G)
        if body[i] >= 0.7 * rng[i] and rng[i] >= 1.5 * A:
            if c[i] > o[i] and c[i] > hh10[i]:
                s.add(i, 1, "B", "STRONGBODY", hh10[i], l[i], *G)
            if c[i] < o[i] and c[i] < ll10[i]:
                s.add(i, -1, "B", "STRONGBODY", ll10[i], h[i], *G)
        if uw[i] >= 0.5 * rng[i] and h[i] > hh10[i] and c[i] < hh10[i]:
            s.add(i, -1, "B", "WICKREJ", hh10[i], h[i], *G)
        if lw[i] >= 0.5 * rng[i] and l[i] < ll10[i] and c[i] > ll10[i]:
            s.add(i, 1, "B", "WICKREJ", ll10[i], l[i], *G)
        # pending breakouts of inside bars / compressions / narrow-range bars
        keep = []
        for kind, st, hi, lo, nm in pend:
            if seg[st] != seg[i] or i - st > 3:
                continue
            if c[i] > hi:
                s.add(i, 1, "B", nm, hi, lo, *G); continue
            if c[i] < lo:
                s.add(i, -1, "B", nm, lo, hi, *G); continue
            keep.append((kind, st, hi, lo, nm))
        pend = keep
        if h[i] <= h[p] and l[i] >= l[p]:
            pend.append(("ib", i, h[p], l[p], "INSIDE_BRK"))
        if rng[i] < 0.6 * A and rng[p] < 0.6 * a[p] and rng[q] < 0.6 * a[q]:
            pend.append(("cp", i, max(h[i], h[p], h[q]), min(l[i], l[p], l[q]), "COMPRESS_BRK"))
        if rng[i] <= rmin7[i]:
            pend.append(("n7", i, h[i], l[i], "NR7_BRK"))
        elif rng[i] <= rmin4[i]:
            pend.append(("n4", i, h[i], l[i], "NR4_BRK"))
    E = s.frame()
    return E
