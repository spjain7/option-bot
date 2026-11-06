"""NSE CASH-STOCK POSITIONAL BUY – monthly relative-strength (momentum) portfolio. BUY ONLY. ALERTS ONLY.

Validated in research (exp/strategy-program-001, research/program/eq_momentum.py, EQ-MOM-001) on official NSE cash
bhavcopies 2005-2026 (point-in-time universe incl. delisted stocks, exact corporate-action adjustment, delivery costs):
chosen on 2006-15 only, untouched 2016-26: CAGR 15.5 % vs Nifty ~11.8 % (incl. dividends) and 12.5 % for the equal-weight
liquid universe; max drawdown −31 % vs −38 % / −44 %. Weak spots: 2008-15 CAGR 2.0 % (Nifty ~4.6 %), years like 2018 −30 %.
STATUS: live-monitoring candidate (not production-approved).

Rules (identical to the research code – see tests/test_cashstock_parity in research):
  * month-end session t; eligible = 60-session median turnover >= ₹25 cr, close >= ₹50, >= 250 sessions of history
  * score = (close[t-21] / close[t-252] - 1) / stdev(daily log return, 126 sessions)
  * market filter: equal-weight index of the 100 most-traded stocks closes above its 200-session average, else hold cash
  * BUY the top 10 at the next session's open (equal weight); hold until the next month-end; names that drop out are sold
"""
import numpy as np
import pandas as pd

MIN_TURNOVER, MIN_PRICE, L, SKIP, VOLN, TOP = 25e7, 50.0, 252, 21, 126, 10
VERSION = "cash-mom-1.0 (EQ-MOM-001)"


def adjusted(P):
    """P: bhavcopy rows (date, symbol, series, isin, open, high, low, close, prevclose, volume, value) -> {key: frame}.
    Same adjustment as research/program/eq_bhav.adjusted (PREVCLOSE factor + UDiFF unadjusted-gap fix)."""
    P = P.sort_values(["date", "symbol", "series"]).drop_duplicates(["date", "symbol"], keep="last").copy()
    P["key"] = P["isin"].where(P["isin"].astype(str).str.len() > 5, P["symbol"])
    out = {}
    for k, g in P.groupby("key", sort=False):
        g = g.sort_values("date")
        if len(g) < 60:
            continue
        pc, c, o = (g[x].values.astype(float) for x in ("prevclose", "close", "open"))
        f = np.ones(len(g))
        f[1:] = np.where((c[:-1] > 0) & (pc[1:] > 0), pc[1:] / c[:-1], 1.0)
        f = np.where(np.abs(f - 1) < 0.002, 1.0, f)
        r = np.ones(len(g)); r[1:] = np.where(c[:-1] > 0, o[1:] / c[:-1], 1.0)
        f = np.where((f == 1.0) & ((r < 0.6) | (r > 1.6)), r, f)
        cum = np.r_[np.cumprod(f[::-1])[::-1][1:], 1.0]
        out[k] = pd.DataFrame(dict(time=g.date.values, open=o * cum, high=g.high.values * cum, low=g.low.values * cum,
                                   close=c * cum, volume=g.volume.values / cum, symbol=g.symbol.values))
    return out


def panels(A):
    C, T = {}, {}
    for k, d in A.items():
        s = d.symbol.iat[-1] + ("" if d.symbol.iat[-1] not in C else f"#{k[-4:]}")
        C[s] = pd.Series(d.close.values, d.time.values)
        T[s] = pd.Series((d.close * d.volume).rolling(60, min_periods=40).median().values, d.time.values)
    C = pd.concat(C, axis=1).sort_index(); T = pd.concat(T, axis=1).sort_index()
    return C, T


def market_index(C, T, top=100):
    """equal-weight daily return of the `top` stocks by trailing (previous-day) turnover – research eq_bhav.market()."""
    ret = C.pct_change(fill_method=None)
    rk = T.shift(1).rank(axis=1, ascending=False)
    m = ret.where(rk <= top).mean(axis=1).clip(-0.2, 0.2).fillna(0)
    return (1 + m).cumprod() * 1000


def rank(C, T, asof=None):
    """-> dict(asof, market_on, picks=[{symbol, score, close, ret12_1, vol}], eligible)"""
    days = C.index
    ia = len(days) - 1 if asof is None else days.get_loc(pd.Timestamp(asof))
    mk = market_index(C, T)
    on = bool(mk.iloc[ia] > mk.rolling(200).mean().iloc[ia])
    hist = C.notna().cumsum()
    el = (T.iloc[ia] >= MIN_TURNOVER) & (C.iloc[ia] >= MIN_PRICE) & (hist.iloc[ia] >= 250) & C.iloc[ia - L].notna()
    r12 = C.iloc[ia - SKIP] / C.iloc[ia - L] - 1
    vol = np.log(C / C.shift(1)).rolling(VOLN, min_periods=60).std().iloc[ia]      # as research (window ends at t)
    sc = (r12 / vol).where(el).replace([np.inf, -np.inf], np.nan).dropna().sort_values(ascending=False)
    picks = [dict(symbol=s.split("#")[0], score=float(sc[s]), close=float(C[s].iloc[ia]), ret12_1=float(r12[s]), vol=float(vol[s]))
             for s in sc.index[:TOP]] if on else []
    return dict(asof=str(days[ia].date()), market_on=on, picks=picks, eligible=int(el.sum()),
                market=float(mk.iloc[ia]), market_ma200=float(mk.rolling(200).mean().iloc[ia]))


def is_month_end(day, next_trading_day):
    return pd.Timestamp(day).month != pd.Timestamp(next_trading_day).month


def messages(res, prev_holdings, nchase=0.03):
    """Owner lifecycle: CONFIRMED SETUP (buy at next open), EXIT (dropped names), market filter note. BUY only."""
    new = [p for p in res["picks"] if p["symbol"] not in prev_holdings]
    keep = [p for p in res["picks"] if p["symbol"] in prev_holdings]
    drop = [s for s in prev_holdings if s not in {p["symbol"] for p in res["picks"]}]
    L_ = [f"📈 CASH POSITIONAL – monthly relative-strength portfolio · {res['asof']} close",
          f"Status: live-monitoring candidate ({VERSION}) · BUY only · alerts only",
          f"Market filter: {'ON – invested' if res['market_on'] else 'OFF – hold cash, no new BUY'} "
          f"(top-100 equal-weight index {res['market']:.0f} vs 200-day avg {res['market_ma200']:.0f})"]
    if new:
        L_.append("🟡 CONFIRMED SETUP – BUY at the next session's open (equal weight, 1/10 of capital each):")
        for p in new:
            L_.append(f"• {p['symbol']} · last close ₹{p['close']:,.2f} · do not chase above ₹{p['close'] * (1 + nchase):,.2f} at the open · "
                      f"12-1m return {100 * p['ret12_1']:+.0f}% · RS score {p['score']:.1f}")
    if keep:
        L_.append("✅ HOLD: " + ", ".join(p["symbol"] for p in keep))
    if drop:
        L_.append("⛔ EXIT at the next open (no longer in the top 10" + ("" if res["market_on"] else " / market filter off") + "): " + ", ".join(drop))
    if not (new or keep or drop):
        L_.append("No positions and no BUY this month.")
    L_ += ["Exit rule: monthly re-ranking (no fixed target). Holding period ~1-3 months on average.",
           "Evidence (research, after delivery costs): 2016-26 out of sample CAGR 15.5 % vs Nifty ~11.8 %, max drawdown −31 %; "
           "2008-15 only 2.0 %. Backtest, not a guarantee. Alert only – not investment advice."]
    return "\n".join(L_), [p["symbol"] for p in res["picks"]]
