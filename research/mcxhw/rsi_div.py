"""MCX-RD – RSI 75 / 25 extremes and multi-indicator divergence (owner's master instruction 10-Nov, sections 7, 8 and 26).
7 commodities, 15-min (intraday, flat by the session end), 1-hour, 3-hour and daily bars; every result is kept per
commodity AND pooled (section 26: nothing is assumed to carry over from one commodity to another).

RSI(14) events at the 75 side (mirrored at 25), each traded BOTH ways (reversal and continuation):
  cross_in (RSI crosses 75) · stay5 (5 bars beyond 75) · cross_out (back inside 75) · cross70 (through 70 after an extreme
  in the last 20 bars) · candle (extreme in the last 3 bars + engulfing / pin bar against it) · vol_exhaust (new 20-bar
  high on volume < 0.7x) · near_level (extreme within 0.25 ATR of the prior 50-bar high) · break5 (extreme in the last
  10 bars, close through the 5-bar low) · ema20 (extreme in the last 10 bars, close crosses EMA20) · rsi_div (extreme
  at the earlier pivot + regular RSI divergence).
Divergence: 12 indicators (RSI, MACD, MACD histogram, stochastic, stochastic RSI, CCI, MFI, OBV, ROC, momentum,
  Williams %R, volume) x regular / hidden x BUY / SELL, plus multi3 / multi5 (>= 3 / 5 indicators at once).
  Pivots need K=3 bars on both sides, so a divergence is only known – and only traded – 3 bars after the swing
  (no repainting; the delay is recorded). Context: none · RSI extreme at the pivot (<= 30 / >= 70) · volume >= 1.5x on
  the confirming bar · a reversal candle in the confirming 3 bars.
MCX history has no open interest (Angel does not serve historical MCX OI), so no OI condition is tested here.
Entry next bar's open. Stop beyond the 5-bar extreme by 0.1 ATR (kept between 0.5 and 3 ATR). Targets 1R, 2R, 3R.
Real MCX costs. Periods: DEV to 2024 · VALID 2025 · OOS 2026 (to 3-Nov).
PASS = net R > 0 and PF >= 1.2 in ALL three periods, >= 30 trades in each and >= 100 in total; BH-FDR 10 % on the
full-sample t-statistic is reported next to it.            python -m research.mcxhw.rsi_div"""
import json
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD  # noqa: E402
from research.mcxhw.search import bars, wilder, sim  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
TFS = (("15m", 15, 400), ("1h", 60, 45), ("3h", 180, 40), ("1d", 1440, 15))
RS = (1.0, 2.0, 3.0)
K = 3
VAL0, OOS0 = np.datetime64("2025-01-01"), np.datetime64("2026-01-01")


def rsi_of(x, n=14):
    d = x.diff()
    return 100 - 100 / (1 + pd.Series(wilder(d.clip(lower=0).values, n)) / pd.Series(wilder((-d).clip(lower=0).values, n)).replace(0, np.nan))


def indicators(o, h, l, c, v):
    I = {}
    I["rsi"] = rsi_of(c)
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    I["macd"] = macd; I["macd_hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    ll, hh = l.rolling(14).min(), h.rolling(14).max()
    I["stoch"] = (100 * (c - ll) / (hh - ll).replace(0, np.nan)).rolling(3).mean()
    r = I["rsi"]; rl, rh = r.rolling(14).min(), r.rolling(14).max()
    I["stoch_rsi"] = (100 * (r - rl) / (rh - rl).replace(0, np.nan)).rolling(3).mean()
    tp = (h + l + c) / 3; sma = tp.rolling(20).mean()
    I["cci"] = (tp - sma) / (0.015 * (tp - sma).abs().rolling(20).mean().replace(0, np.nan))
    mf = tp * v; up = tp > tp.shift(1)
    pos, neg = mf.where(up, 0).rolling(14).sum(), mf.where(~up, 0).rolling(14).sum()
    I["mfi"] = 100 - 100 / (1 + pos / neg.replace(0, np.nan))
    I["obv"] = (np.sign(c.diff()).fillna(0) * v).cumsum()
    I["roc"] = 100 * (c / c.shift(10) - 1); I["mom"] = c - c.shift(10)
    I["willr"] = -100 * (hh - c) / (hh - ll).replace(0, np.nan)
    I["volume"] = v.rolling(3).mean()
    return I


def divergences(h, l, I):
    """dict (indicator, kind, side) -> bool array, True on the bar where the divergence becomes known (pivot + K)."""
    n = len(l); out = {}
    w = 2 * K + 1
    pl = np.where((l == l.rolling(w, center=True).min()).values)[0]
    ph = np.where((h == h.rolling(w, center=True).max()).values)[0]
    lv, hv = l.values, h.values
    for side, piv, px in ((1, pl, lv), (-1, ph, hv)):
        if len(piv) < 2:
            continue
        p0, p1 = piv[:-1], piv[1:]
        ok = (p1 - p0 >= 5) & (p1 - p0 <= 60) & (p1 + K < n)
        p0, p1 = p0[ok], p1[ok]
        lower = px[p1] < px[p0] if side > 0 else px[p1] > px[p0]        # price made a new extreme
        cnt = np.zeros(n, np.int16)
        for name, s in I.items():
            x = s.values
            a, b = x[p0], x[p1]
            fin = np.isfinite(a) & np.isfinite(b)
            better = (b > a) if side > 0 else (b < a)                    # indicator did not confirm
            for kind, m in (("regular", lower & better & fin), ("hidden", ~lower & ~better & fin & (a != b))):
                z = np.zeros(n, bool); z[p1[m] + K] = True
                out[name, kind, side] = z
            cnt[p1[lower & better & fin] + K] += 1
        out["multi3", "regular", side] = cnt >= 3
        out["multi5", "regular", side] = cnt >= 5
        ext = np.full(n, np.nan); r = I["rsi"].values
        ext[p1 + K] = r[p1]; e0 = np.full(n, np.nan); e0[p1 + K] = r[p0]
        out["_rsi_at_pivot", side] = ext; out["_rsi_at_prev", side] = e0
    return out


def study(b, tf):
    o, h, l, c, v = (pd.Series(b[x].values.astype(float)) for x in ("open", "high", "low", "close", "volume"))
    pc = c.shift(1)
    atr = pd.Series(wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14))
    I = indicators(o, h, l, c, v); r = I["rsi"]
    body, rng = (c - o).abs(), (h - l).replace(0, np.nan)
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    bull = ((c > o) & (c.shift(1) < o.shift(1)) & (c >= o.shift(1)) & (o <= c.shift(1))) | ((lw >= 2 * body) & (uw <= 0.3 * rng))
    bear = ((c < o) & (c.shift(1) > o.shift(1)) & (c <= o.shift(1)) & (o >= c.shift(1))) | ((uw >= 2 * body) & (lw <= 0.3 * rng))
    rv = v / v.rolling(20).mean().shift(1)
    e20 = c.ewm(span=20, adjust=False).mean()
    hh20, ll20 = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
    hh50, ll50 = h.shift(5).rolling(50).max(), l.shift(5).rolling(50).min()
    D = divergences(h, l, I)
    S = {}                                                              # (family, event, zone, side) -> bool array
    for zone in (75, 25):
        hi = zone == 75; z = 1 if hi else -1                             # z=+1 overbought side
        beyond = (r >= 75) if hi else (r <= 25)
        ev = {}
        ev["cross_in"] = beyond & ~beyond.shift(1, fill_value=False)
        ev["stay5"] = (beyond.rolling(5).sum() == 5) & ~(beyond.shift(1, fill_value=False).rolling(5).sum() == 5)
        ev["cross_out"] = ~beyond & beyond.shift(1, fill_value=False)
        was = beyond.rolling(20).max().shift(1) > 0
        ev["cross70"] = was & (((r < 70) & (r.shift(1) >= 70)) if hi else ((r > 30) & (r.shift(1) <= 30)))
        ev["candle"] = (beyond.rolling(3).max() > 0) & (bear if hi else bull)
        ev["vol_exhaust"] = beyond & ((h > hh20) if hi else (l < ll20)) & (rv < 0.7)
        ev["near_level"] = beyond & (((h - hh50).abs() <= 0.25 * atr) if hi else ((l - ll50).abs() <= 0.25 * atr)) & ~beyond.shift(1, fill_value=False)
        was10 = beyond.rolling(10).max() > 0
        ev["break5"] = was10 & ((c < l.shift(1).rolling(5).min()) if hi else (c > h.shift(1).rolling(5).max()))
        ev["ema20"] = was10 & (((c < e20) & (c.shift(1) >= e20.shift(1))) if hi else ((c > e20) & (c.shift(1) <= e20.shift(1))))
        prev = D["_rsi_at_prev", -z]
        ev["rsi_div"] = pd.Series(D["rsi", "regular", -z] & ((prev >= 75) if hi else (prev <= 25)))
        for name, e in ev.items():
            e = e.fillna(False).astype(bool).values
            S["RSI", name, zone, -z] = e                                 # reversal
            S["RSI", name, zone, z] = e                                  # continuation
    for key, e in D.items():
        if key[0].startswith("_"):
            continue
        ind, kind, side = key
        rp = D["_rsi_at_pivot", side]
        cand = (bull if side > 0 else bear).rolling(K).max().fillna(0).astype(bool).values
        ctx = {"none": np.ones(len(c), bool), "rsi_extreme": (rp <= 30) if side > 0 else (rp >= 70),
               "volume_1.5x": (rv >= 1.5).fillna(False).values, "reversal_candle": cand}
        for cn, cm in ctx.items():
            S["DIV", f"{ind}:{kind}", cn, side] = e & cm
    lo5, hi5 = l.rolling(5).min(), h.rolling(5).max()
    risk = {1: (c - lo5 + 0.1 * atr).clip(lower=0.5 * atr, upper=3 * atr).values,
            -1: (hi5 - c + 0.1 * atr).clip(lower=0.5 * atr, upper=3 * atr).values}
    return S, risk, o.values, h.values, l.values, c.values


def st(r):
    if not len(r):
        return dict(n=0, win=np.nan, R=np.nan, PF=np.nan)
    w = r > 0; gp, gl = r[w].sum(), -r[~w].sum()
    return dict(n=len(r), win=round(100 * w.mean(), 1), R=round(r.mean(), 3), PF=round(min(gp / gl, 99), 2) if gl > 0 else 99.0)


def row_of(key, X):
    row = dict(zip(("tf", "family", "event", "zone_or_context", "side", "target_R"), key))
    row["side"] = "BUY" if key[4] > 0 else "SELL"
    per = np.where(X.t.values < VAL0, "DEV", np.where(X.t.values < OOS0, "VAL", "OOS"))
    for p in ("DEV", "VAL", "OOS"):
        row.update({f"{p}_{k}": v for k, v in st(X.r.values[per == p]).items()})
    row["n"] = len(X); row["R"] = round(X.r.mean(), 3)
    sd = X.r.std(ddof=1) if len(X) > 2 else np.nan
    row["t"] = round(X.r.mean() / (sd / np.sqrt(len(X))), 2) if sd and sd > 0 else np.nan
    row["rs_lot"] = round(X.rs.mean())
    row["PASS"] = bool(len(X) >= 100 and all(row[f"{p}_n"] >= 30 and row[f"{p}_R"] > 0 and row[f"{p}_PF"] >= 1.2 for p in ("DEV", "VAL", "OOS")))
    return row


def fdr(L, q=0.10):
    from math import erf, sqrt
    p = L.t.apply(lambda t: 1 - 0.5 * (1 + erf(t / sqrt(2))) if np.isfinite(t) else 1.0)
    o = np.argsort(p.values); m = len(p); thr = q * (np.arange(1, m + 1)) / m
    okk = p.values[o] <= thr; kmax = np.where(okk)[0].max() + 1 if okk.any() else 0
    f = np.zeros(m, bool); f[o[:kmax]] = True
    return f


def main():
    t0 = time.time(); pooled, rows_c = {}, []
    for name in MD.NAMES:
        d5 = MD.LM.load(name, "FIVE_MINUTE")
        mult = MD.REG[name]["mult"]; cost = MD.real_cost(name, float(d5.close.iloc[-1]))
        for tf, minutes, hold in TFS:
            b = bars(d5, minutes)
            if len(b) < 300:
                continue
            S, risk, o, h, l, c = study(b, tf)
            hm = (b["time"].dt.hour * 60 + b["time"].dt.minute).values
            day = b["time"].dt.normalize().values.astype("datetime64[D]").astype(np.int64)
            grp = day if tf == "15m" else np.cumsum(b["sw"].fillna(False).astype(bool).values).astype(np.int64)
            ok = ((hm >= 570) & (hm <= 22 * 60)) if tf == "15m" else np.ones(len(b), bool)
            tm = b["time"].values
            for (fam, evn, zc, sd), sig in S.items():
                s2 = sig & ok
                if s2.sum() < 8:
                    continue
                rk = risk[sd]
                for R in RS:
                    ei, net, _ = sim(o, h, l, c, s2, sd, rk, R, 1.0, grp, hold, cost)
                    if not len(ei):
                        continue
                    X = pd.DataFrame(dict(name=name, t=tm[ei], r=net / rk[ei - 1], rs=net * mult))
                    key = (tf, fam, evn, zc, sd, R)
                    pooled.setdefault(key, []).append(X)
                    rc = row_of(key, X); rc["commodity"] = name; rows_c.append(rc)
        print(name, f"{time.time() - t0:.0f}s", flush=True)
    L = pd.DataFrame([dict(row_of(k, pd.concat(p, ignore_index=True)), names_pos=int(sum(x.r.mean() > 0 for x in p)), names=len(p))
                      for k, p in pooled.items()])
    L["FDR10"] = fdr(L)
    C = pd.DataFrame(rows_c); C["FDR10"] = fdr(C)
    L.sort_values("t", ascending=False).to_csv(OUT / "rsi_div_pooled.csv", index=False)
    C.sort_values("t", ascending=False).to_csv(OUT / "rsi_div_by_commodity.csv", index=False)
    summ = dict(variants_pooled=len(L), pooled_pass=int(L.PASS.sum()), pooled_pass_and_fdr=int((L.PASS & L.FDR10).sum()),
                variants_by_commodity=len(C), commodity_pass=int(C.PASS.sum()), commodity_pass_and_fdr=int((C.PASS & C.FDR10).sum()),
                by_family_tf={f"{f}|{t}": dict(n=int(len(g)), passed=int(g.PASS.sum()), median_R=round(float(g.R.median()), 3))
                              for (f, t), g in L.groupby(["family", "tf"])})
    json.dump(summ, open(OUT / "rsi_div_summary.json", "w"), indent=1)
    print(json.dumps(summ, indent=1))
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    print(L[L.PASS].sort_values("t", ascending=False).head(40).to_string(index=False))


if __name__ == "__main__":
    main()
