"""Divergence with price-structure confirmation (numba, one stock per call).
Pivot low at bar p: low[p] is the minimum of low[p-k .. p+k]; it is KNOWN only at bar p+k (no look-ahead).
Regular bullish: two pivot lows p1 < p2 within `maxgap` bars, low[p2] < low[p1], osc[p2] > osc[p1].
Hidden bullish:  low[p2] > low[p1], osc[p2] < osc[p1] (trend continuation).
Signal (actionable): the first close above the highest high between p1 and p2 ("swing break"), within `win` bars after
p2 is confirmed. Bearish versions mirror (pivot highs, close below the lowest low between them)."""
import numpy as np
from numba import njit


@njit(cache=True)
def divergence(h, l, c, osc, side, hidden, k=3, maxgap=40, win=10):
    n = len(c)
    out = np.zeros(n, np.bool_)
    lvl = np.full(n, np.nan)
    p1, p2 = -1, -1
    armed, level, until = False, 0.0, -1
    for t in range(2 * k, n):
        p = t - k                                   # candidate pivot confirmed at t
        is_piv = True
        for j in range(p - k, p + k + 1):
            if side > 0:
                if l[j] < l[p]:
                    is_piv = False; break
            else:
                if h[j] > h[p]:
                    is_piv = False; break
        if is_piv and not np.isnan(osc[p]):
            p1, p2 = p2, p
            if p1 >= 0 and p2 - p1 <= maxgap and p2 - p1 >= k and not np.isnan(osc[p1]):
                if side > 0:
                    pr = l[p2] < l[p1] if not hidden else l[p2] > l[p1]
                    orr = osc[p2] > osc[p1] if not hidden else osc[p2] < osc[p1]
                else:
                    pr = h[p2] > h[p1] if not hidden else h[p2] < h[p1]
                    orr = osc[p2] < osc[p1] if not hidden else osc[p2] > osc[p1]
                if pr and orr:
                    if side > 0:
                        level = np.max(h[p1:p2 + 1])
                    else:
                        level = np.min(l[p1:p2 + 1])
                    armed, until = True, t + win
        if armed:
            if t > until:
                armed = False
            elif (side > 0 and c[t] > level) or (side < 0 and c[t] < level):
                out[t] = True; lvl[t] = level; armed = False
    return out, lvl
