"""MCXD-002 shadow: GOLD/SILVER day-trend continuation – fires only at the 13:00 / 17:00 candle, needs 60m trend + VWAP + 0.3
daily ATR from the open, records a shadow trade (no message), stop and 23:00 square-off tracked.   python alerts/tests/test_mcx_dtc.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from alerts import mcx_dtc as D  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


day = pd.Timestamp("2026-11-06")
h1 = pd.DataFrame(dict(time=pd.date_range(day - pd.Timedelta(days=30), periods=200, freq="h")))
h1["close"] = np.linspace(100000, 110000, len(h1)); h1["open"] = h1.close - 5; h1["high"] = h1.close + 20; h1["low"] = h1.close - 20
h1 = h1[h1.time + pd.Timedelta(minutes=60) <= day + pd.Timedelta(hours=13)]
dd = pd.DataFrame(dict(time=pd.bdate_range(end=day - pd.Timedelta(days=1), periods=30)))
dd["close"] = 109000.0; dd["high"] = 109500.0; dd["low"] = 108500.0; dd["open"] = 109000.0           # daily ATR = 1000
t = pd.date_range(day + pd.Timedelta(hours=9), day + pd.Timedelta(hours=12, minutes=45), freq="15min")
px = np.linspace(110000, 110600, len(t))                                                             # +600 = 0.6 ATR above the open
c15 = pd.DataFrame(dict(time=t, open=px - 10, high=px + 15, low=px - 15, close=px, volume=100.0))
c15.loc[0, "open"] = 110000.0
now = day + pd.Timedelta(hours=13, minutes=2)
s = D.evaluate(c15, h1, dd, now)
check(s["side"] == "BUY" and s["checkpoint"] == "13:00" and abs(s["stop_dist"] - 500) < 1, "13:00 candle, uptrend, above VWAP, 0.6 ATR above open -> BUY, stop 0.5 ATR")
check(D.evaluate(c15.iloc[:-1], h1, dd, now)["side"] is None, "12:45 candle is not a checkpoint -> nothing")
weak = c15.copy(); weak["close"] = 110100.0
check(D.evaluate(weak, h1, dd, now)["side"] is None, "only 0.1 ATR from the open -> nothing")
st, msgs = {"day": {"date": str(day.date())}}, []
D.run(st, msgs, "GOLD", {"token": "9"}, c15, h1, dd, {"ltp": 110620.0}, now)
check(not msgs and len(st["mcxdtc"]["open"]) == 1 and st["mcxdtc"]["open"][0]["entry"] == 110620.0, "shadow trade recorded, NO message")
D.run(st, msgs, "GOLD", {"token": "9"}, c15, h1, dd, {"ltp": 110650.0}, now + pd.Timedelta(minutes=15))
check(len(st["mcxdtc"]["open"]) == 1, "same checkpoint not recorded twice")
D.track(st, "GOLD", {"ltp": 111000.0}, day + pd.Timedelta(hours=18))
check(len(st["mcxdtc"]["open"]) == 1, "price above stop before 23:00 -> still open")
D.track(st, "GOLD", {"ltp": 111120.0}, day + pd.Timedelta(hours=23, minutes=2))
r = st["mcxdtc"]["closed"][-1]
check(r["exit_reason"] == "square-off" and abs(r["result_R"] - 1.0) < 1e-6, "23:00 square-off at the live price, +1.0R recorded")
st2 = {"day": {"date": str(day.date())}}
D.run(st2, [], "SILVER", {"token": "8"}, c15, h1, dd, {"ltp": 110620.0}, now)
D.track(st2, "SILVER", {"ltp": 110100.0}, day + pd.Timedelta(hours=15))
check(st2["mcxdtc"]["closed"][-1]["exit_reason"] == "stop" and st2["mcxdtc"]["closed"][-1]["result_R"] == -1.0, "stop hit -> -1R")
check(D.LIVE is False, "strategy is SHADOW only (LIVE = False)")
print(f"\n{ok} checks passed")
