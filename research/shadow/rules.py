"""Immutable shadow-test strategy definitions (owner approval 11-Nov-2026). SHADOW ONLY: nothing here sends an alert,
places an order or is used by production.

A strategy id is bound to its parameters AND the source of its signal / risk functions (RULE_HASH). The shadow run
refuses to continue a ledger whose stored hash differs: any change needs a NEW id (e.g. -v2) and its own ledger.

SF-CONT-SELL-v1  CONTINUATION SELL – NSE stock futures, daily. Not a conventional RSI reversal: after an oversold fall
                 it SELLS the first bounce, i.e. it bets on the prior down-move continuing.
                 Exactly research/rsidiv/sf_check.py (rule(), pool_of(); trades results/sf_check_trades.csv.gz):
                 RSI(14, Wilder) <= 25 on any of the last 10 sessions (incl. today) AND today's close > the highest high
                 of the 5 previous sessions AND universe (stock has a future today; 60-session median cash turnover,
                 previous day, >= ₹25 cr; close >= ₹50). Indicators on the corporate-action-adjusted CASH series.
                 SELL at the next session's open; risk = 5-session high (incl. today) - close + 0.1 ATR(14), kept
                 between 0.5 and 3 ATR; stop = entry + risk; target = entry - 3 x risk; max 15 sessions (exit at the
                 15th session's close); stop checked before target in a bar; gap through the stop fills at the open;
                 one open trade per stock; a trade held over an expiry pays one extra round trip (roll).
CM-CONT-BUY-v1   CONTINUATION BUY – NSE cash, weekly. Momentum continuation, not a reversal.
                 Exactly research/rsidiv/cash_check.py (trades results/cash_check_trades.csv.gz):
                 weekly bars (week ending Friday or the last session of the week) from adjusted daily data;
                 weekly RSI(14) crosses to >= 75 this week (previous week < 75) AND the stock is eligible this week
                 (60-session median turnover >= ₹25 cr, close >= ₹50, >= 250 sessions of history) AND its 12-week median
                 weekly turnover (previous week) ranks in the bottom third of that week's eligible stocks.
                 BUY at the next week's first open; risk = close - 5-week low + 0.1 ATR(14 weeks), kept 0.5–3 ATR;
                 target 1R; max 10 weeks; stop before target in a bar; delivery costs 0.393 % round trip.
"""
import hashlib
import inspect
import json
import numpy as np
import pandas as pd

RULES = {
    "SF-CONT-SELL-v1": dict(label="CONTINUATION SELL", market="NSE_STOCK_FUT", tf="1d", side=-1, rsi_n=14, rsi_level=25, lookback=10,
                            brk=5, stop_window=5, stop_buf_atr=0.1, stop_min_atr=0.5, stop_max_atr=3.0, target_R=3.0, max_bars=15,
                            min_turnover=25e7, min_close=50.0, slip_per_side=0.0003, lot_value_note="1 lot (exchange lot size)",
                            research="research/rsidiv/sf_check.py", trades="research/rsidiv/results/sf_check_trades.csv.gz"),
    "CM-CONT-BUY-v1": dict(label="CONTINUATION BUY", market="NSE_CASH", tf="1w", side=1, rsi_n=14, rsi_level=75, liq_weeks=12,
                           liq_rank_max=1 / 3, stop_window=5, stop_buf_atr=0.1, stop_min_atr=0.5, stop_max_atr=3.0, target_R=1.0, max_bars=10,
                           min_turnover=25e7, min_close=50.0, min_hist=250, cost_round_trip=0.00393, slip_per_side=0.0005,
                           order_value=5e5, research="research/rsidiv/cash_check.py", trades="research/rsidiv/results/cash_check_trades.csv.gz"),
}


def wilder(x, n):
    return pd.Series(np.asarray(x, float)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().values


def rsi(c, n=14):
    c = pd.Series(np.asarray(c, float)); d = c.diff()
    g = pd.Series(wilder(d.clip(lower=0).values, n)); ls = pd.Series(wilder((-d).clip(lower=0).values, n))
    r = 100 - 100 / (1 + g / ls.replace(0, np.nan))
    return r.where(~((ls == 0) & (g > 0)), 100.0).values


def atr(h, l, c, n=14):
    h, l, c = (pd.Series(np.asarray(x, float)) for x in (h, l, c)); pc = c.shift(1)
    return wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, n)


def sf_signal(b, p=RULES["SF-CONT-SELL-v1"]):
    """b: one stock, adjusted cash daily rows (time open high low close, live bool) -> (signal bool, risk, rsi, atr)."""
    h, l, c = (b[x].astype(float).reset_index(drop=True) for x in ("high", "low", "close"))
    r = pd.Series(rsi(c, p["rsi_n"]))
    was = (r <= p["rsi_level"]).rolling(p["lookback"]).max() > 0
    sig = (was & (c > h.shift(1).rolling(p["brk"]).max())).fillna(False).values & np.asarray(b["live"], bool)
    a = pd.Series(atr(h, l, c))
    risk = (h.rolling(p["stop_window"]).max() - c + p["stop_buf_atr"] * a).clip(lower=p["stop_min_atr"] * a, upper=p["stop_max_atr"] * a).values
    return sig, risk, r.values, a.values


def cm_signal(b, p=RULES["CM-CONT-BUY-v1"]):
    """b: one stock, weekly rows (time open high low close, elig bool, liq_rank) -> (signal, risk, rsi, atr)."""
    b = b.copy()
    for col in ("open", "high", "low"):
        b[col] = b[col].where(b[col] > 0).fillna(b["close"])
    h, l, c = (b[x].astype(float).reset_index(drop=True) for x in ("high", "low", "close"))
    a = pd.Series(atr(h, l, c))
    risk = (c - l.rolling(p["stop_window"]).min() + p["stop_buf_atr"] * a).clip(lower=p["stop_min_atr"] * a, upper=p["stop_max_atr"] * a).values
    r = pd.Series(rsi(c, p["rsi_n"]))
    x = ((r >= p["rsi_level"]) & (r.shift(1) < p["rsi_level"])).fillna(False).values
    sig = x & np.asarray(b["elig"], bool) & (np.asarray(b["liq_rank"], float) <= p["liq_rank_max"])
    return sig, risk, r.values, a.values


def walk(o, h, l, c, e, side, risk, R, hold, cut=None):
    """one trade from entry bar e (fill at o[e]); same exit rules as research/rsidiv/engine.sim. cut = last bar index
    allowed (instrument / data end). MFE / MAE in R from the entry fill; on the exit bar a stop caps MFE at the target
    distance (stop counts first) and a target leaves MAE below 1R (the stop was not touched)."""
    n = len(c) if cut is None else cut + 1
    px = o[e]; st = px - side * risk; tp = px + side * R * risk
    mfe = mae = 0.0
    for j in range(e, n):
        fav = ((h[j] - px) if side > 0 else (px - l[j])) / risk
        adv = ((px - l[j]) if side > 0 else (h[j] - px)) / risk
        why = None
        if j > e and ((side > 0 and o[j] <= st) or (side < 0 and o[j] >= st)):
            x, why = o[j], "stop (gap)"
        elif j > e and ((side > 0 and o[j] >= tp) or (side < 0 and o[j] <= tp)):
            x, why = o[j], "target (gap)"
        elif (side > 0 and l[j] <= st) or (side < 0 and h[j] >= st):
            x, why = st, "stop"
        elif (side > 0 and h[j] >= tp) or (side < 0 and l[j] <= tp):
            x, why = tp, "target"
        elif j - e + 1 >= hold:
            x, why = c[j], "time"
        if why is None:
            mfe, mae = max(mfe, fav), max(mae, adv); continue
        g = side * (x - px) / risk
        if why.startswith("stop"):
            mae = max(mae, -g); mfe = max(mfe, min(fav, R))
        elif why.startswith("target"):
            mfe = max(mfe, g); mae = max(mae, adv)
        else:
            mfe, mae = max(mfe, fav), max(mae, adv)
        return dict(exit_i=j, exit_px=float(x), reason=why, gross_R=float(g), mfe_R=float(mfe), mae_R=float(mae), bars=j - e + 1, done=True)
    j = n - 1
    return dict(exit_i=j, exit_px=float(c[j]), reason="open", gross_R=float(side * (c[j] - px) / risk), mfe_R=float(mfe), mae_R=float(mae),
                bars=n - e, done=False)


def rule_hash(sid):
    src = inspect.getsource(sf_signal if sid.startswith("SF") else cm_signal) + inspect.getsource(walk) + inspect.getsource(rsi) + inspect.getsource(atr)
    return hashlib.sha256((json.dumps(RULES[sid], sort_keys=True) + src).encode()).hexdigest()[:16]
