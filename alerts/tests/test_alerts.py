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
    st["bo_active"][0]["tf"] = "1d"
    msgs = []
    BO.manage(st, msgs, "GOLD", "1d", fr, None, pd.Timestamp("2026-03-01 15:05"))
    check("daily call: no trailing (one stop, one target) – stop stays 96", st["bo_active"][0]["stop"] == 96 and not any("TRAIL" in m for m in msgs))
    c15 = pd.DataFrame(dict(time=pd.to_datetime(["2026-03-01 15:15"]), open=[110], high=[110], low=[st["bo_active"][0]["stop"] - 1], close=[105], volume=[1.0]))
    BO.manage(st, msgs, "GOLD", "1d", fr, c15, pd.Timestamp("2026-03-01 15:35"))
    check("stop-loss hit -> EXIT message with result in R, alert closed", not st["bo_active"] and any("EXIT" in m and "stop-loss" in m for m in msgs))
    st2 = dict(bo_active=[dict(name="SILVER", tf="3h", side="BUY", entry=100.0, stop=96.0, risk=4.0, best=100.0, trailed=False, n=0,
                               last_candle="2026-03-01 09:00:00", checked="2026-03-01 09:00:00", contract="X")], day=dict(outcomes=[]))
    m2 = []
    b1 = pd.DataFrame(dict(time=pd.to_datetime(["2026-03-01 09:15"]), open=[101], high=[106], low=[99.5], close=[105], volume=[1.0]))
    BO.manage(st2, m2, "SILVER", "3h", None, b1, pd.Timestamp("2026-03-01 09:32"))
    check("3h call: no partial booking, no trailing before the single target", st2["bo_active"] and st2["bo_active"][0]["stop"] == 96.0 and not m2)
    b2 = pd.DataFrame(dict(time=pd.to_datetime(["2026-03-01 09:30"]), open=[106], high=[108.5], low=[105], close=[108], volume=[1.0]))
    BO.manage(st2, m2, "SILVER", "3h", None, b2, pd.Timestamp("2026-03-01 09:47"))
    check("3h call: single TARGET (2R = 108) hit -> full exit +2.00R", not st2["bo_active"] and any("TARGET HIT" in x and "+2.00R" in x for x in m2))
    st4 = dict(bo_active=[dict(name="GOLD", tf="3h", side="BUY", entry=100.0, stop=96.0, risk=4.0, best=100.0, trailed=False, n=0,
                               last_candle=str(pre["time"].iloc[-2]), checked="2026-03-01 09:00:00", contract="X")], day=dict(outcomes=[]))
    fw = pre.copy(); fw.loc[fw.index[-1], ["close", "low"]] = [98.0, 97.5]
    m4 = []
    BO.manage(st4, m4, "GOLD", "3h", fw, None, pd.Timestamp("2026-03-01 15:35"))
    check("3h call: close back below EMA20 -> TREND CHANGE WARNING sent before the stop (trade stays open)",
          st4["bo_active"] and any("TREND CHANGE WARNING" in x for x in m4))
    fr = _trend(); last = fr["close"].iloc[-1]
    st3 = dict(bo_active=[dict(name="GOLD", tf="1d", side="BUY", entry=last, stop=last - 50, risk=50.0, best=last, trailed=False, n=0,
                               last_candle=str(fr["time"].iloc[-2]), checked=str(fr["time"].iloc[-1]), contract="X")], day=dict(outcomes=[]))
    fr.loc[fr.index[-1], ["close", "low"]] = [last - 30, last - 31]
    m3 = []
    BO.manage(st3, m3, "GOLD", "1d", fr, None, pd.Timestamp("2026-03-02 15:35"))
    check("daily call: close back below EMA20 -> TREND CHANGE WARNING before the stop (call stays open)",
          st3["bo_active"] and any("TREND CHANGE WARNING" in x for x in m3))
    from alerts import patterns as PT
    rng = np.random.default_rng(1)
    cc = list(100 + np.cumsum(rng.normal(0, 0.3, 100)))
    for _ in range(5): cc.append(cc[-1] + 2.0)
    top = cc[-1]
    for k in range(5): cc.append(top - 0.4 + 0.15 * (k % 2))
    cc.append(top + 1.2)
    cc = np.array(cc); oo = np.r_[cc[0], cc[:-1]]
    fl = pd.DataFrame(dict(time=pd.date_range("2026-01-01", periods=len(cc), freq="3h"), open=oo, high=np.maximum(oo, cc) + 0.2,
                           low=np.minimum(oo, cc) - 0.2, close=cc, volume=1000.0))
    check("chart pattern: impulse + tight pause + close above it -> BULL FLAG BUY (not before the break)",
          PT.detect(fl)[:2] == (1, "BULL FLAG") and PT.detect(fl.iloc[:-1])[0] == 0)
    om = pd.DataFrame([dict(name="NIFTY", exch_seg="NFO", instrumenttype="OPTIDX", symbol=f"NIFTY25NOV26{k}{t}", strike=k * 100, token=f"{k}{t}",
                            lotsize=75, expiry_dt=pd.Timestamp("2026-11-25")) for k in (22500, 22600) for t in ("CE", "PE")])
    oi_ = BO.option_idea(om, "NIFTY", "NFO", 22630, "SELL", "3h", pd.Timestamp("2026-10-27 12:00"))
    check("futures SELL call -> option-buy idea = ATM PE (22600 PE)", oi_ and oi_["symbol"] == "NIFTY25NOV2622600PE")
    dd_ = pd.DataFrame(dict(time=pd.bdate_range("2025-06-02", periods=200), open=100.0, high=101.0, low=99.0, close=100.0, volume=10.0))
    dd_.loc[dd_.index[-5:], ["close", "high"]] = [[104.0, 105.0]] * 5
    wk_ = BO.weekly_candles(dd_)
    check("weekly: close above the 20-week high -> weekly BUY call", BO.evaluate_weekly(wk_)["side"] == "BUY" and len(wk_) == 40)
    tm_ = pd.bdate_range("2025-11-03", periods=260); cm_ = np.linspace(100, 200, 260)
    dm_ = pd.DataFrame(dict(time=tm_, open=cm_, high=cm_ + 0.5, low=cm_ - 0.5, close=cm_, volume=100.0))
    lm_ = dm_.time.iloc[-1]; pmh_ = dm_[dm_.time.dt.to_period("M") == lm_.to_period("M") - 1].high.max()
    dm_.loc[dm_.time.dt.to_period("M") == lm_.to_period("M"), ["open", "high", "low", "close"]] = pmh_ - 3
    dm_.loc[dm_.index[-1], ["close", "high"]] = [pmh_ + 1, pmh_ + 1.5]
    check("monthly: first daily close above last month's high with weekly + monthly up-trend -> MONTHLY BUY",
          BO.evaluate_monthly(dm_)["side"] == "BUY" and BO.evaluate_monthly(dm_.iloc[:-1])["side"] is None)
    w_ = BO.reason_msg("GOLD", "1m", dict(BO.evaluate_monthly(dm_), side="BUY"), dict(support=[], resistance=[]), None, htf=BO.htf_levels(dm_.iloc[:-1]))
    check("WHY shows MONTHLY BREAKOUT and week / month support-resistance levels", "MONTHLY BREAKOUT" in w_ and "month H" in w_)
    import alerts.stocks as STK2
    c_ = list(np.linspace(100, 130, 60)); dE = pd.DataFrame(dict(time=pd.bdate_range("2026-04-13", periods=60), open=c_, high=[x + 1 for x in c_],
                                                             low=[x - 1 for x in c_], close=c_, volume=100.0, oi=1e6))
    dE.loc[dE.index[-2], ["open", "close", "high", "low"]] = [129.0, 131.0, 131.5, 128.8]
    dE.loc[dE.index[-1], ["open", "close", "high", "low", "volume"]] = [131.5, 128.7, 131.8, 128.5, 300.0]
    be_ = STK2.evaluate_bear_engulf(dE)
    check("stock: bearish engulfing after a rise on 3× volume -> SELL, SL 1.5 ATR, target 1R", be_["side"] == "SELL" and be_["tr"] == 1.0 and be_["k"] == 1.5)
    from alerts import optfilter as OF
    class OApi:
        def __init__(self, ltp, vix=(14.0, 14.0)): self.ltp, self.v = ltp, vix
        def quotes(self, d):
            if "NSE" in d: return {OF.VIX_TOKEN: {"ltp": self.v[0], "close": self.v[1]}}
            return {"T": {"ltp": self.ltp, "tradeVolume": 10, "depth": {"buy": [{"price": self.ltp * 0.995}], "sell": [{"price": self.ltp * 1.005}]}}}
    dly = pd.DataFrame(dict(close=22600 * np.exp(np.cumsum(np.r_[0, np.tile([0.008, -0.008], 15)]))))
    op_ = dict(token="T", K=22600.0, typ="CE", expiry=pd.Timestamp("2026-11-10"))
    ok1 = OF.check(OApi(250.0), "NFO", "NIFTY", op_, 22600.0, dly, pd.Timestamp("2026-10-28 12:00"))
    ok2 = OF.check(OApi(900.0), "NFO", "NIFTY", op_, 22600.0, dly, pd.Timestamp("2026-10-28 12:00"))
    ok3 = OF.check(OApi(250.0, (16.0, 14.0)), "NFO", "NIFTY", op_, 22600.0, dly, pd.Timestamp("2026-10-28 12:00"))
    check("option buy: fair premium passes; expensive premium (IV ≫ realised) and a VIX jump block the option call",
          ok1[0] and not ok2[0] and "expensive" in ok2[3] and not ok3[0] and "VIX" in ok3[3])
    om_, (osl_, otg_) = BO.option_msg("SILVER", "MCX", "1d", dict(side="SELL", close=195151.0, atr=9000.0),
                                      dict(K=195000.0, typ="PE", lot=30, expiry=pd.Timestamp("2026-11-27")), 7242.0)
    check("option-buy SL / target are % of the premium (−35% / +80%), never ₹0.05 or 8× the premium",
          osl_ == round(7242 * 0.65, 2) and otg_ == round(7242 * 1.8, 2) and "−35%" in om_)
    check("SL sanity cap: daily max 4% of price, 3h 2.5%, weekly calls off", BO.MAX_SL_PCT["1d"] == 4.0 and BO.MAX_SL_PCT["1w"] == 0.0)
    from alerts import report as RP
    lg = {}
    RP.add(lg, key="k", mark_key="1", seg="NSE", cat="FUTURES", name="NIFTY", symbol="NIFTY25NOV26FUT", type="Positional (3-hour)",
           side="SELL", entry=22630, sl=22790, target=22150, lot=75, mult=75, time="2026-10-28 12:17")
    BO.close_ledger(lg, "k", 22150.0, "🎯 TARGET HIT", pd.Timestamp("2026-10-28 14:00"))
    rr = RP.rows_for(lg, "NSE", "2026-10-28", {})
    check("call ledger: closed SELL 22630 -> 22150, lot 75 = +₹36,000 in the day report",
          rr and rr[0]["status"] == "CLOSED" and rr[0]["pnl"] == 36000 and "36,000" in RP.text_table(rr, "t"))
    check("exits: one stop + one target (3h 2 ATR/2R, daily 1.5 ATR/3R, weekly 3 ATR/2R)", BO.stop_k("1d") == 1.5 and BO.stop_k("3h") == 2.0
          and BO.TARGET_R["3h"] == 2.0 and BO.TARGET_R["1d"] == 3.0 and BO.TARGET_R["1w"] == 2.0 and BO.OPT_MIN_DAYS["3h"] == 2)
    sig = dict(side="BUY", candle="2026-03-01 12:00", close=111.0, hh=108.0, ll=90.0, ema200=100.0, atr=2.0, vol_x=2.1, adx=30.0, rsi=65.0)
    lv = dict(support=[(108.0, "swing high")], resistance=[(115.0, "pivot R1")])
    cg = dict(symbol="GOLD04DEC26FUT", expiry="2026-12-04")
    m = BO.call_msg("GOLD", "MCX", cg, "3h", sig, lv)
    check("simple call card: entry, SL and ONE target (2R = 119)",
          all(k in m for k in ("BUY  GOLD FUT", "Entry", "SL      : 107", "Target  : 119", "Lot")) and "Target 2" not in m and len(m.splitlines()) == 6)
    w = BO.reason_msg("GOLD", "3h", sig, lv, dict(oi=16500, chg_pct=0.8, gap_min=15, label="Long buildup"), None, BO.details("MCX", cg, "3h", sig, lv))
    check("second message WHY: candle timeframe, setup, volume, OI position, trend, next level, exit plan",
          all(k in w for k in ("📌 WHY", "3-hour candle", "BREAKOUT above", "Volume", "Long buildup", "200 EMA", "Next resistance", "TREND CHANGE")))


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
    check("12:15 block: no DAILY stock call (daily rule runs after the 15:30 close; only the 3h scan may run)",
          not any("Daily candle" in x for x in msgs))
    STK.scan(api, m, pd.Timestamp("2026-10-15 15:32"), st, msgs, rep, sys.modules["alerts.engine"])
    check("OI-confirmed breakout -> BUY call (lot size) + WHY message with LONG BUILDUP",
          any("BUY  TCS FUT" in x and "Lot     : 175" in x for x in msgs) and any("WHY – TCS BUY" in x and "Long buildup" in x and "Daily candle" in x for x in msgs))
    hh = pd.DataFrame(dict(time=pd.to_datetime(["2026-10-15 09:15", "2026-10-15 10:15", "2026-10-15 11:15", "2026-10-15 12:15"]),
                           open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0))
    check("3h stock frame: 09:15-12:15 block complete, 12:15 block still forming is dropped", len(STK.frame3h(hh)) == 1)
    class QApi:
        def __init__(self, px): self.px = px
        def quotes(self, d): return {"T": {"ltp": self.px}}
    s3 = dict(active3h=[dict(name="TCS", token="T", side="BUY", entry=100.0, stop=96.0, risk=4.0, best=100.0, trailed=False, n=0)])
    sd = dict(day=dict(outcomes=[])); mm = []
    STK.manage3h_quotes(QApi(104.2), s3, mm, sd)
    check("3h stock call: price beyond T1 -> BOOK 50% + stop to entry", any("T1 HIT" in x for x in mm) and s3["active3h"][0]["stop"] == 100.0)
    STK.manage3h_quotes(QApi(100.0), s3, mm, sd)
    check("then back to entry -> exit +0.50R", not s3["active3h"] and any("+0.50R" in x for x in mm))
    msgs2 = []
    STK.scan(api, m, pd.Timestamp("2026-10-15 15:47"), st, msgs2, rep, sys.modules["alerts.engine"])
    check("no duplicate stock call later the same day", not any("Daily candle" in x for x in msgs2))
    api2 = Api(oi.assign(oi=[1e6] * 60), series={("1", "ONE_HOUR"): h}, now=pd.Timestamp("2026-10-15 15:32"))
    st2 = E.new_state(); st2["day"] = dict(date="2026-10-15", alerts=0, watches=0, startup_sent=True, eod_sent=False, outcomes=[])
    m3 = []
    STK.scan(api2, m, pd.Timestamp("2026-10-15 15:32"), st2, m3, dict(errors=[]), sys.modules["alerts.engine"])
    check("same breakout WITHOUT an OI rise -> no DAILY call (OI confirmation required)", not any("Daily candle" in x for x in m3))


def test_telegram_delivery():
    import json, tempfile, os
    from alerts import run as RUN
    packed = RUN._pack(["a" * 1000] * 10)
    check("burst of messages is packed into ≤ 3,800-character posts (Telegram rate limit)", len(packed) == 4 and all(len(x) <= 3800 for x in packed))
    d = Path(tempfile.mkdtemp())
    with mock.patch.object(RUN, "OUTBOX", d / "outbox.json"), mock.patch.object(RUN, "PENDING", d / "pending.json"), \
         mock.patch.object(RUN, "GAP_SEC", 0), mock.patch.dict(os.environ, {"ALERTS_TELEGRAM": "1", "SAVE_OK": "success"}):
        (d / "outbox.json").write_text(json.dumps(dict(messages=["m1", "m2"])))
        with mock.patch("crude.run.telegram", side_effect=[(True, "ok"), (False, "HTTP 429")]):
            RUN.flush()
        check("undelivered message is kept for the next run, not lost", json.loads((d / "pending.json").read_text()) == ["m2"])
        sent = []
        (d / "outbox.json").write_text(json.dumps(dict(messages=["m3"])))
        with mock.patch("crude.run.telegram", side_effect=lambda t: (sent.append(t) or (True, "ok"))):
            RUN.flush()
        check("next run delivers the kept message first", sent == ["m2", "m3"] and not (d / "pending.json").exists())


def test_no_orders():
    src = "\n".join(f.read_text() for f in (ROOT / "alerts").rglob("*.py") if "tests" not in f.parts)
    check("alerts package has no order API (alert-only, no auto trading)", not re.search(r"placeOrder|modifyOrder|cancelOrder|place_order", src))
    lp = (ROOT / "scripts" / "market_loop.sh").read_text()
    check("market loop: state saved BEFORE Telegram is sent; every engine has a time limit (no stuck loop)",
          lp.index("save alerts-state alerts state.json; then") < lp.index("python -m alerts.run flush")
          and "timeout 1200 python -m alerts.run scan" in lp and 'ALERTS_STATE_DIR="$OLDPWD/state/alerts"' in lp and "timeout 600 python runner.py" in lp)


if __name__ == "__main__":
    for t in (test_patterns, test_bounce, test_quality_gold_case, test_rsi_direction, test_sessions_and_candles, test_engine_replay, test_follow_up, test_levels_and_oi, test_breakout, test_stocks, test_telegram_delivery, test_no_orders):
        t()
    print(f"\nALL {len(OK)} ALERT CHECKS PASSED")
