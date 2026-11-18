"""NSE CASH SWING / POSITIONAL BUY calls on WEEKLY and MONTHLY candles + NSE DELIVERY % (live from 18-Nov-2026 on the owner's
instruction "yes and live best setup"). BUY ONLY. ALERTS ONLY – never places orders. Separate from cashstock/breakout.py
(daily calls), MCX, options and stock / index futures.

Research: exp/cash-equity-engine, research/cashq (cash_combo.py, deliv_study.py, nse_bo_cash.py), official NSE bhavcopies
+ NSE security-wise delivery files 2005-26, delisted stocks included, delivery costs 0.393 %, signal at the candle close,
entry next session's open. Universe: 60-session median turnover >= ₹5 cr, close >= ₹50, >= 250 sessions.
  W_RETEST_DP  weekly: a 20-week breakout in the last 2-15 weeks, the week dips back to within 2 % of the breakout level,
               closes above it and green; that week's delivery % >= 50; market (EW top-100 index) above its 200-day
               average; 6-month (26-week) return in the top 20 % of the universe.  SL 3 weekly ATR, target 3R, max 26 weeks.
               Backtest 412 calls, 54 % won, +9.6 % avg (2005-14 51 % / +5.9 %, 2015-19 55 % / +8.1 %, 2020-26 55 % / +11.1 %)
  W_HI52_DP    weekly close at a 52-week closing high (first in 3 weeks), that week's delivery % >= 1.2x its 10-week
               average. SL 2 weekly ATR; book HALF at 1R and move the stop to cost; rest at 3R; max 26 weeks.
               Backtest 746 calls, 61 % won, +3.7 % avg (2005-14 64 % / +4.1 %, 2015-19 54 % / +0.7 %, 2020-26 62 % / +4.6 %)
  M_ATH_CONF   monthly close at an all-time closing high (>= 24 months listed), market above its 200-day average, and a
               confirmation on the signal day: (close <= 30 % above EMA200 and 20-day return <= 5 %) or (ADX >= 30 and
               close <= 20 % above EMA200). SL 2 monthly ATR, target 3R, max 12 months.
               Backtest 369 calls, 57 % won, +12.8 % avg (2005-14 65 % / +17.8 %, 2015-19 55 % / +8.0 %, 2020-26 56 % / +13.1 %)
  LOW_DP_WARN  info only: delivery % <= 20 on volume >= 3x (speculative) – such stocks lagged the market by ~1.1 % over the
               next 20 sessions in every period. Not a trade.
Calls are sent only for COMPLETED candles: weekly on the last session of the week (run on Friday or later), monthly on the
last session of the month. One open call per stock across these setups. Tracking uses daily bars (stop / target / time exit).
CASHSTOCK_SWING_SETUPS (default all) switches setups. The monthly setup needs the full bhavcopy history (restored by the
workflow); with less than 4 years loaded it is skipped."""
import datetime as dt
import io
import os
import zipfile
import numpy as np
import pandas as pd
import requests

MIN_TURNOVER, MIN_PRICE, MIN_HIST, QTY = 5e7, 50.0, 250, 100
VERSION = "cash-swing-0.1 (weekly retest+delivery, weekly 52w+delivery, monthly ATH confirmed)"
WARN = "Alert only – no auto trade. Not investment advice."
LINE = "━━━━━━━━━━━━━━"
SETUPS = ("M_ATH_CONF", "W_RETEST_DP", "W_HI52_DP")            # call priority when a stock fires more than one
SPEC = {  # stop ATR, target R, half at 1R, max candles, candle
    "W_RETEST_DP": dict(k=3.0, r=3.0, half=False, maxc=26, tf="W"),
    "W_HI52_DP": dict(k=2.0, r=3.0, half=True, maxc=26, tf="W"),
    "M_ATH_CONF": dict(k=2.0, r=3.0, half=False, maxc=12, tf="M")}
TITLE = {"W_RETEST_DP": "weekly breakout-retest + delivery ≥ 50 % (strong stock, market up)",
         "W_HI52_DP": "weekly 52-week high + rising delivery",
         "M_ATH_CONF": "monthly all-time-high breakout (confirmed)"}
RECORD = {"W_RETEST_DP": "412 calls 2005-26, 54 % won, +9.6 % avg per call (2005-14 +5.9 %, 2015-19 +8.1 %, 2020-26 +11.1 %)",
          "W_HI52_DP": "746 calls 2005-26, 61 % won, +3.7 % avg per call (2005-14 +4.1 %, 2015-19 +0.7 %, 2020-26 +4.6 %)",
          "M_ATH_CONF": "369 calls 2005-26, 57 % won, +12.8 % avg per call (2005-14 +17.8 %, 2015-19 +8.0 %, 2020-26 +13.1 %)"}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


# ---------------------------------------------------------------- indicators (research/cashq/ind.py)
def _w(x, n):
    return x.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def atr(h, l, c, n=14):
    pc = c.shift(1)
    return _w(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())), n)


def adx(h, l, c, n=14):
    up, dn = h.diff(), -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0); mdm = dn.where((dn > up) & (dn > 0), 0.0)
    a = atr(h, l, c, n)
    pdi, mdi = 100 * _w(pdm, n) / a, 100 * _w(mdm, n) / a
    return _w(100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan), n)


def first(x, n=3):
    x = x.fillna(False).astype(bool)
    return x & ~x.shift(1).rolling(n, min_periods=1).max().fillna(0).astype(bool)


# ---------------------------------------------------------------- data
def daily(W):
    """W: cashstock.breakout.wide(A) -> adds value (₹, split-invariant), elig and turnover."""
    c, v = W["close"], W["volume"]
    F = dict(W)
    F["value"] = c * v
    to60 = F["value"].rolling(60, min_periods=40).median().shift(1)
    F["turnover_cr"] = to60 / 1e7
    F["elig"] = (to60 >= MIN_TURNOVER) & (c >= MIN_PRICE) & (c.notna().cumsum() >= MIN_HIST) & c.notna()
    return F


def bars(F, rule):
    """weekly ('W', weeks ending Friday) or monthly ('M') candles; index = the candle's last session."""
    idx = F["close"].index
    g = idx.to_period("W-FRI" if rule == "W" else "M")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "value": "sum"}
    out = {f: F[f].groupby(g).agg(agg[f]) for f in agg}
    last = pd.Series(idx, index=idx).groupby(g).last()
    for f in out:
        out[f].index = pd.DatetimeIndex(last.values)
    out["elig"] = F["elig"].groupby(g).last().set_axis(out["close"].index).astype(bool)
    out["symbol"] = F["symbol"]
    return out


def market_on(F, top=100, ma=200):
    """EW index of the `top` stocks by previous-day 60-session median turnover (research eq_bhav.market) above its MA."""
    c = F["close"]; ret = c.pct_change(fill_method=None)
    to = F["value"].rolling(60, min_periods=20).median().shift(1)
    rk = to.rank(axis=1, ascending=False)
    m = ret.where(rk <= top).mean(axis=1).clip(-0.2, 0.2).fillna(0)
    ix = (1 + m).cumprod() * 1000
    return ix > ix.rolling(ma).mean()


def deliv_url(d):
    return f"https://nsearchives.nseindia.com/archives/equities/mto/MTO_{d:%d%m%Y}.DAT"


def parse_mto(text, d):
    rows = [x.split(",") for x in text.splitlines() if x.startswith("20,")]
    df = pd.DataFrame([x[:7] for x in rows], columns=["rt", "sr", "symbol", "series", "traded_qty", "deliv_qty", "deliv_pct"])
    df = df[df.series.str.strip() == "EQ"]
    return pd.DataFrame({"date": pd.Timestamp(d), "symbol": df.symbol.str.strip(), "deliv_pct": pd.to_numeric(df.deliv_pct, errors="coerce")})


def fetch_delivery(days, cache=None):
    """NSE security-wise delivery position for `days` -> long frame (date, symbol, deliv_pct). Cached as csv.gz per day."""
    out = []
    for d in days:
        f = cache / f"MTO_{d:%Y%m%d}.csv.gz" if cache else None
        if f is not None and f.exists():
            out.append(pd.read_csv(f, parse_dates=["date"])); continue
        try:
            r = requests.get(deliv_url(d), headers=UA, timeout=30)
            if r.status_code == 200 and r.text.startswith("Security Wise"):
                x = parse_mto(r.text, d); out.append(x)
                if f is not None:
                    f.parent.mkdir(parents=True, exist_ok=True); x.to_csv(f, index=False)
        except Exception as e:  # noqa: BLE001
            print(f"::warning::delivery {d:%Y-%m-%d}: {type(e).__name__}")
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["date", "symbol", "deliv_pct"])


def deliv_panel(F, X):
    """long delivery frame -> wide delivery % aligned with the daily panel (columns = security keys, matched by symbol)."""
    k_of = {}
    for k, s in F["symbol"].items():
        k_of.setdefault(s, k)
    X = X[X.symbol.isin(k_of)].copy(); X["key"] = X.symbol.map(k_of)
    dp = X.pivot_table(index="date", columns="key", values="deliv_pct", aggfunc="last")
    return dp.reindex(index=F["close"].index, columns=F["close"].columns).clip(0, 100)


def fo_symbols(day=None):
    """stock-futures symbols from the latest NSE F&O UDiFF bhavcopy (up to 7 days back); empty set if unavailable."""
    d = pd.Timestamp(day or dt.date.today())
    for i in range(8):
        x = d - pd.Timedelta(days=i)
        if x.weekday() >= 5:
            continue
        try:
            r = requests.get(f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{x:%Y%m%d}_F_0000.csv.zip", headers=UA, timeout=60)
            if r.status_code == 200 and r.content[:2] == b"PK":
                z = zipfile.ZipFile(io.BytesIO(r.content)); t = pd.read_csv(z.open(z.namelist()[0]), usecols=["FinInstrmTp", "TckrSymb"])
                return set(t[t.FinInstrmTp == "STF"].TckrSymb.astype(str).str.strip())
        except Exception:  # noqa: BLE001
            pass
    return set()


# ---------------------------------------------------------------- signals (identical to research/cashq/cash_combo.entries)
def weekly_signals(Wk, mkt_d, dpw):
    o, h, l, c = (Wk[x] for x in ("open", "high", "low", "close"))
    e = Wk["elig"].reindex_like(c).fillna(False).astype(bool)
    a = atr(h, l, c, 14)
    mk = mkt_d.reindex(c.index, method="ffill").fillna(False)
    MK = pd.DataFrame(np.repeat(mk.values[:, None], c.shape[1], 1), index=c.index, columns=c.columns)
    rs = (c / c.shift(26) - 1).where(e).rank(axis=1, pct=True)
    lvl_at = h.shift(1).rolling(20).max(); bo = first(c > lvl_at)
    lvl = lvl_at.where(bo).ffill(limit=15)
    recent = bo.shift(2).rolling(14, min_periods=1).max().fillna(0).astype(bool)
    retest = first(recent & (l <= lvl * 1.02) & (c > lvl) & (c > o), 5)
    dpx = dpw / dpw.rolling(10, min_periods=8).mean().shift(1)
    hi52 = first(c >= c.rolling(52, min_periods=int(52 * .9)).max())
    S = {"W_RETEST_DP": retest & (dpw >= 50) & MK & (rs >= .8) & e, "W_HI52_DP": hi52 & (dpx >= 1.2) & e}
    info = dict(atr=a, rs=rs, dp=dpw, dpx=dpx, lvl=lvl)
    return S, info


def monthly_signals(Mo, mkt_d, F):
    c = Mo["close"]; h, l = Mo["high"], Mo["low"]
    e = Mo["elig"].reindex_like(c).fillna(False).astype(bool)
    a = atr(h, l, c, 14)
    ath = (c >= c.cummax()) & (c.notna().cumsum() >= 24)
    s = first(ath)
    mk = mkt_d.reindex(c.index, method="ffill").fillna(False)
    MK = pd.DataFrame(np.repeat(mk.values[:, None], c.shape[1], 1), index=c.index, columns=c.columns)
    dc, dh, dl = F["close"], F["high"], F["low"]
    ext = (dc / dc.ewm(span=200, adjust=False, min_periods=200).mean() - 1).reindex(c.index)
    r20 = (dc / dc.shift(20) - 1).reindex(c.index)
    ad = adx(dh, dl, dc, 14).reindex(c.index)
    conf = ((ext <= .30) & (r20 <= .05)) | ((ad >= 30) & (ext <= .20))
    return {"M_ATH_CONF": s & MK & conf & e}, dict(atr=a, ext=ext, r20=r20, adx=ad)


def complete(last, today, rule):
    """True when the candle containing `last` is finished: weekly from the Friday of that week, monthly on the month's last
    weekday (or later)."""
    last, today = pd.Timestamp(last), pd.Timestamp(today)
    if rule == "W":
        fri = last + pd.Timedelta(days=4 - last.weekday())
        return today.normalize() >= fri.normalize()
    me = last + pd.offsets.MonthEnd(0)
    lwd = me - pd.Timedelta(days=max(0, me.weekday() - 4))
    return today.normalize() >= lwd.normalize()


# ---------------------------------------------------------------- messages
def _f(x):
    return f"{x:,.2f}"


def call_msgs(c):
    sp = SPEC[c["setup"]]; risk = sp["k"] * c["atr"]; ref = c["close"]; unit = "week" if sp["tf"] == "W" else "month"
    seg = c.get("segment") or "segment unknown"
    tgt = (f"T1 ~{_f(ref + risk)} (1R) → book HALF, move SL to cost · T2 ~{_f(ref + sp['r'] * risk)} ({sp['r']:g}R)" if sp["half"]
           else f"~{_f(ref + sp['r'] * risk)} ({sp['r']:g}R)")
    card = "\n".join([
        f"🟢 BUY  {c['symbol']} (NSE cash · {seg})  ·  {'Swing (weekly)' if sp['tf'] == 'W' else 'Positional (monthly)'} · 🧪 EXPERIMENTAL",
        LINE,
        f"Setup   : {TITLE[c['setup']]}",
        f"Entry   : next session's open (reference {unit} close {_f(ref)})",
        f"SL      : ~{_f(ref - risk)}  ({sp['k']:g} {unit}ly ATR = {_f(risk)} below the actual entry – exact level sent after the open)",
        f"Target  : {tgt}",
        f"Time    : exit at the close of {unit} {sp['maxc']} if neither SL nor target is hit",
        f"Qty     : {QTY} shares ≈ ₹{QTY * ref:,.0f} · risk ≈ ₹{QTY * risk:,.0f} ({100 * risk / ref:.1f} %) · delivery (CNC)"])
    why = [f"📌 WHY – {c['symbol']} ({TITLE[c['setup']]})", LINE]
    if c["setup"] == "W_RETEST_DP":
        why += [f"• Chart   : week to {pd.Timestamp(c['day']):%d-%b} dipped to {_f(c['low'])} near the 20-week breakout level {_f(c['lvl'])} and closed above it, green",
                f"• Delivery: {c['dp']:.0f} % of the week's volume taken for delivery (needs ≥ 50 %)",
                f"• Strength: 6-month return better than {100 * c['rs']:.0f} % of stocks · market above its 200-day average"]
    elif c["setup"] == "W_HI52_DP":
        why += [f"• Chart   : week to {pd.Timestamp(c['day']):%d-%b} closed at a 52-week high {_f(ref)}",
                f"• Delivery: {c['dp']:.0f} % this week = {c['dpx']:.1f}× its 10-week average (needs ≥ 1.2×)"]
    else:
        why += [f"• Chart   : {pd.Timestamp(c['day']):%b-%Y} closed at an ALL-TIME high {_f(ref)} · market above its 200-day average",
                f"• Confirm : {c['conf']}"]
    why += [f"• Liquidity: ₹{c['turnover_cr']:.0f} cr a day (60-day median)",
            f"• Record  : BACKTEST ONLY (NSE 2005-26, after costs) – {RECORD[c['setup']]}. No live record yet.", WARN]
    return [card, "\n".join(why)]


# ---------------------------------------------------------------- one evening run
def _row(F, key, day):
    if key not in F["close"].columns or pd.Timestamp(day) not in F["close"].index:
        return None
    i = F["close"].index.get_loc(pd.Timestamp(day))
    v = [float(F[f][key].iloc[i]) for f in ("open", "high", "low", "close")]
    return None if not np.isfinite(v[0]) else v


def track(st, F, msgs, today=None):
    today = pd.Timestamp(today or dt.date.today())
    idx = F["close"].index
    keep = []
    for p in st["pending"]:                                     # entries
        after = idx[idx > pd.Timestamp(p["day"])]
        if not len(after):
            keep.append(p); continue
        r = _row(F, p["key"], after[0])
        if r is None:
            msgs.append(f"⛔ CANCELLED – {p['symbol']} BUY ({TITLE[p['setup']]}): no trade on {after[0]:%d-%b}. {WARN}"); continue
        sp = SPEC[p["setup"]]; o = r[0]; risk = sp["k"] * p["atr"]
        rec = dict(p, entry=round(o, 2), entry_day=str(after[0].date()), stop=round(o - risk, 2), risk=round(risk, 2),
                   target=round(o + sp["r"] * risk, 2), t1=round(o + risk, 2), half_done=False, hi=round(o, 2), lo=round(o, 2),
                   checked=str(pd.Timestamp(p["day"]).date()), version=VERSION)
        st["open"].append(rec)
        tg = f"T1 {_f(rec['t1'])} (book half, SL to cost) · T2 {_f(rec['target'])}" if sp["half"] else f"target {_f(rec['target'])}"
        msgs.append(f"⚡ ENTRY – {p['symbol']} BUY ({TITLE[p['setup']]}) filled at the open {_f(o)} on {after[0]:%d-%b}\n"
                    f"SL {_f(rec['stop'])} · {tg} · max {sp['maxc']} {'weeks' if sp['tf'] == 'W' else 'months'} · "
                    f"risk ₹{QTY * risk:,.0f} per {QTY} shares. {WARN}")
    st["pending"] = keep
    still = []
    for r in st["open"]:
        sp = SPEC[r["setup"]]; done = None
        per = "W-FRI" if sp["tf"] == "W" else "M"
        p0 = pd.Timestamp(r["entry_day"]).to_period(per)
        for d in idx[idx > pd.Timestamp(r["checked"])]:
            b = _row(F, r["key"], d)
            if b is None:
                continue
            o, h, l, c = b; r["checked"] = str(d.date())
            first_day = str(d.date()) == r["entry_day"]
            r["hi"], r["lo"] = round(max(r["hi"], h), 2), round(min(r["lo"], l), 2)
            if not first_day and o <= r["stop"]:
                done = (o, d, "stop-loss (gap below the stop at the open)" if not r["half_done"] else "stop at cost (gap)"); break
            if l <= r["stop"]:
                done = (r["stop"], d, "stop-loss" if not r["half_done"] else "rest stopped at cost"); break
            if sp["half"] and not r["half_done"] and h >= r["t1"]:
                r["half_done"] = True; r["stop"] = max(r["stop"], r["entry"])
                msgs.append(f"🎯 T1 (1R) reached – {r['symbol']} BUY ({TITLE[r['setup']]}): high {_f(h)} ≥ {_f(r['t1'])} on {d:%d-%b}. "
                            f"Book HALF, stop for the rest moved to cost {_f(r['entry'])}; T2 {_f(r['target'])}. {WARN}")
            if h >= r["target"]:
                done = (max(o, r["target"]) if not first_day else r["target"], d, f"target {sp['r']:g}R"); break
            n = (d.to_period(per) - p0).n + 1
            i = idx.get_loc(d)
            last_of_candle = (idx[i + 1].to_period(per) != d.to_period(per)) if i + 1 < len(idx) else complete(d, today, sp["tf"])
            if n > sp["maxc"] or (n == sp["maxc"] and last_of_candle):
                done = (c, d, f"time exit ({sp['maxc']} {'weeks' if sp['tf'] == 'W' else 'months'})"); break
        if done:
            px, d, why = done
            g = (px - r["entry"]) / r["risk"]
            R = 0.5 + 0.5 * g if r["half_done"] else g
            pnl = R * r["risk"] * QTY
            r.update(exit=round(px, 2), exit_day=str(d.date()), exit_reason=why, R=round(R, 3), pnl_100=round(pnl))
            st["closed"] = (st["closed"] + [r])[-400:]
            msgs.append(f"{'✅' if pnl > 0 else '❌'} EXIT – {r['symbol']} BUY ({TITLE[r['setup']]}) at {_f(px)} on {d:%d-%b}: {why}\n"
                        f"Entry {_f(r['entry'])} · {R:+.2f}R{' (half booked at 1R)' if r['half_done'] else ''} · ₹{pnl:+,.0f} per {QTY} "
                        f"shares before costs · high {_f(r['hi'])} / low {_f(r['lo'])} after entry. {WARN}")
        else:
            still.append(r)
    st["open"] = still


def new_calls(st, F, cands, msgs):
    held = {r["key"] for r in st["open"]} | {p["key"] for p in st["pending"]}
    on = [x.strip() for x in os.getenv("CASHSTOCK_SWING_SETUPS", ",".join(SETUPS)).split(",") if x.strip() in SETUPS]
    for setup in [s for s in SETUPS if s in on]:
        for c in cands.get(setup, []):
            sid = f"{c['key']}|{c['day']}|{setup}"
            if sid in st["seen"] or c["key"] in held:
                continue
            st["seen"] = (st["seen"] + [sid])[-3000:]
            st["pending"].append(c); held.add(c["key"])
            msgs.extend(call_msgs(c))


def candidates(F, today, dp, fo=None, full=False):
    """signals of completed candles that end on the last loaded session -> {setup: [call dicts]}"""
    last = F["close"].index[-1]; out = {}
    mkt = market_on(F)
    fo = fo or set()
    seg = (lambda s: ("F&O" if s in fo else "cash-only")) if fo else (lambda s: None)
    def base(k, setup, day, close, a):
        return dict(key=k, setup=setup, symbol=F["symbol"][k], day=str(pd.Timestamp(day).date()), close=round(close, 2), atr=round(a, 2),
                    turnover_cr=round(float(F["turnover_cr"][k].iloc[-1]), 1), segment=seg(F["symbol"][k]))
    if complete(last, today, "W"):
        Wk = bars(F, "W"); g = F["close"].index.to_period("W-FRI")
        dval = (dp / 100 * F["value"]).groupby(g).sum(min_count=1).set_axis(Wk["close"].index)
        val = F["value"].where(dp.notna()).groupby(g).sum(min_count=1).set_axis(Wk["close"].index)
        dpw = 100 * dval / val.replace(0, np.nan)
        S, info = weekly_signals(Wk, mkt, dpw)
        i = len(Wk["close"].index) - 1
        if Wk["close"].index[i] == last:
            for setup, s in S.items():
                row = s.iloc[i].fillna(False).astype(bool); L = []
                for k in row.index[row.values]:
                    a = float(info["atr"][k].iloc[i])
                    if not a > 0:
                        continue
                    x = base(k, setup, last, float(Wk["close"][k].iloc[i]), a)
                    x.update(low=round(float(Wk["low"][k].iloc[i]), 2), lvl=round(float(info["lvl"][k].iloc[i]), 2) if setup == "W_RETEST_DP" else None,
                             dp=round(float(info["dp"][k].iloc[i]), 1), dpx=round(float(info["dpx"][k].iloc[i]), 2), rs=round(float(info["rs"][k].iloc[i]), 3))
                    L.append(x)
                out[setup] = sorted(L, key=lambda r: -r["dp"])
    if full and complete(last, today, "M"):
        Mo = bars(F, "M"); S, info = monthly_signals(Mo, mkt, F)
        i = len(Mo["close"].index) - 1
        if Mo["close"].index[i] == last:
            row = S["M_ATH_CONF"].iloc[i].fillna(False).astype(bool); L = []
            for k in row.index[row.values]:
                a = float(info["atr"][k].iloc[i])
                if not a > 0:
                    continue
                x = base(k, "M_ATH_CONF", last, float(Mo["close"][k].iloc[i]), a)
                ex, r20, ad = (float(info[f][k].iloc[i]) for f in ("ext", "r20", "adx"))
                cs = []
                if ex <= .30 and r20 <= .05:
                    cs.append(f"not extended ({100 * ex:.0f} % above EMA200) + no run-up (20-day {100 * r20:+.1f} %)")
                if ad >= 30 and ex <= .20:
                    cs.append(f"strong trend ADX {ad:.0f} + not extended ({100 * ex:.0f} % above EMA200)")
                x["conf"] = " · ".join(cs); L.append(x)
            out["M_ATH_CONF"] = L
    return out


def low_dp_warning(F, dp, msgs, st):
    """info: stocks with delivery <= 20 % on volume >= 3x today (speculative spikes)."""
    last = F["close"].index[-1]
    if st.get("lowdp_day") == str(last.date()) or last not in dp.index:
        return
    v = F["volume"]; vx = (v / v.rolling(20).mean().shift(1)).iloc[-1]
    m = (dp.iloc[-1] <= 20) & (vx >= 3) & F["elig"].iloc[-1]
    ks = list(m.index[m.fillna(False).values])
    st["lowdp_day"] = str(last.date())
    if not ks:
        return
    ks = sorted(ks, key=lambda k: -float(vx[k]))[:12]
    names = ", ".join(f"{F['symbol'][k]} ({float(dp.iloc[-1][k]):.0f} % deliv, {float(vx[k]):.0f}× vol)" for k in ks)
    msgs.append(f"⚠️ LOW-DELIVERY VOLUME SPIKES {last:%d-%b} (info only – NOT a trade): {names}.\nHeavy volume but ≤ 20 % taken for "
                "delivery = mostly intraday / speculative. Backtest 2005-26: such stocks lagged the market by ~1.1 % over the next "
                f"20 sessions in every period – avoid chasing. {WARN}")


def step(st, F, today, dp, msgs, fo=None, full=False):
    for k in ("pending", "open", "closed", "seen"):
        st.setdefault(k, [])
    track(st, F, msgs, today)
    cands = candidates(F, today, dp, fo=fo, full=full)
    st["last_candidates"] = {s: [c["symbol"] for c in L] for s, L in cands.items()}
    new_calls(st, F, cands, msgs)
    if "LOW_DP_WARN" in os.getenv("CASHSTOCK_SWING_SETUPS", "LOW_DP_WARN"):
        low_dp_warning(F, dp, msgs, st)
    st["asof"] = str(F["close"].index[-1].date())
    return st
