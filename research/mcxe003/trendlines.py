"""Family A – trendlines and channels (causal). Uses swings from swing_detection (a swing is usable from bar conf+1).

Line construction (re-done each time a new swing of that kind is confirmed):
  resistance: through two confirmed swing HIGHS a < b (b = the newest, a among the previous 6), price_a > price_b (falling)
  support:    through two confirmed swing LOWS  a < b, price_a < price_b (rising)
  validity:   no CLOSE beyond the line between a and the current bar
  touches:    swing points of that kind between a and now within TOL x ATR of the line (incl. a and b)
  choice:     the valid line with the most touches; ties -> the most recent a
Events (side, level = line value at i, inv):
  TL_BRK      close beyond the line (falling resistance -> BUY; rising support -> SELL); inv = extreme of the last 3 bars
  TL_RET      within 15 bars after a break, the bar trades back to the line (<= RET_TOL ATR) and closes beyond -> with break
  TL_BOUNCE   rising support: low within BOUNCE_TOL ATR of the line (may pierce <= 0.3 ATR), close above line and above open
              -> BUY; falling resistance mirror -> SELL ("rejection"); inv = bar extreme
  CH_EXH      channel exhaustion: rising support with an upper parallel through the highest high between its pivots; a bar
              that touches the upper parallel and closes in its lower half -> SELL (mirror for falling resistance) ; inv = high
Geometry: g1 = touches, g2 = line age in bars (i - a), g3 = slope in ATR per bar (signed).
Name suffix _t2 (2 touches) or _t3 (>= 3 touches).
Failed breakouts of TL_BRK are produced generically by events.fails (family G).
"""
import numpy as np
from research.mcxe003.events import Sink

TOL = 0.25
RET_TOL = 0.15
BOUNCE_TOL = 0.15


def _best_line(P, kind, i, c, atr_i, seg_i, segP):
    """P: list of (piv, price) confirmed swings of one kind (newest last). Returns (a_piv, a_price, slope, touches) or None."""
    if len(P) < 2:
        return None
    bp, bv = P[-1]
    best = None
    for (ap, av) in P[-7:-1][::-1]:
        if bp == ap:
            continue
        if kind > 0 and not av > bv:
            continue
        if kind < 0 and not av < bv:
            continue
        slope = (bv - av) / (bp - ap)
        xs = np.arange(ap, i + 1)
        line = av + slope * (xs - ap)
        cs = c[ap:i + 1]
        if kind > 0 and (cs > line + 1e-12).any():
            continue
        if kind < 0 and (cs < line - 1e-12).any():
            continue
        t = sum(1 for (q, v) in P if ap <= q <= i and abs(v - (av + slope * (q - ap))) <= TOL * atr_i)
        if best is None or t > best[3]:
            best = (ap, av, slope, t)
    return best


def detect(f, sw):
    o, h, l, c, a, seg = (f[x].values for x in ("open", "high", "low", "close", "atr", "seg"))
    n = len(c); s = Sink()
    conf, piv, pr, kd = sw["conf"], sw["piv"], sw["price"], sw["kind"]
    ptr = 0
    H, L = [], []
    lines = {1: None, -1: None}           # kind -> (ap, av, slope, touches, upper-parallel offset or nan)
    broken = []                           # (side, ap, av, slope, bar of break, touches, age)
    for i in range(1, n):
        if seg[i] != seg[i - 1]:
            H, L = [], []; lines = {1: None, -1: None}; broken = []
        newk = set()
        while ptr < len(conf) and conf[ptr] < i:           # swings confirmed at a PREVIOUS close are usable now
            if seg[piv[ptr]] == seg[i]:
                (H if kd[ptr] == 1 else L).append((piv[ptr], pr[ptr])); newk.add(kd[ptr])
            ptr += 1
        A = a[i]
        if not A > 0:
            continue
        for k in newk:
            P = H if k == 1 else L
            bl = _best_line(P, k, i - 1, c, A, seg[i], None)
            if bl is not None:
                ap, av, sl, t = bl
                # channel parallel: through the extreme opposite to the line between its first pivot and now
                if k == -1:
                    xs = np.arange(ap, i); off = (h[ap:i] - (av + sl * (xs - ap))).max()
                else:
                    xs = np.arange(ap, i); off = (l[ap:i] - (av + sl * (xs - ap))).min()
                lines[k] = (ap, av, sl, t, off)
            else:
                lines[k] = None
        for k in (1, -1):
            ln = lines[k]
            if ln is None:
                continue
            ap, av, sl, t, off = ln
            v = av + sl * (i - ap)
            sfx = "_t3" if t >= 3 else "_t2"
            g = (t, i - ap, sl / A)
            side = 1 if k == 1 else -1                       # resistance break -> BUY, support break -> SELL
            if (k == 1 and c[i] > v) or (k == -1 and c[i] < v):
                inv = l[max(0, i - 2):i + 1].min() if side > 0 else h[max(0, i - 2):i + 1].max()
                s.add(i, side, "A", "TL_BRK" + sfx, v, inv, *g)
                broken.append((side, ap, av, sl, i, t, i - ap)); lines[k] = None
                continue
            # bounce / rejection at the line
            if k == -1 and l[i] <= v + BOUNCE_TOL * A and l[i] >= v - 0.3 * A and c[i] > v and c[i] > o[i]:
                s.add(i, 1, "A", "TL_BOUNCE" + sfx, v, l[i], *g)
            if k == 1 and h[i] >= v - BOUNCE_TOL * A and h[i] <= v + 0.3 * A and c[i] < v and c[i] < o[i]:
                s.add(i, -1, "A", "TL_BOUNCE" + sfx, v, h[i], *g)
            # channel exhaustion at the parallel
            if off == off:
                u = v + off
                if k == -1 and sl > 0 and h[i] >= u - 0.1 * A and c[i] < (h[i] + l[i]) / 2:
                    s.add(i, -1, "A", "CH_EXH" + sfx, u, h[i], *g)
                if k == 1 and sl < 0 and l[i] <= u + 0.1 * A and c[i] > (h[i] + l[i]) / 2:
                    s.add(i, 1, "A", "CH_EXH" + sfx, u, l[i], *g)
        # retests of recently broken lines
        keep = []
        for b in broken:
            side, ap, av, sl, ib, t, age = b
            if i - ib > 15:
                continue
            v = av + sl * (i - ap)
            sfx = "_t3" if t >= 3 else "_t2"
            if i > ib and side > 0 and l[i] <= v + RET_TOL * A and c[i] > v:
                s.add(i, 1, "A", "TL_RET" + sfx, v, l[i], t, age, sl / A); continue
            if i > ib and side < 0 and h[i] >= v - RET_TOL * A and c[i] < v:
                s.add(i, -1, "A", "TL_RET" + sfx, v, h[i], t, age, sl / A); continue
            keep.append(b)
        broken = keep
    return s.frame()
