"""Common event record (MCXE-003). Every detector emits rows

    i       bar index whose CLOSE makes the event knowable (decisions use bars <= i only)
    side    +1 BUY / -1 SELL
    fam     family letter (A trendline, B candle, C structure, D sweep, E S/R, F chart pattern, G failed breakout,
            H pull-back, I volatility, J session)
    name    event name (unique inside the family)
    level   reference / trigger price (the broken level, the line value, the candle extreme ...)
    inv     invalidation price (pattern-defined stop reference)
    g1..g3  geometry (documented by each detector; NaN if unused)
"""
import numpy as np
import pandas as pd

COLS = ["i", "side", "fam", "name", "level", "inv", "g1", "g2", "g3"]


class Sink:
    def __init__(self):
        self.rows = []

    def add(self, i, side, fam, name, level, inv, g1=np.nan, g2=np.nan, g3=np.nan):
        self.rows.append((int(i), int(side), fam, name, float(level), float(inv), float(g1), float(g2), float(g3)))

    def frame(self):
        return pd.DataFrame(self.rows, columns=COLS)


def fails(E, f, within=3, fam="G"):
    """Generic FAILED-BREAKOUT events (family G) from any breakout events E (side, level):
    a close back on the other side of the broken level within `within` bars -> event against the breakout,
    invalidation = the extreme reached since the breakout. One fail per breakout. Same segment only."""
    c, h, l, seg = f.close.values, f.high.values, f.low.values, f.seg.values
    n = len(c); s = Sink()
    for r in E.itertuples(index=False):
        i, sd, lv = r.i, r.side, r.level
        for k in range(i + 1, min(n, i + within + 1)):
            if seg[k] != seg[i]:
                break
            if (sd > 0 and c[k] < lv) or (sd < 0 and c[k] > lv):
                ext = h[i:k + 1].max() if sd > 0 else l[i:k + 1].min()
                s.add(k, -sd, fam, "FAIL_" + r.name, lv, ext, k - i)
                break
    return s.frame()
