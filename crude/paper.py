"""Paper book for the Crude Oil engine: costs, sizing, fills, exits, persisted state. No order API exists here.

Shared by the live scan (crude/engine.py) and the backtest (crude/backtest.py) so both use the same fill rules:
  * entries fill at a price that was actually available (live: the quote LTP; backtest: the NEXT candle's open)
    plus slippage ticks against us;
  * stop hit inside a candle -> stop price minus slippage; candle OPENS beyond the stop (gap) -> that open price;
  * stop and target inside the same candle -> the stop is assumed first (conservative);
  * a target fills only if price traded THROUGH it by at least one tick.
"""
import json, math, os, tempfile
from pathlib import Path
import pandas as pd
from crude import config as K

SCHEMA = 1


# ─────────────── costs & sizing ───────────────
def costs(side, entry, exit_, units, cost_x=1.0):
    """₹ round-trip charges (brokerage, CTT on sell, exchange, SEBI, stamp on buy, GST). Slippage is in the fills."""
    buy_v, sell_v = (entry * units, exit_ * units) if side == "BUY" else (exit_ * units, entry * units)
    brok = 2 * K.BROKERAGE_PER_ORDER
    exch = K.EXCH_TXN * (buy_v + sell_v)
    sebi = K.SEBI_FEE * (buy_v + sell_v)
    c = brok + K.CTT_SELL * sell_v + exch + sebi + K.STAMP_BUY * buy_v + K.GST * (brok + exch + sebi)
    return round(c * cost_x, 2)


def size(capital, stop_dist, price, mult, tick, risk_pct=K.RISK_PCT):
    """Whole lots so that (stop distance + exit slippage) × lots × ₹/pt + charges ≤ risk budget."""
    budget = capital * risk_pct
    per_lot = (stop_dist + K.SLIPPAGE_TICKS * tick) * mult + costs("BUY", price, price, mult)
    lots = int(math.floor(budget / per_lot)) if per_lot > 0 else 0
    return lots, round(budget, 2), round(per_lot, 2)


def slip(side, px, tick, opening=True, ticks=None):
    """Price after slippage. opening=True for entries (pay up), False for exits (receive less)."""
    s = (K.SLIPPAGE_TICKS if ticks is None else ticks) * tick
    up = (side == "BUY") == opening
    return round(px + s if up else px - s, 2)


# ─────────────── positions ───────────────
def open_position(engine, side, fill_px, plan, lots, mult, tick, contract, meta):
    sgn = 1 if side == "BUY" else -1
    d = plan["stop_dist"]
    return dict(id=meta["id"], engine=engine, side=side, contract=contract, entry=fill_px, entry_time=meta["time"],
                lots=lots, mult=mult, units=lots * mult, tick=tick, stop=round(fill_px - sgn * d, 2),
                initial_stop=round(fill_px - sgn * d, 2), target=round(fill_px + sgn * plan["target_r"] * d, 2),
                risk_pts=round(d, 2), atr=plan["atr"], best=fill_px, be_moved=False, last_bar=meta.get("last_bar"),
                bars_held=0, sessions=[str(pd.Timestamp(meta["time"]).date())], **{k: v for k, v in meta.items() if k not in ("id", "time", "last_bar")})


def step_bar(p, bar, stop_only=False, ticks=None):
    """Apply one COMPLETED candle of the traded contract to an open position. Returns (exit_price, reason) or None.
    Trailing/breakeven updates use the candle's close and take effect from the NEXT candle."""
    sgn = 1 if p["side"] == "BUY" else -1
    o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
    adverse_open = (o <= p["stop"]) if sgn > 0 else (o >= p["stop"])
    if adverse_open and not stop_only:
        return slip(p["side"], o, p["tick"], False, ticks), "gap through stop – filled at the open"
    hit_stop = (l <= p["stop"]) if sgn > 0 else (h >= p["stop"])
    if hit_stop:
        why = "breakeven stop" if p["be_moved"] and abs(p["stop"] - p["entry"]) < 1e-9 else "trailing stop" if p.get("trailed") else "stop-loss"
        return slip(p["side"], p["stop"], p["tick"], False, ticks), why
    if stop_only:                     # the candle we entered in: its earlier high/low happened before our fill
        return None
    hit_t = (h >= p["target"] + p["tick"]) if sgn > 0 else (l <= p["target"] - p["tick"])
    if hit_t:
        return p["target"], "target"
    p["bars_held"] += 1
    p["best"] = max(p["best"], c) if sgn > 0 else min(p["best"], c)
    gain = sgn * (p["best"] - p["entry"])
    if p["engine"] in ("intraday", "baseline-intraday"):
        if p.get("no_be"):
            return None
        if not p["be_moved"] and gain >= K.INTRA["breakeven_at_r"] * p["risk_pts"]:
            p["stop"], p["be_moved"] = p["entry"], True
    else:
        if gain >= K.POS["trail_after_r"] * p["risk_pts"]:
            new = p["best"] - sgn * K.POS["trail_atr"] * p["atr"]
            if sgn * (new - p["stop"]) > 0:
                p["stop"], p["trailed"] = round(new, 2), True
    return None


def close_position(p, exit_px, reason, when, cost_x=1.0):
    sgn = 1 if p["side"] == "BUY" else -1
    gross = sgn * (exit_px - p["entry"]) * p["units"]
    ch = costs(p["side"], p["entry"], exit_px, p["units"], cost_x)
    net = gross - ch
    r = net / (p["risk_pts"] * p["units"]) if p["units"] else 0.0
    return dict(p, exit=exit_px, exit_time=str(when), exit_reason=reason, gross=round(gross, 2), charges=ch,
                pnl=round(net, 2), r=round(r, 3))


def mtm(p, ltp):
    sgn = 1 if p["side"] == "BUY" else -1
    return round(sgn * (ltp - p["entry"]) * p["units"], 2)


# ─────────────── persisted state ───────────────
class StateError(RuntimeError):
    pass


def new_state(now):
    return dict(schema=SCHEMA, version=K.VERSION, mode=K.MODE, created=str(now), capital=K.CAPITAL, realized=0.0,
                engines={e: dict(open=[], closed=[], last_eval_bar=None, last_exit_bar=None) for e in ("intraday", "positional")},
                seen=[], oi_snaps=[], switches={}, day=None, runs=[], last_error=None)


def load(path, now, allow_new):
    path = Path(path)
    if not path.exists():
        if not allow_new:
            raise StateError(f"state file {path} missing and a new account was not allowed – refusing to reset silently")
        return new_state(now), True
    try:
        s = json.loads(path.read_text())
    except Exception as e:
        raise StateError(f"state file unreadable: {e}")
    if s.get("schema") != SCHEMA or s.get("mode") != "PAPER":
        raise StateError(f"state schema/mode mismatch: {s.get('schema')}/{s.get('mode')}")
    return s, False


def save(path, state):
    """Atomic write (temp file + rename). Raises StateError on any failure – the caller must not report success."""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".state")
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=1, default=str)
        os.replace(tmp, path)
        json.loads(path.read_text())                       # read back
    except Exception as e:
        raise StateError(f"state save failed: {e}")
