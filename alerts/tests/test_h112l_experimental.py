"""7-Nov H1.12L EXPERIMENTAL rule (RB_MCX_1h_BO20X_BUY_EXP): existing rules and BO signals unchanged vs main; first-cross
only; call labelled EXPERIMENTAL with no fixed target; trailing stop on 1h closes never loosens; tracker exits on the
trailing stop with target None; experimental calls never block existing strategies.
python alerts/tests/test_h112l_experimental.py"""
import subprocess
import sys
import types
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from alerts import rulebook as RB, four_hour as FH, strategies as ST  # noqa: E402

ok = 0
RID = "RB_MCX_1h_BO20X_BUY_EXP"


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


# 1. every pre-existing rule identical to the committed baseline (git main at bc3153e6)
try:
    src = subprocess.check_output(["git", "-C", str(ROOT), "show", "bc3153e6:alerts/rulebook.py"], text=True)
    base = types.ModuleType("rb_base"); base.__dict__["__name__"] = "rb_base"
    exec(compile(src, "rb_base", "exec"), base.__dict__)
    added = {RID} | {k for k in RB.RULES if "OIBO" in k}            # 7-Nov: owner OI rules added later (own test)
    check(set(RB.RULES) - added == set(base.RULES) and all(RB.RULES[k] == base.RULES[k] for k in base.RULES),
          "all 16 existing rulebook rules unchanged")
    r = np.random.default_rng(1)
    n = 600; c = 100 + np.cumsum(r.normal(0, 1, n))
    f = pd.DataFrame(dict(time=pd.date_range("2026-01-01 09:00", periods=n, freq="h"), open=c, high=c + r.random(n), low=c - r.random(n),
                          close=c, volume=1000 + 500 * r.random(n)))
    ff = RB.features(f)
    same = all(np.array_equal(a, b) for par in ("N55 vol2", "N10 vol0", "N20 vol1.5") for a, b in zip(RB.raw(ff, "BO", par), base.raw(ff, "BO", par)))
    check(same, "existing BO signals (N55 vol2, N10 vol0, N20 vol1.5) bit-identical to baseline")
except subprocess.CalledProcessError:
    print("(baseline commit not available – skipped identity checks)")

# 2. first cross only
t = pd.date_range("2026-03-02 09:00", periods=300, freq="h")
c = np.r_[np.full(279, 100.0) + np.sin(np.arange(279)) * 0.5, [103.0, 104.0, 105.0], np.full(18, 105.0)]
f = pd.DataFrame(dict(time=t, open=c, high=c + 0.3, low=c - 0.3, close=c, volume=1000.0))
b, _ = RB.raw(RB.features(f), "BO", "N20 vol0 x")
bo, _ = RB.raw(RB.features(f), "BO", "N20 vol0")
check(b[279] and not b[280] and not b[281] and bo[280], "x flag: fires on the first close above the 20-candle high only")

# 3. the call
fr = f.iloc[:280].reset_index(drop=True)
NOW = fr["time"].iloc[-1] + pd.Timedelta(minutes=62)
daily = pd.DataFrame(dict(time=pd.bdate_range(end=NOW.normalize() - pd.Timedelta(days=1), periods=120), open=1.0, high=1.0, low=1.0,
                          close=np.linspace(50, 100, 120), volume=1.0))
C = dict(symbol="ZINC30NOV26FUT", token="9", expiry="2026-11-30", lot=1, tick=0.05)
q = {"ltp": 103.0, "exchFeedTime": f"{NOW:%d-%b-%Y %H:%M:%S}"}
keep = dict(RB.RULES)
RB.RULES = {RID: keep[RID]}
st, m = {"day": {"date": str(NOW.date())}}, []
out = RB.run(st, m, None, "ZINC", "MCX", C, {"1h": fr}, daily, q, NOW, 5000, "MCX")
rec = st["fourh"]["open"][0]
check(out.get(RID) == "SENT" and len(m) == 2, "H1.12L signal -> call + WHY sent")
check("EXPERIMENTAL" in m[0] and "NOT VALIDATED" in m[0] and "Target  : none" in m[0] and "T2" not in m[0] and "NOT validated" in m[1],
      "messages labelled EXPERIMENTAL / not validated, no fixed target")
check(rec["target"] is None and rec["trail_atr"] == 4.0 and st["ledger"][0]["experimental"] and "EXPERIMENTAL" in st["ledger"][0]["type"]
      and st["ledger"][0]["cat"] == "FUTURES (EXPERIMENTAL)",
      "tracked record: trailing 4 ATR, no target; ledger row flagged experimental")
sl0 = rec["stop"]

# 4. trailing on later 1h closes: rises with the best close, never loosens
fr2 = f.iloc[:283].reset_index(drop=True); fr2.loc[280:, "close"] = [110.0, 120.0, 112.0]
m2 = []
RB.run(st, m2, None, "ZINC", "MCX", C, {"1h": fr2}, daily, q, fr2["time"].iloc[-1] + pd.Timedelta(minutes=62), 5000, "MCX")
exp_stop = round(120.0 - 4.0 * rec["atr"], 2)
check(rec["trailed"] and rec["stop"] == max(sl0, exp_stop) and any("SL UPDATE" in x for x in m2), "trailing stop = best close − 4 ATR, SL UPDATE sent")
s_before = rec["stop"]
fr3 = pd.concat([fr2, pd.DataFrame(dict(time=[fr2["time"].iloc[-1] + pd.Timedelta(hours=1)], open=[100.0], high=[100.3], low=[99.7], close=[100.0],
                                        volume=[1000.0]))], ignore_index=True)
RB.run(st, [], None, "ZINC", "MCX", C, {"1h": fr3}, daily, q, fr3["time"].iloc[-1] + pd.Timedelta(minutes=62), 5000, "MCX")
check(rec["stop"] == s_before, "a lower close never loosens the trailing stop")

# 5. exit on the trailing stop, target None does not crash
class Api:
    def __init__(self, ltp): self.ltp = ltp
    def quotes(self, d): return {"9": {"ltp": self.ltp}}
m5 = []
FH.track(st, m5, Api(rec["stop"] - 0.1), fr3["time"].iloc[-1] + pd.Timedelta(minutes=70), lambda ex, now: True)
check(any("EXIT" in x and "trailing stop" in x for x in m5) and not st["fourh"]["open"], "tracker exits on the trailing stop (no target)")

# 6. experimental call never blocks existing strategies (its own ledger category; strategies.py untouched)
st6 = {"ledger": [dict(st["ledger"][0], status="OPEN")]}
check(ST.conflict(st6, "ZINC", "SELL", "1h") is None and ST.conflict(st6, "ZINC", "BUY", "1h") is None, "open EXPERIMENTAL call blocks nothing")
st7 = {"ledger": [dict(status="OPEN", cat="FUTURES", name="ZINC", side="BUY", type="Daily BO", time="x")]}
check(ST.conflict(st7, "ZINC", "SELL", "1d") is not None, "existing calls still block as before")
RB.RULES = keep
print(f"{ok} H1.12L experimental checks passed")
