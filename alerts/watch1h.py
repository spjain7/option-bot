"""1H BIG MOVE – WATCH alerts (owner request 29-Oct-2026: "do live, I will watch next 2-3 days").

NOT a trade call: no entry / stop / target. Hourly breakout CALLS were tested (research BO1H-001/002, 9,491 combos) and
lost money after costs, so this only tells the owner that a big hourly move is under way, and tracks what happened next.

Rule (completed 1-hour futures candle):
  BUY watch : close above the highest high of the previous 20 hourly candles AND volume ≥ 2× their average
  SELL watch: close below the lowest low of the previous 20 hourly candles AND volume ≥ 2× their average
  OI must support the move (BUY: long buildup / short covering · SELL: short buildup / long unwinding); unknown OI -> not sent
Markets: MCX + NIFTY / BANKNIFTY (alerts engine, Angel 1h candles) and the option-buy stock list (hourly candles built from
the 15-min candles already fetched – no extra API calls). One watch per instrument per side per day.
Tracking: the best and worst price after the alert (from later hourly candles) and an end-of-day summary.
"""
import pandas as pd

N, VOL_X = 20, 2.0
GOOD = {"BUY": ("Long buildup", "Short covering"), "SELL": ("Short buildup", "Long unwinding")}


def hourly_from_15m(df, now):
    """NSE 15-min futures candles -> COMPLETED hourly candles 09:15-10:15 ... 14:15-15:15 (the 15:15-15:30 stub is dropped).
    Keeps OI at the hour's last bar."""
    if df is None or df.empty:
        return None
    d = df[["time", "open", "high", "low", "close", "volume"] + (["oi"] if "oi" in df else [])].copy()
    d["day"] = d["time"].dt.normalize()
    mins = (d["time"] - d["day"] - pd.Timedelta(hours=9, minutes=15)).dt.total_seconds() // 60
    d = d[(mins >= 0) & (mins < 360)]
    d["k"] = (mins[mins.index.isin(d.index)] // 60).astype(int)
    agg = dict(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
               volume=("volume", "sum"), bars=("time", "size"))
    if "oi" in d:
        agg["oi"] = ("oi", "last")
    h = d.groupby(["day", "k"]).agg(**agg).reset_index(drop=True)
    h["end"] = h["time"] + pd.Timedelta(minutes=60)
    h = h[(h["bars"] == 4) & (h["end"] <= now)]
    return h.drop(columns=["bars"]).reset_index(drop=True)


def oi_label(price_chg, oi_chg):
    if oi_chg is None or price_chg is None or pd.isna(oi_chg) or pd.isna(price_chg) or oi_chg == 0 or price_chg == 0:
        return None
    if price_chg > 0:
        return "Long buildup" if oi_chg > 0 else "Short covering"
    return "Short buildup" if oi_chg > 0 else "Long unwinding"


def _fmt(x):
    return f"{x:,.2f}" if abs(x) < 1000 else f"{x:,.0f}"


def _track(st, name, h1):
    for r in st["open"]:
        if r["name"] != name:
            continue
        new = h1[h1["time"] > pd.Timestamp(r["bar"])]
        if new.empty:
            continue
        s = 1 if r["side"] == "BUY" else -1
        fav = new["high"].max() if s > 0 else new["low"].min()
        adv = new["low"].min() if s > 0 else new["high"].max()
        if s * (fav - r["best"]) > 0:
            r["best"] = float(fav)
        if s * (adv - r["worst"]) < 0:
            r["worst"] = float(adv)
        r["last"] = float(new["close"].iloc[-1])


def check(state, msgs, name, seg, h1, now, oi=None, unit=""):
    """h1 = completed hourly futures candles (time, open, high, low, close, volume[, oi]).
    oi = label string (MCX / index, from the engine's OI reading) or None -> derived from the hour's OI change if h1 has oi."""
    st = state.setdefault("watch1h", dict(open=[], seen=[]))
    if h1 is None or len(h1) < N + 2:
        return None
    h1 = h1.sort_values("time").reset_index(drop=True)
    _track(st, name, h1)
    x, prev = h1.iloc[-1], h1.iloc[-N - 1:-1]
    hh, ll, va = float(prev["high"].max()), float(prev["low"].min()), float(prev["volume"].mean())
    vx = float(x["volume"]) / va if va > 0 else 0.0
    side = "BUY" if x["close"] > hh else "SELL" if x["close"] < ll else None
    if side is None or vx < VOL_X:
        return None
    if oi is None and "oi" in h1 and len(h1) >= 2:
        oi = oi_label(float(x["close"] - h1["close"].iloc[-2]), float(x["oi"] - h1["oi"].iloc[-2]) if pd.notna(h1["oi"].iloc[-2]) else None)
    day = f"{now:%Y-%m-%d}"
    key = f"{name}|{side}|{day}"
    if key in st["seen"]:
        return None
    if oi not in GOOD[side]:
        print(f"[watch1h] {name} {side} hourly breakout vol {vx:.1f}× not sent: OI {oi or 'n/a'} does not support it")
        st["seen"] = (st["seen"] + [key])[-500:]
        return None
    st["seen"] = (st["seen"] + [key])[-500:]
    t0 = pd.Timestamp(x["time"])
    st["open"].append(dict(name=name, seg=seg, side=side, day=day, bar=str(t0), close=float(x["close"]), level=hh if side == "BUY" else ll,
                           vol_x=round(vx, 2), oi=oi, best=float(x["close"]), worst=float(x["close"]), last=float(x["close"]),
                           sent=str(now)))
    st["open"] = st["open"][-200:]
    arrow = "🟢" if side == "BUY" else "🔴"
    m = (f"👀 1H BIG MOVE – WATCH (not a call) {arrow} {name} {seg}\n"
         f"• 1-hour candle {t0:%H:%M}–{t0 + pd.Timedelta(hours=1):%H:%M} closed {_fmt(x['close'])} "
         f"{'above the 20-hour high' if side == 'BUY' else 'below the 20-hour low'} {_fmt(hh if side == 'BUY' else ll)}\n"
         f"• Volume {vx:.1f}× the 20-hour average · OI: {oi} (supports the move)\n"
         "• Hourly breakouts lost money as trade calls in the 4-year test – no entry / SL / target. Watch only; "
         "the result is tracked in the end-of-day summary.")
    msgs.append(m)
    return m


def summary_msg(state, day, segs):
    st = state.get("watch1h") or {}
    rs = [r for r in st.get("open", []) if r["day"] == day and r["seg"] in segs]
    if not rs:
        return None
    lines = [f"👀 1H BIG MOVE watches – {pd.Timestamp(day):%d-%b} ({', '.join(segs)})"]
    for r in rs:
        s = 1 if r["side"] == "BUY" else -1
        pct = lambda v: s * (v - r["close"]) / r["close"] * 100
        lines.append(f"• {r['name']} {r['side']} at {_fmt(r['close'])} ({pd.Timestamp(r['bar']):%H:%M}): further move "
                     f"{pct(r['best']):+.2f}% · against {pct(r['worst']):+.2f}% · last {_fmt(r['last'])} ({pct(r['last']):+.2f}%)")
    lines.append("Watch only – not trade calls.")
    return "\n".join(lines)
