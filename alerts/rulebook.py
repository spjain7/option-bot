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
def _r(mkt, tf, fam, par, filt, side, k, r, maxh, n, win, R, periods, tier, label, status="LIVE"):
    return dict(mkt=mkt, tf=tf, fam=fam, par=par, filt=filt, side=side, k=k, r=r, maxh=maxh, n=n, win=win, R=R, periods=periods,
                tier=tier, label=label, status=status)


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
    "RB_STK_1d_RSI80_BUY": _r("STOCKS", "1d", "RSICONT", "80/20", "DT", "BUY", 2.0, 3.0, 20, 234, 55, 0.27, "+0.33/+0.19/+0.19", "B",
                              "RSI momentum above 80"),
}


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
        N = int(par.split()[0][1:]); vx = float(par.split("vol")[1]) if "vol" in par else 0.0
        hh, ll = hs.shift(1).rolling(N).max().values, ls.shift(1).rolling(N).min().values
        vb = volx >= vx if vx else np.ones(n, bool)
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
    return dict(candle=str(f["time"].iloc[i]), close=c, atr=float(f["atr"].iloc[i]), adx=float(f["adx"].iloc[i]),
                rsi=float(f["rsi"].iloc[i]), vol_x=float(f["volx"].iloc[i]) if f["volx"].iloc[i] == f["volx"].iloc[i] else None)


def describe(rule):
    fam, par = rule["fam"], rule["par"]
    txt = {"BO": f"close beyond the {par.split()[0][1:]}-candle high/low", "PB": f"pull-back to EMA{par.split('/')[0][3:]} in an EMA trend",
           "NR7": "break of the narrowest candle of 7", "RSIREV": f"RSI back inside {par}", "RSICONT": f"RSI momentum beyond {par}",
           "RSIDIV": "RSI divergence at a 10-candle extreme", "MACD": f"MACD {par} cross", "ST": "Supertrend (10, 3) flip",
           "EMAX": f"EMA {par} cross", "INSIDE": "inside-bar breakout", "PIN": "pin bar at a 20-candle extreme",
           "MOMO": "momentum candle (body ≥ 1.5 ATR)", "FAIL": "failed 20-candle breakout – reversal",
           "RETEST": "breakout retest of the 20-candle level"}.get(fam, fam)
    flt = {"none": "", "DT": " · with the daily trend", "EMA200": " · EMA200 side", "ADX25": " · ADX ≥ 25"}.get(rule["filt"], " · " + rule["filt"])
    return txt + flt


# ── live hook ────────────────────────────────────────────────────────────────────────────────────────────────────────
def run(state, msgs, api, name, ex, c, frames, daily, q, now, mult, mkt, after_close=False):
    """frames: {tf: completed candles}. Checks every rule of this market. Returns {rule_id: outcome}."""
    from alerts import funnel as FN, four_hour as FH, strategies as ST
    out = {}
    st = FH.store(state)
    seen = state.setdefault("rulebook_seen", [])
    dtr = daily_trend_map(daily)
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
            continue
        fk = f"{name}|{last}"
        FN.note(state, rid, "signal", key=fk, now=now)
        if sig.get("rejected"):
            FN.note(state, rid, "rejected", sig["rejected"], key=fk, now=now); out[rid] = sig["rejected"]; continue
        shadow = rule["status"] != "LIVE"
        clash = None if shadow else ST.conflict(state, name, rule["side"])
        if clash:
            FN.note(state, rid, "rejected", clash, key=fk, now=now); out[rid] = clash; continue
        if any(r["name"] == name and r.get("rule") == rid for r in st["open"]):
            FN.note(state, rid, "rejected", "already open", key=fk, now=now); out[rid] = "already open"; continue
        if q is None and not after_close and api is not None and hasattr(api, "quotes"):
            try:                                          # quote only when a signal actually fires (saves the Angel quota)
                q = (api.quotes({ex: [str(c["token"])]}) or {}).get(str(c["token"]))
            except Exception:
                q = None
        live = None if after_close else (float((q or {}).get("ltp") or 0) or None)
        plan = TP.futures_plan(name=name, ex=ex, contract=c["symbol"], tf=rule["tf"], side=rule["side"], signal_time=sig["candle"],
                               signal_close=sig["close"], atr=sig["atr"], stop_mult=rule["k"], target_r=rule["r"], tick=c.get("tick"),
                               lot=c.get("lot"), mult=mult, max_sl_pct=rule.get("cap", 0.0), live=live,
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
        st["open"].append(rec)
        if shadow:
            FN.note(state, rid, "shadow", key=fk, now=now); out[rid] = "shadow"
            print(f"[rulebook] {name} {rid} logged only: entry {plan['entry']} SL {plan['sl']} T {plan['target']}")
            continue
        rr = rule["r"]
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
        state["day"]["alerts"] = state["day"].get("alerts", 0) + 1
        FN.note(state, rid, "sent", key=fk, now=now)
        out[rid] = "SENT"
        print(f"[rulebook] {name} {rid} SENT entry {plan['entry']} SL {plan['sl']} T {plan['target']}")
    return out
