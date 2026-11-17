"""ROUND 5 (owner 17-Nov-2026): add the owner's TradingView indicators and find each commodity's own winning combination.
Python ports (no look-ahead; a pivot is only used once confirmed, 5 candles after it):
  TLB / TLC  Liquidity Trendline [StratifyTrade]: line through the last two confirmed pivot highs when the newer one is lower;
             BUY when a whole candle trades above the line (TLB, as the script: low > line) or a close above it (TLC).
             SELL = mirror (rising line through pivot lows, broken downwards). The script's 4-pivot "valid" refinement is
             simplified to "newer pivot lower than the previous one, line not already broken".
  DIV1/2/3   Divergence for Many Indicators v4 [LonesomeTheBlue], regular divergence, pivot period 5, close source, 10 pivots,
             100 candles, confirmation on (MACD, MACD hist, RSI, Stoch, CCI, Momentum, OBV, VW-MACD, CMF, MFI):
             >= 1 / 2 / 3 indicators diverging at once. DIVR filter = any divergence in the last 15 candles.
  HULL       Hull Trend (24, hl2): BUY on the fast line crossing above the Hull line, SELL below. HULLUP filter = fast above.
  DMOX/DMOR  Dynamic Momentum Oscillator (14, 0.3): DMOX = cross above 0 (momentum), DMOR = first cross below -0.3
             (oversold reversal). DMOP filter = DMO > 0.
  + the round-4 breakouts BO10 / BO20 / MARU20 / PMO for comparison.
  filters    none / VOL / HT1 (higher-timeframe trend) / HULLUP / DMOP / DIVR / HT1+VOL / HT1+HULLUP
  candles    3h, 4h, daily, weekly · side BUY / SELL · exits as round 4 · costs real MCX (x2 weekly)
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round5 -> reports/mcx_round5.csv"""
import warnings
import numpy as np
import pandas as pd
from numba import njit
from research.mcx_institutional_buy.backtesting import data as D
from research.mcx_institutional_buy.backtesting import runner as RN
from research.mcx_institutional_buy.feature_engineering import ind as I
from research.mcx_institutional_buy.stock_rules_on_mcx import round4 as R4

warnings.filterwarnings("ignore")
TFS = ["3h", "4h", "1d", "1w"]
TRIGS = ["TLB", "TLC", "DIV1", "DIV2", "DIV3", "HULL", "DMOX", "DMOR", "BO10", "BO20", "MARU20", "PMO"]
FILTS = [(), ("VOL",), ("HT1",), ("HULLUP",), ("DMOP",), ("DIVR",), ("HT1", "VOL"), ("HT1", "HULLUP")]


def wma(x, n):
    n = max(int(n), 1); w = np.arange(1, n + 1, dtype=float)
    return pd.Series(x).rolling(n).apply(lambda v: np.dot(v, w) / w.sum(), raw=True).values


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().values


def sma(x, n):
    return pd.Series(x).rolling(n).mean().values


def rsi(c, n=14):
    d = np.diff(c, prepend=np.nan); up = pd.Series(np.clip(d, 0, None)).ewm(alpha=1 / n, adjust=False).mean()
    dn = pd.Series(np.clip(-d, 0, None)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + up / dn)).values


def indicators(o, h, l, c, v):
    macd = ema(c, 12) - ema(c, 26); sig = ema(macd, 9)
    ll, hh = pd.Series(l).rolling(14).min().values, pd.Series(h).rolling(14).max().values
    stk = sma(100 * (c - ll) / (hh - ll), 3)
    tp = c  # LonesomeTheBlue uses cci(close, 10)
    m = sma(tp, 10); md = pd.Series(tp).rolling(10).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True).values
    cci = (tp - m) / (0.015 * md)
    mom = c - np.r_[np.full(10, np.nan), c[:-10]]
    obv = np.cumsum(np.sign(np.diff(c, prepend=c[0])) * v)
    vw = lambda n: pd.Series(c * v).rolling(n).sum().values / pd.Series(v).rolling(n).sum().values
    vwmacd = vw(12) - vw(26)
    rng = np.where(h - l == 0, np.nan, h - l)
    cmf = sma(((c - l) - (h - c)) / rng * v, 21) / sma(v, 21)
    tp3 = (h + l + c) / 3; ch = np.diff(tp3, prepend=np.nan)
    pos = pd.Series(np.where(ch > 0, tp3 * v, 0)).rolling(14).sum().values; neg = pd.Series(np.where(ch < 0, tp3 * v, 0)).rolling(14).sum().values
    mfi = 100 - 100 / (1 + pos / np.where(neg == 0, np.nan, neg))
    return [macd, macd - sig, rsi(c), stk, cci, mom, obv, vwmacd, cmf, mfi]


@njit(cache=True)
def pos_reg_div(c, ind, plpos, plval, prd, maxpp, maxbars):
    """LonesomeTheBlue positive regular divergence, confirmation on (startpoint 1). plpos/plval: known pivot lows, newest
    last (position = bar where it became known = pivot + prd). Returns the divergence length (0 = none) per bar."""
    n = len(c); out = np.zeros(n, np.int64)
    k0 = 0
    for t in range(2, n):
        while k0 < len(plpos) and plpos[k0] <= t:
            k0 += 1
        if not (ind[t] > ind[t - 1] or c[t] > c[t - 1]):
            continue
        s = t - 1
        cnt = 0
        for x in range(k0 - 1, -1, -1):
            if cnt >= maxpp:
                break
            cnt += 1
            ln = t - plpos[x] + prd
            if ln > maxbars:
                break
            if ln <= 5 or t - ln < 0:
                continue
            if ind[s] > ind[t - ln] and c[s] < plval[x]:
                sl1 = (ind[s] - ind[t - ln]) / (ln - 1); v1 = ind[s] - sl1
                sl2 = (c[s] - c[t - ln]) / (ln - 1); v2 = c[s] - sl2
                ok = True
                for y in range(2, ln):
                    if ind[t - y] < v1 or c[t - y] < v2:
                        ok = False; break
                    v1 -= sl1; v2 -= sl2
                if ok:
                    out[t] = ln; break
    return out


@njit(cache=True)
def trendline(h, l, c, ph, R):
    """StratifyTrade-style descending trendline through the last two confirmed pivot highs; returns (whole-candle break,
    close break) masks."""
    n = len(c); tlb = np.zeros(n, np.bool_); tlc = np.zeros(n, np.bool_)
    pv = np.nan; pi = -1; active = False; x1 = 0; y1 = 0.0; slope = 0.0; closed_through = False
    for t in range(n):
        p = t - R
        if p >= 0 and ph[p]:
            v = h[p]
            if pi >= 0 and v < pv:
                sl = (v - pv) / (p - pi)
                ok = True
                for j in range(p + 1, t + 1):
                    if l[j] > pv + sl * (j - pi):
                        ok = False; break
                if ok:
                    active = True; x1 = pi; y1 = pv; slope = sl; closed_through = False
            pv = v; pi = p
        if active:
            line = y1 + slope * (t - x1)
            if c[t] > line and not closed_through:
                tlc[t] = True; closed_through = True
            if l[t] > line:
                tlb[t] = True; active = False
    return tlb, tlc


def parts(d, side):
    P, cond, arr = R4.signals(d, side)
    f = d["f"]; o, h, l, c = arr["o"], arr["h"], arr["l"], arr["c"]; v = f["volume"].values.astype(float)
    # trendline
    plo, phi = I.pivots(l, h, 5, 5)
    P["TLB"], P["TLC"] = trendline(h, l, c, phi, 5)
    # divergence (pivots on close)
    pl_, _ = I.pivots(c, c, 5, 5)
    idx = np.where(pl_)[0]
    plpos = (idx + 5).astype(np.int64); plval = c[idx]
    cnt = np.zeros(len(c), int)
    for ind in indicators(o, h, l, c, v):
        ind = np.nan_to_num(np.asarray(ind, float), nan=0.0)
        cnt += pos_reg_div(c, ind, plpos, plval, 5, 10, 100) > 0
    for k in (1, 2, 3):
        P[f"DIV{k}"] = cnt >= k
    divr = pd.Series((cnt >= 1).astype(float)).rolling(15, min_periods=1).max().values > 0
    # Hull trend (length 24, hl2)
    hl2 = (h + l) / 2
    a = wma(2 * wma(hl2, 12) - wma(hl2, 24), round(np.sqrt(24)))
    b = wma(wma(c, 4) * 3 - wma(c, 6) - wma(c, 12), 12)
    up = b > a
    P["HULL"] = up & ~np.r_[False, up[:-1]] & np.r_[False, (b < a)[:-1]]
    # DMO (14, 0.3)
    mom = c - np.r_[np.full(14, np.nan), c[:-14]]
    rg = pd.Series(h).rolling(14).max().values - pd.Series(l).rolling(14).min().values
    dmo = mom / np.where(rg == 0, np.nan, rg)
    pd_ = np.r_[np.nan, dmo[:-1]]
    P["DMOX"] = (dmo > 0) & (pd_ <= 0)
    os_ = (dmo < -0.3) & (pd_ >= -0.3); ob_ = (dmo > 0.3) & (pd_ <= 0.3)
    # first oversold cross since the last overbought cross
    last = 0; dmor = np.zeros(len(c), bool)
    for t in range(len(c)):
        if ob_[t]:
            last = 1
        if os_[t]:
            if last != -1:
                dmor[t] = True
            last = -1
    P["DMOR"] = dmor
    cond.update(HULLUP=up, DMOP=dmo > 0, DIVR=divr)
    return {k: np.nan_to_num(np.asarray(x, float)).astype(bool) for k, x in P.items()}, cond, arr


def main():
    rows = []
    for name in D.INTRA:
        B = R4.build(name)
        for tf in TFS:
            d = B[tf]
            for side in (1, -1):
                P, cond, arr = parts(d, side)
                for trig in TRIGS:
                    if trig not in P:
                        continue
                    for flt in FILTS:
                        m = P[trig].copy()
                        for c_ in flt:
                            m &= cond[c_]
                        if m.sum() < 5:
                            continue
                        for k, r, kind in R4.EXITS:
                            si, ei, xi, g, nr, mfe, mae, why = R4.run(arr, d, m, side, k, r, kind, tf, name)
                            if not len(nr):
                                continue
                            pe = d["per"][ei]
                            rows.append(dict(name=name, tf=tf, side="BUY" if side > 0 else "SELL", fam=trig, filt="+".join(flt) or "none",
                                             k=k, r=r, exit="trail 3ATR" if kind == 2 else f"{r}R", **R4.pstats(nr, pe),
                                             sum_TRAIN=float(nr[pe == "TRAIN"].sum()), sum_VAL=float(nr[pe == "VAL"].sum()),
                                             sum_OOS=float(nr[pe == "OOS"].sum()), win_TRAIN=int((nr[pe == "TRAIN"] > 0).sum()),
                                             win_VAL=int((nr[pe == "VAL"] > 0).sum()), win_OOS=int((nr[pe == "OOS"] > 0).sum())))
                print(name, tf, side, len(rows), {k: int(v.sum()) for k, v in P.items() if k in ("TLB", "TLC", "DIV1", "DIV3", "HULL", "DMOR")}, flush=True)
    L = pd.DataFrame(rows)
    L.to_csv(RN.REPORTS / "mcx_round5.csv", index=False)
    print("tested", len(L))


if __name__ == "__main__":
    main()
