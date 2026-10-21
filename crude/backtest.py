"""Backtest of the Crude Oil engines on REAL Angel One candles (research/data/angel, branch research-data).

  python -m crude.backtest            -> crude/reports/*.csv + crude/BACKTEST.md

Data: Angel's vendor-stitched CRUDEOIL front-month 15-minute series (Oct-2020 → today; holes reported, not filled).
1-hour candles are built from the 15-minute ones (same 09:00-based boundaries Angel uses; checked against Angel's own
1-hour series), 3-hour candles from 1-hour ones with crude/data.three_hour (the live code).
Rolls: switch = first session after each contract's expiry (crude/data.crude_expiry, the rule that matches every listed
contract; cross-checked with the volume jump). Indicators use a Panama back-adjusted series; the roll gap is ESTIMATED
(MCX move not explained by WTI × USD/INR that day – research/roll_adjust). No trade is ever held across a switch, so
trade P&L never contains a roll gap. Entries are skipped in the last 4 trading days before expiry (live trades the
next contract then; its history is not available for the past).
Fills: next candle's OPEN after the signal candle closes (+2 ticks slippage); stops/targets via crude/paper.step_bar.
Sizing: 0.25% of a fixed ₹5,00,000 on CRUDEOILM (₹10/pt) – the same as paper. R-multiples are size-independent.
OI: Angel has no historical MCX OI -> every backtest trade ran under the 'fallback' OI policy (OI filter unavailable).
Parameters are the fixed values in crude/config.py – nothing here is optimised.
"""
import json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from crude import config as K, data as D, rules as R, paper as P, indicators as I  # noqa: E402

SRC = ROOT / "research" / "data" / "angel" / "MCX"
OUT = ROOT / "crude" / "reports"
MULT, TICK = K.RS_PER_POINT[K.TRADE_NAME], 1.0
SPLIT = pd.Timestamp("2024-01-01")
_DEC = {}                                   # decisions don't depend on costs -> evaluate once, reuse for 2×/3× runs          # first half / second half (no parameters were fitted on either)


# ─────────────── data ───────────────
def load_15m():
    f = sorted(SRC.glob("CRUDEOIL*_FIFTEEN_MINUTE.csv"))
    man = pd.read_csv(ROOT / "research" / "data" / "angel" / "manifest.csv")
    row = man[(man["name"] == "CRUDEOIL") & (man["interval"] == "FIFTEEN_MINUTE") & (man["front_stitched"])].iloc[0]
    d = pd.read_csv(SRC / f"{row['symbol']}_FIFTEEN_MINUTE.csv", parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]]
    d = d.sort_values("time").drop_duplicates("time").iloc[:-1].reset_index(drop=True)     # last candle was still forming
    return d, row


def expiries(d):
    out = []
    for y in range(d["time"].dt.year.min() - 1, d["time"].dt.year.max() + 2):
        for m in range(1, 13):
            out.append(D.crude_expiry(y, m))
    return sorted(out)


def roll_table(d):
    """Switch = first candle after each expiry day. Volume check: the expiring contract trades thinly on its last
    day(s), the next one shows a jump – confirmed when the switch day has the biggest day-volume jump within ±3 days."""
    from research.roll_adjust import expected_return
    day = d.groupby(d["time"].dt.normalize()).agg(close=("close", "last"), volume=("volume", "sum"))
    jump = day["volume"] / day["volume"].shift(1)
    exp_ret = expected_return("CRUDEOIL", day.index)
    rows = []
    for e in expiries(d):
        nxt = day.index[day.index > e]
        prv = day.index[day.index <= e]
        if not len(nxt) or not len(prv) or (nxt[0] - e).days > 7 or (e - prv[-1]).days > 7:
            continue
        sd = nxt[0]
        win = jump[(jump.index >= sd - pd.offsets.BDay(3)) & (jump.index <= sd + pd.offsets.BDay(3))]
        best = win.idxmax() if win.notna().any() else None
        er = exp_ret.get(sd)
        prev_c, c = day.at[prv[-1], "close"], day.at[sd, "close"]
        gap = c - prev_c * (1 + (er if pd.notna(er) else 0.0))
        rows.append(dict(expiry=e, switch_day=sd, switch_time=d.loc[d["time"].dt.normalize() == sd, "time"].iloc[0],
                         vol_jump=round(float(jump.get(sd, np.nan)), 2), volume_confirms=bool(best == sd),
                         est_gap_pts=round(float(gap), 1), est_gap_pct=round(float(gap / prev_c * 100), 3),
                         proxy_missing=bool(pd.isna(er))))
    return pd.DataFrame(rows)


def adjust(d, rolls):
    a = d.copy()
    a["offset"] = 0.0
    for r in rolls.itertuples():
        a.loc[a["time"] < r.switch_time, "offset"] += r.est_gap_pts
    for k in ("open", "high", "low", "close"):
        a[k] = a[k] + a["offset"]
    a["seg"] = np.searchsorted(rolls["switch_time"].values, a["time"].values, side="right")
    return a


def hourly(a):
    g = a.groupby(a["time"].dt.floor("h"))
    h = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
              volume=("volume", "sum"), offset=("offset", "last"), n=("close", "size")).reset_index()
    return h


def check_hourly(h):
    """Compare our 1-hour candles with Angel's own 1-hour series where both exist (raw prices)."""
    f = SRC / "CRUDEOIL19NOV26FUT_ONE_HOUR.csv"
    if not f.exists():
        return None
    ang = pd.read_csv(f, parse_dates=["time"])
    m = (h.assign(close_raw=h["close"] - h["offset"])).merge(ang[["time", "close", "volume"]], on="time", suffixes=("", "_a"))
    m = m[m["time"] < ang["time"].max()]
    return dict(overlap_bars=len(m), close_match_pct=round(float((m["close_raw"].round(2) == m["close_a"]).mean() * 100), 2),
                volume_match_pct=round(float((m["volume"] == m["volume_a"]).mean() * 100), 2))


# ─────────────── simulation ───────────────
def _ends(times, minutes):
    return pd.Series([D.bar_end(t, minutes) for t in times], index=times.index)


def simulate(engine, a, h1, h3, rolls, cost_x=1.0, baseline=False):
    """One engine, its own book. Returns (trades DataFrame, decision counter dict)."""
    n = len(a)
    T = a["time"]
    end15 = _ends(T, 15).values
    day = T.dt.normalize().values
    exps = np.array(sorted(set(rolls["expiry"])), dtype="datetime64[ns]")
    nxt_exp = exps[np.searchsorted(exps, day, side="left").clip(max=len(exps) - 1)]
    tdl = np.busday_count(day.astype("datetime64[D]"), nxt_exp.astype("datetime64[D]"))
    closes = {dd: D.session_close(dd) for dd in pd.unique(T.dt.normalize())}
    h1_end = _ends(h1["time"], 60).values
    h3_end = h3["end"].values if len(h3) else np.array([])
    ticks = K.SLIPPAGE_TICKS * cost_x
    cap = K.CAPITAL
    trades, cnt = [], dict(evaluated=0, signal=0, blocked=0, ignored=0, none=0, reasons={})
    pos, last_exit_i, pending = None, -10 ** 9, None
    day_pnl = {}
    seg = a["seg"].values
    P_ = K.INTRA if engine == "intraday" else K.POS
    warm = 800
    if engine == "positional":
        ev_idx = {}
        for j, e in enumerate(h3_end):
            k = np.searchsorted(end15, e, side="right") - 1
            if k >= 0 and end15[k] == e:
                ev_idx[k] = j
    elif baseline:
        ev_idx = {}
        for j, e in enumerate(h1_end):
            k = np.searchsorted(end15, e, side="right") - 1
            if k >= 0 and end15[k] == e:
                ev_idx[k] = j

    def _close(p, px, why, i):
        nonlocal pos, last_exit_i
        t = P.close_position(p, px, why, T.iloc[i], cost_x)
        trades.append(t)
        dd = str(T.iloc[i].date())
        day_pnl[dd] = day_pnl.get(dd, 0.0) + t["pnl"]
        if p.get("leg") != "A":
            pos, last_exit_i = None, i
        return t

    for i in range(warm, n - 1):
        bar = dict(open=a.at[i, "open"], high=a.at[i, "high"], low=a.at[i, "low"], close=a.at[i, "close"])
        cs = closes[T.iloc[i].normalize()]
        # 1) fill a pending entry at this candle's open
        if pending is not None:
            sig, j = pending
            pending = None
            if j == i and seg[i] == seg[i - 1]:
                o = bar["open"]
                atr = sig["plan"]["atr"]
                if abs(o - sig["signal_close"]) > P_["max_chase_atr"] * atr:
                    cnt["ignored"] += 1
                    cnt["reasons"]["ignored: chase"] = cnt["reasons"].get("ignored: chase", 0) + 1
                else:
                    lots, budget, per_lot = P.size(cap, sig["plan"]["stop_dist"], o, MULT, TICK)
                    if lots < 1:
                        cnt["ignored"] += 1
                        cnt["reasons"]["ignored: 1 lot > risk budget"] = cnt["reasons"].get("ignored: 1 lot > risk budget", 0) + 1
                    else:
                        fill = P.slip(sig["side"], o, TICK, True, ticks)
                        meta = dict(id=f"{engine}|{T.iloc[i]}", time=str(T.iloc[i]), setup=sig.get("setup"), signal_bar=sig["bar_time"],
                                    expiry=str(pd.Timestamp(nxt_exp[i]).date()), oi="UNAVAILABLE (no historical MCX OI)",
                                    trend=sig["metrics"].get("trend_1h") or sig["metrics"].get("trend_3h"))
                        eng_name = "baseline-intraday" if baseline and engine == "intraday" else engine
                        pos = P.open_position(eng_name, sig["side"], fill, sig["plan"], lots, MULT, TICK, "CRUDEOILM", meta)
                        pos["entry_i"] = i
                        if baseline and engine == "intraday":          # Engine D: half at T1 (1R), rest at T2 (2R), SL to cost after T1
                            pos["lots"] = lots
                            pos["leg_a"] = dict(pos, leg="A", target=round(fill + (1 if sig["side"] == "BUY" else -1) * pos["risk_pts"], 2),
                                                units=pos["units"] / 2, no_be=True)
                            pos["units"] = pos["units"] / 2
        # 2) manage the open position with this candle
        if pos is not None and pos["entry_i"] <= i:
            if seg[i] != seg[pos["entry_i"]]:                       # must never happen (flat before expiry) – guard
                _close(pos, a.at[i - 1, "close"], "roll guard", i - 1)
            elif engine == "intraday" and (D.bar_end(T.iloc[i], 15) > cs - pd.Timedelta(minutes=K.SQUARE_OFF_BEFORE_CLOSE_MIN)
                                           or T.iloc[i].normalize() != T.iloc[pos["entry_i"]].normalize()):
                px = P.slip(pos["side"], bar["open"], TICK, False, ticks)
                if pos.get("leg_a"):
                    _close(pos.pop("leg_a"), px, "intraday square-off", i)
                _close(pos, px, "intraday square-off", i)
            else:
                if pos.get("leg_a"):
                    r = P.step_bar(pos["leg_a"], bar, ticks=ticks)
                    if r:
                        _close(pos.pop("leg_a"), r[0], r[1], i)
                r = P.step_bar(pos, bar, ticks=ticks)
                if r:
                    _close(pos, r[0], r[1], i)
                elif engine == "positional":
                    nd = T.iloc[i + 1].normalize()
                    if tdl[i + 1] <= K.FLAT_BEFORE_EXPIRY_DAYS and nd != T.iloc[i].normalize():
                        _close(pos, P.slip(pos["side"], a.at[i + 1, "open"], TICK, False, ticks), "roll: flat before expiry", i + 1)
                    elif i in ev_idx:
                        j = ev_idx[i]
                        c3 = h3.iloc[max(0, j - 300):j + 1]
                        e50 = I.ema(c3["close"], K.POS["ema_slow"]).iloc[-1]
                        sgn = 1 if pos["side"] == "BUY" else -1
                        sess = len(set(T.iloc[pos["entry_i"]:i + 1].dt.normalize()))
                        if sgn * (c3["close"].iloc[-1] - e50) < 0:
                            _close(pos, P.slip(pos["side"], a.at[i + 1, "open"], TICK, False, ticks), "3h close beyond EMA50", i + 1)
                        elif sess > K.POS["max_hold_sessions"]:
                            _close(pos, P.slip(pos["side"], a.at[i + 1, "open"], TICK, False, ticks), "time stop", i + 1)
        # 3) evaluate a new signal on the candle that just closed
        if pos is not None or pending is not None:
            continue
        ck = (engine, baseline, i)
        if ck in _DEC:
            dec, win = _DEC[ck]
            dec = dict(dec)
        elif engine == "intraday" and not baseline:
            c15 = a.iloc[max(0, i - 700):i + 1]
            k = np.searchsorted(h1_end, end15[i], side="right")
            h1w = h1.iloc[max(0, k - 400):k]
            dec = R.intraday(c15, h1w)
            win = (T.iloc[i] >= D.hm(T.iloc[i], K.FIRST_ENTRY)) and (pd.Timestamp(end15[i]) <= cs - pd.Timedelta(minutes=K.LAST_ENTRY_BEFORE_CLOSE_MIN))
        elif engine == "intraday" and baseline:
            if i not in ev_idx:
                continue
            j = ev_idx[i]
            from calls import rules as CR
            sig0, why = CR.intraday(h1.iloc[max(0, j - 400):j + 1])
            win = (T.iloc[i] >= D.hm(T.iloc[i], "10:00")) and (pd.Timestamp(end15[i]) <= D.hm(T.iloc[i], "22:00"))
            if sig0 is None:
                dec = dict(decision="NONE", blocks=[why], metrics={})
            elif sig0.get("blocked"):
                dec = dict(decision="BLOCKED", blocks=[sig0["blocked"]], metrics={})
            else:
                pl = CR.intraday_plan(sig0, sig0["close"])
                dec = dict(decision="SIGNAL", side=sig0["side"], signal_close=sig0["close"], bar_time=str(T.iloc[i]), metrics={},
                           plan=dict(stop_dist=pl["R"], target_r=2.0, atr=sig0["atr"]), blocks=[])
        else:
            if i not in ev_idx:
                continue
            j = ev_idx[i]
            dec = R.positional(h3.iloc[max(0, j - 300):j + 1])
            win = True
        if ck not in _DEC:
            _DEC[ck] = (dict(dec), win)
        cnt["evaluated"] += 1
        d0 = dec["decision"]
        if d0 == "NONE":
            cnt["none"] += 1
            continue
        key = (dec.get("blocks") or ["?"])[0].split(":")[0][:40] if d0 == "BLOCKED" else "signal"
        if d0 == "BLOCKED":
            cnt["blocked"] += 1
            cnt["reasons"]["blocked: " + key] = cnt["reasons"].get("blocked: " + key, 0) + 1
            continue
        cnt["signal"] += 1
        gate = None
        if not win:
            gate = "outside entry window"
        elif tdl[i] <= K.ROLL_TRADING_DAYS:
            gate = "expiry week (live trades next contract; no history)"
        elif day_pnl.get(str(T.iloc[i].date()), 0.0) <= -K.DAILY_LOSS_PCT * cap:
            gate = "daily loss limit"
        elif (i - last_exit_i) < K.COOLDOWN_BARS[engine] * (1 if engine == "intraday" else 12):
            gate = "cool-down"
        elif seg[i + 1] != seg[i]:
            gate = "next candle is in the next contract"
        if gate:
            cnt["ignored"] += 1
            cnt["reasons"]["ignored: " + gate] = cnt["reasons"].get("ignored: " + gate, 0) + 1
            continue
        dec.setdefault("bar_time", str(T.iloc[i]))
        pending = (dec, i + 1)
    if pos is not None:
        if pos.get("leg_a"):
            _close(pos.pop("leg_a"), a.at[n - 1, "close"], "end of data", n - 1)
        _close(pos, a.at[n - 1, "close"], "end of data", n - 1)
    t = pd.DataFrame(trades)
    if baseline and len(t):                                        # merge the two halves of each baseline trade
        t = t.groupby("id").agg(side=("side", "first"), entry_time=("entry_time", "first"), exit_time=("exit_time", "last"),
                                entry=("entry", "first"), exit=("exit", "mean"), exit_reason=("exit_reason", "last"),
                                pnl=("pnl", "sum"), charges=("charges", "sum"), risk_pts=("risk_pts", "first"),
                                units=("units", "sum"), lots=("lots", "first")).reset_index()
        t["r"] = t["pnl"] / (t["risk_pts"] * t["units"])
    return t, cnt


# ─────────────── metrics ───────────────
def metrics(t, cap=K.CAPITAL):
    if t is None or not len(t):
        return dict(trades=0)
    p, r = t["pnl"], t["r"]
    w, l = p[p > 0], p[p <= 0]
    eq = cap + p.cumsum()
    dd = (eq - eq.cummax()).min()
    streak = mx = 0
    for x in p:
        streak = streak + 1 if x <= 0 else 0
        mx = max(mx, streak)
    rng = np.random.default_rng(7)
    boot = [rng.choice(r.values, len(r)).mean() for _ in range(2000)]
    return dict(trades=int(len(t)), win_rate=round(float((p > 0).mean() * 100), 1),
                avg_win=round(float(w.mean()), 0) if len(w) else 0, avg_loss=round(float(l.mean()), 0) if len(l) else 0,
                expectancy_rs=round(float(p.mean()), 0), expectancy_r=round(float(r.mean()), 3),
                profit_factor=round(float(w.sum() / -l.sum()), 2) if len(l) and l.sum() < 0 else None,
                net_rs=round(float(p.sum()), 0), max_dd_rs=round(float(dd), 0), max_dd_pct=round(float(dd / cap * 100), 2),
                max_consec_losses=int(mx), boot_p5_r=round(float(np.percentile(boot, 5)), 3),
                charges_rs=round(float(t["charges"].sum()), 0))


def regimes(a):
    """Daily regime labels from the adjusted series: trend (close vs 100-day SMA) × volatility (20-day ATR% vs median)."""
    dd = a.groupby(a["time"].dt.normalize()).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    sma = dd["close"].rolling(100, min_periods=60).mean()
    atrp = I.atr(dd.reset_index(drop=True), 20).values / dd["close"].values
    med = pd.Series(atrp, index=dd.index).rolling(250, min_periods=100).median()
    lab = pd.Series("unknown", index=dd.index)
    tr = np.where(dd["close"] > sma, "uptrend", "downtrend")
    vo = np.where(pd.Series(atrp, index=dd.index) > med, "high-vol", "low-vol")
    lab[:] = [f"{x}/{y}" for x, y in zip(tr, vo)]
    lab[sma.isna() | med.isna()] = "warm-up"
    return lab.shift(1).fillna("warm-up")             # yesterday's regime: known before the session (no look-ahead)


def criteria(m, m2):
    """Pre-registered checks from research/CRITERIA.md."""
    if not m.get("trades"):
        return dict(passed=False, checks={"trades ≥ 50": False})
    c = {"trades ≥ 50": m["trades"] >= 50, "expectancy > 0.10R": m["expectancy_r"] > 0.10,
         "bootstrap p5 > 0": m["boot_p5_r"] > 0, "profit factor ≥ 1.2": (m["profit_factor"] or 0) >= 1.2,
         "still positive at 2× costs": m2.get("expectancy_r", -1) > 0}
    return dict(passed=all(c.values()), checks=c)


def run(write=True):
    d, row = load_15m()
    rolls = roll_table(d)
    a = adjust(d, rolls)
    h1 = hourly(a)
    h3 = D.three_hour(h1[["time", "open", "high", "low", "close", "volume", "offset"]])
    hchk = check_hourly(h1)
    reg = regimes(a)
    # coverage
    days = pd.Series(pd.unique(d["time"].dt.normalize()))
    bdays = pd.bdate_range(days.min(), days.max())
    holes = d.loc[d["time"].diff() > pd.Timedelta(days=5), "time"]
    cover = dict(first=str(d["time"].min()), last=str(d["time"].max()), bars_15m=len(d), sessions=len(days),
                 weekdays_in_range=len(bdays), session_coverage_pct=round(len(days) / len(bdays) * 100, 1),
                 holes=[f"{d.loc[i - 1, 'time']:%d-%b-%Y} → {d.loc[i, 'time']:%d-%b-%Y}" for i in holes.index],
                 volume_nonzero_pct=round(float((d["volume"] > 0).mean() * 100), 2),
                 oi_coverage_pct=0.0, hourly_vs_angel=hchk, rolls=len(rolls),
                 rolls_volume_confirmed=int(rolls["volume_confirms"].sum()),
                 rolls_proxy_missing=int(rolls["proxy_missing"].sum()),
                 ema200_1h_available_from=str(h1["time"].iloc[K.INTRA["ema_long_min_bars"]]),
                 h3_complete_pct=round(float(h3["complete"].mean() * 100), 1))
    res = {}
    for eng, base in (("intraday", False), ("positional", False), ("intraday", True)):
        name = ("baseline-" if base else "") + eng
        out = {}
        for cx in K.COST_STRESS:
            t, cnt = simulate(eng, a, h1, h3, rolls, cost_x=cx, baseline=base)
            out[cx] = (t, cnt)
            print(name, cx, len(t), flush=True)
        t, cnt = out[1.0]
        if len(t):
            t["year"] = pd.to_datetime(t["entry_time"]).dt.year
            t["regime"] = pd.to_datetime(t["entry_time"]).dt.normalize().map(reg).fillna("warm-up")
            t["half"] = np.where(pd.to_datetime(t["entry_time"]) < SPLIT, "2020-10…2023", "2024…2026-10")
        m = {cx: metrics(out[cx][0]) for cx in K.COST_STRESS}
        by = lambda col: {str(k): metrics(g) for k, g in t.groupby(col)} if len(t) else {}
        wf = {}
        if len(t):                                               # rolling 12-month windows, stepped 6 months (no re-fitting)
            et = pd.to_datetime(t["entry_time"])
            s = pd.Timestamp(et.min().year, 1, 1)
            while s < et.max():
                e = s + pd.DateOffset(months=12)
                g = t[(et >= s) & (et < e)]
                wf[f"{s:%Y-%m}…{e - pd.Timedelta(days=1):%Y-%m}"] = dict(trades=len(g), expectancy_r=round(float(g["r"].mean()), 3) if len(g) else None,
                                                                           net_rs=round(float(g["pnl"].sum()), 0))
                s += pd.DateOffset(months=6)
        res[name] = dict(cost={str(k): v for k, v in m.items()}, decisions=cnt, by_year=by("year"), by_regime=by("regime"),
                         by_half=by("half"), walk_forward=wf, criteria=criteria(m[1.0], m[2.0]),
                         exit_reasons=t["exit_reason"].value_counts().to_dict() if len(t) else {})
        if write and len(t):
            OUT.mkdir(parents=True, exist_ok=True)
            t.drop(columns=[c for c in ("reasons", "leg_a") if c in t], errors="ignore").to_csv(OUT / f"trades_{name}.csv", index=False)
    if write:
        OUT.mkdir(parents=True, exist_ok=True)
        rolls.to_csv(OUT / "rolls.csv", index=False)
        (OUT / "backtest.json").write_text(json.dumps(dict(coverage=cover, results=res), indent=1, default=str))
    return cover, res, rolls


if __name__ == "__main__":
    cover, res, rolls = run()
    print(json.dumps(cover, indent=1, default=str))
    for k, v in res.items():
        print(k, json.dumps(v["cost"]["1.0"]), v["criteria"])
