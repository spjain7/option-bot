"""Offline test: support / resistance line in every setup call + 3h SELL skipped into support. python -m alerts.tests.test_sr"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import candle_setups as CS

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


n = 120
t = pd.date_range("2026-06-01", periods=n, freq="D")
c = 100 + 3 * np.sin(np.arange(n) / 5.0)
df = pd.DataFrame(dict(time=t, open=c, high=c + 1, low=c - 1, close=c, volume=1000.0))
txt, dr = CS.sr_line(df, "BUY", 100.0, 98.0, 2.0)
check("Resistance" in txt and dr is not None and dr > 0, "BUY: nearest resistance above the trigger with its distance in R")
check(("BEFORE the 2R target" in txt) == (dr < 2), "warning only when the level lies before the target")
txt2, dr2 = CS.sr_line(df, "SELL", 100.0, 102.0, 2.0)
check("Support" in txt2 and dr2 is not None and dr2 > 0, "SELL: nearest support below the trigger")
flat = pd.DataFrame(dict(time=t, open=np.linspace(50, 200, n), high=np.linspace(51, 201, n), low=np.linspace(49, 199, n),
                         close=np.linspace(50, 200, n), volume=1000.0))
txt3, dr3 = CS.sr_line(flat, "BUY", 202.0, 199.0, 2.0)
check("none found" in txt3 or (dr3 is not None and dr3 >= 2), "steady rise to a new high: no resistance before the target")
r = dict(setup="STK_HANGMAN", name="X", contract="XFUT", side="SELL", trigger=100.0, stop=102.0, tick=0.05, mult=1, lot=1,
         pattern_time="2026-10-29", pattern=dict(open=101, high=102, low=100, close=101.5), vol_x=1.0, trend_ok=True, sr=txt2)
check(txt2 in CS.setup_msg(r), "the S/R line is part of the setup message")
# OI line (30-Oct)
d = pd.DataFrame(dict(time=pd.date_range("2026-10-27", periods=3), close=[100.0, 101.0, 99.0], oi=[1000.0, 1100.0, 1210.0]))
note = CS.oi_from_daily(d)
check(note and "+10.0% on the day" in note and "Short buildup" in note, "stock OI note from daily OI: change and buildup label")
r2 = dict(r, oi_note=note)
check("• OI         : 1,210" in CS.setup_msg(r2), "setup message carries the OI line")
check("• OI         : not available" in CS.setup_msg(dict(r, oi_note=None)), "missing OI is said, never invented")
er = dict(r, entry=100.0, risk=2.0, target=96.0, oi_entry="16,071 (−0.37% in 15 min) → Short buildup")
check("Short buildup" in CS.entry_msg(er, False), "TRIGGERED message carries the OI at entry")

print(f"\nsr: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
