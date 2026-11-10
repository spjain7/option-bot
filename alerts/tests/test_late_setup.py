"""10-Nov: NATURALGAS 9-Nov – (1) the Diwali Muhurat session (Sun 8-Nov 14:20-15:30) became a 'daily' hammer candle;
(2) the setup was found at 23:17 (slot busy with the 30-Oct NG trade), when price (~301) was already far past the trigger
285.6, and the tracker replayed the day's 15-min bars -> 'TRIGGERED 285.6' and 'EXIT target 292.4' sent at 23:32 for moves
of 09:48 / 18:59, booked as a +2R win nobody could take. Now: weekend sessions are not daily candles; a setup whose trigger
already traded is not sent; bars before the alert never count.   python alerts/tests/test_late_setup.py"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import candle_setups as CS, breakout as BO  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_candle_setups import base, add, C  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


# 1. weekend (Muhurat) 1-hour bars are not a daily candle
h = pd.DataFrame(dict(time=pd.to_datetime(["2026-11-06 09:00", "2026-11-06 10:00", "2026-11-08 14:20", "2026-11-09 09:00"]),
                      open=[1, 2, 3, 4.0], high=[2, 3, 4, 5.0], low=[0.5, 1, 2, 3.0], close=[2, 3, 3.5, 4.5], volume=[10, 10, 1, 10.0]))
d = BO.daily_candles(h, None)
check([str(x.date()) for x in d["time"]] == ["2026-11-06", "2026-11-09"], "Sunday 8-Nov Muhurat bars are not a daily candle")
check(d["volume"].iloc[0] == 20 and d["high"].iloc[0] == 3, "weekday daily candles unchanged")

# 2. setup found late: trigger already traded -> not sent
d0 = base()
last = d0["close"].iloc[-1]
d0 = add(d0, "2026-10-21", last, last + 1, last - 20, last + 0.5)                  # hammer
hi = d0["high"].iloc[-1]
st, m = {"day": {}}, []
c15 = pd.DataFrame(dict(time=pd.date_range("2026-10-22 09:00", "2026-10-22 23:00", freq="15min")))
c15["open"] = hi + 15.0; c15["high"] = hi + 16; c15["low"] = hi + 14; c15["close"] = hi + 15
CS.on_mcx(st, m, "GOLD", "MCX", C, d0, None, c15, pd.Timestamp("2026-10-22 23:17"))
check(not m and not st["candle_setups"]["open"], "price already above the trigger when the setup is found -> no call (no chase)")

# 3. setup found late but trigger not traded: bars BEFORE the alert never trigger / exit it
st, m = {"day": {}}, []
early = c15.copy(); early["open"] = hi - 5.0; early["high"] = hi - 4; early["low"] = hi - 6; early["close"] = hi - 5
early.loc[5, "high"] = hi + 50                                                    # 10:15 spike through trigger AND target
now = pd.Timestamp("2026-10-22 23:17")
CS.on_mcx(st, m, "GOLD", "MCX", C, d0, None, early, now)
r = st["candle_setups"]["open"][0]
check(len(m) == 2 and r["status"] == "pending" and pd.Timestamp(r["last_bar"]) >= now - pd.Timedelta(minutes=1),
      "late setup sent with its tracking starting at the alert time")
m2 = []
CS.on_mcx(st, m2, "GOLD", "MCX", C, d0, None, early, now + pd.Timedelta(minutes=15))
check(not m2 and st["candle_setups"]["open"][0]["status"] == "pending", "the 10:15 spike (before the alert) is NOT replayed as an entry / target")
later = pd.concat([early, pd.DataFrame(dict(time=[pd.Timestamp("2026-10-22 23:30")], open=[hi - 1.0], high=[hi + 2], low=[hi - 2],
                                            close=[hi + 1]))], ignore_index=True)
m3 = []
CS.on_mcx(st, m3, "GOLD", "MCX", C, d0, None, later, pd.Timestamp("2026-10-22 23:47"))
check(any("TRIGGERED" in x for x in m3) and st["candle_setups"]["open"][0]["status"] == "open", "a break AFTER the alert triggers normally")
print(f"{ok} late-setup checks passed")
