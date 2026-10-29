"""Offline tests for alerts/watch1h.py (1H BIG MOVE watch). python -m alerts.tests.test_watch1h"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import watch1h as W

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


def hours(n, last_close=None, last_vol=1000.0, start="2026-10-26 09:00"):
    t = pd.date_range(start, periods=n, freq="h")
    c = 100 + np.sin(np.arange(n)) * 0.5
    df = pd.DataFrame(dict(time=t, open=c, high=c + 0.5, low=c - 0.5, close=c, volume=1000.0))
    if last_close is not None:
        df.loc[n - 1, ["close", "high"]] = [last_close, last_close + 0.1]
        df.loc[n - 1, "volume"] = last_vol
    return df


NOW = pd.Timestamp("2026-10-27 12:05")
st, m = {}, []
check(W.check(st, m, "GOLD", "MCX", hours(30, 103.0, 2500), NOW, oi="Long buildup") and "WATCH (not a call)" in m[0]
      and "2.5×" in m[0] and "no entry / SL / target" in m[0], "breakout + 2.5× volume + supporting OI -> watch sent")
check(W.check(st, m, "GOLD", "MCX", hours(30, 103.0, 2500), NOW, oi="Long buildup") is None and len(m) == 1,
      "same instrument / side / day -> not repeated")
st2, m2 = {}, []
check(W.check(st2, m2, "GOLD", "MCX", hours(30, 103.0, 1500), NOW, oi="Long buildup") is None and not m2, "volume only 1.5× -> nothing")
check(W.check(st2, m2, "GOLD", "MCX", hours(30, 103.0, 2500), NOW, oi="Short buildup") is None and not m2,
      "OI against the move -> not sent")
check(W.check({}, [], "GOLD", "MCX", hours(30, 103.0, 2500), NOW, oi=None) is None, "OI unknown -> not sent (never invented)")
check(W.check({}, [], "GOLD", "MCX", hours(30, 100.2, 2500), NOW, oi="Long buildup") is None, "no 20-hour breakout -> nothing")
d = hours(30, 97.0, 3000)
d.loc[29, ["close", "low", "high"]] = [97.0, 96.9, 99.0]
s3, m3 = {}, []
check(W.check(s3, m3, "NIFTY", "INDEX", d, NOW, oi="Long unwinding") and "🔴" in m3[0], "SELL watch below the 20-hour low")

# tracking + summary
nxt = pd.concat([hours(30, 103.0, 2500), pd.DataFrame(dict(time=[pd.Timestamp("2026-10-27 15:00")], open=[103.0], high=[105.0],
                                                           low=[102.5], close=[104.0], volume=[900.0]))], ignore_index=True)
W.check(st, m, "GOLD", "MCX", nxt, NOW + pd.Timedelta(hours=1), oi="Long buildup")
r = st["watch1h"]["open"][0]
check(r["best"] == 105.0 and r["worst"] == 102.5 and r["last"] == 104.0, "later candles tracked: best / worst / last price")
sm = W.summary_msg(st, "2026-10-27", ["MCX"])
check(sm and "GOLD BUY" in sm and "+1.94%" in sm, "end-of-day summary with the further move in %")
check(W.summary_msg(st, "2026-10-27", ["INDEX"]) is None, "no index watches -> no index summary")

# hourly candles from 15-min, OI derived
t = pd.date_range("2026-10-23 09:15", periods=25, freq="15min").append(pd.date_range("2026-10-26 09:15", periods=25, freq="15min"))
f = pd.DataFrame(dict(time=t, open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0, oi=np.arange(50.0)))
h = W.hourly_from_15m(f, pd.Timestamp("2026-10-26 15:40"))
check(len(h) == 12 and str(h["time"].iloc[0])[11:16] == "09:15" and h["volume"].iloc[0] == 40, "15-min -> 6 complete hours per day")
h2 = W.hourly_from_15m(f, pd.Timestamp("2026-10-26 11:20"))
check(str(h2["time"].iloc[-1]) == "2026-10-26 10:15:00", "an hour still forming is not used")
check(W.oi_label(1, 5) == "Long buildup" and W.oi_label(-1, 5) == "Short buildup" and W.oi_label(1, -5) == "Short covering"
      and W.oi_label(-1, -5) == "Long unwinding" and W.oi_label(1, None) is None, "OI labels from price / OI change")
# stock path: OI derived from the hourly OI change
sh = hours(30, 103.0, 2500).assign(oi=np.arange(30.0) * 10)
s5, m5 = {}, []
check(W.check(s5, m5, "TITAN", "STOCK FUT", sh, NOW) and "Long buildup" in m5[0], "stock: price up + OI up in the hour -> long buildup, sent")

print(f"\nwatch1h: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
