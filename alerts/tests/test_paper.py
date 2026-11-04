"""PAPER-ONLY E_BUY_v1 (alerts/paper.py) and the hard guard on every Telegram sender. Synthetic candles = fixtures only."""
import inspect, sys
from pathlib import Path
from unittest import mock
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from alerts import paper as PP  # noqa: E402
import paperguard  # noqa: E402


def check(name, cond):
    assert cond, name
    print("✅", name)


def series(n=240, seed=4):
    """Wide noise for 150 candles, then a tight range (volatility contraction), then a breakout candle with volume."""
    rng = np.random.default_rng(seed)
    t = pd.date_range("2026-10-01 09:00", periods=n, freq="h")
    c = np.empty(n); c[0] = 100
    for i in range(1, n):
        c[i] = c[i - 1] + (rng.normal(0, 1.2) if i < 150 else rng.normal(0.02, 0.15))
    o = np.r_[c[0], c[:-1]]
    sp = np.where(np.arange(n) < 150, 1.0, 0.15)
    h, l = np.maximum(o, c) + sp * 0.3, np.minimum(o, c) - sp * 0.3
    v = np.full(n, 1000.0)
    d = pd.DataFrame(dict(time=t, open=o, high=h, low=l, close=c, volume=v))
    k = n - 1                                                   # breakout candle
    top = d["high"].iloc[k - 20:k].max()
    d.loc[k, ["open", "close", "high", "low", "volume"]] = [d["close"].iloc[k - 1], top + 0.05, top + 0.08, d["close"].iloc[k - 1] - 0.02, 2500]
    return d


h1 = series()
s = PP.check_signal(h1)
check("compression + 20-candle breakout + volume + RSI -> E_BUY_v1 signal", s.get("signal") is True and s["stop"] < s["close"])
check("one candle earlier: no signal", not PP.check_signal(h1.iloc[:-1]).get("signal"))
z = h1.copy(); z["volume"] = 0
check("no valid volume -> rule not checked (never assumed)", "volume not valid" in PP.check_signal(z)["reason"])
check("on_candles has no message-list parameter (cannot send)", "msgs" not in inspect.signature(PP.on_candles).parameters)

state = {}
st = PP.on_candles(state, "GOLD", "MCX", "GOLDFUT", h1, pd.Timestamp("2026-11-04 12:05"), grade_fields={"grade": "B"})
b = state["paper"]["E_BUY_v1"]
check("signal recorded as PENDING, PAPER_ONLY, with grade", "signal" in st and b["pending"][0]["mode"] == "PAPER_ONLY"
      and b["pending"][0]["grade"] == "B" and b["pending"][0]["status"] == "PENDING")
check("paper book is separate from the live ledger", "ledger" not in state)
PP.on_candles(state, "GOLD", "MCX", "GOLDFUT", h1, pd.Timestamp("2026-11-04 12:20"))
check("same candle is not recorded twice", len(b["pending"]) == 1)

# next candles: entry at the next open, then T1 then T2
last = h1.iloc[-1]
e = float(last["close"]); R = e - b["pending"][0]["stop"]
nxt = pd.DataFrame(dict(time=pd.date_range(last["time"] + pd.Timedelta(hours=1), periods=3, freq="h"),
                        open=[e, e + 0.5 * R, e + 1.5 * R], high=[e + 0.4 * R, e + 1.2 * R, e + 2.3 * R],
                        low=[e - 0.2 * R, e + 0.3 * R, e + 1.4 * R], close=[e + 0.3 * R, e + 1.1 * R, e + 2.1 * R], volume=[1000] * 3))
h2 = pd.concat([h1, nxt], ignore_index=True)
PP.on_candles(state, "GOLD", "MCX", "GOLDFUT", h2, pd.Timestamp("2026-11-04 15:05"))
cl = b["closed"][-1]
check("filled at the next open, half at T1, rest at T2", cl["entry"] == e and cl["t1_hit"] and cl["t2_hit"] and cl["exit_reason"] == "T2")
check("net R after costs = 1.5R minus 0.04 % of entry in R", abs(cl["net_R"] - (1.5 - 0.0004 * cl["entry"] / cl["R"])) < 1e-3)
check("MFE / MAE recorded from candle highs / lows", cl["mfe_R"] >= 2.0 and cl["mae_R"] <= -0.19 and cl["measure"] == "1-hour candle highs/lows")

# stop first when one candle touches both
state2 = {}
PP.on_candles(state2, "GOLD", "MCX", "GOLDFUT", h1, pd.Timestamp("2026-11-04 12:05"))
both = nxt.copy(); both.loc[0, ["high", "low"]] = [e + 1.2 * R, e - 1.2 * R]
PP.on_candles(state2, "GOLD", "MCX", "GOLDFUT", pd.concat([h1, both.iloc[:1]], ignore_index=True), pd.Timestamp("2026-11-04 13:05"))
c2 = state2["paper"]["E_BUY_v1"]["closed"][-1]
check("candle touching stop and T1 -> stop (stop first)", c2["exit_reason"] == "stop" and c2["net_R"] < -0.99)
sm = PP.summary(state)
check("summary is labelled PAPER_ONLY", sm["mode"] == "PAPER_ONLY" and sm["closed"] == 1)

# ---- hard guard on every sender ----
clean, dropped = PP.guard_outbox(["🟢 BUY GOLD FUT", "E_BUY_v1 GOLD PAPER_ONLY"])
check("outbox guard drops PAPER_ONLY items", clean == ["🟢 BUY GOLD FUT"] and len(dropped) == 1)
import notify  # noqa: E402
with mock.patch.object(notify, "TG_TOKEN", "x"), mock.patch.object(notify, "TG_CHAT", "y"), mock.patch.object(notify, "_post") as p:
    notify.send("paper trade PAPER_ONLY")
    check("notify.send refuses PAPER_ONLY", not p.called)
from crude import run as CR  # noqa: E402
with mock.patch.dict("os.environ", {"TELEGRAM_TOKEN": "x", "TELEGRAM_CHAT_ID": "y"}), mock.patch.object(CR.requests, "post") as p:
    ok, why = CR.telegram("E_BUY_v1 PAPER_ONLY")
    check("crude.run.telegram refuses PAPER_ONLY", not ok and not p.called)
from alerts import run as AR  # noqa: E402
check("send_photo refuses a PAPER_ONLY caption", AR.send_photo(__file__, "PAPER_ONLY") == (False, "blocked: PAPER_ONLY"))
check("guard marker is shared", PP.PAPER_ONLY == paperguard.MARKER)
print("ALL PAPER CHECKS PASSED")

# engine hook: E_BUY_v1 runs inside alerts.engine._breakouts for MCX without sending anything
from alerts import engine as E  # noqa: E402
stE, msgsE, info = E.new_state(), [], {}
stE.setdefault("day", {"alerts": 0})
cE = dict(symbol="GOLD04DEC26FUT", token="1", lot=1, tick=1.0, expiry="2026-12-04", name="GOLD")
E._breakouts(stE, msgsE, info, "GOLD", "MCX", cE, h1, None, pd.Timestamp("2026-10-11 09:05"), None, None)
check("engine hook records the paper signal", "signal" in str(info.get("paper_ebuy")) and stE["paper"]["E_BUY_v1"]["pending"])
check("engine hook sends nothing for the paper signal", not any("PAPER_ONLY" in str(m) or "E_BUY" in str(m) for m in msgsE))
print("ALL PAPER ENGINE CHECKS PASSED")
