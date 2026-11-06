"""6-Nov rate-limit fix: daily OI history cached once per day + today's quote OI; pre-open prefetch; 15:31 scan uses it.
Run: python tests/test_oi_daily_cache.py"""
import sys, tempfile
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import angel as A  # noqa: E402
from alerts import stocks as S  # noqa: E402


def check(name, cond):
    assert cond, name
    print("✅", name)


class Smart:
    def __init__(self): self.n = 0
    def getOIData(self, p):
        self.n += 1
        days = pd.bdate_range(end=pd.Timestamp(p["todate"][:10]), periods=40)
        return {"status": True, "data": [{"time": f"{d:%Y-%m-%d}T00:00:00+05:30", "openInterest": 1000 + i} for i, d in enumerate(days)]}


a = A.Angel.__new__(A.Angel)
a._setup(cache_dir=tempfile.mkdtemp(), ws=False)
a.api = Smart(); A.Angel.HIST_GAP = 0.0
now = pd.Timestamp("2026-11-06 08:45")
d1 = a.oi_daily("NFO", "123", now)
check("first call fetches once and stops at yesterday", a.api.n == 1 and d1["time"].max() < now.normalize())
d2 = a.oi_daily("NFO", "123", now + pd.Timedelta(hours=7), live_oi=5555)
check("later scan same day: no new request, today's row = quote OI", a.api.n == 1 and d2["oi"].iat[-1] == 5555
      and d2["time"].iat[-1] == now.normalize() and len(d2) == len(d1) + 1)
check("cache-only lookup for an unknown token returns None without a request", a.oi_daily("NFO", "999", now, fetch=False) is None and a.api.n == 1)
uni = {f"S{i}": {"token": str(200 + i)} for i in range(5)}
n = S.prefetch_oi_daily(a, uni, now)
check("pre-open prefetch caches every stock (5 requests)", n == 5 and a.api.n == 6)
check("prefetch again: nothing fetched", S.prefetch_oi_daily(a, uni, now) == 5 and a.api.n == 6)
d3 = S._oi_daily(a, {"token": "201"}, now + pd.Timedelta(hours=7), {"201": 777})
check("15:31 helper uses cache + quote OI (no request)", a.api.n == 6 and d3["oi"].iat[-1] == 777)
d4 = S._oi_daily(a, {"token": "201"}, now + pd.Timedelta(hours=7), {})
check("no quote OI -> falls back to the old REST call", d4 is not None and a.api.n == 7)
print("all oi-daily cache checks passed")
