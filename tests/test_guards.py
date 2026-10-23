"""Offline tests for guards/bounce.py and guards/covering.py. Run: python tests/test_guards.py"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from guards import bounce, covering

ok = fail = 0
def check(c, name):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("FAIL", name)

def bars(closes, vol=100):
    t0 = pd.Timestamp("2026-10-23 09:00")
    rows = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        rows.append([t0 + pd.Timedelta(minutes=15 * i), o, max(o, c) + 50, min(o, c) - 50, c, vol])
    return pd.DataFrame(rows, columns="time open high low close volume".split())

# today's Silver: fall 196,900 -> 192,800, then bounce to 195,400 (10:58 sell)
silver = bars([196900, 196100, 195300, 194300, 193600, 193100, 192900, 193300, 193800, 194500, 195000, 195400])
check(bounce.check(silver, 195436, "BEARISH") is not None, "bounce: Silver CE sell at 10:58 would be blocked")
falling = bars([196900, 196500, 196000, 195600, 195100, 194700, 194300, 193900, 193500, 193100, 192800, 192600])
check(bounce.check(falling, 192600, "BEARISH") is None, "bounce: CE sell still allowed while price keeps falling below VWAP")
check(bounce.check(bars([100 + i for i in range(12)]), 111, "BULLISH") is None, "bounce: PE sell allowed in a steady rise")
drop = bars([100, 101, 102, 103, 104, 105, 106, 107, 106, 104, 102, 100])
check(bounce.check(drop, 100, "BULLISH") is not None, "bounce: PE sell into a fresh drop blocked (mirror)")
check(bounce.check(silver, 195436, "NEUTRAL") is None and bounce.check(None, 1, "BEARISH") is None, "bounce: neutral / no data -> not blocked")
check(bounce.check(bars([196900, 196100, 195300, 194300, 193600, 193100, 192900, 193300, 193800, 194500, 195000, 195400], vol=0), 195436, "BEARISH") is not None,
      "bounce: index spot without volume still checked by the ATR rule")

# covering
now = pd.Timestamp("2026-10-23 10:51")
rec = {"hist": [["2026-10-23 09:54:00", 193061.0, 548190.0, 0, 196924.0, 193058.0],
                ["2026-10-23 10:21:00", 193685.0, 534720.0, 0, 196924.0, 192800.0],
                ["2026-10-23 10:51:00", 195436.0, 529110.0, 0, 196924.0, 192800.0]], "oi_day": -7.66}
d = covering.detect(rec, "mcx", now)
check(d and d["type"] == "SHORT COVERING" and round(d["pts"]) == 2636, "covering: today's Silver bounce flagged as short covering")
rec2 = {"hist": [[x[0], x[1], x[2] * 1.03 if i == 2 else x[2], 0, x[4], x[5]] for i, x in enumerate(rec["hist"])]}
check(covering.detect(rec2, "mcx", now) is None, "covering: OI rising (fresh buying) is not covering")
rec3 = {"hist": [["2026-10-23 09:54:00", 196000.0, 548190.0, 0, 196924.0, 193058.0],
                 ["2026-10-23 10:51:00", 194000.0, 540000.0, 0, 196924.0, 192800.0]]}
check(covering.detect(rec3, "mcx", now) and covering.detect(rec3, "mcx", now)["type"] == "LONG UNWINDING", "covering: fall + OI drop = long unwinding")
sent = []
covering.notify.send = lambda t, *a, **k: sent.append(t)
class B: pass
bot = B(); bot.st = B()
bot.st.s = {"snap": {"1": rec}, "positions": [{"id": 217, "name": "SILVER", "legs": [{"typ": "CE", "K": 201000}], "sl_val": 1836}]}
covering.run(bot, [{"name": "SILVER", "token": "1", "kind": "mcx", "exch": "MCX"}], now)
check(len(sent) == 1 and "SHORT COVERING" in sent[0] and "#217" in sent[0] and "not a call" in sent[0], "covering: alert with open-position warning")
covering.run(bot, [{"name": "SILVER", "token": "1", "kind": "mcx", "exch": "MCX"}], now + pd.Timedelta(minutes=15))
check(len(sent) == 1, "covering: cooldown – not repeated within 2 hours")
print(f"guards: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
