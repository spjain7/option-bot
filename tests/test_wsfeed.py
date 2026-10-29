"""Offline tests: WebSocket 1-minute bars (wsbars.py), their use in angel.Angel (today from the stream, history from REST once
a day, REST before the collector start, hourly verification) and the separate quote / candle pauses. python tests/test_wsfeed.py"""
import json, sys, tempfile, time
from pathlib import Path
from unittest import mock
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import angel as A  # noqa: E402
import wsbars as WB  # noqa: E402
import wsfeed as WF  # noqa: E402

ok = fail = 0


def check(name, c):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


DAY = pd.Timestamp("2026-10-30")
NOW = DAY + pd.Timedelta(hours=11, minutes=2)


class Rest:
    """REST stand-in: getCandleData returns 15-min / 1-h bars for the requested range at price 100 (history) or 200 (today)."""
    def __init__(self, rate=False):
        self.calls, self.rate = [], rate

    def _bars(self, p):
        f, t = pd.Timestamp(p["fromdate"]), pd.Timestamp(p["todate"])
        step = {"FIFTEEN_MINUTE": "15min", "ONE_HOUR": "60min", "ONE_DAY": "1D"}[p["interval"]]
        rng = pd.date_range(f.normalize() + pd.Timedelta(hours=9, minutes=15), t, freq=step)
        rng = [x for x in rng if f <= x <= t and (p["interval"] == "ONE_DAY" or "09:15" <= f"{x:%H:%M}" < "15:30")]
        return rng

    def getCandleData(self, p):
        self.calls.append(p)
        if self.rate:
            raise Exception("Access denied because of exceeding access rate")
        px = lambda x: 200.0 if x.normalize() == DAY else 100.0
        return {"status": True, "data": [[f"{x:%Y-%m-%dT%H:%M:%S}+05:30", px(x), px(x) + 1, px(x) - 1, px(x), 1000] for x in self._bars(p)]}

    def getOIData(self, p):
        self.calls.append(p)
        return {"status": True, "data": [{"time": f"{x:%Y-%m-%dT%H:%M:%S}+05:30", "openInterest": 5000} for x in self._bars(p)]}

    def getMarketData(self, mode, d):
        self.calls.append("quote")
        return {"status": True, "data": {"fetched": [{"symbolToken": "1", "ltp": 10.0}]}}


def make(cache, wsd, rest, now=NOW):
    a = A.Angel.__new__(A.Angel)
    a.api = rest
    a._setup(cache_dir=cache, ws_dir=wsd, ws=True)
    a.HIST_GAP = a.QUOTE_GAP = 0
    a._now = lambda: now
    return a


def verified(wsd, now=NOW):
    (Path(wsd) / "verify.json").write_text(json.dumps({"NFO": dict(hour=f"{now:%Y%m%d%H}", ok=True, note="OK (test)")}))


def feed(wsd, token, start, end, px=200.0, vol_step=10, oi=7000):
    """Write ticks every 20 s from start to end into a Builder (cumulative volume rises vol_step per tick)."""
    B = WB.Builder(wsd)
    t, cum = start, 0
    while t <= end:
        cum += vol_step
        B.tick(token, t, px + (t.minute % 3) * 0.1, cum, oi)
        t += pd.Timedelta(seconds=20)
    B.flush(end + pd.Timedelta(minutes=1))
    return B


with tempfile.TemporaryDirectory() as c, tempfile.TemporaryDirectory() as w:
    # 1. Builder -> minute bars
    B = WB.Builder(w)
    B.tick("9", DAY + pd.Timedelta(hours=9, minutes=15, seconds=5), 100.0, 1000, 50)
    B.tick("9", DAY + pd.Timedelta(hours=9, minutes=15, seconds=40), 101.0, 1300, 55)
    B.tick("9", DAY + pd.Timedelta(hours=9, minutes=16, seconds=1), 99.0, 1500, 56)
    B.flush(DAY + pd.Timedelta(hours=9, minutes=16, seconds=30))
    m = WB.minutes("9", DAY, w)
    check("1-minute bars: OHLC from ticks", len(m) == 2 and m["high"].iat[0] == 101.0 and m["low"].iat[0] == 100.0 and m["close"].iat[1] == 99.0)
    check("bar volume = rise of the day's cumulative volume (first bar partial, then exact)", m["volume"].iat[0] == 300 and m["volume"].iat[1] == 200)
    check("OI = last value in the minute; forming minute readable", m["oi"].iat[0] == 55 and m["oi"].iat[1] == 56)
    # 2. aggregation alignment
    mm = pd.DataFrame(dict(time=pd.date_range(DAY + pd.Timedelta(hours=9, minutes=15), periods=120, freq="1min"), open=1.0, high=2.0,
                           low=0.5, close=1.5, volume=1.0, oi=3.0))
    h = WB.aggregate(mm, "ONE_HOUR", "NFO")
    check("NSE hourly bars start 09:15 / 10:15 (as Angel's)", [f"{x:%H:%M}" for x in h["time"]] == ["09:15", "10:15"] and h["volume"].iat[0] == 60)
    q = WB.aggregate(mm.assign(time=mm["time"] - pd.Timedelta(minutes=15)), "ONE_HOUR", "MCX")
    check("MCX hourly bars start 09:00", f"{q['time'].iat[0]:%H:%M}" == "09:00")
    check("daily bucket", len(WB.aggregate(mm, "ONE_DAY", "NFO")) == 1)

with tempfile.TemporaryDirectory() as c, tempfile.TemporaryDirectory() as w:
    # 3. collector running since before the open: today entirely from the stream, history from REST once a day
    start = DAY + pd.Timedelta(hours=9, minutes=10)
    feed(w, "77", DAY + pd.Timedelta(hours=9, minutes=15), NOW - pd.Timedelta(seconds=30))
    WB.write_status(dict(start=str(start), last_tick={"NFO": str(NOW - pd.Timedelta(seconds=20))}, tokens=["77"]), w)
    verified(w)
    r = Rest(); a = make(c, w, r)
    df = a.candles("NFO", "77", "FIFTEEN_MINUTE", DAY - pd.Timedelta(days=3), NOW)
    today = df[df["time"] >= DAY]
    check("today's 15-min bars come from the WebSocket (stream volume, not REST's 1000)", len(today) >= 6 and today["volume"].iat[1] == 450
          and a.stats["ws_hits"] == 1)
    check("history before today from REST (price 100)", (df[df["time"] < DAY]["close"] == 100).all() and (df["time"] < DAY).sum() > 0)
    n1 = len(r.calls)
    b = make(c, w, r)                                       # another engine process, later in the day
    b.candles("NFO", "77", "FIFTEEN_MINUTE", DAY - pd.Timedelta(days=3), NOW)
    check("history is fetched once a day (second process: no new REST call)", len(r.calls) == n1)
    check("only 1 REST call in total for this series today", n1 == 1)
    oi = b.oi_history("NFO", "77", "FIFTEEN_MINUTE", DAY - pd.Timedelta(days=2), NOW)
    check("OI history: today from the stream (7000), before today REST (5000)", (oi[oi["time"] >= DAY]["oi"] == 7000).all()
          and (oi[oi["time"] < DAY]["oi"] == 5000).all())
    check("token not subscribed -> normal REST path", make(c, w, Rest())._ws_series("NFO", "99", "FIFTEEN_MINUTE", DAY, NOW, "candles") is None)

with tempfile.TemporaryDirectory() as c, tempfile.TemporaryDirectory() as w:
    # 4. collector started late (10:07): REST for today up to 10:07 (once), stream after, the 10:00 bar merged
    start = DAY + pd.Timedelta(hours=10, minutes=7)
    feed(w, "5", start, NOW - pd.Timedelta(seconds=30))
    WB.write_status(dict(start=str(start), last_tick={"NFO": str(NOW)}, tokens=["5"]), w)
    verified(w)
    r = Rest(); a = make(c, w, r)
    df = a.candles("NFO", "5", "FIFTEEN_MINUTE", DAY, NOW)
    t = [f"{x:%H:%M}" for x in df["time"]]
    check("late start: bars from 09:15 continuous, no gap", t[:4] == ["09:15", "09:30", "09:45", "10:00"] and "10:15" in t)
    bb = df[df["time"] == DAY + pd.Timedelta(hours=10)].iloc[0]
    check("boundary bar 10:00 = REST part + stream part (volume added)", bb["volume"] > 1000)
    check("REST used once for the part before the collector started", sum(1 for x in r.calls if x != "quote") == 1)

with tempfile.TemporaryDirectory() as c, tempfile.TemporaryDirectory() as w:
    # 5. stale feed -> REST; verification mismatch -> REST for the hour
    WB.write_status(dict(start=str(DAY + pd.Timedelta(hours=9)), last_tick={"NFO": str(NOW - pd.Timedelta(minutes=10))}, tokens=["5"]), w)
    check("feed silent for 10 min during market hours -> not used", make(c, w, Rest())._ws_series("NFO", "5", "ONE_HOUR", DAY, NOW, "candles") is None)
    WB.write_status(dict(start=str(DAY + pd.Timedelta(hours=9)), last_tick={"NFO": str(NOW)}, tokens=["5"]), w)
    feed(w, "5", DAY + pd.Timedelta(hours=9, minutes=15), NOW - pd.Timedelta(seconds=30), px=150.0)   # REST says 200 -> mismatch
    a = make(c, w, Rest())
    with mock.patch("builtins.print"):
        res = a._ws_series("NFO", "5", "FIFTEEN_MINUTE", DAY, NOW, "candles")
    v = json.loads((Path(w) / "verify.json").read_text())
    check("hourly check: stream price differs from REST -> stream switched off, REST used", res is None and v["NFO"]["ok"] is False)
    check("the mismatch is remembered for the hour (no repeated check calls)", make(c, w, Rest())._ws_verify("NFO", "5", WB.status(w), NOW) is False)

with tempfile.TemporaryDirectory() as c, tempfile.TemporaryDirectory() as w:
    # 6. separate pauses: candles blocked, quotes still go out
    a = make(c, w, Rest(rate=True)); a._ws_on = False
    with mock.patch("angel.time.sleep"), mock.patch("builtins.print"):
        for i in range(8):
            a.candles("NFO", str(i), "ONE_HOUR", DAY - pd.Timedelta(days=5), NOW)
    check("candle API blocked -> candle fail-fast on", a.failfast() is True)
    a.api.rate = False
    check("quotes are NOT blocked by the candle pause (own limit)", a.quotes({"NFO": ["1"]}).get("1", {}).get("ltp") == 10.0)

# 7. collector token list
mst = pd.DataFrame([dict(exch_seg="NFO", instrumenttype="FUTSTK", name="TITAN", token=str(i), expiry_dt=DAY + pd.Timedelta(days=d))
                    for i, d in ((1, 27), (2, 55), (3, 90))] +
                   [dict(exch_seg="NFO", instrumenttype="FUTIDX", name="NIFTY", token="10", expiry_dt=DAY + pd.Timedelta(days=27)),
                    dict(exch_seg="MCX", instrumenttype="FUTCOM", name="GOLD", token="20", expiry_dt=DAY + pd.Timedelta(days=35)),
                    dict(exch_seg="MCX", instrumenttype="FUTCOM", name="CARDAMOM", token="30", expiry_dt=DAY + pd.Timedelta(days=35))])
tk = WF.tokens(mst, NOW)
check("collector subscribes the 2 nearest stock expiries, index and followed MCX futures only",
      sorted(tk["NFO"]) == ["1", "10", "2"] and tk["MCX"] == ["20"])

# 8. export for the data branch
with tempfile.TemporaryDirectory() as w:
    feed(w, "20", DAY + pd.Timedelta(hours=9), DAY + pd.Timedelta(hours=10), oi=4321)
    pd.DataFrame([dict(token="20", exch="MCX", name="GOLD", symbol="GOLD04DEC26FUT", expiry="2026-12-04")]).to_csv(Path(w) / "tokens.csv", index=False)
    out = Path(w) / "x" / "ws.csv.gz"
    n = WB.export(out, d=w)
    e = pd.read_csv(out)
    check("export: 5-min bars with OI and symbol (MCX aligned 09:00)", n == 13 and e["symbol"].iat[0] == "GOLD04DEC26FUT"
          and (e["oi"] == 4321).all() and e["time"].iat[0].endswith("09:00:00"))

print(f"\nwsfeed: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
