"""6-Nov-2026: a minute written in several rows (lagging exchange timestamps vs the 15-second flush) must keep its full
volume and its true open/high/low/close.   python tests/test_wsbars_merge.py"""
import sys
import tempfile
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wsbars as WB  # noqa: E402

d = tempfile.mkdtemp()
B = WB.Builder(d)
real0, lag, cv = pd.Timestamp("2026-11-05 09:00:00"), pd.Timedelta(seconds=75), 1000
for s in range(300):
    cv += 5
    px = 100 + (s % 60) / 10                                  # price path inside each minute
    B.tick("7", real0 + pd.Timedelta(seconds=s) - lag, px, cv, 9)
    if s % 15 == 0:
        B.flush(real0 + pd.Timedelta(seconds=s))
B.flush(real0 + pd.Timedelta(minutes=10))
raw = pd.read_csv(Path(d) / "bars_7.csv", names=WB.COLS, header=None, parse_dates=["time"])
m = WB.minutes("7", real0, d)
full = m[(m["time"] > m["time"].min()) & (m["time"] < m["time"].max())]
assert raw["time"].duplicated().any(), "fixture must produce split minutes"
assert (full["volume"] == 300).all(), f"full-minute volume must be 300, got {full['volume'].tolist()}"
assert m["volume"].sum() == raw["volume"].sum(), "no volume lost or double counted"
assert (full["high"] - full["low"]).min() > 5, "high/low span the whole minute, not one row"
agg = WB.aggregate(m, "FIFTEEN_MINUTE", "MCX")
assert agg["volume"].sum() == m.loc[m["time"] >= real0, "volume"].sum()   # 9-Nov: pre-open (08:58/59) minutes are dropped
print("✅ split minutes merged: volume 300/minute, OHLC of the whole minute, 15-min aggregate consistent")
