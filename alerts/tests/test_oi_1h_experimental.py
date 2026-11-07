"""7-Nov owner OI-breakout rule (RB_*_1h_OIBO_*_EXP, UNTESTED): existing rules unchanged vs 567805d; call only when ALL of
first 1h close beyond the 20-candle high, volume >= 2.5x, OI build-up in the signal hour, no rejection wick, no swing /
daily level within the 3R target; SL 1 ATR, T2 3R; messages say EXPERIMENTAL / UNTESTED; ledger row is experimental.
python alerts/tests/test_oi_1h_experimental.py"""
import subprocess
import sys
import types
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from alerts import rulebook as RB  # noqa: E402
import wsbars as WB  # noqa: E402

ok = 0
RID = "RB_MCX_1h_OIBO_BUY_EXP"


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


try:
    src = subprocess.check_output(["git", "-C", str(ROOT), "show", "567805d:alerts/rulebook.py"], text=True)
    base = types.ModuleType("rb_base"); exec(compile(src, "rb_base", "exec"), base.__dict__)
    new = {k for k in RB.RULES if "OIBO" in k}
    check(set(RB.RULES) - new == set(base.RULES) and all(RB.RULES[k] == base.RULES[k] for k in base.RULES) and len(new) == 4,
          "17 existing rules unchanged; 4 new OI rules (MCX / index × BUY / SELL)")
except subprocess.CalledProcessError:
    print("(baseline commit not available – identity check skipped)")


def frame(last_open=100.45, last_close=101.0, last_high=101.1, last_low=100.4, last_vol=3000.0, n=300):
    r = np.random.default_rng(3)
    t = pd.date_range("2026-10-01 09:00", periods=n, freq="h")
    c = 100 + r.normal(0, 0.15, n)
    f = pd.DataFrame(dict(time=t, open=c, high=c + 0.3, low=c - 0.3, close=c, volume=1000.0))
    f.loc[n - 1, ["open", "close", "high", "low", "volume"]] = [last_open, last_close, last_high, last_low, last_vol]
    return f


fr = frame()
NOW = fr["time"].iloc[-1] + pd.Timedelta(minutes=62)
daily = pd.DataFrame(dict(time=pd.bdate_range(end=NOW.normalize() - pd.Timedelta(days=1), periods=80), open=95.0,
                          high=95.0 + np.sin(np.arange(80)), low=90.0, close=94.0, volume=1.0))
C = dict(symbol="GOLD04DEC26FUT", token="77", expiry="2026-12-04", lot=1, tick=0.05)
q = {"ltp": 101.0, "exchFeedTime": f"{NOW:%d-%b-%Y %H:%M:%S}"}


def ws(oi_from, oi_to, t0=fr["time"].iloc[-1]):
    m = pd.DataFrame(dict(time=pd.date_range(t0 - pd.Timedelta(minutes=10), periods=70, freq="min")))
    m["oi"] = np.r_[np.full(10, oi_from), np.linspace(oi_from, oi_to, 60)]
    for k in ("open", "high", "low", "close", "volume"):
        m[k] = 1.0
    return m


keep = dict(RB.RULES)
RB.RULES = {RID: keep[RID]}


def run(f=fr, d=daily, oi=None, ws_df=None):
    WB.minutes = (lambda token, day, d_=None: ws_df) if ws_df is not None else (lambda token, day, d_=None: pd.DataFrame())
    st, m = {"day": {"date": str(NOW.date())}}, []
    out = RB.run(st, m, None, "GOLD", "MCX", C, {"1h": f}, d, q, NOW, 100, "MCX", oi=oi)
    return st, m, out.get(RID)


st, m, o = run(ws_df=ws(1000, 1100))
check(o == "SENT" and len(m) == 2, "breakout + volume 3× + OI +10 % in the hour + room -> call sent")
check("UNTESTED" in m[0] and "EXPERIMENTAL" in m[0] and "Evidence: NONE" in m[1] and "Long build-up" in m[1], "messages say EXPERIMENTAL / UNTESTED, show OI build-up")
rec = st["fourh"]["open"][0]
atr = RB.features(fr)["atr"].iloc[-1]
lvl20 = fr["high"].iloc[-21:-1].max()
check(abs((rec["entry"] - rec["stop"]) - 1.5 * atr) < 0.06 and rec["stop"] < lvl20, "v2: SL = 1.5 ATR and beyond (below) the breakout level")
check(abs((rec["target"] - rec["entry"]) - 3.0 * atr) < 0.06 and "3 ATR reference" in rec["target_basis"], "v2: no level ahead -> 3-ATR reference target")
check(rec["version"].startswith("OIBO-v2") and rec["vol_x"] >= 2.5 and "build-up" in rec["oi_txt"], "tracking fields: version, volume ×, OI")
check(st["ledger"][0]["cat"] == "FUTURES (EXPERIMENTAL)", "ledger row in the experimental category (never blocks existing calls)")
_, m2, o2 = run(f=frame(last_vol=2000.0), ws_df=ws(1000, 1100))
check(o2 is None and not m2, "volume 2× (< 2.5×) -> no signal")
_, m3, o3 = run(ws_df=ws(1100, 1000))
check(not m3 and "no long build-up" in str(o3), "OI falling during the hour -> rejected")
_, m4, o4 = run(f=frame(last_open=101.0, last_close=101.6, last_high=104.5, last_low=100.9), ws_df=ws(1000, 1100))
check(not m4 and "rejection wick" in str(o4), "long upper wick (reversing from resistance) -> rejected")
dres = daily.copy(); dres.loc[60, "high"] = 101.0 + 2.4 * atr          # resistance before the 3-ATR target, room ~1.5R
st5, m5, o5 = run(d=dres, ws_df=ws(1000, 1100))
r5 = st5["fourh"]["open"][0] if st5.get("fourh", {}).get("open") else {}
check(o5 == "SENT" and abs(r5["target"] - (dres.loc[60, "high"] - 0.1 * atr)) < 0.06 and "resistance" in r5["target_basis"],
      "v2: resistance before the 3-ATR target -> target placed just before the resistance")
dres2 = daily.copy(); dres2.loc[60, "high"] = 101.0 + 1.2 * atr         # room < 1.2R
_, m5b, o5b = run(d=dres2, ws_df=ws(1000, 1100))
check(not m5b and "leaves only" in str(o5b), "v2: resistance too close (room < 1.2R) -> no call")
q["ltp"] = 103.0
_, m5c, o5c = run(f=frame(last_open=101.5, last_close=103.0, last_high=103.1, last_low=101.4), ws_df=ws(1000, 1100))
q["ltp"] = 101.0
check(not m5c and "chasing" in str(o5c), "v2: breakout candle so big that the SL would sit above the breakout level -> no call (chasing)")
_, m6, o6 = run(ws_df=None)
check(not m6 and "OI not available" in str(o6), "no live OI at all -> rejected (never invented)")
_, m7, o7 = run(ws_df=None, oi=dict(oi=1e6, chg_pct=0.8, gap_min=15, label="Long buildup"))
check(o7 == "SENT", "no 1-min OI feed but quote OI reading shows build-up -> call sent (fallback)")
WB.minutes = lambda token, day, d_=None: ws(1000, 1100)
st8 = {"day": {"date": str(NOW.date())}, "ledger": [dict(status="OPEN", cat="FUTURES (EXPERIMENTAL)", experimental=True, name="GOLD",
                                                          side="SELL", type="1-hour BO (EXPERIMENTAL)", key="x", time="x")]}
m8 = []
o8 = RB.run(st8, m8, None, "GOLD", "MCX", C, {"1h": fr}, daily, q, NOW, 100, "MCX").get(RID)
check(not m8 and "conflicts with open experimental" in str(o8), "experimental BUY blocked by an open experimental SELL (no contradictory calls)")
st9 = {"day": {"date": str(NOW.date())}, "ledger": [dict(st8["ledger"][0], side="BUY")]}; m9 = []   # fresh state (candle not seen)
o9 = RB.run(st9, m9, None, "GOLD", "MCX", C, {"1h": fr}, daily, q, NOW, 100, "MCX").get(RID)
check(not m9 and "duplicate" in str(o9), "same-side experimental call already open -> duplicate rejected")
RB.RULES = keep
print(f"{ok} OI 1h experimental checks passed")
