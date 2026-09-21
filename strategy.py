"""Turn a market view into a hedged option-selling trade (strikes picked by DELTA)."""
import math
import pandas as pd
import config as C


def _pick(df, typ, target, beyond=None):
    """Option of type typ whose |delta| is closest to target; optionally further OTM than `beyond` strike."""
    d = df[(df["typ"] == typ) & df["delta"].notna()].copy()
    if beyond is not None:
        d = d[d["K"] > beyond] if typ == "CE" else d[d["K"] < beyond]
    d = d[d["mid"] > 0.5]
    if d.empty:
        return None
    return d.iloc[(d["delta"].abs() - target).abs().argsort().iloc[0]]


def k_(x):
    return int(x) if float(x).is_integer() else x


def pick_nearest_safe(df, typ, band, F, exp_move, min_oi, dte=99):
    """Nearest strike to price (most premium / time-decay) that is still >= SAFE_EM_DISTANCE x expected move
    away and inside the delta band, with enough OI and a tight bid-ask."""
    lo, hi = band
    safe = C.SAFE_EM_DISTANCE
    if dte <= 1:                       # expiry is near: gamma is high, stay at least 1 expected move away
        safe, lo = max(safe, 1.0), min(lo, 0.08)
    d = df[(df["typ"] == typ) & df["delta"].notna() & (df["mid"] > 0.5)].copy()
    d = d[(d["delta"].abs() >= lo) & (d["delta"].abs() <= hi) & (d["oi"] >= min_oi) & (d["ba_pct"] <= C.MAX_BID_ASK_PCT)]
    if exp_move:
        d = d[(d["K"] - F).abs() >= safe * exp_move]
    d = d[d["K"] > F] if typ == "CE" else d[d["K"] < F]
    if d.empty:
        return None
    return d.iloc[(d["K"] - F).abs().argsort().iloc[0]]


_CHAIN = {}


def _sell_px(o):
    return float(o["bid"]) if o["bid"] > 0 else float(o["mid"])


def _buy_px(o):
    return float(o["ask"]) if o["ask"] > 0 else float(o["mid"])


def _leg(o, side):
    return {"symbol": o["symbol"], "token": str(o["token"]), "K": float(o["K"]), "typ": o["typ"], "side": side,
            "entry": round(_sell_px(o) if side == "SELL" else _buy_px(o), 2),
            "delta": round(float(o["delta"]), 3), "iv": round(float(o["iv"]), 1),
            "gamma": float(o["gamma"]), "theta": float(o["theta"]), "vega": float(o["vega"])}


def _liquid(o, min_oi):
    return o is not None and o["ba_pct"] <= C.MAX_BID_ASK_PCT and o["oi"] >= min_oi


def _spread(df, typ, d_short, d_hedge, min_oi=None, mode="intraday"):
    oi = C.MIN_SHORT_OI if min_oi is None else min_oi
    if C.SELL_STYLE == "NAKED":
        band = C.DELTA_BAND["intraday" if mode.startswith("intraday") else mode]
        s = pick_nearest_safe(df, typ, band, _CHAIN.get("F"), _CHAIN.get("exp_move"), oi, _CHAIN.get("dte", 99))
        return [_leg(s, "SELL")] if s is not None else None
    s = _pick(df, typ, d_short)
    if not _liquid(s, oi):
        return None
    h = _pick(df, typ, d_hedge, beyond=s["K"])
    if h is None:
        return None
    return [_leg(s, "SELL"), _leg(h, "BUY")]


NAMES = {"HEDGED": {"BULLISH": "Bull Put Spread", "BEARISH": "Bear Call Spread", "NEUTRAL": "Iron Condor"},
         "NAKED": {"BULLISH": "Single PE Sell", "BEARISH": "Single CE Sell", "NEUTRAL": "Short Strangle"}}


def gamma_risk(legs, F, T, exp_move, dte):
    """LOW / MEDIUM / HIGH / EXTREME from how close the short strike is (in expected-move units) and DTE."""
    if not exp_move:
        return "UNKNOWN", None
    z = min(abs(l["K"] - F) for l in legs if l["side"] == "SELL") / exp_move
    if dte == 0 and z < 1.0:
        lvl = "EXTREME"
    elif z < 0.6 or (dte <= 1 and z < 1.0):
        lvl = "HIGH"
    elif z < 1.0:
        lvl = "MEDIUM"
    else:
        lvl = "LOW"
    return lvl, round(z, 2)


def build_trade(chain, bias, mode, allow_condor=True):
    """mode: intraday | intraday_expiry | weekly | monthly"""
    df, lot = chain["df"], chain["lot"]
    d = C.DELTA[mode]
    oi = C.MCX_MIN_SHORT_OI if chain.get("exch") == "MCX" else C.MIN_SHORT_OI
    _CHAIN.clear(); _CHAIN.update(F=chain["F"], exp_move=chain.get("exp_move"), dte=chain.get("dte", 99))
    strat = NAMES[C.SELL_STYLE][bias]
    if bias == "BULLISH":
        legs = _spread(df, "PE", d["short"], d["hedge"], oi, mode)
    elif bias == "BEARISH":
        legs = _spread(df, "CE", d["short"], d["hedge"], oi, mode)
    else:
        if not allow_condor or (C.SELL_STYLE == "NAKED" and not C.ALLOW_STRANGLE):
            return None
        p = _spread(df, "PE", d["condor_short"], d["hedge"], oi, mode)
        c = _spread(df, "CE", d["condor_short"], d["hedge"], oi, mode)
        legs = p + c if p and c else None
    if not legs:
        return None

    naked = C.SELL_STYLE == "NAKED"
    credit = sum(l["entry"] * (1 if l["side"] == "SELL" else -1) for l in legs)
    if credit <= 0:
        return None
    if naked:
        width, max_loss = None, None
    else:
        width = max(abs(tl[0]["K"] - tl[1]["K"]) for typ in ("PE", "CE")
                    if (tl := [l for l in legs if l["typ"] == typ]))
        if credit / width < C.MIN_CREDIT_TO_WIDTH:
            return None
        max_loss = width - credit
    be = []
    for l in legs:
        if l["side"] == "SELL":
            be.append(round(l["K"] - credit if l["typ"] == "PE" else l["K"] + credit, 1))

    sign = lambda l: -1 if l["side"] == "SELL" else 1
    pg = {g: round(sum(sign(l) * l[g] for l in legs) * lot, 2) for g in ("delta", "gamma", "theta", "vega")}

    rules = C.RULES["intraday" if mode.startswith("intraday") else mode]
    sl_val = credit * (1 + rules["sl_pct"] / 100) if naked else credit * rules["sl_mult"]
    if naked and credit * lot < C.MIN_PREMIUM_RS_PER_LOT:
        return None
    if naked and (credit - credit * (1 - rules["target_pct"] / 100)) / max(sl_val - credit, 1e-9) < C.MIN_RR - 1e-9:
        return None                                             # reward smaller than risk -> skip
    spot = chain["spot"]
    shorts = [l for l in legs if l["side"] == "SELL"]
    spot_stop = None
    if naked and len(shorts) == 1:                   # exit if price covers half the way to the sold strike
        spot_stop = round(spot + C.SPOT_STOP_FRACTION * (shorts[0]["K"] - spot), 1)
    target_val = credit * (1 - rules["target_pct"] / 100)
    risk, reward = sl_val - credit, credit - target_val          # per unit, as the spec defines
    loss_for_sizing = max_loss if max_loss else risk
    lots = max(1, math.floor(C.CAPITAL_RS * C.MAX_RISK_PER_TRADE / (loss_for_sizing * lot)))
    margin = None
    if naked:
        kind = "mcx" if chain.get("exch") == "MCX" else ("index" if chain.get("name") in C.INDEX_TOKENS else "stock")
        margin = round(chain["spot"] * lot * C.MARGIN_PCT[kind] * len(shorts) + credit * lot)
        lots = max(1, min(lots, math.floor(C.CAPITAL_RS * C.MAX_CAPITAL_USE / margin)))
    costs = C.COST_PER_ORDER_RS * len(legs) * 2                  # entry + exit, per lot
    g_lvl, g_z = gamma_risk(legs, chain["F"], chain["T"], chain.get("exp_move"), chain.get("dte", 99))
    return {
        "strategy": strat, "bias": bias, "legs": legs, "lot": lot, "lots": lots,
        "credit": round(credit, 2), "width": width, "max_loss": round(max_loss, 2) if max_loss else None,
        "risk_rs": round(risk * lot), "reward_rs": round(reward * lot), "rr": round(reward / risk, 2),
        "costs_rs": costs, "rom_pct": round(credit / max_loss * 100, 1) if max_loss else None,
        "gamma_risk": g_lvl, "strike_em": g_z,
        "breakevens": be, "pos_greeks": pg,
        "target_val": round(target_val, 2),
        "sl_val": round(sl_val, 2),
        "adjust_delta": rules["adjust_delta"], "spot_stop": spot_stop, "margin_rs": margin,
        "pop": round((1 - sum(abs(l["delta"]) for l in legs if l["side"] == "SELL")) * 100),
    }
