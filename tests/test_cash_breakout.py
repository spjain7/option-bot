"""Cash positional scored breakout (EXPERIMENTAL, live 10-Nov): scoring, one-position-per-stock parity rule, the nightly
step (call -> entry at the next open -> T1 -> exit on a close below EMA50 / stop), messages labelled EXPERIMENTAL.
python tests/test_cash_breakout.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cashstock import breakout as B  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


p, sc = B.score_parts(rs=0.9, adx=31, tight=0.8, clv=0.6, breadth=0.6)
check(sc == 100 and p == dict(rs=35, trend=25, base=20, entry=10, breadth=10), "full score 100")
check(B.score_parts(rs=0.72, adx=20, tight=0.95, clv=0.95, breadth=0.45)[1] == 22 + 6 + 10 + 0 + 5, "partial score 43")
check(B.score_parts(rs=0.4, adx=10, tight=1.2, clv=0.99, breadth=0.2)[1] == 0, "weak candidate 0")

# synthetic panel: 320 flat sessions, a breakout day, then the following sessions are appended step by step
days = pd.bdate_range("2025-06-02", periods=330)
r = np.random.default_rng(5)


def panel(n, tail):
    c = np.r_[100 + r.normal(0, 0.2, 320), tail][:n]
    d = pd.DataFrame(dict(time=days[:n], open=c - 0.1, high=c + 0.5, low=c - 0.5, close=c, volume=5e6, symbol="AAA"))
    others = {f"K{i}": pd.DataFrame(dict(time=days[:n], open=50.0 + i, high=50.6 + i, low=49.4 + i, close=50.0 + i + 0.001 * np.arange(n),
                                         volume=1e7, symbol=f"S{i}")) for i in range(6)}
    return B.features(B.wide(dict(AAA=d, **others)))


tail = [104.0, 104.5, 109.5, 112.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0]
F = panel(321, tail)
cs = [c for c in B.candidates(F) if c["symbol"] == "AAA"]
check(len(cs) == 1 and cs[0]["close"] == 104.0 and cs[0]["score"] >= 35, f"breakout day found, score {cs[0]['score']}")
B.MIN_SCORE = min(B.MIN_SCORE, cs[0]["score"])                      # the synthetic stock need not reach 70
st, m = {}, []
B.step(st, F, m)
check(len(m) == 2 and "EXPERIMENTAL" in m[0] and "BACKTEST ONLY" in m[1] and "1 trade in 3" in m[1] and len(st["pending"]) == 1,
      "call + WHY sent, labelled EXPERIMENTAL with the honest record; waiting for the open")
m2 = []
B.step(st, F, m2)
check(not m2 and len(st["pending"]) == 1, "same evening run twice -> nothing new")
F2 = panel(322, tail); m3 = []
B.step(st, F2, m3)
rec = st["open"][0]
check(len(st["pending"]) == 0 and "ENTRY" in m3[0] and abs(rec["entry"] - 104.4) < 1e-6 and abs(rec["entry"] - rec["stop"] - 3 * cs[0]["atr"]) < 0.02,
      "next session: entry at the open, stop 3 ATR below")
F4 = panel(324, tail); m4 = []
B.step(st, F4, m4)
check(any("T1" in x for x in m4) and st["open"][0]["t1_hit"] and st["open"][0]["hi"] == 112.5, "T1 reached -> one message; high since entry tracked")
F5 = panel(325, tail); m5 = []
B.step(st, F5, m5)
closed = st["closed"][-1] if st["closed"] else None
check(closed is not None and "stop-loss" in closed["exit_reason"] and any("EXIT" in x and "per 100 shares" in x for x in m5),
      "gap down through the stop -> EXIT with the P&L for 100 shares")
check(closed["lo"] <= 99.0 and closed["pnl_100"] == round((closed["exit"] - closed["entry"]) * 100), "low after entry and ₹ result recorded")
# parity rule: a second breakout while the first trade is running is ignored
t2 = [104.0, 104.5, 105.0, 105.5, 106.0, 106.2, 106.4, 110.0, 110.5, 111.0]
Fb = panel(328, t2)
check(bool(Fb["signal"]["AAA"].iloc[320]) and bool(B.busy_mask(Fb)["AAA"].iloc[327]) and not bool(B.busy_mask(Fb)["AAA"].iloc[320]),
      "while a breakout trade of the stock is running, later signals are busy (research holds one position per stock)")
print(f"{ok} cash-breakout checks passed")
