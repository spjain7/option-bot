"""Market intelligence for futures calls (P2/P3, 4-Nov-2026) – regime, structure, volume, VWAP, OI context and an
explainable setup grade. Used in SHADOW mode first: every futures call gets a grade and reasons in the ledger; nothing is
blocked and no message changes unless config switches say so (INTEL_IN_MESSAGE / INTEL_BLOCK).

Data honesty: inputs are OHLCV candles (completed only) and exchange OI. Nothing here sees real orders; "accumulation",
"distribution" or "liquidity" labels are price/volume/OI footprints, named as such.

The grade is a rule-based quality class (A / B / C / NO TRADE) with reasons – NOT a probability of profit. It may be
calibrated only after enough independent live outcomes (alerts/EXPERIMENTS.md, INTEL-001).
"""
import math
import numpy as np
import pandas as pd

GRADE_VERSION = "intel-1.0"         # stored with every grade; change it whenever a grading rule changes (INTEL-001 is per version)
ADX_TREND, ADX_RANGE = 22.0, 18.0
VOL_EXP, VOL_CON = 1.25, 0.8            # ATR(14) vs its 100-bar median
REL_VOL_HIGH, REL_VOL_ABN = 1.5, 2.5
PIVOT_K = 3


# ─────────── basic indicators (completed candles; Wilder smoothing) ───────────
def _ema(x, n):
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def _rma(x, n):
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def _atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return _rma(tr, n)


def _adx(df, n=14):
    h, l = df["high"], df["low"]
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    a = _atr(df, n)
    pdi, mdi = 100 * _rma(pdm, n) / a, 100 * _rma(mdm, n) / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return _rma(dx, n), pdi, mdi


def _rsi(c, n=14):
    d = c.diff()
    up, dn = _rma(d.clip(lower=0), n), _rma((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _f(x):
    try:
        x = float(x)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


# ─────────── structure ───────────
def swings(df, k=PIVOT_K):
    """Confirmed swing highs / lows (pivot with k candles each side; the last k candles cannot be pivots yet)."""
    h, l = df["high"].values, df["low"].values
    hi, lo = [], []
    for i in range(k, len(df) - k):
        if h[i] == max(h[i - k:i + k + 1]) and h[i] > max(h[i - k:i]):
            hi.append((i, float(h[i])))
        if l[i] == min(l[i - k:i + k + 1]) and l[i] < min(l[i - k:i]):
            lo.append((i, float(l[i])))
    return hi, lo


def structure(df, atr=None):
    """Swing sequence (HH/HL, LH/LL), last break of structure (BOS) / change of character (CHoCH), equal highs / lows,
    nearest swing support / resistance, failed breakout of the last candle."""
    out = dict(trend="unclear", event=None, eq_highs=False, eq_lows=False, support=None, resistance=None, failed_breakout=None)
    if df is None or len(df) < 4 * PIVOT_K + 5:
        return out
    hi, lo = swings(df)
    c = float(df["close"].iloc[-1])
    a = atr if atr else float(_atr(df).iloc[-1] or 0) or None
    if len(hi) >= 2 and len(lo) >= 2:
        hh, hl = hi[-1][1] > hi[-2][1], lo[-1][1] > lo[-2][1]
        lh, ll = hi[-1][1] < hi[-2][1], lo[-1][1] < lo[-2][1]
        out["trend"] = "up (HH + HL)" if hh and hl else "down (LH + LL)" if lh and ll else "mixed"
        if a:
            out["eq_highs"] = abs(hi[-1][1] - hi[-2][1]) <= 0.15 * a
            out["eq_lows"] = abs(lo[-1][1] - lo[-2][1]) <= 0.15 * a
    if hi:
        last_h = hi[-1][1]
        if c > last_h:
            out["event"] = "BOS up" if out["trend"].startswith("up") else "CHoCH up"
    if lo and out["event"] is None:
        last_l = lo[-1][1]
        if c < last_l:
            out["event"] = "BOS down" if out["trend"].startswith("down") else "CHoCH down"
    res = [p for _, p in hi if p > c]
    sup = [p for _, p in lo if p < c]
    out["resistance"] = min(res) if res else None
    out["support"] = max(sup) if sup else None
    if len(df) >= 21:
        prev_hi = float(df["high"].iloc[-21:-1].max()); prev_lo = float(df["low"].iloc[-21:-1].min())
        last = df.iloc[-1]
        if last["high"] > prev_hi and last["close"] < prev_hi:
            out["failed_breakout"] = "up (wick above the 20-candle high, closed back inside)"
        elif last["low"] < prev_lo and last["close"] > prev_lo:
            out["failed_breakout"] = "down (wick below the 20-candle low, closed back inside)"
    return out


# ─────────── volume / VWAP / OI ───────────
def volume_state(df, n=20):
    if df is None or "volume" not in df or len(df) < n + 2:
        return dict(rel=None, label="volume n/a", divergence=None)
    v = df["volume"].astype(float)
    base = v.iloc[-n - 1:-1].mean()
    if not base or base <= 0 or not math.isfinite(base):
        return dict(rel=None, label="volume n/a (no traded volume)", divergence=None)
    rel = float(v.iloc[-1] / base)
    label = ("abnormal" if rel >= REL_VOL_ABN else "high" if rel >= REL_VOL_HIGH else "normal" if rel >= 0.7 else "low")
    c = df["close"].astype(float)
    up5, vol5 = c.iloc[-1] > c.iloc[-6], v.iloc[-5:].mean() > v.iloc[-25:-5].mean() if len(df) >= 26 else None
    div = None
    if vol5 is not None:
        div = ("price up on falling volume" if up5 and not vol5 else "price down on falling volume" if not up5 and not vol5 else None)
    return dict(rel=round(rel, 2), label=f"{label} ({rel:.1f}× 20-candle avg)", divergence=div)


def session_vwap(intraday):
    """Today's session VWAP from intraday candles (completed) -> dict(vwap, state). None when there is no volume."""
    if intraday is None or len(intraday) < 2 or "volume" not in intraday:
        return dict(vwap=None, state="VWAP n/a")
    d = intraday[intraday["time"].dt.normalize() == intraday["time"].iloc[-1].normalize()]
    vol = d["volume"].astype(float)
    if len(d) < 2 or vol.sum() <= 0:
        return dict(vwap=None, state="VWAP n/a (no session volume)")
    tp = (d["high"] + d["low"] + d["close"]) / 3
    vw = (tp * vol).cumsum() / vol.cumsum()
    c, pc, v, pv = float(d["close"].iloc[-1]), float(d["close"].iloc[-2]), float(vw.iloc[-1]), float(vw.iloc[-2])
    if pc <= pv and c > v:
        st = "reclaimed VWAP"
    elif pc >= pv and c < v:
        st = "lost VWAP (rejection)"
    elif c > v:
        st = "above VWAP"
    else:
        st = "below VWAP"
    return dict(vwap=round(v, 2), state=st)


def oi_state(price_chg, oi_chg, min_oi_pct=0.5):
    """Exchange OI change vs price change -> classic buildup label (a footprint, not proof of who traded)."""
    p, o = _f(price_chg), _f(oi_chg)
    if p is None or o is None:
        return "OI n/a"
    if abs(o) < min_oi_pct:
        return "OI flat"
    return ("Long buildup" if p > 0 and o > 0 else "Short buildup" if p < 0 and o > 0 else
            "Short covering" if p > 0 and o < 0 else "Long unwinding")


# ─────────── regime ───────────
def regime(df):
    """Regime of one timeframe (completed candles). Returns primary label + all tags + the numbers behind them."""
    if df is None or len(df) < 60:
        return dict(primary="unknown (not enough candles)", tags=[], adx=None)
    c = df["close"].astype(float)
    e20, e50 = _ema(c, 20), _ema(c, 50)
    e200 = _ema(c, 200) if len(df) >= 200 else e50
    adx, pdi, mdi = _adx(df)
    a = _atr(df)
    atr_ratio = float(a.iloc[-1] / a.iloc[-100:].median()) if len(a.dropna()) >= 30 else 1.0
    r = float(_rsi(c).iloc[-1])
    ad, pd_, md_ = float(adx.iloc[-1]), float(pdi.iloc[-1]), float(mdi.iloc[-1])
    last = float(c.iloc[-1])
    bull_stack = last > e20.iloc[-1] > e50.iloc[-1] > e200.iloc[-1]
    bear_stack = last < e20.iloc[-1] < e50.iloc[-1] < e200.iloc[-1]
    hh20, ll20 = float(df["high"].iloc[-21:-1].max()), float(df["low"].iloc[-21:-1].min())
    tags = []
    if ad >= ADX_TREND and pd_ > md_ and bull_stack:
        primary = "Bullish trending"
    elif ad >= ADX_TREND and md_ > pd_ and bear_stack:
        primary = "Bearish trending"
    elif ad < ADX_RANGE:
        primary = "Sideways"
    else:
        primary = "Transition (trend not confirmed)"
    if atr_ratio >= VOL_EXP:
        tags.append("Volatility expansion")
    elif atr_ratio <= VOL_CON:
        tags.append("Volatility contraction")
    if last > hh20:
        tags.append("Breakout environment")
    elif last < ll20:
        tags.append("Breakdown environment")
    if (primary == "Bullish trending" and r >= 75) or (primary == "Bearish trending" and r <= 25):
        tags.append("Stretched (RSI extreme in trend)")
    st = structure(df, float(a.iloc[-1]))
    if (primary == "Bullish trending" and st["event"] == "CHoCH down") or (primary == "Bearish trending" and st["event"] == "CHoCH up"):
        tags.append("Potential reversal (change of character)")
    return dict(primary=primary, tags=tags, adx=round(ad, 1), di=round(pd_ - md_, 1), atr_ratio=round(atr_ratio, 2), rsi=round(r, 1),
                ema="bull stack" if bull_stack else "bear stack" if bear_stack else "mixed")


def htf_bias(daily):
    """Daily bias: close vs EMA50 and EMA50 slope (previous completed days only are expected as input)."""
    if daily is None or len(daily) < 60:
        return "unknown"
    c = daily["close"].astype(float)
    e = _ema(c, 50)
    if c.iloc[-1] > e.iloc[-1] and e.iloc[-1] > e.iloc[-6]:
        return "bullish"
    if c.iloc[-1] < e.iloc[-1] and e.iloc[-1] < e.iloc[-6]:
        return "bearish"
    return "neutral"


# ─────────── grade ───────────
FAMILY_REGIMES = {   # which regimes suit which setup family (from the project's research record)
    "breakout": ("Bullish trending", "Bearish trending", "Transition (trend not confirmed)"),
    "pullback": ("Bullish trending", "Bearish trending"),
    "reversal": ("Sideways", "Transition (trend not confirmed)"),
}


def grade(side, family, sig_df, daily=None, intraday=None, plan=None, oi_label=None, data_ok=True):
    """Explainable quality class for one futures setup. side BUY/SELL, family breakout/pullback/reversal.
    Returns dict(grade, points, reasons_for, reasons_against, context). Never a probability."""
    s = 1 if side == "BUY" else -1
    rg = regime(sig_df)
    st = structure(sig_df)
    vo = volume_state(sig_df)
    vw = session_vwap(intraday)
    hb = htf_bias(daily)
    pro, con, pts, hard = [], [], 0, []
    if not data_ok:
        hard.append("data quality check failed")
    if rg["primary"].startswith("unknown"):
        hard.append("not enough completed candles for market context")
    # 1 regime fit (one indicator family: EMA/ADX trend state – not counted twice)
    trend_dir = 1 if rg["primary"] == "Bullish trending" else -1 if rg["primary"] == "Bearish trending" else 0
    if rg["primary"] in FAMILY_REGIMES.get(family, ()) and (trend_dir in (0, s)):
        pts += 2; pro.append(f"regime fits a {family} ({rg['primary']}, ADX {rg['adx']})")
    elif trend_dir == -s:
        pts -= 2; con.append(f"against the {rg['primary'].lower()} regime")
    else:
        con.append(f"regime {rg['primary']} is not ideal for a {family}")
    # 2 higher timeframe
    if (hb == "bullish" and s > 0) or (hb == "bearish" and s < 0):
        pts += 2; pro.append(f"daily bias {hb}")
    elif hb in ("bullish", "bearish"):
        pts -= 2; con.append(f"daily bias {hb} (against)")
    # 3 structure
    if (st["event"] or "").endswith("up" if s > 0 else "down"):
        pts += 1; pro.append(f"structure: {st['event']}")
    if st["failed_breakout"] and st["failed_breakout"].startswith("up" if s > 0 else "down"):
        pts -= 2; con.append(f"failed breakout {st['failed_breakout']}")
    # 4 volume
    if vo["rel"] is not None:
        if vo["rel"] >= REL_VOL_HIGH:
            pts += 1; pro.append(f"volume {vo['label']}")
        elif vo["rel"] < 0.7 and family == "breakout":
            pts -= 1; con.append(f"breakout on {vo['label']}")
    # 5 OI (exchange data; footprint only)
    if oi_label:
        good = {"BUY": ("Long buildup", "Short covering"), "SELL": ("Short buildup", "Long unwinding")}[side]
        if oi_label in good:
            pts += 1; pro.append(f"OI {oi_label}")
        elif oi_label not in ("OI flat", "OI n/a"):
            pts -= 1; con.append(f"OI {oi_label} (does not confirm)")
    # 6 VWAP (intraday alignment, informative for positional calls)
    if vw["vwap"] is not None:
        if (s > 0 and vw["state"] in ("above VWAP", "reclaimed VWAP")) or (s < 0 and vw["state"] in ("below VWAP", "lost VWAP (rejection)")):
            pts += 1; pro.append(vw["state"])
        else:
            con.append(f"{vw['state']} (against)")
    # 7 trade plan: R:R, stop width, room to the next level
    if plan:
        rr = _f(plan.get("rr")) or (_f(plan.get("target_r")))
        ru, atr = _f(plan.get("risk_unit")), _f(plan.get("atr"))
        if rr is not None:
            if rr >= 2:
                pts += 1; pro.append(f"reward:risk {rr:.1f}")
            elif rr < 1.2:
                hard.append(f"reward:risk {rr:.1f} < 1.2")
        if ru and atr:
            k = ru / atr
            if k < 0.5:
                con.append(f"stop only {k:.1f} ATR away (noise risk)")
            elif k > 3.5:
                con.append(f"stop {k:.1f} ATR away (large risk)")
        lvl = st["resistance"] if s > 0 else st["support"]
        if lvl is not None and ru and plan.get("entry"):
            room = s * (lvl - float(plan["entry"])) / ru
            if 0 < room < 1:
                pts -= 1; con.append(f"{'resistance' if s > 0 else 'support'} {lvl:,.2f} only {room:.1f}R away")
    if "Stretched (RSI extreme in trend)" in rg["tags"] and family == "breakout":
        con.append("RSI extreme – late entry risk")
    if hard:
        g = "NO TRADE"
    elif pts >= 6:
        g = "A"
    elif pts >= 3:
        g = "B"
    elif pts >= 0:
        g = "C"
    else:
        g = "NO TRADE"
    return dict(grade=g, points=pts, reasons_for=pro, reasons_against=con + hard, hard=hard,
                context=dict(regime=rg, structure=st, volume=vo, vwap=vw, htf=hb, oi=oi_label or "OI n/a"))


def card(name, ex, side, tf_label, family, plan, g, signal_time, quote_time=None, expiry=None, data_quality="checked"):
    """POKHARNA RESEARCH alert text (used only when INTEL_IN_MESSAGE is on)."""
    c = g["context"]; rg = c["regime"]; st = c["structure"]
    t1 = plan.get("target"); t2 = plan.get("target2")
    rr = _f(plan.get("rr")) or _f(plan.get("target_r"))
    lines = ["POKHARNA RESEARCH — MARKET ALERT", "",
             f"Instrument: {name} FUT", f"Direction: {side}", f"Exchange: {'MCX' if ex == 'MCX' else 'NSE'}",
             f"Setup: {family}", f"Regime: {rg['primary']}" + (f" · {', '.join(rg['tags'])}" if rg["tags"] else ""),
             f"Timeframe: {tf_label}", f"Signal time: {signal_time}" + (f" · quote {quote_time}" if quote_time else ""), "",
             f"Entry: {plan.get('entry')}", f"Stop Loss: {plan.get('sl')}", f"Target 1: {t1}"]
    if t2:
        lines.append(f"Target 2: {t2}")
    lines += ["", f"Risk/Reward: {rr:.1f}" if rr else "Risk/Reward: n/a", f"Setup Grade: {g['grade']}", f"Data Quality: {data_quality}", "",
              "Market Context:", f"- Trend: {rg['primary']} (ADX {rg['adx']}, EMAs {rg['ema']}); daily bias {c['htf']}",
              f"- Structure: {st['trend']}" + (f", {st['event']}" if st["event"] else ""), f"- Volume: {c['volume']['label']}",
              f"- VWAP: {c['vwap']['state']}", f"- OI: {c['oi']}", "",
              "Why this trade?"] + [f"+ {x}" for x in g["reasons_for"]] + [f"− {x}" for x in g["reasons_against"]] + [
              f"Invalidation: close beyond {plan.get('sl')}", f"Expiry: {expiry or 'see timeframe rules'}", "Status: CONFIRMED", "",
              "Risk warning: This is a research alert, not a guaranteed outcome."]
    return "\n".join(lines)


def shadow_fields(side, family, sig_df, daily=None, intraday=None, plan=None, oi_label=None, tag=""):
    """One interface for every engine: grade a setup and return the ledger fields (empty dict on any error, so a call is
    never blocked or broken by grading). Prints one [intel] line for the run log."""
    try:
        g = grade(side, family, sig_df, daily=daily, intraday=intraday, plan=plan, oi_label=oi_label)
        print(f"[intel] {tag} {side} {family}: grade {g['grade']} ({g['points']} pts, {GRADE_VERSION}) · "
              f"{g['context']['regime']['primary']} · for: {'; '.join(g['reasons_for']) or '-'} · "
              f"against: {'; '.join(g['reasons_against']) or '-'}")
        return dict(grade=g["grade"], grade_v=GRADE_VERSION, grade_pts=g["points"], regime=g["context"]["regime"]["primary"],
                    family=family, why_for=g["reasons_for"][:5], why_against=g["reasons_against"][:5])
    except Exception as e:
        print(f"[intel] {tag} grade skipped: {type(e).__name__}: {e}")
        return {}
