"""Option-sell exits touched BETWEEN scans (28-Oct GOLD 142000 PE: premium spiked above the ₹628 SL around 20:05 and fell
back to ₹572 before the next 15-min scan, so no STOP-LOSS was sent).  python -m tests.test_sell_stops"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from positions import range_check  # noqa: E402

ok = 0


def check(c, name):
    global ok
    assert c, name
    ok += 1
    print("✅", name)


P = dict(legs=[dict(side="SELL", token="1")], credit=465.0, sl_val=628.0, target_val=302.5, opened="2026-10-28 18:02")
t = pd.date_range("2026-10-28 20:00", periods=20, freq="min")
high = [600, 610, 640, 690, 660, 640, 620, 600] + [580] * 12
bars = pd.DataFrame(dict(time=t, high=high, low=[h - 30 for h in high]))
a, lv, when = range_check(P, bars, "2026-10-28 19:59")
check(a == "SL" and lv == 628.0 and when == pd.Timestamp("2026-10-28 20:02"),
      "28-Oct GOLD replay: premium above ₹628 between scans -> STOP-LOSS at the SL level, touched 20:02")
check(range_check(P, bars, "2026-10-28 20:15")[0] is None, "bars before the last check are ignored (no double exit)")
b2 = bars.assign(high=400.0, low=[400.0] * 5 + [300.0] + [400.0] * 14)
check(range_check(P, b2, "2026-10-28 19:59")[:2] == ("TARGET", 302.5), "target touched between scans -> booked at the target")
b3 = b2.assign(high=[700.0] + [400.0] * 19)
check(range_check(P, b3, "2026-10-28 19:59")[0] == "SL", "both SL and target touched in the window -> STOP-LOSS (order unknown, conservative)")
spread = dict(P, legs=[dict(side="SELL", token="1"), dict(side="BUY", token="2")])
check(range_check(spread, bars, "2026-10-28 19:59")[0] is None, "spreads are not judged on one leg's bars")
check(range_check(P, None, "2026-10-28 19:59")[0] is None and range_check(P, bars.iloc[:0], "x")[0] is None,
      "no candle data -> no invented exit (the normal LTP check still runs)")
print(f"sell-stops: {ok} passed")
