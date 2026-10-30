"""Offline tests: 4-hour MCX BUY / stock SELL (alerts/four_hour.py). python -m alerts.tests.test_four_hour"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import four_hour as FH

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


# 1. candles
t = pd.date_range("2026-10-29 09:00", "2026-10-29 23:00", freq="h")
h1 = pd.DataFrame(dict(time=t, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0))
m4 = FH.four_hour(h1, "MCX", pd.Timestamp("2026-10-29 23:45"))
check([f"{x:%H:%M}" for x in m4["time"]] == ["09:00", "13:00", "17:00", "21:00"] and m4["volume"].iat[0] == 40, "MCX 4h blocks 09/13/17/21, volume summed")
check(len(FH.four_hour(h1, "MCX", pd.Timestamp("2026-10-29 16:30"))) == 1, "a 4h block still forming is not used")
tn = pd.date_range("2026-10-29 09:15", periods=7, freq="h")
n4 = FH.four_hour(pd.DataFrame(dict(time=tn, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0)), "NFO", pd.Timestamp("2026-10-29 15:40"))
check([f"{x:%H:%M}" for x in n4["time"]] == ["09:15", "13:15"] and list(n4["volume"]) == [40, 30], "NSE 4h day blocks 09:15-13:15 / 13:15-15:30")


def series(side, n=260, last_vol=3.0, jump=1.5):
    tt = pd.date_range("2026-01-01 09:00", periods=n, freq="4h")
    c = np.linspace(100, 130, n) if side > 0 else np.linspace(130, 100, n)
    c = c + np.sin(np.arange(n)) * 0.3
    f = pd.DataFrame(dict(time=tt, open=c, high=c + 0.5, low=c - 0.5, close=c, volume=100.0))
    f.loc[n - 1, ["open", "close", "high", "low", "volume"]] = [c[-2], c[-2] + side * jump, max(c[-2], c[-2] + side * jump) + 0.1,
                                                                 min(c[-2], c[-2] + side * jump) - 0.1, 100.0 * last_vol]
    f["end"] = f["time"] + pd.Timedelta(hours=4)
    return f


b = FH.evaluate(series(1), FH.RULES["MCX"])
check(b["side"] == "BUY" and b["vol_x"] > 2, "MCX: close above the 10-candle high, volume > 2×, above EMA200 -> BUY")
check(FH.evaluate(series(1, last_vol=1.5), FH.RULES["MCX"])["side"] is None, "volume 1.5× -> no call")
check(FH.evaluate(series(-1), FH.RULES["NFO"])["side"] == "SELL", "stocks: close below the 5-candle low, volume > 2×, below EMA200 -> SELL")


class Api:
    def __init__(self, oi_up=True, ltp=None):
        self.oi_up, self.ltp = oi_up, ltp
    def oi_history(self, ex, tok, iv, frm, to):
        return pd.DataFrame(dict(time=[frm, to], oi=[1000.0, 1100.0 if self.oi_up else 900.0]))
    def quotes(self, ex):
        return {t: {"ltp": self.ltp} for v in ex.values() for t in v}


NOW = pd.Timestamp("2026-03-15 13:02")
C = dict(symbol="GOLD04DEC26FUT", token="7", expiry="2026-12-04", lot=1, tick=1.0)


def run(f, side, oi_up=True, ex="MCX", sr=None):
    st = {"day": {}}
    m = []
    import alerts.signals as S
    orig = S.levels
    if sr is not None:
        S.levels = lambda *a, **k: sr
    try:
        q = {"ltp": float(f["close"].iloc[-1]), "exchFeedTime": f"{NOW:%d-%b-%Y %H:%M:%S}"}
        r = FH.on_candles(st, m, Api(oi_up), "GOLD", ex, C, None, f, q, NOW, 100)
    finally:
        S.levels = orig
    return st, m, r


f = series(1)
st, m, r = run(f, 1, sr=dict(support=[], resistance=[]))
check(r == "SENT" and len(m) == 2 and "Long buildup" in m[1] and "4-hour" in m[0] and st["ledger"][0]["type"] == "Swing (4-hour)",
      "BUY with OI rising during the candle: call + WHY (OI line) + report row")
_, m2, r2 = run(f, 1, oi_up=False, sr=dict(support=[], resistance=[]))
check(r2 == "SENT" and "Short covering" in m2[1], "BUY with OI falling (short covering) also supports it")
e = float(f["close"].iloc[-1])
_, m3, r3 = run(f, 1, sr=dict(support=[], resistance=[(e + 0.2, "swing high")]))
check(r3.startswith("skipped: resistance") and not m3, "resistance within 0.5R of the entry -> no BUY call")


class NoOI(Api):
    def oi_history(self, *a): return None
st5 = {"day": {}}
q = {"ltp": e, "exchFeedTime": f"{NOW:%d-%b-%Y %H:%M:%S}"}
r5 = FH.on_candles(st5, [], NoOI(), "GOLD", "MCX", C, None, f, q, NOW, 100)
check(r5 == "skipped: OI over the candle not available", "OI not available -> no call (never assumed)")
fs = series(-1)
_, m6, r6 = run(fs, -1, oi_up=True, ex="NFO", sr=dict(support=[], resistance=[]))
check(r6 == "SENT" and "Short buildup" in m6[1] and "SELL" in m6[0], "stock SELL with short buildup -> call")

# tracking
rec = st["fourh"]["open"][0]
from alerts import breakout as BO  # noqa
m7 = []
FH.track(st, m7, Api(ltp=rec["target"] + 1), NOW + pd.Timedelta(hours=2), lambda ex, now: True)
check(m7 and "target" in m7[0] and "✅ EXIT" in m7[0] and not st["fourh"]["open"] and st["ledger"][0]["status"] == "CLOSED",
      "target touched on the live price -> profit exit message, report row closed")
print(f"\nfour-hour: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
