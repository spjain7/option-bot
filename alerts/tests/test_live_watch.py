"""Offline test: LIVE trigger / stop / target messages for waiting stock setups (candle_setups.live_watch).
python -m alerts.tests.test_live_watch"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import candle_setups as CS

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


class Q:
    def __init__(self, px): self.px = px
    def quotes(self, ex): return {t: {"ltp": self.px} for t in ex["NFO"]}


def rec(**k):
    r = dict(setup="STK_HANGMAN", name="AUROPHARMA", contract="AUROPHARMA23NOV26FUT", token="77", side="SELL", status="pending",
             trigger=1638.4, stop=1662.2, target_r=2.0, key="k", lot=550, mult=550, tick=0.1, pattern_time="2026-10-29 09:15")
    r.update(k); return r


NOW = pd.Timestamp("2026-10-30 11:02")
st = {"candle_setups": {"open": [rec()], "closed": [], "seen": []}}
m = []; CS.live_watch(st, m, Q(1650.0), NOW)
check(not m, "price between stop and trigger -> nothing")
m = []; CS.live_watch(st, m, Q(1635.2), NOW)
check(len(m) == 1 and "ACTIVE" in m[0] and "1,590.8" in m[0], "price below the SELL trigger -> LIVE active message with stop and 2R target")
m = []; CS.live_watch(st, m, Q(1634.0), NOW)
check(not m, "trigger message sent only once")
m = []; CS.live_watch(st, m, Q(1590.0), NOW)
check(len(m) == 1 and "target" in m[0], "target reached -> LIVE target message")
m = []; CS.live_watch(st, m, Q(1663.0), NOW)
check(len(m) == 1 and "stop-loss" in m[0], "later stop touch -> LIVE stop message (once)")
st2 = {"candle_setups": {"open": [rec()], "closed": [], "seen": []}}
m = []; CS.live_watch(st2, m, Q(1663.0), NOW)
check(len(m) == 1 and "before the trigger" in m[0], "stop reached before the trigger -> cancel warning")
st3 = {"candle_setups": {"open": [rec(status="open", entry=1638.4, target=1590.8, risk=23.8)], "closed": [], "seen": []}}
m = []; CS.live_watch(st3, m, Q(1589.0), NOW)
check(len(m) == 1 and "target 1,590.8 reached" in m[0], "open (confirmed) setup -> LIVE target")
st4 = {"candle_setups": {"open": [rec(setup="MCX_HAMMER")], "closed": [], "seen": []}}
m = []; CS.live_watch(st4, m, Q(1600.0), NOW)
check(not m, "MCX setups are already tracked live on 15-min candles -> not repeated here")
print(f"\nlive-watch: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
