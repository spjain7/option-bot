"""6-Nov signal funnel: counts once per instrument + candle, rejection reasons, summary text.  python alerts/tests/test_funnel.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from alerts import funnel as FN  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


st = {"day": {"date": "2026-11-06"}}
for _ in range(3):
    FN.note(st, "MCX 4h BUY", "signal", key="GOLD|2026-11-06 09:00")
FN.note(st, "MCX 4h BUY", "rejected", "OI Long unwinding", key="GOLD|2026-11-06 09:00")
FN.note(st, "MCX 4h BUY", "signal", key="SILVER|2026-11-06 09:00")
FN.note(st, "MCX 4h BUY", "sent", key="SILVER|2026-11-06 09:00")
FN.note(st, "STOCK 1d BUY", "signal", key="TITAN|x"); FN.note(st, "STOCK 1d BUY", "shadow", key="TITAN|x")
FN.note(st, "MCX data", "data", key="GOLD|1h|10")
r = st["funnel"]["2026-11-06"]["MCX 4h BUY"]
check(r["signal"] == 2 and r["sent"] == 1 and r["rejected"] == {"OI Long unwinding": 1}, "a signal re-checked every 15 min is counted once")
check(FN.classify("BUY · · vol 2.1× · skipped: OI Short buildup does not confirm") == ("rejected", "OI Short buildup does not confirm")
      and FN.classify("SELL · · 3h SELL logged only (registry SHADOW: x)")[0] == "shadow", "engine info strings -> stage + reason")
m = FN.summary(st)
check("TOTAL: 3 signals → 1 sent · 1 logged only · 1 rejected" in m and "OI Long unwinding ×1" in m and "1 data failures" in m,
      "daily summary shows totals, reasons and data failures")
print(f"\nfunnel: {ok} passed")
