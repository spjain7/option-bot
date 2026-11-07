"""Causal swing detection (MCXE-003).

Every method returns the SAME record layout, one row per swing, in the order the swings became KNOWABLE:
    conf  int   bar index at whose CLOSE the swing is confirmed (usable from bar conf on, never earlier)
    piv   int   bar index of the swing extreme (piv <= conf)
    price float swing price (high for a swing high, low for a swing low)
    kind  int   +1 swing high, -1 swing low
Segments: `seg` (int array, same length as the bars) – swings never connect across a segment change (contract roll,
or a new stock / instrument). A pivot window that crosses a segment boundary is not formed.

Methods
  fractal(k)      pivot high at j if high[j] is the max of high[j-k .. j+k]; confirmed at j+k (classic fractal / "pivot k")
  zigzag(mult)    ATR zig-zag: track the running extreme since the last swing; when price closes mult*ATR beyond it in the
                  opposite direction, the extreme is confirmed as a swing at that bar (no fixed width; adapts to volatility)
METHODS = {"f2": fractal k=2 (internal), "f3": k=3, "f5": k=5 (external), "z15": zigzag 1.5 ATR, "z3": zigzag 3 ATR}
"""
import numpy as np
from numba import njit

METHODS = {"f2": ("fractal", 2), "f3": ("fractal", 3), "f5": ("fractal", 5), "z15": ("zigzag", 1.5), "z3": ("zigzag", 3.0)}


@njit(cache=True)
def _fractal(h, l, seg, k):
    n = len(h)
    conf = np.empty(2 * n, np.int64); piv = np.empty(2 * n, np.int64); pr = np.empty(2 * n); kd = np.empty(2 * n, np.int64)
    m = 0
    for c in range(2 * k, n):
        j = c - k
        if seg[c - 2 * k] != seg[c]:
            continue
        hi = True; lo = True
        for q in range(j - k, j + k + 1):
            if q == j:
                continue
            if h[q] > h[j] or (q > j and h[q] == h[j]):        # ties: the EARLIER bar is the pivot
                hi = False
            if l[q] < l[j] or (q > j and l[q] == l[j]):
                lo = False
        if hi:
            conf[m] = c; piv[m] = j; pr[m] = h[j]; kd[m] = 1; m += 1
        if lo:
            conf[m] = c; piv[m] = j; pr[m] = l[j]; kd[m] = -1; m += 1
    return conf[:m], piv[:m], pr[:m], kd[:m]


@njit(cache=True)
def _zigzag(h, l, c, atr, seg, mult):
    n = len(h)
    conf = np.empty(n, np.int64); piv = np.empty(n, np.int64); pr = np.empty(n); kd = np.empty(n, np.int64)
    m = 0
    dirn = 0                                            # 0 undecided, 1 tracking a high, -1 tracking a low
    hx = 0.0; hxi = 0; lx = 0.0; lxi = 0
    for i in range(n):
        if i == 0 or seg[i] != seg[i - 1]:
            dirn = 0; hx = h[i]; hxi = i; lx = l[i]; lxi = i
            continue
        if h[i] > hx:
            hx = h[i]; hxi = i
        if l[i] < lx:
            lx = l[i]; lxi = i
        a = atr[i]
        if not a > 0:
            continue
        if dirn >= 0 and c[i] <= hx - mult * a:         # swing high confirmed now
            conf[m] = i; piv[m] = hxi; pr[m] = hx; kd[m] = 1; m += 1
            dirn = -1
            lx = l[hxi]; lxi = hxi                       # low tracking restarts after the high
            for q in range(hxi + 1, i + 1):
                if l[q] < lx:
                    lx = l[q]; lxi = q
            hx = h[i]; hxi = i
        elif dirn <= 0 and c[i] >= lx + mult * a:       # swing low confirmed now
            conf[m] = i; piv[m] = lxi; pr[m] = lx; kd[m] = -1; m += 1
            dirn = 1
            hx = h[lxi]; hxi = lxi
            for q in range(lxi + 1, i + 1):
                if h[q] > hx:
                    hx = h[q]; hxi = q
            lx = l[i]; lxi = i
    return conf[:m], piv[:m], pr[:m], kd[:m]


def swings(f, method):
    """f: DataFrame with high, low, close, atr, seg. Returns dict of arrays (conf, piv, price, kind), sorted by conf."""
    kind, p = METHODS[method]
    h, l, c = (f[x].values.astype(np.float64) for x in ("high", "low", "close"))
    seg = f["seg"].values.astype(np.int64)
    if kind == "fractal":
        r = _fractal(h, l, seg, int(p))
    else:
        r = _zigzag(h, l, c, f["atr"].values.astype(np.float64), seg, float(p))
    o = np.argsort(r[0], kind="stable")
    return dict(conf=r[0][o], piv=r[1][o], price=r[2][o], kind=r[3][o])
