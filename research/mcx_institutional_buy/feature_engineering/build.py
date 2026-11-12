"""Feature + trigger construction for one commodity / timeframe. Everything causal (see ind.py).
Output dict F:
  arrays   time, o h l c (back-adjusted), raw_c, v, seg, atr, costf
  TRIG     name -> (signal bool, stop level, stop-entry level or NaN = next-bar open, family, module)
  COND     name -> bool (context conditions for combinations / regime splits)
  TGT      name -> target level (structural targets known at the signal bar)
  EV       sweep event descriptors (depth, recovery time, reclaim strength, RVOL, OI change)
"""
import numpy as np
import pandas as pd
from . import ind as I
from ..backtesting import data as D
from ..backtesting import costs as K

PIV_R = {"15m": 3, "30m": 3, "1h": 3, "4h": 2, "1d": 2}


def _period_levels(t, h, l, freq):
    """previous completed period's high / low (freq 'D', 'W', 'M') mapped to each bar."""
    key = t.dt.to_period(freq)
    g = pd.DataFrame(dict(k=key, h=h, l=l)).groupby("k").agg(h=("h", "max"), l=("l", "min"))
    ph = g.h.shift(1); pl = g.l.shift(1)
    return key.map(ph).values.astype(float), key.map(pl).values.astype(float)


def _daily(t, o, h, l, c, v):
    day = t.dt.normalize()
    g = pd.DataFrame(dict(day=day, o=o, h=h, l=l, c=c, v=v)).groupby("day").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"),
                                                                                c=("c", "last"), v=("v", "sum"))
    return day, g


def _map_prev_day(day, s):
    """value computed at the close of day d -> available on bars of the next trading day."""
    return day.map(s.shift(1)).values.astype(float)


def build(name, tf):
    b = D.bars(name, tf)
    if b is None or len(b) < 300:
        return None
    t = pd.to_datetime(b.time)
    o, h, l, c = (b[f"a_{x}"].values.astype(float) for x in ("open", "high", "low", "close"))
    v = b.volume.values.astype(float); seg = b.seg.values.astype(np.int64); n = len(c)
    raw_c = b.close.values.astype(float)
    atr = I.atr(h, l, c, 14)
    intraday = tf != "1d"
    F = dict(name=name, tf=tf, time=t.values, o=o, h=h, l=l, c=c, raw_c=raw_c, v=v, seg=seg, atr=atr,
             costf=K.cost_frac(name, raw_c, t), TRIG={}, COND={}, TGT={}, EV={})
    T, C = F["TRIG"], F["COND"]
    lw = lambda k: pd.Series(l).rolling(k, min_periods=1).min().values
    R = PIV_R[tf]
    pl, ph = I.pivots(l, h, R, R)
    PL, PLi = I.known_levels(pl, l, R, 6); PH, PHi = I.known_levels(ph, h, R, 10)

    def add(nm, sig, stop, fam, mod, elev=None):
        sig = np.asarray(sig, bool) & np.isfinite(stop) & np.isfinite(atr)
        T[nm] = (sig, np.asarray(stop, float), np.full(n, np.nan) if elev is None else np.asarray(elev, float), fam, mod)

    # ---------------- indicators ----------------
    rs = {k: I.rsi(c, k) for k in (7, 9, 14, 21)}
    m_line, m_hist = I.macd(c)
    st_k = I.stoch(h, l, c); srsi = I.stochrsi(rs[14]); cc = I.cci(h, l, c); mf = I.mfi(h, l, c, v); ob = I.obv(c, v)
    roc = 100 * (c / I.lag(c, 10) - 1); mom = c - I.lag(c, 10); wr = I.willr(h, l, c)
    pvol = -I.sma(v, 3)                                    # price-volume: lower low on LOWER volume = bullish
    dmom = (c - I.lag(c, 5)) / atr                         # downside momentum (ATR-normalised 5-bar change)
    e20, e50, e200 = I.ema(c, 20), I.ema(c, 50), I.ema(c, 200)
    vavg = pd.Series(v).rolling(20, min_periods=10).mean().shift(1).values
    rvol = v / np.where(vavg > 0, vavg, np.nan)
    vpct = pd.Series(v).rolling(100, min_periods=50).rank(pct=True).values
    rng = h - l; body = np.abs(c - o)
    F["ind"] = dict(rsi14=rs[14], rvol=rvol, e200=e200)

    # ---------------- HTF levels ----------------
    day, Dd = _daily(t, o, h, l, c, v)
    datr = I.atr(Dd.h.values, Dd.l.values, Dd.c.values, 14)
    datr_b = _map_prev_day(day, pd.Series(datr, index=Dd.index)) if intraday else I.lag(atr, 1)
    if intraday:
        pdh, pdl = _period_levels(t, h, l, "D")
    else:
        pdh, pdl = I.lag(h, 1), I.lag(l, 1)
    pwh, pwl = _period_levels(t, h, l, "W")
    pmh, pml = _period_levels(t, h, l, "M")
    dpl, dph = I.pivots(Dd.l.values, Dd.h.values, 2, 2)
    DPL, _ = I.known_levels(dpl, Dd.l.values, 2, 3)
    dsl = pd.Series(DPL[:, 0], index=Dd.index)
    dswing = _map_prev_day(day, dsl) if intraday else I.lag(DPL[:, 0], 0)
    lo3 = lw(3)
    near = lambda lv: np.isfinite(lv) & (np.abs(lo3 - lv) <= 0.5 * datr_b)
    C["AT_DSUP"] = near(pdl) | near(dswing)
    C["AT_WSUP"] = near(pwl)
    C["AT_MSUP"] = near(pml)
    r20h = pd.Series(h).rolling(20 if not intraday else 20 * {"15m": 26, "30m": 13, "1h": 7, "4h": 2}[tf]).max().values
    r20l = pd.Series(l).rolling(20 if not intraday else 20 * {"15m": 26, "30m": 13, "1h": 7, "4h": 2}[tf]).min().values
    pos = (c - r20l) / np.where(r20h - r20l > 0, r20h - r20l, np.nan)
    C["MIDRANGE"] = (pos > 0.35) & (pos < 0.65) & ~(C["AT_DSUP"] | C["AT_WSUP"] | C["AT_MSUP"])
    C["COUNTER"] = (c < e200) & (e50 < e200)
    C["TRANSITION"] = (e20 > e50) & (e50 < e200)
    C["UPTREND"] = (e50 > e200) & (c > e50)
    C["BELOW200"] = c < e200
    C["RSI_OS"] = pd.Series(rs[14]).rolling(5, min_periods=1).min().values < 30
    C["RVOL15"] = rvol >= 1.5; C["RVOL2"] = rvol >= 2.0; C["VOLPCT90"] = vpct >= 0.9
    down = c < o
    climax = (vpct >= 0.95) & (rng >= 1.5 * atr) & down
    C["VCLIMAX_RECENT"] = pd.Series(climax).rolling(3, min_periods=1).max().values.astype(bool)
    vex = (c < I.lag(c, 5)) & (I.sma(v, 3) < 0.7 * I.lag(I.sma(v, 10), 3))
    C["VEXHAUST"] = vex
    decline = (I.lag(pd.Series(h).rolling(10).max().values, 0) - c) >= 3 * atr
    lwick = (np.minimum(o, c) - l) >= 0.6 * rng
    C["EXHAUST"] = decline & (C["VCLIMAX_RECENT"] | pd.Series(lwick).rolling(3, min_periods=1).max().values.astype(bool))
    # low price impact per unit volume on down bars (proxy only: NOT observed absorption)
    impact = (rng / atr) / np.where(rvol > 0, rvol, np.nan)
    C["LOWIMPACT_PROXY"] = pd.Series(down & (rvol >= 1.5) & (impact < 0.5)).rolling(3, min_periods=1).max().values.astype(bool)
    C["BULL_CANDLE"] = (c > o) & ((c - l) >= 0.6 * rng)
    if intraday:
        tp = (h + l + c) / 3
        cv = pd.Series(v).groupby(day.values).cumsum().replace(0, np.nan).values
        vw = pd.Series(tp * v).groupby(day.values).cumsum().values / cv
        C["VWAP_ABOVE"] = c > vw
    else:
        vw = None

    # ---------------- OI (official end-of-day, previous completed day) ----------------
    try:
        oi = D.daily_oi(name)
    except Exception:
        oi = None
    if oi is not None and len(oi):
        dd = Dd.copy(); dd["oi"] = oi.oi.reindex(dd.index)
        dp3 = dd.c - dd.c.shift(3); doi3 = dd.oi - dd.oi.shift(3)
        z = doi3 / doi3.rolling(60, min_periods=20).std()
        v3 = dd.v.rolling(3).mean() / dd.v.rolling(20, min_periods=10).mean().shift(3)
        rng5 = (dd.h.rolling(5).max() - dd.l.rolling(5).min()) / pd.Series(datr, index=dd.index)
        st = {"OI_H1_PDN_VUP_OIUP": (dp3 < 0) & (v3 > 1.2) & (z > 0.5),       # possible short build-up
              "OI_H2_PDN_VUP_OIDN": (dp3 < 0) & (v3 > 1.2) & (z < -0.5),      # possible long liquidation
              "OI_H3_PDN_VDN_OIDN": (dp3 < 0) & (v3 < 0.8) & (z < -0.5),      # possible exhaustion of selling
              "OI_H4_FLAT_VUNUSUAL": (rng5 < 1.5) & (v3 > 1.5),               # unusual volume, stable price
              "OI_H5_PUP_VUP_OIUP": (dp3 > 0) & (v3 > 1.2) & (z > 0.5),       # possible new long participation
              "OI_H6_PUP_VUP_OIDN": (dp3 > 0) & (v3 > 1.2) & (z < -0.5)}      # possible short covering
        for k, s in st.items():
            C[k] = np.nan_to_num(_map_prev_day(day, s.astype(float)) if intraday else s.shift(0).astype(float).values) > 0
        C["OI_KNOWN"] = np.isfinite(_map_prev_day(day, dd.oi) if intraday else dd.oi.values)
        F["oi_daily"] = dd
    # ---------------- global benchmark (previous completed international day) ----------------
    px = D.proxy_daily(name)
    if px is not None:
        px = px[~px.index.duplicated()].sort_index()
        upd = (px.close > px.open) & (px.close > px.close.shift(1))
        dn2 = (px.close.diff() < 0).shift(1).rolling(2).sum() == 2
        g = pd.DataFrame(dict(UPDAY=upd, REV=upd & dn2, ABOVE5=px.close > px.close.rolling(5).mean()))
        u = D.usdinr(); u = u[~u.index.duplicated()].sort_index()
        g["USDINR_UP"] = (u / u.shift(5) - 1).reindex(g.index, method="ffill") > 0
        if name == "SILVER":
            gp = D.proxy_daily("GOLD"); gp = gp[~gp.index.duplicated()].sort_index()
            ratio = (gp.close / px.close.reindex(gp.index)).dropna()
            g["GSR_FALL"] = (ratio.diff(5) < 0).reindex(g.index).fillna(False)
        # strictly earlier international date than the MCX bar's date
        dd = pd.DataFrame(dict(day=day.values)); g.index = g.index + pd.Timedelta(days=1)
        for k in g.columns:
            s = pd.merge_asof(dd, g[[k]].astype(float).reset_index().rename(columns={g.index.name or "index": "day", "time": "day"}).sort_values("day"),
                              on="day", direction="backward")[k].values
            C[f"GLB_{k}"] = np.nan_to_num(s) > 0
        C["GLB_KNOWN"] = np.ones(n, bool)

    # ---------------- MODULE A: divergence ----------------
    IND = dict(RSI7=rs[7], RSI9=rs[9], RSI14=rs[14], RSI21=rs[21], MACD=m_line, MACDH=m_hist, STOCH=st_k, STOCHRSI=srsi,
               CCI=cc, MFI=mf, OBV=ob, ROC=roc, MOM=mom, WILLR=wr, PVOL=pvol, DOWNMOM=dmom)
    CLUSTER = dict(RSI7="osc", RSI9="osc", RSI14="osc", RSI21="osc", STOCH="osc", STOCHRSI="osc", CCI="osc", WILLR="osc", ROC="osc",
                   MOM="osc", DOWNMOM="osc", MACD="macd", MACDH="macd", OBV="vol", MFI="vol", PVOL="vol")
    regR3 = {}
    for Rp in (2, 3, 5):
        plp, _ = I.pivots(l, h, Rp, Rp) if Rp != R else (pl, ph)
        for nm_, x in IND.items():
            for hid in (False, True):
                sig, p2 = I.divergence(l, np.asarray(x, float), plp, Rp, 5, 60, hid)
                stop = np.full(n, np.nan); ii = np.where(sig)[0]
                for i in ii:
                    stop[i] = l[p2[i]:i + 1].min() - 0.2 * atr[i]
                add(f"DIV_{nm_}_{'HID' if hid else 'REG'}_R{Rp}", sig, stop, "EARLY", "A_divergence")
                if Rp == 3 and not hid:
                    regR3[nm_] = (sig, stop)
    sigs = np.array([regR3[k][0] for k in regR3]); stops = np.array([regR3[k][1] for k in regR3])
    clus = np.array([CLUSTER[k] for k in regR3])
    ncl = sum(sigs[clus == q].any(axis=0).astype(int) for q in ("osc", "macd", "vol"))
    anyd = sigs.any(axis=0); stp_any = np.nanmin(np.where(sigs, stops, np.nan), axis=0) if anyd.any() else np.full(n, np.nan)
    add("DIV_ANY_REG_R3", anyd, stp_any, "EARLY", "A_divergence")
    add("DIV_MULTI2CLUSTER_R3", ncl >= 2, stp_any, "EARLY", "A_divergence")
    add("DIV_MULTI3CLUSTER_R3", ncl >= 3, stp_any, "EARLY", "A_divergence")
    # sequential: RSI14 regular divergence now AND at the previous pivot pair (three falling lows, rising RSI)
    s14, st14 = regR3["RSI14"]
    prev = pd.Series(np.where(s14, 1.0, np.nan)).ffill(limit=60).shift(1).fillna(0).values > 0
    add("DIV_SEQ_RSI14_R3", s14 & prev, st14, "EARLY", "A_divergence")
    C["DIV_RECENT"] = pd.Series(anyd).rolling(5, min_periods=1).max().values.astype(bool)
    F["div_delay_bars"] = {2: 2, 3: 3, 5: 5}

    # ---------------- MODULE B: RSI extremes ----------------
    for k, r in rs.items():
        stp = lw(5) - 0.2 * atr
        add(f"RSI{k}_BELOW25", I.first(r < 25), stp, "EARLY", "B_rsi")
        add(f"RSI{k}_CROSSUP25", I.cross_up(r, 25), stp, "EARLY", "B_rsi")
        rec = (pd.Series(r).rolling(5, min_periods=1).min().values <= 25) & (r >= 30)
        add(f"RSI{k}_TOUCH25_RECOVER30", I.first(rec), stp, "EARLY", "B_rsi")
        rl = I.run_len(r < 25)
        add(f"RSI{k}_BELOW25X3_CROSSUP", I.cross_up(r, 25) & (I.lag(rl, 1) >= 3), stp, "EARLY", "B_rsi")
        add(f"RSI{k}_LT30_STRUCT", (pd.Series(r).rolling(5, min_periods=1).min().values < 30) & (c > I.lag(h, 1)) & (c > o), stp, "EARLY", "B_rsi")
        st75 = lw(5) - 0.2 * atr
        add(f"RSI{k}_CROSS75", I.cross_up(r, 75), st75, "CONF", "B_rsi_cont")
        add(f"RSI{k}_ABOVE75X3", I.run_len(r > 75) == 3, st75, "CONF", "B_rsi_cont")
        add(f"RSI{k}_CROSS75_RVOL", I.cross_up(r, 75) & (rvol >= 1.5), st75, "CONF", "B_rsi_cont")
        hhhl = (PH[:, 0] > PH[:, 1]) & (PL[:, 0] > PL[:, 1])
        add(f"RSI{k}_CROSS75_HHHL", I.cross_up(r, 75) & hhhl, st75, "CONF", "B_rsi_cont")
    # candles
    prior_dn = I.lag(c, 1) < I.lag(c, 4)
    lwk = np.minimum(o, c) - l; uwk = h - np.maximum(o, c)
    hammer = prior_dn & (lwk >= 2 * body) & (uwk <= np.maximum(body, 0.1 * rng)) & (rng >= 0.5 * atr)
    engulf = prior_dn & (I.lag(c, 1) < I.lag(o, 1)) & (c > o) & (o <= I.lag(c, 1)) & (c >= I.lag(o, 1))
    mstar = (I.lag(c, 2) < I.lag(o, 2)) & (np.abs(I.lag(c, 1) - I.lag(o, 1)) <= 0.3 * I.lag(rng, 1)) & (c > o) & (c > (I.lag(o, 2) + I.lag(c, 2)) / 2)
    pierce = prior_dn & (I.lag(c, 1) < I.lag(o, 1)) & (o < I.lag(l, 1) + 0.1 * atr) & (c > (I.lag(o, 1) + I.lag(c, 1)) / 2) & (c < I.lag(o, 1))
    lwick_rej = prior_dn & (lwk >= 0.6 * rng) & (rng >= atr)
    strong = (c > o) & ((c - l) >= 0.8 * rng) & (rng >= 1.2 * atr)
    inside = (I.lag(h, 1) <= I.lag(h, 2)) & (I.lag(l, 1) >= I.lag(l, 2))
    ibo = inside & (c > I.lag(h, 2))
    CAN = dict(HAMMER=(hammer, 1), ENGULF=(engulf, 2), MSTAR=(mstar, 3), PIERCE=(pierce, 2), LWICK=(lwick_rej, 1), STRONGCLOSE=(strong, 1),
               INSIDEBO=(ibo, 3))
    for k, (s, nb) in CAN.items():
        stp = lw(nb) - 0.1 * atr
        add(f"CANDLE_{k}", s, stp, "EARLY", "B_candle")
        add(f"CANDLE_{k}_HIGHBO", s, stp, "EARLY", "B_candle", elev=h + 1e-9)

    # ---------------- MODULE C: liquidity sweeps ----------------
    eql = np.isfinite(PL[:, 1]) & (np.abs(PL[:, 0] - PL[:, 1]) <= 0.25 * atr)
    pk = np.array([h[int(PLi[i, 1]):int(PLi[i, 0]) + 1].max() if PLi[i, 1] >= 0 and PLi[i, 0] > PLi[i, 1] else np.nan for i in range(n)]) \
        if n else np.array([])
    dbl = np.isfinite(PL[:, 1]) & (np.abs(PL[:, 0] - PL[:, 1]) <= 0.5 * atr) & ((PLi[:, 0] - PLi[:, 1]) >= 5) & \
        ((pk - np.maximum(PL[:, 0], PL[:, 1])) >= 1.5 * atr)
    LEV = dict(PDL=pdl, PWL=pwl, PML=pml, SWING=PL[:, 0], EQL=np.where(eql, np.fmin(PL[:, 0], PL[:, 1]), np.nan),
               DBL=np.where(dbl, np.fmin(PL[:, 0], PL[:, 1]), np.nan))
    sweep_any = np.zeros(n, bool)
    for k, lv in LEV.items():
        sw = np.isfinite(lv) & (l < lv) & (c > lv)                         # traded below, closed back above
        sw = sw & ~np.r_[False, sw[:-1]]
        _sweep_family(add, F, f"SWEEP_{k}", sw, lv, o, h, l, c, atr, rvol, PH, ph, R, n)
        sweep_any |= sw
    # support breakdown then reclaim within 1–5 bars (level = PDL or swing low)
    for k, lv in (("PDL", pdl), ("SWING", PL[:, 0])):
        below = np.isfinite(lv) & (c < lv)                     # a CLOSE below support = breakdown; level frozen there
        rec = np.zeros(n, bool); lvl = np.full(n, np.nan)
        lastb = -999; frozen = np.nan
        for i in range(n):
            if below[i] and (i - lastb > 5 or not np.isfinite(frozen)):
                frozen = lv[i]
            if below[i]:
                lastb = i
            elif np.isfinite(frozen) and c[i] > frozen and 1 <= i - lastb <= 5 and seg[i] == seg[max(lastb, 0)]:
                rec[i] = True; lvl[i] = frozen; frozen = np.nan; lastb = -999
        _sweep_family(add, F, f"SWEEP_BDRECLAIM_{k}", rec, lvl, o, h, l, c, atr, rvol, PH, ph, R, n)
        sweep_any |= rec
    if intraday:
        swept_today = pd.Series(np.isfinite(pdl) & (l < pdl)).groupby(day.values).cummax().values.astype(bool)
        fbv = swept_today & I.cross_up(c - vw, 0)
        fbv = fbv & (pd.Series(fbv.astype(int)).groupby(day.values).cumsum().values == 1)
        _sweep_family(add, F, "SWEEP_FBVWAP", fbv, pdl, o, h, l, c, atr, rvol, PH, ph, R, n)
        sweep_any |= fbv
    C["SWEPT_RECENT"] = pd.Series(sweep_any).rolling(5, min_periods=1).max().values.astype(bool)

    # ---------------- MODULE F: market structure (confirmed) ----------------
    dtrend = (PH[:, 0] < PH[:, 1]) & (PL[:, 1] < PL[:, 2])               # descending highs, previous lows descending
    hl = PL[:, 0] > PL[:, 1]
    bos = (c > PH[:, 0]) & (I.lag(c, 1) <= PH[:, 0])
    stp_hl = PL[:, 0] - 0.1 * atr
    add("MS_MSS_HL_BREAK_LH", bos & hl & dtrend, stp_hl, "CONF", "F_structure")
    add("MS_BOS_LH", bos & dtrend, np.fmin(PL[:, 0], lw(5)) - 0.1 * atr, "CONF", "F_structure")
    hl_new = np.r_[False, (PLi[1:, 0] != PLi[:-1, 0])] & hl & (PL[:, 1] < PL[:, 2])   # first bar a HL after a LL is known
    add("MS_HL_CONFIRMED", hl_new, stp_hl, "CONF", "F_structure")
    add("MS_MSS_RVOL", bos & hl & dtrend & (rvol >= 1.5), stp_hl, "CONF", "F_structure")
    # retest of the broken lower high within 10 bars
    ret = np.zeros(n, bool); rstop = np.full(n, np.nan)
    for i in np.where(bos & dtrend)[0]:
        lv = PH[i, 0]
        for j in range(i + 1, min(i + 11, n)):
            if seg[j] != seg[i] or c[j] < lv - 0.5 * atr[j]:
                break
            if l[j] <= lv + 0.2 * atr[j] and c[j] > lv:
                ret[j] = True; rstop[j] = l[i:j + 1].min() - 0.1 * atr[j]; break
    add("MS_BOS_RETEST", ret, rstop, "CONF", "F_structure")
    if intraday:
        rb = I.run_len(c < vw)
        add("MS_VWAP_RECLAIM", (c > vw) & (I.lag(rb, 1) >= 6), lw(6) - 0.1 * atr, "CONF", "F_structure")
    C["HL_RECENT"] = pd.Series(hl_new).rolling(5, min_periods=1).max().values.astype(bool)
    C["BOS_RECENT"] = pd.Series(bos).rolling(5, min_periods=1).max().values.astype(bool)

    # ---------------- MODULE D: volume triggers ----------------
    add("VOL_CLIMAX_REVERSAL", (I.lag(climax.astype(float), 1) > 0) & (c > o) & (c > I.lag(c, 1)), lw(2) - 0.1 * atr, "EARLY", "D_volume")
    add("VOL_EXHAUST_BULLBAR", vex & C["BULL_CANDLE"], lw(5) - 0.1 * atr, "EARLY", "D_volume")
    add("VOL_LOWIMPACT_PROXY_BULLBAR", C["LOWIMPACT_PROXY"] & C["BULL_CANDLE"], lw(5) - 0.1 * atr, "EARLY", "D_volume")
    if not intraday and "OI_H1_PDN_VUP_OIUP" in C:
        for k in [x for x in C if x.startswith("OI_H")]:
            add(f"VOLOI_{k[3:]}", I.first(C[k]), lw(3) - 0.2 * atr, "EARLY" if "PDN" in k else "CONF", "D_volume_oi")

    # ---------------- baselines ----------------
    add("BASE_RSI14_CROSSUP30", I.cross_up(rs[14], 30), lw(5) - 0.2 * atr, "BASE", "baseline")
    add("BASE_BREAKOUT20", I.first(c > I.lag(pd.Series(h).rolling(20).max().values, 1)), lw(5) - 0.2 * atr, "BASE", "baseline")
    every = np.zeros(n, bool); every[::10] = True
    add("BASE_RANDOM_EVERY10", every, c - atr, "BASE", "baseline")
    add("BASE_RANDOM_EVERY10_SAMESTOP", every, lw(3) - 0.1 * atr, "BASE", "baseline")

    # ---------------- structural targets (known at the signal bar) ----------------
    above = np.where(PH > c[:, None], PH, np.nan)
    F["TGT"]["SWING"] = np.nanmin(np.where(np.isfinite(above), above, np.inf), axis=1)
    F["TGT"]["SWING"][~np.isfinite(F["TGT"]["SWING"])] = np.nan
    cand = np.c_[np.where(pwh > c, pwh, np.nan), np.where(pmh > c, pmh, np.nan), np.where(pdh > c, pdh, np.nan) if intraday else np.full(n, np.nan)]
    with np.errstate(all="ignore"):
        F["TGT"]["HTF"] = np.nanmin(cand, axis=1)
    return F


def _sweep_family(add, F, base, sw, lv, o, h, l, c, atr, rvol, PH, ph, R, n):
    """one sweep definition -> four entry variants + event descriptors."""
    idx = np.where(sw)[0]
    sweep_low = np.full(n, np.nan); depth = np.full(n, np.nan); strength = np.full(n, np.nan)
    for i in idx:
        j = i
        while j > 0 and j > i - 10 and l[j - 1] < lv[i]:
            j -= 1
        sweep_low[i] = l[j:i + 1].min(); depth[i] = (lv[i] - sweep_low[i]) / atr[i]; strength[i] = (c[i] - lv[i]) / atr[i]
    stop = sweep_low - 0.1 * atr
    add(f"{base}_RECLAIM", sw, stop, "EARLY", "C_sweep")
    add(f"{base}_HIGHBO", sw, stop, "EARLY", "C_sweep", elev=h + 1e-9)
    # next higher low: first pivot low (known) after the sweep with low > sweep low, within 20 bars; stop below it
    hl = np.zeros(n, bool); hst = np.full(n, np.nan)
    # retest: close above the nearest known pivot high (lower high) after the sweep, then a retest within 10 bars
    rt = np.zeros(n, bool); rst = np.full(n, np.nan)
    seg = F["seg"]
    for i in idx:
        sl = sweep_low[i]; lh = PH[i, 0]
        for j in range(i + 1, min(i + 21, n - R)):
            if seg[j] != seg[i] or l[j] < sl:
                break
            p = j - R                                           # pivot at p known at j
            if p > i and l[p] == l[p - R:p + R + 1].min() and l[p] > sl:
                hl[j] = True; hst[j] = l[p] - 0.1 * atr[j]; break
        if np.isfinite(lh) and lh > c[i]:
            brk = -1
            for j in range(i + 1, min(i + 21, n)):
                if seg[j] != seg[i] or l[j] < sl:
                    break
                if brk < 0 and c[j] > lh:
                    brk = j; continue
                if brk >= 0 and j - brk <= 10 and l[j] <= lh + 0.2 * atr[j] and c[j] > lh:
                    rt[j] = True; rst[j] = l[i:j + 1].min() - 0.1 * atr[j]; break
    add(f"{base}_NEXTHL", hl, hst, "CONF", "C_sweep")
    add(f"{base}_LHBREAK_RETEST", rt, rst, "CONF", "C_sweep")
    F["EV"][base] = dict(sig=sw, depth_atr=depth, reclaim_atr=strength, rvol=rvol)
