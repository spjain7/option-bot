"""Offline checks for research/rsidiv: simulator rules, no look-ahead in signals, RSI events, cost schedule.
python -m research.rsidiv.tests.test_engine"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E, stockfut as SF  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


def run(o, h, l, c, sig, side=1, risk=1.0, R=2.0, grp=None, hold=10, cost=0.0, exp=None):
    n = len(c); a = lambda x: np.asarray(x, float)
    return E.sim(a(o), a(h), a(l), a(c), np.asarray(sig, bool), side, np.full(n, risk), R, np.zeros(n, np.int64) if grp is None else np.asarray(grp, np.int64),
                 hold, np.full(n, cost), np.zeros(n, np.int64) if exp is None else np.asarray(exp, np.int64))


# entry next open, target 2R
ei, xi, nr, gr, cr = run([100, 100, 101, 102], [100, 101, 103, 103], [100, 99.5, 100.5, 101], [100, 100.5, 102.5, 102], [1, 0, 0, 0])
check(ei[0] == 1 and xi[0] == 2 and abs(gr[0] - 2.0) < 1e-9, "entry at the next bar's open, target 2R hit")
# stop and target in the same bar -> stop first
ei, xi, nr, gr, cr = run([100, 100, 100], [100, 103, 100], [100, 98, 100], [100, 100, 100], [1, 0, 0])
check(abs(gr[0] + 1.0) < 1e-9, "stop and target in one bar: stop counts first")
# gap through the stop fills at the open (worse than the stop)
ei, xi, nr, gr, cr = run([100, 100, 97, 97], [100, 100.2, 97.5, 98], [100, 99.8, 96, 96], [100, 100, 97, 97], [1, 0, 0, 0])
check(abs(gr[0] + 3.0) < 1e-9, "gap below the stop fills at the open (-3R, not -1R)")
# SELL mirror
ei, xi, nr, gr, cr = run([100, 100, 99, 98], [100, 100.5, 99.5, 98.5], [100, 99.5, 97.9, 97], [100, 100, 98, 98], [1, 0, 0, 0], side=-1)
check(abs(gr[0] - 2.0) < 1e-9, "SELL: target 2R below the entry")
# costs, roll and instrument boundary
ei, xi, nr, gr, cr = run([100] * 6, [100.5] * 6, [99.5] * 6, [100] * 6, [1, 0, 0, 0, 0, 0], hold=3, cost=0.001, exp=[0, 0, 1, 1, 1, 1])
check(abs(cr[0] - 0.2) < 1e-9, "a trade held over an expiry pays the round trip twice (roll)")
ei, xi, nr, gr, cr = run([100] * 6, [100.5] * 6, [99.5] * 6, [100] * 6, [1, 0, 0, 0, 0, 0], hold=10, grp=[0, 0, 0, 1, 1, 1])
check(xi[0] == 2, "a trade never runs into the next instrument (closed on its last bar)")
ei, xi, nr, gr, cr = run([100] * 8, [100.5] * 8, [99.5] * 8, [100] * 8, [1, 1, 1, 0, 0, 1, 0, 0], hold=3)
check(list(ei) == [1, 6], "one open trade at a time per instrument")

# no look-ahead: signals up to bar m-K-1 are identical whether or not later bars exist
rng = np.random.default_rng(3)
n = 700
c = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
b = pd.DataFrame(dict(time=pd.date_range("2020-01-01", periods=n), open=c * (1 + rng.normal(0, 0.002, n)), high=c * 1.008, low=c * 0.992, close=c,
                      volume=rng.integers(1000, 5000, n).astype(float)))
S_full, _ = E.study(b, 3)
m = 500
S_cut, _ = E.study(b.iloc[:m].reset_index(drop=True), 3)
same = all((S_full[k][:m - 4] == S_cut[k][:m - 4]).all() for k in S_cut if k in S_full)
check(same, "no look-ahead: every signal before the cut is unchanged when later bars are removed")
check(sum(int(v.sum()) for k, v in S_full.items() if k[0] == "DIV") > 0, "divergence signals do occur on random data")
# divergence appears exactly K bars after the second pivot low
l = pd.Series(np.r_[np.linspace(110, 100, 10), np.linspace(100, 108, 8), np.linspace(108, 98, 8), np.linspace(98, 115, 20)])
h = l + 1
I = {"rsi": pd.Series(np.r_[np.linspace(50, 20, 10), np.linspace(20, 60, 8), np.linspace(60, 30, 8), np.linspace(30, 70, 20)])}
D = E.divergences(h, l, I, 3)
piv2 = int(np.argmin(l.values[15:])) + 15
check(np.where(D["rsi", "regular", 1])[0].tolist() == [piv2 + 3], f"regular bullish divergence flagged at pivot + K (bar {piv2 + 3})")
# RSI cross_in fires once on the crossing bar
x = pd.Series(np.r_[np.full(30, 100.0), 100 + np.arange(1, 21) * 2.0, np.full(10, 140.0)])
bb = pd.DataFrame(dict(time=pd.date_range("2021-01-01", periods=len(x)), open=x, high=x + 0.5, low=x - 0.5, close=x, volume=1000.0))
S, _ = E.study(bb, 3)
r = E.rsi_of(x)
first = int(np.argmax((r >= 75).values))
check(np.where(S["RSI", "cross_in:continuation", "zone75", 1])[0].tolist() == [first], "RSI 75 cross_in on the first bar at / above 75 only")
check((S["RSI", "cross_in:continuation", "zone75", 1] == S["RSI", "cross_in:reversal", "zone75", -1]).all(), "same event traded both ways (BUY continuation, SELL reversal)")
# cost schedule
cst = SF.fut_cost(np.array(["2024-01-02", "2025-01-02", "2026-05-04"], dtype="datetime64[D]"))
check(cst[1] - cst[0] > 0.00007 and cst[2] - cst[1] > 0.00029, "futures STT schedule 0.0125 % -> 0.02 % (Oct-2024) -> 0.05 % (Apr-2026)")
check(0.0008 < cst[2] < 0.0015, f"2026 stock-futures round trip incl. slippage {100 * cst[2]:.3f} %")
print(f"{ok} rsidiv engine checks passed")
