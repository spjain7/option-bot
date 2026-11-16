"""Offline tests: after-close futures calls are confirmed ACTIVE / SKIPPED at the next open; gap fills at the open (16-Nov-2026).
python -m alerts.tests.test_after_close_open"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import four_hour as FH

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


class Api:
    def __init__(self, q):
        self.q = q

    def quotes(self, req):
        return {t: self.q[t] for toks in req.values() for t in toks if t in self.q}


def is_open(ex, now):
    return 9 * 60 + 15 <= now.hour * 60 + now.minute < 15 * 60 + 30 and now.weekday() < 5


def rec(**k):
    r = dict(name="TMPV", ex="NFO", token="1", contract="TMPV23NOV26FUT", expiry="2026-11-23", side="SELL", entry=288.5, stop=299.05,
             target=267.5, risk=10.55, tick=0.05, mult=1600, opened="2026-11-13 17:32:02", days=["2026-11-13"], key="4H|TMPV|x",
             max_days=20, tfl="4-hour", await_open=True, atr=5.0)
    r.update(k)
    return r


def run(r, q, now="2026-11-17 09:17", state=None):
    state = state or dict(fourh=dict(open=[r], closed=[], last={}, await_v=1),
                          ledger=[dict(key=r["key"], status="OPEN", entry=r["entry"])])
    msgs = []
    FH.track(state, msgs, Api({"1": q}), pd.Timestamp(now), is_open)
    return state, msgs


# verdicts
check(FH.open_verdict(rec(), 287.0) == ("active", None), "SELL: open slightly below entry (0.3 ATR) -> ACTIVE")
check(FH.open_verdict(rec(), 290.0)[0] == "active", "SELL: open against the call but above the SL -> ACTIVE")
check(FH.open_verdict(rec(), 284.0)[0] == "skip", "SELL: open 0.9 ATR past the entry -> SKIP (no chasing)")
check(FH.open_verdict(rec(), 300.0)[0] == "skip", "SELL: open beyond the SL -> SKIP")
check(FH.open_verdict(rec(), 267.0)[0] == "skip", "SELL: open beyond the target -> SKIP")
check(FH.open_verdict(rec(side="BUY", entry=100, stop=95, target=110, atr=2.0), 101.5)[0] == "skip", "BUY: open 0.75 ATR above -> SKIP")

# same evening: nothing happens
st_, m = run(rec(), dict(ltp=287.0, open=287.0), now="2026-11-13 15:20")
check(st_["fourh"]["open"][0]["await_open"] and not m, "same session: still waiting, no message")

# next open inside the zone -> ACTIVE message, entry = open, risk from the open
st_, m = run(rec(), dict(ltp=287.2, open=287.0))
r = st_["fourh"]["open"][0]
check(len(m) == 1 and m[0].startswith("✅ ACTIVE – TMPV FUT SELL") and "opened 287" in m[0], "ACTIVE message at the next open")
check(r["entry"] == 287.0 and abs(r["risk"] - 12.05) < 1e-6 and r["call_entry"] == 288.5 and not r["await_open"], "entry = open, risk re-measured")
check(st_["ledger"][0]["entry"] == 287.0, "ledger entry moved to the open")
check(r["days"] == ["2026-11-17"], "time exit counted from activation")

# gap past the entry -> SKIPPED, no trade, ledger closed flat
st_, m = run(rec(), dict(ltp=266.0, open=266.5))
check(len(m) == 1 and m[0].startswith("🚫 SKIPPED – TMPV FUT SELL") and "NO TRADE" in m[0], "SKIPPED message when it opens past the target")
check(not st_["fourh"]["open"] and st_["fourh"]["closed"][0]["result_R"] is None, "skipped call closed with no result")
check(st_["ledger"][0]["status"] == "CLOSED" and st_["ledger"][0]["exit"] == 288.5, "ledger row closed flat (no win booked)")

# no quote yet -> keep waiting
st_, m = run(rec(), dict())
check(st_["fourh"]["open"][0]["await_open"] and not m, "no quote: decision deferred, nothing sent")

# shadow call: decided silently
st_, m = run(rec(shadow=True), dict(ltp=287.2, open=287.0))
check(not m and not st_["fourh"]["open"][0]["await_open"], "shadow call activated silently")

# gap fills on an already-active call
r0 = rec(await_open=False, days=["2026-11-13", "2026-11-16"])
st_, m = run(r0, dict(ltp=301.0, open=302.0))
c = st_["fourh"]["closed"][-1]
check(c["exit"] == 302.0 and "gap" in c["exit_reason"] and c["result_R"] < -1, "SELL opens above the SL -> exit at the open (worse than -1R)")
st_, m = run(rec(await_open=False, days=["2026-11-13", "2026-11-16"]), dict(ltp=265.0, open=264.0))
c = st_["fourh"]["closed"][-1]
check(c["exit"] == 264.0 and c["result_R"] > 2.0, "SELL opens below the target -> exit at the open")
st_, m = run(rec(await_open=False, days=["2026-11-13", "2026-11-16"]), dict(ltp=299.5, open=295.0))
c = st_["fourh"]["closed"][-1]
check(c["exit"] == 299.05 and "gap" not in c["exit_reason"], "intraday stop (open inside) -> exit at the SL")
st_, m = run(rec(await_open=False, stop_day="2026-11-17", days=["2026-11-13", "2026-11-16"]), dict(ltp=301.0, open=302.0))
check(st_["fourh"]["closed"][-1]["exit"] == 299.05, "stop moved today (trailing) -> no gap fill at the open")

# activated this morning, then the level is hit later the same day -> filled at the level
st_, m = run(rec(), dict(ltp=299.2, open=297.0))
c = st_["fourh"]["closed"][-1]
check(len(m) == 2 and m[0].startswith("✅ ACTIVE") and c["exit"] == 299.05, "activated at the open, stopped later at the SL level")

# one-time correction (16-Nov): TMPV closed at the open as a 'target'
tm = rec(await_open=False, closed="2026-11-16 09:17:01", exit=267.5, exit_reason="🎯 target", result_R=1.991, atr=None)
gr = rec(name="GRASIM", token="2", key="4H|GRASIM|x", entry=3033.3, stop=3129.1, target=2841.9, risk=95.8, await_open=False, atr=None,
         opened="2026-11-13 17:32:02")
old = rec(name="ICICIBANK", token="3", key="RB|x|ICICIBANK|y", side="BUY", entry=1568.2, stop=1502.0, target=1766.5, risk=66.2,
          opened="2026-11-06 15:32:01", await_open=False, atr=None)
state = dict(fourh=dict(open=[gr, old], closed=[tm], last={}),
             ledger=[dict(key="4H|TMPV|x", status="CLOSED", entry=288.5, exit=267.5), dict(key="4H|GRASIM|x", status="OPEN", entry=3033.3)])
msgs = []
api = Api({"1": dict(ltp=265.0, open=266.0), "2": dict(ltp=3020.0, open=3025.0), "3": dict(ltp=1600.0, open=1590.0)})
FH.track(state, msgs, api, pd.Timestamp("2026-11-16 10:02"), is_open)
check(any(x.startswith("ℹ️ CORRECTION – TMPV") and "NO TRADE" in x for x in msgs), "TMPV correction message (no trade, not +1.99R)")
check(state["fourh"]["closed"][0]["result_R"] is None and state["ledger"][0]["exit"] == 288.5, "TMPV result and ledger corrected to flat")
g = [r for r in state["fourh"]["open"] if r["name"] == "GRASIM"][0]
check(any(x.startswith("✅ ACTIVE – GRASIM") for x in msgs) and g["entry"] == 3025.0, "GRASIM (13-Nov after-close) confirmed ACTIVE at today's open")
i = [r for r in state["fourh"]["open"] if r["name"] == "ICICIBANK"][0]
check(not any("ICICIBANK" in x for x in msgs) and i["entry"] == 1568.2, "older calls untouched")
msgs = []
FH.track(state, msgs, api, pd.Timestamp("2026-11-16 10:17"), is_open)
check(not any("CORRECTION" in x or "ACTIVE" in x for x in msgs), "one-time fix does not repeat")

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
