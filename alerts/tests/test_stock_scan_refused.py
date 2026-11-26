"""26-Nov-2026 fix (alerts/stocks.py): an empty candle fetch while Angel refused requests (rate-limited / skipped / failed)
is NOT counted as scanned – the stock is retried next cycle (max 3 times per block).
python -m alerts.tests.test_stock_scan_refused"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import stocks as SK  # noqa: E402

ok = 0


def check(n, c):
    global ok
    assert c, n
    ok += 1; print("✅", n)


class Api:
    def __init__(self, ff=False, over=False):
        self.stats = dict(rate_limited=0, skipped=0, failed=0)
        self.ff, self.over = ff, over

    def failfast(self):
        return self.ff

    def over_budget(self):
        return self.over


a = Api(); prog = {}
b = SK.refusals(a)
a.stats["rate_limited"] += 3                       # 3 refused retries, streak below fail-fast (the 26-Nov case)
check("refused while fetching -> deferred (not counted as scanned)", SK.defer(a, prog, "SBIN", b) is True)
a2 = Api(); p2 = {}
check("empty data with no refusal -> counted as scanned", SK.defer(a2, p2, "SBIN", SK.refusals(a2)) is False)
check("fail-fast block -> deferred", SK.defer(Api(ff=True), {}, "SBIN", 0) is True)
check("time budget used up -> deferred", SK.defer(Api(over=True), {}, "SBIN", 0) is True)
p3 = {}
for _ in range(SK.MAX_DEFER):
    SK.defer(Api(ff=True), p3, "SBIN", 0)
check("after MAX_DEFER retries the stock is counted as scanned", SK.defer(Api(ff=True), p3, "SBIN", 0) is False)
check("client without stats -> no refusals", SK.refusals(object()) == 0)
print(f"{ok} checks passed")
