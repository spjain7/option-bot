"""CASHQ-DIV2 – port of "Divergence for Many Indicators v4" (LonesomeTheBlue, MPL 2.0; owner upload 10-Nov-2026) and a
controlled test of it on NSE cash daily data (BUY side: positive regular / positive hidden divergence).

Port (same logic as the Pine script): pivot lows on CLOSE with period prd (known prd bars later); on bar b, for each
indicator: only if indicator > indicator[1] or close > close[1] (confirmation); compare bar b-1 with each of the last
maxpp pivot lows within maxbars: regular = indicator higher but close lower than the pivot; hidden = indicator lower but
close higher; and neither the indicator nor the close may cut the straight line between the two points. The signal value
is the NUMBER of indicators showing a divergence on that bar ("Minimum Number of Divergence" = showlimit).
Indicators (script defaults): MACD, MACD histogram, RSI 14, Stochastic 14/3, CCI 10, Momentum 10, OBV, VW-MACD, CMF 21,
MFI 14. Groups for de-duplication: momentum (RSI, Stoch, CCI, MOM) · trend (MACD, Hist, VWMACD) · volume (OBV, CMF, MFI).
No look-ahead: everything on bar b uses bars <= b; entries at the next open.
python -m research.cashq.lonesome"""
import gc
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit
from . import data as D, ind as I, engine as EN, validate as V
from .daily_run import summarise

OUT = Path(__file__).resolve().parent / "results"
NAMES = ["MACD", "HIST", "RSI", "STOCH", "CCI", "MOM", "OBV", "VWMACD", "CMF", "MFI"]
GROUP = np.array([1, 1, 0, 0, 0, 0, 2, 1, 2, 2])        # 0 momentum, 1 trend, 2 volume


def indicators(o, h, l, c, v):
    c_, h_, l_, v_ = (pd.Series(x) for x in (c, h, l, v))
    e12, e26 = c_.ewm(span=12, adjust=False, min_periods=12).mean(), c_.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = e12 - e26
    hist = macd - macd.ewm(span=9, adjust=False, min_periods=9).mean()
    rsi = I.rsi(c_, 14)
    lo, hi = l_.rolling(14).min(), h_.rolling(14).max()
    stk = (100 * (c_ - lo) / (hi - lo).replace(0, np.nan)).rolling(3).mean()
    cci = (c_ - c_.rolling(10).mean()) / (0.015 * (c_ - c_.rolling(10).mean()).abs().rolling(10).mean().replace(0, np.nan))
    mom = c_ - c_.shift(10)
    obv = I.obv(c_, v_)
    vw = lambda n: (c_ * v_).rolling(n).sum() / v_.rolling(n).sum().replace(0, np.nan)
    vwmacd = vw(12) - vw(26)
    cmf = I.cmf(h_, l_, c_, v_, 21)
    mfi = I.mfi(h_, l_, c_, v_, 14)
    return np.vstack([x.values.astype(np.float64) for x in (macd, hist, rsi, stk, cci, mom, obv, vwmacd, cmf, mfi)])


@njit(cache=True)
def scan(c, X, prd, maxpp, maxbars):
    """-> reg[k, b], hid[k, b] (bool) for each indicator k on bar b – positive (bullish) divergences only."""
    n = len(c); K = X.shape[0]
    reg = np.zeros((K, n), np.bool_); hid = np.zeros((K, n), np.bool_)
    ppos = np.zeros(maxpp, np.int64); pval = np.zeros(maxpp); npv = 0
    for b in range(2 * prd + 2, n):
        p = b - prd                                   # pivot low at p, confirmed on bar b
        if not np.isnan(c[p]):
            ok = True
            for j in range(p - prd, p + prd + 1):
                if np.isnan(c[j]) or c[j] < c[p]:
                    ok = False; break
            if ok:
                for q in range(maxpp - 1, 0, -1):
                    ppos[q] = ppos[q - 1]; pval[q] = pval[q - 1]
                ppos[0] = p; pval[0] = c[p]
                if npv < maxpp:
                    npv += 1
        if np.isnan(c[b]) or np.isnan(c[b - 1]):
            continue
        for k in range(K):
            s = X[k]
            if np.isnan(s[b]) or np.isnan(s[b - 1]):
                continue
            if not (s[b] > s[b - 1] or c[b] > c[b - 1]):
                continue
            for cond in range(2):
                found = False
                for x in range(npv):
                    ln = b - ppos[x]
                    if ln > maxbars:
                        break
                    if ln <= 5 or np.isnan(s[b - ln]):
                        continue
                    if cond == 0:
                        hit = s[b - 1] > s[b - ln] and c[b - 1] < pval[x]
                    else:
                        hit = s[b - 1] < s[b - ln] and c[b - 1] > pval[x]
                    if not hit:
                        continue
                    sl1 = (s[b - 1] - s[b - ln]) / (ln - 1); v1 = s[b - 1] - sl1
                    sl2 = (c[b - 1] - c[b - ln]) / (ln - 1); v2 = c[b - 1] - sl2
                    arrived = True
                    for y in range(2, ln):
                        if s[b - y] < v1 or c[b - y] < v2:
                            arrived = False; break
                        v1 -= sl1; v2 -= sl2
                    if arrived:
                        found = True; break
                if found:
                    if cond == 0:
                        reg[k, b] = True
                    else:
                        hid[k, b] = True
    return reg, hid


def counts(W, prd):
    """wide frames: number of indicators (and of indicator groups) with a positive regular / hidden divergence."""
    c = W["close"]
    out = {k: np.zeros(c.shape, np.int8) for k in ("reg", "hid", "reg_g", "hid_g")}
    per = np.zeros((len(NAMES), c.shape[0], c.shape[1]), np.bool_) if prd == 5 else None
    for j, key in enumerate(c.columns):
        cc = c[key].values.astype(np.float64)
        if np.isfinite(cc).sum() < 300:
            continue
        X = indicators(W["open"][key].values, W["high"][key].values.astype(float), W["low"][key].values.astype(float), cc,
                       W["volume"][key].values.astype(float))
        r, hd = scan(cc, X, prd, 10, 100)
        out["reg"][:, j] = r.sum(0); out["hid"][:, j] = hd.sum(0)
        for g in range(3):
            out["reg_g"][:, j] += r[GROUP == g].any(0); out["hid_g"][:, j] += hd[GROUP == g].any(0)
        if per is not None:
            per[:, :, j] = r
    return {k: pd.DataFrame(v, index=c.index, columns=c.columns) for k, v in out.items()}, per


def main():
    t0 = time.time()
    W = D.daily_panel()
    for f in ("open", "high", "low", "close", "volume"):
        W[f] = W[f].astype("float64")
    o, h, l, c = W["open"], W["high"], W["low"], W["close"]
    e = W["elig"]
    F = dict(open=o, high=h, low=l, close=c, atr=I.atr(h, l, c, 14))
    ema50, ema200 = I.ema(c, 50), I.ema(c, 200)
    rsi = I.rsi(c, 14)
    rows, led = [], []
    exits = (("2R_20d", dict(R=2.0, mb=20, k=1.5, trail=None)), ("3R_40d", dict(R=3.0, mb=40, k=2.0, trail=None)),
             ("trail50", dict(R=0.0, mb=250, k=3.0, trail=ema50)))
    filters = {"none": None, "uptrend": c > ema200, "oversold": rsi.rolling(10).min() < 35}
    saved = {}
    for prd in (3, 5, 8):
        C, per = counts(W, prd)
        print(f"prd {prd}: scanned {time.time() - t0:.0f}s · bars with >=1 regular {int((C['reg'] > 0).values.sum()):,}", flush=True)
        if prd == 5:
            saved = dict(reg=C["reg"], hid=C["hid"], reg_g=C["reg_g"])
            for i, nm in enumerate(NAMES):                                  # single-indicator ablation
                sig = pd.DataFrame(per[i], index=c.index, columns=c.columns) & e
                T = EN.daily_trades(F, sig, 1.5 * F["atr"], 1, 2.0, 20)
                T["strategy"], T["R"] = f"L5_only_{nm}", 2.0
                rows.append(summarise(f"L5_only_{nm}", "DIVERGENCE", T, dict(params="prd 5, regular, single indicator, 2R / 1.5 ATR / 20 d", R=2.0, hold="swing", side="LONG")))
            del per
        for typ in ("reg", "hid", "reg_g"):
            for N in ((1, 2, 3, 4, 5, 6) if typ != "reg_g" else (2, 3)):
                base = (C[typ] >= N) & e
                for fn, fm in filters.items():
                    sig = base if fm is None else base & fm.fillna(False)
                    for xn, x in exits:
                        T = EN.daily_trades(F, sig, x["k"] * F["atr"], 1, x["R"], x["mb"], trail=x["trail"])
                        if not len(T):
                            continue
                        nm = f"L{prd}_{typ}{N}_{fn}_{xn}"
                        T["strategy"], T["R"] = nm, x["R"]
                        rows.append(summarise(nm, "DIVERGENCE", T, dict(params=f"prd {prd}, {typ} >= {N}, filter {fn}, exit {xn}", R=x["R"], hold=xn, side="LONG")))
                        if prd == 5 and typ == "reg" and fn == "none":
                            led.append(T)
        del C; gc.collect()
    L = pd.DataFrame(rows)
    L["exp_id"] = "CQL-" + L["strategy"]
    sel = L.apply(V.verdict, axis=1) != "NOT_SELECTED"
    L["OOS_q"] = 1.0
    L.loc[sel, "OOS_q"] = V.bh(L.loc[sel, "OOS_p"].fillna(1).values)
    L["status"] = L.apply(V.verdict, axis=1)
    L.to_csv(OUT / "lonesome_leaderboard.csv", index=False)
    pd.concat(led, ignore_index=True).assign(symbol=lambda x: x["key"].map(W["symbol"])).to_csv(OUT / "lonesome_trades.csv.gz", index=False)
    # early-warning use: was there a divergence in the 20 sessions BEFORE a 50-day breakout call?
    ev = pd.read_csv(OUT / "buy_events_scored.csv.gz", parse_dates=["signal_time", "entry_time"])
    pos = c.index.get_indexer(ev["signal_time"]); ci = c.columns.get_indexer(ev["key"])
    for nm, fr in (("div_reg20", saved["reg"]), ("div_hid20", saved["hid"])):
        mx = fr.rolling(20, min_periods=1).max().shift(1).values
        ev[nm] = mx[pos, ci]
    ev.to_csv(OUT / "buy_events_div.csv.gz", index=False)
    json.dump(dict(variants=len(L), seconds=round(time.time() - t0)), open(OUT / "lonesome_run.json", "w"))
    print(L["status"].value_counts().to_dict(), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
