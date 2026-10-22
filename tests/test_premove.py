"""Offline tests for premove.py (pre-move watch). Run: python tests/test_premove.py"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
import premove as P

ok = fail = 0
def check(c, name):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("FAIL", name)

T0 = pd.Timestamp("2026-10-22 13:00")
OPEN = pd.Timestamp("2026-10-22 09:15")
def rec(px, oi, vol, step=15, day_hi=101.0, day_lo=99.0):
    return {"hist": [[str(T0 + pd.Timedelta(minutes=i * step)), p, o, v, day_hi, day_lo] for i, (p, o, v) in enumerate(zip(px, oi, vol))]}
now = T0 + pd.Timedelta(minutes=60)
day_vol = 10000  # volume by 13:00 after 225 min -> pace ~44/min; last hour needs >= 1.3x -> > ~3500
quiet = rec([100.9, 100.95, 100.92, 100.97, 100.94], [1000, 1006, 1012, 1018, 1025], [day_vol, 11200, 12400, 13600, 14800])
c = P.coil(quiet, now, "stock", OPEN)
check(c is not None and c["side"] == "UP" and c["doi"] > 2 and c["range"] < 0.4, "coil: quiet price + OI up + volume up near day high -> UP watch")
check(P.coil(rec([100, 100.5, 101, 101.5, 102], [1000, 1006, 1012, 1018, 1025], [day_vol, 11200, 12400, 13600, 14800]), now, "stock", OPEN) is None, "coil: price already moving -> no watch")
check(P.coil(rec([100.9] * 5, [1000] * 5, [day_vol, 11200, 12400, 13600, 14800]), now, "stock", OPEN) is None, "coil: OI flat -> no watch")
check(P.coil(rec([100.9] * 5, [1000, 1006, 1012, 1018, 1025], [day_vol, 10100, 10200, 10300, 10400]), now, "stock", OPEN) is None, "coil: volume slow -> no watch")
check(P.coil(rec([100.9] * 5, [0] * 5, [day_vol] * 5), now, "stock", OPEN) is None, "coil: OI missing -> no watch (never guessed)")
check(P.coil(rec([100.9] * 5, [1000, 1006, 1012, 1018, 1025], [0] * 5), now, "stock", OPEN) is None, "coil: volume missing -> no watch")
check(P.coil(rec([100.9] * 2, [1000, 1030], [day_vol, 14000]), now, "stock", OPEN) is None, "coil: too few snapshots -> no watch")
low = rec([99.1, 99.12, 99.1, 99.15, 99.12], [1000, 1006, 1012, 1018, 1025], [day_vol, 11200, 12400, 13600, 14800])
check(P.coil(low, now, "stock", OPEN)["side"] == "DOWN", "coil: near the day low -> DOWN side")

# tracking: hit, miss, still open
item = {"token": "1", "kind": "stock", "t": str(now), "px": 100.0, "group": "watch"}
r_hit = {"hist": [[str(now + pd.Timedelta(minutes=30)), 101.5, 0, 0, 0, 0]]}
r_flat = {"hist": [[str(now + pd.Timedelta(minutes=30)), 100.2, 0, 0, 0, 0]]}
check(P.moved(r_hit, item, now + pd.Timedelta(minutes=30)) is True, "track: >= big-move size within 2 h = hit")
check(P.moved(r_flat, item, now + pd.Timedelta(minutes=30)) is None, "track: no move yet, window open = undecided")
check(P.moved(r_flat, item, now + pd.Timedelta(minutes=125)) is False, "track: no move by the end = miss")
check(P.moved(None, item, now + pd.Timedelta(minutes=125)) is None, "track: no data = not counted")
st = {"premove": {"open": [item, {**item, "token": "2", "group": "control"}], "stats": {"watch": [0, 0], "control": [0, 0]}, "last": {}}}
P.track(st, {"1": r_hit, "2": r_flat}, now + pd.Timedelta(minutes=125))
check(st["premove"]["stats"] == {"watch": [1, 1], "control": [1, 0]} and st["premove"]["open"] == [], "track: watch vs control counted separately")
check("100% followed" in P.summary_line(st) and "0% for random" in P.summary_line(st), "report line shows watch vs control")

# run(): sends one message, adds a matched control, respects cooldown
sent = []
P.notify.send = lambda t, *a, **k: sent.append(t)
class B: pass
bot = B(); bot.st = B(); bot.st.s = {"snap": {"1": quiet, "2": r_flat | {"hist": quiet["hist"][:4] + [[str(now), 50, 0, 0, 0, 0]]}}, "positions": []}
live = [{"name": "SBIN", "exch": "NFO", "token": "1", "kind": "stock"}, {"name": "ITC", "exch": "NFO", "token": "2", "kind": "stock"}]
P.run(bot, live, now, lambda ex: OPEN)
check(len(sent) == 1 and "PRE-MOVE WATCH" in sent[0] and "SBIN" in sent[0] and "not a call" in sent[0], "run: alert sent with disclaimer")
groups = sorted(i["group"] for i in bot.st.s["premove"]["open"])
check(groups == ["control", "watch"], "run: one random control tracked per alert")
P.run(bot, live, now + pd.Timedelta(minutes=15), lambda ex: OPEN)
check(len(sent) == 1, "run: same script not re-alerted within the cooldown")
print(f"premove: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
