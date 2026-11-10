"""10-Nov (Diwali Balipratipada: NSE closed, MCX evening only): one "no live data" notice, one "resumed" notice, no repeats;
normal days silent; impossible OI jumps ignored.   python alerts/tests/test_feed_health.py"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import engine as E  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


names = [("CRUDEOIL", "MCX"), ("SILVER", "MCX"), ("NIFTY", "NFO")]
cmap = {"CRUDEOIL": dict(token="1"), "SILVER": dict(token="2"), "NIFTY": dict(token="3")}
q = lambda t: {"ltp": 1.0, "exchFeedTime": pd.Timestamp(t).strftime("%d-%b-%Y %H:%M:%S")}
stale = {k: q("2026-11-09 23:29:58") for k in "123"}
st, out = {}, []
E.feed_health(st, out, stale, cmap, names, pd.Timestamp("2026-11-10 09:10"))
check(not out, "inside the first 20 minutes after the open: silent")
E.feed_health(st, out, stale, cmap, names, pd.Timestamp("2026-11-10 09:32"))
check(not out, "first scan without live data: not yet (needs two)")
E.feed_health(st, out, stale, cmap, names, pd.Timestamp("2026-11-10 09:47"))
check(len(out) == 1 and "NO LIVE DATA – MCX" in out[0] and "09-Nov 23:29" in out[0], "second MCX scan: ONE notice with the last exchange time")
E.feed_health(st, out, stale, cmap, names, pd.Timestamp("2026-11-10 09:55"))
check(len(out) == 2 and "NO LIVE DATA – NSE" in out[1], "NSE (opens 09:15) gets its own notice after its second dead scan")
for t in ("10:02", "12:00", "16:45"):
    E.feed_health(st, out, stale, cmap, names, pd.Timestamp(f"2026-11-10 {t}"))
check(len(out) == 2, "no repeats during the day")
live = dict(stale, **{"1": q("2026-11-10 17:01:30"), "2": q("2026-11-10 17:01:40")})
E.feed_health(st, out, live, cmap, names, pd.Timestamp("2026-11-10 17:02"))
check(len(out) == 3 and "LIVE DATA RESUMED – MCX at 17:02" in out[2], "MCX evening session opens -> ONE resumed notice (NSE stays closed)")
E.feed_health(st, out, live | {"1": q("2026-11-10 17:16:00")}, cmap, names, pd.Timestamp("2026-11-10 17:17"))
check(len(out) == 3, "no further messages")
st2, o2 = {}, []
for t in ("09:32", "09:47", "12:02"):
    E.feed_health(st2, o2, {k: q(f"2026-11-11 {t}:00") for k in "123"}, cmap, names, pd.Timestamp(f"2026-11-11 {t}") + pd.Timedelta(seconds=40))
check(not o2, "normal day: silent")
st3, o3 = {}, []
E.feed_health(st3, o3, {"1": q("2026-11-11 09:31:00")}, cmap, names, pd.Timestamp("2026-11-11 09:32"))
E.feed_health(st3, o3, {"1": q("2026-11-11 09:46:00")}, cmap, names, pd.Timestamp("2026-11-11 09:47"))
check(not any("MCX" in m for m in o3), "one live MCX contract is enough (illiquid contracts do not trigger it)")
s4 = {}
now = pd.Timestamp("2026-11-10 17:02")
E.oi_reading(s4, "CRUDE", {"opnInterest": 9336, "ltp": 8040.0}, now - pd.Timedelta(minutes=15))
r = E.oi_reading(s4, "CRUDE", {"opnInterest": 933600, "ltp": 7990.0}, now)
check(r["chg_pct"] is None and r.get("label") is None, "OI +9,900 % in 15 min -> ignored, no build-up label")
r = E.oi_reading(s4, "CRUDE", {"opnInterest": 943600, "ltp": 7970.0}, now + pd.Timedelta(minutes=15))
check(abs(r["chg_pct"] - 1.071) < 0.01 and r["label"] == "Short buildup", "next normal reading works from the new baseline")
print(f"{ok} feed-health checks passed")
