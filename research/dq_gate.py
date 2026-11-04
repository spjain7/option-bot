"""Research data-quality gate (DATA-AUDIT-001). Every research loader asks here before a dataset is used.

Statuses: VERIFIED (checked against an independent official source and passed) · ACCEPTABLE (checked, known minor
issues) · DEGRADED (checked with material issues, or not independently verifiable – results need a VERIFIED re-test
before any status change) · INVALID (must not be used; require() raises).
Source of truth: research/data_quality/manifest.json (python -m research.data_audit).
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "research" / "data_quality" / "manifest.json"
ORDER = ["VERIFIED", "ACCEPTABLE", "DEGRADED", "INVALID"]
BHAV_START = pd.Timestamp("2022-07-01")


class DataInvalid(RuntimeError):
    pass


def _man():
    try:
        return json.loads(MANIFEST.read_text())["datasets"]
    except Exception:
        return {}


def status(exch, name, iv, source="angel", start=None):
    """-> (status, reasons). source 'verified' = research/continuous_verified.py (bhavcopy)."""
    if source == "verified":
        return "VERIFIED", ["MCX bhavcopy, OI-leader roll, exact roll gaps (daily only, from 2022-07-01)"]
    if exch != "MCX":
        return "DEGRADED", ["not yet audited against an official source (NSE bhavcopy audit pending)"]
    m = _man().get(name)
    if not m:
        return "DEGRADED", ["no audit record – run python -m research.data_audit"]
    st, why = m.get("status", "DEGRADED"), list(m.get("reasons", []))
    if iv != "ONE_DAY":
        why.append("intraday: only the daily aggregate is checked; roll gaps uncorrected in the raw file")
        st = max(st, "DEGRADED", key=ORDER.index)
    if start is None or pd.Timestamp(start) < BHAV_START:
        why.append("history before 2022-07-01 has no independent check (Angel close = last trade then, rolls uncorrected)")
        st = max(st, "DEGRADED", key=ORDER.index)
    return st, why


def require(exch, name, iv, source="angel", start=None, allow=("VERIFIED", "ACCEPTABLE", "DEGRADED")):
    st, why = status(exch, name, iv, source, start)
    if st not in allow:
        raise DataInvalid(f"{exch} {name} {iv} ({source}) is {st}: {'; '.join(why)}")
    return st, why
