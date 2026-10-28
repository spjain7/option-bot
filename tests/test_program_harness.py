"""Regression tests for the STRATEGY-PROGRAM-001 research harness (research only; deterministic fixtures, no network).
python -m tests.test_program_harness"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.program import harness as H  # noqa: E402

OK = []


def check(name, cond):
    assert cond, name
    OK.append(name)
    print("✅", name)


def frame(o, h, l, c, atr=1.0, switch=None):
    n = len(c)
    return pd.DataFrame(dict(time=pd.date_range("2025-01-01", periods=n, freq="D"), open=o, high=h, low=l, close=c,
                             atr=atr, switch=switch if switch is not None else [False] * n))


def sig_at(n, i, s=1):
    a = np.zeros(n, int); a[i] = s; return a


ZERO = np.zeros(10)


def test_execution():
    # signal bar 0, entry next open 100, stop 2 ATR = 98, target 1R = 102
    f = frame([100, 100, 101, 101], [100.5, 101, 103, 103], [99.5, 99.5, 97, 100], [100, 100.5, 102, 102])
    t = H.simulate(f, sig_at(4, 0), 1, 2.0, 1.0, 40, None, ZERO, start=0)[0]
    check("stop and target crossed in the SAME bar -> counted as a STOP (conservative ordering)", t["exit"] == "stop" and t["r1"] == -1.0)
    f2 = frame([100, 100, 97, 97], [100.5, 101, 97.5, 98], [99.5, 99.6, 96, 96.5], [100, 100.5, 97, 97])
    t2 = H.simulate(f2, sig_at(4, 0), 1, 2.0, 1.0, 40, None, ZERO, start=0)[0]
    check("gap below the stop -> filled at the OPEN 97 (−1.5R), not at the stop", t2["exit"] == "stop-gap" and abs(t2["r1"] + 1.5) < 1e-9)
    f3 = frame([100, 100.8, 101], [100.5, 101, 101], [99.5, 100.5, 100.5], [100, 100.9, 101])
    t3 = H.simulate(f3, sig_at(3, 0), 1, 2.0, 1.0, 40, None, ZERO, start=0)[0]
    check("next open 0.8 ATR beyond the signal close -> INVALIDATED (live chase rule), no trade", t3["status"] == "invalidated")
    f4 = frame([100, 100, 100.5, 104], [100.5, 100.6, 101, 104.5], [99.5, 99.8, 100, 103.5], [100, 100.4, 100.8, 104], switch=[False, False, False, True])
    t4 = H.simulate(f4, sig_at(4, 0), 1, 2.0, 5.0, 40, None, ZERO, start=0)[0]
    check("contract switch -> exit at the old contract's last close (100.8), the new contract's price is not used",
          t4["exit"] == "roll" and abs(t4["r1"] - 0.4) < 1e-9)
    t5 = H.simulate(frame([100, 100, 101], [100.5, 101, 101], [99.5, 99.5, 100], [100, 100.5, 101], atr=3.0),
                    sig_at(3, 0), 1, 2.0, 1.0, 40, 2.5, ZERO, start=0)[0]
    check("stop wider than the live cap (6 % > 2.5 %) -> INVALIDATED", t5["status"] == "invalidated" and "wider" in t5["why"])
    f6 = frame([100, 100, 99.5, 99], [100.5, 100.5, 99.8, 99.2], [99.5, 99.4, 99, 98.9], [100, 99.6, 99.2, 99.0])
    t6 = H.simulate(f6, sig_at(4, 0, -1), -1, 2.0, 1.0, 40, None, ZERO, start=0)[0]
    check("SELL side: target below entry hit at 98 is NOT reached; trade stays open to the end (no invented win)", t6["exit"] == "open-at-end")
    t7 = H.simulate(f, sig_at(4, 0), 1, 2.0, 1.0, 40, None, np.full(10, 0.2), start=0)[0]
    check("costs reduce R: −1R stop becomes −1.1R with 0.2 points cost on a 2-point risk", abs(t7["r1"] + 1.1) < 1e-9 and abs(t7["r2"] + 1.2) < 1e-9)


def test_features_no_lookahead():
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 1, 400))
    df = pd.DataFrame(dict(time=pd.date_range("2024-01-01", periods=400), open=c, high=c + 1, low=c - 1, close=c, volume=1000.0))
    a = H.features(df)
    df2 = df.copy(); df2.loc[300:, ["high", "close"]] += 50
    b = H.features(df2)
    cols = ["hh", "ll", "atr", "ema200", "adx", "rsi", "volx", "comp", "hi120", "clv"]
    check("every feature at bar 299 is unchanged when bars 300+ change (no look-ahead)",
          all(np.isclose(a[x].iat[299], b[x].iat[299], equal_nan=True) for x in cols))
    m = H.F(a, 1)
    check("13 pre-declared filters, each a boolean mask of the same length", len(m) == 13 and all(len(v) == 400 for v in m.values()))


def test_metrics():
    g = pd.DataFrame(dict(time=pd.date_range("2025-01-01", periods=10, freq="W"), status="trade",
                          r1=[0.5] * 8 + [-1.0] * 2, r2=[0.45] * 8 + [-1.05] * 2, exit=["target"] * 8 + ["stop"] * 2))
    m = H.metrics(g)
    check("metrics: 80 % wins, expectancy +0.2R, PF 2.0, target / stop rates", m["win"] == 80 and m["exp1"] == 0.2 and m["pf"] == 2.0
          and m["tgt"] == 80 and m["stop"] == 20)


if __name__ == "__main__":
    for t in (test_execution, test_features_no_lookahead, test_metrics):
        t()
    print(f"\nALL {len(OK)} PROGRAM-HARNESS CHECKS PASSED")
