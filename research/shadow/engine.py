"""Shadow engine: detect -> ledger (append-only) -> lifecycle (rebuilt every run from the ledger + official prices).
Every qualifying signal is written; nothing is filtered away. A signal that cannot be traded keeps its row with the
reason (overlap with an open trade of the same stock, F&O ban, no trades in the contract, missing / suspended, locked
circuit, late detection, data not yet published). Two outcomes are kept per trade:
  research_R – the research convention on adjusted cash prices (what the back-test would have recorded; reconciliation)
  exec_R     – what a real order would have got: actual futures contract (SF) / cash (CM) prices, slippage on the fill,
               measured spread when a Best-5 snapshot exists, real costs, rolls at expiry, daily bars for the order of
               events.  SHADOW ONLY – no alert, no order, nothing read by production."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

from research.shadow import rules as RU, data as DA

START = pd.Timestamp("2026-11-11")          # forward test start (owner approval 11-Nov-2026); earlier = history only
HIST_FROM = "2023-06-01"                    # indicator warm-up window for the nightly run
UNIV = Path(__file__).resolve().parent / "universe.csv"     # NIFTY 500 industry list (6-Nov-2026 copy)


def fut_cost(day, slip):
    d = pd.Timestamp(day)
    stt = 0.000125 if d < pd.Timestamp("2024-10-01") else (0.0002 if d < pd.Timestamp("2026-04-01") else 0.0005)
    exch = 2 * 0.0000173; brok = 40.0 / 6e5
    return stt + exch + 0.18 * (exch + brok) + brok + 0.00002 + 2e-6 + 2 * slip


# ───────────────────────── market data ─────────────────────────
def adjusted(P):
    from research.program import eq_bhav as EB
    return EB.adjusted(P)


def market_regime(A):
    from research.program import eq_bhav as EB
    m = EB.market(A).set_index("time")["close"]
    e200 = m.ewm(span=200, adjust=False).mean()
    return pd.DataFrame(dict(mkt=m, up=m > e200, r20=m.pct_change(20)))


def sector_map():
    try:
        return dict(pd.read_csv(UNIV)[["symbol", "industry"]].fillna("").values)
    except Exception:
        return {}


# ───────────────────────── detection ─────────────────────────
def detect_sf(A, fo, start=None):
    """-> DataFrame of SF-CONT-SELL-v1 signals with signal_date >= start. fo: F&O rows (date, symbol, kind ...)."""
    p = RU.RULES["SF-CONT-SELL-v1"]; start = START if start is None else start
    stk = fo[fo.kind == "STK"]
    have = set(zip(stk.date, stk.symbol))
    rows = []
    for key, a in A.items():
        a = a.reset_index(drop=True)
        if a["time"].iloc[-1] < start or len(a) < 30:
            continue
        to60 = a["value"].rolling(60, min_periods=40).median().shift(1)
        live = np.array([(t, s) in have for t, s in zip(a["time"], a["symbol"])]) & (to60 >= p["min_turnover"]).values & (a["close"] >= p["min_close"]).values
        b = a.assign(live=live)
        sig, risk, r, at = RU.sf_signal(b)
        for i in np.where(sig & (a["time"] >= start).values)[0]:
            rows.append(dict(strategy="SF-CONT-SELL-v1", signal_date=a["time"].iloc[i], symbol=a["symbol"].iloc[i], key=key,
                             close=float(a["close"].iloc[i]), risk=float(risk[i]), risk_pct=float(risk[i] / a["close"].iloc[i]),
                             rsi=round(float(r[i]), 2), rsi_min10=round(float(np.nanmin(r[max(0, i - 9): i + 1])), 2), atr=float(at[i]),
                             prior5_high=float(a["high"].iloc[max(0, i - 5): i].max()), turnover60_cr=round(float(to60.iloc[i]) / 1e7, 1)))
    return pd.DataFrame(rows)


def weekly_panels(A):
    """the research weekly construction (research/cashq/data.daily_panel + weekly) for the keys in A."""
    keys = list(A)
    idx = pd.DatetimeIndex(sorted({t for d in A.values() for t in d["time"]}))
    col = lambda f: pd.DataFrame({k: pd.Series(A[k][f].values.astype("float64"), index=pd.DatetimeIndex(A[k]["time"])) for k in keys}).reindex(idx)
    close, value = col("close"), col("value")
    to60 = value.rolling(60, min_periods=40).median().shift(1)
    hist = close.notna().cumsum()
    p = RU.RULES["CM-CONT-BUY-v1"]
    elig = (to60 >= p["min_turnover"]) & (close >= p["min_close"]) & (hist >= p["min_hist"]) & close.notna()
    W = dict(close=close, value=value, elig=elig, open=col("open"), high=col("high"), low=col("low"), volume=col("volume"))
    g = idx.to_period("W-FRI")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "value": "sum"}
    out = {f: W[f].groupby(g).agg(agg[f]) for f in agg}
    last_day = pd.Series(idx, index=idx).groupby(g).last()
    for f in out:
        out[f].index = pd.DatetimeIndex(last_day.values)
    out["elig"] = W["elig"].groupby(g).last().set_axis(out["close"].index).astype(bool)
    out["symbol"] = pd.Series({k: str(A[k]["symbol"].iloc[-1]) for k in keys})
    return out


def detect_cm(A, start=None, week_complete=None):
    """-> CM-CONT-BUY-v1 signals for completed weeks ending >= start. week_complete(last_day) decides whether the last
    week in the data is finished (a Friday session, or a later session already exists)."""
    p = RU.RULES["CM-CONT-BUY-v1"]; start = START if start is None else start
    Wk = weekly_panels(A)
    el = Wk["elig"]
    tor = Wk["value"].rolling(p["liq_weeks"], min_periods=8).median().shift(1).where(el).rank(axis=1, pct=True)
    idx = Wk["close"].index; rows = []
    for k in Wk["close"].columns:
        ok = Wk["close"][k].notna().values
        if ok.sum() < 60 or idx[ok][-1] < start:
            continue
        b = pd.DataFrame(dict(time=idx[ok], **{f: Wk[f][k].values[ok] for f in ("open", "high", "low", "close", "value")}))
        b["elig"] = el[k].values[ok]; b["liq_rank"] = tor[k].values[ok]
        sig, risk, r, at = RU.cm_signal(b)
        for i in np.where(sig & (b["time"] >= start).values)[0]:
            if i == len(b) - 1 and week_complete is not None and not week_complete(b["time"].iloc[i]):
                continue
            rows.append(dict(strategy="CM-CONT-BUY-v1", signal_date=b["time"].iloc[i], symbol=str(Wk["symbol"][k]), key=k,
                             close=float(b["close"].iloc[i]), risk=float(risk[i]), risk_pct=float(risk[i] / b["close"].iloc[i]),
                             rsi=round(float(r[i]), 2), rsi_prev=round(float(r[i - 1]), 2) if i else np.nan, atr=float(at[i]),
                             liq_rank=round(float(b["liq_rank"].iloc[i]), 3), week_value_cr=round(float(b["value"].iloc[i]) / 1e7, 1)))
    return pd.DataFrame(rows)


# ───────────────────────── lifecycle ─────────────────────────
def _next_session(days, d):
    later = days[days > pd.Timestamp(d)]
    return later[0] if len(later) else None


def _depth(date, token=None, symbol=None):
    try:
        x = DA.depth_rows(date)
    except Exception:
        return {}
    if not len(x):
        return dict(depth="no depth file for this date")
    m = x[(x.token.astype(str) == str(token))] if token is not None else x[x.get("symbol", pd.Series(dtype=str)).astype(str) == f"{symbol}-EQ"]
    if not len(m):
        return dict(depth="instrument not in the recorded depth set")
    m = m.sort_values("time"); r = m.iloc[0]
    # the bid side is whichever list has the lower best price (the SDK swaps the lists; see research/DEPTH_AUDIT.md)
    a1, b1 = r.get("A1p", np.nan), r.get("B1p", np.nan)
    bid, ask = (a1, b1) if a1 < b1 else (b1, a1)
    if not (bid > 0 and ask > 0):
        return dict(depth=f"snapshot {r['time']} has an empty side")
    mid = (bid + ask) / 2
    qa = sum(r.get(f"A{i}q", 0) for i in range(1, 6)); qb = sum(r.get(f"B{i}q", 0) for i in range(1, 6))
    qbid, qask = (qa, qb) if a1 < b1 else (qb, qa)
    return dict(depth=f"snapshot {r['time']}", depth_bid=bid, depth_ask=ask, half_spread_pct=round(100 * (ask - bid) / 2 / mid, 4),
                depth_imbalance=round((qbid - qask) / max(qbid + qask, 1), 3))


def lifecycle_sf(L, A, fo, days, regime, sectors, asof, bans):
    p = RU.RULES["SF-CONT-SELL-v1"]; out = []
    busy = {}
    for s in L.sort_values(["signal_date", "symbol"]).to_dict("records"):
        r = dict(s); sd = pd.Timestamp(s["signal_date"])
        rg = regime.reindex([sd]).iloc[0] if sd in regime.index else None
        r.update(market_up=bool(rg["up"]) if rg is not None else None, market_r20=round(float(rg["r20"]), 4) if rg is not None else None,
                 sector=sectors.get(s["symbol"], ""))
        f_sig = fo[(fo.date == sd) & (fo.symbol == s["symbol"]) & (fo.kind == "STK")].sort_values("expiry")
        r["basis_pct"] = round(100 * (float(f_sig.close.iloc[0]) / s["close"] - 1), 3) if len(f_sig) else None
        if s["symbol"] in busy and sd <= busy[s["symbol"]]:
            out.append(dict(r, status="OVERLAP – not taken (one open trade per stock, as in research)")); continue
        e = _next_session(days, sd)
        if e is None:
            out.append(dict(r, status="PENDING ENTRY (next session not yet published)")); continue
        r["entry_date"] = e
        if pd.Timestamp(s["detected_on"]) > sd:
            r["late"] = f"detected {pd.Timestamp(s['detected_on']).date()} – after the signal day; real-time entry was not possible"
        a = A[s["key"]].reset_index(drop=True); ti = a.index[a["time"] == sd]
        # research-equivalent: adjusted cash, research sim rules
        if len(ti):
            i = int(ti[0])
            if i + 1 < len(a):
                w = RU.walk(a.open.values, a.high.values, a.low.values, a.close.values, i + 1, -1, s["risk"], p["target_R"], p["max_bars"])
                exp = fo[(fo.symbol == s["symbol"]) & (fo.kind == "STK")]
                near = lambda d: exp[(exp.date == d) & (exp.expiry >= d)].expiry.min()
                roll = pd.notna(near(a.time.iloc[i + 1])) and near(a.time.iloc[w["exit_i"]]) != near(a.time.iloc[i + 1])
                cR = fut_cost(a.time.iloc[i + 1], p["slip_per_side"]) * (2 if roll else 1) * a.open.iloc[i + 1] / s["risk"]
                r.update(research_status="closed" if w["done"] else "open", research_reason=w["reason"], research_R=round(w["gross_R"] - cR, 4),
                         research_exit=a.time.iloc[w["exit_i"]])
                if w["done"]:
                    busy[s["symbol"]] = a.time.iloc[w["exit_i"]]
                else:
                    busy[s["symbol"]] = pd.Timestamp("2100-01-01")
        bl = bans.get(e)
        if bl is None:
            r["ban_check"] = "ban list not available"
        elif s["symbol"] in bl:
            out.append(dict(r, status="NOT EXECUTABLE – stock in F&O ban on the entry day (no new positions)")); continue
        fe = fo[(fo.date == e) & (fo.symbol == s["symbol"]) & (fo.kind == "STK") & (fo.expiry >= e)].sort_values("expiry")
        if not len(fe):
            out.append(dict(r, status="NOT EXECUTABLE – no futures contract on the entry day (left F&O / data missing)")); continue
        c0 = fe.iloc[0]
        if c0.expiry == e and len(fe) > 1:
            c0 = fe.iloc[1]; r["contract_note"] = "near month expires on the entry day – next month used"
        if not (c0.open > 0) or c0.contracts <= 0:
            out.append(dict(r, status="NOT EXECUTABLE – contract did not trade on the entry day")); continue
        r.update(contract=f"{s['symbol']} {pd.Timestamp(c0.expiry):%d-%b-%Y}", token=c0.token, lot=int(c0.lot), fut_open=float(c0.open))
        r.update(_depth(e, token=c0.token))
        slip = p["slip_per_side"]
        fill = c0.open * (1 - slip)                                  # SELL: filled slightly below the open
        kfrac = s["risk"] / float(a.open.iloc[int(ti[0]) + 1]) if len(ti) and int(ti[0]) + 1 < len(a) else s["risk_pct"]
        risk_f = c0.open * kfrac
        r.update(entry_px=round(fill, 2), stop_px=round(c0.open + risk_f, 2), target_px=round(c0.open - p["target_R"] * risk_f, 2),
                 risk_per_lot_rs=round(risk_f * c0.lot, 0), notional_per_lot_rs=round(c0.open * c0.lot, 0))
        # actual contract path, with a roll at expiry
        path, roll_at, exp_d, tok = [], [], c0.expiry, c0.token
        scale = 1.0
        for d in days[days >= e]:
            x = fo[(fo.date == d) & (fo.token == tok)]
            if not len(x):
                break
            x = x.iloc[0]; path.append((d, x.open * scale, x.high * scale, x.low * scale, x.close * scale))
            if d == exp_d:
                nx = fo[(fo.date == d) & (fo.symbol == s["symbol"]) & (fo.kind == "STK") & (fo.expiry > d)].sort_values("expiry")
                if not len(nx):
                    break
                n0 = nx.iloc[0]; scale = scale * x.close / n0.close; tok, exp_d = n0.token, n0.expiry; roll_at.append(len(path) - 1)
            if len(path) >= p["max_bars"]:
                break
        P = pd.DataFrame(path, columns=["d", "o", "h", "l", "c"])
        w = RU.walk(P.o.values, P.h.values, P.l.values, P.c.values, 0, -1, risk_f, p["target_R"], p["max_bars"])
        rolls = sum(1 for k in roll_at if w["exit_i"] > k)                 # held past that expiry day's close
        gross = (P.o.iloc[0] * (1 - slip) - w["exit_px"] * (1 + slip))      # per unit, SELL, slippage both sides
        cost_frac = fut_cost(e, 0.0) * (1 + rolls)                         # fees + roll round trips (slippage already in the fills)
        net = gross - cost_frac * P.o.iloc[0]
        r.update(status=("ACTIVE" if not w["done"] else {"target": "TARGET HIT", "target (gap)": "TARGET HIT (gap)", "stop": "STOP HIT",
                                                             "stop (gap)": "STOP HIT (gap through stop)", "time": "TIME EXIT (15 sessions)"}[w["reason"]]),
                 exit_date=P.d.iloc[w["exit_i"]] if w["done"] else None, exit_px=round(w["exit_px"], 2) if w["done"] else None,
                 last_px=round(float(P.c.iloc[-1]), 2), sessions=w["bars"], rolls=rolls, mfe_R=round(w["mfe_R"], 3), mae_R=round(w["mae_R"], 3),
                 exec_R=round(net / risk_f, 4), exec_net_pct=round(100 * net / P.o.iloc[0], 3), pnl_per_lot_rs=round(net * c0.lot, 0))
        out.append(r)
    return pd.DataFrame(out)


def lifecycle_cm(L, A, days, regime, sectors, asof, bands_by_day, mom_holdings):
    p = RU.RULES["CM-CONT-BUY-v1"]; out = []; busy = {}
    Wk = None
    for s in L.sort_values(["signal_date", "symbol"]).to_dict("records"):
        r = dict(s); sd = pd.Timestamp(s["signal_date"])
        rg = regime.reindex([sd]).iloc[0] if sd in regime.index else None
        r.update(market_up=bool(rg["up"]) if rg is not None else None, market_r20=round(float(rg["r20"]), 4) if rg is not None else None,
                 sector=sectors.get(s["symbol"], ""), in_momentum_portfolio=s["symbol"] in mom_holdings)
        if s["symbol"] in busy and sd <= busy[s["symbol"]]:
            out.append(dict(r, status="OVERLAP – not taken (one open trade per stock, as in research)")); continue
        e = _next_session(days, sd)
        if e is None:
            out.append(dict(r, status="PENDING ENTRY (next session not yet published)")); continue
        r["entry_date"] = e
        if pd.Timestamp(s["detected_on"]) > sd and pd.Timestamp(s["detected_on"]) >= e:
            r["late"] = f"detected {pd.Timestamp(s['detected_on']).date()} – after the entry open; real-time entry was not possible"
        a = A[s["key"]].reset_index(drop=True)
        ed = a[a["time"] == e]
        if not len(ed):
            out.append(dict(r, status="NOT EXECUTABLE – no trade in the stock on the entry day (suspended / not traded)")); continue
        ed = ed.iloc[0]
        raw = P_RAW.get((e, s["symbol"]))
        if raw is not None:
            o, h, l, pc, val = raw
            band = (bands_by_day.get(e) or {}).get(s["symbol"])
            r.update(entry_gap_pct=round(100 * (o / pc - 1), 2), price_band=band, entry_day_value_cr=round(val / 1e7, 2),
                     participation_pct=round(100 * p["order_value"] / max(val, 1), 3))
            if o == h == l and o > pc:
                out.append(dict(r, status="NOT EXECUTABLE – locked at the upper circuit all day (no sellers)")); continue
            if r["participation_pct"] > 5:
                r["capacity_note"] = "₹5 lakh order > 5 % of the day's turnover – fill doubtful"
        r.update(_depth(e, symbol=s["symbol"]))
        # research-equivalent on weekly bars + daily execution path
        if Wk is None:
            Wk = WEEKLY
        k = s["key"]; wc = Wk["close"][k]; ok = wc.notna().values; wi = Wk["close"].index[ok]
        b = pd.DataFrame(dict(time=wi, **{f: Wk[f][k].values[ok] for f in ("open", "high", "low", "close")}))
        for col in ("open", "high", "low"):
            b[col] = b[col].where(b[col] > 0).fillna(b["close"])
        i = int(np.where(b.time == sd)[0][0])
        if i + 1 < len(b):
            w = RU.walk(b.open.values, b.high.values, b.low.values, b.close.values, i + 1, 1, s["risk"], p["target_R"], p["max_bars"])
            cR = p["cost_round_trip"] * b.open.iloc[i + 1] / s["risk"]
            r.update(research_status="closed" if w["done"] else "open", research_reason=w["reason"], research_R=round(w["gross_R"] - cR, 4),
                     research_exit=b.time.iloc[w["exit_i"]])
            busy[s["symbol"]] = b.time.iloc[w["exit_i"]] if w["done"] else pd.Timestamp("2100-01-01")
        # execution: daily adjusted bars from the entry day until the end of the 10th week
        dd = a[a["time"] >= e].reset_index(drop=True)
        wk_end = b.time.iloc[min(i + p["max_bars"], len(b) - 1)] if i + 1 < len(b) else dd.time.iloc[-1]
        dd = dd[dd.time <= wk_end].reset_index(drop=True)
        slip = p["slip_per_side"]; o0 = float(dd.open.iloc[0]); fill = o0 * (1 + slip)
        stop, tgt = o0 - s["risk"], o0 + p["target_R"] * s["risk"]
        hold = len(dd) if (i + p["max_bars"] < len(b)) else 10 ** 6
        w = RU.walk(dd.open.values, dd.high.values, dd.low.values, dd.close.values, 0, 1, s["risk"], p["target_R"], hold)
        done = w["done"] and (w["reason"] != "time" or i + p["max_bars"] < len(b))
        xpx = w["exit_px"] * (1 - slip)
        net = xpx - fill - (p["cost_round_trip"] - 2 * 0.0005) * o0           # delivery fees without the research slippage
        f_ = ed["close"] / raw[3] if raw is not None and raw[3] else 1.0
        r.update(entry_px=round(fill, 2), stop_px=round(stop, 2), target_px=round(tgt, 2),
                 status=("ACTIVE" if not done else {"target": "TARGET HIT", "target (gap)": "TARGET HIT (gap)", "stop": "STOP HIT",
                                                    "stop (gap)": "STOP HIT (gap through stop)", "time": "TIME EXIT (10 weeks)"}[w["reason"]]),
                 exit_date=dd.time.iloc[w["exit_i"]] if done else None, exit_px=round(w["exit_px"], 2) if done else None,
                 last_px=round(float(dd.close.iloc[-1]), 2), sessions=w["bars"], mfe_R=round(w["mfe_R"], 3), mae_R=round(w["mae_R"], 3),
                 exec_R=round(net / s["risk"], 4), exec_net_pct=round(100 * net / o0, 3), pnl_per_100_shares_rs=round(100 * net, 0))
        out.append(r)
    return pd.DataFrame(out)


P_RAW, WEEKLY = {}, None     # filled by run.py (raw cash rows of entry days; weekly panels)
