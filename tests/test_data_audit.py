"""DATA-AUDIT-001: verified continuous construction (OI-leader roll, exact gap, back-adjust) and the research gate."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research import continuous_verified as CV, dq_gate as G  # noqa: E402


def check(name, cond):
    assert cond, name
    print("✅", name)


rows = []
days = pd.bdate_range("2024-01-01", periods=6)
for i, d in enumerate(days):
    # contract A expires day 5; B leads OI from day 3 on; B trades 10 above A (contango)
    a_oi, b_oi = (100, 20) if i < 3 else (30, 120)
    rows.append(dict(date=d, symbol="TEST", exp=days[5], open=100 + i, high=101 + i, low=99 + i, close=100 + i,
                     volume_lots=50, oi_lots=a_oi))
    rows.append(dict(date=d, symbol="TEST", exp=pd.Timestamp("2024-02-28"), open=110 + i, high=111 + i, low=109 + i,
                     close=110 + i, volume_lots=50, oi_lots=b_oi))
CV._bhav.cache_clear()
CV._bhav = lambda: pd.DataFrame(rows)
d = CV.build("TEST")
check("rolls on the first day the next contract leads open interest", list(d["roll"]) == [False, False, False, True, False, False]
      and str(d["contract"].iloc[3]) == "2024-02-28")
check("exact same-day gap stored on the old contract's last day", d["gap"].iloc[2] == 10.0 and d["gap"].sum() == 10.0)
check("back-adjusted: no artificial jump, raw prices kept", d["close"].diff().iloc[3] == 1.0 and d["raw_close"].iloc[2] == 102
      and d["close"].iloc[2] == 112 and d["close"].iloc[-1] == d["raw_close"].iloc[-1])
check("verified series is VERIFIED", (d["status"] == "VERIFIED").all() and G.status("MCX", "GOLD", "ONE_DAY", "verified")[0] == "VERIFIED")

check("unaudited / pre-bhavcopy data is at best DEGRADED", G.status("NFO", "NIFTY", "ONE_DAY")[0] == "DEGRADED"
      and G.status("MCX", "GOLD", "ONE_HOUR", start="2020-01-01")[0] == "DEGRADED")
try:
    G.require("MCX", "GOLD", "ONE_HOUR", allow=("VERIFIED",))
    raise AssertionError("gate did not refuse")
except G.DataInvalid:
    print("✅ gate refuses a dataset below the required status")
print("ALL DATA-AUDIT CHECKS PASSED")
