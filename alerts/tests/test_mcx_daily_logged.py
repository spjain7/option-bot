"""Owner-approved 6-Nov (ROLLCHECK-001): MCX daily 20-day breakout + ADX BUY is LOGGED ONLY – no Telegram call, no ledger
row, outcome still tracked; index daily BUY and MCX weekly / monthly / 3h calls are unchanged.
python alerts/tests/test_mcx_daily_logged.py"""
import sys
from pathlib import Path
from unittest import mock
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from alerts import engine as E, breakout as BO, strategies as ST  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


def hourly(days=300, s=1):
    d0 = pd.bdate_range(end="2026-11-05", periods=days)
    rows, px = [], 70000.0
    rng = np.random.default_rng(4)
    for d in d0:
        for h in range(14):
            o = px; px = px * (1 + s * 0.0003 + rng.normal(0, 0.0008)); hi = max(o, px) * 1.0006; lo = min(o, px) * 0.9994
            rows.append((d + pd.Timedelta(hours=9 + h), o, hi, lo, px, 1000.0))
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


def fake_sig(fr, side="BUY"):
    x = fr.iloc[-1]; a = float((fr["high"] - fr["low"]).tail(14).mean())
    return dict(side=side, candle=str(x.time), close=float(x.close), hh=float(x.close) - a, ll=float(x.close) - 5 * a,
                ema200=float(x.close) * 0.9, atr=a, vol_x=2.0, adx=30.0, rsi=60.0)


def day():
    return dict(date="2026-11-06", alerts=0, watches=0, startup_sent=True, eod_sent=False, outcomes=[])


NOW = pd.Timestamp("2026-11-06 10:05")
h = hourly()
live = float(h["close"].iloc[-1])
q = {"ltp": live, "exchFeedTime": "06-Nov-2026 10:04:50"}
none = lambda fr, *a, **k: dict(side=None, why="test")  # noqa: E731

C_mcx = dict(symbol="GOLD05DEC26FUT", token="9", expiry="2026-12-05", lot=1, tick=1.0)
with mock.patch.object(BO, "evaluate_mcx_daily", side_effect=lambda fr: fake_sig(fr)), \
     mock.patch.object(BO, "evaluate", side_effect=none), mock.patch.object(BO, "evaluate_weekly", side_effect=none), \
     mock.patch.object(BO, "evaluate_monthly", side_effect=none), mock.patch.object(BO, "evaluate_monthly_candle", side_effect=none):
    st = E.new_state(); st["day"] = day(); msgs, info = [], {}
    E._breakouts(st, msgs, info, "GOLD", "MCX", C_mcx, h, None, NOW, None, q)
d1 = [p for p in st["bo_active"] if p["tf"] == "1d"]
check(len(d1) == 1 and d1[0].get("shadow"), "MCX daily 20-day + ADX BUY -> recorded as logged-only (outcome tracked)")
bo_calls = [m for m in msgs if "GOLD" in m and "DAILY" in m.upper() and "breakout retest" not in m and "WHY" not in m]
check(not bo_calls, "no Telegram call for the 20-day + ADX breakout")
check(not any(r.get("key", "").startswith(d1[0]["key"]) for r in st.get("ledger", [])), "no ledger / report row for it")
check(any("breakout retest" in m for m in msgs), "other MCX daily rules (rulebook breakout retest) still send – not disabled")
check("BO_1d_BUY_MCX" in info.get("bo_1d", "") or "logged only" in info.get("bo_1d", ""), "scan report says logged only")

C_idx = dict(symbol="NIFTY25NOV26FUT", token="1", expiry="2026-11-25", lot=75, tick=0.05)
hi_ = h.assign(open=h.open / 3, high=h.high / 3, low=h.low / 3, close=h.close / 3)
qi = {"ltp": float(hi_["close"].iloc[-1]), "exchFeedTime": "06-Nov-2026 10:04:50"}
with mock.patch.object(BO, "evaluate", side_effect=lambda fr, n_buy=None: fake_sig(fr) if len(fr) and (fr.time.diff().median() >= pd.Timedelta(hours=20)) else dict(side=None, why="t")), \
     mock.patch.object(BO, "evaluate_weekly", side_effect=none), mock.patch.object(BO, "evaluate_monthly", side_effect=none), \
     mock.patch.object(BO, "evaluate_monthly_candle", side_effect=none):
    st2 = E.new_state(); st2["day"] = day(); m2 = []
    E._breakouts(st2, m2, {}, "NIFTY", "NFO", C_idx, hi_, None, NOW, None, qi)
d2 = [p for p in st2["bo_active"] if p["tf"] == "1d"]
check(len(d2) == 1 and not d2[0].get("shadow") and any("NIFTY" in m for m in m2), "index daily BUY is still SENT (unchanged)")
check(ST.is_live("BO_1w_BUY") and ST.is_live("BO_1M_BUY") and ST.is_live("BO_3h_BUY") and ST.is_live("BO_1d_BUY"),
      "other breakout strategies remain LIVE")
print(f"\n{ok} checks passed")
