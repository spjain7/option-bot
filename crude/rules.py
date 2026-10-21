"""Crude Oil entry rules. Pure functions on COMPLETED candles (callers drop the forming candle).

Every evaluation returns a decision dict:
  decision: "SIGNAL" | "BLOCKED" | "NONE"
  side, setup, reasons (why it qualifies), blocks (why it was stopped), metrics, plan (stop distance, target R ...)
RSI rule (both engines): RSI > 75 blocks SELL entries, RSI < 25 blocks BUY entries. These are entry restrictions
only – an extreme RSI never creates a trade in the opposite direction.
"""
import numpy as np
import pandas as pd
from crude import config as K
from crude import indicators as I


def _pos(bar):
    rng = bar.high - bar.low
    return 0.5 if rng <= 0 else (bar.close - bar.low) / rng


def _body(bar):
    rng = bar.high - bar.low
    return 0.0 if rng <= 0 else abs(bar.close - bar.open) / rng


def trend(df, P):
    """EMA20/50 (+EMA200 when ≥ ema_long_min_bars bars) and ADX on completed candles of one timeframe."""
    if df is None or len(df) < P["ema_slow"] + P["adx_len"]:
        return dict(dir="UNKNOWN", why=f"only {0 if df is None else len(df)} candles (need {P['ema_slow'] + P['adx_len']})")
    c = df["close"]
    e20, e50 = I.ema(c, P["ema_fast"]).iloc[-1], I.ema(c, P["ema_slow"]).iloc[-1]
    e200 = I.ema(c, P["ema_long"]).iloc[-1] if len(df) >= P["ema_long_min_bars"] else None
    a = I.adx(df, P["adx_len"]).iloc[-1]
    x = c.iloc[-1]
    up = x > e20 > e50 and (e200 is None or x > e200)
    dn = x < e20 < e50 and (e200 is None or x < e200)
    d = "UP" if up else "DOWN" if dn else "MIXED"
    if d != "MIXED" and not (a >= P["adx_min"]):
        d = "RANGE"
    return dict(dir=d, close=float(x), ema20=float(e20), ema50=float(e50), ema200=None if e200 is None else float(e200),
                adx=None if pd.isna(a) else float(a), bars=len(df),
                why=f"close {x:.0f} EMA20 {e20:.0f} EMA50 {e50:.0f} EMA200 {'n/a (history ' + str(len(df)) + ' bars)' if e200 is None else f'{e200:.0f}'} ADX {a:.1f}")


def _rsi_block(side, r, P):
    if side == "BUY" and r < P["rsi_block_buy_below"]:
        return f"RSI {r:.1f} < {P['rsi_block_buy_below']:.0f} blocks BUY"
    if side == "SELL" and r > P["rsi_block_sell_above"]:
        return f"RSI {r:.1f} > {P['rsi_block_sell_above']:.0f} blocks SELL"
    return None


def _volume(df, P, x_min):
    if "volume" not in df or df["volume"].isna().all() or (df["volume"].fillna(0) <= 0).all():
        return None, "volume unavailable"
    ratio, n = I.slot_volume_ratio(df, P["vol_slots"], P["vol_slots_min"])
    r = ratio.iloc[-1]
    if pd.isna(r):
        return None, f"volume comparison unavailable (only {int(n.iloc[-1])} earlier same-time candles, need {P['vol_slots_min']})"
    return float(r), None if r >= x_min else f"volume {r:.2f}× same-time average < {x_min}×"


def _setup(df, side, P, a, e20, e50):
    """Breakout or pullback-resumption on the last completed candle. Returns (setup, level, fail_reason)."""
    x, prev = df.iloc[-1], df.iloc[-2]
    sgn = 1 if side == "BUY" else -1
    n = P["breakout_bars"]
    win = df.iloc[-n - 1:-1]
    level = win["high"].max() if side == "BUY" else win["low"].min()
    beyond = sgn * (x.close - level)
    cp = _pos(x) if side == "BUY" else 1 - _pos(x)
    if beyond > 0:
        fresh = not any(sgn * (c - level) > 0 for c in df["close"].iloc[-3:-1])
        if beyond < P["breakout_buffer_atr"] * a:
            return None, level, f"weak breakout: close only {beyond:.1f} pts beyond {level:.0f} (< {P['breakout_buffer_atr']} ATR)"
        if cp < P["close_pos_min"]:
            return None, level, f"weak breakout candle: closed at {cp:.0%} of its range (need ≥ {P['close_pos_min']:.0%})"
        if "body_min" in P and _body(x) < P["body_min"]:
            return None, level, f"weak breakout candle: body {_body(x):.0%} of range"
        if not fresh:
            return None, level, "not a fresh breakout (an earlier candle already closed beyond the level)"
        return "breakout", level, None
    lb = df.iloc[-P["pullback_lookback"] - 1:-1]
    touched = (lb["low"].min() <= e20 + P["pullback_touch_atr"] * a) if side == "BUY" else (lb["high"].max() >= e20 - P["pullback_touch_atr"] * a)
    held = (lb["low"].min() > e50 - 0.5 * a) if side == "BUY" else (lb["high"].max() < e50 + 0.5 * a)
    resumed = (x.close > prev.high and x.close > x.open and x.close > e20) if side == "BUY" else \
              (x.close < prev.low and x.close < x.open and x.close < e20)
    if touched and held and resumed and cp >= 0.6:
        return "pullback", float(prev.high if side == "BUY" else prev.low), None
    return None, level, "no setup: no confirmed breakout and no pullback-and-resume candle"


def _plan(df, side, P, a, entry, swing_bars=None, swing_level=None):
    sgn = 1 if side == "BUY" else -1
    if swing_level is None:
        w = df.iloc[-swing_bars:]
        swing_level = w["low"].min() if side == "BUY" else w["high"].max()
    stop = swing_level - sgn * P["sl_buffer_atr"] * a
    dist = sgn * (entry - stop)
    note = "swing"
    if dist < P["sl_min_atr"] * a:
        dist, note = P["sl_min_atr"] * a, f"widened to {P['sl_min_atr']} ATR"
    if dist > P["sl_max_atr"] * a:
        return None, f"stop too wide: {dist:.0f} pts = {dist / a:.1f} ATR > {P['sl_max_atr']} ATR"
    return dict(stop_dist=float(dist), stop_note=note, target_r=P["target_r"], atr=float(a)), None


def _room(levels_df, side, entry, dist):
    """Reward-to-risk to the nearest obstacle (highest high / lowest low of the lookback) – None if price is beyond it."""
    if side == "BUY":
        ob = levels_df["high"].max()
        room = ob - entry
    else:
        ob = levels_df["low"].min()
        room = entry - ob
    if room <= 0:
        return None, None
    return float(ob), float(room / dist)


def _common(df, P, side, x_min, volume_policy):
    blocks = []
    r = I.rsi(df["close"], P["rsi_len"]).iloc[-1]
    b = _rsi_block(side, r, P)
    if b:
        blocks.append(b)
    vx, vb = _volume(df, P, x_min)
    if vb and ("unavailable" not in vb or volume_policy == "block"):
        blocks.append(vb)
    at = I.atr(df, P["atr_len"])
    a = at.iloc[-1]
    base = at.iloc[-P["atr_regime_len"]:].median()
    x = df.iloc[-1]
    if a / base > P["atr_regime_max"]:
        blocks.append(f"abnormal volatility: ATR {a:.1f} = {a / base:.1f}× its median")
    if (x.high - x.low) > P["max_bar_atr"] * a:
        blocks.append(f"abnormal candle: range {x.high - x.low:.0f} > {P['max_bar_atr']} ATR")
    return dict(rsi=float(r), vol_x=vx, atr=float(a), atr_x=float(a / base)), blocks


def intraday(c15, c1h, P=K.INTRA, volume_policy=K.VOLUME_POLICY):
    """15-minute entry with 1-hour trend confirmation. c1h must contain only 1-hour candles that had closed by the
    end of the last 15-minute candle (the caller guarantees it; the backtest slices the same way)."""
    need = max(P["ema_slow"], P["atr_len"]) + 10
    if c15 is None or len(c15) < need:
        return dict(decision="NONE", blocks=[f"insufficient 15-min history ({0 if c15 is None else len(c15)} < {need})"], metrics={})
    t = trend(c1h, P)
    m = dict(trend_1h=t["dir"], trend_1h_detail=t["why"], adx_1h=t.get("adx"))
    if t["dir"] not in ("UP", "DOWN"):
        r15 = I.rsi(c15["close"], P["rsi_len"]).iloc[-1]
        m["rsi"] = float(r15)
        return dict(decision="NONE", blocks=[f"1-hour trend {t['dir']}: {t['why']}"], metrics=m)
    side = "BUY" if t["dir"] == "UP" else "SELL"
    c = c15["close"]
    e20, e50 = I.ema(c, P["ema_fast"]).iloc[-1], I.ema(c, P["ema_slow"]).iloc[-1]
    a = I.atr(c15, P["atr_len"]).iloc[-1]
    x = c15.iloc[-1]
    met, blocks = _common(c15, P, side, P["vol_min_x_breakout"], volume_policy)
    m.update(met)
    sgn = 1 if side == "BUY" else -1
    if sgn * (x.close - e50) < 0:
        return dict(decision="NONE", side=side, blocks=[f"15-min close {x.close:.0f} on the wrong side of 15-min EMA50 {e50:.0f} (conflicts with 1-hour {t['dir']})"], metrics=m)
    setup, level, fail = _setup(c15, side, P, a, e20, e50)
    if setup is None:
        return dict(decision="NONE", side=side, blocks=[fail], metrics=m)
    if setup == "pullback":                         # pullbacks need ordinary volume, not breakout volume
        blocks = [b for b in blocks if not b.startswith("volume ")] + \
                 ([f"volume {met['vol_x']:.2f}× same-time average < {P['vol_min_x_pullback']}×"]
                  if met["vol_x"] is not None and met["vol_x"] < P["vol_min_x_pullback"] else [])
    plan, pb = _plan(c15, side, P, a, float(x.close), swing_bars=P["sl_swing_bars"])
    if pb:
        blocks.append(pb)
    else:
        ob, rr = _room(c1h.iloc[-P["obstacle_bars_1h"]:], side, float(x.close), plan["stop_dist"])
        plan.update(obstacle=ob, rr_to_obstacle=rr)
        if rr is not None and rr < K.MIN_RR:
            blocks.append(f"reward:risk {rr:.2f} to the 1-hour {'high' if side == 'BUY' else 'low'} {ob:.0f} < {K.MIN_RR}")
    reasons = [f"1-hour trend {t['dir']} ({t['why']})", f"15-min {setup} {'above' if side == 'BUY' else 'below'} {level:.0f}",
               f"RSI {met['rsi']:.1f}", "volume n/a" if met["vol_x"] is None else f"volume {met['vol_x']:.2f}× same-time avg"]
    return dict(decision="BLOCKED" if blocks else "SIGNAL", side=side, setup=setup, level=float(level),
                signal_close=float(x.close), bar_time=str(x.time), reasons=reasons, blocks=blocks, metrics=m, plan=plan)


def structure(df, side, k):
    """Swing structure from confirmed pivots: HH+HL for BUY, LH+LL for SELL. Returns (ok, last swing level, text)."""
    hi, lo = I.pivots(df, k)
    if len(hi) < 2 or len(lo) < 2:
        return False, None, "not enough confirmed swings"
    (_, h1), (_, h2) = hi[-2], hi[-1]
    (_, l1), (_, l2) = lo[-2], lo[-1]
    if side == "BUY":
        return (h2 > h1 and l2 > l1), float(l2), f"swings H {h1:.0f}→{h2:.0f}, L {l1:.0f}→{l2:.0f}"
    return (h2 < h1 and l2 < l1), float(h2), f"swings H {h1:.0f}→{h2:.0f}, L {l1:.0f}→{l2:.0f}"


def positional(c3, P=K.POS, volume_policy=K.VOLUME_POLICY):
    """Signal on the last COMPLETED 3-hour candle."""
    need = P["ema_slow"] + P["adx_len"] + 5
    if c3 is None or len(c3) < need:
        return dict(decision="NONE", blocks=[f"insufficient 3-hour history ({0 if c3 is None else len(c3)} < {need})"], metrics={})
    t = trend(c3, P)
    m = dict(trend_3h=t["dir"], trend_3h_detail=t["why"], adx_3h=t.get("adx"))
    m["rsi"] = float(I.rsi(c3["close"], P["rsi_len"]).iloc[-1])
    if t["dir"] not in ("UP", "DOWN"):
        return dict(decision="NONE", blocks=[f"3-hour trend {t['dir']}: {t['why']}"], metrics=m)
    side = "BUY" if t["dir"] == "UP" else "SELL"
    x = c3.iloc[-1]
    if "complete" in c3 and not bool(x.complete):
        return dict(decision="NONE", side=side, blocks=["last 3-hour candle is missing hourly bars (data gap) – not used"], metrics=m)
    a = I.atr(c3, P["atr_len"]).iloc[-1]
    e20, e50 = I.ema(c3["close"], P["ema_fast"]).iloc[-1], I.ema(c3["close"], P["ema_slow"]).iloc[-1]
    met, blocks = _common(c3, P, side, P["vol_min_x"], volume_policy)
    m.update(met)
    ok, swing, stext = structure(c3, side, P["pivot"])
    m["structure"] = stext
    if not ok:
        return dict(decision="NONE", side=side, blocks=[f"swing structure not {'HH/HL' if side == 'BUY' else 'LH/LL'}: {stext}"], metrics=m)
    setup, level, fail = _setup(c3, side, P, a, e20, e50)
    if setup is None:
        return dict(decision="NONE", side=side, blocks=[fail], metrics=m)
    plan, pb = _plan(c3, side, P, a, float(x.close), swing_level=swing)
    if pb:
        blocks.append(pb)
    else:
        ob, rr = _room(c3.iloc[-P["obstacle_bars"]:-1], side, float(x.close), plan["stop_dist"])
        plan.update(obstacle=ob, rr_to_obstacle=rr)
        if rr is not None and rr < K.MIN_RR:
            blocks.append(f"reward:risk {rr:.2f} to the 3-hour {'high' if side == 'BUY' else 'low'} {ob:.0f} < {K.MIN_RR}")
    reasons = [f"3-hour trend {t['dir']} ({t['why']})", f"{stext}", f"3-hour {setup} {'above' if side == 'BUY' else 'below'} {level:.0f}",
               f"RSI {met['rsi']:.1f}", "volume n/a" if met["vol_x"] is None else f"volume {met['vol_x']:.2f}× same-block avg"]
    return dict(decision="BLOCKED" if blocks else "SIGNAL", side=side, setup=setup, level=float(level),
                signal_close=float(x.close), bar_time=str(x.time), reasons=reasons, blocks=blocks, metrics=m, plan=plan)


def oi_gate(side, oi):
    """Apply the OI filter. Returns (block_reason or None, tag). Missing OI is never treated as zero."""
    if oi is None or oi.get("status") != "OK":
        why = (oi or {}).get("reason", "OI unavailable")
        if K.OI_POLICY == "require":
            return f"OI filter required but unavailable: {why}", "UNAVAILABLE"
        return None, f"UNAVAILABLE ({why}) – evaluated without OI filter"
    if oi["label"] in K.OI_BLOCKS[side]:
        return f"OI shows {oi['label']} ({oi['d_oi_pct']:+.2f}% OI, {oi['d_price']:+.0f} pts in {oi['gap_min']:.0f} min) against a {side}", oi["label"]
    return None, f"{oi['label']} ({oi['d_oi_pct']:+.2f}% OI in {oi['gap_min']:.0f} min)"
