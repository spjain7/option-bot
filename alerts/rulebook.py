"""RULEBOOK (6-Nov-2026, owner mission: more high-quality calls on every timeframe).

Generic engine for rules that passed the walk-forward searches (research branch exp/strategy-program-001: SEARCH-ALL-001,
SEARCH-V2): each rule = market · timeframe · signal family · filter · side · stop k ATR · target r R · max candles.
The signal code below is a copy of research/program/search_v2.py (same definitions, so live = test).
  * completed candles only; entry at the next candle's open (the call shows the live price and a 0.5-ATR no-chase zone)
  * LIVE rules are sent; SHADOW rules are logged and their outcome tracked, never sent
  * one call per instrument and direction (alerts/strategies.conflict); every signal goes through the funnel
Calls carry: instrument, side, timeframe, strategy, signal time, entry, SL, T1 (1R) and T2 (target), R:R, validity, evidence.
ALERTS ONLY – no orders.
"""
import numpy as np
import pandas as pd
from crude import indicators as I
from alerts import tradeplan as TP, report as RP, signals as SG

WARN = "Alert only – not investment advice."
TF_MIN = {"15m": 15, "30m": 30, "1h": 60, "2h": 120, "3h": 180, "4h": 240, "1d": 1440}
TF_TXT = {"15m": "15-minute", "30m": "30-minute", "1h": "1-hour", "2h": "2-hour", "3h": "3-hour", "4h": "4-hour", "1d": "daily"}
CANDLES_PER_DAY = {"MCX": {"15m": 58, "30m": 29, "1h": 15, "2h": 8, "3h": 5, "4h": 4, "1d": 1},
                   "NFO": {"15m": 25, "30m": 13, "1h": 7, "2h": 4, "3h": 2, "4h": 2, "1d": 1}}

# id: dict(mkt, tf, fam, par, filt, side, k, r, maxh, status, n, win %, R after 2x costs, periods p1/p2/p3, tier, label)
# Evidence: research/program/results/search_v2_summary.csv (SEARCH-V2, 6-Nov-2026): positive in all three periods,
# Benjamini-Hochberg q < 0.10 across 5,292 combinations, >= 55 % of instruments positive. Stock 2h / 4h rules are NOT used:
# their research candles were not day-anchored, so live candles would differ from the test.
def _r(mkt, tf, fam, par, filt, side, k, r, maxh, n, win, R, periods, tier, label, status="LIVE", mode="next_open"):
    return dict(mkt=mkt, tf=tf, fam=fam, par=par, filt=filt, side=side, k=k, r=r, maxh=maxh, n=n, win=win, R=R, periods=periods,
                tier=tier, label=label, status=status, mode=mode)


RULES = {
    "RB_MCX_4h_EMA1348_BUY": _r("MCX", "4h", "EMAX", "13/48", "DT", "BUY", 2.0, 3.0, 40, 112, 52, 0.62, "+0.50/+1.40/+0.35", "A",
                                "EMA 13/48 cross"),
    "RB_MCX_4h_MACD0_BUY": _r("MCX", "4h", "MACD", "zero", "DT", "BUY", 1.5, 2.0, 40, 163, 53, 0.44, "+0.30/+0.76/+0.34", "A",
                              "MACD zero-line cross"),
    "RB_MCX_2h_MOMO_BUY": _r("MCX", "2h", "MOMO", "1.5ATR", "DT", "BUY", 2.0, 3.0, 50, 309, 42, 0.36, "+0.27/+0.11/+0.55", "A",
                             "momentum candle"),
    "RB_MCX_2h_EMA921_BUY": _r("MCX", "2h", "EMAX", "9/21", "DT", "BUY", 3.0, 6.0, 50, 357, 45, 0.31, "+0.18/+0.24/+0.47", "A",
                               "EMA 9/21 cross"),
    "RB_MCX_1d_RETEST_BUY": _r("MCX", "1d", "RETEST", "20/5", "DT", "BUY", 2.0, 3.0, 20, 121, 55, 0.47, "+0.47/+0.05/+0.75", "B",
                               "breakout retest"),
    "RB_MCX_1h_MACD_BUY": _r("MCX", "1h", "MACD", "signal", "DT", "BUY", 3.0, 6.0, 60, 742, 42, 0.21, "+0.20/+0.07/+0.30", "B",
                             "MACD signal cross"),
    "RB_STK_3h_MACD0_SELL": _r("STOCKS", "3h", "MACD", "zero", "DT", "SELL", 1.5, 2.0, 40, 1036, 49, 0.17, "+0.08/+0.22/+0.19", "B",
                               "MACD zero-line cross"),
    "RB_STK_3h_EMA921_SELL": _r("STOCKS", "3h", "EMAX", "9/21", "DT", "SELL", 2.0, 3.0, 40, 1274, 49, 0.15, "+0.08/+0.09/+0.21", "B",
                                "EMA 9/21 cross"),
    # LONG20-001 (6-Nov, 20 years of daily candles: MCX 2006-26, NIFTY / BANKNIFTY futures 2011-26, 2x costs, periods
    # 2006-12 / 2013-19 / 2020-26 incl. the 2013-19 metals bear market, BH-FDR across 1,604 combinations):
    "RB_MCX_1d_BO55_BUY": _r("MCX", "1d", "BO", "N55 vol2", "none", "BUY", 2.0, 3.0, 20, 124, 50, 0.49, "+0.38/+0.39/+0.62 (20 y)", "A",
                             "55-day breakout, volume 2x"),
    "RB_IDX_1d_EMA2050_BUY": _r("INDEX", "1d", "EMAX", "20/50", "none", "BUY", 1.5, 2.0, 20, 67, 55, 0.50, "+0.50/+0.85/+0.21 (15 y)", "B",
                                "EMA 20/50 cross"),
    "RB_IDX_1d_RSI70_BUY": _r("INDEX", "1d", "RSICONT", "70/30", "none", "BUY", 1.5, 2.0, 20, 107, 51, 0.36, "+0.91/+0.25/+0.22 (15 y)", "B",
                              "RSI momentum above 70"),
    "RB_IDX_1d_BO10_BUY": _r("INDEX", "1d", "BO", "N10 vol0", "none", "BUY", 1.5, 2.0, 20, 339, 45, 0.23, "+0.13/+0.24/+0.27 (15 y)", "A",
                             "10-day breakout"),
    # STK-ANCHOR-001 (6-Nov): stock 2h / 4h on DAY-ANCHORED candles (= live candles), 181 stocks 2022-26, 2x costs, FDR
    "RB_STK_2h_SQZ_SELL": _r("STOCKS", "2h", "SQZ", "BB20", "DT", "SELL", 2.0, 3.0, 50, 1014, 46, 0.27, "+0.23/+0.31/+0.28", "A",
                             "Bollinger squeeze breakdown"),
    "RB_STK_4h_MACD0_SELL": _r("STOCKS", "4h", "MACD", "zero", "DT", "SELL", 1.5, 2.0, 40, 1034, 49, 0.19, "+0.11/+0.24/+0.20", "A",
                               "MACD zero-line cross"),
    # RSIX-001 (6-Nov-2026, owner request "RSI extreme + reversal candle high breakout"): of 216k RSI-reversal variants this is
    # the one family positive in all three 20-year periods. Entry = BUY-STOP above the reversal candle's high (next 3 sessions;
    # cancelled if its low breaks first). Close-confirmed entries lost the edge. ROLLCHECK-001: evidence re-stated on the
    # roll-adjusted daily series (the first numbers, +0.19R, held trades through contract-roll gaps).
    "RB_MCX_1d_RSIX_BUY": _r("MCX", "1d", "RSIX", "7/30", "none", "BUY", 1.5, 3.0, 20, 250, 45, 0.16, "+0.08/+0.05/+0.36 (20 y, roll-adjusted)", "B",
                             "RSI(7) oversold reversal · buy above candle high", mode="stop"),
    "RB_STK_1d_RSI80_BUY": _r("STOCKS", "1d", "RSICONT", "80/20", "DT", "BUY", 2.0, 3.0, 20, 234, 55, 0.27, "+0.33/+0.19/+0.19", "B",
                              "RSI momentum above 80"),
}

# 7-Nov-2026 (owner: "start H1.12L live", answered "Live Telegram alerts, labelled EXPERIMENTAL"): research MCXE-006 H1.12L,
# research branch exp/strategy-program-001 research/mcxe006/TOP_CANDIDATES.md. NOT validated: OOS 79 trades, 41.8 % won,
# +0.31R after 2x costs, 95 % CI [-0.17, +0.80] includes 0, profit concentrated in Aug-2026. No fixed target: 4-ATR trailing
# stop on 1-hour closes (trail ATR = the signal candle's ATR), initial stop 2 ATR, time exit 240 candles. Every message says so.
RULES["RB_MCX_1h_BO20X_BUY_EXP"] = dict(
    _r("MCX", "1h", "BO", "N20 vol0 x", "none", "BUY", 2.0, 0.0, 240, 79, 42, 0.31,
       "DEV +0.58 / VALID +0.40 / OOS +0.31 (1-year windows; OOS CI includes 0)", "EXP",
       "🧪 EXPERIMENTAL – 1-hour 20-candle breakout (H1.12L)"), trail=4.0, experimental=True)

# 7-Nov-2026 (owner: "Add without any check: 1 hour base, OI based call, volume must 2.5x normal, no nearby resistance /
# support or reversing from support / resistance, low SL for higher target"). UNTESTED – added without a backtest at the
# owner's request; every message says so. Rule: first 1h close beyond the 20-candle high/low, that candle's volume >= 2.5x
# the 20-candle average, OI build-up during the signal hour in the trade direction, no swing / daily level within the 3R
# target, no rejection wick (> 50 % of the candle range against the trade). SL 1 ATR, target 3R, time exit 40 candles.
for _mkt in ("MCX", "INDEX"):
    for _side in ("BUY", "SELL"):
        RULES[f"RB_{'MCX' if _mkt == 'MCX' else 'IDX'}_1h_OIBO_{_side}_EXP"] = dict(
            _r(_mkt, "1h", "BO", "N20 vol2.5 x", "none", _side, 1.0, 3.0, 40, 0, 0, 0.0, "UNTESTED (owner rule, 7-Nov-2026)", "EXP",
               "🧪 EXPERIMENTAL (UNTESTED) – 1-hour OI breakout"), oi=True, sr_room=True, wick_max=0.5, experimental=True, untested=True)



# ── candles ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def blocks(h1, ex, hours):
    """Day-anchored n-hour candles from completed 1-hour candles (MCX from 09:00, NSE from 09:15)."""
    if h1 is None or h1.empty:
        return None
    d = h1.copy()
    day = d["time"].dt.normalize()
    if ex == "MCX":
        k = ((d["time"].dt.hour - 9).clip(lower=0) // hours).astype(int)
    else:
        k = d.groupby(day).cumcount() // hours
    g = d.groupby([day, k], sort=True)
    out = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum"), n=("close", "size")).reset_index(drop=True)
    return out


def complete(fr, tf, ex, now):
    """Drop a candle that is still forming (its end is in the future)."""
    if fr is None or not len(fr):
        return fr
    end = fr["time"].iloc[-1] + pd.Timedelta(minutes=TF_MIN[tf])
    if tf in ("2h", "3h", "4h"):
        close = now.normalize() + (pd.Timedelta(hours=23, minutes=30) if ex == "MCX" else pd.Timedelta(hours=15, minutes=30))
        end = min(end, close) if fr["time"].iloc[-1].normalize() == now.normalize() else end
    return fr if end <= now else fr.iloc[:-1].reset_index(drop=True)


def resample_min(c15, m):
    """30-minute candles from 15-minute candles (anchored at the session open)."""
    if c15 is None or c15.empty:
        return None
    d = c15.copy(); day = d["time"].dt.normalize()
    mins = (d["time"] - day).dt.total_seconds() // 60
    first = mins.groupby(day).transform("min")
    k = ((mins - first) // m).astype(int)
    return d.groupby([day, k]).agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                   close=("close", "last"), volume=("volume", "sum")).reset_index(drop=True)


def features(df):
    f = df.reset_index(drop=True).copy()
    c, v = f["close"], f["volume"].astype(float)
    f["atr"] = I.atr(f, 14); f["ema200"] = I.ema(c, 200); f["adx"] = I.adx(f); f["rsi"] = I.rsi(c, 14)
    f["volx"] = v / v.rolling(20).mean().shift(1)
    return f


def daily_trend_map(daily):
    """date -> previous completed day's trend (+1 / -1 / 0), as research SA.daily_trend."""
    if daily is None or len(daily) < 55:
        return pd.Series(dtype=float)
    c = daily["close"].reset_index(drop=True)
    e20, e50 = I.ema(c, 20), I.ema(c, 50)
    t = np.where((e20 > e50) & (c > e50), 1, np.where((e20 < e50) & (c < e50), -1, 0))
    s = pd.Series(t, index=pd.to_datetime(daily["time"]).dt.normalize().values).shift(1)
    s = s[~s.index.duplicated(keep="last")]
    s.attrs["last_day"], s.attrs["last"] = pd.Timestamp(s.index[-1]), int(t[-1])   # for days after the frame (today, intraday)
    return s


# ── signal families (copied from research/program/search_v2.py) ──────────────────────────────────────────────────────
def _xup(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return (a > b) & (np.r_[np.nan, a[:-1]] <= np.r_[np.nan, b[:-1]])


def _supertrend(f, n=10, m=3.0):
    h, l, c = f["high"].values, f["low"].values, f["close"].values
    a = I.atr(f, n).values
    hl2 = (h + l) / 2
    ub, lb = hl2 + m * a, hl2 - m * a
    fu, fl = ub.copy(), lb.copy()
    d = np.ones(len(c))
    for i in range(1, len(c)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        d[i] = 1 if c[i] > fu[i - 1] else (-1 if c[i] < fl[i - 1] else d[i - 1])
    return d


def raw(f, fam, par):
    """-> (buy mask, sell mask) of a family / parameter set, before the filter."""
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    cs, hs, ls = f["close"].astype(float), f["high"].astype(float), f["low"].astype(float)
    ema200, adx, volx, atr, rsi = (f[x].values for x in ("ema200", "adx", "volx", "atr", "rsi"))
    n = len(c)
    if fam == "BO":
        N = int(par.split()[0][1:]); vx = float(par.split("vol")[1].split()[0]) if "vol" in par else 0.0
        hh, ll = hs.shift(1).rolling(N).max().values, ls.shift(1).rolling(N).min().values
        vb = volx >= vx if vx else np.ones(n, bool)
        if "x" in par.split():                             # 7-Nov H1.12L: first close beyond the level only (research donchian)
            pc, phh, pll = np.r_[np.nan, c[:-1]], np.r_[np.nan, hh[:-1]], np.r_[np.nan, ll[:-1]]
            return (c > hh) & ~(pc > phh) & vb, (c < ll) & ~(pc < pll) & vb
        return (c > hh) & vb, (c < ll) & vb
    if fam == "PB":
        a, b = (int(x) for x in par.replace("EMA", "").split("/"))
        ef, es = I.ema(cs, a).values, I.ema(cs, b).values
        return (ef > es) & (l <= ef) & (c > ef) & (c > o), (ef < es) & (h >= ef) & (c < ef) & (c < o)
    if fam == "NR7":
        rng = h - l
        nr7 = rng <= pd.Series(rng).rolling(7).min().values
        nr7p = np.r_[False, nr7[:-1]]
        hp, lp = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
        return nr7p & (c > hp), nr7p & (c < lp)
    if fam == "RSIREV":
        L, U = (int(x) for x in par.split("/"))
        return _xup(rsi, np.full(n, L)), _xup(-rsi, np.full(n, -U))
    if fam == "RSICONT":
        U, L = (int(x) for x in par.split("/"))
        return _xup(rsi, np.full(n, U)), _xup(-rsi, np.full(n, -L))
    if fam == "RSIDIV":
        lo10, hi10 = ls.rolling(10).min().values, hs.rolling(10).max().values
        rmin = pd.Series(rsi).shift(1).rolling(10).min().values; rmax = pd.Series(rsi).shift(1).rolling(10).max().values
        return (l <= lo10) & (rsi > rmin + 5) & (rsi < 40) & (c > o), (h >= hi10) & (rsi < rmax - 5) & (rsi > 60) & (c < o)
    if fam == "MACD":
        e12, e26 = I.ema(cs, 12).values, I.ema(cs, 26).values
        m_ = e12 - e26; sg = pd.Series(m_).ewm(span=9, adjust=False).mean().values
        if par == "signal":
            return _xup(m_, sg) & (c > ema200), _xup(sg, m_) & (c < ema200)
        return _xup(m_, np.zeros(n)), _xup(-m_, np.zeros(n))
    if fam == "ST":
        st = _supertrend(f); stp = np.r_[st[0], st[:-1]]
        return (st > 0) & (stp < 0), (st < 0) & (stp > 0)
    if fam == "EMAX":
        a, b = (int(x) for x in par.split("/"))
        ea, eb = I.ema(cs, a).values, I.ema(cs, b).values
        return _xup(ea, eb), _xup(eb, ea)
    if fam == "INSIDE":
        hp, lp = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
        hp2, lp2 = np.r_[np.nan, np.nan, h[:-2]], np.r_[np.nan, np.nan, l[:-2]]
        ins = (hp <= hp2) & (lp >= lp2)
        return ins & (c > hp2), ins & (c < lp2)
    if fam == "PIN":
        rng = h - l; body = np.abs(c - o)
        lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
        lo20, hi20 = ls.rolling(20).min().values, hs.rolling(20).max().values
        return (lw >= 2 * body) & (lw >= 0.6 * rng) & (l <= lo20), (uw >= 2 * body) & (uw >= 0.6 * rng) & (h >= hi20)
    if fam == "MOMO":
        rng = h - l; body = np.abs(c - o); pos = (c - l) / np.where(rng > 0, rng, np.nan)
        return (body >= 1.5 * atr) & (c > o) & (pos >= 0.8), (body >= 1.5 * atr) & (c < o) & (pos <= 0.2)
    if fam == "FAIL":
        hh20, ll20 = hs.shift(1).rolling(20).max().values, ls.shift(1).rolling(20).min().values
        hh20p, ll20p = np.r_[np.nan, hh20[:-1]], np.r_[np.nan, ll20[:-1]]
        cp = np.r_[np.nan, c[:-1]]
        return (cp < ll20p) & (c > ll20p), (cp > hh20p) & (c < hh20p)
    if fam == "RETEST":
        hh20, ll20 = hs.shift(1).rolling(20).max().values, ls.shift(1).rolling(20).min().values
        bu = pd.Series(c > hh20).rolling(5).max().shift(1).fillna(0).values.astype(bool)
        bd = pd.Series(c < ll20).rolling(5).max().shift(1).fillna(0).values.astype(bool)
        lu = pd.Series(np.where(c > hh20, hh20, np.nan)).ffill().values
        ld = pd.Series(np.where(c < ll20, ll20, np.nan)).ffill().values
        return bu & (l <= lu + 0.3 * atr) & (c > lu), bd & (h >= ld - 0.3 * atr) & (c < ld)
    if fam == "RSIX":                                      # research/program/rsix.py E1 + bull/bear candle + ADX(14) < 20
        n_, L = (int(x) for x in par.split("/"))
        r7 = I.rsi(cs, n_)
        rng = np.where(h - l > 0, h - l, np.nan); pos = (c - l) / rng
        lowadx = np.nan_to_num(adx, nan=99) < 20
        return ((r7.rolling(3).min().values <= L) & (c > o) & (pos >= 0.5) & lowadx,
                (r7.rolling(3).max().values >= 100 - L) & (c < o) & (pos <= 0.5) & lowadx)
    if fam == "SQZ":                                       # Bollinger (20, 2) squeeze: width near its 100-candle low, then a close outside
        mid = cs.rolling(20).mean(); sd = cs.rolling(20).std()
        up, dn = (mid + 2 * sd).values, (mid - 2 * sd).values
        w = (up - dn) / mid.values
        sq = pd.Series(w <= pd.Series(w).rolling(100).min().values * 1.1).rolling(5).max().fillna(0).values.astype(bool)
        return sq & (c > up), sq & (c < dn)
    raise ValueError(f"unknown family {fam}")


def evaluate(f, rule, dtr):
    """Signal on the LAST completed candle of f for this rule -> dict or None."""
    if f is None or len(f) < 220:
        return None
    b, s = raw(f, rule["fam"], rule["par"])
    i = len(f) - 1
    side = 1 if rule["side"] == "BUY" else -1
    hit = bool((b if side > 0 else s)[i])
    if not hit:
        return None
    flt = rule["filt"]
    c, e = float(f["close"].iloc[i]), float(f["ema200"].iloc[i])
    if flt == "EMA200" and not (side * (c - e) > 0):
        return dict(rejected="EMA200 against the call")
    if flt == "ADX25" and not float(f["adx"].iloc[i]) >= 25:
        return dict(rejected="ADX < 25")
    if flt.startswith("DT"):
        day = pd.Timestamp(f["time"].iloc[i]).normalize()
        if len(dtr) and day > dtr.attrs.get("last_day", day):
            t = dtr.attrs.get("last", 0)                          # candle after the last completed day -> that day's trend
        else:
            t = dtr.get(day, np.nan) if len(dtr) else np.nan
            t = 0 if t != t else t
        if t != side:
            return dict(rejected=f"daily trend not {'up' if side > 0 else 'down'}")
    if "VOL" in flt and not float(f["volx"].iloc[i]) >= 1.5:
        return dict(rejected="volume < 1.5x")
    return dict(candle=str(f["time"].iloc[i]), close=c, open=float(f["open"].iloc[i]), high=float(f["high"].iloc[i]), low=float(f["low"].iloc[i]), atr=float(f["atr"].iloc[i]), adx=float(f["adx"].iloc[i]),
                rsi=float(f["rsi"].iloc[i]), vol_x=float(f["volx"].iloc[i]) if f["volx"].iloc[i] == f["volx"].iloc[i] else None)


def describe(rule):
    fam, par = rule["fam"], rule["par"]
    txt = {"BO": f"close beyond the {par.split()[0][1:]}-candle high/low", "PB": f"pull-back to EMA{par.split('/')[0][3:]} in an EMA trend",
           "NR7": "break of the narrowest candle of 7", "RSIREV": f"RSI back inside {par}", "RSICONT": f"RSI momentum beyond {par}",
           "RSIDIV": "RSI divergence at a 10-candle extreme", "MACD": f"MACD {par} cross", "ST": "Supertrend (10, 3) flip",
           "EMAX": f"EMA {par} cross", "INSIDE": "inside-bar breakout", "PIN": "pin bar at a 20-candle extreme",
           "MOMO": "momentum candle (body ≥ 1.5 ATR)", "FAIL": "failed 20-candle breakout – reversal",
           "RETEST": "breakout retest of the 20-candle level", "SQZ": "Bollinger squeeze (20, 2) break",
           "RSIX": f"RSI({par.split('/')[0]}) touched {par.split('/')[1]} / {100 - int(par.split('/')[1])} + reversal candle, ADX < 20"}.get(fam, fam)
    flt = {"none": "", "DT": " · with the daily trend", "EMA200": " · EMA200 side", "ADX25": " · ADX ≥ 25"}.get(rule["filt"], " · " + rule["filt"])
    return txt + flt


# ── live hook ────────────────────────────────────────────────────────────────────────────────────────────────────────
def run(state, msgs, api, name, ex, c, frames, daily, q, now, mult, mkt, after_close=False, oi=None):
    """frames: {tf: completed candles}. Checks every rule of this market. Returns {rule_id: outcome}."""
    from alerts import funnel as FN, four_hour as FH, strategies as ST
    out = {}
    st = FH.store(state)
    seen = state.setdefault("rulebook_seen", [])
    dtr = daily_trend_map(daily)
    _trail_update(state, msgs, st, name, frames)
    feats = {}
    for rid, rule in RULES.items():
        if rule["mkt"] != mkt or rule["tf"] not in frames:
            continue
        fr = frames[rule["tf"]]
        if fr is None or len(fr) < 220:
            out[rid] = "insufficient candles"; continue
        last = str(fr["time"].iloc[-1])
        key = f"{rid}|{name}|{last}"
        if key in seen:
            continue
        seen.append(key); state["rulebook_seen"] = seen[-3000:]
        if rule["tf"] not in feats:
            feats[rule["tf"]] = features(fr)
        sig = evaluate(feats[rule["tf"]], rule, dtr)
        if sig is None:
            if rule.get("mode") == "stop" and rule["status"] == "LIVE":
                _early_warning(state, msgs, rid, rule, feats[rule["tf"]], name, last, now)
            continue
        fk = f"{name}|{last}"
        FN.note(state, rid, "signal", key=fk, now=now)
        if sig.get("rejected"):
            FN.note(state, rid, "rejected", sig["rejected"], key=fk, now=now); out[rid] = sig["rejected"]; continue
        if rule.get("oi") or rule.get("sr_room") or rule.get("wick_max"):     # 7-Nov owner OI-breakout rule (untested)
            why_not = _owner_checks(rule, sig, feats[rule["tf"]], daily, c, now, oi)
            if why_not:
                FN.note(state, rid, "rejected", why_not, key=fk, now=now); out[rid] = why_not; continue
        shadow = rule["status"] != "LIVE"
        clash = None if shadow else ST.conflict(state, name, rule["side"], rule["tf"])
        if clash:
            FN.note(state, rid, "rejected", clash, key=fk, now=now); out[rid] = clash; continue
        if any(r["name"] == name and r.get("rule") == rid for r in st["open"]):
            FN.note(state, rid, "rejected", "already open", key=fk, now=now); out[rid] = "already open"; continue
        if rule.get("mode") == "stop":
            out[rid] = _stop_entry(state, msgs, st, rid, rule, sig, name, ex, c, q, api, now, mult, shadow, fk, last, after_close)
            continue
        if q is None and not after_close and api is not None and hasattr(api, "quotes"):
            try:                                          # quote only when a signal actually fires (saves the Angel quota)
                q = (api.quotes({ex: [str(c["token"])]}) or {}).get(str(c["token"]))
            except Exception:
                q = None
        live = None if after_close else (float((q or {}).get("ltp") or 0) or None)
        plan = TP.futures_plan(name=name, ex=ex, contract=c["symbol"], tf=rule["tf"], side=rule["side"], signal_time=sig["candle"],
                               signal_close=sig["close"], atr=sig["atr"], stop_mult=rule["k"], target_r=None if rule.get("trail") else rule["r"],
                               tick=c.get("tick"), lot=c.get("lot"), mult=mult, max_sl_pct=rule.get("cap", 0.0), live=live,
                               quote=None if after_close else q, now=now, require_live=not after_close and not shadow)
        if not plan["valid"]:
            FN.note(state, rid, "rejected", plan["reason"], key=fk, now=now); out[rid] = plan["reason"]; continue
        s_ = 1 if rule["side"] == "BUY" else -1
        t = plan["tick"]
        t1 = plan["entry"] + s_ * plan["risk_unit"]
        cpd = CANDLES_PER_DAY["MCX" if ex == "MCX" else "NFO"][rule["tf"]]
        max_days = max(1, int(np.ceil(rule["maxh"] / cpd)))
        valid_to = pd.Timestamp(sig["candle"]) + pd.Timedelta(minutes=2 * TF_MIN[rule["tf"]])
        rec = dict(name=name, ex=ex, token=str(c["token"]), contract=c["symbol"], expiry=c["expiry"], side=rule["side"],
                   entry=plan["entry"], stop=plan["sl"], target=plan["target"], risk=plan["risk_unit"], tick=t, mult=mult,
                   opened=str(now), days=[str(now.date())], key=f"RB|{rid}|{name}|{last}", max_days=max_days,
                   tfl=TF_TXT[rule["tf"]], rule=rid, **({"shadow": True} if shadow else {}))
        if rule.get("trail"):                                 # 7-Nov H1.12L: trailing stop on candle closes, no fixed target
            rec.update(trail_atr=float(rule["trail"]), atr=float(sig["atr"]), best=float(plan["entry"]), trailed=False,
                       trail_tf=rule["tf"], trail_from=last, trail_noted=float(plan["sl"]))
        st["open"].append(rec)
        if shadow:
            FN.note(state, rid, "shadow", key=fk, now=now); out[rid] = "shadow"
            print(f"[rulebook] {name} {rid} logged only: entry {plan['entry']} SL {plan['sl']} T {plan['target']}")
            continue
        rr = rule["r"]
        if rule.get("trail"):
            msgs.extend(_trail_messages(rule, rid, sig, plan, c, t, s_, name, valid_to, after_close, max_days))
        elif rule.get("untested"):
            msgs.extend(_untested_messages(rule, rid, sig, plan, c, t, s_, name, valid_to, after_close, max_days, t1, ex))
        else:
          msgs.append("\n".join([
              f"{'🟢 BUY' if s_ > 0 else '🔴 SELL'}  {name} FUT  ·  {TF_TXT[rule['tf']].upper()} · {rule.get('label', rid)}",
              "━━━━━━━━━━━━━━",
              f"Entry   : {TP.fmt(plan['entry'], t)}  (no chase beyond {TP.fmt(plan['entry'] + s_ * 0.5 * sig['atr'], t)})",
              f"SL      : {TP.fmt(plan['sl'], t)}",
              f"T1      : {TP.fmt(t1, t)}  (1R)",
              f"T2      : {TP.fmt(plan['target'], t)}  ({rr:g}R – exit here)",
              f"R:R     : 1:{rr:g} · risk ₹{plan['risk_lot']:,.0f} per lot",
              f"Lot     : {c.get('lot') or '-'}  ·  {pd.Timestamp(c['expiry']):%b} expiry  ·  {'MCX' if ex == 'MCX' else 'NSE'}",
              f"Valid   : enter by {valid_to:%d-%b %H:%M}" + (" (next session open)" if after_close else "")]))
          msgs.append("\n".join([
              f"📌 WHY – {name} {rule['side']} ({TF_TXT[rule['tf']]})",
              f"• Signal  : {pd.Timestamp(sig['candle']):%d-%b %H:%M} candle – {describe(rule)}",
              f"• Numbers : close {TP.fmt(sig['close'], t)} · ATR {TP.fmt(sig['atr'], t)} · RSI {sig['rsi']:.0f} · ADX {sig['adx']:.0f}"
              + (f" · volume {sig['vol_x']:.1f}×" if sig.get("vol_x") else ""),
              f"• Exit    : SL or T2 · time exit after {rule['maxh']} candles (~{max_days} sessions) · exit 1 session before expiry",
              f"• Strength: tier {rule.get('tier', 'B')} – {rule['n']} backtest trades, {rule['win']:.0f}% won, {rule['R']:+.2f}R avg after "
              f"2× costs, periods {rule['periods']} (backtest, not a guarantee)",
              WARN]))
        RP.add(state, key=rec["key"], mark_key=str(c["token"]), seg="MCX" if ex == "MCX" else "NSE", cat="FUTURES", name=name,
               symbol=c["symbol"], type=f"{TF_TXT[rule['tf']].capitalize()} {rule['fam']}", side=rule["side"], entry=plan["entry"],
               sl=plan["sl"], target=plan["target"], tick=t, lot=c.get("lot"), mult=mult, time=str(now))
        if rule.get("experimental") and state.get("ledger"):   # own category: strategies.conflict and the scorecard only read cat == FUTURES
            state["ledger"][-1].update(type=f"{TF_TXT[rule['tf']].capitalize()} BO (EXPERIMENTAL)", cat="FUTURES (EXPERIMENTAL)",
                                       experimental=True)
        state["day"]["alerts"] = state["day"].get("alerts", 0) + 1
        FN.note(state, rid, "sent", key=fk, now=now)
        out[rid] = "SENT"
        print(f"[rulebook] {name} {rid} SENT entry {plan['entry']} SL {plan['sl']} T {plan['target']}")
    return out


STOP_VALID_SESSIONS = 3          # research: trigger window = the 3 candles after the setup candle


def _stop_entry(state, msgs, st, rid, rule, sig, name, ex, c, q, api, now, mult, shadow, fk, last, after_close):
    """RSIX-style call: BUY-STOP above the setup candle's high (SELL-STOP below its low). Stored as a PENDING record;
    four_hour.track() activates it when the live price crosses the trigger, cancels it if the setup candle's other
    extreme breaks first, and expires it after STOP_VALID_SESSIONS sessions. Entry/SL/targets are fixed from the trigger."""
    from alerts import funnel as FN
    s_ = 1 if rule["side"] == "BUY" else -1
    t = float(c.get("tick") or 0.05)
    trig = TP.tick_round(sig["high"] if s_ > 0 else sig["low"], t)
    inv = sig["low"] if s_ > 0 else sig["high"]
    risk = rule["k"] * sig["atr"]
    if not risk > 0:
        FN.note(state, rid, "rejected", "ATR missing", key=fk, now=now); return "ATR missing"
    if q is None and not after_close and api is not None and hasattr(api, "quotes"):
        try:
            q = (api.quotes({ex: [str(c["token"])]}) or {}).get(str(c["token"]))
        except Exception:
            q = None
    ltp = float((q or {}).get("ltp") or 0)
    entry, pending = trig, True
    if ltp > 0 and s_ * (ltp - trig) > 0:                       # already through the trigger at the first look
        if s_ * (ltp - trig) > 0.5 * sig["atr"]:
            FN.note(state, rid, "rejected", "already ran > 0.5 ATR past the trigger", key=fk, now=now)
            return "already ran past the trigger"
        entry, pending = TP.tick_round(ltp, t), False
    if ltp > 0 and s_ * (ltp - inv) < 0:
        FN.note(state, rid, "rejected", "setup candle broken the other way", key=fk, now=now); return "setup broken"
    sl = TP.tick_round(entry - s_ * risk, t)
    tgt = TP.tick_round(entry + s_ * rule["r"] * risk, t)
    t1 = TP.tick_round(entry + s_ * risk, t)
    rec = dict(name=name, ex=ex, token=str(c["token"]), contract=c["symbol"], expiry=c["expiry"], side=rule["side"],
               entry=entry, stop=sl, target=tgt, risk=risk, tick=t, mult=mult, opened=str(now), days=[str(now.date())],
               key=f"RB|{rid}|{name}|{last}", max_days=int(rule["maxh"]), tfl=TF_TXT[rule["tf"]], rule=rid,
               trigger=trig, invalid=inv, pending=pending, pending_days=[str(now.date())],
               **({"shadow": True} if shadow else {}))
    st["open"].append(rec)
    if shadow:
        FN.note(state, rid, "shadow", key=fk, now=now); return "shadow"
    lot = c.get("lot")
    risk_lot = risk * float(mult or 1)
    word = ("BUY ABOVE" if s_ > 0 else "SELL BELOW") if pending else ("BUY NOW" if s_ > 0 else "SELL NOW")
    stage = "🟡 CONFIRMED SETUP – not a trade until triggered" if pending else "⚡ ACTIONABLE CALL – trigger already traded"
    msgs.append("\n".join([
        stage,
        f"{'🟢' if s_ > 0 else '🔴'} {word} {TP.fmt(trig, t)}  ·  {name} FUT  ·  DAILY · {rule.get('label', rid)}",
        "━━━━━━━━━━━━━━",
        f"Trigger : {TP.fmt(trig, t)} (reversal candle {'high' if s_ > 0 else 'low'}) – stop order, enter only if traded through",
        f"SL      : {TP.fmt(sl, t)}  (1.5 ATR)",
        f"T1      : {TP.fmt(t1, t)}  (1R)",
        f"T2      : {TP.fmt(tgt, t)}  ({rule['r']:g}R – exit here)",
        f"R:R     : 1:{rule['r']:g} · risk ₹{risk_lot:,.0f} per lot",
        f"Lot     : {lot or '-'}  ·  {pd.Timestamp(c['expiry']):%b} expiry  ·  MCX",
        f"Valid   : {STOP_VALID_SESSIONS} sessions · cancel if price trades {'below' if s_ > 0 else 'above'} {TP.fmt(inv, t)} first"
        + ("" if pending else " · ALREADY TRIGGERED")]))
    msgs.append("\n".join([
        f"📌 WHY – {name} {rule['side']} (daily)",
        f"• Signal  : {pd.Timestamp(sig['candle']):%d-%b} candle – {describe(rule)}",
        f"• Numbers : close {TP.fmt(sig['close'], t)} · ATR {TP.fmt(sig['atr'], t)} · ADX {sig['adx']:.0f}",
        f"• Exit    : SL or T2 · time exit after {rule['maxh']} sessions · exit 1 session before expiry",
        f"• Strength: tier {rule.get('tier', 'B')} – {rule['n']} backtest trades (2006-26, 7 commodities), {rule['win']:.0f}% won, "
        f"{rule['R']:+.2f}R avg after 2× costs, periods {rule['periods']} (backtest, not a guarantee)",
        WARN]))
    if not pending:
        RP.add(state, key=rec["key"], mark_key=str(c["token"]), seg="MCX", cat="FUTURES", name=name, symbol=c["symbol"],
               type="Daily RSIX", side=rule["side"], entry=entry, sl=sl, target=tgt, tick=t, lot=lot, mult=mult, time=str(now))
        state["day"]["alerts"] = state["day"].get("alerts", 0) + 1
    FN.note(state, rid, "sent" if not pending else "setup", key=fk, now=now)
    if not pending:
        FN.note(state, rid, "triggered", key=fk, now=now)
    print(f"[rulebook] {name} {rid} SENT {'pending trigger' if pending else 'entry'} {entry} SL {sl} T {tgt}")
    return "SENT (pending trigger)" if pending else "SENT"


def _early_warning(state, msgs, rid, rule, f, name, last, now):
    """EARLY WARNING (owner lifecycle, 6-Nov): the RSIX condition is forming (RSI touched the extreme, ADX < 20) but the
    reversal candle has not printed. Information only – never a trade, never in the ledger, max one per instrument+candle."""
    from alerts import funnel as FN
    n_, L = (int(x) for x in rule["par"].split("/"))
    r = I.rsi(f["close"].astype(float), n_)
    s_ = 1 if rule["side"] == "BUY" else -1
    ext = r.iloc[-3:].min() <= L if s_ > 0 else r.iloc[-3:].max() >= 100 - L
    if not (ext and float(f["adx"].iloc[-1]) < 20):
        return
    FN.note(state, rid, "early", key=f"{name}|{last}", now=now)
    seen = state.setdefault("early_seen", [])
    k = f"{rid}|{name}|{last}"
    if k in seen:
        return
    state["early_seen"] = (seen + [k])[-500:]
    msgs.append(f"👀 EARLY WARNING (info only – NOT a trade) · {name} daily: RSI({n_}) {r.iloc[-1]:.0f} after touching "
                f"{L if s_ > 0 else 100 - L}, ADX {float(f['adx'].iloc[-1]):.0f}. A {'BUY' if s_ > 0 else 'SELL'} setup needs a "
                f"{'bullish' if s_ > 0 else 'bearish'} reversal candle next; the call (with trigger/SL/target) follows only then.")


# ─────────────── 7-Nov-2026: trailing-stop rules (H1.12L, EXPERIMENTAL) ───────────────
def _trail_messages(rule, rid, sig, plan, c, t, s_, name, valid_to, after_close, max_days):
    """Call + WHY for a rule with a trailing stop and no fixed target. Clearly labelled experimental / unvalidated."""
    tr = rule["trail"]
    call = "\n".join([
        f"{'🟢 BUY' if s_ > 0 else '🔴 SELL'}  {name} FUT  ·  {TF_TXT[rule['tf']].upper()} · {rule.get('label', rid)}",
        "━━━━━━━━━━━━━━",
        "🧪 EXPERIMENTAL – NOT VALIDATED. Research candidate only; trade small or just observe.",
        f"Entry   : {TP.fmt(plan['entry'], t)}  (no chase beyond {TP.fmt(plan['entry'] + s_ * 0.5 * sig['atr'], t)})",
        f"SL      : {TP.fmt(plan['sl'], t)}  ({rule['k']:g} ATR) – then trails {tr:g} ATR behind the best {TF_TXT[rule['tf']]} close",
        "Target  : none – exit on the trailing stop (SL UPDATE messages follow)",
        f"Risk    : ₹{plan['risk_lot']:,.0f} per lot",
        f"Lot     : {c.get('lot') or '-'}  ·  {pd.Timestamp(c['expiry']):%b} expiry  ·  MCX",
        f"Valid   : enter by {valid_to:%d-%b %H:%M}" + (" (next session open)" if after_close else "")])
    why = "\n".join([
        f"📌 WHY – {name} {rule['side']} ({TF_TXT[rule['tf']]}) · EXPERIMENTAL",
        f"• Signal  : {pd.Timestamp(sig['candle']):%d-%b %H:%M} candle – first close above the 20-candle high",
        f"• Numbers : close {TP.fmt(sig['close'], t)} · ATR {TP.fmt(sig['atr'], t)} · RSI {sig['rsi']:.0f} · ADX {sig['adx']:.0f}",
        f"• Exit    : trailing stop ({tr:g} ATR on {TP.fmt(sig['atr'], t)} ATR) · time exit after {rule['maxh']} candles (~{max_days} sessions)"
        " · exit 1 session before expiry",
        f"• Evidence: research only – final test {rule['n']} trades, {rule['win']:.0f}% won, {rule['R']:+.2f}R avg after 2× costs, "
        f"{rule['periods']}. Wins only ~40 % of the time; profit depends on a few large trends. NOT validated.",
        WARN])
    return [call, why]


def _trail_update(state, msgs, st, name, frames):
    """On each completed candle: raise (BUY) / lower (SELL) the stop of open trailing-rule calls of this instrument to
    best close -/+ trail_atr x ATR (ATR of the signal candle, as in the research). Never loosens a stop. A message is sent
    when the stop has moved by >= 0.5 ATR since the last message (non-shadow calls only)."""
    for r in st.get("open", []):
        if r.get("name") != name or not r.get("trail_atr") or r.get("pending"):
            continue
        fr = frames.get(r.get("trail_tf"))
        if fr is None or not len(fr):
            continue
        new = fr[fr["time"] > pd.Timestamp(r["trail_from"])]
        if not len(new):
            continue
        s_ = 1 if r["side"] == "BUY" else -1
        closes = new["close"].astype(float)
        r["best"] = max(r["best"], float(closes.max())) if s_ > 0 else min(r["best"], float(closes.min()))
        ns = r["best"] - s_ * r["trail_atr"] * r["atr"]
        if s_ * (ns - r["stop"]) > 0:
            r["stop"] = round(ns, 2); r["trailed"] = True
            if not r.get("shadow") and s_ * (r["stop"] - r.get("trail_noted", r["stop"])) >= 0.5 * r["atr"]:
                msgs.append(f"🔁 SL UPDATE – {r['name']} FUT {r['side']} ({r.get('tfl', '')}) · EXPERIMENTAL: trailing stop now "
                            f"{TP.fmt(r['stop'], r.get('tick'))} (best close {TP.fmt(r['best'], r.get('tick'))})")
                r["trail_noted"] = r["stop"]
        r["trail_from"] = str(new["time"].iloc[-1])


# ─────────────── 7-Nov-2026: owner OI-breakout rule (UNTESTED) ───────────────
def _oi_hour(c, sig, now, oi):
    """OI change during the signal candle from the live 1-minute WebSocket bars (wsbars); fallback: the engine's quote
    reading (10-40 min). -> (pct or None, source). Never invented: None when no OI is available."""
    try:
        import wsbars as WB
        t0 = pd.Timestamp(sig["candle"]); t1 = t0 + pd.Timedelta(minutes=60)
        m = WB.minutes(str(c["token"]), t0.normalize())
        if m is not None and len(m) and "oi" in m:
            m = m[pd.to_numeric(m["oi"], errors="coerce") > 0]
            before, inside = m[m["time"] < t0], m[(m["time"] >= t0) & (m["time"] < t1)]
            if len(inside) >= 30:
                a = float(before["oi"].iloc[-1]) if len(before) else float(inside["oi"].iloc[0])
                b = float(inside["oi"].iloc[-1])
                if a > 0:
                    return (b / a - 1) * 100, "live 1-min OI, signal hour"
    except Exception:
        pass
    if oi and oi.get("chg_pct") is not None:
        return float(oi["chg_pct"]), f"quote OI, last {oi.get('gap_min', 0):.0f} min"
    return None, None


def _levels(fr, daily, side, close):
    """nearest swing level beyond the price in the trade direction: confirmed 1h pivots (last 200 candles, before the
    signal candle) and daily swing highs / lows + the previous day's high / low (last 60 completed sessions)."""
    lv = []
    f = fr.iloc[-201:-1] if len(fr) > 201 else fr.iloc[:-1]
    hi, lo = I.pivots(f.reset_index(drop=True), 2)
    lv += [p for _, p in (hi if side > 0 else lo)]
    if daily is not None and len(daily) > 3:
        d = daily.iloc[-61:-1] if len(daily) > 61 else daily.iloc[:-1]
        dh, dl = I.pivots(d.reset_index(drop=True), 2)
        lv += [p for _, p in (dh if side > 0 else dl)]
        lv.append(float(d["high"].iloc[-1]) if side > 0 else float(d["low"].iloc[-1]))
    beyond = [x for x in lv if side * (x - close) > 0]
    return (min(beyond) if side > 0 else max(beyond)) if beyond else None


def _owner_checks(rule, sig, fr, daily, c, now, oi):
    """-> rejection reason or None. Order: reversal wick, OI build-up, room to the target."""
    s_ = 1 if rule["side"] == "BUY" else -1
    rng = sig["high"] - sig["low"]
    if rule.get("wick_max") and rng > 0:
        wick = (sig["high"] - max(sig["open"], sig["close"])) if s_ > 0 else (min(sig["open"], sig["close"]) - sig["low"])
        if wick > rule["wick_max"] * rng:
            return f"reversing – rejection wick {wick / rng:.0%} of the candle"
    if rule.get("oi"):
        pct, src = _oi_hour(c, sig, now, oi)
        if pct is None:
            return "OI not available (no live OI feed / quote reading)"
        if not (pct > 0 and s_ * (sig["close"] - sig["open"]) > 0):
            return f"no {'long' if s_ > 0 else 'short'} build-up (OI {pct:+.2f}%, {src})"
        sig["oi_txt"] = f"OI {pct:+.2f}% with price {'up' if s_ > 0 else 'down'} → {'Long' if s_ > 0 else 'Short'} build-up ({src})"
    if rule.get("sr_room"):
        lvl = _levels(fr, daily, s_, sig["close"])
        need = rule["r"] * rule["k"] * sig["atr"]
        if lvl is not None and abs(lvl - sig["close"]) < need:
            return f"{'resistance' if s_ > 0 else 'support'} {lvl:,.2f} within the {rule['r']:g}R target"
        sig["room_txt"] = ("no swing level ahead" if lvl is None else
                           f"next {'resistance' if s_ > 0 else 'support'} {lvl:,.2f} is beyond the {rule['r']:g}R target")
    return None


def _untested_messages(rule, rid, sig, plan, c, t, s_, name, valid_to, after_close, max_days, t1, ex):
    call = "\n".join([
        f"{'🟢 BUY' if s_ > 0 else '🔴 SELL'}  {name} FUT  ·  {TF_TXT[rule['tf']].upper()} · {rule.get('label', rid)}",
        "━━━━━━━━━━━━━━",
        "🧪 EXPERIMENTAL – UNTESTED RULE (no backtest). Trade small or just observe.",
        f"Entry   : {TP.fmt(plan['entry'], t)}  (no chase beyond {TP.fmt(plan['entry'] + s_ * 0.5 * sig['atr'], t)})",
        f"SL      : {TP.fmt(plan['sl'], t)}  ({rule['k']:g} ATR – tight)",
        f"T1      : {TP.fmt(t1, t)}  (1R)",
        f"T2      : {TP.fmt(plan['target'], t)}  ({rule['r']:g}R – exit here)",
        f"R:R     : 1:{rule['r']:g} · risk ₹{plan['risk_lot']:,.0f} per lot",
        f"Lot     : {c.get('lot') or '-'}  ·  {pd.Timestamp(c['expiry']):%b} expiry  ·  {'MCX' if ex == 'MCX' else 'NSE'}",
        f"Valid   : enter by {valid_to:%d-%b %H:%M}" + (" (next session open)" if after_close else "")])
    why = "\n".join([
        f"📌 WHY – {name} {rule['side']} ({TF_TXT[rule['tf']]}) · EXPERIMENTAL / UNTESTED",
        f"• Signal  : {pd.Timestamp(sig['candle']):%d-%b %H:%M} candle – first close {'above the 20-candle high' if s_ > 0 else 'below the 20-candle low'}",
        f"• Volume  : {sig['vol_x']:.1f}× the 20-candle average (rule ≥ 2.5×)" if sig.get("vol_x") else "• Volume  : ≥ 2.5× (rule)",
        f"• OI      : {sig.get('oi_txt') or '-'}",
        f"• Room    : {sig.get('room_txt') or '-'} · no rejection wick",
        f"• Exit    : SL or T2 · time exit after {rule['maxh']} candles (~{max_days} sessions) · exit 1 session before expiry",
        "• Evidence: NONE – added without a backtest at the owner's request. Results are logged.",
        WARN])
    return [call, why]
