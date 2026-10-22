"""Offline tests for the BUY/SELL alert engine. Run: python -m alerts.tests.test_alerts"""
import re, sys
from pathlib import Path
from unittest import mock
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from alerts import signals as S, engine as E  # noqa: E402
from crude.tests import fake as F  # noqa: E402

OK = []


def check(name, cond):
    assert cond, name
    OK.append(name); print("✅", name)


def frame(rows):
    t = pd.date_range("2026-10-20 09:00", periods=len(rows), freq="15min")
    return pd.DataFrame([dict(time=t[i], open=o, high=h, low=l, close=c, volume=1000.0) for i, (o, h, l, c) in enumerate(rows)])


def test_patterns():
    b, s = S.patterns(frame([(100, 101, 99, 100), (102, 102.5, 98.5, 99), (98.8, 103, 98.5, 102.8)]), atr=2.0)
    check("bullish engulfing detected", "Bullish engulfing" in b and not s)
    b, s = S.patterns(frame([(100, 101, 99, 100), (98, 101.5, 97.5, 101), (101.2, 101.5, 97.5, 97.8)]), atr=2.0)
    check("bearish engulfing detected", "Bearish engulfing" in s and not b)
    b, s = S.patterns(frame([(100, 101, 99, 100), (100, 100.5, 99, 99.5), (99.5, 100.1, 96, 99.9)]), atr=2.0)
    check("hammer detected (long lower wick)", any(x.startswith("Hammer") for x in b))
    b, s = S.patterns(frame([(100, 101, 99, 100), (100, 101, 99.5, 100.5), (100.4, 104, 99.9, 100.1)]), atr=2.0)
    check("shooting star detected (long upper wick)", any(x.startswith("Shooting star") for x in s))
    b, s = S.patterns(frame([(100, 100.3, 99.7, 100), (100, 100.2, 99.9, 100.1), (100.1, 100.3, 99.9, 100.2)]), atr=2.0)
    check("tiny candles are not patterns (noise filter)", not b and not s)


def test_bounce():
    b, s = S.patterns(frame([(100, 100.5, 97, 97.5), (97.5, 98, 96, 96.5), (96.6, 99.2, 96.4, 99.0)]), atr=2.0)
    check("V-bounce: strong green candle closing above the previous high counts as bullish confirmation", any("reversal close" in x for x in b))


def _series(n=300, drift=0.0, seed=1):
    rng = np.random.default_rng(seed)
    t = [x for x in pd.date_range("2026-09-01", periods=n * 3, freq="15min") if 9 <= x.hour < 23 and x.weekday() < 5][:n]
    c = 1000 * np.exp(np.cumsum(rng.normal(drift, 0.002, n)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame(dict(time=t, open=o, high=np.maximum(o, c) * 1.001, low=np.minimum(o, c) * 0.999, close=c, volume=1000.0))


def test_rsi_direction():
    d = _series()
    with mock.patch.object(S.I, "rsi", lambda c, n=14: pd.Series(80.0, index=c.index)), \
         mock.patch.object(S, "patterns", lambda df, atr: ([], ["Bearish engulfing"])):
        r = S.evaluate(d, "15m")
    check("RSI > 75 + bearish candle -> SELL alert", r["kind"] == "SELL" and r["sl"] > r["entry"] > r["t1"] > r["t2"])
    with mock.patch.object(S.I, "rsi", lambda c, n=14: pd.Series(20.0, index=c.index)), \
         mock.patch.object(S, "patterns", lambda df, atr: (["Hammer"], [])):
        r = S.evaluate(d, "1h")
    check("RSI < 25 + bullish candle -> BUY alert", r["kind"] == "BUY" and r["sl"] < r["entry"] < r["t1"] < r["t2"])
    with mock.patch.object(S.I, "rsi", lambda c, n=14: pd.Series(80.0, index=c.index)), \
         mock.patch.object(S, "patterns", lambda df, atr: (["Hammer"], [])):
        r = S.evaluate(d, "15m")
    check("RSI > 75 never produces a BUY", r["kind"] not in ("BUY",))
    with mock.patch.object(S.I, "rsi", lambda c, n=14: pd.Series(20.0, index=c.index)), \
         mock.patch.object(S, "patterns", lambda df, atr: ([], ["Bearish engulfing"])):
        r = S.evaluate(d, "15m")
    check("RSI < 25 never produces a SELL", r["kind"] != "SELL")
    for v, exp in ((75.0, None), (75.1, "SELL"), (25.0, None), (24.9, "BUY")):
        with mock.patch.object(S.I, "rsi", lambda c, n=14, v=v: pd.Series(v, index=c.index)), \
             mock.patch.object(S, "patterns", lambda df, atr: (["Hammer"], ["Bearish engulfing"])):
            r = S.evaluate(d, "15m")
        assert (r["kind"] == exp) or (exp is None and r["kind"] not in ("BUY", "SELL")), (v, r["kind"])
    check("boundaries: 75.0 / 25.0 no alert, 75.1 SELL, 24.9 BUY", True)
    rs = pd.Series([50.0] * (len(d) - 1) + [22.0], index=d.index)
    with mock.patch.object(S.I, "rsi", lambda c, n=14: rs.iloc[:len(c)].set_axis(c.index)), \
         mock.patch.object(S, "patterns", lambda df, atr: ([], [])):
        r = S.evaluate(d, "15m")
    check("RSI just crossed below 25 without a reversal candle -> WATCH BUY (setup not missed)", r["kind"] == "WATCH_BUY")
    with mock.patch.object(S.I, "rsi", lambda c, n=14: pd.Series([50.0] * (len(c) - 3) + [22.0, 30.0, 35.0], index=c.index)), \
         mock.patch.object(S, "patterns", lambda df, atr: (["Bullish engulfing"], [])):
        r = S.evaluate(d, "15m")
    check("reversal candle up to 2 candles after the RSI extreme still gives the BUY alert", r["kind"] == "BUY")


def test_sessions_and_candles():
    now = pd.Timestamp("2026-10-21 14:10")
    d = _series(); d["time"] = pd.date_range(end="2026-10-21 14:00", periods=len(d), freq="15min")
    c = E.closed(d, "MCX", 15, now)
    check("forming candle dropped (alerts use closed candles only)", c["time"].iloc[-1] == pd.Timestamp("2026-10-21 13:45"))
    check("NSE session 09:15–15:30, MCX 09:00–23:30", E.is_open("NFO", pd.Timestamp("2026-10-21 15:20")) and not E.is_open("NFO", pd.Timestamp("2026-10-21 15:45"))
          and E.is_open("MCX", pd.Timestamp("2026-10-21 23:00")))
    h = pd.DataFrame(dict(time=pd.to_datetime([f"2026-10-21 {x}" for x in ("09:15", "10:15", "11:15", "12:15", "13:15", "14:15", "15:15")]),
                          open=range(7), high=range(1, 8), low=range(7), close=range(7), volume=1.0))
    p = E.positional_candles(h, "NFO", pd.Timestamp("2026-10-21 16:00"))
    check("NSE positional candles: 09:15–12:15 and 12:15–15:30", len(p) == 2 and p["close"].tolist() == [2, 6])
    check("unfinished NSE block not used", len(E.positional_candles(h.iloc[:5], "NFO", pd.Timestamp("2026-10-21 14:00"))) == 1)


def test_engine_replay():
    api = F.real_api(None)
    if ("573422", "FIFTEEN_MINUTE") not in api.series:
        return
    api.series[("573422", "ONE_HOUR")] = api.series[("573422", "ONE_HOUR")]
    st, sent, codes = E.new_state(), [], []
    for now in pd.date_range("2026-10-15 09:07", "2026-10-21 20:52", freq="15min"):
        if now.weekday() >= 5:
            continue
        api.now = now
        st, msgs, rep = E.scan(api, F.master(), now, st, only=["CRUDEOIL"])
        sent += msgs
    calls = [m for m in sent if " CALL – " in m]
    check("replay on real CRUDEOIL candles (6 sessions) runs and produces messages", len(sent) > 0)
    check("every BUY/SELL alert carries reasoning, entry, SL, targets and the no-auto-trade warning",
          all(all(k in m for k in ("Why this call:", "RSI(14)", "Stop loss", "Target 1", "Target 2", "Entry", "Support", "Resistance",
                                   "Volume", "OI", "Alert only")) for m in calls))
    watches = [m for m in sent if m.startswith("🟡 WATCH")]
    check("watch messages also carry trigger, provisional SL/targets, support/resistance, volume and OI",
          all(all(k in m for k in ("Possible", "SL ~", "T1 ~", "Support", "Resistance", "Volume", "OI")) for m in watches))
    ids = st["seen"]
    check("no duplicate alerts for the same candle", len(ids) == len(set(ids)))
    check("daily startup message sent once per day", sum("ALERTS ACTIVE" in m for m in sent) <= 6)
    print(f"   (replay: {len(calls)} BUY/SELL alerts, {sum('WATCH' in m for m in sent)} watch messages, "
          f"{sum(('T1 hit' in m) or ('SL hit' in m) or ('T2 hit' in m) for m in sent)} follow-ups)")


def test_follow_up():
    st = E.new_state(); st["day"] = dict(date="2026-10-21", alerts=0, watches=0, startup_sent=True, eod_sent=False, outcomes=[])
    st["active"] = [dict(id="CRUDEOIL|15m|2026-10-21 10:00:00|BUY", name="CRUDEOIL", ex="MCX", tf="15m", side="BUY", entry=100.0,
                         sl=98.0, t1=102.0, t2=104.0, time="2026-10-21 10:00:00", t1_hit=False, contract="X", expiry="2026-11-19")]
    bars = frame([(100, 102.5, 99.5, 102), (102, 102.2, 99.9, 100.5)])
    bars["time"] = pd.to_datetime(["2026-10-21 10:15", "2026-10-21 10:30"])
    msgs = []
    E._follow_up(st, msgs, "CRUDEOIL", "MCX", bars, pd.Timestamp("2026-10-21 10:50"))
    check("follow-up: T1 hit message, then exit at cost when price returns to entry",
          any("T1 hit" in m for m in msgs) and any("Exit at cost" in m for m in msgs) and not st["active"])


def test_levels_and_oi():
    d = _series(400)
    h = d.groupby(d["time"].dt.floor("h")).agg(time=("time", "first"), open=("open", "first"), high=("high", "max"),
                                                low=("low", "min"), close=("close", "last"), volume=("volume", "sum")).reset_index(drop=True)
    px = float(d["close"].iloc[-1])
    lv = S.levels(d, h, px, 2.0)
    check("supports are below price and resistances above it (nearest first)",
          all(v < px for v, _ in lv["support"]) and all(v > px for v, _ in lv["resistance"])
          and lv["support"] == sorted(lv["support"], key=lambda x: -x[0]) and lv["resistance"] == sorted(lv["resistance"]))
    st = {}
    now = pd.Timestamp("2026-10-21 14:02")
    a = E.oi_reading(st, "X", dict(opnInterest=100000, ltp=100.0), now)
    check("first OI reading: current OI shown, change marked unavailable (never zero)", a["oi"] == 100000 and a["chg_pct"] is None)
    b = E.oi_reading(st, "X", dict(opnInterest=101000, ltp=101.0), now + pd.Timedelta(minutes=15))
    check("OI change from two real readings 15 min apart: price up + OI up = Long buildup", round(b["chg_pct"], 2) == 1.0 and b["label"] == "Long buildup")
    check("missing OI in the quote -> None, not 0", E.oi_reading(st, "Y", dict(ltp=5.0), now) is None)


def test_no_orders():
    src = "\n".join(f.read_text() for f in (ROOT / "alerts").rglob("*.py") if "tests" not in f.parts)
    check("alerts package has no order API (alert-only, no auto trading)", not re.search(r"placeOrder|modifyOrder|cancelOrder|place_order", src))
    wf = (ROOT / ".github" / "workflows" / "alerts.yml").read_text()
    check("workflow: own concurrency group, Telegram sent after state push", "group: buy-sell-alerts" in wf
          and wf.index("Save state") < wf.index("alerts.run flush"))


if __name__ == "__main__":
    for t in (test_patterns, test_bounce, test_rsi_direction, test_sessions_and_candles, test_engine_replay, test_follow_up, test_levels_and_oi, test_no_orders):
        t()
    print(f"\nALL {len(OK)} ALERT CHECKS PASSED")
