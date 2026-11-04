"""Scan outcome record (alerts/run.scan_record): status classification and sequence advance."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts.run import scan_record  # noqa: E402

t0, t1 = pd.Timestamp("2026-11-04 15:32"), pd.Timestamp("2026-11-04 15:45:30")
ok = dict(instruments={"GOLD": {"bo_3h": "none"}}, errors=[])
r = scan_record(None, t0, t1, dict(calls=20, ok=20), ok, 0)
assert r["status"] == "SUCCESS" and r["seq"] == 1 and r["seconds"] == 810, r
assert scan_record(r, t0, t1, dict(calls=20, ok=10, deadline_skips=5, skipped=5), ok, 0)["status"] == "BUDGET_EXHAUSTED"
assert scan_record(r, t0, t1, dict(calls=20, ok=10, rate_limited=4, skipped=3), ok, 0)["status"] == "RATE_LIMITED"
assert scan_record(r, t0, t1, dict(calls=5, ok=5), dict(instruments={"GOLD": {}}, errors=[]), 0)["status"] == "NO_DATA"
assert scan_record(r, t0, t1, dict(calls=5, ok=5), dict(instruments=ok["instruments"], errors=["x"]), 0)["status"] == "PARTIAL_SUCCESS"
assert scan_record(r, t0, t1, {}, ok, 2)["seq"] == 2, "sequence must advance from the previous record"
print("ALL SCAN RECORD CHECKS PASSED")
