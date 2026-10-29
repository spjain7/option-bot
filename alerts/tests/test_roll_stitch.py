"""Offline test: next-month contract history joined with the expiring contract (alerts.engine.stitch_prev). python -m alerts.tests.test_roll_stitch"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import engine as E

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


t = pd.date_range("2026-03-01 09:00", periods=24 * 240, freq="h"); t = t[(t.hour >= 9) & (t.hour <= 23)]
front = pd.DataFrame(dict(time=t, open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0))
tn = t[t >= "2026-09-01"]
nxt = pd.DataFrame(dict(time=tn, open=105.0, high=106.0, low=104.0, close=105.0,
                        volume=np.where(tn < pd.Timestamp("2026-10-20"), 100.0, 2000.0)))
s, sw, gap = E.stitch_prev(nxt, front)
check(sw == pd.Timestamp("2026-10-20") and gap == 5.0, "switch = day after the expiring contract last led on volume; gap measured +5")
check(len(s) > 2 * len(nxt) and (s["close"] == 105.0).all() and s["time"].is_monotonic_increasing,
      "older history shifted by the gap -> one continuous series, no jump")
d = s.groupby(s["time"].dt.normalize()).size()
check(len(d) >= 205, f"enough daily candles for the daily breakout ({len(d)} ≥ 205; next contract alone had {nxt['time'].dt.normalize().nunique()})")
check((s[s["time"] >= sw]["volume"] == 2000).all(), "after the switch: the new contract's own prices and volume")
check(E.stitch_prev(nxt.assign(volume=100.0), front)[1] is None, "expiring contract still leads on volume -> no stitch")
check(E.stitch_prev(nxt, None)[1] is None, "no older data -> unchanged")
print(f"\nroll-stitch: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
