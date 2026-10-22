"""STRAT-SEARCH-001 – disciplined search for a strategy that survives costs and an untouched hold-out.

  python -m research.search.strategy_search      -> research/search/results/*.json/.csv + REPORT.md

Universe: CRUDEOIL, NATURALGAS, GOLD, SILVER, COPPER, ZINC, ALUMINIUM, NIFTY, BANKNIFTY futures (real Angel candles,
front-month stitched). Timeframes: 1h, 3h, daily (built from 1h, Jul-2022 →) and 15m (CRUDEOIL only, Oct-2020 →).
Strategies: 10 well-known rule sets with TEXTBOOK parameters only – nothing is tuned (see REGISTRY in this file).
Execution: signal on a closed candle, entry at the NEXT candle's open, ATR stop checked first inside every candle,
gap through stop fills at the open, full MCX/NSE charges + slippage (research/instruments), no entries on a contract-
switch day and every trade closed before the switch (no roll gap in P&L).
Protocol (pre-registered, research/search/REGISTRY.md):
  design period  : everything before 2024-07-01  -> a strategy×timeframe is SHORTLISTED only if pooled over the
                   universe: ≥ 60 trades, expectancy ≥ +0.10R, PF ≥ 1.20, bootstrap p1 > 0 (stricter than p5 because
                   ~40 combinations are tested), still > 0 at 2× costs, and positive in ≥ 60% of instruments with ≥ 5 trades.
  hold-out       : 2024-07-01 → today, looked at ONLY for shortlisted combinations. PASS needs ≥ 40 trades,
                   expectancy ≥ +0.05R, PF ≥ 1.10, > 0 at 2× costs.
Nothing is deployed automatically.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research import instruments as INS  # noqa: E402
from crude import indicators as I, data as CD  # noqa: E402
from alerts import stats as ST, signals as SG  # noqa: E402

OUT = ROOT / "research" / "search" / "results"
SPLIT = pd.Timestamp("2024-07-01")
NAMES = [("MCX", n) for n in ("CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM")] + \
        [("NFO", "NIFTY"), ("NFO", "BANKNIFTY")]
MAX_HOLD = {"15m": 32, "1h": 40, "3h": 30, "1d": 40}


# ─────────────── data ───────────────
def load(exch, name, iv):
    f = ST.front_file(exch, name, iv)
    if f is None or not f.exists():
        return None
    d = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]]
    return d.sort_values("time").drop_duplicates("time").iloc[:-1].reset_index(drop=True)


def daily_from(h):
    g = h.groupby(h["time"].dt.normalize())
    return g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                 close=("close", "last"), volume=("volume", "sum")).reset_index(drop=True)


def nfo_expiry(y, m):
    last = pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)
    wd = 3 if pd.Timestamp(y, m, 1) < pd.Timestamp("2025-09-01") else 1        # Thursday, Tuesday from Sep-2025
    while last.weekday() != wd:
        last -= pd.Timedelta(days=1)
    return last


def switch_days(name, exch, d):
    """Trading day on which the stitched series moves to the next contract (first session after the expiry)."""
    days = pd.Series(pd.unique(d["time"].dt.normalize()))
    out = set()
    if name == "CRUDEOIL" or exch == "NFO":
        for y in range(days.min().year, days.max().year + 1):
            for m in range(1, 13):
                e = CD.crude_expiry(y, m) if name == "CRUDEOIL" else nfo_expiry(y, m)
                nxt = days[days > e]
                if len(nxt) and (nxt.iloc[0] - e).days <= 7:
                    out.add(nxt.iloc[0])
    else:
        from research.roll_adjust import detect_rolls
        dd = daily_from(d)
        out = {dd.at[i, "time"].normalize() for i in detect_rolls(dd, name)}
    return out


# ─────────────── strategies (textbook parameters, NOT tuned) ───────────────
def supertrend(df, n=10, k=3.0):
    a = I.atr(df, n).values
    hl2 = ((df["high"] + df["low"]) / 2).values
    up, dn = hl2 + k * a, hl2 - k * a
    c = df["close"].values
    trend = np.ones(len(df))
    fu, fl = up.copy(), dn.copy()
    for i in range(1, len(df)):
        fu[i] = up[i] if (up[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = dn[i] if (dn[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        trend[i] = 1 if c[i] > fu[i - 1] else -1 if c[i] < fl[i - 1] else trend[i - 1]
    return trend


def signals(df, strat):
    """Returns (entry array: +1/-1/0 decided at the close of each candle, exit function(i, side) -> bool, stop ATR mult,
    target R or None)."""
    c, h, l = df["close"], df["high"], df["low"]
    n = len(df)
    e = lambda s: I.ema(c, s)
    ent = np.zeros(n)
    if strat == "donchian_20_10":                       # Turtle-style channel breakout
        up, dn = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
        x_up, x_dn = l.shift(1).rolling(10).min(), h.shift(1).rolling(10).max()
        ent[(c > up).values] = 1; ent[(c < dn).values] = -1
        ex = lambda i, s: (c.iat[i] < x_up.iat[i]) if s > 0 else (c.iat[i] > x_dn.iat[i])
        return ent, ex, 2.0, None
    if strat == "ema_20_50_adx":
        f, s_, ad = e(20), e(50), I.adx(df)
        cu = (f > s_) & (f.shift(1) <= s_.shift(1)); cd = (f < s_) & (f.shift(1) >= s_.shift(1))
        ent[(cu & (ad > 20)).values] = 1; ent[(cd & (ad > 20)).values] = -1
        ex = lambda i, s: (f.iat[i] < s_.iat[i]) if s > 0 else (f.iat[i] > s_.iat[i])
        return ent, ex, 2.0, None
    if strat == "supertrend_10_3":
        t = supertrend(df)
        ent[1:][(t[1:] == 1) & (t[:-1] == -1)] = 1; ent[1:][(t[1:] == -1) & (t[:-1] == 1)] = -1
        ex = lambda i, s: t[i] != s
        return ent, ex, 3.0, None
    if strat == "rsi2_connors":                          # mean reversion in the direction of the 200 EMA
        r2, e200, e5 = I.rsi(c, 2), e(200), e(5)
        ent[((r2 < 10) & (c > e200)).values] = 1; ent[((r2 > 90) & (c < e200)).values] = -1
        ex = lambda i, s: (c.iat[i] > e5.iat[i]) if s > 0 else (c.iat[i] < e5.iat[i])
        return ent, ex, 2.5, None
    if strat == "bollinger_mr_trend":
        m, sd, e200 = c.rolling(20).mean(), c.rolling(20).std(), e(200)
        ent[((c < m - 2 * sd) & (c > e200)).values] = 1; ent[((c > m + 2 * sd) & (c < e200)).values] = -1
        ex = lambda i, s: (c.iat[i] > m.iat[i]) if s > 0 else (c.iat[i] < m.iat[i])
        return ent, ex, 2.0, None
    if strat == "macd_zero_trend":
        macd = e(12) - e(26); sig = I.ema(macd, 9); hist = macd - sig; e200 = e(200)
        cu = (hist > 0) & (hist.shift(1) <= 0); cd = (hist < 0) & (hist.shift(1) >= 0)
        ent[(cu & (c > e200)).values] = 1; ent[(cd & (c < e200)).values] = -1
        ex = lambda i, s: (hist.iat[i] < 0) if s > 0 else (hist.iat[i] > 0)
        return ent, ex, 2.0, None
    if strat == "trend_pullback_rsi":                    # buy the dip in an uptrend: RSI(14) back above 40
        r, e50, e200 = I.rsi(c, 14), e(50), e(200)
        upt, dnt = (c > e50) & (e50 > e200), (c < e50) & (e50 < e200)
        ent[(upt & (r > 40) & (r.shift(1) <= 40)).values] = 1; ent[(dnt & (r < 60) & (r.shift(1) >= 60)).values] = -1
        ex = lambda i, s: (c.iat[i] < e50.iat[i]) if s > 0 else (c.iat[i] > e50.iat[i])
        return ent, ex, 2.0, 2.5
    if strat == "inside_bar_trend":                      # inside bar, then close beyond the mother bar with the trend
        e50 = e(50)
        inside = (h.shift(1) < h.shift(2)) & (l.shift(1) > l.shift(2))
        ent[(inside & (c > h.shift(2)) & (c > e50)).values] = 1; ent[(inside & (c < l.shift(2)) & (c < e50)).values] = -1
        ex = lambda i, s: False
        return ent, ex, 1.5, 2.0
    if strat == "rsi_reversal_live":                     # the current alert rule (incl. quality layer) for reference
        return None, None, None, None
    if strat == "orb_30m":                               # crude 15m only: opening range 09:00-09:30
        t = df["time"]
        day = t.dt.normalize()
        rng = df[(t.dt.hour == 9) & (t.dt.minute < 30)].groupby(day[(t.dt.hour == 9) & (t.dt.minute < 30)]).agg(hi=("high", "max"), lo=("low", "min"))
        hi, lo = day.map(rng["hi"]), day.map(rng["lo"])
        window = (t.dt.hour * 60 + t.dt.minute >= 570) & (t.dt.hour < 13)
        first = lambda cond: cond & ~cond.groupby(day).cumsum().shift(1).fillna(0).astype(bool)
        lu = first(window & (c > hi)); ld = first(window & (c < lo))
        ent[lu.values] = 1; ent[ld.values] = -1
        ex = lambda i, s: False
        return ent, ex, None, 2.0
    raise ValueError(strat)


STRATS = ["donchian_20_10", "ema_20_50_adx", "supertrend_10_3", "rsi2_connors", "bollinger_mr_trend", "macd_zero_trend",
          "trend_pullback_rsi", "inside_bar_trend", "orb_30m"]


def backtest(df, strat, name, exch, tf, sw, cost_x=1.0):
    df = df.reset_index(drop=True)
    ent, ex, stop_k, tgt = signals(df, strat)
    a = I.atr(df, 14).values
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    t = df["time"]
    day = t.dt.normalize().values
    swd = np.array([pd.Timestamp(x) in sw for x in day])
    nxt_sw = np.r_[swd[1:], False] & (day != np.r_[day[1:], day[-1]])     # next candle starts a switch day
    intraday = (strat == "orb_30m")
    trades, pos = [], None
    for i in range(210, len(df) - 1):
        if pos is not None:
            s, e0, stop, tp, k0 = pos
            done = None
            if (o[i] <= stop) if s > 0 else (o[i] >= stop):
                done = (o[i], "gap stop")
            elif (l[i] <= stop) if s > 0 else (h[i] >= stop):
                done = (stop, "stop")
            elif tp is not None and ((h[i] >= tp) if s > 0 else (l[i] <= tp)):
                done = (tp, "target")
            elif intraday and (i + 1 >= len(df) or day[i + 1] != day[i]):
                done = (c[i], "session end")
            elif nxt_sw[i]:
                done = (c[i], "before contract switch")
            elif (ex is not None and ex(i, s)) or i - k0 >= MAX_HOLD[tf]:
                done = (o[i + 1], "exit signal" if ex(i, s) else "time")
            if done:
                px = done[0]
                risk = abs(e0 - pos_stop0[0])
                cost = INS.cost_points(name, e0, cost_x)
                r = (s * (px - e0) - cost) / risk
                trades.append(dict(name=name, tf=tf, strat=strat, side=s, entry_time=t.iat[k0], exit_time=t.iat[i], r=r, why=done[1]))
                pos = None
            continue
        if ent[i] == 0 or swd[i] or nxt_sw[i] or not np.isfinite(a[i]) or a[i] <= 0:
            continue
        if intraday and day[i + 1] != day[i]:
            continue
        s = int(ent[i]); e0 = o[i + 1]
        if intraday:
            t9 = (t.dt.normalize() == t.iat[i].normalize()) & (t.dt.hour == 9) & (t.dt.minute < 30)
            stop = (l[t9.values].min() if s > 0 else h[t9.values].max())
        else:
            stop = e0 - s * stop_k * a[i]
        if s * (e0 - stop) <= 0:
            continue
        tp = e0 + s * tgt * abs(e0 - stop) if tgt else None
        pos = (s, e0, stop, tp, i + 1)
        pos_stop0 = (stop,)
    return trades


def live_rule_trades(df, h1, name, tf, cost_x=1.0):
    """The current RSI-reversal alert rule, scored the same way (next open entry, its own SL/T1/T2)."""
    t = ST.score(df, h1=h1)
    if t.empty:
        return []
    t = t[t["passed"]]
    return [dict(name=name, tf=tf, strat="rsi_reversal_live", side=1 if x.side == "BUY" else -1, entry_time=x.time,
                 exit_time=x.time, r=x.r - (cost_x - 1) * ST.COST_R, why="") for x in t.itertuples()]


def stats(r, rng=np.random.default_rng(7)):
    r = np.asarray(r, float)
    if len(r) == 0:
        return dict(trades=0)
    w, l = r[r > 0], r[r <= 0]
    b = rng.choice(r, (4000, len(r))).mean(axis=1)
    return dict(trades=int(len(r)), exp_r=round(float(r.mean()), 3), win=round(float((r > 0).mean() * 100), 1),
                pf=round(float(w.sum() / -l.sum()), 2) if l.sum() < 0 else None,
                p1=round(float(np.percentile(b, 1)), 3), p5=round(float(np.percentile(b, 5)), 3))


def main():
    rows = []
    for exch, name in NAMES:
        h = load(exch, name, "ONE_HOUR")
        if h is None:
            continue
        sw = switch_days(name, exch, h)
        frames = {"1h": h, "3h": ST.three_hour_generic(h), "1d": daily_from(h)}
        if name == "CRUDEOIL":
            frames["15m"] = load(exch, name, "FIFTEEN_MINUTE")
        for tf, df in frames.items():
            for strat in STRATS + ["rsi_reversal_live"]:
                if strat == "orb_30m" and tf != "15m":
                    continue
                if strat == "rsi_reversal_live" and tf == "1d":
                    continue
                for cx in (1.0, 2.0):
                    tr = (live_rule_trades(df, h, name, tf, cx) if strat == "rsi_reversal_live"
                          else backtest(df, strat, name, exch, tf, sw, cx))
                    for x in tr:
                        x["cost_x"] = cx
                    rows += tr
            print(name, tf, "done", flush=True)
    T = pd.DataFrame(rows)
    T["period"] = np.where(pd.to_datetime(T["entry_time"]) < SPLIT, "design", "holdout")
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "all_trades.csv", index=False)
    res = []
    for (strat, tf), g in T[T["cost_x"] == 1.0].groupby(["strat", "tf"]):
        d, ho = g[g["period"] == "design"], g[g["period"] == "holdout"]
        d2 = T[(T["cost_x"] == 2.0) & (T["strat"] == strat) & (T["tf"] == tf) & (T["period"] == "design")]
        sd = stats(d["r"])
        inst = [gg["r"].mean() > 0 for _, gg in d.groupby("name") if len(gg) >= 5]
        short = (sd.get("trades", 0) >= 60 and sd.get("exp_r", -9) >= 0.10 and (sd.get("pf") or 0) >= 1.2 and sd.get("p1", -9) > 0
                 and d2["r"].mean() > 0 and bool(inst) and np.mean(inst) >= 0.6)
        row = dict(strat=strat, tf=tf, design=sd, design_2x_exp=round(float(d2["r"].mean()), 3) if len(d2) else None,
                   design_inst_positive=f"{sum(inst)}/{len(inst)}", shortlisted=bool(short))
        if short:                                   # hold-out opened only for shortlisted combinations
            h2 = T[(T["cost_x"] == 2.0) & (T["strat"] == strat) & (T["tf"] == tf) & (T["period"] == "holdout")]
            sh = stats(ho["r"])
            row.update(holdout=sh, holdout_2x_exp=round(float(h2["r"].mean()), 3) if len(h2) else None,
                       holdout_by_inst={n: round(float(gg["r"].mean()), 3) for n, gg in ho.groupby("name")},
                       PASS=bool(sh.get("trades", 0) >= 40 and sh.get("exp_r", -9) >= 0.05 and (sh.get("pf") or 0) >= 1.1
                                 and len(h2) and h2["r"].mean() > 0))
        res.append(row)
        print(strat, tf, sd, "SHORTLIST" if short else "", row.get("PASS", ""), flush=True)
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
