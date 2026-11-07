"""Family C – market structure from confirmed swings (causal; swing usable from bar conf+1).

State: up if the last two confirmed highs are rising AND the last two lows are rising (HH+HL); down if both falling;
otherwise neutral. Internal vs external structure = the swing method (f2 internal ... f5 / z3 external).
Events (level = broken swing price, inv):
  BOS     close beyond the last swing high (state up) -> BUY / beyond the last swing low (state down) -> SELL
          inv = last swing low (BUY) / high (SELL)
  CHOCH   close beyond the last swing AGAINST the state (state down, close above last swing high -> BUY), inv likewise
  BRKN    close beyond the last swing high/low while state neutral
  BOS_RET within 10 bars after a BOS/CHOCH, price trades back to the broken level (<= 0.15 ATR, may pierce <= 0.3 ATR) and
          closes beyond it -> with the break ("first pull-back after BOS"); inv = bar extreme
Each swing level can be broken once. Failed BOS = events.fails on BOS/CHOCH/BRKN (family G).
g1 = state (1/0/-1), g2 = distance of the close beyond the level in ATR, g3 = size of the leg (last high - last low) in ATR.
"""
from research.mcxe003.events import Sink


def detect(f, sw):
    h, l, c, a, seg = (f[x].values for x in ("high", "low", "close", "atr", "seg"))
    n = len(c); s = Sink()
    conf, piv, pr, kd = sw["conf"], sw["piv"], sw["price"], sw["kind"]
    ptr = 0; H = []; L = []; usedH = usedL = -1; pend = []
    for i in range(1, n):
        if seg[i] != seg[i - 1]:
            H, L, pend = [], [], []; usedH = usedL = -1
        while ptr < len(conf) and conf[ptr] < i:
            if seg[piv[ptr]] == seg[i]:
                (H if kd[ptr] == 1 else L).append((piv[ptr], pr[ptr]))
            ptr += 1
        A = a[i]
        if not A > 0 or not H or not L:
            continue
        st = 0
        if len(H) >= 2 and len(L) >= 2:
            if H[-1][1] > H[-2][1] and L[-1][1] > L[-2][1]:
                st = 1
            elif H[-1][1] < H[-2][1] and L[-1][1] < L[-2][1]:
                st = -1
        leg = (H[-1][1] - L[-1][1]) / A
        hp, hv = H[-1]; lp, lv = L[-1]
        if hp != usedH and c[i] > hv and c[i - 1] <= hv:
            nm = "BOS" if st == 1 else ("CHOCH" if st == -1 else "BRKN")
            s.add(i, 1, "C", nm, hv, lv, st, (c[i] - hv) / A, leg); usedH = hp; pend.append((1, hv, i))
        if lp != usedL and c[i] < lv and c[i - 1] >= lv:
            nm = "BOS" if st == -1 else ("CHOCH" if st == 1 else "BRKN")
            s.add(i, -1, "C", nm, lv, hv, st, (lv - c[i]) / A, leg); usedL = lp; pend.append((-1, lv, i))
        keep = []
        for sd, lev, ib in pend:
            if i - ib > 10:
                continue
            if i > ib and sd > 0 and l[i] <= lev + 0.15 * A and l[i] >= lev - 0.3 * A and c[i] > lev:
                s.add(i, 1, "C", "BOS_RET", lev, l[i], st, i - ib, leg); continue
            if i > ib and sd < 0 and h[i] >= lev - 0.15 * A and h[i] <= lev + 0.3 * A and c[i] < lev:
                s.add(i, -1, "C", "BOS_RET", lev, h[i], st, i - ib, leg); continue
            keep.append((sd, lev, ib))
        pend = keep
    return s.frame()
