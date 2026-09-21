"""Tracks every signal as a (paper) position and tells you when to book, stop, adjust or exit."""
import json, math
from pathlib import Path
import pandas as pd
import config as C
import greeks as G
from angel import now_ist

STATE_FILE = Path(__file__).parent / "state" / "state.json"


class Store:
    def __init__(self):
        self.s = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        for k, v in {"next_id": 1, "positions": [], "closed": [], "done": {}, "iv_hist": {}}.items():
            self.s.setdefault(k, v)
        cutoff = (now_ist() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        self.s["done"] = {k: v for k, v in self.s["done"].items() if v >= cutoff}

    def save(self):
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps(self.s, indent=1, default=str))

    def done(self, key):
        return key in self.s["done"]

    def mark(self, key):
        self.s["done"][key] = now_ist().strftime("%Y-%m-%d")

    def open_positions(self, mode=None, name=None):
        return [p for p in self.s["positions"]
                if (mode is None or p["mode"] == mode) and (name is None or p["name"] == name)]

    def add(self, trade):
        trade["id"] = self.s["next_id"]
        self.s["next_id"] += 1
        trade["opened"] = now_ist().strftime("%Y-%m-%d %H:%M")
        trade["flags"] = []
        self.s["positions"].append(trade)
        self.save()
        return trade["id"]

    def close(self, p, value, reason):
        p["exit_value"] = round(value, 2)
        p["pnl_pts"] = round(p["credit"] - value, 2)
        p["pnl_rs_per_lot"] = round(p["pnl_pts"] * p["lot"], 0)
        p["closed"] = now_ist().strftime("%Y-%m-%d %H:%M")
        p["exit_reason"] = reason
        self.s["positions"].remove(p)
        self.s["closed"].append(p)

    def record_iv(self, name, iv):
        if iv:
            h = self.s["iv_hist"].setdefault(name, {})
            h[now_ist().strftime("%Y-%m-%d")] = iv
            for k in sorted(h)[:-260]:
                del h[k]

    def iv_rank(self, name, iv):
        h = list(self.s["iv_hist"].get(name, {}).values())
        if len(h) < 20 or not iv:
            return None
        lo, hi = min(h), max(h)
        return round((iv - lo) / (hi - lo) * 100) if hi > lo else 50


# ─────────────── monitoring ───────────────
def _leg_state(leg, qs, spot, T):
    q = qs.get(leg["token"], {})
    ltp = float(q.get("ltp") or 0)
    dep = q.get("depth") or {}
    b = (dep.get("buy") or [{}])[0].get("price") or 0
    a = (dep.get("sell") or [{}])[0].get("price") or 0
    px = (b + a) / 2 if b and a else ltp
    F = spot * math.exp(C.RISK_FREE * T)
    iv = G.implied_vol(px, F, leg["K"], T, C.RISK_FREE, leg["typ"]) if px else None
    delta = G.greeks(F, leg["K"], T, iv, C.RISK_FREE, leg["typ"])["delta"] if iv else (
        (1.0 if leg["typ"] == "CE" else -1.0) if (spot > leg["K"]) == (leg["typ"] == "CE") else 0.0)
    return px, delta


def check(p, qs, spot, T, now):
    """returns (action, value, details) - action in TARGET, SL, TIME, ADJUST, None"""
    vals, deltas = 0.0, []
    for l in p["legs"]:
        px, dlt = _leg_state(l, qs, spot, T)
        if px <= 0:
            return None, None, None
        vals += px if l["side"] == "SELL" else -px
        if l["side"] == "SELL":
            deltas.append((l, dlt))
    value = max(vals, 0.0)
    info = {"value": round(value, 2), "pnl": round(p["credit"] - value, 2),
            "short_deltas": {f"{int(l['K'])}{l['typ']}": round(d, 2) for l, d in deltas}}

    exp = pd.Timestamp(p["expiry"])
    if value <= p["target_val"]:
        return "TARGET", value, info
    if value >= p["sl_val"]:
        return "SL", value, info
    if p["mode"] == "intraday" and (now >= now.normalize() + _hm(C.INTRADAY_EXIT_TIME)
                                    or pd.Timestamp(p["opened"]).normalize() < now.normalize()):
        return "TIME", value, info
    if p["mode"] == "weekly" and now.normalize() >= exp and now >= now.normalize() + _hm(C.WEEKLY_EXIT_TIME):
        return "TIME", value, info
    if p["mode"] == "monthly" and (exp - now.normalize()).days <= C.MONTHLY_EXIT_DTE:
        return "TIME", value, info
    if any(abs(d) >= p["adjust_delta"] for _, d in deltas) and "adjust" not in p["flags"]:
        return "ADJUST", value, info
    return None, value, info


def _hm(s):
    h, m = map(int, s.split(":"))
    return pd.Timedelta(hours=h, minutes=m)
