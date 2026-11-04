"""Offline checks for alerts/news.py (no internet: the feed is faked)."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import news as N  # noqa: E402

T = pd.Timestamp("2026-11-04 13:40")
N._fetch = lambda q, timeout=8: [dict(title="Oil prices jump after OPEC output cut - Reuters", link="x", time=T - pd.Timedelta(minutes=20)),
                                 dict(title="Gold slips as dollar rises - Mint", link="y", time=T - pd.Timedelta(minutes=30))]
N._CACHE.clear()
ev = N.events(T, 72)
assert ("EIA_CRUDE", pd.Timestamp("2026-11-04 21:00")) in ev, ev            # EST after 1-Nov -> 21:00 IST
assert ("US_JOBS", pd.Timestamp("2026-11-06 19:00")) in ev, ev
assert N._et_to_ist(pd.Timestamp("2026-07-01"), "10:30") == pd.Timestamp("2026-07-01 20:00")   # EDT -> 20:00 IST
call = "🔴 SELL  CRUDEOIL FUT  ·  Positional\n━━\nEntry   : 6000\nSL      : 6100\nTarget  : 5800"
out = N.enrich([call, "📊 day report"], T)
assert "OPEC output cut" in out[0] and "AGAINST this SELL" in out[0] and "EIA crude" in out[0], out[0]
assert "Gold slips" not in out[0], "gold headline must not appear under crude"
assert out[1] == "📊 day report"
st = {}
a = N.alerts(st, T)
assert any("HIGH-IMPACT" in m and "OPEC" in m for m in a), a
assert N.alerts(st, T + pd.Timedelta(minutes=15)) == [], "same headline must not repeat"
ng = N.alerts({}, pd.Timestamp("2026-11-05 19:30"))
assert any("natural-gas storage" in m for m in ng), ng
assert not any("EIA crude" in m for m in N.alerts({}, pd.Timestamp("2026-11-04 19:30"))), "EIA crude hour is not a big mover -> no heads-up"
N.NEWS_ENABLED = False
assert N.enrich([call], T) == [call]
print("ALL NEWS CHECKS PASSED")
