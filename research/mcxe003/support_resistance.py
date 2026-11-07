"""Family E – support / resistance zones from confirmed swings only (causal; swing usable from bar conf+1).

Zone = cluster of confirmed swing prices (highs and lows together) within TOL x ATR, lookback LB bars, >= 2 swings.
Zone price = mean of its swings; width = max-min of its swings; touches = number of swings in it.
At bar i the nearest zone ABOVE the previous close is resistance, the nearest BELOW is support.
Events:
  SR_BRK   close through a zone (resistance -> BUY, support -> SELL); inv = extreme of the last 3 bars
  SR_RET   within 10 bars after a break, trade back into the zone (<= 0.15 ATR) and close beyond = role flip -> with break
  SR_REJ   touch of resistance (high within 0.15 ATR, may pierce <= 0.3 ATR) and close back below it in the lower half of the
           bar -> SELL; support mirror -> BUY ("bounce")
Name suffix _fresh (2 touches) / _tested (>= 3 touches).
Failed breaks of SR_BRK come from events.fails (family G).
g1 = touches, g2 = zone width / ATR, g3 = approach strength = (close[i-1] - close[i-6]) / ATR in the event direction.
"""
import numpy as np
from research.mcxe003.events import Sink

TOL, LB = 0.25, 100


def _zones(P, A):
    P = sorted(P)
    Z = []; cur = [P[0]] if P else []
    for v in P[1:]:
        if v - cur[0] <= TOL * A:
            cur.append(v)
        else:
            Z.append(cur); cur = [v]
    if cur:
        Z.append(cur)
    return [(float(np.mean(z)), len(z), max(z) - min(z)) for z in Z if len(z) >= 2]


def detect(f, sw):
    h, l, c, a, seg = (f[x].values for x in ("high", "low", "close", "atr", "seg"))
    n = len(c); s = Sink()
    conf, piv, pr = sw["conf"], sw["piv"], sw["price"]
    ptr = 0; S = []; Z = []; pend = []; last_used = {}
    for i in range(6, n):
        if seg[i] != seg[i - 1]:
            S, Z, pend = [], [], []
        new = False
        while ptr < len(conf) and conf[ptr] < i:
            if seg[piv[ptr]] == seg[i]:
                S.append((piv[ptr], pr[ptr])); new = True
            ptr += 1
        A = a[i]
        if not A > 0:
            continue
        S = [x for x in S if i - x[0] <= LB]
        if new or i % 10 == 0:
            Z = _zones([v for _, v in S], A)
        if not Z:
            continue
        pc = c[i - 1]
        above = [z for z in Z if z[0] > pc]; below = [z for z in Z if z[0] < pc]
        appr = (c[i - 1] - c[i - 6]) / A
        if above:
            zp, t, wd = min(above, key=lambda z: z[0])
            sfx = "_tested" if t >= 3 else "_fresh"
            if c[i] > zp + wd / 2:
                s.add(i, 1, "E", "SR_BRK" + sfx, zp, l[i - 2:i + 1].min(), t, wd / A, appr)
                pend.append((1, zp, i, t, wd))
            elif h[i] >= zp - 0.15 * A and h[i] <= zp + 0.3 * A and c[i] < zp and c[i] < (h[i] + l[i]) / 2:
                s.add(i, -1, "E", "SR_REJ" + sfx, zp, h[i], t, wd / A, -appr)
        if below:
            zp, t, wd = max(below, key=lambda z: z[0])
            sfx = "_tested" if t >= 3 else "_fresh"
            if c[i] < zp - wd / 2:
                s.add(i, -1, "E", "SR_BRK" + sfx, zp, h[i - 2:i + 1].max(), t, wd / A, -appr)
                pend.append((-1, zp, i, t, wd))
            elif l[i] <= zp + 0.15 * A and l[i] >= zp - 0.3 * A and c[i] > zp and c[i] > (h[i] + l[i]) / 2:
                s.add(i, 1, "E", "SR_REJ" + sfx, zp, l[i], t, wd / A, appr)
        keep = []
        for sd, zp, ib, t, wd in pend:
            if i - ib > 10:
                continue
            if i == ib:
                keep.append((sd, zp, ib, t, wd)); continue
            sfx = "_tested" if t >= 3 else "_fresh"
            if sd > 0 and l[i] <= zp + 0.15 * A and c[i] > zp:
                s.add(i, 1, "E", "SR_RET" + sfx, zp, l[i], t, wd / A, i - ib); continue
            if sd < 0 and h[i] >= zp - 0.15 * A and c[i] < zp:
                s.add(i, -1, "E", "SR_RET" + sfx, zp, h[i], t, wd / A, i - ib); continue
            keep.append((sd, zp, ib, t, wd))
        pend = keep
    return s.frame()
