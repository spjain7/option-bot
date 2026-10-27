"""Chart-pattern calls on 3-hour candles (INST-PAT-001, research/search/REGISTRY_INST.md, 27-Oct-2026).

Only the two patterns that passed design AND hold-out with the live exits are used:
  FLAG               impulse ≥ 3 ATR in ≤ 5 candles, then a 3–8 candle pause (range ≤ 1.5 ATR, holding the upper half
                     of the impulse) → close beyond the pause.  Backtest (3h, after costs): win 80% / 79%, 9 of 9 instruments +.
  HEAD & SHOULDERS   three swing points, middle one extreme, shoulders within 1 ATR → close through the neckline.
                     Backtest (3h): win 79% / 85%, 8 of 9 instruments +.
Swing points are confirmed K candles after they form (no look-ahead). Same exits as the breakout calls:
stop 2 ATR, book 50% at T1 (1R) + stop to entry, trailing 3 ATR. ALERTS ONLY – no orders.
"""
import numpy as np
import pandas as pd
from crude import indicators as I

K = 3


def _pivots(h, l):
    n = len(h)
    ph, pl = np.zeros(n, bool), np.zeros(n, bool)
    for i in range(K, n - K):
        ph[i] = h[i] == h[i - K:i + K + 1].max()
        pl[i] = l[i] == l[i - K:i + K + 1].min()
    return ph, pl


def detect(df, kinds=("hs", "flag")):
    """Pattern completed on the LAST candle of df: (side +1/-1/0, pattern name, neckline/level)."""
    o, h, l, c = (df[x].values.astype(float) for x in ("open", "high", "low", "close"))
    a = I.atr(df, 14).values
    n = len(c)
    if n < 40 or not a[-1] > 0:
        return 0, None, None
    i = n - 1
    ph, pl = _pivots(h, l)
    lows = [j for j in range(n - K) if pl[j] and j + K <= i]
    highs = [j for j in range(n - K) if ph[j] and j + K <= i]
    # double bottom / top (stock futures only – STOCK-PAT-001)
    if "double" in kinds and len(lows) >= 2:
        l1, l2 = lows[-2:]
        hb = [x for x in highs if l1 < x < l2]
        if hb and l2 - l1 >= 5 and abs(l[l1] - l[l2]) <= 0.5 * a[i] and i - l2 <= 30:
            neck = max(h[x] for x in hb)
            if c[i] > neck >= c[i - 1]:
                return 1, "DOUBLE BOTTOM", neck
    if "double" in kinds and len(highs) >= 2:
        h1, h2 = highs[-2:]
        lb = [x for x in lows if h1 < x < h2]
        if lb and h2 - h1 >= 5 and abs(h[h1] - h[h2]) <= 0.5 * a[i] and i - h2 <= 30:
            neck = min(l[x] for x in lb)
            if c[i] < neck <= c[i - 1]:
                return -1, "DOUBLE TOP", neck
    # head & shoulders (inverse = bullish)
    if "hs" in kinds and len(lows) >= 3:
        a1, b1, c1 = lows[-3:]
        if l[b1] < l[a1] and l[b1] < l[c1] and abs(l[a1] - l[c1]) <= a[i] and i - c1 <= 30:
            hb = [x for x in highs if a1 < x < c1]
            if hb:
                neck = max(h[x] for x in hb)
                if c[i] > neck >= c[i - 1]:
                    return 1, "INVERSE HEAD & SHOULDERS", neck
    if "hs" in kinds and len(highs) >= 3:
        a1, b1, c1 = highs[-3:]
        if h[b1] > h[a1] and h[b1] > h[c1] and abs(h[a1] - h[c1]) <= a[i] and i - c1 <= 30:
            lb = [x for x in lows if a1 < x < c1]
            if lb:
                neck = min(l[x] for x in lb)
                if c[i] < neck <= c[i - 1]:
                    return -1, "HEAD & SHOULDERS", neck
    # flag
    for m in (range(3, 9) if "flag" in kinds else ()):
        s0 = i - m
        if s0 - 6 < 0:
            break
        imp = c[s0 - 1] - c[s0 - 6]
        hi_, lo_ = h[s0:i].max(), l[s0:i].min()
        if hi_ - lo_ > 1.5 * a[i]:
            continue
        if imp >= 3 * a[i] and lo_ > c[s0 - 6] + imp / 2 and c[i] > hi_:
            return 1, "BULL FLAG", hi_
        if imp <= -3 * a[i] and hi_ < c[s0 - 6] + imp / 2 and c[i] < lo_:
            return -1, "BEAR FLAG", lo_
    return 0, None, None


def evaluate(df, kinds=("hs", "flag")):
    """Same output shape as breakout.evaluate, plus 'pattern' and 'level'."""
    if df is None or len(df) < 60:
        return dict(side=None, why="not enough candles for patterns")
    s, name, lvl = detect(df, kinds)
    c, v = df["close"], df["volume"].astype(float)
    va = v.rolling(20).mean().shift(1).iloc[-1]
    x = df.iloc[-1]
    out = dict(candle=str(x.time), close=float(x.close), atr=float(I.atr(df, 14).iloc[-1]),
               ema200=float(I.ema(c, 200).iloc[-1]), vol_x=float(x.volume / va) if va and va > 0 else None,
               adx=float(I.adx(df).iloc[-1]), rsi=float(I.rsi(c, 14).iloc[-1]), hh=None, ll=None,
               pattern=name, level=lvl)
    return dict(out, side={1: "BUY", -1: "SELL"}.get(s), why=None if s else "no pattern")


def reason_msg(name, tf, sig, levels, oi=None, plan=None, note=None):
    s = 1 if sig["side"] == "BUY" else -1
    f = lambda v: f"{v:,.2f}" if abs(v) < 1000 else f"{v:,.0f}"
    pts = [f"📐 Pattern: {sig['pattern']} completed – candle closed at {f(sig['close'])}, "
           f"{'above' if s > 0 else 'below'} the {'flag' if 'FLAG' in sig['pattern'] else 'neckline'} {f(sig['level'])}"]
    if sig.get("vol_x"):
        pts.append(f"🔊 Volume: {sig['vol_x']:.1f}× normal")
    pts.append(f"🧭 200 EMA {f(sig['ema200'])}: price {'above' if sig['close'] > sig['ema200'] else 'below'}")
    pts.append(f"💪 ADX {sig['adx']:.0f} · 📊 RSI {sig['rsi']:.0f}")
    if oi and oi.get("label"):
        pts.append(f"🏦 OI: {oi['label']} ({oi['chg_pct']:+.2f}% in {oi['gap_min']:.0f} min)")
    pts.append(note or ("📚 Backtest 2022-26 (3h, after costs, book 50% at T1 + stop to entry): flags won ~80%, "
                        "head & shoulders ~79-85% of trades – not guaranteed."))
    return "\n".join([f"💡 {sig['side']} {name} – {sig['pattern']} – details & reason", "━━━━━━━━━━━━━━━━━━",
                      *(plan or []), *pts, "Backtested, not guaranteed · not investment advice."])
