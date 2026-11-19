"""19-Nov-2026 one-time reversal catch-up (alerts/stocks.rev_catchup): after today's daily stock scan has run, the rulebook
daily stock rules run once more on today's candle (new REV rules only can fire - already-seen keys are skipped), the daily
EMA200 cache is filled, and stk.rev_v becomes 1. Before the daily scan has run it just sets rev_v.
python -m alerts.tests.test_rev_catchup"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import stocks as SK, rulebook as RB  # noqa: E402

ok = 0


def check(n, c):
    global ok
    assert c, n
    ok += 1; print("✅", n)


NOW = pd.Timestamp("2026-11-19 16:50")
days = pd.bdate_range(end="2026-11-19", periods=300)
rows = []
for k, dd in enumerate(days):
    px = 100 + 0.2 * k
    for hh in range(7):
        t = dd + pd.Timedelta(hours=9, minutes=15) + pd.Timedelta(hours=hh)
        rows.append(dict(time=t, open=px, high=px + 0.5, low=px - 0.5, close=px, volume=1000.0))
H1 = pd.DataFrame(rows)


class Api:
    calls = 0

    def candles(self, ex, tok, iv, a, b):
        Api.calls += 1
        return H1.copy()


class Eng:
    @staticmethod
    def closed(h, ex, m, now):
        return h


uni = {"AAA": dict(token="1", symbol="AAA25NOVFUT", lot=100, tick=0.05, expiry="2026-11-25"),
       "BBB": dict(token="2", symbol="BBB25NOVFUT", lot=100, tick=0.05, expiry="2026-11-25")}
seen_runs = []
_orig = RB.run
RB.run = lambda *a, **k: seen_runs.append((a[3], tuple(a[6]), k.get("after_close"))) or {}
state = dict(stk=dict(active=[], last_block="2026-11-19 15:30:00"))
r = SK.rev_catchup(Api(), NOW, state, [], uni, Eng)
check("catch-up runs the rulebook daily stock rules once per stock, after-close mode",
      [x[0] for x in seen_runs] == ["AAA", "BBB"] and all(x[1] == ("1d",) and x[2] for x in seen_runs))
check("done -> stk.rev_v = 1, progress cleared", state["stk"]["rev_v"] == 1 and "rev_prog" not in state["stk"] and r.startswith("done"))

seen_runs.clear()
SK.REV_CATCHUP_BUDGET_SEC, _b = -1, SK.REV_CATCHUP_BUDGET_SEC
state2 = dict(stk=dict(active=[], last_block="2026-11-19 15:30:00"))
r2 = SK.rev_catchup(Api(), NOW, state2, [], uni, Eng)
check("time budget used up -> resumes next scan, rev_v not set", "resumes" in r2 and state2["stk"].get("rev_v") is None)
SK.REV_CATCHUP_BUDGET_SEC = _b
RB.run = _orig

# real rulebook: the EMA200 cache gets filled, already-seen RSI80 key is not re-evaluated
state3 = dict(stk=dict(active=[], last_block="2026-11-19 15:30:00"), rulebook_seen=[], ledger=[])
d = SK.BO.daily_candles(H1, None)
state3["rulebook_seen"].append(f"RB_STK_1d_RSI80_BUY|AAA|{d['time'].iloc[-1]}")
SK.rev_catchup(Api(), NOW, state3, [], {"AAA": uni["AAA"]}, Eng)
check("daily EMA200 cache filled for tomorrow's 4-hour scan", state3.get("a200", {}).get("AAA", {}).get("day") == "2026-11-19")
check("RSI80 (already evaluated today) not evaluated again; REV keys added",
      state3["rulebook_seen"].count(f"RB_STK_1d_RSI80_BUY|AAA|{d['time'].iloc[-1]}") == 1
      and any(k.startswith("RB_STK_1d_REV_") for k in state3["rulebook_seen"]))
print(f"{ok} checks passed")
