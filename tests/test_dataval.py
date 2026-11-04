"""Shared candle validation (candlecheck.py) and quote timestamp references (alerts/tradeplan.quote_check)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import candlecheck as CC  # noqa: E402
from alerts import tradeplan as TP  # noqa: E402


def check(name, cond):
    assert cond, name
    print("✅", name)


t = pd.date_range("2026-11-04 09:15", periods=8, freq="15min")
d = pd.DataFrame(dict(time=t, open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0))
clean, rep = CC.validate(d, now=pd.Timestamp("2026-11-04 12:00"), interval_min=15)
check("clean data passes untouched", len(clean) == 8 and not rep["removed"] and not rep["flags"] and rep["ok"])

bad = d.copy()
bad.loc[1, "high"] = 98.0                                       # high below open/close
bad.loc[2, "close"] = np.nan
bad = pd.concat([bad, bad.iloc[[3]]], ignore_index=True)        # duplicate bar
bad.loc[4, "volume"] = -5
bad.loc[5, "time"] = pd.Timestamp("2026-11-04 15:00")           # bar starting in the future
bad = bad.sample(frac=1, random_state=1)                        # out of order
c2, r2 = CC.validate(bad, now=pd.Timestamp("2026-11-04 11:30"), interval_min=15)
check("inconsistent OHLC removed", r2["removed"].get("inconsistent OHLC") == 1)
check("non-finite price removed", r2["removed"].get("non-finite price") == 1)
check("duplicate bar removed", r2["removed"].get("duplicate time") == 1)
check("future-dated bar removed", r2["removed"].get("bar starts in the future") == 1)
check("negative volume -> missing (never zero)", r2["flags"].get("negative volume (set to missing)") == 1 and c2["volume"].isna().sum() == 1)
check("out-of-order rows sorted back", r2["flags"].get("out of order (sorted)") == 1 and c2["time"].is_monotonic_increasing)
check("result is strictly usable", len(c2) == 5 and (c2["high"] >= c2[["open", "close"]].max(axis=1)).all())
g = d.drop(index=[3, 4, 5, 6]).reset_index(drop=True)
check("intraday gap flagged", CC.validate(g, interval_min=15)[1]["flags"].get("intraday gaps > 3 intervals") == 1)
j = d.copy(); j.loc[5, ["open", "high", "low", "close"]] = [100, 120, 99, 118]
check("price jump flagged, not removed", CC.validate(j, interval_min=15)[1]["flags"] and len(CC.validate(j)[0]) == 8)
check("all-zero volume flagged", "volume all zero / missing" in CC.validate(d.assign(volume=0.0))[1]["flags"])
check("empty / None handled", CC.validate(None)[1]["ok"] is False and CC.validate(d.iloc[:0])[1]["ok"] is False)

# ---- quote timestamps: reference = receipt time, not the scan start ----
scan_start = pd.Timestamp("2026-11-04 14:02:00")
q = {"exchFeedTime": "04-Nov-2026 14:12:40", "_recv_ist": "2026-11-04 14:12:41.300"}
check("quote received 10 min into a slow scan is NOT 'in the future'", TP.quote_check(q, scan_start)[1] is None)
check("same quote without a receipt stamp still trips the old check (reference = caller's now)",
      "in the future" in (TP.quote_check({"exchFeedTime": q["exchFeedTime"]}, scan_start)[1] or ""))
fut = {"exchFeedTime": "04-Nov-2026 14:20:00", "_recv_ist": "2026-11-04 14:12:41"}
check("exchange timestamp genuinely ahead of receipt -> rejected", "in the future" in (TP.quote_check(fut, scan_start)[1] or ""))
skew = {"exchFeedTime": "04-Nov-2026 14:13:20", "_recv_ist": "2026-11-04 14:12:41"}
check("small clock skew (< 60 s) tolerated", TP.quote_check(skew, scan_start)[1] is None)
old = {"exchFeedTime": "04-Nov-2026 14:00:00", "_recv_ist": "2026-11-04 14:12:41"}
check("delayed / stale quote rejected", "stale" in (TP.quote_check(old, scan_start)[1] or ""))
used_late = {"exchFeedTime": "04-Nov-2026 14:02:10", "_recv_ist": "2026-11-04 14:02:11"}
check("quote reused later in the scan judged stale vs decision time", "stale" in (TP.quote_check(used_late, pd.Timestamp("2026-11-04 14:15"))[1] or ""))
check("missing timestamp rejected", "no exchange timestamp" in TP.quote_check({"_recv_ist": "2026-11-04 14:12:41"}, scan_start)[1])
check("malformed timestamp rejected", "malformed" in TP.quote_check({"exchFeedTime": "yesterday"}, scan_start)[1])
check("bad receipt stamp falls back safely", TP.quote_check({"exchFeedTime": q["exchFeedTime"], "_recv_ist": "x"}, pd.Timestamp("2026-11-04 14:13"))[1] is None)
print("ALL DATA VALIDATION CHECKS PASSED")
