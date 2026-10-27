"""Option-BUY checks, taken from the option-SELLING engine's rules and turned around for a buyer (27-Oct-2026).

  seller skips CHEAP premium      -> buyer skips EXPENSIVE premium: option IV > 1.5 × 20-day realised volatility
  seller skips VIX spikes         -> buyer skips VIX spikes too (index options): India VIX up > 8% today = inflated premium
  seller skips high gamma (expiry)-> buyer avoids fast time decay: expiry ≥ 2 days away (option_idea) + a warning ≤ 3 days
  seller needs liquidity          -> buyer too: traded today and bid-ask spread ≤ 3% (MCX 5%)
  seller needs trend/buildup      -> already required for every futures call (trend, volume, OI must confirm)
These are sensible guards, NOT backtested: there is no option-price history to test them on.
"""
import math
import pandas as pd

IV_HV_MAX = 1.5
VIX_JUMP_PCT = 8.0
VIX_TOKEN = "99926017"
INDEX = ("NIFTY", "BANKNIFTY")


def hv20(daily):
    if daily is None or len(daily) < 12:
        return None
    r = (daily["close"].astype(float)).apply(math.log).diff().dropna().tail(20)
    return float(r.std() * math.sqrt(252)) if len(r) >= 10 else None


def check(api, ex, name, opt, fut_px, daily, now):
    """-> (ok, premium, notes, skip_reason)."""
    from greeks import implied_vol
    notes = []
    try:
        q = (api.quotes({ex: [opt["token"]]}) or {}).get(opt["token"]) or {}
    except Exception:
        q = {}
    ltp = float(q.get("ltp") or 0)
    dep = q.get("depth") or {}
    bid = float((dep.get("buy") or [{}])[0].get("price") or 0)
    ask = float((dep.get("sell") or [{}])[0].get("price") or 0)
    traded = float(q.get("tradeVolume") or 0) > 0 or not dep
    if ltp <= 0:
        return False, None, notes, "option price not available"
    if not traded:
        return False, ltp, notes, "option not traded today"
    if bid > 0 and ask > 0:
        spr = (ask - bid) / ((ask + bid) / 2)
        if spr > (0.05 if ex == "MCX" else 0.03):
            return False, ltp, notes, f"bid-ask spread {spr * 100:.1f}% too wide"
        notes.append(f"spread {spr * 100:.1f}%")
    dte = max((pd.Timestamp(opt["expiry"]).normalize() - pd.Timestamp(now).normalize()).days, 0)
    T = max(dte, 0.5) / 365
    iv = implied_vol(ltp, float(fut_px), float(opt["K"]), T, 0.065, opt["typ"])
    hv = hv20(daily)
    if iv and hv:
        notes.append(f"IV {iv * 100:.0f}% vs 20-day move {hv * 100:.0f}%")
        if iv > IV_HV_MAX * hv:
            return False, ltp, notes, f"premium expensive (IV {iv * 100:.0f}% > {IV_HV_MAX}× realised {hv * 100:.0f}%)"
    if name in INDEX:
        try:
            v = (api.quotes({"NSE": [VIX_TOKEN]}) or {}).get(VIX_TOKEN) or {}
            cur, prev = float(v.get("ltp") or 0), float(v.get("close") or 0)
            if cur and prev:
                chg = (cur / prev - 1) * 100
                notes.append(f"VIX {cur:.1f} ({chg:+.1f}%)")
                if chg > VIX_JUMP_PCT:
                    return False, ltp, notes, f"India VIX jumping {chg:+.1f}% – premiums inflated"
        except Exception:
            pass
    if dte <= 3:
        notes.append(f"⚠️ expiry in {dte} days – fast time decay, exit quickly")
    return True, ltp, notes, None
