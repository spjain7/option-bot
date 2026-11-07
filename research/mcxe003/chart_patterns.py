"""Family F – classic chart patterns from confirmed swings (causal; a swing is usable from bar conf+1).
The event is the BREAKOUT close (detection time = completion). Patterns are formed only from swings of the same segment
and within the last MAXW bars. Tolerances in ATR at the event bar.
  DTOP / DBOT     two swing highs (lows) within 0.3 ATR, >= 5 bars apart, intermediate swing low (high) >= 1 ATR away
                  = neckline; close through the neckline -> SELL (BUY); inv = the higher top (lower bottom)
  HS / IHS        three swing highs L < H > R with H >= max(L, R) + 0.5 ATR and |L - R| <= 0.6 ATR; neckline = line
                  through the two swing lows between them; close through it -> SELL (inverse: BUY); inv = right shoulder
  TRI_ASC / TRI_DESC / TRI_SYM   last 2 highs / 2 lows: flat (<= 0.25 ATR) vs rising / falling (> 0.25 ATR) lines;
                  close beyond either line -> with the break (asc / desc are labelled with their classic side, but both
                  breaks are recorded, the side is the break direction)
  WEDGE_RISE / WEDGE_FALL   both lines rising (falling) and converging; close beyond either line -> with the break
  RECT            flat highs and flat lows, height >= 1.5 ATR; close beyond -> with the break
  FLAG            impulse >= 2.5 ATR over <= 5 bars, then a 3-8 bar pause with range <= 1.2 ATR not retracing > 50 %;
                  close beyond the pause in the impulse direction -> with impulse; inv = other side of the pause
  PENNANT         as FLAG but the pause bars' ranges are strictly shrinking (last 3)
  _RET variants   (DTOP/DBOT/HS/IHS) within 10 bars after the break: trade back to the neckline (<= 0.15 ATR) and close
                  beyond it again -> retest entry
Cup and handle: NOT implemented – no objective causal definition that does not depend on the later handle shape.
g1 = pattern height / ATR, g2 = pattern width in bars, g3 = break distance beyond the line / ATR.
"""
import numpy as np
from research.mcxe003.events import Sink

MAXW = 60


def detect(f, sw):
    o, h, l, c, a, seg = (f[x].values for x in ("open", "high", "low", "close", "atr", "seg"))
    n = len(c); s = Sink()
    conf, piv, pr, kd = sw["conf"], sw["piv"], sw["price"], sw["kind"]
    ptr = 0; H = []; L = []
    armed = {}                    # pattern key -> dict(state)
    pend_ret = []
    for i in range(1, n):
        if seg[i] != seg[i - 1]:
            H, L, armed, pend_ret = [], [], {}, []
        new = False
        while ptr < len(conf) and conf[ptr] < i:
            if seg[piv[ptr]] == seg[i]:
                (H if kd[ptr] == 1 else L).append((piv[ptr], pr[ptr])); new = True
            ptr += 1
        H = [x for x in H if i - x[0] <= MAXW]; L = [x for x in L if i - x[0] <= MAXW]
        A = a[i]
        if not A > 0:
            continue
        if new:
            armed = {}
            # double top / bottom
            if len(H) >= 2:
                (p1, v1), (p2, v2) = H[-2], H[-1]
                mids = [v for (q, v) in L if p1 < q < p2]
                if abs(v1 - v2) <= 0.3 * A and p2 - p1 >= 5 and mids and max(v1, v2) - min(mids) >= A:
                    armed["DTOP"] = dict(side=-1, lv=lambda k, m=min(mids): m, inv=max(v1, v2), ht=(max(v1, v2) - min(mids)) / A, w=i - p1)
            if len(L) >= 2:
                (p1, v1), (p2, v2) = L[-2], L[-1]
                mids = [v for (q, v) in H if p1 < q < p2]
                if abs(v1 - v2) <= 0.3 * A and p2 - p1 >= 5 and mids and max(mids) - min(v1, v2) >= A:
                    armed["DBOT"] = dict(side=1, lv=lambda k, m=max(mids): m, inv=min(v1, v2), ht=(max(mids) - min(v1, v2)) / A, w=i - p1)
            # head & shoulders
            if len(H) >= 3:
                (pa, va), (pb, vb), (pc, vc) = H[-3], H[-2], H[-1]
                ls = [(q, v) for (q, v) in L if pa < q < pc]
                if vb >= max(va, vc) + 0.5 * A and abs(va - vc) <= 0.6 * A and len(ls) >= 2:
                    (q1, w1), (q2, w2) = ls[0], ls[-1]
                    sl = (w2 - w1) / (q2 - q1) if q2 != q1 else 0.0
                    armed["HS"] = dict(side=-1, lv=lambda k, q1=q1, w1=w1, sl=sl: w1 + sl * (k - q1), inv=vc, ht=(vb - (w1 + w2) / 2) / A, w=i - pa)
            if len(L) >= 3:
                (pa, va), (pb, vb), (pc, vc) = L[-3], L[-2], L[-1]
                hs = [(q, v) for (q, v) in H if pa < q < pc]
                if vb <= min(va, vc) - 0.5 * A and abs(va - vc) <= 0.6 * A and len(hs) >= 2:
                    (q1, w1), (q2, w2) = hs[0], hs[-1]
                    sl = (w2 - w1) / (q2 - q1) if q2 != q1 else 0.0
                    armed["IHS"] = dict(side=1, lv=lambda k, q1=q1, w1=w1, sl=sl: w1 + sl * (k - q1), inv=vc, ht=((w1 + w2) / 2 - vb) / A, w=i - pa)
            # two-line patterns from the last two highs and lows
            if len(H) >= 2 and len(L) >= 2 and H[-2][0] != H[-1][0] and L[-2][0] != L[-1][0]:
                (h1p, h1), (h2p, h2) = H[-2], H[-1]; (l1p, l1), (l2p, l2) = L[-2], L[-1]
                su = (h2 - h1) / (h2p - h1p); sd_ = (l2 - l1) / (l2p - l1p)
                up = lambda k, h1p=h1p, h1=h1, su=su: h1 + su * (k - h1p)          # noqa: E731
                lo = lambda k, l1p=l1p, l1=l1, sd_=sd_: l1 + sd_ * (k - l1p)       # noqa: E731
                fh = abs(h2 - h1) <= 0.25 * A; fl = abs(l2 - l1) <= 0.25 * A
                rh = h2 > h1 + 0.25 * A; rl = l2 > l1 + 0.25 * A; dh = h2 < h1 - 0.25 * A; dl = l2 < l1 - 0.25 * A
                ht = (up(i) - lo(i)) / A; w = i - min(h1p, l1p)
                nm = None
                if fh and rl:
                    nm = "TRI_ASC"
                elif dh and fl:
                    nm = "TRI_DESC"
                elif dh and rl:
                    nm = "TRI_SYM"
                elif rh and rl and sd_ > su:
                    nm = "WEDGE_RISE"
                elif dh and dl and su < sd_:
                    nm = "WEDGE_FALL"
                elif fh and fl and (h1 + h2 - l1 - l2) / 2 >= 1.5 * A:
                    nm = "RECT"
                if nm and ht > 0:
                    armed[nm] = dict(side=0, up=up, lo=lo, ht=ht, w=w)
        # flag / pennant (no swings needed): impulse then pause, evaluated at each bar
        for nm_ in ("FLAG",):
            for pl in range(3, 9):
                st = i - pl                          # pause bars st+1 .. i-1? -> pause = bars [i-pl, i-1], event bar i
                ib = st - 5
                if ib < 1 or seg[ib] != seg[i]:
                    break
                ph_, pl_ = h[st:i].max(), l[st:i].min()
                if ph_ - pl_ > 1.2 * A:
                    continue
                imp = c[st - 1] - c[ib - 1]
                if abs(imp) < 2.5 * A:
                    continue
                sd = 1 if imp > 0 else -1
                retr = (c[st - 1] - pl_) / imp if sd > 0 else (ph_ - c[st - 1]) / -imp
                if retr > 0.5:
                    continue
                rg = h[st:i] - l[st:i]
                penn = len(rg) >= 3 and rg[-1] < rg[-2] < rg[-3]
                if sd > 0 and c[i] > ph_ and c[i - 1] <= ph_:
                    s.add(i, 1, "F", "PENNANT" if penn else "FLAG", ph_, pl_, abs(imp) / A, pl, (c[i] - ph_) / A)
                    break
                if sd < 0 and c[i] < pl_ and c[i - 1] >= pl_:
                    s.add(i, -1, "F", "PENNANT" if penn else "FLAG", pl_, ph_, abs(imp) / A, pl, (pl_ - c[i]) / A)
                    break
        # breakout checks of armed swing patterns
        done = []
        for nm, P in armed.items():
            if P["side"] != 0:
                v = P["lv"](i)
                if (P["side"] < 0 and c[i] < v and c[i - 1] >= P["lv"](i - 1)) or (P["side"] > 0 and c[i] > v and c[i - 1] <= P["lv"](i - 1)):
                    s.add(i, P["side"], "F", nm, v, P["inv"], P["ht"], P["w"], abs(c[i] - v) / A)
                    pend_ret.append((nm, P["side"], P["lv"], i, P["inv"], P["ht"], P["w"])); done.append(nm)
                elif (P["side"] < 0 and c[i] > P["inv"]) or (P["side"] > 0 and c[i] < P["inv"]):
                    done.append(nm)                              # invalidated before the break
            else:
                u, lw_ = P["up"](i), P["lo"](i)
                if u <= lw_:
                    done.append(nm); continue
                if c[i] > u and c[i - 1] <= P["up"](i - 1):
                    s.add(i, 1, "F", nm, u, lw_, P["ht"], P["w"], (c[i] - u) / A); done.append(nm)
                elif c[i] < lw_ and c[i - 1] >= P["lo"](i - 1):
                    s.add(i, -1, "F", nm, lw_, u, P["ht"], P["w"], (lw_ - c[i]) / A); done.append(nm)
        for nm in done:
            armed.pop(nm, None)
        keep = []
        for nm, sd, lvf, ib, inv, ht, w in pend_ret:
            if i - ib > 10 or i == ib:
                if i == ib:
                    keep.append((nm, sd, lvf, ib, inv, ht, w))
                continue
            v = lvf(i)
            if sd < 0 and h[i] >= v - 0.15 * A and c[i] < v:
                s.add(i, -1, "F", nm + "_RET", v, h[i], ht, w, (v - c[i]) / A); continue
            if sd > 0 and l[i] <= v + 0.15 * A and c[i] > v:
                s.add(i, 1, "F", nm + "_RET", v, l[i], ht, w, (c[i] - v) / A); continue
            keep.append((nm, sd, lvf, ib, inv, ht, w))
        pend_ret = keep
    return s.frame()
