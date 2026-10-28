"""One validated trade plan for every futures / stock-futures / option-buy call (28-Oct-2026 audit).

The plan is built ONCE and used for the Telegram message, the open-call tracker and the report ledger, so the
displayed and the tracked prices are always identical. Nothing here changes a strategy's own rule (ATR multiple,
target in R) – it only checks that the numbers are valid and tradable.

Checks (a failed check = no call, with the reason logged):
  * signal close, ATR, live price must be finite and > 0 (no silent defaults for missing data)
  * live entries during market hours need a valid exchange timestamp on the quote: missing / malformed -> rejected,
    older than MAX_QUOTE_AGE_MIN -> rejected, more than MAX_CLOCK_SKEW_SEC in the future -> rejected.
    Outside market hours (require_live=False) a timestamp is optional, but if present it must parse and pass the same checks.
    All times are compared as naive Asia/Kolkata (exchange time); tz-aware values are converted first.
  * slippage both ways: live price must be within MAX_CHASE_ATR beyond the signal close (in the trade direction) and
    within MAX_AGAINST_ATR on the other side (a BUY whose price already fell back is not a BUY any more)
  * levels rounded to the instrument's tick, then risk / reward recomputed
  * BUY: SL < entry < target · SELL: SL > entry > target
  * stop distance ≤ max % of price (per timeframe) – the stop is never widened to fit a poor entry
  * reward / risk ≥ the strategy's minimum after rounding
"""
import math
import os
import datetime as dt
import pandas as pd

MAX_QUOTE_AGE_MIN = 5
MAX_CLOCK_SKEW_SEC = float(os.getenv("QUOTE_CLOCK_SKEW_SEC", "60"))   # quote may be at most this far "ahead" of our clock
EXCH_TZ = "Asia/Kolkata"
_FMTS = ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S")
MAX_CHASE_ATR = 0.5
MAX_AGAINST_ATR = 0.5


def finite(*xs):
    return all(x is not None and isinstance(x, (int, float)) and math.isfinite(x) for x in xs)


def tick_round(x, tick, mode="nearest"):
    """Round a price to the exchange tick. mode: nearest / down / up."""
    if not tick or tick <= 0:
        tick = 0.05
    q = x / tick
    n = math.floor(q + 1e-9) if mode == "down" else math.ceil(q - 1e-9) if mode == "up" else math.floor(q + 0.5)
    return round(n * tick, 6)


def decimals(tick):
    t = f"{tick:.6f}".rstrip("0").rstrip(".")
    return len(t.split(".")[1]) if "." in t else 0


def fmt(x, tick=0.05):
    """Display a price exactly as tracked (tick precision, thousands separator)."""
    return f"{x:,.{decimals(tick)}f}"


def to_ist(t):
    """Timestamp -> naive Asia/Kolkata. tz-aware values are converted; naive values are taken as exchange (IST) time."""
    t = pd.Timestamp(t)
    if t.tzinfo is not None:
        t = t.tz_convert(EXCH_TZ).tz_localize(None)
    return t


def parse_exch_time(v):
    """Strict parse of an Angel exchange time ('28-Oct-2026 12:16:30' and a few ISO forms). None if missing / malformed."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return to_ist(v)
    v = str(v).strip()
    if not v:
        return None
    for f in _FMTS:
        try:
            return to_ist(dt.datetime.strptime(v, f))
        except ValueError:
            pass
    try:                                                   # ISO with offset, e.g. 2026-10-28T06:46:30+00:00
        t = pd.Timestamp(v)
        if t.tzinfo is not None:
            return to_ist(t)
    except (ValueError, TypeError):
        pass
    return None


def quote_time(q):
    """Exchange time of an Angel quote, or None when the quote has no (parseable) timestamp."""
    return quote_check(q, None, require=False)[0]


def quote_check(q, now, require=True):
    """-> (time or None, reason or None). reason set = the quote must not be used for an entry."""
    q = q or {}
    raw = next((q.get(k) for k in ("exchFeedTime", "exchTradeTime") if q.get(k) not in (None, "")), None)
    if raw is None:
        return None, ("live quote has no exchange timestamp" if require else None)
    t = parse_exch_time(raw)
    if t is None:
        return None, f"live quote timestamp malformed ({str(raw)[:30]!r})"
    if now is None:
        return t, None
    age = (to_ist(now) - t).total_seconds()
    if age < -MAX_CLOCK_SKEW_SEC:
        return t, f"live quote timestamp {-age:.0f}s in the future (max skew {MAX_CLOCK_SKEW_SEC:.0f}s)"
    if age / 60 > MAX_QUOTE_AGE_MIN:
        return t, f"live quote stale ({age / 60:.0f} min old)"
    return t, None


def futures_plan(*, name, ex, contract, tf, side, signal_time, signal_close, atr, stop_mult, target_r, tick, lot, mult,
                 max_sl_pct, live=None, quote=None, now=None, require_live=True, min_rr=1.0, levels=None):
    """-> dict(valid=bool, reason=str, ...levels...). target_r None = no fixed target (trailing / trend exit)."""
    s = 1 if side == "BUY" else -1
    p = dict(name=name, ex=ex, contract=contract, tf=tf, side=side, signal_time=str(signal_time), signal_close=signal_close,
             atr=atr, stop_mult=stop_mult, target_r=target_r, tick=tick or 0.05, lot=lot, mult=mult, valid=False, reason="")
    tick = p["tick"]
    if side not in ("BUY", "SELL"):
        p["reason"] = "no direction"; return p
    if not finite(signal_close, atr) or signal_close <= 0:
        p["reason"] = "signal price missing / not a number"; return p
    if atr <= 0:
        p["reason"] = "ATR zero or negative"; return p
    if live is None:
        if require_live:
            p["reason"] = "no live price"; return p
        live = signal_close
    if not finite(live) or live <= 0:
        p["reason"] = "live price invalid"; return p
    if require_live and now is None:
        p["reason"] = "no clock time to check the live quote against"; return p
    qt, why = quote_check(quote, now, require=require_live)
    p["quote_time"] = str(qt) if qt is not None else None
    if why:
        p["reason"] = why; return p
    move = s * (live - signal_close) / atr
    if move > MAX_CHASE_ATR:
        p["reason"] = f"price already ran {move:.2f} ATR past the signal (max {MAX_CHASE_ATR}) – no chasing"; return p
    if move < -MAX_AGAINST_ATR:
        p["reason"] = f"price moved {-move:.2f} ATR against the signal – setup no longer valid"; return p
    entry = tick_round(live, tick)
    R = stop_mult * atr
    sl = tick_round(entry - s * R, tick, "down" if s > 0 else "up")        # never closer than the rule
    tgt = tick_round(entry + s * target_r * R, tick, "down" if s > 0 else "up") if target_r else None   # never further
    risk = s * (entry - sl)
    p.update(entry=entry, sl=sl, target=tgt, risk_unit=round(risk, 6), risk_lot=round(risk * (mult or 1), 2))
    if risk <= 0:
        p["reason"] = "stop-loss on the wrong side of entry"; return p
    if tgt is not None and s * (tgt - entry) <= 0:
        p["reason"] = "target on the wrong side of entry"; return p
    sl_pct = risk / entry * 100
    p["sl_pct"] = round(sl_pct, 2)
    if max_sl_pct and sl_pct > max_sl_pct:
        p["reason"] = f"stop-loss {sl_pct:.1f}% away (max {max_sl_pct}%) – not tradable for one lot"; return p
    if tgt is not None:
        rr = s * (tgt - entry) / risk
        p["rr"] = round(rr, 2)
        if rr < min_rr - 1e-9:
            p["reason"] = f"reward/risk {rr:.2f} below {min_rr}"; return p
    # support / resistance: a strong level in the first half of the way to the target is shown as a warning in WHY
    # (not a reason to reject – no research shows that it improves results)
    if tgt is not None and levels:
        opp = levels.get("resistance" if s > 0 else "support") or []
        near = [v for v, _ in opp if 0 < s * (v - entry) < 0.5 * s * (tgt - entry)]
        if near:
            v = min(near, key=lambda x: abs(x - entry))
            p["warn"] = f"{'resistance' if s > 0 else 'support'} {fmt(v, tick)} lies before the target – price may pause there"
    p["valid"] = True
    return p


def option_plan(*, premium, sl_pct, tg_pct, tick=0.05, lot=1):
    """Option-BUY levels on the PREMIUM (kept separate from the futures stop)."""
    p = dict(valid=False, reason="", tick=tick or 0.05, lot=lot)
    if not finite(premium) or premium <= 0:
        p["reason"] = "option premium missing"; return p
    t = p["tick"]
    entry = tick_round(premium, t)
    sl = tick_round(entry * (1 - sl_pct), t, "down")
    tg = tick_round(entry * (1 + tg_pct), t, "down")
    if not (0 < sl < entry < tg):
        p["reason"] = "option levels invalid after rounding"; return p
    p.update(valid=True, entry=entry, sl=sl, target=tg, sl_pct=sl_pct, tg_pct=tg_pct)
    return p
