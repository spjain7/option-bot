"""Black-76 pricing, implied volatility and Greeks (per 1 unit of underlying)."""
import math

SQ2 = math.sqrt(2.0)


def N(x):
    return 0.5 * (1 + math.erf(x / SQ2))


def n(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def price(F, K, T, sigma, r, typ):
    if T <= 0 or sigma <= 0:
        return max(0.0, (F - K) if typ == "CE" else (K - F)) * math.exp(-r * max(T, 0))
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    df = math.exp(-r * T)
    return df * (F * N(d1) - K * N(d2)) if typ == "CE" else df * (K * N(-d2) - F * N(-d1))


def implied_vol(p, F, K, T, r, typ):
    if p is None or p <= 0 or T <= 0:
        return None
    intrinsic = max(0.0, (F - K) if typ == "CE" else (K - F)) * math.exp(-r * T)
    if p <= intrinsic + 1e-6:
        return None
    lo, hi = 0.005, 4.0
    if price(F, K, T, hi, r, typ) < p:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if price(F, K, T, mid, r, typ) > p:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def greeks(F, K, T, sigma, r, typ):
    """delta, gamma (per 1 pt), theta (per day, per unit), vega (per 1 vol point)"""
    S = F * math.exp(-r * T)
    sT = sigma * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / sT
    d2 = d1 - sT
    delta = N(d1) if typ == "CE" else N(d1) - 1
    gamma = n(d1) / (S * sT)
    t1 = -S * n(d1) * sigma / (2 * math.sqrt(T))
    theta = (t1 - r * K * math.exp(-r * T) * N(d2)) if typ == "CE" else (t1 + r * K * math.exp(-r * T) * N(-d2))
    vega = S * n(d1) * math.sqrt(T) / 100
    return {"delta": delta, "gamma": gamma, "theta": theta / 365, "vega": vega}
