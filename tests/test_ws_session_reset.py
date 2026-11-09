"""9-Nov-2026 live findings (morning job, collector started 08:42 IST before the open):
1. first ticks carried the PREVIOUS day's cumulative volume (NFO 27,300 at 08:42) -> with max() every bar stayed 0 until
   today's total passed yesterday's (MCX 100 % zero 09:00-09:59, NIFTY volume 0 until ~12:20) -> a drop restarts the baseline;
2. stale pre-open prints made phantom minutes (NIFTY 06:55, CRUDEOIL 03:26 / 08:45) -> dropped before the session open;
3. hourly check passed MCX at day-ratio 0.67 although morning bars were 0 -> any zero-volume bar now fails the check.
python tests/test_ws_session_reset.py"""
import sys
import tempfile
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wsbars as WB  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


d = tempfile.mkdtemp()
B = WB.Builder(d)
B.tick("1", "2026-11-09 08:42:10", 100.0, 27300, 5)      # stale: yesterday's total before the open
B.tick("1", "2026-11-09 08:42:50", 100.0, 27300, 5)
B.tick("1", "2026-11-09 09:15:05", 101.0, 50, 6)         # session starts: counter restarts
B.tick("1", "2026-11-09 09:15:40", 101.5, 400, 6)
B.tick("1", "2026-11-09 09:16:10", 101.2, 650, 7)
B.tick("1", "2026-11-09 09:16:50", 101.3, 640, 7)        # small out-of-order regression: NOT a reset
B.tick("1", "2026-11-09 09:17:01", 101.4, 900, 7)
B.flush(pd.Timestamp("2026-11-09 09:18:00"))
m = WB.minutes("1", "2026-11-09", d).set_index("time")
v = m["volume"].to_dict()
check(v[pd.Timestamp("2026-11-09 08:42")] == 0, "stale pre-open minute has no volume")
check(v[pd.Timestamp("2026-11-09 09:15")] == 400, f"first session minute counts today's trades (400): {v[pd.Timestamp('2026-11-09 09:15')]}")
check(v[pd.Timestamp("2026-11-09 09:16")] == 250 and v[pd.Timestamp("2026-11-09 09:17")] == 250,
      "following minutes = change of today's counter; a small regression is not treated as a reset")
check(m["volume"].sum() == 900, "minute volumes add up to today's total (900), nothing of yesterday")

# (same ticks on main before this fix: every minute 0 – reproduced 9-Nov)

B2 = WB.Builder(tempfile.mkdtemp())
for t_, c_ in (("10:00:01", 5000), ("10:00:30", 5200), ("10:00:40", 30), ("10:01:05", 5300), ("10:02:01", 5400)):
    B2.tick("2", "2026-11-09 " + t_, 100.0, c_, 1)        # glitch tick (30) in a live session
B2.flush(pd.Timestamp("2026-11-09 10:03"))
v2 = WB.minutes("2", "2026-11-09", B2.d)["volume"].tolist()
check(sum(v2) == 400 and max(v2) <= 200, f"a glitchy low tick mid-session is ignored, no fake volume spike: {v2}")

agg = WB.aggregate(m.reset_index(), "FIFTEEN_MINUTE", "NFO")
check(list(agg["time"]) == [pd.Timestamp("2026-11-09 09:15")] and agg["volume"].iloc[0] == 900,
      "pre-open minute dropped: no phantom 08:30 candle, first bar 09:15")
mc = pd.DataFrame(dict(time=pd.to_datetime(["2026-11-09 03:26", "2026-11-09 08:45", "2026-11-09 08:59", "2026-11-09 09:00"]),
                       open=1.0, high=1.0, low=1.0, close=1.0, volume=[0, 0, 0, 5], oi=1))
check(list(WB.aggregate(mc, "ONE_HOUR", "MCX")["time"]) == [pd.Timestamp("2026-11-09 09:00")], "MCX 03:26 / 08:45 / 08:59 prints dropped")
check(len(WB.aggregate(mc, "ONE_DAY", "MCX")) == 1, "daily aggregation unchanged (one bar)")

t = pd.date_range("2026-11-09 09:00", periods=4, freq="15min")
rest = pd.DataFrame(dict(time=t, open=1.0, high=1.0, low=1.0, close=1.0, volume=[100.0, 100, 100, 100]))
ws = rest.assign(volume=[0.0, 0, 130, 140])                 # day ratio 0.68 -> passed before
okv, note = WB.verify_ok(rest, ws)
check(not okv and "zero-volume bars 2" in note, f"zero-volume bars now fail the check: {note}")
okv2, note2 = WB.verify_ok(rest, rest.assign(volume=[95.0, 104, 100, 99]))
check(okv2 and "zero-volume" not in note2, "normal bars still pass")
print(f"{ok} WebSocket session-reset checks passed")
