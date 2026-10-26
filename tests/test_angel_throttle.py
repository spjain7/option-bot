"""Offline tests for angel.Angel rate-limit handling (shared cool-down, fail-fast, shared candle cache, counters).
Run: python tests/test_angel_throttle.py"""
import json, sys, tempfile, time
from pathlib import Path
from unittest import mock
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import angel as A  # noqa: E402

RATE_MSG = "Couldn't parse the JSON response received from the server: b'Access denied because of exceeding access rate'"


def check(name, cond):
    assert cond, name
    print("✅", name)


class FakeSmart:
    """Stands in for SmartConnect. `script` = list of outcomes consumed per call: 'ok' | 'rate' | 'rate_json' | 'nodata'."""
    def __init__(self, script=None, default="ok"):
        self.script, self.default, self.n = list(script or []), default, 0

    def _next(self):
        self.n += 1
        return self.script.pop(0) if self.script else self.default

    def getCandleData(self, p):
        o = self._next()
        if o == "rate":
            raise Exception(RATE_MSG)
        if o == "rate_json":
            return {"status": False, "message": "Access denied because of exceeding access rate", "errorcode": "AB1021", "data": None}
        if o == "nodata":
            return {"status": False, "message": "Invalid Bad Request", "errorcode": "AB1012", "data": None}
        return {"status": True, "data": [["2026-10-26T09:00:00+05:30", 1, 2, 0.5, 1.5, 100],
                                          ["2026-10-26T10:00:00+05:30", 1.5, 2.5, 1, 2, 120]]}

    getOIData = getCandleData

    def getMarketData(self, mode, d):
        o = self._next()
        if o == "rate":
            raise Exception(RATE_MSG)
        return {"status": True, "data": {"fetched": [{"symbolToken": "1", "ltp": 10.0}]}}


def make(tmp, smart):
    a = A.Angel.__new__(A.Angel)
    a.api = smart
    a._setup(cache_dir=tmp)
    a.HIST_GAP = a.QUOTE_GAP = 0           # no pacing in tests
    return a


T0 = pd.Timestamp("2026-10-26 09:00")
NOW = pd.Timestamp("2026-10-26 14:50")


def test_normal_and_caches():
    with tempfile.TemporaryDirectory() as d:
        s1 = FakeSmart()
        a = make(d, s1)
        df = a.candles("MCX", "111", "ONE_HOUR", T0, NOW)
        check("normal fetch returns candles", df is not None and len(df) == 2 and a.stats["ok"] == 1)
        a.candles("MCX", "111", "ONE_HOUR", T0, NOW)
        check("same series again in the same process = memory hit, no new request", s1.n == 1 and a.stats["mem_hits"] == 1)
        s2 = FakeSmart()
        b = make(d, s2)                                    # another engine process of the same job
        df2 = b.candles("MCX", "111", "ONE_HOUR", T0, NOW + pd.Timedelta(seconds=90))
        check("another engine process re-uses the series from disk (no request)", s2.n == 0 and b.stats["disk_hits"] == 1 and len(df2) == 2)
        check("disk-cached frame is identical", df2["close"].tolist() == df["close"].tolist())
        b2 = make(d, FakeSmart())
        b2.candles("MCX", "111", "ONE_HOUR", T0 - pd.Timedelta(days=5), NOW)
        check("a request reaching further back than the cached series is NOT served from cache", b2.api.n == 1)
        e = pd.read_pickle(next(Path(d).glob("c_MCX_111_ONE_HOUR.pkl")))
        e["saved"] -= A.Angel.DISK_TTL + 5
        pd.to_pickle(e, next(Path(d).glob("c_MCX_111_ONE_HOUR.pkl")))
        c = make(d, FakeSmart())
        c.candles("MCX", "111", "ONE_HOUR", T0, NOW)
        check("expired disk entry (older than the TTL) is refetched", c.api.n == 1)
        f = make(d, FakeSmart())
        f.candles("MCX", "111", "ONE_HOUR", T0, NOW + pd.Timedelta(minutes=30))
        check("a series fetched for a much earlier 'now' is refetched", f.api.n == 1)


def test_failures_not_cached():
    with tempfile.TemporaryDirectory() as d:
        a = make(d, FakeSmart(["nodata"]))
        check("'no data' reply returns None", a.candles("MCX", "5", "ONE_DAY", T0, NOW) is None)
        check("'no data' is a real answer: not retried, breaker untouched", a.api.n == 1 and a._breaker()[1] == 0)
        check("failures are never written to the shared disk cache", not list(Path(d).glob("c_*.pkl")))


def test_cooldown_then_retry():
    with tempfile.TemporaryDirectory() as d:
        a = make(d, FakeSmart(["rate", "ok"]))
        with mock.patch("angel.time.sleep") as sl:
            df = a.candles("MCX", "7", "ONE_HOUR", T0, NOW)
        check("one rate-limit error, retried after the cool-down, then succeeds", df is not None and a.api.n == 2)
        check("cool-down pause was taken before the retry", sl.called and max(c.args[0] for c in sl.call_args_list) >= 1)
        check("breaker cleared again after the success", a._breaker()[1] == 0)
        check("rate-limit and ok counted", a.stats["rate_limited"] == 1 and a.stats["ok"] == 1)
        a2 = make(d, FakeSmart(["rate_json", "ok"]))
        with mock.patch("angel.time.sleep"):
            check("rate limit given as a JSON reply (AB1021) is handled the same way", a2.candles("MCX", "8", "ONE_HOUR", T0, NOW) is not None)


def test_failfast_and_probe():
    with tempfile.TemporaryDirectory() as d:
        s = FakeSmart(default="rate")
        a = make(d, s)
        with mock.patch("angel.time.sleep") as sl:
            res = [a.candles("MCX", str(i), "ONE_HOUR", T0, NOW) for i in range(12)]
        check("blocked API: every call returns None", all(r is None for r in res))
        check("blocked API: requests stop after a few errors (12 series x 3 tries would be 36)", s.n <= A.Angel.FAILFAST_AFTER + 1)
        check("blocked API: the rest were skipped, not sent", a.stats["skipped"] >= 6)
        check("fail-fast flag is on while blocked", a.failfast() is True)
        slept = sum(c.args[0] for c in sl.call_args_list)
        check("total waiting stays bounded (< 6 min), no endless retries", slept < 360)
        b = make(d, FakeSmart())
        check("a second engine process sees the shared block and skips calls", b.candles("MCX", "99", "ONE_HOUR", T0, NOW) is None and b.api.n == 0)
        (Path(d) / "breaker.json").write_text(json.dumps({"until": time.time() - 1, "streak": 6}))
        check("after the pause is over the next call is a probe", b.failfast() is False)
        check("probe succeeds -> calls flow again", b.candles("MCX", "100", "ONE_HOUR", T0, NOW) is not None and b._breaker()[1] == 0)


def test_quotes_and_stats():
    with tempfile.TemporaryDirectory() as d:
        a = make(d, FakeSmart(["rate", "ok"]))
        with mock.patch("angel.time.sleep"):
            q = a.quotes({"MCX": ["1"]})
        check("quotes: rate-limit error retried after the cool-down", q.get("1", {}).get("ltp") == 10.0 and a.api.n == 2)
        calls = (Path(d) / "calls.log").read_text().split()
        check("every real request is logged for the hourly total", len(calls) == 2)
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            a.report()
        out = buf.getvalue()
        check("end-of-run summary line printed", "[angel-stats]" in out and "API requests=2" in out and "rate-limited=1" in out and "last 60 min=2" in out)


def test_detection():
    check("'exceeding access rate' text detected", A.Angel._is_rate(RATE_MSG))
    check("AB1021 detected", A.Angel._is_rate("AB1021 Too many requests"))
    check("ordinary errors are not treated as rate limits", not A.Angel._is_rate("Invalid Bad Request AB1012") and not A.Angel._is_rate("Connection reset"))


if __name__ == "__main__":
    for t in (test_normal_and_caches, test_failures_not_cached, test_cooldown_then_retry, test_failfast_and_probe, test_quotes_and_stats, test_detection):
        t()
    print("all angel throttle tests passed")
