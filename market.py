"""Market view: spot, option chain with IV/Greeks, PCR, OI walls, futures buildup, VIX, trend bias."""
import math
import numpy as np
import pandas as pd
import config as C
import greeks as G
from angel import now_ist

MIN_PER_YEAR = 365 * 24 * 60


# ─────────────── expiries ───────────────
OPT_TYPES = {"NFO": ["OPTIDX", "OPTSTK"], "BFO": ["OPTIDX"], "MCX": ["OPTFUT", "OPTCOM"]}
FUT_TYPES = {"NFO": ["FUTIDX", "FUTSTK"], "BFO": ["FUTIDX"], "MCX": ["FUTCOM"]}
EXPIRY_TIME = {"NFO": "15:30", "BFO": "15:30", "MCX": "23:30"}


def deriv_exch(name):
    return "BFO" if name in C.BSE_INDICES else "NFO"


def spot_seg(name):
    return "BSE" if name in C.BSE_INDICES else "NSE"


def expiries(master, name, exch="NFO"):
    today = now_ist().normalize()
    e = master[(master["name"] == name) & (master["exch_seg"] == exch)
               & master["instrumenttype"].isin(OPT_TYPES[exch])]["expiry_dt"]
    return sorted(d for d in e.dropna().unique() if pd.Timestamp(d) >= today)


def monthly_expiries(exps):
    s = pd.Series(pd.to_datetime(exps))
    return sorted(s.groupby(s.dt.to_period("M")).max().tolist())


def time_to_expiry(expiry, exch="NFO"):
    h, mi = map(int, EXPIRY_TIME[exch].split(":"))
    exp = pd.Timestamp(expiry) + pd.Timedelta(hours=h, minutes=mi)
    return max((exp - now_ist()).total_seconds() / 60, 1) / MIN_PER_YEAR


def dte(expiry):
    return (pd.Timestamp(expiry).normalize() - now_ist().normalize()).days


# ─────────────── spot / futures ───────────────
def spot_token(master, name):
    if name in C.INDEX_TOKENS:
        return C.INDEX_TOKENS[name]
    m = master[(master["exch_seg"] == "NSE") & (master["symbol"] == f"{name}-EQ")]
    return None if m.empty else str(m.iloc[0]["token"])


def near_future(master, name, exch="NFO", on_or_after=None):
    """Nearest future; for MCX options pass the option expiry to get its underlying future."""
    start = pd.Timestamp(on_or_after) if on_or_after is not None else now_ist().normalize()
    m = master[(master["name"] == name) & (master["exch_seg"] == exch)
               & master["instrumenttype"].isin(FUT_TYPES[exch]) & (master["expiry_dt"] >= start)].sort_values("expiry_dt")
    return None if m.empty else m.iloc[0].to_dict()


def futures_buildup(api, master, name, exch="NFO", fut=None):
    """Price vs OI change of near-month future since yesterday."""
    fut = fut or near_future(master, name, exch)
    if fut is None:
        return None
    q = api.quotes({exch: [fut["token"]]}).get(str(fut["token"]))
    oi = api.oi_history(exch, fut["token"], "ONE_DAY", now_ist() - pd.Timedelta(days=10), now_ist())
    if not q or oi is None or oi.empty:
        return None
    today = now_ist().normalize()
    prev = oi[oi["time"].dt.normalize() < today]
    if prev.empty:
        return None
    oi_prev, oi_now = float(prev["oi"].iloc[-1]), float(q.get("opnInterest") or 0)
    px_chg = float(q.get("percentChange") or 0)
    oi_chg = (oi_now / oi_prev - 1) * 100 if oi_prev else 0
    if px_chg >= 0 and oi_chg >= 0:
        label, score = "Long buildup", 1
    elif px_chg < 0 and oi_chg >= 0:
        label, score = "Short buildup", -1
    elif px_chg >= 0:
        label, score = "Short covering", 0.5
    else:
        label, score = "Long unwinding", -0.5
    return {"label": label, "score": score, "px_chg": round(px_chg, 2), "oi_chg": round(oi_chg, 2),
            "lot": int(fut["lotsize"])}


# ─────────────── VIX / volatility ───────────────
def vix_info(api):
    now = now_ist()
    d = api.candles("NSE", C.VIX_TOKEN, "ONE_DAY", now - pd.Timedelta(days=370), now)
    q = api.quotes({"NSE": [C.VIX_TOKEN]}).get(C.VIX_TOKEN, {})
    cur = float(q.get("ltp") or (d["close"].iloc[-1] if d is not None and not d.empty else 0))
    prev = float(q.get("close") or 0)
    pct = float((d["close"] < cur).mean() * 100) if d is not None and len(d) > 50 else 50.0
    return {"vix": round(cur, 2), "chg": round((cur / prev - 1) * 100, 1) if prev else 0.0,
            "pctile": round(pct)}


def hv20(daily):
    r = np.log(daily["close"]).diff().dropna().tail(20)
    return float(r.std() * math.sqrt(252) * 100) if len(r) >= 10 else None


# ─────────────── trend bias ───────────────
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def adx(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    up, dn = h.diff(), -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False).mean() / atr
    ndi = 100 * ndm.ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return float(dx.ewm(alpha=1 / n, adjust=False).mean().iloc[-1])


def trend_score(df, fast, slow):
    """+1 bullish, -1 bearish, 0 range/neutral: EMA stack, ignored when ADX says RANGE."""
    if df is None or len(df) < slow + 2:
        return 0, None
    c = df["close"]
    ef, es = ema(c, fast).iloc[-1], ema(c, slow).iloc[-1]
    last = c.iloc[-1]
    a = adx(df) if {"high", "low"} <= set(df.columns) else 25.0
    if a < C.ADX_RANGE_BELOW:
        s, regime = 0, "RANGE"
    elif last > ef > es:
        s, regime = 1, "UPTREND"
    elif last < ef < es:
        s, regime = -1, "DOWNTREND"
    else:
        s, regime = 0, "MIXED"
    return s, {"close": round(float(last), 2), "ema_fast": round(float(ef), 2), "ema_slow": round(float(es), 2),
               "adx": round(a, 1), "regime": regime}


def iv_label(iv, rv):
    """How expensive options are vs how much the market is actually moving."""
    if not iv or not rv:
        return "UNKNOWN", None
    x = iv / rv
    lab = "CHEAP" if x < C.IV_RV_CHEAP else "NORMAL" if x < 1.1 else "EXPENSIVE" if x < 1.5 else "EXTREMELY EXPENSIVE"
    return lab, round(x, 2)


def combine_bias(trend, buildup, pcr):
    score = trend * 1.5
    if buildup:
        score += buildup["score"]
    if pcr is not None:
        score += 0.5 if pcr >= C.PCR_BULL else -0.5 if pcr <= C.PCR_BEAR else 0
    if score >= 1.5:
        return "BULLISH", score
    if score <= -1.5:
        return "BEARISH", score
    return "NEUTRAL", score


# ─────────────── option chain ───────────────
def build_chain(api, master, name, expiry, spot, width_pct=0.08, exch="NFO"):
    exp = pd.Timestamp(expiry)
    ch = master[(master["name"] == name) & (master["expiry_dt"] == exp) & (master["exch_seg"] == exch)
                & master["instrumenttype"].isin(OPT_TYPES[exch])].copy()
    if ch.empty:
        return None
    # Angel stores strike x100 for NFO; pick the scale closest to spot
    med = ch["strike"].median()
    ch["K"] = ch["strike"] / (100 if abs(med / 100 - spot) < abs(med - spot) else 1)
    ch["typ"] = ch["symbol"].str[-2:]
    ch = ch[(ch["K"] >= spot * (1 - width_pct)) & (ch["K"] <= spot * (1 + width_pct))]
    if ch.empty:
        return None

    qs = api.quotes({exch: ch["token"].astype(str).tolist()})

    def field(tok, key):
        return qs.get(str(tok), {}).get(key)

    def best(tok, side):
        d = (qs.get(str(tok), {}).get("depth") or {}).get(side) or []
        return float(d[0]["price"]) if d and d[0].get("price") else 0.0

    ch["ltp"] = ch["token"].map(lambda t: float(field(t, "ltp") or 0))
    ch["oi"] = ch["token"].map(lambda t: float(field(t, "opnInterest") or 0))
    ch["volume"] = ch["token"].map(lambda t: float(field(t, "tradeVolume") or 0))
    ch["bid"] = ch["token"].map(lambda t: best(t, "buy"))
    ch["ask"] = ch["token"].map(lambda t: best(t, "sell"))
    ch = ch[ch["ltp"] > 0].copy()
    if ch.empty:
        return None
    ch["mid"] = np.where((ch["bid"] > 0) & (ch["ask"] > 0), (ch["bid"] + ch["ask"]) / 2, ch["ltp"])
    ch["ba_pct"] = np.where((ch["bid"] > 0) & (ch["ask"] > 0), (ch["ask"] - ch["bid"]) / ch["mid"] * 100, 0)

    T, r = time_to_expiry(exp, exch), C.RISK_FREE
    # implied forward from put-call parity at the strike where |C-P| is smallest
    piv = ch.pivot_table(index="K", columns="typ", values="mid", aggfunc="first").dropna()
    if not piv.empty and {"CE", "PE"} <= set(piv.columns):
        k0 = (piv["CE"] - piv["PE"]).abs().idxmin()
        F = k0 + (piv.loc[k0, "CE"] - piv.loc[k0, "PE"]) * math.exp(r * T)
    else:
        F = spot * math.exp(r * T)

    rows = []
    for _, o in ch.iterrows():
        iv = G.implied_vol(o["mid"], F, o["K"], T, r, o["typ"])
        g = G.greeks(F, o["K"], T, iv, r, o["typ"]) if iv else {"delta": None, "gamma": None, "theta": None, "vega": None}
        rows.append({**{k: o[k] for k in ["K", "typ", "token", "symbol", "ltp", "bid", "ask", "mid", "ba_pct", "oi",
                                          "volume", "lotsize"]}, "iv": iv * 100 if iv else None, **g})
    df = pd.DataFrame(rows).sort_values(["typ", "K"]).reset_index(drop=True)

    ce_oi, pe_oi = df[df.typ == "CE"]["oi"].sum(), df[df.typ == "PE"]["oi"].sum()
    atm = df.iloc[(df["K"] - F).abs().argsort()[:2]]
    atm_iv = float(atm["iv"].dropna().mean()) if atm["iv"].notna().any() else None

    def iv_at(typ, target=0.25):
        d = df[(df.typ == typ) & df["delta"].notna()]
        return None if d.empty else float(d.iloc[(d["delta"].abs() - target).abs().argsort().iloc[0]]["iv"])
    pe25, ce25 = iv_at("PE"), iv_at("CE")
    return {
        "df": df, "F": F, "T": T, "spot": spot, "expiry": exp,
        "pcr": round(pe_oi / ce_oi, 2) if ce_oi else None,
        "call_wall": float(df[df.typ == "CE"].sort_values("oi").iloc[-1]["K"]) if ce_oi else None,
        "put_wall": float(df[df.typ == "PE"].sort_values("oi").iloc[-1]["K"]) if pe_oi else None,
        "atm_iv": round(atm_iv, 2) if atm_iv else None,
        "exp_move": round(F * atm_iv / 100 * math.sqrt(T), 1) if atm_iv else None,   # 1 SD to expiry
        "skew": round(pe25 - ce25, 1) if pe25 and ce25 else None,                  # + = puts richer
        "lot": int(C.MCX_RS_PER_POINT.get(name, df["lotsize"].iloc[0])) if exch == "MCX" else int(df["lotsize"].iloc[0]),
        "exch": exch, "name": name,
    }
