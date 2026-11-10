"""MCX-REV – reversal-candle strategies only (owner 10-Nov: "check now only reversal candle based strategy").
7 commodities, BUY (bullish reversal) and SELL (bearish reversal), timeframes 15-min (intraday, out by the session end),
1-hour (max 3 sessions), 3-hour (max 8 sessions) and daily (max 15 sessions).
Candles (mirror for SELL): hammer / pin bar, bullish engulfing, morning star, piercing line, tweezer bottom, bullish harami,
dragonfly doji, key reversal (new 20-bar low then close above the previous close).
Context (one at a time, plus 'none'): at a 20-bar extreme · RSI(14) oversold (< 35 within 3 bars) · volume >= 1.5x ·
with the larger trend (EMA20 > EMA50) · against it · previous-day low / high within 0.5 ATR (15-min, 1-hour only).
Entry: next bar's open, or CONFIRMED (a later close above the candle's high within 2 bars -> next open).
Stop: beyond the candle's extreme by 0.1 ATR (kept between 0.5 and 3 ATR). Targets 0.5R, 1R, 1.5R, 2R, 3R. Real MCX costs.
Periods: FOCUS 1-Feb-2026 … 3-Nov-2026, CHECK 2023 … Jan-2026. Results per commodity AND pooled over the 7 commodities.
GOOD = pooled: net R > 0 and PF >= 1.2 in BOTH periods with >= 100 trades in FOCUS and >= 300 in CHECK.
python -m research.mcxhw.reversal"""
import json
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD  # noqa: E402
from research.mcxhw.search import bars, wilder, sim, FOCUS0  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
TFS = (("15m", 15, 400), ("1h", 60, 45), ("3h", 180, 40), ("1d", 1440, 15))
RS = (0.5, 1.0, 1.5, 2.0, 3.0)


def candles(b, tf):
    o, h, l, c, v = (pd.Series(b[x].values.astype(float)) for x in ("open", "high", "low", "close", "volume"))
    pc = c.shift(1)
    atr = pd.Series(wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14))
    body, rng = (c - o).abs(), (h - l).replace(0, np.nan)
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    up, dn = c > o, c < o
    mid1 = (o.shift(1) + c.shift(1)) / 2
    P = {}
    P["hammer", 1] = (lw >= 2 * body) & (uw <= 0.3 * rng) & (rng >= 0.7 * atr)
    P["hammer", -1] = (uw >= 2 * body) & (lw <= 0.3 * rng) & (rng >= 0.7 * atr)                      # shooting star
    P["engulfing", 1] = up & dn.shift(1) & (c >= o.shift(1)) & (o <= c.shift(1)) & (body >= 0.5 * atr)
    P["engulfing", -1] = dn & up.shift(1) & (c <= o.shift(1)) & (o >= c.shift(1)) & (body >= 0.5 * atr)
    small1 = body.shift(1) <= 0.3 * rng.shift(1)
    P["star", 1] = dn.shift(2) & (body.shift(2) >= 0.6 * rng.shift(2)) & small1 & up & (c > (o.shift(2) + c.shift(2)) / 2)
    P["star", -1] = up.shift(2) & (body.shift(2) >= 0.6 * rng.shift(2)) & small1 & dn & (c < (o.shift(2) + c.shift(2)) / 2)
    P["piercing", 1] = dn.shift(1) & (body.shift(1) >= 0.6 * rng.shift(1)) & up & (o < l.shift(1)) & (c > mid1) & (c < o.shift(1))
    P["piercing", -1] = up.shift(1) & (body.shift(1) >= 0.6 * rng.shift(1)) & dn & (o > h.shift(1)) & (c < mid1) & (c > o.shift(1))  # dark cloud
    P["tweezer", 1] = dn.shift(1) & up & ((l - l.shift(1)).abs() <= 0.05 * atr) & (c > mid1)
    P["tweezer", -1] = up.shift(1) & dn & ((h - h.shift(1)).abs() <= 0.05 * atr) & (c < mid1)
    P["harami", 1] = dn.shift(1) & (body.shift(1) >= 0.6 * rng.shift(1)) & up & (h <= o.shift(1)) & (l >= c.shift(1))
    P["harami", -1] = up.shift(1) & (body.shift(1) >= 0.6 * rng.shift(1)) & dn & (l >= o.shift(1)) & (h <= c.shift(1))
    P["doji", 1] = (body <= 0.1 * rng) & (lw >= 0.6 * rng) & (rng >= 0.7 * atr)                       # dragonfly
    P["doji", -1] = (body <= 0.1 * rng) & (uw >= 0.6 * rng) & (rng >= 0.7 * atr)                      # gravestone
    ll20, hh20 = l.shift(1).rolling(20).min(), h.shift(1).rolling(20).max()
    P["key_reversal", 1] = (l < ll20) & (c > c.shift(1)) & (c > o)
    P["key_reversal", -1] = (h > hh20) & (c < c.shift(1)) & (c < o)
    d = c.diff()
    rsi = 100 - 100 / (1 + pd.Series(wilder(d.clip(lower=0).values, 14)) / pd.Series(wilder((-d).clip(lower=0).values, 14)).replace(0, np.nan))
    e20, e50 = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    rv = v / v.rolling(20).mean().shift(1)
    lo3 = l.rolling(3).min(); hi3 = h.rolling(3).max()
    ctx = {1: {"none": pd.Series(True, index=c.index), "at_20bar_low": lo3 <= ll20 + 0.25 * atr, "rsi_oversold": rsi.rolling(3).min() < 35,
               "volume_1.5x": rv >= 1.5, "with_trend": e20 > e50, "against_trend": e20 < e50},
           -1: {"none": pd.Series(True, index=c.index), "at_20bar_high": hi3 >= hh20 - 0.25 * atr, "rsi_overbought": rsi.rolling(3).max() > 65,
                "volume_1.5x": rv >= 1.5, "with_trend": e20 < e50, "against_trend": e20 > e50}}
    if tf in ("15m", "1h"):
        day = b["time"].dt.normalize()
        dl = pd.Series(l.values, index=b.index).groupby(day.values).transform("min"); dh = pd.Series(h.values, index=b.index).groupby(day.values).transform("max")
        first = ~day.duplicated()
        pdl = pd.Series(np.where(first, np.nan, np.nan)); 
        dlow = l.groupby(day.values).min(); dhigh = h.groupby(day.values).max()
        pdl = day.map(dlow.shift(1)).reset_index(drop=True); pdh = day.map(dhigh.shift(1)).reset_index(drop=True)
        ctx[1]["prev_day_low"] = (lo3 - pdl).abs() <= 0.5 * atr
        ctx[-1]["prev_day_high"] = (hi3 - pdh).abs() <= 0.5 * atr
    # stop distance from the next open is not known yet -> use distance from the signal close to the pattern extreme
    ext_lo = pd.concat([l, l.shift(1), l.shift(2)], axis=1).min(axis=1); ext_hi = pd.concat([h, h.shift(1), h.shift(2)], axis=1).max(axis=1)
    risk = {1: (c - ext_lo + 0.1 * atr).clip(lower=0.5 * atr, upper=3 * atr), -1: (ext_hi - c + 0.1 * atr).clip(lower=0.5 * atr, upper=3 * atr)}
    return P, ctx, risk, atr, h, l, c


def confirmed(sig, sd, h, l, c):
    """a close beyond the signal candle's high (low) within the next 2 bars."""
    out = np.zeros(len(sig), bool); s = sig.values; hv, lv, cv = h.values, l.values, c.values
    for i in np.where(s)[0]:
        for j in (i + 1, i + 2):
            if j < len(s) and ((sd > 0 and cv[j] > hv[i]) or (sd < 0 and cv[j] < lv[i])):
                out[j] = True; break
    return out


def main():
    t0 = time.time()
    per, pooled = [], {}
    for name in MD.NAMES:
        d5 = MD.LM.load(name, "FIVE_MINUTE")
        mult = MD.REG[name]["mult"]; cost = MD.real_cost(name, float(d5.close.iloc[-1]))
        for tf, minutes, hold in TFS:
            b = bars(d5, minutes)
            if len(b) < 300:
                continue
            P, ctx, risk, atr, h, l, c = candles(b, tf)
            o = b["open"].values.astype(float)
            hm = (b["time"].dt.hour * 60 + b["time"].dt.minute).values
            day = b["time"].dt.normalize().values.astype("datetime64[D]").astype(np.int64)
            grp = day if tf == "15m" else np.cumsum(b["sw"].fillna(False).astype(bool).values).astype(np.int64)
            ok = ((hm >= 570) & (hm <= 22 * 60)) if tf == "15m" else np.ones(len(b), bool)
            tm = b["time"].values
            for (pat, sd), sig in P.items():
                sig = sig.fillna(False).astype(bool)
                for cn, cm in ctx[sd].items():
                    base = sig & cm.fillna(False).astype(bool)
                    for entry in ("next_open", "confirmed"):
                        s2 = (base.values if entry == "next_open" else confirmed(base, sd, h, l, c)) & ok
                        if s2.sum() < 8:
                            continue
                        rk = risk[sd].values if entry == "next_open" else risk[sd].shift(1).bfill().values + 0.0
                        for R in RS:
                            ei, net, _ = sim(o, h.values, l.values, c.values, s2, sd, rk, R, 1.0, grp, hold, cost)
                            if not len(ei):
                                continue
                            r = net / rk[ei - 1]
                            key = (tf, pat, "BUY" if sd > 0 else "SELL", cn, entry, R)
                            f = tm[ei] >= np.datetime64(FOCUS0)
                            pooled.setdefault(key, []).append(pd.DataFrame(dict(name=name, t=tm[ei], r=r, rs=net * mult, focus=f)))
        print(name, f"{time.time() - t0:.0f}s", flush=True)

    def st(x):
        if not len(x):
            return dict(n=0)
        w = x.r > 0; gp, gl = x.r[w].sum(), -x.r[~w].sum()
        return dict(n=len(x), win=round(100 * w.mean(), 1), R=round(x.r.mean(), 3), PF=round(gp / gl, 2) if gl > 0 else 99.0,
                    rs_lot=round(x.rs.mean()), names_pos=int((x.groupby("name").r.mean() > 0).sum()))
    rows = []
    for key, parts in pooled.items():
        X = pd.concat(parts, ignore_index=True)
        row = dict(zip(("tf", "candle", "side", "context", "entry", "target_R"), key))
        row.update({f"F_{k}": v for k, v in st(X[X.focus]).items()}); row.update({f"C_{k}": v for k, v in st(X[~X.focus]).items()})
        rows.append(row)
    L = pd.DataFrame(rows)
    L["GOOD"] = (L.F_n >= 100) & (L.C_n >= 300) & (L.F_R > 0) & (L.C_R > 0) & (L.F_PF >= 1.2) & (L.C_PF >= 1.2)
    L["tf_n_ok"] = np.where(L.tf.isin(["3h", "1d"]), (L.F_n >= 30) & (L.C_n >= 100), (L.F_n >= 100) & (L.C_n >= 300))
    L["GOOD_small"] = L.tf_n_ok & (L.F_R > 0) & (L.C_R > 0) & (L.F_PF >= 1.2) & (L.C_PF >= 1.2)
    L.to_csv(OUT / "reversal_pooled.csv", index=False)
    json.dump(dict(variants=int(len(L)), good=int(L.GOOD.sum()), good_incl_small_tf=int(L.GOOD_small.sum()), seconds=round(time.time() - t0)),
              open(OUT / "reversal_summary.json", "w"))
    c_ = ["tf", "candle", "side", "context", "entry", "target_R", "F_n", "F_win", "F_R", "F_PF", "F_rs_lot", "F_names_pos", "C_n", "C_win", "C_R", "C_PF", "C_rs_lot", "C_names_pos"]
    print("variants", len(L), "GOOD", int(L.GOOD.sum()), "GOOD incl. 3h/1d smaller samples", int(L.GOOD_small.sum()))
    print(L[L.GOOD_small].sort_values("C_R", ascending=False)[c_].head(25).to_string(index=False))
    base = L[(L.context == "none") & (L.entry == "next_open") & (L.target_R == 1.0)]
    print(base.sort_values(["tf", "candle"])[c_].to_string(index=False))
    a = L[L.tf_n_ok]
    print(a.groupby("tf").agg(n=("F_R", "size"), F_R=("F_R", "mean"), C_R=("C_R", "mean"), both_pos=("GOOD_small", "sum")).round(3).to_string())
    print(a.groupby("context").agg(n=("F_R", "size"), F_R=("F_R", "mean"), C_R=("C_R", "mean")).round(3).to_string())
    print(a.groupby("entry").agg(F_R=("F_R", "mean"), C_R=("C_R", "mean")).round(3).to_string())
    print(a.groupby("target_R").agg(F_win=("F_win", "mean"), C_win=("C_win", "mean"), F_R=("F_R", "mean"), C_R=("C_R", "mean")).round(3).to_string())


if __name__ == "__main__":
    main()
