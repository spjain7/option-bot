"""19-Nov-2026 reversal SELL basket (alerts/rulebook.py RB_STK_*_REV_*_SELL): 8 LIVE stock SELL rules, stop 2 ATR, target 1R,
signal = reversal TOP while the daily trend is DOWN and the stock is ABOVE its daily EMA200 (previous completed day).
python -m alerts.tests.test_reversal_sell"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import rulebook as RB  # noqa: E402

ok = 0


def check(n, c):
    global ok
    assert c, n
    ok += 1; print("✅", n)


REV = {k: v for k, v in RB.RULES.items() if v["fam"] == "REV"}
check("8 reversal SELL rules, all LIVE stock SELL, SL 2 ATR, target 1R, filter DT+A200",
      len(REV) == 8 and all(v["mkt"] == "STOCKS" and v["side"] == "SELL" and v["status"] == "LIVE" and v["k"] == 2.0 and v["r"] == 1.0
                            and v["filt"] == "DT+A200" for v in REV.values()))
check("4-hour: TD9P / TD9 / CCI200 · daily: TD9P / TD9 / WPR20 / STOCH80 / FISHER",
      sorted(v["par"] for v in REV.values() if v["tf"] == "4h") == ["CCI200", "TD9", "TD9P"]
      and sorted(v["par"] for v in REV.values() if v["tf"] == "1d") == ["FISHER", "STOCH80", "TD9", "TD9P", "WPR20"])
check("no reversal BUY rule", not any(v["fam"] == "REV" and v["side"] == "BUY" for v in RB.RULES.values()))

# TD Sequential 9: nine closes in a row above the close 4 candles earlier
n = 260
t = pd.date_range("2025-06-02", periods=n, freq="B")
base = np.r_[np.linspace(100, 80, n - 13), np.linspace(80.5, 87, 13)]
f = pd.DataFrame(dict(time=t, open=base - 0.2, high=base + 0.5, low=base - 0.5, close=base, volume=1000.0))
S = RB.rev_tops(f)
up_start = n - 13
check("TD9 fires on the 9th consecutive close above the close 4 candles earlier", S["TD9"].any() and int(np.flatnonzero(S["TD9"])[-1]) >= up_start)
i9 = int(np.flatnonzero(S["TD9"])[-1])
F = RB.features(f.iloc[:i9 + 1])


def dtr_with(trend, a200_last=None, a200_day=None):
    s = pd.Series([float(trend)], index=[pd.Timestamp(t[i9 - 1])]); s.attrs["last_day"], s.attrs["last"] = pd.Timestamp(t[i9 - 1]), trend
    if a200_last is not None:
        a = pd.Series(dtype=float); a.attrs["last_day"], a.attrs["last"] = pd.Timestamp(a200_day or t[i9 - 1]), a200_last
        s.attrs["a200"] = a
    return s


rule = RB.RULES["RB_STK_1d_REV_TD9_SELL"]
sig = RB.evaluate(F, rule, dtr_with(-1, 1))
check("signal accepted: daily trend down + above EMA200", sig is not None and "rejected" not in sig)
check("rejected: stock below its daily EMA200", RB.evaluate(F, rule, dtr_with(-1, 0)) == dict(rejected="stock below its daily EMA200"))
check("rejected: daily trend not down", RB.evaluate(F, rule, dtr_with(1, 1))["rejected"] == "daily trend not down")
check("rejected: EMA200 unknown (no long daily history, nothing cached)",
      "EMA200 unknown" in RB.evaluate(F, rule, dtr_with(-1))["rejected"])

# EMA200 flag: computed from >= 250 daily candles, cached per stock, used by the 4-hour scan (short history)
st = {}
d_long = pd.DataFrame(dict(time=pd.date_range("2025-01-01", periods=300, freq="B"), open=0.0, high=0.0, low=0.0,
                           close=np.r_[np.linspace(100, 200, 280), np.linspace(199, 190, 20)], volume=1.0))
a = RB.a200_map(d_long, st, "ABC")
check("long daily history -> flag map, previous day, cached", len(a) == 300 and st["a200"]["ABC"]["v"] == 1 and np.isnan(a.iloc[0]))
a_short = RB.a200_map(d_long.iloc[-130:], st, "ABC")
check("short daily history -> cached flag of the last long run", len(a_short) == 0 and a_short.attrs["last"] == 1
      and str(a_short.attrs["last_day"].date()) == st["a200"]["ABC"]["day"])
check("short history and nothing cached -> unknown", not len(RB.a200_map(d_long.iloc[-130:], st, "XYZ").attrs))
check("describe: reversal text", "TD Sequential 9 top" in RB.describe(rule) and "EMA200" in RB.describe(rule))
print(f"{ok} checks passed")
