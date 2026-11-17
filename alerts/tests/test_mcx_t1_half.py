"""Offline tests (17-Nov-2026): new per-commodity MCX rules with T1 1R (book half, stop to cost) + T2 1.5R; the 3 MCX 1-hour
EXPERIMENTAL rules are off; aluminium gets weekly / monthly calls only. python -m alerts.tests.test_mcx_t1_half"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import rulebook as RB, four_hour as FH, engine as EN

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


R = RB.RULES
check(all(R[k]["status"] == "OFF" for k in ("RB_MCX_1h_BO20X_BUY_EXP", "RB_MCX_1h_OIBO_BUY_EXP", "RB_MCX_1h_OIBO_SELL_EXP")),
      "the 3 MCX 1-hour EXPERIMENTAL rules are off")
check(R["RB_IDX_1h_OIBO_BUY_EXP"]["status"] == "LIVE" and R["RB_IDX_1h_OIBO_SELL_EXP"]["status"] == "LIVE", "index 1-hour OI rules unchanged")
new = {k: v for k, v in R.items() if v.get("half_t1")}
check(sorted(v["names"][0] + " " + v["tf"] for v in new.values()) == ["COPPER 1d", "GOLD 3h", "GOLD 4h", "SILVER 1d", "ZINC 1d"],
      "new rules: gold 3h + 4h, silver / copper / zinc daily")
check(all(v["k"] == 2.0 and v["r"] == 1.5 and v["fam"] == "BO" and v["par"] == "N10 vol0" and v["side"] == "BUY" and v["status"] == "LIVE"
          for v in new.values()), "SL 2 ATR, T2 1.5R, 10-candle breakout BUY, live")
old_live = [k for k, v in R.items() if v["mkt"] == "MCX" and v["status"] == "LIVE" and not v.get("half_t1")]
check(len(old_live) == 8, f"the other 8 MCX rules still live ({len(old_live)})")
check(EN._positional_only() == {"ALUMINIUM"}, "aluminium is weekly / monthly only")
for k in ("PETRONET", "GLENMARK", "TITAN"):
    check(not any(k in str(v.get("names") or "") for v in R.values()), f"{k} untouched by the rulebook change")


def frame(n=260, start="2026-08-03 09:00", step="3h", breakout=True):
    t = pd.date_range(start, periods=n, freq=step)
    rng = np.random.default_rng(3)
    c = 150000 + np.cumsum(rng.normal(0, 150, n))
    if breakout:
        c[-1] = c[-11:-1].max() + 2500
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + 200; l = np.minimum(o, c) - 200
    return pd.DataFrame(dict(time=t, open=o, high=h, low=l, close=c, volume=1000.0))


def contract(name):
    return dict(token="77", symbol=f"{name}05DEC26FUT", expiry="2026-12-05", tick=1.0, lot=1)


now = pd.Timestamp("2026-11-17 15:05")
f3 = frame()
f3["time"] = pd.date_range(end=now - pd.Timedelta(hours=3), periods=len(f3), freq="3h")
last = float(f3["close"].iloc[-1])
st, msgs = dict(day={}, ledger=[]), []
out = RB.run(st, msgs, None, "GOLD", "MCX", contract("GOLD"), {"3h": f3}, None, dict(ltp=last + 50, open=last, exchFeedTime="17-Nov-2026 15:04:50"), now, 100, "MCX")
check(out.get("RB_MCX_3h_BO10_GOLD_BUY") == "SENT", f"gold 3h 10-candle breakout fires ({out})")
txt = "\n".join(msgs)
check("book HALF" in txt and "1.5R – exit the rest" in txt and "real MCX costs" in txt, "call shows T1 book half / SL to cost, T2 1.5R")
rec = [r for r in st["fourh"]["open"] if r["rule"] == "RB_MCX_3h_BO10_GOLD_BUY"][0]
check(rec["half_t1"] and abs((rec["t1"] - rec["entry"]) - rec["risk"]) < 1e-6 and abs((rec["target"] - rec["entry"]) / rec["risk"] - 1.5) < 0.01,
      "record: T1 = entry + 1R, T2 = entry + 1.5R")

st2, m2 = dict(day={}, ledger=[]), []
o2 = RB.run(st2, m2, None, "SILVER", "MCX", contract("SILVER"), {"3h": f3}, None, dict(ltp=last + 50, open=last, exchFeedTime="17-Nov-2026 15:04:50"), now, 30, "MCX")
check("RB_MCX_3h_BO10_GOLD_BUY" not in o2 and not [m for m in m2 if "10-candle breakout · T1" in m], "gold-only rule does not fire on silver")
st3, m3 = dict(day={}, ledger=[]), []
f3a = f3.copy()
o3 = RB.run(st3, m3, None, "ALUMINIUM", "MCX", contract("ALUMINIUM"), {"3h": f3a, "1d": f3a.assign(time=pd.date_range(end="2026-11-16", periods=len(f3a)))},
            None, dict(ltp=last + 50, open=last, exchFeedTime="17-Nov-2026 15:04:50"), now, 5000, "MCX")
check(o3 == {} and m3 == [], "aluminium: no rulebook call on 3-hour / daily candles")


class Api:
    def __init__(self, q):
        self.q = q

    def quotes(self, req):
        return {t: self.q for toks in req.values() for t in toks}


def is_open(ex, t):
    return True


e, risk = rec["entry"], rec["risk"]
m = []
FH.track(st, m, Api(dict(ltp=e + 1.05 * risk, open=e)), pd.Timestamp("2026-11-18 10:00"), is_open)
check(len(m) == 1 and m[0].startswith("🎯 T1 HIT – GOLD FUT BUY") and "book HALF" in m[0], "T1 hit message")
check(rec["t1_done"] and rec["stop"] == e and st["fourh"]["open"], "after T1: stop at cost, trade still open")
m = []
FH.track(st, m, Api(dict(ltp=e - 0.2 * risk, open=e + 0.5 * risk)), pd.Timestamp("2026-11-18 13:00"), is_open)
cl = st["fourh"]["closed"][-1]
check(len(m) == 1 and "T1 half + rest stopped at cost after T1" in m[0] and abs(cl["result_R"] - 0.5) < 0.01, f"rest stopped at cost: +0.5R overall ({m})")
L = [x for x in st["ledger"] if x["key"] == rec["key"]][0]
check(L["status"] == "CLOSED" and abs(L["exit"] - (e + 0.5 * risk)) < 1.0, "report: exit = average of both halves")

# T1 then T2
st4, m4 = dict(day={}, ledger=[]), []
RB.run(st4, m4, None, "GOLD", "MCX", contract("GOLD"), {"3h": f3}, None, dict(ltp=last + 50, open=last, exchFeedTime="17-Nov-2026 15:04:50"), now, 100, "MCX")
r4 = st4["fourh"]["open"][0]; e4, k4 = r4["entry"], r4["risk"]
FH.track(st4, [], Api(dict(ltp=e4 + 1.1 * k4, open=e4)), pd.Timestamp("2026-11-18 10:00"), is_open)
m = []
FH.track(st4, m, Api(dict(ltp=e4 + 1.6 * k4, open=e4 + 1.1 * k4)), pd.Timestamp("2026-11-18 14:00"), is_open)
check(len(m) == 1 and "T1 half + target" in m[0] and abs(st4["fourh"]["closed"][-1]["result_R"] - 1.25) < 0.01, "T1 + T2: +1.25R overall")

# stop before T1: full loss, no blending
st5, m5 = dict(day={}, ledger=[]), []
RB.run(st5, m5, None, "GOLD", "MCX", contract("GOLD"), {"3h": f3}, None, dict(ltp=last + 50, open=last, exchFeedTime="17-Nov-2026 15:04:50"), now, 100, "MCX")
r5 = st5["fourh"]["open"][0]
m = []
FH.track(st5, m, Api(dict(ltp=r5["stop"] - 10, open=r5["entry"])), pd.Timestamp("2026-11-18 10:00"), is_open)
check(len(m) == 1 and "stop-loss" in m[0] and "T1 half" not in m[0] and st5["fourh"]["closed"][-1]["result_R"] < -0.99, "stop before T1: −1R")

print(f"\nmcx t1-half: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
