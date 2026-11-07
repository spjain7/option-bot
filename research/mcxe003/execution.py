"""MCXE-003 stage-2 execution simulator (numba), one position at a time per stream.

sim_one(o, h, l, c, i, side, stop, tgtR, iend, cost, trail=0.0, atr=0.0, entry_mode=0, trig=nan, inv=nan, wait=3)
  signal at the CLOSE of bar i.
  entry_mode 0: market at open[i+1].
  entry_mode 1: stop order at `trig` valid for `wait` bars after i; cancelled if `inv` trades first; a bar that touches
                both trig and inv = NO TRADE (conservative); fill at max(trig, open) for BUY (gap -> open).
  stop: price level (fixed at the signal). R = |entry - stop| (must be > 0).
  exits (checked in this order inside every bar after entry): gap through stop -> open; stop touched -> stop price;
        target (tgtR > 0, never on the entry bar) -> target price; trailing stop (trail > 0: trail*atr behind the best
        close, only tightens); time exit at iend -> close[iend].
  cost: round-trip cost in price points, charged as cost / R.
returns (net_R, gross_R, exit_index, entry_index, mae_R, mfe_R); net_R = nan if no trade.
"""
import numpy as np
from numba import njit


@njit(cache=True)
def sim_one(o, h, l, c, i, side, stop, tgtR, iend, cost, trail=0.0, atr=0.0, entry_mode=0, trig=np.nan, inv=np.nan, wait=3):
    n = len(c)
    nan = np.nan
    if i + 1 >= n or i + 1 > iend:
        return nan, nan, -1, -1, nan, nan
    if entry_mode == 0:
        k0 = i + 1; e = o[k0]
    else:
        k0 = -1; e = nan
        for k in range(i + 1, min(iend, i + wait) + 1):
            hit_t = h[k] >= trig if side > 0 else l[k] <= trig
            hit_i = l[k] <= inv if side > 0 else h[k] >= inv
            if hit_t and hit_i:
                return nan, nan, -1, -1, nan, nan
            if hit_i:
                return nan, nan, -1, -1, nan, nan
            if hit_t:
                k0 = k
                e = max(trig, o[k]) if side > 0 else min(trig, o[k])
                break
        if k0 < 0:
            return nan, nan, -1, -1, nan, nan
    R = side * (e - stop)
    if not R > 0:
        return nan, nan, -1, -1, nan, nan
    st = stop; best = e; mae = 0.0; mfe = 0.0
    tg = e + side * tgtR * R if tgtR > 0 else nan
    px = nan; kx = iend
    for k in range(k0, iend + 1):
        if k > k0:
            if (side > 0 and o[k] <= st) or (side < 0 and o[k] >= st):
                px = o[k]; kx = k; break
        if (side > 0 and l[k] <= st) or (side < 0 and h[k] >= st):
            px = st; kx = k
            if k == k0 and ((side > 0 and o[k] <= st) or (side < 0 and o[k] >= st)):
                px = o[k]
            break
        adv = (l[k] - e) * side if side > 0 else (e - h[k])
        fav = (h[k] - e) if side > 0 else (e - l[k])
        mae = min(mae, adv / R); mfe = max(mfe, fav / R)
        if k > k0 and tgtR > 0:
            if (side > 0 and h[k] >= tg) or (side < 0 and l[k] <= tg):
                px = max(tg, o[k]) if side > 0 else min(tg, o[k]); kx = k; break
        if trail > 0 and atr > 0:
            if side > 0:
                best = max(best, c[k]); st = max(st, best - trail * atr)
            else:
                best = min(best, c[k]); st = min(st, best + trail * atr)
    if px != px:
        px = c[iend]; kx = iend
    g = side * (px - e) / R
    return g - cost / R, g, kx, k0, mae, mfe


@njit(cache=True)
def run_stream(o, h, l, c, I, S, STOP, IEND, COST, ATR, TRIG, INV, tgtR, trail, entry_mode, cost_mult):
    """events sorted by I; one position at a time: an event is skipped while a position is open."""
    m = len(I)
    out = np.full((m, 6), np.nan)
    busy = -1
    for q in range(m):
        if I[q] <= busy:
            continue
        r = sim_one(o, h, l, c, I[q], S[q], STOP[q], tgtR, IEND[q], cost_mult * COST[q], trail, ATR[q], entry_mode,
                    TRIG[q], INV[q], 3)
        out[q, 0] = r[0]; out[q, 1] = r[1]; out[q, 2] = r[2]; out[q, 3] = r[3]; out[q, 4] = r[4]; out[q, 5] = r[5]
        if r[2] >= 0:
            busy = r[2]
    return out
