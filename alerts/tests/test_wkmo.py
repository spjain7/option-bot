"""6-Nov approved changes: MCX daily BUY = 20-day high + ADX >= 25 (2R); weekly BUY 2 ATR / 3R back on (SELL logged only);
monthly-candle BUY "1M" from a once-a-month long daily fetch.   python alerts/tests/test_wkmo.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from alerts import breakout as BO, engine as E, strategies as ST  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


def daily(n=300, slope=0.004, last_jump=0.03, noise=0.002, seed=1):
    r = np.random.default_rng(seed)
    t = pd.bdate_range(end="2026-11-05", periods=n)
    c = 100 * np.cumprod(1 + slope + r.normal(0, noise, n)); c[-1] = c[-2] * (1 + last_jump)
    return pd.DataFrame(dict(time=t, open=c * 0.999, high=c * 1.004, low=c * 0.996, close=c, volume=1000.0))


up = daily()
s = BO.evaluate_mcx_daily(up)
check(s["side"] == "BUY" and s["adx"] >= 25 and s.get("rule") == "mcx1d", "trending market, close above the 20-day high -> MCX daily BUY")
flat = daily(slope=0.0, noise=0.004, last_jump=0.05, seed=6)
s2 = BO.evaluate_mcx_daily(flat)
check(s2["side"] is None and "ADX" in (s2.get("why") or ""), "same breakout in a choppy market (ADX < 25) -> no call")
check(BO.target_r("1d", "MCX", "BUY") == 2.0 and BO.stop_k("1w") == 2.0 and BO.TARGET_R["1w"] == 3.0 and BO.TARGET_R["1M"] == 3.0,
      "targets: MCX daily BUY 2R, weekly 2 ATR / 3R, monthly-candle 3R")
mo = BO.monthly_candles(daily(n=600, slope=0.002), pd.Timestamp("2026-11-06"))
check(len(mo) >= 25 and pd.Timestamp(mo["time"].iloc[-1]).to_period("M") == pd.Period("2026-10", "M"), "monthly candles exclude the running month")
m = BO.evaluate_monthly_candle(mo)
check(m["side"] in ("BUY", None) and m.get("monthly_candle") and m["hh"] == float(mo["high"].iloc[-2]), "1M compares with last month's high")
check(("1w", "SELL") in E.SHADOW_ONLY and ("1M", "SELL") in E.SHADOW_ONLY and ST.is_live("BO_1w_BUY") and ST.is_live("BO_1M_BUY"),
      "weekly / monthly-candle SELL logged only, BUY live")


class Api:
    calls = 0

    def candles(self, ex, tok, iv, frm, to):
        Api.calls += 1
        return daily(n=1200, slope=0.001)


st = {}
a = Api()
x1 = E._monthly_hist(st, a, "MCX", dict(token="1"), "GOLD", pd.Timestamp("2026-11-06 10:00"))
x2 = E._monthly_hist(st, a, "MCX", dict(token="1"), "GOLD", pd.Timestamp("2026-11-07 10:00"))
check(x1 is not None and len(x1) >= 16 and Api.calls == 1 and len(x2) == len(x1), "long daily history fetched once per month, cached in the state")
print(f"\nwkmo: {ok} passed")
