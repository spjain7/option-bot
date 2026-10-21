"""Offline tests for the Crude Oil PAPER engine (crude/). Run: python -m crude.tests.test_crude"""
import json, os, re, sys, tempfile
from pathlib import Path
from unittest import mock
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import config as K, data as D, rules as R, paper as P, engine as E, report as REP, indicators as I  # noqa
from crude.tests import fake as F  # noqa

OK = []


def check(name, cond):
    assert cond, name
    OK.append(name); print("✅", name)


# ─────────────── synthetic candles ───────────────
def bars15(n=900, drift=0.0, end="2026-10-21 14:00", price=6000.0, seed=1, noise=0.0012):
    rng = np.random.default_rng(seed)
    t = [x for x in pd.date_range(pd.Timestamp(end) - pd.Timedelta(days=40), end, freq="15min")
         if x.weekday() < 5 and 9 <= x.hour < 23][-n:]
    c = price * np.exp(np.cumsum(rng.normal(drift, noise, len(t))))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame(dict(time=t, open=o, high=np.maximum(o, c) * 1.0008, low=np.minimum(o, c) * 0.9992, close=c,
                             volume=rng.integers(800, 1200, len(t)).astype(float)))


def to_h1(d):
    g = d.groupby(d["time"].dt.floor("h"))
    return g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                 volume=("volume", "sum")).reset_index()


def breakout(d, side="BUY"):
    """Make the last candle a clean breakout with strong close and high volume."""
    d = d.copy()
    s = 1 if side == "BUY" else -1
    a = float(I.atr(d).iloc[-1])
    lvl = d["high"].iloc[-9:-1].max() if s > 0 else d["low"].iloc[-9:-1].min()
    o = lvl - s * 0.2 * a
    c = lvl + s * 0.6 * a
    d.loc[d.index[-1], ["open", "close"]] = [o, c]
    d.loc[d.index[-1], "high"] = max(o, c) + 0.05 * a
    d.loc[d.index[-1], "low"] = min(o, c) - 0.05 * a
    d.loc[d.index[-1], "volume"] = 5000.0
    return d


# ─────────────── RSI boundaries ───────────────
def test_rsi_boundaries():
    P_ = K.INTRA
    check("RSI 24.99 blocks BUY", R._rsi_block("BUY", 24.99, P_) is not None)
    check("RSI exactly 25 does NOT block BUY", R._rsi_block("BUY", 25.0, P_) is None)
    check("RSI 75.01 blocks SELL", R._rsi_block("SELL", 75.01, P_) is not None)
    check("RSI exactly 75 does NOT block SELL", R._rsi_block("SELL", 75.0, P_) is None)
    check("RSI 90 does not block BUY and RSI 10 does not block SELL (only the stated restrictions)",
          R._rsi_block("BUY", 90, P_) is None and R._rsi_block("SELL", 10, P_) is None)
    up = breakout(bars15(drift=0.0004, seed=3), "BUY")
    h1 = to_h1(up)
    with mock.patch.object(R.I, "rsi", lambda c, n=14: pd.Series(20.0, index=c.index)):
        d = R.intraday(up, h1)
    check("integration: BUY breakout with RSI 20 is BLOCKED, never turned into a SELL",
          d["decision"] == "BLOCKED" and d["side"] == "BUY" and any("RSI 20.0 < 25" in b for b in d["blocks"]))
    dn = breakout(bars15(drift=-0.0004, seed=3), "SELL")
    with mock.patch.object(R.I, "rsi", lambda c, n=14: pd.Series(80.0, index=c.index)):
        d2 = R.intraday(dn, to_h1(dn))
    check("integration: SELL breakdown with RSI 80 is BLOCKED (side stays SELL)",
          d2["decision"] == "BLOCKED" and d2["side"] == "SELL" and any("> 75 blocks SELL" in b for b in d2["blocks"]))
    with mock.patch.object(R.I, "rsi", lambda c, n=14: pd.Series(80.0, index=c.index)):
        d3 = R.intraday(up, h1)
    check("integration: RSI 80 does not block a BUY", not any("RSI" in b for b in d3.get("blocks", [])))
    c3 = D.three_hour(h1)
    with mock.patch.object(R.I, "rsi", lambda c, n=14: pd.Series(20.0, index=c.index)):
        p = R.positional(c3)
    check("positional applies the same RSI rule (BUY never allowed at RSI < 25)",
          p["decision"] != "SIGNAL" or p["side"] != "BUY")


# ─────────────── closed candles / timeframes ───────────────
def test_closed_candles_and_htf():
    d = bars15(n=200, end="2026-10-21 14:00")
    now = pd.Timestamp("2026-10-21 14:10")                 # 14:00 candle is forming
    c = D.closed(d, 15, now)
    check("forming 15-min candle is dropped", c["time"].iloc[-1] == pd.Timestamp("2026-10-21 13:45"))
    c2 = D.closed(d, 15, pd.Timestamp("2026-10-21 14:15:30"))
    check("a candle counts as closed only after the 60 s grace", c2["time"].iloc[-1] == pd.Timestamp("2026-10-21 13:45"))
    c3 = D.closed(d, 15, pd.Timestamp("2026-10-21 14:16:01"))
    check("…and is used once the grace has passed", c3["time"].iloc[-1] == pd.Timestamp("2026-10-21 14:00"))
    h = to_h1(d)
    hc = D.htf_closed_by(h, pd.Timestamp("2026-10-21 13:45"))
    check("1-hour confirmation uses only 1-hour candles closed by the 15-min candle's end (no look-ahead)",
          hc["time"].iloc[-1] == pd.Timestamp("2026-10-21 12:00"))
    last = pd.DataFrame(dict(time=[pd.Timestamp("2026-10-21 23:00")], open=[1.0], high=[1.0], low=[1.0], close=[1.0], volume=[1.0]))
    check("last 1-hour candle of the day ends at the session close (23:30 in US summer time)",
          D.bar_end(pd.Timestamp("2026-10-21 23:00"), 60) == pd.Timestamp("2026-10-21 23:30")
          and len(D.closed(last, 60, pd.Timestamp("2026-10-21 23:31:01"))) == 1)
    check("session close 23:55 in US winter time", D.session_close("2026-12-01") == pd.Timestamp("2026-12-01 23:55"))


def test_trend_conflict():
    d = breakout(bars15(drift=0.0004, seed=3), "BUY")
    h_down = to_h1(bars15(drift=-0.0005, seed=9))
    r = R.intraday(d, h_down)
    check("15-min BUY breakout is NOT taken when the 1-hour trend is DOWN (conflict)",
          r["decision"] == "NONE" or r.get("side") == "SELL")
    check("…and is never reversed into an extreme-RSI trade", r["decision"] != "SIGNAL" or r["side"] == "SELL")
    flat = bars15(drift=0.0, seed=11, noise=0.0004)
    r2 = R.intraday(flat, to_h1(flat))
    check("ranging/mixed 1-hour market -> no entry", r2["decision"] == "NONE")
    up = breakout(bars15(drift=0.0004, seed=3), "BUY")
    r3 = R.intraday(up, to_h1(up))
    check("aligned 15-min breakout + 1-hour uptrend is evaluated as a BUY setup", r3.get("side") == "BUY" and r3["decision"] in ("SIGNAL", "BLOCKED"))


def test_three_hour():
    day = pd.Timestamp("2026-10-21")
    t = [day + pd.Timedelta(hours=h) for h in range(9, 24)]
    h1 = pd.DataFrame(dict(time=t, open=np.arange(15) + 100.0, high=np.arange(15) + 101.0, low=np.arange(15) + 99.0,
                           close=np.arange(15) + 100.5, volume=np.ones(15) * 10))
    c = D.three_hour(h1)
    check("five 3-hour candles per MCX day: 09, 12, 15, 18, 21", list(c["time"].dt.hour) == [9, 12, 15, 18, 21])
    f = c.iloc[0]
    check("3-hour OHLCV = first open, max high, min low, last close, summed volume",
          f.open == 100 and f.high == 103 and f.low == 99 and f.close == 102.5 and f.volume == 30)
    check("last block 21:00 → close includes 21, 22, 23 h and ends at the session close",
          c.iloc[-1]["bars"] == 3 and c.iloc[-1]["end"] == pd.Timestamp("2026-10-21 23:30"))
    part = D.three_hour(h1, now=pd.Timestamp("2026-10-21 14:30"))
    check("an unfinished 3-hour block is not emitted", list(part["time"].dt.hour) == [9])
    gap = D.three_hour(h1.drop(index=[4]))                    # 13:00 missing
    check("a block missing an hourly candle is flagged incomplete", not bool(gap.loc[gap["time"].dt.hour == 12, "complete"].iloc[0]))
    p = R.positional(D.three_hour(to_h1(bars15(n=3000, drift=0.0002))).assign(complete=lambda x: x["complete"].astype(bool)))
    check("positional evaluates on 3-hour candles", "trend_3h" in p["metrics"] or "insufficient" in p["blocks"][0])


# ─────────────── OI / volume integrity ───────────────
def test_oi_and_volume():
    now = dict(time="2026-10-21 14:15:10", contract="X", oi=100500, ltp=101.0)
    u = D.oi_change([], "X", now)
    check("no earlier snapshot -> OI change UNAVAILABLE (not zero)", u["status"] == "UNAVAILABLE" and "d_oi_pct" not in u)
    m = D.oi_change([], "X", dict(now, oi=None))
    check("missing OI value -> UNAVAILABLE, never 0", m["status"] == "UNAVAILABLE")
    snaps = [dict(time="2026-10-21 14:00:05", contract="X", oi=100000, ltp=100.0)]
    k = D.oi_change(snaps, "X", now)
    check("price ↑ OI ↑ = Long buildup from two real snapshots 15 min apart", k["status"] == "OK" and k["label"] == "Long buildup")
    check("snapshot of another contract is never compared", D.oi_change(snaps, "Y", dict(now, contract="Y"))["status"] == "UNAVAILABLE")
    old = [dict(time="2026-10-21 12:00:00", contract="X", oi=100000, ltp=100.0)]
    check("snapshots too far apart (> 40 min) are not compared", D.oi_change(old, "X", now)["status"] == "UNAVAILABLE")
    for lbl, dp, doi in (("Short buildup", -1, +1), ("Long unwinding", -1, -1), ("Short covering", +1, -1)):
        r = D.oi_change(snaps, "X", dict(now, oi=100000 * (1 + doi * 0.01), ltp=100 + dp))
        check(f"classification: {lbl}", r["label"] == lbl)
    b, tag = R.oi_gate("BUY", dict(status="OK", label="Short buildup", d_oi_pct=1.0, d_price=-2, gap_min=15))
    check("OI contradicting a BUY blocks it", b is not None)
    with mock.patch.object(K, "OI_POLICY", "require"):
        b2, _ = R.oi_gate("BUY", dict(status="UNAVAILABLE", reason="x"))
    check("OI policy 'require': unavailable OI blocks entries", b2 is not None)
    b3, tag3 = R.oi_gate("BUY", dict(status="UNAVAILABLE", reason="x"))
    check("OI policy 'fallback': entry evaluated without OI and tagged UNAVAILABLE", b3 is None and tag3.startswith("UNAVAILABLE"))
    d = breakout(bars15(drift=0.0004, seed=3), "BUY")
    d["volume"] = 0.0
    r = R.intraday(d, to_h1(d))
    check("volume missing (all zero) -> entry blocked, not assumed", r["decision"] != "SIGNAL")
    check("no 'buying/selling volume' labels anywhere in crude/",
          not re.search(r"buying volume|selling volume|buy volume|sell volume", "\n".join(f.read_text().lower() for f in (ROOT / "crude").glob("*.py"))))


# ─────────────── fills, stops, targets, costs, sizing ───────────────
def _pos(side="BUY", engine="intraday"):
    plan = dict(stop_dist=50.0, target_r=2.0, atr=40.0)
    return P.open_position(engine, side, 1000.0, plan, 2, 10, 1.0, "CRUDEOILM", dict(id="t", time="2026-10-21 10:00", expiry="2026-11-19"))


def test_stops_targets():
    p = _pos()
    check("BUY: stop 950, target 1100", p["stop"] == 950 and p["target"] == 1100)
    r = P.step_bar(p, dict(open=940, high=960, low=930, close=950))
    check("gap through stop fills at the (worse) open minus slippage", r == (938.0, "gap through stop – filled at the open"))
    r = P.step_bar(_pos(), dict(open=1000, high=1150, low=940, close=1000))
    check("stop and target in the same candle -> stop assumed first", r[1] == "stop-loss" and r[0] == 948.0)
    r = P.step_bar(_pos(), dict(open=1000, high=1100, low=990, close=1050))
    check("target needs a trade THROUGH it by a tick", r is None)
    r = P.step_bar(_pos(), dict(open=1000, high=1101, low=990, close=1050))
    check("target fills at the target price", r == (1100, "target"))
    p = _pos()
    P.step_bar(p, dict(open=1000, high=1055, low=995, close=1052))
    check("intraday: breakeven after +1R (takes effect from the next candle)", p["stop"] == 1000 and p["be_moved"])
    s = _pos("SELL")
    check("SELL: stop above, target below", s["stop"] == 1050 and s["target"] == 900)
    q = _pos("BUY", "positional")
    P.step_bar(q, dict(open=1000, high=1065, low=995, close=1060))
    check("positional: trailing stop after +1R = best close − 3×ATR, only ever tightened",
          q["stop"] == 950 and P.step_bar(q, dict(open=1060, high=1099, low=1055, close=1098)) is None and q["stop"] == 1098 - 120
          and P.step_bar(q, dict(open=1098, high=1099, low=1090, close=1095)) is None and q["stop"] == 978)
    r = P.step_bar(_pos(), dict(open=1000, high=1200, low=900, close=1000), stop_only=True)
    check("entry candle: only the stop is checked (its earlier high happened before our fill)", r[1] == "stop-loss")


def test_costs_sizing():
    c = P.costs("BUY", 6000, 6100, 100)
    buy, sell = 600000, 610000
    exp = 40 + 0.0001 * sell + 0.000026 * (buy + sell) + 0.000001 * (buy + sell) + 0.00002 * buy + 0.18 * (40 + 0.000026 * (buy + sell) + 0.000001 * (buy + sell))
    check("charges = brokerage + CTT(sell) + exchange + SEBI + stamp(buy) + GST", abs(c - round(exp, 2)) < 0.01)
    check("cost stress multiplies charges", abs(P.costs("BUY", 6000, 6100, 100, 2.0) - 2 * c) < 0.02)
    lots, budget, per_lot = P.size(500000, 50, 9000, 10, 1.0)
    check("0.25% risk budget = ₹1,250", budget == 1250)
    check("lots = floor(budget / (stop+slippage)×₹/pt + charges)", lots == int(1250 // per_lot) and lots == 2)
    lots0, _, _ = P.size(500000, 200, 9000, 10, 1.0)
    check("stop too wide for 1 lot -> 0 lots (trade ignored, never forced)", lots0 == 0)
    check("slippage: entries pay up, exits receive less", P.slip("BUY", 100, 1, True) == 102 and P.slip("BUY", 100, 1, False) == 98
          and P.slip("SELL", 100, 1, True) == 98)
    t = P.close_position(_pos(), 1100, "target", "2026-10-21 12:00")
    check("closed trade P&L is net of charges and R uses the initial risk", t["pnl"] == round(2000 - t["charges"], 2) and abs(t["r"] - t["pnl"] / 1000) < 1e-3)


# ─────────────── sessions, contracts, expiry ───────────────
def test_session_expiry():
    m = F.master()
    for sym, e in (("CRUDEOIL19NOV26FUT", "2026-11-19"), ("CRUDEOIL18DEC26FUT", "2026-12-18"), ("CRUDEOIL19JAN27FUT", "2027-01-19")):
        ts = pd.Timestamp(e)
        assert D.crude_expiry(ts.year, ts.month) == ts, sym
    extra = [(2027, 2, 19), (2027, 3, 19), (2027, 4, 19), (2027, 6, 21), (2027, 9, 20), (2027, 12, 17), (2028, 3, 20)]
    check("expiry rule reproduces every listed CRUDEOIL expiry (Nov-26 … Mar-28)",
          all(D.crude_expiry(y, mo) == pd.Timestamp(y, mo, dd) for y, mo, dd in extra))
    r = D.resolve(m, pd.Timestamp("2026-10-21 10:00"))
    check("front contract traded far from expiry; mini contract matched by month; lot/tick verified",
          r["signal"]["symbol"] == "CRUDEOIL19NOV26FUT" and r["trade"]["symbol"] == "CRUDEOILM19NOV26FUT" and not r["issues"]
          and r["trade"]["tick"] == 1.0)
    r2 = D.resolve(m, pd.Timestamp("2026-11-16 10:00"))
    check("inside the roll window (≤ 4 trading days) the next contract is used", r2["rolled"] and r2["signal"]["symbol"] == "CRUDEOIL18DEC26FUT"
          and r2["trade"]["symbol"] == "CRUDEOILM18DEC26FUT")
    bad = F.master()
    bad.loc[bad["symbol"] == "CRUDEOILM19NOV26FUT", "lotsize"] = 1
    check("lot size mismatch vs configured ₹/pt is reported as an issue", D.resolve(bad, pd.Timestamp("2026-10-21 10:00"))["issues"])
    check("session status", D.session_status(pd.Timestamp("2026-10-24 12:00")).startswith("CLOSED")
          and D.session_status(pd.Timestamp("2026-10-21 08:30")) == "PRE-OPEN" and D.session_status(pd.Timestamp("2026-10-21 12:00")) == "OPEN")
    n = F.load("CRUDEOIL19NOV26FUT", "ONE_HOUR"); x = F.load("CRUDEOIL18DEC26FUT", "ONE_HOUR")
    if n is not None and x is not None:
        sw = D.detect_switches(n, x, "2026-11-19")
        meas = {str(t.date()): s for t, s, q in sw if q == "measured"}
        check("roll switches measured from the real overlap with the next contract (22-Sep, 20-Oct-2026)",
              "2026-09-22" in meas and "2026-10-20" in meas)
        a = D.continuity(n, sw)
        check("back-adjusted series has no jump at the switch and drops unverifiable older history",
              a["time"].min() > pd.Timestamp("2026-08-20") and a.loc[a["time"] >= pd.Timestamp("2026-10-20"), "offset"].eq(0).all())


# ─────────────── engine: duplicates, state, failures, status ───────────────
def _engine_run(now, api, sp, mode="scan", allow_new=True):
    api.now = pd.Timestamp(now)
    return E.scan(api, F.master(), pd.Timestamp(now), mode=mode, state_path=sp, allow_new=allow_new)


def test_engine_flow():
    sp = Path(tempfile.mkdtemp()) / "state.json"
    api = F.real_api(None)
    if ("573422", "FIFTEEN_MINUTE") not in api.series:
        print("(skipping engine replay: research data not present)"); return
    rec, out, code = _engine_run("2026-10-21 11:17", api, sp)
    check("scan on real recorded data: code 0, health queued first", code == 0 and out and "STARTUP" in out[0])
    st = json.loads(sp.read_text())
    n_open = len(st["engines"]["intraday"]["open"])
    rec2, out2, code2 = _engine_run("2026-10-21 11:19", api, sp)
    st2 = json.loads(sp.read_text())
    check("same candle re-scanned -> no second evaluation, no duplicate position",
          len(st2["engines"]["intraday"]["open"]) == n_open and not rec2["decisions"]["intraday"]["new_candle"])
    check("state restored across runs (open positions, counters persist)", st2["day"]["generated"] == st["day"]["generated"])
    rec3, out3, _ = _engine_run("2026-10-21 11:33", api, sp, mode="health")
    st3 = json.loads(sp.read_text())
    check("health mode never changes state", st3 == st2 and "HEALTH CHECK" in out3[0])
    for field in ("IST", "PAPER", "Session:", "Contract:", "Last closed candles:", "Freshness:", "Volume:", "OI now:", "OI change:",
                  "Trend:", "RSI(14):", "Today: signals", "Open paper positions" if not st3["engines"]["intraday"]["open"] else "Open:", "Day P&L", "Errors this run"):
        assert field in out3[0], field
    check("health message carries every required status field", True)
    # failed data fetch
    api_bad = F.real_api(None); api_bad.fail = {"candles"}
    rec4, out4, code4 = _engine_run("2026-10-21 12:02", api_bad, sp)
    check("candle fetch failure during the session -> FAILED status, non-zero exit, error alert, no entries",
          code4 == 2 and any("FAILED" in v for v in rec4["api"].values()) and any("problem" in m.lower() or "data" in m.lower() for m in out4))
    # failed state save
    ro = Path(tempfile.mkdtemp()) / "sub"
    ro.mkdir(); (ro / "state.json").write_text(sp.read_text())
    os.chmod(ro, 0o500)
    try:
        rec5, out5, code5 = _engine_run("2026-10-21 12:17", F.real_api(None), ro / "state.json")
        writable = os.access(ro, os.W_OK)
    finally:
        os.chmod(ro, 0o700)
    if not writable:
        check("state save failure -> exit 3 and only a 'STATE SAVE FAILED' message (no success report)",
              code5 == 3 and len(out5) == 1 and "STATE SAVE FAILED" in out5[0])
    else:
        with mock.patch.object(P, "save", side_effect=P.StateError("disk full")):
            rec5, out5, code5 = _engine_run("2026-10-21 12:17", F.real_api(None), sp)
        check("state save failure -> exit 3 and only a 'STATE SAVE FAILED' message (no success report)",
              code5 == 3 and len(out5) == 1 and "STATE SAVE FAILED" in out5[0])
    # end-of-day summary for the previous session is not lost when the first later scan is already the next date
    st = json.loads(sp.read_text()); st["day"]["date"] = "2026-10-20"; st["day"]["eod_sent"] = False
    sp.write_text(json.dumps(st))
    r8, o8, c8 = _engine_run("2026-10-21 13:02", F.real_api(None), sp)
    check("previous day's end-of-day summary sent once on the next date (winter close 23:55)",
          sum("END OF DAY 20-Oct-2026" in m for m in o8) == 1 and json.loads(sp.read_text())["day"]["date"] == "2026-10-21")
    # missing / corrupt state
    r6, o6, c6 = _engine_run("2026-10-21 12:17", F.real_api(None), Path(tempfile.mkdtemp()) / "none.json", allow_new=False)
    check("missing state without permission to create -> stops (no silent reset)", c6 == 3 and "STATE LOAD FAILED" in o6[0])
    bad = Path(tempfile.mkdtemp()) / "s.json"; bad.write_text("{not json")
    r7, o7, c7 = _engine_run("2026-10-21 12:17", F.real_api(None), bad)
    check("corrupt state -> stops with an error, file untouched", c7 == 3 and bad.read_text() == "{not json")


def test_replay_day():
    """Replay a full real session (21-Oct-2026) every 15 minutes: every scan succeeds, each candle evaluated once."""
    sp = Path(tempfile.mkdtemp()) / "state.json"
    api = F.real_api(None)
    if ("573422", "FIFTEEN_MINUTE") not in api.series:
        return
    codes, bars = [], []
    for now in pd.date_range("2026-10-21 09:07", "2026-10-21 21:07", freq="15min"):
        rec, out, code = _engine_run(now, api, sp)
        codes.append(code)
        d = rec["decisions"].get("intraday", {})
        if d.get("new_candle"):
            bars.append(d.get("bar_time"))
    st = json.loads(sp.read_text())
    check("12-hour replay: all scans exit 0", set(codes) == {0})
    check("each 15-min candle evaluated at most once", len(bars) == len(set(bars)))
    check("at most 1 open position per engine at any time", all(len(e["open"]) <= 1 for e in st["engines"].values()))
    ids = [t["id"] for e in st["engines"].values() for t in e["closed"]] + [p["id"] for e in st["engines"].values() for p in e["open"]]
    check("no signal id traded twice", len(ids) == len(set(ids)))


# ─────────────── telegram flush & workflow ───────────────
def test_flush_and_workflow():
    from crude import run as RUN
    sd = Path(tempfile.mkdtemp())
    with mock.patch.object(RUN, "OUTBOX", sd / "outbox.json"):
        (sd / "outbox.json").write_text(json.dumps(dict(messages=["hello"], code=0)))
        sent = []
        with mock.patch.object(RUN, "telegram", lambda t: (sent.append(t) or (True, "ok"))), \
             mock.patch.dict(os.environ, {"CRUDE_TELEGRAM": "1", "SAVE_OK": "failure"}):
            rc = RUN.flush()
        check("state push failed -> Telegram says STATE SAVE FAILED instead of the normal messages",
              rc == 0 and len(sent) == 1 and "STATE SAVE FAILED" in sent[0])
        with mock.patch.object(RUN, "telegram", lambda t: (False, "HTTP 401")), \
             mock.patch.dict(os.environ, {"CRUDE_TELEGRAM": "1", "SAVE_OK": "success"}):
            rc = RUN.flush()
        check("Telegram delivery failure makes the step fail (visible in GitHub)", rc == 1)
        (sd / "outbox.json").unlink()
        with mock.patch.object(RUN, "telegram", lambda t: (True, "ok")), mock.patch.dict(os.environ, {"CRUDE_TELEGRAM": "1"}):
            check("scan step crashed before writing a result -> flush fails", RUN.flush() == 1)
    with mock.patch("requests.post", side_effect=RuntimeError("boom")), \
         mock.patch.dict(os.environ, {"TELEGRAM_TOKEN": "SECRET123", "TELEGRAM_CHAT_ID": "1"}):
        ok, d = RUN.telegram("x")
    check("telegram error detail never contains the token", not ok and "SECRET123" not in d)
    wf = (ROOT / ".github" / "workflows" / "crude-paper.yml").read_text()
    check("workflow: own concurrency group, never cancels runs", "group: crude-paper" in wf and "cancel-in-progress: false" in wf)
    check("workflow: tests run before the scan, Telegram is flushed only after the state push",
          wf.index("python -m crude.tests.test_crude") < wf.index('python -m crude.run "$MODE"') < wf.index("name: Save state")
          < wf.index("python -m crude.run flush"))
    check("workflow: SAVE_OK passed to the flush step and failure is not masked", "SAVE_OK" in wf and "|| true" not in wf)
    src = "\n".join(f.read_text() for f in (ROOT / "crude").rglob("*.py") if "tests" not in f.parts)
    check("no order API anywhere in crude/", not re.search(r"placeOrder|modifyOrder|cancelOrder|place_order|gtt", src, re.I))
    check("mode is PAPER", K.MODE == "PAPER")
    import config as C
    check("existing engines' switches untouched (Engine D on, Engine C off)", C.CALLS_ENABLED is True and C.MCXT_ENABLED is False)
    check("runner.py does not import or call the crude engine (independent)", "crude" not in (ROOT / "runner.py").read_text())


if __name__ == "__main__":
    for t in (test_rsi_boundaries, test_closed_candles_and_htf, test_trend_conflict, test_three_hour, test_oi_and_volume,
              test_stops_targets, test_costs_sizing, test_session_expiry, test_engine_flow, test_replay_day, test_flush_and_workflow):
        t()
    print(f"\nALL {len(OK)} CRUDE ENGINE CHECKS PASSED")
