"""Live 1-minute futures bars from the Angel WebSocket (written by wsfeed.py, read by angel.Angel).

Why (29-Oct-2026): Angel's historical-candle API answers "Access denied because of exceeding access rate" at rates far below
its published limit (many users on the SmartAPI forum since Aug/Sep-2026). On 27-29 Oct the bot lost NIFTY / BANKNIFTY /
MCX / stock data for most of each day. The WebSocket stream is a different service: one connection gives live ticks for
hundreds of futures, and the candles are built here, so the engines need the candle API only once a day for older history.

Files (in .cache/ws): bars_<token>.csv (completed minutes: time,open,high,low,close,volume,oi), live_<token>.json (the minute
still forming), status.json (collector start, last tick per exchange, tokens). Times are IST, bar label = minute start.
"""
import json
import time
from pathlib import Path
import pandas as pd

DIR = Path(__file__).parent / ".cache" / "ws"
COLS = ["time", "open", "high", "low", "close", "volume", "oi"]
MINUTES = {"ONE_MINUTE": 1, "THREE_MINUTE": 3, "FIVE_MINUTE": 5, "TEN_MINUTE": 10, "FIFTEEN_MINUTE": 15,
           "THIRTY_MINUTE": 30, "ONE_HOUR": 60, "ONE_DAY": None}
OPEN = {"NFO": (9, 15), "MCX": (9, 0)}
CLOSE = {"NFO": (15, 30), "MCX": (23, 55)}
FRESH_SEC = 180


def _dir(d=None):
    p = Path(d) if d else DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


# ─────────────── writer side (wsfeed.py) ───────────────
class Builder:
    """Ticks -> 1-minute bars. Bar volume = change of the day's cumulative traded volume since the previous bar."""

    def __init__(self, d=None):
        self.d = _dir(d)
        self.cur, self.cum = {}, {}

    def tick(self, token, t, ltp, cum_vol, oi):
        m = pd.Timestamp(t).floor("min")
        b = self.cur.get(token)
        if b is not None and m > b["time"]:
            self._close(token)
            b = None
        if b is None:
            prev = self.cum.get(token, cum_vol)
            self.cur[token] = b = dict(time=m, open=ltp, high=ltp, low=ltp, close=ltp, v0=prev, v=cum_vol, oi=oi)
        else:
            b["high"], b["low"], b["close"] = max(b["high"], ltp), min(b["low"], ltp), ltp
            b["v"], b["oi"] = max(b["v"], cum_vol), oi if oi else b["oi"]
        self.cum[token] = max(self.cum.get(token, 0), cum_vol)

    def _close(self, token):
        b = self.cur.pop(token)
        vol = max(b["v"] - b["v0"], 0)
        with open(self.d / f"bars_{token}.csv", "a") as f:
            f.write(f"{b['time']:%Y-%m-%d %H:%M},{b['open']},{b['high']},{b['low']},{b['close']},{vol},{b['oi']}\n")

    def flush(self, now):
        """Close minutes that are over (no tick needed) and write the forming minute of every token."""
        m = pd.Timestamp(now).floor("min")
        for tok in [t for t, b in self.cur.items() if b["time"] < m]:
            self._close(tok)
        for tok, b in self.cur.items():
            x = dict(b, time=str(b["time"]), volume=max(b["v"] - b["v0"], 0))
            tmp = self.d / f"live_{tok}.tmp"
            tmp.write_text(json.dumps({k: x[k] for k in COLS}))
            tmp.replace(self.d / f"live_{tok}.json")


def write_status(st, d=None):
    p = _dir(d) / "status.tmp"
    p.write_text(json.dumps(st, default=str))
    p.replace(_dir(d) / "status.json")


# ─────────────── reader side (angel.Angel) ───────────────
def status(d=None):
    try:
        return json.loads((_dir(d) / "status.json").read_text())
    except Exception:
        return None


def usable(st, exch, token, now):
    """True when the collector covers this token and its feed for this exchange is live (or ran to the session close)."""
    if not st or str(token) not in set(map(str, st.get("tokens", []))):
        return False
    last = (st.get("last_tick") or {}).get(exch)
    if not last:
        return False
    last = pd.Timestamp(last)
    if (now - last).total_seconds() <= FRESH_SEC:
        return True
    close = now.normalize() + pd.Timedelta(hours=CLOSE[exch][0], minutes=CLOSE[exch][1])
    return last.normalize() == now.normalize() and now >= close and last >= close - pd.Timedelta(minutes=10)


def minutes(token, day, d=None):
    """Today's 1-minute bars (completed + the forming one) for a token."""
    p = _dir(d) / f"bars_{token}.csv"
    try:
        df = pd.read_csv(p, names=COLS, header=None, parse_dates=["time"])
    except Exception:
        df = pd.DataFrame(columns=COLS)
    try:
        live = json.loads((_dir(d) / f"live_{token}.json").read_text())
        live["time"] = pd.Timestamp(live["time"])
        df = pd.concat([df, pd.DataFrame([live])], ignore_index=True)
    except Exception:
        pass
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"])
    df = df[df["time"].dt.normalize() == pd.Timestamp(day).normalize()]
    return df.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)


def bucket_start(t, interval, exch):
    t = pd.Timestamp(t)
    if MINUTES[interval] is None:
        return t.normalize()
    h, m = OPEN[exch]
    anchor = t.normalize() + pd.Timedelta(hours=h, minutes=m)
    k = (t - anchor) // pd.Timedelta(minutes=MINUTES[interval])
    return anchor + k * pd.Timedelta(minutes=MINUTES[interval])


def aggregate(m1, interval, exch):
    """1-minute bars -> interval bars aligned to the session open (NSE 09:15, MCX 09:00), label = bar start."""
    if m1 is None or m1.empty:
        return pd.DataFrame(columns=COLS)
    x = m1.copy()
    x["b"] = [bucket_start(t, interval, exch) for t in x["time"]]
    g = x.groupby("b", sort=True)
    out = pd.DataFrame(dict(time=list(g.groups.keys()), open=g["open"].first().values, high=g["high"].max().values,
                            low=g["low"].min().values, close=g["close"].last().values, volume=g["volume"].sum().values,
                            oi=g["oi"].last().values))
    return out.reset_index(drop=True)


def combine(hist, pre, ws, boundary):
    """hist: bars before today (REST, cached) · pre: today's REST bars up to the collector start · ws: WebSocket bars ·
    boundary: start of the bucket that holds the collector start (REST part + WS part are merged into one bar)."""
    parts = []
    if hist is not None and len(hist):
        parts.append(hist)
    if pre is not None and len(pre):
        pre = pre[pre["time"] <= boundary]
    if ws is not None and len(ws):
        if pre is not None and len(pre) and (pre["time"] == boundary).any() and (ws["time"] == boundary).any():
            r, w = pre[pre["time"] == boundary].iloc[0], ws[ws["time"] == boundary].iloc[0]
            mb = dict(time=boundary, open=r["open"], high=max(r["high"], w["high"]), low=min(r["low"], w["low"]), close=w["close"],
                      volume=r["volume"] + w["volume"])
            if "oi" in ws:
                mb["oi"] = w["oi"]
            pre = pd.concat([pre[pre["time"] < boundary], pd.DataFrame([mb])], ignore_index=True)
            ws = ws[ws["time"] > boundary]
        elif pre is not None and len(pre):
            ws = ws[ws["time"] > pre["time"].max()]
    for p in (pre, ws):
        if p is not None and len(p):
            parts.append(p)
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    return df.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)


def verify_ok(rest, ws, tol_px=0.003, tol_vol=0.35):
    """Compare REST and WebSocket bars of the same completed buckets -> (ok, note)."""
    if rest is None or ws is None or rest.empty or ws.empty:
        return None, "nothing to compare"
    j = rest.merge(ws, on="time", suffixes=("_r", "_w"))
    if j.empty:
        return None, "no common bars"
    px = ((j["close_w"] - j["close_r"]).abs() / j["close_r"]).max()
    hl = max(((j["high_w"] - j["high_r"]).abs() / j["high_r"]).max(), ((j["low_w"] - j["low_r"]).abs() / j["low_r"]).max())
    vr = (j["volume_w"].sum() / j["volume_r"].sum()) if j["volume_r"].sum() > 0 else None
    ok = px <= tol_px and hl <= tol_px and (vr is None or abs(vr - 1) <= tol_vol)
    return ok, f"{len(j)} bars · close diff {px * 100:.2f}% · high/low diff {hl * 100:.2f}% · volume ratio {vr if vr is None else round(vr, 2)}"


def now_epoch():
    return time.time()
