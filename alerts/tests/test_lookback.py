"""Offline test: MCX BUY breakout lookback (daily 5, 3-hour 10); SELL and index stay 20. python -m alerts.tests.test_lookback"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import breakout as BO

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


n = 260
t = pd.date_range("2026-01-01", periods=n, freq="D")
c = np.linspace(100, 130, n)
df = pd.DataFrame(dict(time=t, open=c, high=c + 1, low=c - 1, close=c, volume=1000.0))
df.loc[n - 9, "high"] = c[n - 9] + 8                  # an 8-day-old spike: the 20-day high is above the 5-day high
df.loc[n - 1, ["close", "high", "volume"]] = [c[-1] + 3.0, c[-1] + 3.1, 3000.0]
a, b = BO.evaluate(df), BO.evaluate(df, n_buy=5)
check(a["side"] is None and b["side"] == "BUY", "close above the 5-day high but below the 20-day high: BUY only with the 5-day lookback")
check(b["hh"] < a["hh"] and b["ll"] == a["ll"], "the SELL level (20-candle low) is unchanged")
check(BO.BUY_LOOKBACK_MCX == {"1d": 5, "3h": 10}, "MCX lookbacks: daily 5, 3-hour 10")
msg = BO.reason_msg("GOLD", "1d", dict(b, close=float(df.close.iloc[-1])), dict(support=[], resistance=[]))
check("5-day high" in msg, "WHY message names the 5-day high")
print(f"\nlookback: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
