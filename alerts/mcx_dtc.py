"""MCX GOLD / SILVER intraday DAY-TREND CONTINUATION – SHADOW MODE (logged and tracked, never sent). Research MCXD-001/002
(exp/strategy-program-001, research/program/mcx_disc.py + mcx_dtc.py), 6-Nov-2026.

Rule: at the 13:00 and 17:00 checkpoints (the 15-minute candle that closes then), if
  * the 60-minute trend agrees (EMA20 > EMA50 and close > EMA50 on completed hourly candles; mirror for SELL),
  * price is beyond today's session VWAP, and
  * price is beyond today's 09:00 open by >= 0.3 x daily ATR(14, previous sessions),
then follow the move: entry at the current price, stop 0.5 x daily ATR, hold to the 23:00 square-off. BUY and SELL.
Evidence (5-min front-month data 2023-26, realistic MCX costs, 2 x stress): 542 trades, +0.18R per trade (+0.15R at 2 x
costs), DEV 2025-11…06 +0.13R, VALID 2026-07…11 +0.26R, older 2023-25 +0.19R, every year positive; 54 / 54 neighbouring
parameter sets positive in the older history. Does NOT transfer to CRUDEOIL / COPPER (≈ 0).
STATUS: SHADOW – the owner's rule: experimental strategies are never sent to Telegram before live shadow evidence.
Live differences vs research: VWAP from 15-minute candles (research: 5-minute), entry at the scan's live price.
"""
import numpy as np
import pandas as pd
from crude import indicators as I

NAMES = ("GOLD", "SILVER")
CHECKPOINTS = (13 * 60, 17 * 60)
K_OPEN, M_STOP = 0.3, 0.5
SQUARE_OFF = 23 * 60
LIVE = True                        # 10-Nov-2026 (owner: "we need all calls live first") – sent, labelled EXPERIMENTAL
WARN = "Alert only – no auto trade. Not investment advice."
MAX_PER_COMMODITY, MAX_TOTAL = 2, 4  # MCXD-004: the 17:00 add-on helps (blocking it cut +0.18R to +0.10R) -> cap, don't block
VERSION = "mcx-dtc-0.1 (MCXD-002, shadow)"


def daily_atr(dd):
    """dd: completed daily candles BEFORE today (time, open, high, low, close)."""
    if dd is None or len(dd) < 15:
        return None
    h, l, c = dd["high"].values, dd["low"].values, dd["close"].values
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    return float(np.mean(tr[-14:]))


def trend60(h1, upto):
    """+1 / -1 / 0 from completed hourly candles that ended at or before `upto`."""
    if h1 is None or len(h1) < 60:
        return 0
    x = h1[pd.to_datetime(h1["time"]) + pd.Timedelta(minutes=60) <= upto]
    if len(x) < 60:
        return 0
    c = x["close"].astype(float)
    e20, e50 = c.ewm(span=20, adjust=False).mean().iat[-1], c.ewm(span=50, adjust=False).mean().iat[-1]
    if e20 > e50 and c.iat[-1] > e50:
        return 1
    if e20 < e50 and c.iat[-1] < e50:
        return -1
    return 0


def evaluate(c15, h1, dd, now):
    """-> dict(side, checkpoint, close, vwap, day_open, atr_d, stop_dist, why) or dict(side=None, why=...)."""
    if c15 is None or not len(c15):
        return dict(side=None, why="no 15m candles")
    t = pd.to_datetime(c15["time"])
    day = pd.Timestamp(now).normalize()
    today = c15[t.dt.normalize() == day]
    if today.empty:
        return dict(side=None, why="no candles today")
    last_t = pd.Timestamp(today["time"].iloc[-1])
    end_m = last_t.hour * 60 + last_t.minute + 15
    if end_m not in CHECKPOINTS and len(today) >= 2 and end_m - 15 in CHECKPOINTS:
        # 10-Nov FIX: on 9-Nov the 12:45 candle was not yet in the data at the 13:02 scan ("not a checkpoint candle") and
        # the 13:17 scan was one candle past it -> the 13:00 checkpoint was never evaluated. One candle late is accepted:
        # evaluated on the candles up to the checkpoint only; the record shows the entry delay (run() dedups by key).
        today = today.iloc[:-1]
        last_t = pd.Timestamp(today["time"].iloc[-1])
        end_m -= 15
    if end_m not in CHECKPOINTS:
        return dict(side=None, why="not a checkpoint candle")
    tp = (today["high"] + today["low"] + today["close"]) / 3
    v = today["volume"].astype(float)
    vwap = float((tp * v).sum() / v.sum()) if v.sum() > 0 else np.nan
    day_open = float(today["open"].iloc[0])
    close = float(today["close"].iloc[-1])
    a = daily_atr(dd)
    if not a or not vwap == vwap:
        return dict(side=None, why="ATR / VWAP unavailable")
    tr = trend60(h1, last_t + pd.Timedelta(minutes=15))
    for s in (1, -1):
        if tr == s and s * (close - vwap) > 0 and s * (close - day_open) >= K_OPEN * a:
            return dict(side="BUY" if s > 0 else "SELL", checkpoint=f"{end_m // 60}:{end_m % 60:02d}", close=close, vwap=vwap,
                        day_open=day_open, atr_d=a, stop_dist=M_STOP * a, trend=tr,
                        why=f"60m trend {'up' if s > 0 else 'down'}, price {'above' if s > 0 else 'below'} VWAP {vwap:.1f} and "
                            f"{abs(close - day_open) / a:.2f} x daily ATR from the open")
    return dict(side=None, why=f"conditions not met (trend {tr}, close {close:.1f}, VWAP {vwap:.1f}, open {day_open:.1f})")


def store(state):
    return state.setdefault("mcxdtc", dict(open=[], closed=[], seen=[]))


def run(state, msgs, name, c, c15, h1, dd, q, now):
    """Shadow: record a signal at a checkpoint, never send. Returns the evaluation dict."""
    from alerts import funnel as FN
    st = store(state)
    sig = evaluate(c15, h1, dd, now)
    if not sig.get("side"):
        return sig
    key = f"{name}|{pd.Timestamp(now).date()}|{sig['checkpoint']}"
    if key in st["seen"]:
        return dict(sig, note="already recorded")
    st["seen"] = (st["seen"] + [key])[-400:]
    FN.note(state, "MCX_DTC (shadow)", "signal", key=key, now=now)
    ltp = float((q or {}).get("ltp") or 0)
    if not ltp:
        FN.note(state, "MCX_DTC (shadow)", "rejected", "no live price", key=key, now=now)
        return dict(sig, note="no live price")
    s = 1 if sig["side"] == "BUY" else -1
    same = [r for r in st["open"] if r["name"] == name and r["day"] == str(pd.Timestamp(now).date())]
    if len(same) >= MAX_PER_COMMODITY or len([r for r in st["open"] if r["day"] == str(pd.Timestamp(now).date())]) >= MAX_TOTAL:
        FN.note(state, "MCX_DTC (shadow)", "rejected", "risk cap (2 per commodity / 4 total per day)", key=key, now=now)
        return dict(sig, note="risk cap")
    if any(r["name"] == name and r["side"] != sig["side"] for r in same):
        FN.note(state, "MCX_DTC (shadow)", "rejected", "contradicts an open position", key=key, now=now)
        return dict(sig, note="contradictory")
    cp_min = int(sig["checkpoint"].split(":")[0]) * 60 + int(sig["checkpoint"].split(":")[1])
    delay = now.hour * 60 + now.minute - cp_min
    st["open"].append(dict(name=name, token=str(c["token"]), side=sig["side"], entry=ltp, stop=ltp - s * sig["stop_dist"],
                           risk=sig["stop_dist"], opened=str(now), day=str(pd.Timestamp(now).date()), key=key, why=sig["why"],
                           version=VERSION, checkpoint=sig["checkpoint"], signal_close=sig["close"], vwap=sig["vwap"],
                           day_open=sig["day_open"], atr_d=sig["atr_d"], slip_vs_signal=round(s * (ltp - sig["close"]), 2),
                           entry_delay_min=delay, executable=delay <= 15, assumed_cost="fees + 1.5 ticks/side",
                           mfe=0.0, mae=0.0))
    rec = st["open"][-1]
    if not LIVE:
        FN.note(state, "MCX_DTC (shadow)", "shadow", key=key, now=now)
        print(f"[mcx-dtc] {name} {sig['side']} logged only (shadow): entry {ltp} stop {ltp - s * sig['stop_dist']:.1f} · {sig['why']}")
        return dict(sig, note="shadow recorded")
    from alerts import report as RP, tradeplan as TP
    t = c.get("tick") or 1.0
    rec["live"] = True
    msgs.append("\n".join([
        f"{'🟢 BUY' if s > 0 else '🔴 SELL'}  {name} FUT  ·  INTRADAY · 🧪 EXPERIMENTAL – day-trend continuation",
        "━━━━━━━━━━━━━━",
        f"Entry   : {TP.fmt(ltp, t)}  (now; skip if price has moved more than {TP.fmt(0.1 * sig['atr_d'], t)} further)",
        f"SL      : {TP.fmt(rec['stop'], t)}  (0.5 × daily ATR)",
        "Target  : none – hold to the 23:00 square-off (exit alert follows)",
        f"Lot     : {c.get('lot') or '-'}  ·  {(format(pd.Timestamp(c['expiry']), '%b') + ' expiry') if c.get('expiry') else 'expiry n/a'}  ·  MCX"]))
    msgs.append("\n".join([
        f"📌 WHY – {name} {sig['side']} (intraday)", "━━━━━━━━━━━━━━",
        f"• Chart   : {sig['checkpoint']} checkpoint – 15-min close {TP.fmt(sig['close'], t)}",
        f"• Setup   : {sig['why']}",
        f"• Levels  : VWAP {TP.fmt(sig['vwap'], t)} · day open {TP.fmt(sig['day_open'], t)} · daily ATR {TP.fmt(sig['atr_d'], t)}",
        "• Exit    : SL on the live price or square-off at 23:00 · max 2 per commodity / 4 per day",
        "• Record  : BACKTEST ONLY – 542 trades 2023-26, +0.18R avg after costs (GOLD / SILVER only). "
        "No live record yet → EXPERIMENTAL, small size.",
        WARN]))
    RP.add(state, key="DTC|" + key, mark_key=str(c["token"]), seg="MCX", cat="FUTURES (EXPERIMENTAL)", name=name, symbol=c.get("symbol", name),
           type="Intraday day-trend (EXPERIMENTAL)", side=sig["side"], entry=ltp, sl=rec["stop"], target=None, tick=t, lot=c.get("lot"),
           mult=RP.mult_for(name, "MCX", c.get("lot")), time=str(now), experimental=True)
    FN.note(state, "MCX_DTC (experimental)", "sent", key=key, now=now)
    print(f"[mcx-dtc] {name} {sig['side']} SENT (experimental): entry {ltp} stop {rec['stop']:.1f} · {sig['why']}")
    return dict(sig, note="sent")


def track(state, name, q, now, msgs=None):
    """Every scan: stop on the live price, square-off at the first scan at / after 23:00 (or on a later day)."""
    st = store(state)
    ltp = float((q or {}).get("ltp") or 0)
    keep = []
    for r in st["open"]:
        if r["name"] != name:
            keep.append(r); continue
        s = 1 if r["side"] == "BUY" else -1
        if ltp:
            r["mfe"] = round(max(r.get("mfe", 0.0), s * (ltp - r["entry"]) / r["risk"]), 3)
            r["mae"] = round(min(r.get("mae", 0.0), s * (ltp - r["entry"]) / r["risk"]), 3)
        hm = now.hour * 60 + now.minute
        why = px = None
        if ltp and s * (ltp - r["stop"]) <= 0:
            why, px = "stop", r["stop"]
        elif str(pd.Timestamp(now).date()) != r["day"] or hm >= SQUARE_OFF:
            why, px = "square-off", ltp or None
        if why and px:
            r.update(exit=px, exit_reason=why, closed=str(now), result_R=round(s * (px - r["entry"]) / r["risk"], 3))
            st["closed"] = (st["closed"] + [r])[-300:]
            if r.get("live"):
                for L in state.get("ledger", []):
                    if L.get("key") == "DTC|" + r["key"] and L.get("status") == "OPEN":
                        L.update(status="CLOSED", exit=round(float(px), 2), note=why, closed=str(now))
                if msgs is not None:
                    g = r["result_R"]
                    msgs.append(f"{'✅' if g > 0 else '❌' if g < 0 else '➖'} EXIT – {name} FUT {r['side']} (intraday day-trend, "
                                f"EXPERIMENTAL) at {px:,.1f}: {why} · entry {r['entry']:,.1f} · {g:+.2f}R. {WARN}")
        else:
            keep.append(r)
    st["open"] = keep


def summary(state):
    """Shadow scoreboard by commodity / side / checkpoint (for the daily funnel message and reviews)."""
    cl = store(state)["closed"]
    if not cl:
        return None
    x = pd.DataFrame(cl)
    x["R"] = x["result_R"].astype(float)
    parts = []
    for col in ("name", "side", "checkpoint"):
        if col in x:
            g = x.groupby(col)["R"].agg(["size", "mean"])
            parts.append(" · ".join(f"{k} {int(v['size'])} trades {v['mean']:+.2f}R" for k, v in g.iterrows()))
    return f"MCX day-trend (shadow, not sent): {len(x)} closed, {x.R.mean():+.2f}R avg, win {100 * (x.R > 0).mean():.0f}% | " + " | ".join(parts)
