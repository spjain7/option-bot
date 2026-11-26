"""26-Nov-2026: system-health notices (alerts/health.py) + pre-open history prefetch (stocks.prefetch_history,
angel.prefetch_day_hist). python -m alerts.tests.test_health"""
import json
import sys
import tempfile
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import health as HL, stocks as SK  # noqa: E402

ok = 0


def check(n, c):
    global ok
    assert c, n
    ok += 1; print("✅", n)


T = pd.Timestamp("2026-11-26 12:30")
rec = dict(status="SUCCESS", errors=0, seconds=120, note="")
FRESH = lambda: {"stk": {"last_block": "2026-11-26 15:30:00"}}   # noqa: E731  stock blocks done (isolates other checks)
# ANGEL: 45 % refused over the hour -> one notice, no repeat within 2 h, resolved after 2 clean scans
st = FRESH()
m1 = HL.check(st, T, rec, dict(calls=40, rate_limited=18, skipped=0))
check("Angel refusals >= 35 % -> notice", len(m1) == 1 and "refusing" in m1[0] and m1[0].startswith(HL.TAG))
m2 = HL.check(st, T + pd.Timedelta(minutes=15), rec, dict(calls=40, rate_limited=18, skipped=0))
check("no repeat within 2 h", m2 == [])
m3 = HL.check(st, T + pd.Timedelta(minutes=135), rec, dict(calls=40, rate_limited=18, skipped=0))
check("reminder after 2 h", len(m3) == 1 and "still open" in m3[0])
t = T + pd.Timedelta(minutes=150)
HL.check(st, t, rec, dict(calls=40, rate_limited=0, skipped=0))
m4 = HL.check(st, t + pd.Timedelta(minutes=70), rec, dict(calls=40, rate_limited=0, skipped=0))
m4 += HL.check(st, t + pd.Timedelta(minutes=85), rec, dict(calls=40, rate_limited=0, skipped=0))
check("resolved message after clean scans", any(x.startswith(HL.OK_TAG) and "normally" in x for x in m4))
check("quiet day -> no notices", HL.check(FRESH(), T, rec, dict(calls=40, rate_limited=2, skipped=0)) == [])
# STOCKS: block finished with many data failures
st = {"stk": {"last_block": "2026-11-26 12:15:00"},
      "funnel": {"2026-11-26": {"STOCK data": {"keys": [f"data|S{i}|2026-11-26 12:15:00" for i in range(172)]}}}}
m = HL.check(st, T, rec, {})
check("12:15 block with 172 unscanned stocks -> notice", any("172 stocks NOT scanned" in x for x in m))
check("block notice only once", not any("NOT scanned" in x for x in HL.check(st, T + pd.Timedelta(minutes=15), rec, {})))
st = {"stk": {"last_block": "2026-11-25 15:30:00"}}
check("12:15 block unfinished at 13:05 -> notice", any("still not finished" in x for x in HL.check(st, pd.Timestamp("2026-11-26 13:05"), rec, {})))
# SCAN: errors 3 in a row
st = FRESH()
bad = dict(status="PARTIAL_SUCCESS", errors=2, seconds=100, note="x")
out = [HL.check(st, T + pd.Timedelta(minutes=15 * i), bad, {}) for i in range(3)]
check("3 failing scans in a row -> notice (not before)", out[0] == [] and out[1] == [] and any("errors" in x for x in out[2]))
# WEBSOCKET
st = FRESH()
out = [HL.check(st, T + pd.Timedelta(minutes=15 * i), rec, dict(ws_hits=0, ws_fallback=5), True) for i in range(3)]
check("WebSocket candles unused 3 scans -> notice", out[1] == [] and any("WebSocket" in x for x in out[2]))
check("market closed -> no WebSocket notice", HL.check(FRESH(), T, rec, dict(ws_hits=0, ws_fallback=5), False) == [])
# PREFETCH
st = {"stk": {"last_block": "2026-11-25 15:30:00"}, "health": {"hist_prefetch": dict(day="2026-11-26", cached=120, total=210)}}
check("pre-open history download < 90 % -> notice at 09:20",
      any("pre-open history" in x for x in HL.check(st, pd.Timestamp("2026-11-26 09:22"), rec, {})))
# WATCHDOG
with tempfile.TemporaryDirectory() as d:
    sj, mem = Path(d) / "scan.json", Path(d) / "m.json"
    sj.write_text(json.dumps(dict(finished="2026-11-26 11:40:00")))
    out, mm = HL.watchdog(sj, mem, pd.Timestamp("2026-11-26 12:30"))
    check("watchdog: 50 min without a scan -> notice", len(out) == 1 and "NO SCAN" in out[0])
    mem.write_text(json.dumps(mm))
    out, mm = HL.watchdog(sj, mem, pd.Timestamp("2026-11-26 13:00"))
    check("watchdog: no repeat within 2 h", out == [])
    mem.write_text(json.dumps(mm)); sj.write_text(json.dumps(dict(finished="2026-11-26 13:17:00")))
    out, mm = HL.watchdog(sj, mem, pd.Timestamp("2026-11-26 13:30"))
    check("watchdog: scans back -> resumed notice", len(out) == 1 and out[0].startswith(HL.OK_TAG))
    out, _ = HL.watchdog(sj, mem, pd.Timestamp("2026-11-28 13:30"))
    check("watchdog: weekend -> silent", out == [])
    out, _ = HL.watchdog(sj, mem, pd.Timestamp("2026-11-26 08:50"))
    check("watchdog: before 09:20 -> silent", out == [])


# PREFETCH (stocks + angel)
class Api:
    def __init__(self):
        self.cached, self.n = set(), 0

    def day_hist_cached(self, ex, tok, iv, now):
        return tok in self.cached

    def prefetch_day_hist(self, ex, tok, iv, now):
        self.n += 1; self.cached.add(tok); return True

    def failfast(self):
        return False

    def over_budget(self):
        return False


a = Api(); uni = {"A": dict(token="1", prev_token=None), "B": dict(token="2", prev_token="3")}
check("prefetch_history caches every series incl. the expiring contract", SK.prefetch_history(a, uni, T) == (3, 3) and a.n == 3)
check("prefetch again: nothing fetched", SK.prefetch_history(a, uni, T) == (3, 3) and a.n == 3)

import angel as AN  # noqa: E402
with tempfile.TemporaryDirectory() as d:
    g = AN.Angel.__new__(AN.Angel); g._dir = Path(d); g.stats = dict(disk_hits=0)
    calls = []
    g._rest = lambda kind, ex, tok, iv, f, t: (calls.append((f, t)) or
                                               pd.DataFrame(dict(time=pd.date_range("2026-11-20", periods=5, freq="D"), open=1, high=1, low=1, close=1, volume=1)))
    check("angel.prefetch_day_hist fetches once and writes the day file",
          g.prefetch_day_hist("NFO", "9", "ONE_HOUR", T) and g.day_hist_cached("NFO", "9", "ONE_HOUR", T) and len(calls) == 1)
    check("second call served from disk", g.prefetch_day_hist("NFO", "9", "ONE_HOUR", T) and len(calls) == 1)
    check("history covers 400 days and stops before today", calls[0][0] <= T.normalize() - pd.Timedelta(days=400) and calls[0][1] < T.normalize())
print(f"{ok} checks passed")
