"""BUY-only trade simulator (numba). Conservative fill rules:
  entry      next bar's OPEN after the signal bar (mode "open"), or a stop-entry: first bar within W bars whose high reaches
             the entry level, filled at max(open, level) (mode "stop").
  stop       checked FIRST inside every bar (worst case when stop and target share a bar). If a bar OPENS below the stop the
             fill is that open (gap-through, realistic loss beyond -1R). On a stop-entry bar the stop is checked on the same bar.
  validity   risk must be between min_risk and max_risk ATR; structural targets must give >= min_rr reward/risk at the fill.
  segments   no trade spans a contract switch; at the last bar of a segment the trade is closed at that bar's close.
  overlap    one position at a time per commodity per rule; the next signal must come after the exit bar.
Exit kinds: 0 fixed-R target, 1 level target (structural), 2 chandelier trail (k ATR from the highest close, never below the
initial stop), 3 time exit (close of bar entry+N-1), 4 partial (half at +1R, stop to break-even, rest at +3R).
All exits also stop at max_hold bars (closed at that bar's close)."""
import numpy as np
from numba import njit


@njit(cache=True)
def simulate(o, h, l, c, atr, seg, costf, sig, stop, elev, tgt, kind, Rmult, maxhold, ntime, trailk, win,
             min_risk, max_risk, min_rr):
    n = len(c)
    out_s = np.empty(n, np.int64); out_e = np.empty(n, np.int64); out_x = np.empty(n, np.int64)
    gR = np.empty(n); nR = np.empty(n); mfe = np.empty(n); mae = np.empty(n); why = np.empty(n, np.int64)
    m = 0; t = 0; rej = 0
    while t < n - 2:
        if not sig[t] or not np.isfinite(stop[t]) or not np.isfinite(atr[t]):
            t += 1; continue
        # ---- entry ----
        e = -1; px = np.nan
        if np.isnan(elev[t]):
            if seg[t + 1] == seg[t]:
                e = t + 1; px = o[e]
        else:
            for j in range(t + 1, min(t + 1 + win, n)):
                if seg[j] != seg[t] or l[j] < stop[t]:
                    break
                if h[j] >= elev[t]:
                    e = j; px = max(o[j], elev[t]); break
        if e < 0:
            t += 1; continue
        st = stop[t]; rk = px - st
        if rk < min_risk * atr[t] or rk > max_risk * atr[t] or rk <= 0:
            rej += 1; t += 1; continue
        if kind == 0 or kind == 4:
            tp = px + (Rmult if kind == 0 else 3.0) * rk
        elif kind == 1:
            tp = tgt[t]
            if not np.isfinite(tp) or (tp - px) / rk < min_rr:
                rej += 1; t += 1; continue
        else:
            tp = np.inf
        # ---- walk ----
        j = e; x = np.nan; reason = 0; hi_c = px; cur = st; half = False; bank = 0.0; best = 0.0; worst = 0.0
        while j < n:
            if j > e and o[j] <= cur:                                   # gap through the stop
                x = o[j]; reason = 1; break
            if l[j] <= cur:
                x = cur; reason = 1 if not half else 5; break
            if (kind == 0 or kind == 1 or kind == 4) and h[j] >= tp:
                x = max(o[j], tp) if j > e else tp; reason = 2; break
            if kind == 4 and not half and h[j] >= px + rk:
                half = True; bank = 0.5 * 1.0; cur = max(cur, px)
            best = max(best, (h[j] - px) / rk); worst = min(worst, (l[j] - px) / rk)
            if kind == 2:
                hi_c = max(hi_c, c[j]); cur = max(cur, hi_c - trailk * atr[j])
            if kind == 3 and j - e + 1 >= ntime:
                x = c[j]; reason = 3; break
            if j - e + 1 >= maxhold:
                x = c[j]; reason = 3; break
            if j == n - 1 or seg[j + 1] != seg[j]:
                x = c[j]; reason = 4; break
            j += 1
        if np.isnan(x):
            break
        best = max(best, (h[j] - px) / rk); worst = min(worst, (l[j] - px) / rk)
        g = (x - px) / rk
        if kind == 4:
            g = bank + 0.5 * g if half else g
        out_s[m] = t; out_e[m] = e; out_x[m] = j; gR[m] = g; nR[m] = g - costf[e] * px / rk
        mfe[m] = best; mae[m] = worst; why[m] = reason; m += 1
        t = j if j > t else t + 1
    return out_s[:m], out_e[:m], out_x[:m], gR[:m], nR[:m], mfe[:m], mae[:m], why[:m], rej
