"""python tests/test_angel_quiet_hours.py"""
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from angel_quiet_hours import busy  # noqa: E402
cases = {"2026-11-06 15:15": True, "2026-11-06 08:29": False, "2026-11-06 08:30": True, "2026-11-06 23:59": True,
         "2026-11-07 00:20": True, "2026-11-07 00:31": False, "2026-11-07 12:00": False, "2026-11-08 12:00": False,
         "2026-11-09 00:20": False, "2026-11-09 09:00": True, "2026-11-10 03:00": False}
for t, exp in cases.items():
    assert busy(datetime.fromisoformat(t)) is exp, (t, exp)
print(f"✅ {len(cases)} quiet-hour cases (6-Nov 15:15 IST overlap now blocked; Fri night / weekend allowed)")
