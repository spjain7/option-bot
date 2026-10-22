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


def test_quality_gold_case():
    """The 22-Oct GOLD 15-min BUY that hit SL: strong downtrend (ADX 34), no support nearby, volume 0.99x."""
    sig = dict(trend="DOWN", adx=34.0, atr=150.0, close=144385.0, vol_x=0.99,
               patterns=["Bullish reversal close (strong green candle closed above the previous high)"],
               levels=dict(support=[], resistance=[(145026.0, "pivot S2"), (145525.0, "prev-day low")]))
    q = S.quality(sig, "BUY")
    check("GOLD 22-Oct case is now suppressed (falling knife, no support, weak volume)",
          len(q) == 3 and any("falling knife" in x for x in q) and any("support" in x for x in q) and any("volume" in x for x in q))
    ok = dict(sig, trend="DOWN", adx=22.0, vol_x=1.8, patterns=["Hammer"], levels=dict(support=[(144300.0, "prev-day low")], resistance=[]))
    check("a hammer at support with 1.8x volume in a weak trend still passes", S.quality(ok, "BUY") == [])
    sell = dict(ok, trend="UP", adx=40.0, levels=dict(support=[], resistance=[(150000.0, "swing high")]), close=144385.0)
    check("SELL against a strong uptrend far from resistance is suppressed", any("falling knife" in x for x in S.quality(sell, "SELL")))


def _series(n=300, drift=0.0, seed=1):
    rng = np.random.default_rng(seed)
    t = [x for x in pd.date_range("2026-09-01", periods=n * 3, freq="15min") if 9 <= x.hour < 23 and x.weekday() < 5][:n]
    c = 1000 * np.exp(np.cumsum(rng.normal(drift, 0.002, n)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame(dict(time=t, open=o, high=np.maximum(o, c) * 1.001, low=np.minimum(o, c) * 0.999, close=c, volume=1000.0))


def test_rsi_direction():
    d = _series()
    _q = S.quality
    S.quality = lambda sig, side: []          # this test is about RSI direction only
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
    S.quality = _q


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


def _trend(n=260, up=True):
    t = pd.date_range("2026-01-01", periods=n, freq="3h")
    c = np.linspace(100, 200, n) if up else np.linspace(200, 100, n)
    c = c + np.sin(np.arange(n)) * 2
    return pd.DataFrame(dict(time=t, open=c - 0.5, high=c + 1.5, low=c - 1.5, close=c, volume=1000.0))


def test_breakout():
    from alerts import breakout as BO
    d = _trend()
    d.loc[d.index[-1], ["close", "high", "volume"]] = [d["high"].iloc[-21:-1].max() + 3, d["high"].iloc[-21:-1].max() + 4, 2500.0]
    check("volume breakout: close above 20-candle high, volume 2.5× and above EMA200 -> BUY", BO.evaluate(d)["side"] == "BUY")
    d2 = d.copy(); d2.loc[d2.index[-1], "volume"] = 1200.0
    check("same breakout on 1.2× volume -> no call (volume filter)", BO.evaluate(d2)["side"] is None and "volume" in BO.evaluate(d2)["why"])
    dn = _trend(up=False)
    dn.loc[dn.index[-1], ["close", "high", "volume"]] = [dn["high"].iloc[-21:-1].max() + 3, dn["high"].iloc[-21:-1].max() + 4, 2500.0]
    check("upside breakout below EMA200 (down-trend) -> no BUY", BO.evaluate(dn)["side"] != "BUY")
    st = dict(bo_active=[dict(name="GOLD", tf="3h", side="BUY", entry=100.0, stop=96.0, risk=4.0, best=100.0, trailed=False, n=0,
                              last_candle="2026-03-01 09:00:00", checked="2026-03-01 09:00:00", contract="X")],
              day=dict(outcomes=[]))
    fr = pd.DataFrame(dict(time=pd.to_datetime(["2026-03-01 09:00", "2026-03-01 12:00"]), open=[100, 105], high=[101, 112], low=[99, 104],
                           close=[100, 111], volume=[1.0, 1.0]))
    pre = pd.DataFrame(dict(time=pd.date_range("2026-02-20", periods=30, freq="3h"), open=100.0, high=101.0, low=99.0, close=100.0, volume=1.0))
    fr = pd.concat([pre, fr], ignore_index=True)
    msgs = []
    BO.manage(st, msgs, "GOLD", "3h", fr, None, pd.Timestamp("2026-03-01 15:05"))
    check("trailing stop raised after a new higher close and an update is sent", st["bo_active"][0]["stop"] > 96 and any("TRAIL UPDATE" in m for m in msgs))
    c15 = pd.DataFrame(dict(time=pd.to_datetime(["2026-03-01 15:15"]), open=[110], high=[110], low=[st["bo_active"][0]["stop"] - 1], close=[105], volume=[1.0]))
    BO.manage(st, msgs, "GOLD", "3h", fr, c15, pd.Timestamp("2026-03-01 15:35"))
    check("trailing stop hit -> EXIT message with result in R, alert closed", not st["bo_active"] and any("EXIT" in m and "R" in m for m in msgs))
    sig = dict(side="BUY", candle="2026-03-01 12:00", close=111.0, hh=108.0, ll=90.0, ema200=100.0, atr=2.0, vol_x=2.1, adx=30.0, rsi=65.0)
    lv = dict(support=[(108.0, "swing high")], resistance=[(115.0, "pivot R1")])
    m = BO.call_msg("GOLD", "MCX", dict(symbol="GOLD04DEC26FUT", expiry="2026-12-04"), "3h", sig, lv)
    check("call card: entry, no-chase, SL, T1/T2/T3, trailing, support/resistance",
          all(k in m for k in ("Entry", "chase", "Stop loss", "Target 1", "Target 2", "Target 3", "Trailing", "Resistance", "Support")))
    w = BO.reason_msg("GOLD", "3h", sig, lv, dict(oi=16500, chg_pct=0.8, gap_min=15, label="Long buildup"), None)
    check("separate WHY message: breakout, volume, trend, ADX, RSI, OI, next level, backtest note",
          all(k in w for k in ("WHY THIS BUY", "Breakout", "Volume", "200 EMA", "ADX", "RSI", "OI", "Long buildup", "Backtest")))


def test_stocks():
    from alerts import stocks as STK
    m = pd.DataFrame([dict(name="TCS", exch_seg="NFO", instrumenttype="FUTSTK", symbol="TCS27OCT26FUT", token="1", lotsize=175, expiry_dt=pd.Timestamp("2026-10-27")),
                      dict(name="TCS", exch_seg="NFO", instrumenttype="FUTSTK", symbol="TCS24NOV26FUT", token="2", lotsize=175, expiry_dt=pd.Timestamp("2026-11-24")),
                      dict(name="IDEA", exch_seg="NFO", instrumenttype="FUTSTK", symbol="IDEA27OCT26FUT", token="3", lotsize=70000, expiry_dt=pd.Timestamp("2026-10-27"))])
    u = STK.universe(m, pd.Timestamp("2026-10-15 12:20"))
    check("stock universe: lot size < 3000 only (IDEA 70,000 excluded)", list(u) == ["TCS"] and u["TCS"]["lot"] == 175)
    check("stock contract rolls to next month within 2 trading days of expiry", STK.universe(m, pd.Timestamp("2026-10-26 12:20"))["TCS"]["symbol"] == "TCS24NOV26FUT")
    check("OI ignored around expiry (rollover window) but used mid-month", STK.in_rollover_window("2026-10-26") and STK.in_rollover_window("2026-10-29")
          and not STK.in_rollover_window("2026-10-15"))
    days = list(pd.bdate_range("2025-09-01", "2026-10-15"))
    rows, px = [], 1000.0
    for d in days:
        for hh, mm in ((9, 15), (10, 15), (11, 15), (12, 15), (13, 15), (14, 15), (15, 15)):
            px *= 1.0003
            rows.append(dict(time=d + pd.Timedelta(hours=hh, minutes=mm), open=px, high=px * 1.002, low=px * 0.998, close=px, volume=1000.0))
    h = pd.DataFrame(rows)
    last = h["time"].dt.normalize() == pd.Timestamp("2026-10-15")
    h.loc[last, ["close", "high"]] = [px * 1.06, px * 1.061]
    h.loc[last, "volume"] = 4000.0
    oi = pd.DataFrame(dict(time=[d for d in days[-60:]], oi=[1e6] * 59 + [1.05e6]))

    class Api(F.FakeAngel):
        def __init__(self, oi_df, **k):
            super().__init__(**k); self.oi_df = oi_df
        def oi_history(self, ex, tok, iv, frm, to):
            return self.oi_df
    api = Api(oi, series={("1", "ONE_HOUR"): h}, now=pd.Timestamp("2026-10-15 15:32"))
    st = E.new_state(); st["day"] = dict(date="2026-10-15", alerts=0, watches=0, startup_sent=True, eod_sent=False, outcomes=[])
    import sys
    msgs, rep = [], dict(errors=[])
    STK.scan(api, m, pd.Timestamp("2026-10-15 12:17"), st, msgs, rep, sys.modules["alerts.engine"])
    check("no stock scan at the 12:15 block (daily rule runs after the 15:30 close)", not msgs)
    STK.scan(api, m, pd.Timestamp("2026-10-15 15:32"), st, msgs, rep, sys.modules["alerts.engine"])
    check("OI-confirmed breakout -> BUY call (lot size) + WHY message with LONG BUILDUP",
          any("BUY | TCS FUT" in x and "Lot size: 175" in x for x in msgs) and any("WHY THIS BUY – TCS" in x and "LONG BUILDUP" in x for x in msgs))
    msgs2 = []
    STK.scan(api, m, pd.Timestamp("2026-10-15 15:47"), st, msgs2, rep, sys.modules["alerts.engine"])
    check("no duplicate stock call later the same day", not any("BUY |" in x for x in msgs2))
    api2 = Api(oi.assign(oi=[1e6] * 60), series={("1", "ONE_HOUR"): h}, now=pd.Timestamp("2026-10-15 15:32"))
    st2 = E.new_state(); st2["day"] = dict(date="2026-10-15", alerts=0, watches=0, startup_sent=True, eod_sent=False, outcomes=[])
    m3 = []
    STK.scan(api2, m, pd.Timestamp("2026-10-15 15:32"), st2, m3, dict(errors=[]), sys.modules["alerts.engine"])
    check("same breakout WITHOUT an OI rise -> no call (OI confirmation required)", not any("BUY |" in x for x in m3))


def test_no_orders():
    src = "\n".join(f.read_text() for f in (ROOT / "alerts").rglob("*.py") if "tests" not in f.parts)
    check("alerts package has no order API (alert-only, no auto trading)", not re.search(r"placeOrder|modifyOrder|cancelOrder|place_order", src))
    wf = (ROOT / ".github" / "workflows" / "alerts.yml").read_text()
    check("workflow: own concurrency group, Telegram sent after state push", "group: buy-sell-alerts" in wf
          and wf.index("Save state") < wf.index("alerts.run flush"))


if __name__ == "__main__":
    for t in (test_patterns, test_bounce, test_quality_gold_case, test_rsi_direction, test_sessions_and_candles, test_engine_replay, test_follow_up, test_levels_and_oi, test_breakout, test_stocks, test_no_orders):
        t()
    print(f"\nALL {len(OK)} ALERT CHECKS PASSED")
