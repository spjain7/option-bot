"""Offline checks for alerts/intel.py (synthetic candles = test fixtures, never market evidence)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import intel as IN  # noqa: E402


def candles(drift, n=260, vol=1.0, seed=1, start="2026-01-01", freq="D", base=100.0, volume=1000):
    rng = np.random.default_rng(seed)
    c = base + np.cumsum(drift + rng.normal(0, vol, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0.1, 0.6, n)
    l = np.minimum(o, c) - rng.uniform(0.1, 0.6, n)
    return pd.DataFrame(dict(time=pd.date_range(start, periods=n, freq=freq), open=o, high=h, low=l, close=c,
                             volume=np.full(n, float(volume))))


def check(name, cond):
    assert cond, name
    print("✅", name)


up, down, flat = candles(0.6), candles(-0.6), candles(0.0, vol=0.4, seed=3)
check("uptrend -> Bullish trending", IN.regime(up)["primary"] == "Bullish trending")
check("downtrend -> Bearish trending", IN.regime(down)["primary"] == "Bearish trending")
check("flat noise -> not a trend", IN.regime(flat)["primary"] in ("Sideways", "Transition (trend not confirmed)"))
check("daily bias", IN.htf_bias(up) == "bullish" and IN.htf_bias(down) == "bearish")
check("structure trend labels", IN.structure(up)["trend"] in ("up (HH + HL)", "mixed") and IN.structure(down)["trend"] in ("down (LH + LL)", "mixed"))

fb = up.copy()
hi20 = fb["high"].iloc[-21:-1].max()
fb.loc[fb.index[-1], ["high", "close", "open"]] = [hi20 + 2, hi20 - 1, hi20 - 0.5]
check("failed breakout detected", (IN.structure(fb)["failed_breakout"] or "").startswith("up"))

check("OI labels", IN.oi_state(1, 2) == "Long buildup" and IN.oi_state(-1, 2) == "Short buildup"
      and IN.oi_state(1, -2) == "Short covering" and IN.oi_state(-1, -2) == "Long unwinding" and IN.oi_state(1, 0.1) == "OI flat"
      and IN.oi_state(None, 1) == "OI n/a")

v = up.copy(); v.loc[v.index[-1], "volume"] = 3000
check("abnormal volume", IN.volume_state(v)["rel"] == 3.0 and IN.volume_state(v)["label"].startswith("abnormal"))
z = up.copy(); z["volume"] = 0
check("zero volume -> n/a, not a signal", IN.volume_state(z)["rel"] is None)

intr = candles(0.05, n=30, vol=0.2, freq="15min", start="2026-11-04 09:15")
vw = IN.session_vwap(intr)
check("session VWAP computed", vw["vwap"] is not None and "VWAP" in vw["state"])

plan = dict(entry=float(up["close"].iloc[-1]), sl=float(up["close"].iloc[-1]) - 3, target=float(up["close"].iloc[-1]) + 6,
            rr=2.0, risk_unit=3.0, atr=2.0)
g_with = IN.grade("BUY", "breakout", v, daily=up, intraday=intr, plan=plan, oi_label="Long buildup")
g_against = IN.grade("BUY", "breakout", down, daily=down, plan=plan, oi_label="Short buildup")
check("BUY with trend, daily bias, volume, OI -> A or B", g_with["grade"] in ("A", "B"))
check("BUY against trend + daily + OI -> NO TRADE", g_against["grade"] == "NO TRADE" and g_against["reasons_against"])
check("grade is a class with reasons, not a probability", set(g_with) >= {"grade", "points", "reasons_for", "reasons_against", "context"}
      and not any("prob" in k for k in g_with))
bad = IN.grade("BUY", "breakout", up, daily=up, plan=dict(plan, rr=1.0))
check("reward:risk below 1.2 is a hard NO TRADE", bad["grade"] == "NO TRADE" and any("reward:risk" in x for x in bad["hard"]))
check("data failure is a hard NO TRADE", IN.grade("BUY", "breakout", up, daily=up, plan=plan, data_ok=False)["grade"] == "NO TRADE")
check("too few candles handled", IN.regime(up.head(20))["primary"].startswith("unknown"))

txt = IN.card("GOLD", "MCX", "BUY", "3-hour", "breakout", plan, g_with, "04-Nov 12:00", quote_time="12:02")
for k in ("POKHARNA RESEARCH", "Entry:", "Stop Loss:", "Setup Grade:", "Regime:", "Invalidation:", "Risk warning"):
    assert k in txt, k
print("✅ alert card has every required field")
print("ALL INTEL CHECKS PASSED")

# engine hook: real trade-plan dict from alerts/tradeplan.py through engine._intel_grade (shadow, never raises)
from alerts import engine as E, tradeplan as TP  # noqa: E402
fr = up.copy()
sig = dict(side="BUY", candle=str(fr["time"].iloc[-1]), close=float(fr["close"].iloc[-1]), atr=2.0)
pl = TP.futures_plan(name="GOLD", ex="MCX", contract="GOLDFUT", tf="1d", side="BUY", signal_time=sig["candle"], signal_close=sig["close"],
                     atr=2.0, stop_mult=1.5, target_r=3.0, tick=1.0, lot=1, mult=100, max_sl_pct=10, live=sig["close"], quote=None,
                     now=pd.Timestamp(sig["candle"]) + pd.Timedelta(hours=1), require_live=False)
gi = E._intel_grade("GOLD", "1d", sig, fr, up, None, pl, {"label": "Long buildup"})
assert gi is not None and gi["grade"] in ("A", "B", "C", "NO TRADE"), gi
r_ = E._intel_grade("X", "1d", sig, None, None, None, {}, None)   # missing data: no exception
assert r_ is None or r_["grade"] == "NO TRADE", r_
print("✅ engine hook grades a real plan and never raises")
