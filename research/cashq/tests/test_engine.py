"""Engine unit tests on hand-made bars (synthetic data is used ONLY to test the mechanics, never for performance).
python -m research.cashq.tests.test_engine"""
import numpy as np
import pandas as pd
from research.cashq import sim, div, ind, validate as V, data as D

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


def bars(rows):
    a = np.array(rows, float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


z = np.zeros(6, np.int64); nan = np.full(6, np.nan)
o, h, l, c = bars([[100, 101, 99, 100], [100, 103, 99.5, 102], [102, 102.5, 97, 98], [98, 99, 97, 98], [98, 99, 97, 98], [98, 99, 97, 98]])
sig = np.array([1, 0, 0, 0, 0, 0], bool); rd = np.full(6, 2.0)
ei, xi, ep, xp, gr, cd = sim.run(o, h, l, c, sig, 1, rd, 1.0, 0, nan, z, z, False, 0, 0)
check(ei[0] == 1 and ep[0] == 100 and cd[0] == 2 and xp[0] == 102 and gr[0] == 1.0, "entry next open; target 1R hit in the entry bar")
o2, h2, l2, c2 = bars([[100, 101, 99, 100], [100, 103, 97.5, 102], [102, 102, 101, 101], [101, 101, 100, 100], [100, 100, 99, 99], [99, 99, 98, 98]])
ei, xi, ep, xp, gr, cd = sim.run(o2, h2, l2, c2, sig, 1, rd, 1.0, 0, nan, z, z, False, 0, 0)
check(cd[0] == 1 and xp[0] == 98 and gr[0] == -1.0, "stop and target in the same bar -> stop first (conservative)")
o3, h3, l3, c3 = bars([[100, 101, 99, 100], [100, 101, 99.5, 100.5], [95, 96, 94, 95], [95, 96, 94, 95], [95, 96, 94, 95], [95, 96, 94, 95]])
ei, xi, ep, xp, gr, cd = sim.run(o3, h3, l3, c3, sig, 1, rd, 2.0, 0, nan, z, z, False, 0, 0)
check(cd[0] == 1 and xp[0] == 95 and gr[0] == -2.5, "gap through the stop fills at the open (−2.5R)")
ei, xi, ep, xp, gr, cd = sim.run(o2, h2, l2, c2, sig, -1, np.full(6, 10.0), 0.0, 3, nan, z, z, False, 0, 0)
check(cd[0] == 3 and xi[0] == 3, "short side + time exit after 3 bars")
lock = h.copy(); lock[1] = l[1]
ei, *_ = sim.run(o, lock, l, c, sig, 1, rd, 1.0, 0, nan, z, z, False, 0, 0)
check(len(ei) == 0, "locked next bar (high == low: circuit) -> no fill")
day = np.array([1, 1, 1, 2, 2, 2], np.int64); mins = np.array([900, 905, 910, 555, 560, 565], np.int64)
ei, xi, ep, xp, gr, cd = sim.run(o2, h2, l2, c2, np.array([0, 0, 1, 0, 0, 0], bool), 1, rd, 1.0, 0, nan, day, mins, True, 870, 915)
check(len(ei) == 0, "intraday: signal at the session's last bar -> no entry next day")
ei, xi, ep, xp, gr, cd = sim.run(o2, h2, l2, c2, np.array([0, 1, 0, 0, 0, 0], bool), 1, np.full(6, 10.0), 3.0, 0, nan, day, mins, True, 920, 915)
check(cd[0] == 5 and xi[0] == 2, "intraday: square-off at the session close, never held overnight")
# divergence: no look-ahead – the signal never changes when future bars are appended
r = np.random.default_rng(1); px = 100 + np.cumsum(r.normal(0, 1, 400))
hh, ll, cc = px + 1, px - 1, px
os_ = ind.rsi(pd.Series(cc)).values
a, _ = div.divergence(hh, ll, cc, os_, 1, False, 3, 60, 40)
b, _ = div.divergence(hh[:300], ll[:300], cc[:300], os_[:300], 1, False, 3, 60, 40)
check(np.array_equal(a[:300], b), "divergence signals identical with / without future bars (no look-ahead)")
check(a.sum() > 0, f"divergence detector fires on a random walk ({int(a.sum())} signals)")
x = pd.Series(cc); rs = ind.rsi(x)
check(np.allclose(ind.rsi(x[:200]).values, rs[:200].values, equal_nan=True), "RSI has no look-ahead")
check(list(V.bh([0.01, 0.02, 0.5])) == [0.03, 0.03, 0.5], "BH-FDR")
d5 = pd.DataFrame(dict(time=pd.date_range("2026-01-05 09:15", periods=75, freq="5min"), open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0))
r15 = D.resample(d5.iloc[:-1], 15)
check(r15["time"].iloc[-1] == pd.Timestamp("2026-01-05 15:00") and len(r15) == 24, "incomplete last 15-min bar dropped")
print(f"{ok} engine checks passed")
