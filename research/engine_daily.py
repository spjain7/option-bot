"""Daily-bar backtest engine for strategies B-I (see CRITERIA.md).

Decision at the CLOSE of day t using only data up to t  ->  order at the OPEN of day t+1.
Intraday stop on the held contract (gap through the stop -> filled at the open). Channel exit decided at a close,
filled at the next open. Rolls at the close of roll days (cost of a full round trip per roll).
P&L is computed on the back-adjusted series (identical to contract legs rolled at those closes); the trade log
also shows the actual contract prices (adjusted - offset).
"""
import numpy as np
import pandas as pd
from research.instruments import REGISTRY, trade_cost_points, mcx_ref_price


# ─────────────── indicators (each value at t uses data <= t only) ───────────────
def add_indicators(d):
    d = d.copy()
    c, h, l = d["close"], d["high"], d["low"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(20).mean()                                   # Turtle "N"
    atr14 = tr.ewm(alpha=1 / 14, adjust=False).mean()
    up, dn = h.diff(), -l.diff()
    pdm, ndm = up.where((up > dn) & (up > 0), 0.0), dn.where((dn > up) & (dn > 0), 0.0)
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr14
    ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False).mean() / atr14
    d["adx"] = (100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)).ewm(alpha=1 / 14, adjust=False).mean()
    dd = c.diff()
    u, v = dd.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(), (-dd.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + u / v.replace(0, 1e-9))
    d["sma200"] = c.rolling(200).mean()
    # ATR% must use RAW prices: back-adjusted levels distort percentages
    atrp = d["atr"] / d["raw_close"].where(d["raw_close"] > 0)
    d["atrp_pct"] = atrp.rolling(252, min_periods=126).rank(pct=True) * 100
    vol = d["volume"].astype(float) if "volume" in d else pd.Series(np.nan, index=d.index)
    d["vol_x"] = vol / vol.shift(1).rolling(20).mean()
    d["oi_up"] = d["oi"] > d["oi"].shift(5) if "oi" in d and d["oi"].notna().any() else np.nan
    return d


BASE = dict(entry=55, exit=20, stop=2.0, trend=True, rsi_block=False, vol=None, oi=False, regime=False,
            sides=(1, -1),
            # v2 options (defaults reproduce v1 exactly)
            vol_lag=False,      # volume confirmation uses the PREVIOUS day's volume ratio (no same-bar dependence)
            exit_mode="channel",  # "channel" = opposite N-day channel | "trail" = trailing stop trail_atr x ATR from best close
            trail_atr=3.0,
            chase=None,         # skip entry if the next open is already > chase x ATR beyond the signal close
            hole_block=60)      # bars blocked for new signals after a data hole (only if the frame has a "hole" column)
STRATS = {
    "B": dict(entry=20, exit=10, stop=2.0, trend=False),
    "C": dict(),
    "D": dict(rsi_block=True),
    "E": dict(vol=1.5),
    "F": dict(oi=True),
    "G": dict(regime=True),
    "H1": dict(rsi_block=True, regime=True),
    "H2": dict(vol=1.5, regime=True),
    "H3": dict(oi=True, regime=True),
    "H4": dict(rsi_block=True, vol=1.5),
    "I": dict(sides=(1,)),
}


def signals(d, p):
    hi = d["high"].shift(1).rolling(p["entry"]).max()
    lo = d["low"].shift(1).rolling(p["entry"]).min()
    c = d["close"]
    long_, short = c > hi, c < lo
    if p["trend"]:
        long_ &= c > d["sma200"]; short &= c < d["sma200"]
    if p["rsi_block"]:
        long_ &= ~(d["rsi"] > 70); short &= ~(d["rsi"] < 30)
    if p["vol"]:
        vx = d["vol_x"].shift(1) if p.get("vol_lag") else d["vol_x"]
        ok = vx >= p["vol"]
        long_ &= ok; short &= ok
    if p["oi"]:
        ok = d["oi_up"] == True                                          # noqa: E712 (NaN -> False)
        long_ &= ok; short &= ok
    if p["regime"]:
        ok = (d["adx"] >= 20) & d["atrp_pct"].between(10, 90)
        long_ &= ok; short &= ok
    s = np.where(long_, 1, np.where(short, -1, 0))
    s[d["atr"].isna().values | d["sma200"].isna().values] = 0
    if "hole" in d:                                                      # indicators are unreliable after a data hole
        h = np.where(d["hole"].values)[0]
        for k in h:
            s[k:k + p.get("hole_block", 60)] = 0
    return s


def run(name, d, overrides=None, cost_x=1.0):
    """d: continuous frame (add_indicators applied). Returns trade log DataFrame."""
    p = {**BASE, **(overrides or {})}
    s = signals(d, p)
    xo_hi = d["high"].shift(1).rolling(p["exit"]).max().values
    xo_lo = d["low"].shift(1).rolling(p["exit"]).min().values
    O, H, L, C, A = (d[k].values for k in ("open", "high", "low", "close", "atr"))
    off, roll, T = d["offset"].values, d["roll"].values, d["time"].values
    con = d["contract"].values
    proxy = bool((d["contract"] == "PROXY").all())
    hole = d["hole"].values if "hole" in d else np.zeros(len(d), bool)
    out, i, n = [], 0, len(d)
    while i < n - 1:
        side = s[i]
        if side == 0 or side not in p["sides"]:
            i += 1; continue
        j = i + 1
        if p.get("chase") and side * (O[j] - C[i]) > p["chase"] * A[i]:   # opened too far beyond the signal: no trade
            i += 1; continue
        e = O[j]; R = p["stop"] * A[i]; stop = e - side * R
        mae = mfe = 0.0; rolls = 0; k = j; x = None; why = None; best = e
        while k < n:
            if hole[k] and k > j:                                         # data missing in between: trade not valid
                k -= 1; x, why = C[k], "data_hole"; break
            if k > j and side * (O[k] - stop) <= 0:                       # gapped through the stop
                x, why = O[k], "gap_stop"; break
            lo_, hi_ = (L[k], H[k])
            mae = min(mae, side * ((lo_ if side > 0 else hi_) - e))
            mfe = max(mfe, side * ((hi_ if side > 0 else lo_) - e))
            if side * ((lo_ if side > 0 else hi_) - stop) <= 0:
                x, why = stop, "stop"; break
            if p.get("exit_mode") == "trail":
                best = max(best, C[k]) if side > 0 else min(best, C[k])
                tstop = best - side * p["trail_atr"] * A[k]
                stop = max(stop, tstop) if side > 0 else min(stop, tstop)  # only tightens, applies from next bar
            elif side * (C[k] - (xo_lo[k] if side > 0 else xo_hi[k])) < 0 and k + 1 < n:
                rolls += int(bool(roll[k]))                               # rolled at that close, exits next open
                x, why, k = O[k + 1], "channel", k + 1                    # decided at close, filled next open
                mae = min(mae, side * (x - e)); mfe = max(mfe, side * (x - e))
                break
            if roll[k]:
                rolls += 1                                                # held through a roll close
            k += 1
        if x is None:                                                     # still open at the end of data
            k = n - 1; x, why = C[k], "open_at_end"
        raw_e, raw_x = e - off[j], x - off[k]
        cpts = trade_cost_points(name, max(abs(raw_e), 1e-9), proxy, cost_x) * (1 + rolls)
        gross = side * (x - e)
        out.append(dict(instrument=name, signal_time=T[i], entry_time=T[j], exit_time=T[k], side="LONG" if side > 0 else "SHORT",
                        entry_contract=con[j], exit_contract=con[k], entry_px=round(raw_e, 2), exit_px=round(raw_x, 2),
                        entry_adj=e, exit_adj=x, entry_i=j, exit_i=k,
                        stop_px=round(stop - off[j], 2), R_pts=R, rolls=rolls, cost_pts=cpts,
                        gross_R=gross / R, net_R=(gross - cpts) / R, mae_R=mae / R, mfe_R=mfe / R,
                        exit_reason=why, valid=why != "data_hole", days=int((pd.Timestamp(T[k]) - pd.Timestamp(T[j])).days) + 1,
                        adx=d["adx"].values[i], atrp_pct=d["atrp_pct"].values[i],
                        trend_up=bool(C[i] > d["sma200"].values[i])))
        i = max(k, i + 1)                                                 # flat from bar k; may re-enter on close k
        if why == "open_at_end":
            break
    t = pd.DataFrame(out)
    if not t.empty:
        mult = REGISTRY[name]["mult"]
        # proxies: rupees = % move applied to today's MCX-equivalent price ("as if traded at today's level")
        t["pt_scale"] = (mcx_ref_price(name) / t["entry_px"].abs()) if proxy else 1.0
        t["net_pts"] = t["net_R"] * t["R_pts"]
        t["pnl_rs_1lot"] = t["net_pts"] * t["pt_scale"] * mult
        t["cost_rs_1lot"] = t["cost_pts"] * t["pt_scale"] * mult
    return t
