"""Family D – liquidity sweeps (causal).

Levels known at bar i (all from completed data):
  PD   previous session high / low (intraday) ; previous 20-bar high / low (daily frames)
  OR   opening-range high / low (first 60 minutes; MCX 09:00-10:00, NSE 09:15-10:15), only after the range is complete
  DAY  running session high / low before this bar (intraday only)
  SW   last confirmed swing high / low (swing method)
  EQ   equal highs / lows: the last two confirmed swing highs (lows) within 0.1 ATR -> their max (min)
Events (each level swept at most once per session / once per swing):
  SWP_<L>       bar trades beyond the level and CLOSES back inside -> reversal (high swept -> SELL); inv = bar extreme
  SWPC_<L>      sweep followed within 8 bars by a close through the last swing on the other side (sweep + CHoCH/BOS)
                -> reversal; inv = sweep extreme
  SWPF_<L>      sweep failure: within 3 bars after a sweep, a close beyond the swept level -> continuation (with the
                original direction of the level break); inv = low (BUY) / high (SELL) of the sweep bar
g1 = sweep depth beyond the level in ATR, g2 = bars between sweep and event (0 for SWP), g3 = wick share of the sweep bar.
"""
import numpy as np
from research.mcxe003.events import Sink


def detect(f, sw, intraday=True):
    o, h, l, c, a, seg = (f[x].values for x in ("open", "high", "low", "close", "atr", "seg"))
    n = len(c); s = Sink()
    day = f.day.values
    if intraday:
        pdh, pdl = f.pdh.values, f.pdl.values
        m = f.m.values
        mkt = f.attrs.get("market", "MCX")
        or_end = 600 if mkt == "MCX" else 615
    else:
        pdh = f.high.rolling(20).max().shift(1).values; pdl = f.low.rolling(20).min().shift(1).values
    conf, piv, pr, kd = sw["conf"], sw["piv"], sw["price"], sw["kind"]
    ptr = 0; H = []; L = []
    used = set(); pend = []
    dh = dl = np.nan; orh = orl = np.nan
    for i in range(1, n):
        if seg[i] != seg[i - 1]:
            H, L, pend = [], [], []
        newday = day[i] != day[i - 1]
        if intraday and newday:
            dh = dl = np.nan; orh = orl = np.nan; used = {u for u in used if u[0] in ("SW", "EQ")}
        while ptr < len(conf) and conf[ptr] < i:
            if seg[piv[ptr]] == seg[i]:
                (H if kd[ptr] == 1 else L).append((piv[ptr], pr[ptr]))
            ptr += 1
        A = a[i]
        if A > 0:
            lv = []
            if pdh[i] == pdh[i]:
                lv += [("PD", 1, pdh[i], day[i] if intraday else i // 20), ("PD", -1, pdl[i], day[i] if intraday else i // 20)]
            if intraday:
                if orh == orh and m[i] >= or_end:
                    lv += [("OR", 1, orh, day[i]), ("OR", -1, orl, day[i])]
                if dh == dh:
                    lv += [("DAY", 1, dh, (day[i], dh)), ("DAY", -1, dl, (day[i], dl))]
            if H:
                lv.append(("SW", 1, H[-1][1], H[-1][0]))
            if L:
                lv.append(("SW", -1, L[-1][1], L[-1][0]))
            if len(H) >= 2 and abs(H[-1][1] - H[-2][1]) <= 0.1 * A:
                lv.append(("EQ", 1, max(H[-1][1], H[-2][1]), H[-1][0]))
            if len(L) >= 2 and abs(L[-1][1] - L[-2][1]) <= 0.1 * A:
                lv.append(("EQ", -1, min(L[-1][1], L[-2][1]), L[-1][0]))
            rng = h[i] - l[i]
            for nm, k, v, key in lv:
                if (nm, key, k) in used:
                    continue
                if k == 1 and h[i] > v and c[i] < v:
                    used.add((nm, key, k))
                    s.add(i, -1, "D", "SWP_" + nm, v, h[i], (h[i] - v) / A, 0, (h[i] - max(o[i], c[i])) / rng if rng > 0 else np.nan)
                    pend.append((nm, -1, v, i, h[i], l[i]))
                elif k == -1 and l[i] < v and c[i] > v:
                    used.add((nm, key, k))
                    s.add(i, 1, "D", "SWP_" + nm, v, l[i], (v - l[i]) / A, 0, (min(o[i], c[i]) - l[i]) / rng if rng > 0 else np.nan)
                    pend.append((nm, 1, v, i, h[i], l[i]))
                elif (k == 1 and c[i] > v) or (k == -1 and c[i] < v):
                    used.add((nm, key, k))                 # level taken out by a close: no later sweep of it
            keep = []
            for nm, sd, v, ib, sh_, sl_ in pend:
                if i == ib:
                    keep.append((nm, sd, v, ib, sh_, sl_)); continue
                if i - ib > 8:
                    continue
                if i - ib <= 3 and ((sd < 0 and c[i] > v) or (sd > 0 and c[i] < v)):
                    s.add(i, -sd, "D", "SWPF_" + nm, v, sl_ if sd < 0 else sh_, np.nan, i - ib); continue
                if sd < 0 and L and c[i] < L[-1][1] and c[i - 1] >= L[-1][1]:
                    s.add(i, -1, "D", "SWPC_" + nm, v, sh_, np.nan, i - ib); continue
                if sd > 0 and H and c[i] > H[-1][1] and c[i - 1] <= H[-1][1]:
                    s.add(i, 1, "D", "SWPC_" + nm, v, sl_, np.nan, i - ib); continue
                keep.append((nm, sd, v, ib, sh_, sl_))
            pend = keep
        if intraday:
            dh = h[i] if dh != dh else max(dh, h[i]); dl = l[i] if dl != dl else min(dl, l[i])
            if m[i] < or_end:
                orh = h[i] if orh != orh else max(orh, h[i]); orl = l[i] if orl != orl else min(orl, l[i])
    return s.frame()
