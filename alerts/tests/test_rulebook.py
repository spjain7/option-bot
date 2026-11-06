"""6-Nov rulebook: a validated rule fires on the last completed candle -> call with T1/T2/R:R/validity + WHY with evidence;
shadow rule -> logged and tracked silently; dedupe per candle; funnel counts.   python alerts/tests/test_rulebook.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from alerts import rulebook as RB, four_hour as FH  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


def frame(n=400, seed=2):
    r = np.random.default_rng(seed)
    t = pd.date_range("2026-01-01 09:00", periods=n, freq="4h")
    c = 100 + np.cumsum(r.normal(0.02, 0.4, n))
    return pd.DataFrame(dict(time=t, open=c - 0.1, high=c + 0.5, low=c - 0.5, close=c, volume=1000.0))


f = frame()
ff = RB.features(f)
b, s = RB.raw(ff, "EMAX", "13/48")
i = int(np.flatnonzero(b)[-1])                            # last EMA13/48 up-cross
fr = f.iloc[:i + 1].reset_index(drop=True)
daily = pd.DataFrame(dict(time=pd.bdate_range(end=fr["time"].iloc[-1].normalize() - pd.Timedelta(days=1), periods=120),
                          open=1.0, high=1.0, low=1.0, close=np.linspace(50, 100, 120), volume=1.0))
NOW = fr["time"].iloc[-1] + pd.Timedelta(hours=4, minutes=2)
C = dict(symbol="GOLD04DEC26FUT", token="7", expiry="2026-12-04", lot=1, tick=0.1)
q = {"ltp": float(fr["close"].iloc[-1]), "exchFeedTime": f"{NOW:%d-%b-%Y %H:%M:%S}"}
keep = dict(RB.RULES)
RB.RULES = {"RB_MCX_4h_EMA1348_BUY": keep["RB_MCX_4h_EMA1348_BUY"]}
st, m = {"day": {"date": str(NOW.date())}}, []
out = RB.run(st, m, None, "GOLD", "MCX", C, {"4h": fr}, daily, q, NOW, 100, "MCX")
check(out.get("RB_MCX_4h_EMA1348_BUY") == "SENT" and len(m) == 2, "EMA 13/48 cross in a daily uptrend -> call + WHY")
check(all(x in m[0] for x in ("T1", "T2", "R:R", "Valid", "4-HOUR")) and "backtest trades" in m[1] and "periods" in m[1],
      "call shows T1 / T2 / R:R / validity; WHY shows the evidence")
check(st["ledger"][0]["status"] == "OPEN" and st["fourh"]["open"][0]["rule"] == "RB_MCX_4h_EMA1348_BUY", "ledger row + tracked")
m2 = []
RB.run(st, m2, None, "GOLD", "MCX", C, {"4h": fr}, daily, q, NOW + pd.Timedelta(minutes=15), 100, "MCX")
check(not m2, "same candle checked again 15 minutes later -> nothing new")
check(st["funnel"][str(NOW.date())]["RB_MCX_4h_EMA1348_BUY"]["sent"] == 1, "funnel counted the call once")
down = daily.assign(close=np.linspace(100, 50, 120))
st3, m3 = {"day": {"date": str(NOW.date())}}, []
o3 = RB.run(st3, m3, None, "GOLD", "MCX", C, {"4h": fr}, down, q, NOW, 100, "MCX")
check(not m3 and "daily trend" in o3["RB_MCX_4h_EMA1348_BUY"], "same signal in a daily downtrend -> rejected (reason recorded)")
RB.RULES = {"X": dict(keep["RB_MCX_4h_EMA1348_BUY"], status="SHADOW")}
st4, m4 = {"day": {"date": str(NOW.date())}}, []
RB.run(st4, m4, None, "GOLD", "MCX", C, {"4h": fr}, daily, q, NOW, 100, "MCX")
check(not m4 and st4["fourh"]["open"][0].get("shadow") and not st4.get("ledger"), "SHADOW rule: no message, no ledger row, tracked")


class Api:
    def __init__(self, ltp): self.ltp = ltp
    def quotes(self, d): return {"7": {"ltp": self.ltp}}


m5 = []
FH.track(st4, m5, Api(st4["fourh"]["open"][0]["target"] + 1), NOW + pd.Timedelta(hours=1), lambda ex, now: True)
check(not m5 and st4["fourh"]["closed"][0]["exit_reason"].endswith("target"), "shadow outcome recorded silently")
RB.RULES = keep
print(f"\nrulebook: {ok} passed")
