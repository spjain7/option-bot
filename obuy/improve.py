"""Option-BUY improvements (owner approved 29-Oct-2026: "do all improvement required").
Why: an option buyer wins only if the underlying moves FAR and FAST enough before time decay, an expensive premium and
costs eat the gain (profit ≈ delta·move + ½·gamma·move² − theta·time ± vega·ΔIV − costs). These rules are sensible
guards based on option pricing, NOT backtested (no history of option prices to test them on) – the live scorecard is the test.

  1. STRIKE      one strike in-the-money (delta ≈ 0.6) instead of ATM when it is liquid: less of the premium is time value
  2. NORMAL MOVE a normal move for the time left (daily ATR × √(minutes left / 375), positional: 1 daily ATR) must lift the
                 premium by at least the stop-loss % (reward ≥ risk on an ordinary move) – otherwise skip
  3. OI WALL     skip a CE buy when a strike between the price and that normal move has call OI ≥ 2× the bought strike's
                 OI (sellers defend it); PE mirror
  4. F&O BAN     skip stocks in today's NSE F&O ban list (new positions not allowed)
  5. TIME        no new intraday buys after 13:30 · intraday options at least 4 days from expiry
  6. EXITS       besides −30 % / +60 %: exit if after 60 minutes the premium has not gained 10 % (the move did not come),
                 or if a completed 15-min futures candle closes back across VWAP (the signal is invalid)
"""
import math
import pandas as pd

LAST_ENTRY = "13:30"
MIN_DTE_INTRADAY = 4
WALL_X = 2.0
TIME_STOP_MIN = 60
TIME_STOP_GAIN = 0.10
BAN_URL = "https://nsearchives.nseindia.com/content/fo/fo_secban.csv"


def strikes(master, name, typ, expiry):
    o = master[(master["name"] == name) & (master["exch_seg"] == "NFO") & master["instrumenttype"].isin(["OPTIDX", "OPTSTK"])
               & master["symbol"].str.endswith(typ) & (master["expiry_dt"].dt.strftime("%Y-%m-%d") == str(expiry))].copy()
    o["K"] = o["strike"] / 100
    return o.sort_values("K").reset_index(drop=True)


def itm_strike(chain, px, typ):
    """The nearest in-the-money strike (CE: below the price, PE: above) – None if there is none."""
    x = chain[chain["K"] < px] if typ == "CE" else chain[chain["K"] > px]
    if x.empty:
        return None
    r = x.iloc[-1] if typ == "CE" else x.iloc[0]
    return {"token": str(r["token"]), "symbol": r["symbol"], "K": float(r["K"]), "expiry": str(r["expiry_dt"].date()), "lot": int(r["lotsize"])}


def normal_move(daily_atr, now, mode):
    if mode == "positional":
        return float(daily_atr)
    close = now.normalize() + pd.Timedelta(hours=15, minutes=15)
    mins = max((close - now).total_seconds() / 60, 15)
    return float(daily_atr) * math.sqrt(min(mins, 375) / 375)


def projected_gain(premium, F, K, T, iv, typ, move, hold_days):
    """Premium change (fraction) if the futures move `move` points in the trade direction while `hold_days` pass, IV unchanged."""
    from greeks import price
    s = 1 if typ == "CE" else -1
    p1 = price(F + s * move, K, max(T - hold_days / 365, 0.5 / 365), iv, 0.065, typ)
    return p1 / premium - 1


def oi_wall(api, chain, px, typ, move, k_bought):
    """-> (strike, oi_ratio) of the biggest same-type OI strike between the price and the normal move if ≥ WALL_X × bought."""
    s = 1 if typ == "CE" else -1
    lo, hi = sorted([px, px + s * move])
    band = chain[(chain["K"] > lo) & (chain["K"] <= hi)] if typ == "CE" else chain[(chain["K"] >= lo) & (chain["K"] < hi)]
    toks = [str(t) for t in band["token"]] + [str(chain.loc[chain["K"] == k_bought, "token"].iloc[0])] if len(band) else []
    if not toks:
        return None
    q = api.quotes({"NFO": toks}) or {}
    base = float((q.get(toks[-1]) or {}).get("opnInterest") or 0)
    if base <= 0:
        return None
    best = None
    for t, k in zip(band["token"].astype(str), band["K"]):
        oi = float((q.get(t) or {}).get("opnInterest") or 0)
        if oi >= WALL_X * base and (best is None or oi > best[1] * base):
            best = (float(k), oi / base)
    return best


def ban_list(state, now, fetch=None):
    """Today's NSE F&O ban list, fetched once a day. None = unknown (fetch failed) – then the check is skipped and noted."""
    day = f"{now:%Y-%m-%d}"
    b = state.get("ban") or {}
    if b.get("day") == day and "names" in b:
        return b["names"]
    names = None
    try:
        if fetch is None:
            import requests
            r = requests.get(BAN_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            r.raise_for_status()
            text = r.text
        else:
            text = fetch()
        names = sorted({ln.split(",")[-1].strip().upper() for ln in text.splitlines()[1:] if ln.strip()})
    except Exception:
        names = None
    state["ban"] = {"day": day, "names": names}
    return names


def vwap_invalid(df, i, d):
    """True when the completed 15-min futures candle i closed back on the wrong side of VWAP."""
    if df is None or i is None or "vwap" not in df:
        return False
    c, v = float(df["close"].iat[i]), float(df["vwap"].iat[i])
    return (c < v) if d > 0 else (c > v)


# ─────────────── option idea for a PROVEN futures call (hanging-man SELL, liquidity-sweep SELL) ───────────────
def option_for_futures_call(api, master, name, side, fut_entry, fut_stop, fut_target, now, daily=None, hold_days=3):
    """Option to BUY alongside a triggered stock-futures call, judged on the FUTURES levels (not premium %):
    gain if the futures reach the target vs loss if they hit the stop, with time decay over `hold_days`.
    Returns a message, or None when no suitable option (reason printed)."""
    from greeks import implied_vol
    typ = "CE" if side > 0 else "PE"
    o = master[(master["name"] == name) & (master["exch_seg"] == "NFO") & (master["instrumenttype"] == "OPTSTK")
               & master["symbol"].str.endswith(typ) & (master["expiry_dt"] >= now.normalize() + pd.Timedelta(days=hold_days + 4))]
    if o.empty:
        print(f"[opt-idea] {name}: no option expiry far enough"); return None
    exp = o["expiry_dt"].min()
    chain = strikes(master, name, typ, f"{exp:%Y-%m-%d}")
    atm = chain.iloc[(chain["K"] - fut_entry).abs().argsort().iloc[0]]
    cands = [{"token": str(atm["token"]), "symbol": atm["symbol"], "K": float(atm["K"]), "lot": int(atm["lotsize"])}]
    itm = itm_strike(chain, fut_entry, typ)
    if itm and itm["token"] != cands[0]["token"]:
        cands.append(itm)
    T = max((exp - now.normalize()).days, 0.5) / 365
    best = None
    q = api.quotes({"NFO": [c["token"] for c in cands]}) or {}
    for c in cands:
        x = q.get(c["token"]) or {}
        ltp = float(x.get("ltp") or 0)
        dep = x.get("depth") or {}
        bid = float((dep.get("buy") or [{}])[0].get("price") or 0); ask = float((dep.get("sell") or [{}])[0].get("price") or 0)
        if ltp <= 0 or float(x.get("tradeVolume") or 0) <= 0 or (bid > 0 and ask > 0 and (ask - bid) / ((ask + bid) / 2) > 0.03):
            continue
        prem = ask if ask > 0 else ltp
        iv = implied_vol(ltp, fut_entry, c["K"], T, 0.065, typ)
        if not iv:
            continue
        up = projected_gain(prem, fut_entry, c["K"], T, iv, typ, abs(fut_target - fut_entry), hold_days)
        dn = projected_gain(prem, fut_entry, c["K"], T, iv, typ, -abs(fut_entry - fut_stop), hold_days)
        if best is None or up / max(-dn, 1e-9) > best["rr"]:
            best = dict(c=c, prem=prem, iv=iv, up=up, dn=dn, rr=up / max(-dn, 1e-9))
    if best is None:
        print(f"[opt-idea] {name}: no liquid {typ} near the money"); return None
    if daily is not None and len(daily) >= 12:
        from alerts.optfilter import hv20, IV_HV_MAX
        hv = hv20(daily)
        if hv and best["iv"] > IV_HV_MAX * hv:
            print(f"[opt-idea] {name}: premium expensive (IV {best['iv'] * 100:.0f}% vs {hv * 100:.0f}%)"); return None
    if best["up"] < -best["dn"]:
        print(f"[opt-idea] {name}: option pays less at the futures target ({best['up'] * 100:+.0f}%) than it loses at the stop "
              f"({best['dn'] * 100:+.0f}%) – no option idea"); return None
    c = best["c"]
    return (f"💡 OPTION IDEA – BUY {name} {c['K']:g} {typ} ({pd.Timestamp(exp):%d-%b}) at ~₹{best['prem']:,.2f} · lot {c['lot']:,}\n"
            f"• If the futures reach the target: ≈ {best['up'] * 100:+.0f}% · if they hit the stop: ≈ {best['dn'] * 100:+.0f}% "
            f"(IV {best['iv'] * 100:.0f}%, {hold_days} days of time decay included)\n"
            f"• Exit the option when the FUTURES call exits (stop / target / time) – not on a premium %.\n"
            "Option buying can lose the whole premium. Alert only – not investment advice.")
