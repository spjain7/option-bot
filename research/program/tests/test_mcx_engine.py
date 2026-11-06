"""Regression tests for the MCXE v2 simulator and detectors (owner audit list 6-Nov-2026).
python research/program/tests/test_mcx_engine.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.program import mcx_engine as E  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


def bars(rows):
    a = np.array(rows, dtype=np.float64)                  # columns o, h, l, c
    return a[:, 0].copy(), a[:, 1].copy(), a[:, 2].copy(), a[:, 3].copy()


def run(rows, act, side, trig, inv, atr, eod, last, entry=0, stop=0, exitc=0.0, cost=0.0):
    o, h, l, c = bars(rows)
    A = lambda x, t: np.array(x, dtype=t)  # noqa: E731
    return E.sim(o, h, l, c, A(act, np.int64), A(side, np.int64), A(trig, np.float64), A(inv, np.float64), A(atr, np.float64),
                 A(eod, np.int64), A(last, np.int64), entry, stop, exitc, np.full(len(rows), cost))


flat = [[100, 100.5, 99.5, 100]] * 3
# 1 next-bar timing: market entry fills at the OPEN of the activation bar (first bar after the signal candle closed)
r = run(flat + [[101, 102, 100.8, 101.5], [101.5, 103, 101, 102]], [3], [1], [100.5], [99.0], [1.0], [4], [4])
check(r[0, 2] == 3 and abs(r[0, 0] * (101 - 98.9) - (102 - 101)) < 1e-9, "market entry at the activation bar's open; exit at the session-close bar's close")
# 2 stop and target touched in the same bar -> stop first
r = run(flat + [[100, 100.2, 99.8, 100], [100, 104, 97, 100]], [3], [1], [100.2], [99.0], [1.0], [4], [4], exitc=2.0)
check(r[0, 0] == -1.0, "stop and target in the same 5-min bar -> stop assumed first (-1R)")
# 3 gap through the stop -> filled at the open, worse than the stop
r = run(flat + [[100, 100.2, 99.8, 100], [97, 97.5, 96.5, 97]], [3], [1], [100.2], [99.0], [1.0], [4], [4])
check(r[0, 0] < -1.0 and abs(r[0, 0] - (97 - 100) / (100 - 98.9)) < 1e-9, "gap through the stop -> exit at the open (loss > 1R)")
# 4 target never filled on the entry bar
r = run(flat + [[100, 103, 99.9, 102], [102, 102.1, 101.9, 102]], [3], [1], [100.2], [99.0], [1.0], [4], [4], exitc=2.0)
check(r[0, 0] != 2.0, "no target fill inside the entry bar (intrabar order unknown)")
# 5 costs subtracted in R
r = run(flat + [[100, 100.2, 99.8, 100], [100, 100.1, 99.9, 100]], [3], [1], [100.2], [99.0], [1.0], [4], [4], cost=0.55)
check(abs(r[0, 1] - 0.5) < 1e-9, "round-trip cost converted to R (0.55 points / 1.1 risk = 0.5R)")
# 6 session close: position closed at the eod bar even if later bars move
r = run(flat + [[100, 100.2, 99.8, 100], [100, 100.4, 99.9, 100.3], [110, 111, 109, 110]], [3], [1], [100.2], [99.0], [1.0], [4], [4])
check(r[0, 3] == 4 and abs(r[0, 0] - 0.3 / 1.1) < 1e-9, "square-off at the session-close bar; later bars ignored")
# 7 overlapping positions: second setup activating before the first trade's exit is skipped
r = run(flat + [[100, 100.2, 99.8, 100]] * 4, [3, 4, 6], [1, 1, 1], [100.2] * 3, [99.0] * 3, [1.0] * 3, [5, 5, 6], [5, 5, 6])
check(not np.isnan(r[0, 0]) and np.isnan(r[1, 0]), "one position at a time: overlapping setup skipped")
# 8 stop-entry: invalidation and trigger in the same bar -> no trade (conservative)
r = run(flat + [[100, 101.5, 98.5, 100], [100, 102, 99.9, 101]], [3], [1], [101.0], [99.0], [1.0], [4], [4], entry=1)
check(np.isnan(r[0, 0]), "stop-entry bar touches trigger AND invalidation -> no trade")
# 9 stop-entry cancelled when the invalidation trades first
r = run(flat + [[100, 100.5, 98.5, 99], [99, 102, 99, 101]], [3], [1], [101.0], [99.0], [1.0], [4], [4], entry=1)
check(np.isnan(r[0, 0]), "invalidation before the trigger -> order cancelled")
# 10 stop-entry fills at max(trigger, open) and never chases > 0.5 ATR
r = run(flat + [[102, 102.2, 101.8, 102], [102, 102.1, 101.9, 102]], [3], [1], [101.0], [99.0], [1.0], [4], [4], entry=1)
check(np.isnan(r[0, 0]), "gap 1 ATR beyond the trigger -> no chase")
r = run(flat + [[100.8, 101.4, 100.7, 101.3], [101.3, 101.4, 101.2, 101.3]], [3], [1], [101.0], [99.0], [1.0], [4], [4], entry=1)
check(r[0, 2] == 3 and abs(r[0, 0] - (101.3 - 101.0) / (101.0 - 98.9)) < 1e-9, "stop-entry fills at the trigger price")


# 11 detectors use no future data: setups found on a prefix equal those found on the full data up to that point
def synth(n=900, seed=3):
    rng = np.random.default_rng(seed)
    t = pd.date_range("2025-01-06 09:00", periods=n, freq="15min")
    t = t[(t.hour >= 9) & (t.hour < 23)][:n]
    c = 100 + np.cumsum(rng.normal(0, 0.4, len(t)))
    o = np.r_[c[0], c[:-1]]; h = np.maximum(o, c) + rng.random(len(t)) * 0.3; l = np.minimum(o, c) - rng.random(len(t)) * 0.3
    f = pd.DataFrame(dict(time=t, open=o, high=h, low=l, close=c, volume=1000 + rng.random(len(t)) * 500))
    f["day"] = f.time.dt.normalize(); f["m"] = f.time.dt.hour * 60 + f.time.dt.minute
    tr = np.maximum(f.high - f.low, np.maximum((f.high - f.close.shift()).abs(), (f.low - f.close.shift()).abs()))
    f["atr"] = tr.rolling(14).mean()
    dd = f.groupby("day").agg(h=("high", "max"), l=("low", "min"))
    dd["ph"], dd["pl"] = dd.h.shift(1), dd.l.shift(1)
    return f, dd


f, dd = synth()
full = E.detect(f, "15m", dd, set())
cut = 600
pre = E.detect(f.iloc[:cut].reset_index(drop=True), "15m", dd, set())
a_ = sorted((x[0], x[1], x[2], x[8]) for x in full if x[8] < cut - 1)
b_ = sorted((x[0], x[1], x[2], x[8]) for x in pre if x[8] < cut - 1)
check(len(a_) > 50 and a_ == b_, f"no look-ahead: {len(a_)} setups on a prefix identical to the full-data run")
check(len({x[0] for x in full} & {"SWEEP", "SR", "TL", "CH", "MS", "CDL", "CMP"}) >= 6, "all detector families produce setups")
check(E.fingerprint(pd.DataFrame(dict(time=pd.date_range("2025", periods=3), close=[1.0, 2, 3], volume=[1.0, 1, 1]))) ==
      E.fingerprint(pd.DataFrame(dict(time=pd.date_range("2025", periods=3), close=[1.0, 2, 3], volume=[1.0, 1, 1]))), "dataset fingerprint is deterministic")
print(f"\n{ok} checks passed")
