"""ICSS-001 (4-Nov-2026) – historical check of the owner's TradingView indicator "BTC ICSS" (Conservative, default inputs).

Faithful bar-by-bar port of the Pine v6 script on DAILY candles (the owner's chart), every signal it prints
(BUY / STRONG BUY / SELL / STRONG SELL) is traded the next morning at the open. Nothing is tuned: all inputs are the
script defaults, so the whole history is out-of-sample for this rule.

Approximations (stated): VWAP on a daily chart is the session VWAP = hlc3 of that day (one bar per session);
HTF(240) on a daily chart = last 4h bar of the day -> htfClose = close, htfVwap = hlc3, htfEma200 = EMA(close, 200 x 4h bars
per day): NSE 2 bars/day -> EMA 100, MCX 4 bars/day -> EMA 50 on daily closes.

Measured per signal (entry = next open, stop = 2 x ATR14, costs 0.1R, max hold 30 days, roll-adjusted series):
  * direction hit after 5 / 10 / 20 days (close beyond entry in the call's direction)
  * +0.5R / +1R / +2R reached before the stop, and average R of the 2R trade
  * the same numbers for RANDOM entries on the same instruments/side (the base rate to beat)

  python -m research.search.icss_backtest      -> research/search/results_icss/*
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.search import hit80_search as H  # noqa: E402

OUT = ROOT / "research/search/results_icss"
STOP = "2.0"
MAXH = 30


# ─────────── Pine-equivalent helpers ───────────
def rma(x, n):
    x = pd.Series(x, dtype=float)
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def ema(x, n):
    return pd.Series(x, dtype=float).ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(c, n=14):
    d = c.diff()
    up, dn = rma(d.clip(lower=0), n), rma((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def pivots(x, left, right, high=True):
    """ta.pivothigh/low: value at bar i-right is the max/min of [i-right-left, i]; reported on bar i."""
    s = pd.Series(x)
    w = s.rolling(left + right + 1).max() if high else s.rolling(left + right + 1).min()
    cand = s.shift(right)
    out = np.where(cand.values == w.values, cand.values, np.nan)
    return out


def icss(df, htf_len):
    o, h, l, c, v = (df[k].astype(float) for k in ("open", "high", "low", "close", "volume"))
    n = len(df)
    hlc3 = (h + l + c) / 3
    e20, e50, e200, s200 = ema(c, 20), ema(c, 50), ema(c, 200), c.rolling(200).mean()
    vwap = hlc3                                                   # daily chart: one bar per session
    vwapR, vwapF = vwap > vwap.shift(5), vwap < vwap.shift(5)
    # MFI 14 (hlc3)
    mf = hlc3 * v
    pos = mf.where(hlc3 > hlc3.shift(1), 0.0).rolling(14).sum()
    neg = mf.where(hlc3 < hlc3.shift(1), 0.0).rolling(14).sum()
    mfi = 100 - 100 / (1 + pos / neg.replace(0, np.nan))
    r = rsi(c, 14)
    ml = ema(c, 12) - ema(c, 26); sg = ema(ml, 9); hist = ml - sg
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = rma(tr, 14)
    atrp = atr / c * 100
    volma = v.rolling(20).mean()
    bovol = v > volma * 1.10
    upm, dnm = h.diff(), -l.diff()
    pdm = pd.Series(np.where((upm > dnm) & (upm > 0), upm, 0.0)); mdm = pd.Series(np.where((dnm > upm) & (dnm > 0), dnm, 0.0))
    trr = rma(tr, 14).values
    pdi = 100 * rma(pdm, 14).values / trr; mdi = 100 * rma(mdm, 14).values / trr
    dx = 100 * np.abs(pdi - mdi) / np.where(pdi + mdi == 0, np.nan, pdi + mdi)
    adx = rma(pd.Series(dx), 14).values
    rngc = h - l; body = (c - o).abs()
    bodyp = np.where(rngc > 0, body / rngc * 100, 0.0)
    cpos = np.where(rngc > 0, (c - l) / rngc, 0.5)
    bullC = (bodyp >= 40) & (cpos >= 0.55); bearC = (bodyp >= 40) & (cpos <= 0.45)

    bullS = (c > e20) & (c > e50) & (e20 > e50) & (c > e200) & (e50 > e200) & (c > s200)
    bearS = (c < e20) & (c < e50) & (e20 < e50) & (c < e200) & (e50 < e200) & (c < s200)
    x20u = (e20 > e50) & (e20.shift() <= e50.shift()); x20d = (e20 < e50) & (e20.shift() >= e50.shift())
    extA = (c > e50) & ((c - e50).abs() > atr * 3); extB = (c < e50) & ((c - e50).abs() > atr * 3)
    farA = (c > vwap) & ((c - vwap).abs() > atr * 2); farB = (c < vwap) & ((c - vwap).abs() > atr * 2)
    aboveV, belowV = c > vwap, c < vwap
    tol = atr * 0.25
    vrhB = aboveV & (l <= vwap + tol) & (c > vwap) & vwapR
    vrfB = belowV & (h >= vwap - tol) & (c < vwap) & vwapF
    vwB, vwS = aboveV & vwapR, belowV & vwapF
    mfB = (mfi > 50) & (mfi > mfi.shift()); mfS = (mfi < 50) & (mfi < mfi.shift())
    rd = r.diff()
    rB = (r > 50) & (rd >= 0.5) & (r < 70); rS = (r < 50) & (rd <= -0.5) & (r > 30)
    rchop = (r >= 45) & (r <= 55)
    xU = (ml > sg) & (ml.shift() <= sg.shift()); xD = (ml < sg) & (ml.shift() >= sg.shift())
    momB = (hist > hist.shift()) & (hist.shift() > hist.shift(2)); momS = (hist < hist.shift()) & (hist.shift() < hist.shift(2))
    htfE = ema(c, htf_len)
    htfB = (c > htfE) & (c > hlc3); htfS = (c < htfE) & (c < hlc3)
    avgh = hist.abs().rolling(20).mean()
    mflat = hist.abs() < avgh.fillna(0) * 0.5
    stuck = ((c - e50).abs() < atr * 0.4) & ((c - vwap).abs() < atr * 0.4)
    comp = (e20 - e50).abs() <= atr * 0.25
    chop = (stuck & mflat) | (comp & mflat) | ~(atrp >= 0.15)
    ph, pl = pivots(h.values, 10, 5, True), pivots(l.values, 10, 5, False)

    A = {k: np.asarray(val, dtype=float) if not isinstance(val, np.ndarray) else val for k, val in dict(
        o=o, h=h, l=l, c=c, e20=e20, atr=atr, adx=adx, bodyp=bodyp).items()}
    B = {k: np.asarray(val.fillna(False) if hasattr(val, "fillna") else val, dtype=bool) for k, val in dict(
        bullS=bullS, bearS=bearS, x20u=x20u, x20d=x20d, extA=extA, extB=extB, farA=farA, farB=farB, aboveV=aboveV,
        belowV=belowV, vrhB=vrhB, vrfB=vrfB, vwB=vwB, vwS=vwS, mfB=mfB, mfS=mfS, rB=rB, rS=rS, rchop=rchop, xU=xU, xD=xD,
        momB=momB, momS=momS, htfB=htfB, htfS=htfS, mflat=mflat, chop=chop, bullC=bullC, bearC=bearC, vwapR=vwapR,
        vwapF=vwapF, atrok=(atrp >= 0.15), bovol=bovol).items()}
    rv, mlv, sgv, hv, vwv = r.values, ml.values, sg.values, hist.values, vwap.values
    ready = ~np.isnan(e200.values) & ~np.isnan(s200.values) & ~np.isnan(adx) & ~np.isnan(htfE.values)

    sig = np.zeros(n, int); strong = np.zeros(n, bool); score = np.zeros(n, int)
    res, resb, sup, supb = [], [], [], []
    lbr = np.nan; rbb = None; lbs = np.nan; sbb = None
    bsb = bsr = 999
    allowB = allowS = True; last = None
    for i in range(n):
        ci, hi, li, oi, at = A["c"][i], A["h"][i], A["l"][i], A["o"][i], A["atr"][i]
        bsb = 0 if B["xU"][i] else bsb + 1
        bsr = 0 if B["xD"][i] else bsr + 1
        if not np.isnan(ph[i]):
            res.insert(0, ph[i]); resb.insert(0, i - 5); res, resb = res[:5], resb[:5]
        if not np.isnan(pl[i]):
            sup.insert(0, pl[i]); supb.insert(0, i - 5); sup, supb = sup[:5], supb[:5]
        keep = [k for k in range(len(res)) if i - resb[k] <= 150]; res = [res[k] for k in keep]; resb = [resb[k] for k in keep]
        keep = [k for k in range(len(sup)) if i - supb[k] <= 150]; sup = [sup[k] for k in keep]; supb = [supb[k] for k in keep]
        if not ready[i] or np.isnan(at):
            continue
        nr = min([x for x in res if x > ci], default=np.nan)
        ns = max([x for x in sup if x < ci], default=np.nan)
        prox = at
        nearS = not np.isnan(ns) and abs(ci - ns) <= prox
        nearR = not np.isnan(nr) and abs(ci - nr) <= prox
        sB = nearS and li <= ns + prox * 0.5 and ci > oi and ci > ns
        rR = nearR and hi >= nr - prox * 0.5 and ci < oi and ci < nr
        swH = (not np.isnan(nr)) and hi > nr and ci < nr and B["bovol"][i] and B["bearC"][i] and A["bodyp"][i] >= 40
        swL = (not np.isnan(ns)) and li < ns and ci > ns and B["bovol"][i] and B["bullC"][i] and A["bodyp"][i] >= 40
        cprev = A["c"][i - 1] if i else np.nan
        if not np.isnan(nr) and ci > nr and cprev <= nr:           # never true (nr > close) – kept as in the script
            lbr, rbb = nr, i
        if not np.isnan(ns) and ci < ns and cprev >= ns:
            lbs, sbb = ns, i
        bBO = rbb is not None and i - rbb <= 1 and ci > lbr + at * 0.15 and B["bovol"][i] and B["bullC"][i]
        bBD = sbb is not None and i - sbb <= 1 and ci < lbs - at * 0.15 and B["bovol"][i] and B["bearC"][i]
        recl = not np.isnan(lbr) and ci > lbr and li <= lbr * 1.005 and ci > oi
        lost = not np.isnan(lbs) and ci < lbs and hi >= lbs * 0.995 and ci < oi
        srB, srS = sB or recl or bBO, rR or lost or bBD
        mabove, mbelow = mlv[i] > sgv[i], mlv[i] < sgv[i]
        fB, fS = bsb <= 8, bsr <= 8
        hpos, hrise = hv[i] > 0, i > 0 and hv[i] > hv[i - 1]
        hneg, hfall = hv[i] < 0, i > 0 and hv[i] < hv[i - 1]
        macB = ((B["xU"][i] or (mabove and fB)) or (hpos and hrise)) or B["momB"][i]
        macS = ((B["xD"][i] or (mbelow and fS)) or (hneg and hfall)) or B["momS"][i]
        adxp = 1 if A["adx"][i] >= 15 else 0
        bs = 3 * B["bullS"][i] + 2 * B["vwB"][i] + B["mfB"][i] + B["rB"][i] + macB + srB + B["htfB"][i] + 2 * swL + adxp - B["rchop"][i]
        ss = 3 * B["bearS"][i] + 2 * B["vwS"][i] + B["mfS"][i] + B["rS"][i] + macS + srS + B["htfS"][i] + 2 * swH + adxp - B["rchop"][i]
        bs, ss = int(bs), int(ss)
        near20 = abs(ci - A["e20"][i]) <= at
        bG = sB or recl or B["vrhB"][i] or (B["x20u"][i] and B["bullS"][i]) or bBO or swL or (ci > A["e20"][i] and near20 and B["vwB"][i])
        sG = rR or lost or B["vrfB"][i] or (B["x20d"][i] and B["bearS"][i]) or bBD or swH or (ci < A["e20"][i] and near20 and B["vwS"][i])
        cB = B["bullS"][i] and B["vwB"][i] and macB and B["rB"][i] and bG
        cS = B["bearS"][i] and B["vwS"][i] and macS and B["rS"][i] and sG
        chop = B["chop"][i]
        buyR = cB and not chop and B["atrok"][i] and not B["extA"][i] and not B["farA"][i]
        sellR = cS and not chop and B["atrok"][i] and not B["extB"][i] and not B["farB"][i]
        eB = B["x20u"][i] and B["aboveV"][i] and B["vwapR"][i] and rv[i] >= 52 and not chop and fB
        eS = B["x20d"][i] and B["belowV"][i] and B["vwapF"][i] and rv[i] <= 48 and not chop and fS
        ebR = eB and not chop and B["atrok"][i] and not B["extA"][i] and not B["farA"][i] and not B["mflat"][i]
        esR = eS and not chop and B["atrok"][i] and not B["extB"][i] and not B["farB"][i] and not B["mflat"][i]
        if ci < A["e20"][i]:
            allowB = True
        if ci > A["e20"][i]:
            allowS = True
        can = last is None or i - last >= 8
        gap = abs(bs - ss)
        bW, sW = bs > ss and gap >= 1, ss > bs and gap >= 1
        bStr = (buyR and bs >= 7) or (ebR and bs >= 6); bBuy = (buyR and bs >= 5) or (ebR and bs >= 4)
        sStr = (sellR and ss >= 7) or (esR and ss >= 6); sSell = (sellR and ss >= 5) or (esR and ss >= 4)
        bGate = (buyR or ebR) and can and bW and allowB
        sGate = (sellR or esR) and can and sW and allowS
        fSB = bGate and bStr and B["htfB"][i]; fSS = sGate and sStr and B["htfS"][i]
        fB_ = bGate and bBuy and not fSB; fS_ = sGate and sSell and not fSS
        if fB_ or fSB:
            sig[i], strong[i], score[i], last, allowB = 1, fSB, bs, i, False
        if fS_ or fSS:
            sig[i], strong[i], score[i], last, allowS = -1, fSS, ss, i, False
    return sig, strong, score


def fwd_hit(df, side, k):
    o, c = df["open"].values, df["close"].values
    e = np.r_[o[1:], np.nan]
    fc = np.r_[c[k:], np.full(k, np.nan)]
    sw = df["switch"].values.astype(bool)
    blk = pd.Series(sw[::-1]).rolling(k + 1, min_periods=1).max().values[::-1].astype(bool)   # roll inside window
    ok = np.isfinite(fc) & np.isfinite(e) & ~blk
    return ok, side * (fc - e) > 0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for seg, tf, name, df in H.datasets():
        if tf != "1d":
            continue
        df = df.reset_index(drop=True)
        htf_len = 50 if seg == "MCX" else 100
        sig, strong, score = icss(df, htf_len)
        F = H.features(df, "1d")
        for side in (1, -1):
            valid, res = H.outcomes(df, F, side, STOP, MAXH)
            fw = {k: fwd_hit(df, side, k) for k in (5, 10, 20)}
            first_ok = np.arange(len(df)) >= 260                      # same warm-up as the indicator (EMA/SMA 200)
            for kind, mask in (("signal", sig == side), ("random", np.ones(len(df), bool) & first_ok)):
                for i in np.flatnonzero(mask & valid):
                    r = dict(seg=seg, name=name, side="BUY" if side > 0 else "SELL", kind=kind, time=df["time"].iloc[i],
                             strong=bool(strong[i]) if kind == "signal" else False, score=int(score[i]) if kind == "signal" else 0)
                    for k in (5, 10, 20):
                        ok, hit = fw[k]
                        r[f"d{k}"] = float(hit[i]) if ok[i] else np.nan
                    for kk in (0.5, 1.0, 2.0):
                        r[f"w{kk}"] = bool(res[kk]["win"][i])
                    r["R2"] = res[2.0]["r"][i]
                    rows.append(r)
        print(seg, name, int((sig != 0).sum()), "signals", flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "trades.csv.gz", index=False)

    def agg(g):
        return pd.Series(dict(n=len(g), d5=g.d5.mean(), d10=g.d10.mean(), d20=g.d20.mean(), w05=g["w0.5"].mean(),
                              w1=g["w1.0"].mean(), w2=g["w2.0"].mean(), avgR_2R=g.R2.mean()))
    sumrows = []
    for keys, g in t.groupby(["seg", "side", "kind"]):
        sumrows.append(dict(zip(("seg", "side", "kind"), keys), **agg(g)))
    for keys, g in t[t.kind == "signal"].groupby(["seg", "side", "strong"]):
        sumrows.append(dict(seg=keys[0], side=keys[1], kind="STRONG" if keys[2] else "plain", **agg(g)))
    s = pd.DataFrame(sumrows).round(3)
    s.to_csv(OUT / "summary.csv", index=False)
    t["year"] = pd.to_datetime(t.time).dt.year
    y = t[t.kind == "signal"].groupby(["seg", "side", "year"]).apply(agg).round(3)
    y.to_csv(OUT / "by_year.csv")
    print(s.to_string())
    print(y.to_string())


if __name__ == "__main__":
    main()
