"""Trade simulator (numba, one stock per call). Conventions (conservative):
* signal on bar t is known at its CLOSE; entry = OPEN of bar t+1 (intraday: only if t+1 is the same session and before
  the last-entry time; daily: skipped if bar t+1 is locked (high == low, circuit / no fill)).
* stop = entry − side × risk, risk = rdist[t] (price units, fixed at the signal); target = entry + side × R × risk
  (R = 0 -> no target). In every bar the STOP is checked before the target (also in the entry bar); a gap through the
  stop / target fills at the open.
* exits also: time (max_bars after entry, at that bar's close), trailing MA (close beyond trail[t] -> next open),
  intraday square-off at the close of the bar starting at `sq` minutes (15:15) or the session's last bar.
* one position per stock at a time; a new signal while in a trade is ignored.
Returns arrays: entry index, exit index, entry px, exit px, gross R, exit code (1 stop, 2 target, 3 time, 4 trail, 5 EOD)."""
import numpy as np
from numba import njit


@njit(cache=True)
def run(o, h, l, c, sig, side, rdist, R, max_bars, trail, day, mins, intraday, last_entry, sq):
    n = len(c)
    ei = np.empty(n, np.int64); xi = np.empty(n, np.int64)
    ep = np.empty(n); xp = np.empty(n); gr = np.empty(n); code = np.empty(n, np.int64)
    m = 0
    t = 0
    while t < n - 1:
        if not sig[t] or np.isnan(rdist[t]) or rdist[t] <= 0:
            t += 1; continue
        e = t + 1
        if intraday:
            if day[e] != day[t] or mins[t] > last_entry:
                t += 1; continue
        else:
            if h[e] <= l[e] or np.isnan(o[e]):
                t += 1; continue
        s = side
        px = o[e]
        rk = rdist[t]
        st = px - s * rk
        tg = px + s * R * rk if R > 0 else np.nan
        j = e
        xx, xc = np.nan, 0
        while j < n:
            if intraday and day[j] != day[e]:
                xx, xc = c[j - 1], 5; j -= 1; break
            if np.isnan(o[j]):
                j += 1; continue
            if j > e:                                     # gap at the open of a later bar
                if (s > 0 and o[j] <= st) or (s < 0 and o[j] >= st):
                    xx, xc = o[j], 1; break
                if R > 0 and ((s > 0 and o[j] >= tg) or (s < 0 and o[j] <= tg)):
                    xx, xc = o[j], 2; break
            if (s > 0 and l[j] <= st) or (s < 0 and h[j] >= st):
                xx, xc = st, 1; break
            if R > 0 and ((s > 0 and h[j] >= tg) or (s < 0 and l[j] <= tg)):
                xx, xc = tg, 2; break
            if intraday and (mins[j] >= sq or j == n - 1 or day[j + 1] != day[j]):
                xx, xc = c[j], 5; break
            if max_bars > 0 and j - e + 1 >= max_bars:
                xx, xc = c[j], 3; break
            if not np.isnan(trail[j]) and ((s > 0 and c[j] < trail[j]) or (s < 0 and c[j] > trail[j])):
                if j + 1 < n and not np.isnan(o[j + 1]):
                    xx, xc = o[j + 1], 4; j += 1; break
            j += 1
        if xc == 0:                                       # data ended: mark to the last close
            j = n - 1
            while j > e and np.isnan(c[j]):
                j -= 1
            xx, xc = c[j], 3
        ei[m] = e; xi[m] = j; ep[m] = px; xp[m] = xx; gr[m] = s * (xx - px) / rk; code[m] = xc
        m += 1
        t = j + 1 if j >= t else t + 1
    return ei[:m], xi[:m], ep[:m], xp[:m], gr[:m], code[:m]
