"""Regression tests for the STOCK-OI-BUY-001 candidate logic (research only – nothing here is used by live alerts).
Deterministic fixtures, no network.   python -m tests.test_stock_oi_buy_research"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.search import stock_oi_buy as X  # noqa

OK = []


def check(name, cond):
    assert cond, name
    OK.append(name)
    print("✅", name)


def daily(n=260, px=100.0, step=0.1, seed=1):
    rng = np.random.default_rng(seed)
    t = pd.bdate_range("2025-01-01", periods=n)
    c = px + np.cumsum(rng.normal(step, 1.0, n))
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.2, n)
    h = np.maximum(o, c) + 0.8
    l = np.minimum(o, c) - 0.8
    return pd.DataFrame(dict(time=t, open=o, high=h, low=l, close=c, volume=1000.0))


def test_corporate_actions():
    d = daily(60)
    d.loc[40:, ["open", "high", "low", "close"]] *= 0.2
    d.loc[40:, "volume"] *= 5
    ev = X.corporate_actions(d)
    check("1:5 split detected with the canonical factor 0.2", len(ev) == 1 and ev[0][1] == 0.2 and ev[0][0] == d["time"].iat[40])
    a = X.adjust(d, ev)
    r = a["open"].iat[40] / a["close"].iat[39]
    check("after adjustment the split day has no artificial gap; volume is continuous",
          0.9 < r < 1.1 and abs(a["volume"].iat[39] - a["volume"].iat[40]) < 1e-6)
    check("normal day-to-day moves are not taken as corporate actions", X.corporate_actions(daily(60)) == [])


def test_oi_validity():
    days = pd.bdate_range("2025-03-03", periods=12)
    base = [1000, 1010, 1005, 1020, 1015, 1030, 10, 1045, 1060, 0, 1090, 1123.0]
    raw = pd.DataFrame(dict(time=[str(x.date()) for x in days], oi=base))
    raw = raw.drop(index=[10])                                       # missing day
    oi, doi, why = X.oi_series(raw, days, [])
    check("normal +1.5 % OI change is valid", abs(doi[5] - (1030 / 1015 - 1)) < 1e-12 and why[5] == "ok")
    check("bad tick (−99 %) is rejected, and so is the rebound day measured against it",
          np.isnan(doi[6]) and np.isnan(doi[7]) and why[6] == "outlier" and why[7] == "outlier")
    check("zero OI -> invalid, never a confirmation", np.isnan(doi[9]) and why[9] == "zero")
    check("missing OI day -> invalid (and the next day too)", np.isnan(doi[10]) and np.isnan(doi[11]) and why[10] == "missing")
    oi2, doi2, _ = X.oi_series(raw.assign(oi=raw["oi"].where(raw.index < 8, 5000.0)), days, [])
    check("OI change at day t does not use OI after t (changing later values leaves it unchanged)", doi2[5] == doi[5])
    ev = [(days[4], 0.5)]
    _, doi3, why3 = X.oi_series(raw, days, ev)
    check("corporate-action day -> OI change invalid", np.isnan(doi3[4]) and why3[4] == "corporate action")


def test_features_and_filters():
    d = daily()
    doi = np.full(len(d), 0.03)
    f = X.features(d, doi)
    d2 = d.copy(); d2.loc[200:, ["high", "close"]] += 50
    f2 = X.features(d2, doi)
    check("previous-20-day high / extension at day t unaffected by later data (no look-ahead)",
          f["hh"].iat[199] == f2["hh"].iat[199] and f["ext"].iat[199] == f2["ext"].iat[199])
    i = 250
    check("extension = (close − previous 20-day high) / ATR14",
          abs(f["ext"].iat[i] - (f["close"].iat[i] - d["high"].iloc[i - 20:i].max()) / f["atr"].iat[i]) < 1e-9)
    x = pd.DataFrame(dict(doi=[0.019, 0.02, 0.03, 0.0301, 0.04, 0.05, 0.051, np.nan]))
    check("OI band 2–3 % is inclusive: 2 % and 3 % in, 1.9 % / 3.01 % / NaN out",
          list(X.oi_band(x, 0.02, 0.03)) == [False, True, True, False, False, False, False, False])
    check("OI band 2–5 % keeps 5.0 %, drops 5.1 %", list(X.oi_band(x, 0.02, 0.05))[5:7] == [True, False])
    check("baseline ≥ 2 % (no upper bound) keeps big jumps, drops NaN", list(X.oi_band(x, 0.02, None)) == [False] + [True] * 6 + [False])
    e = pd.DataFrame(dict(close=[101.0, 102.0], hh=[100.0, 100.0], ll=[90.0, 90.0], atr=[2.0, 2.0]))
    check("extension cap 0.5 ATR: 0.5 kept, 1.0 dropped", list(X.ext_cap(e, 0.5)) == [True, False])


def test_base_rule():
    d = daily(300, step=0.3)
    i = 280
    d.loc[i, "close"] = d["high"].iloc[i - 20:i].max() + 1
    d.loc[i, "high"] = d.loc[i, "close"] + 0.2
    d.loc[i, "volume"] = 3000.0
    doi = np.full(len(d), np.nan); doi[i] = 0.02
    f = X.features(d, doi)
    roll = pd.Series(False, index=d.index)
    check("live BUY rule fires at OI exactly +2 %, volume 3×, close above 20-day high", X.base_buy(f, roll)[i])
    check("invalid (NaN) OI -> no BUY", not X.base_buy(f.assign(doi=np.nan), roll)[i])
    r2 = roll.copy(); r2[i] = True
    check("rollover window -> no BUY (exclusion kept)", not X.base_buy(f, r2)[i])


def frame(o, h, l, c, atr=2.0, start="2025-06-02"):
    t = pd.bdate_range(start, periods=len(c))
    return pd.DataFrame(dict(time=t, open=o, high=h, low=l, close=c, atr=atr, hh=0.0, ll=0.0, ext=0.0, doi=0.03))


def test_execution():
    cost = lambda p: 0.0                                   # noqa: E731
    f = frame([100, 101, 102, 103, 104], [101, 102, 103, 104, 105], [99, 100.5, 101.5, 102.5, 103.5], [100, 101.5, 102.5, 103.5, 104.5])
    last = np.array([False, False, False, False, True])
    t = X.simulate(f, 0, last, {}, cost)
    check("next-open entry at 101; held to the expiry session and exited at its close 104.5",
          t["entry"] == 101 and t["why"] == "expiry" and t["exit"] == 104.5 and abs(t["r1"] - 3.5 / 4) < 1e-9)
    f2 = frame([100, 101, 95, 96], [101, 102, 96, 97], [99, 100.5, 94, 95], [100, 101.5, 95.5, 96])
    t2 = X.simulate(f2, 0, np.zeros(4, bool), {}, cost)
    check("gap through the stop (97) -> filled at the open 95, not at the stop", t2["why"] == "stop-gap" and t2["exit"] == 95)
    bars = pd.DataFrame(dict(time=pd.date_range("2025-06-03 09:15", periods=3, freq="h"), open=[103.0, 103.5, 104.0],
                             high=[104.0, 104.2, 104.5], low=[102.8, 103.0, 103.6], close=[103.5, 104.0, 104.2]))
    k, px = X.confirm_fill(bars, 101.05)
    check("confirmation: gap open above trigger -> fill at the OPEN (103) + stop-order slippage, not at the trigger",
          k == 0 and abs(px - 103 * (1 + X.STOP_SLIP)) < 1e-9)
    k, px = X.confirm_fill(bars, 104.1)
    check("confirmation: trigger reached inside bar 2 -> fill at the trigger + slippage", k == 1 and abs(px - 104.1 * (1 + X.STOP_SLIP)) < 1e-9)
    check("confirmation: trigger never traded -> missed (no fill invented)", X.confirm_fill(bars, 110.0) == (None, None))
    f3 = frame([100, 103, 104], [101, 104, 105], [99, 98, 103], [100, 103.5, 104.5])
    f3.loc[0, "high"] = 101.0
    bars3 = pd.DataFrame(dict(time=pd.date_range("2025-06-03 09:15", periods=2, freq="h"), open=[101.5, 101.0],
                              high=[103.0, 101.2], low=[96.5, 98.0], close=[101.0, 100.0]))
    t3 = X.simulate(f3, 0, np.zeros(3, bool), {f3["time"].iat[1].normalize(): bars3}, cost, mode="confirm")
    check("confirmation: the fill bar's low also reaches the stop -> counted as STOPPED (bar order unknown)",
          t3["why"] == "stop" and abs(t3["exit"] - (t3["entry"] - 4.0)) < 1e-9)
    t4 = X.simulate(f3, 0, np.zeros(3, bool), {}, cost, mode="confirm")
    check("confirmation without hourly data -> missed, not filled", t4.get("missed"))
    f5 = frame([100, 100, 100.4, 100.9, 101.1], [100.5, 100.5, 101, 101.4, 101.5], [99.5, 99.5, 100.1, 100.6, 100.9],
               [100, 100.2, 100.8, 101.0, 101.2], atr=1.0)
    t5 = X.simulate(f5, 0, np.r_[np.zeros(4, bool), True], {}, cost)
    check("live trail settings (3 ATR, step 0.25 ATR): small up-drift is held to expiry",
          t5["why"] == "expiry" and X.CFG["trail_atr"] == 3.0 and X.CFG["trail_step"] == 0.25)
    f6 = frame([100, 100, 110, 110, 104], [100.5, 101, 111, 110.5, 104.5], [99.5, 99.5, 109.5, 109, 103.8],
               [100, 100.5, 110.5, 110, 104], atr=1.0)
    t6 = X.simulate(f6, 0, np.zeros(5, bool), {}, cost)
    check("trailing stop follows a new high (110.5 − 3 ATR = 107.5) and exits on the gap below it at the open",
          t6["why"] == "stop-gap" and t6["exit"] == 104)
    z = frame([100, 100.9, 0], [0] * 3, [0] * 3, [100, 0, 0], atr=2.0)
    check("live open zone: open +0.45 ATR from the close -> allowed; +0.6 ATR -> cancelled",
          X.open_zone_ok(z, 0) and not X.open_zone_ok(z.assign(open=[100, 101.2, 0]), 0))
    check("OOS exit model flags the session before the rollover window",
          list(X.last_before_window([False, False, True, True, False])) == [False, True, False, False, False])


if __name__ == "__main__":
    for t in (test_corporate_actions, test_oi_validity, test_features_and_filters, test_base_rule, test_execution):
        t()
    print(f"\nALL {len(OK)} STOCK-OI-BUY RESEARCH CHECKS PASSED")
