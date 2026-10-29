"""29-Oct approved LIVE candle-setup calls (alerts/candle_setups.py). Deterministic fixtures, no network.
python -m alerts.tests.test_candle_setups"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from alerts import candle_setups as CS  # noqa: E402
from crude import indicators as I  # noqa: E402

OK = []
C = dict(symbol="GOLD26DECFUT", token="t1", tick=1.0, lot=1)


def check(name, cond):
    assert cond, name
    OK.append(name)
    print("✅", name)


def base(n=80, start=1000.0, step=-2.0):
    """Daily candles drifting down with small bodies but NO hammer shape (upper and lower wicks equal)."""
    days = pd.bdate_range(end="2026-10-20", periods=n)
    rows, px = [], start
    for d in days:
        o = px; c = px + step
        rows.append((d + pd.Timedelta(hours=9), o, max(o, c) + 3, min(o, c) - 3, c, 1000.0))
        px = c
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


def add(df, day, o, h, l, c):
    t = pd.Timestamp(day) + pd.Timedelta(hours=9)
    return pd.concat([df, pd.DataFrame([(t, o, h, l, c, 1000.0)], columns=df.columns)], ignore_index=True)


def hammer_day(df):
    last = df["close"].iloc[-1]
    return add(df, "2026-10-21", last, last + 1, last - 20, last + 0.5)      # long lower wick, tiny body


def run(frames, now):
    st, msgs = {"day": {}}, []
    for d in frames:
        CS.on_mcx(st, msgs, "GOLD", "MCX", C, d, None, None, now)
    return st, msgs


def test_hammer_flow():
    d0 = hammer_day(base())
    hi, lo = d0["high"].iloc[-1], d0["low"].iloc[-1]
    st, msgs = run([d0], pd.Timestamp("2026-10-21 23:40"))
    r = st["candle_setups"]["open"][0]
    check("hammer -> BUY SETUP message with trigger = hammer high, stop below its low",
          len(msgs) == 1 and "BUY SETUP – GOLD FUT (MCX)" in msgs[0] and r["trigger"] == hi and r["stop"] < lo)
    R = hi - r["stop"]
    d1 = add(d0, "2026-10-22", hi - 1, hi + 5, hi - 2, hi + 4)              # breaks the high intraday
    d2 = add(d1, "2026-10-23", hi + 4, hi + 2 * R + 10, hi + 3, hi + 2 * R + 5)
    st2, m2 = {"day": {}}, []
    for d in (d0, d1, d2):
        CS.on_mcx(st2, m2, "GOLD", "MCX", C, d, None, None, pd.Timestamp(d["time"].iloc[-1]) + pd.Timedelta(hours=15))
    cl = st2["candle_setups"]["closed"]
    check("breakout fills at the trigger, then target 2R is hit: TRIGGERED and EXIT messages, +2R",
          any("TRIGGERED" in m for m in m2) and len(cl) == 1 and cl[0]["exit_reason"].endswith("target 2R") and abs(cl[0]["gross_R"] - 2) < 1e-6)
    check("the call is written to the ledger and closed there", any(L["key"] == cl[0]["key"] and L["status"] == "CLOSED" for L in st2["ledger"]))


def test_gap_through_target():
    d0 = hammer_day(base()); hi = d0["high"].iloc[-1]
    st, m = {"day": {}}, []
    CS.on_mcx(st, m, "GOLD", "MCX", C, d0, None, None, pd.Timestamp("2026-10-21 23:40"))
    R = hi - st["candle_setups"]["open"][0]["stop"]
    d1 = add(d0, "2026-10-22", hi - 1, hi + 1, hi - 2, hi)
    d2 = add(d1, "2026-10-23", hi + 3 * R, hi + 3 * R + 5, d0["low"].iloc[-1] - 50, hi + 3 * R)   # opens above target, low below stop
    for d in (d1, d2):
        CS.on_mcx(st, m, "GOLD", "MCX", C, d, None, None, pd.Timestamp(d["time"].iloc[-1]) + pd.Timedelta(hours=15))
    cl = st["candle_setups"]["closed"][0]
    check("360ONE case: a day opening beyond the target fills the target at the open even if its low is below the stop",
          "gap" in cl["exit_reason"] and "target" in cl["exit_reason"] and cl["gross_R"] > 2)


def test_cancellations():
    d0 = hammer_day(base()); hi, lo = d0["high"].iloc[-1], d0["low"].iloc[-1]
    st, m = {"day": {}}, []
    CS.on_mcx(st, m, "GOLD", "MCX", C, d0, None, None, pd.Timestamp("2026-10-21 23:40"))
    d1 = add(d0, "2026-10-22", lo + 2, lo + 3, lo - 30, lo - 20)
    CS.on_mcx(st, m, "GOLD", "MCX", C, d1, None, None, pd.Timestamp("2026-10-22 23:40"))
    check("stop level touched before the breakout -> CANCELLED, no entry",
          st["candle_setups"]["closed"][0]["entry"] is None if "entry" in st["candle_setups"]["closed"][0] else True)
    check("cancel message sent", any("CANCELLED" in x for x in m))
    st2, m2 = {"day": {}}, []
    d = d0
    CS.on_mcx(st2, m2, "GOLD", "MCX", C, d, None, None, pd.Timestamp("2026-10-21 23:40"))
    for k, day in enumerate(("2026-10-22", "2026-10-23", "2026-10-26")):
        d = add(d, day, hi - 3, hi - 1, hi - 4, hi - 2)                     # inside, no breakout, no stop
        CS.on_mcx(st2, m2, "GOLD", "MCX", C, d, None, None, pd.Timestamp(day) + pd.Timedelta(hours=23, minutes=40))
    check("no breakout within 3 sessions -> cancelled", st2["candle_setups"]["closed"][0]["exit_reason"] == "no breakout within 3 sessions")


def test_contract_change_and_one_at_a_time():
    d0 = hammer_day(base()); hi = d0["high"].iloc[-1]
    st, m = {"day": {}}, []
    CS.on_mcx(st, m, "GOLD", "MCX", C, d0, None, None, pd.Timestamp("2026-10-21 23:40"))
    CS.on_mcx(st, m, "GOLD", "MCX", C, d0, None, None, pd.Timestamp("2026-10-21 23:55"))
    check("same candle evaluated twice -> one setup only", len(st["candle_setups"]["open"]) == 1 and len(m) == 1)
    d1 = add(d0, "2026-10-22", hi - 1, hi + 5, hi - 2, hi + 4)
    CS.on_mcx(st, m, "GOLD", "MCX", C, d1, None, None, pd.Timestamp("2026-10-22 23:40"))
    C2 = dict(C, symbol="GOLD27FEBFUT")
    CS.on_mcx(st, m, "GOLD", "MCX", C2, d1, None, None, pd.Timestamp("2026-10-23 10:00"))
    cl = st["candle_setups"]["closed"]
    check("contract change closes the open call at the last price", len(cl) == 1 and "contract changed" in cl[0]["exit_reason"]
          and cl[0]["exit"] is not None)


def test_stock_hanging_man_needs_uptrend():
    up = base(step=+2.0)
    last = up["close"].iloc[-1]
    d = add(up, "2026-10-21", last, last + 1, last - 20, last + 0.5)
    st, m = {"day": {}}, []
    CS.on_stock_daily(st, m, "TCS", dict(symbol="TCS26NOVFUT", token="t", tick=0.05, lot=175), d, pd.Timestamp("2026-10-21 15:40"))
    r = st["candle_setups"]["open"][0]
    check("stock hanging man in an uptrend -> SELL SETUP below its low, stop above its high, ₹ risk per lot shown",
          "SELL SETUP – TCS FUT (NSE)" in m[0] and r["trigger"] == d["low"].iloc[-1] and r["stop"] > d["high"].iloc[-1] and "per lot" in m[0])
    dn = base(step=-2.0); last = dn["close"].iloc[-1]
    d2 = add(dn, "2026-10-21", last, last + 1, last - 20, last + 0.5)
    st2, m2 = {"day": {}}, []
    CS.on_stock_daily(st2, m2, "TCS", dict(symbol="TCS26NOVFUT", token="t", tick=0.05, lot=175), d2, pd.Timestamp("2026-10-21 15:40"))
    check("the same candle in a downtrend is not a hanging-man SELL", not m2)


def test_ema_cross():
    n = 200
    t = pd.date_range("2026-06-01 09:00", periods=n, freq="3h")
    k = np.arange(150)
    px = np.r_[130 - 0.15 * k, 130 - 0.15 * 149 + np.cumsum(np.r_[np.full(10, 0.2), np.full(40, 1.0)])]
    f = pd.DataFrame(dict(time=t, open=px, high=px + 1.0, low=px - 1.0, close=px + 0.5, volume=1000.0))
    st, m = {"day": {}}, []
    hit = None
    for i in range(130, n):
        before = len(m)
        CS.on_mcx(st, m, "GOLD", "MCX", C, None, f.iloc[: i + 1], None, t[i] + pd.Timedelta(hours=3))
        if hit is None and any("EMA 13/48" in x and "BUY –" in x for x in m[before:]):
            hit = i
    op = [r for r in st["candle_setups"]["open"] if r["setup"] == "MCX_EMA1348"]
    check("EMA13 crossing above EMA48 with ADX ≥ 20 rising -> BUY alert, entered at the next 3-hour open with a 3-ATR safety stop",
          hit is not None and op and op[0]["status"] == "open" and op[0]["entry"] == f["open"].iloc[hit + 1]
          and abs(op[0]["entry"] - op[0]["stop"] - 3 * op[0]["atr"]) < 1e-6)
    q = px[-1] - np.cumsum(np.full(40, 0.6))
    g = pd.concat([f, pd.DataFrame(dict(time=pd.date_range(t[-1] + pd.Timedelta(hours=3), periods=40, freq="3h"),
                                        open=q + 0.3, high=q + 0.8, low=q - 0.8, close=q, volume=1000.0))], ignore_index=True)
    for i in range(n, len(g)):
        CS.on_mcx(st, m, "GOLD", "MCX", C, None, g.iloc[: i + 1], None, g["time"].iloc[i] + pd.Timedelta(hours=3))
    cl = [r for r in st["candle_setups"]["closed"] if r["setup"] == "MCX_EMA1348"]
    check("exit at the next open after EMA13 closes back below EMA48 (warning, then EXIT message)",
          len(cl) == 1 and cl[0]["exit_reason"] == "EMA13 closed back below EMA48" and any("closed below EMA48" in x for x in m)
          and any(x.startswith("✅ EXIT") or x.startswith("❌ EXIT") for x in m))


def test_hourly_rule():
    check("1-hour pattern candles at 14:15 and 15:15 are not allowed; 13:15 is",
          not CS.hourly_pattern_allowed("2026-10-28 14:15") and not CS.hourly_pattern_allowed("2026-10-28 15:15")
          and CS.hourly_pattern_allowed("2026-10-28 13:15"))


def test_engine_path():
    """End to end through alerts.engine._breakouts for an MCX contract: a hammer day produces exactly one BUY SETUP message."""
    from alerts import engine as E
    days = pd.bdate_range(end="2026-10-21", periods=140)
    rows, px = [], 1000.0
    for k, d in enumerate(days):
        last = k == len(days) - 1
        for h in range(9, 24):
            o = px
            px = px - 0.15 if not last else px
            hi, lo = max(o, px) + 0.4, min(o, px) - 0.4
            if last and h == 13:
                lo = o - 25                                        # long lower wick on the last day
            if last and h == 23:
                px = o + 0.3
            rows.append((d + pd.Timedelta(hours=h), o, hi, lo, px, 500.0))
    h1 = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    st = E.new_state(); st["day"] = dict(date="2026-10-21", alerts=0, watches=0, outcomes=[])
    msgs, info = [], {}
    c = dict(symbol="GOLD26DECFUT", token="g1", tick=1.0, lot=1, expiry="2026-12-04")
    E._breakouts(st, msgs, info, "GOLD", "MCX", c, h1, None, pd.Timestamp("2026-10-22 08:00"), None, None)
    check("engine path: MCX hammer day -> one BUY SETUP message, setup tracked in the state",
          sum("BUY SETUP – GOLD FUT (MCX)" in m for m in msgs) == 1 and st["candle_setups"]["open"][0]["setup"] == "MCX_HAMMER")


def sweep_frame(vol_last=3000.0):
    """3-hour candles: a range with two equal pivot highs at 110, then a candle that pokes to 111 and closes at 108."""
    t = pd.date_range("2026-08-03 09:15", periods=120, freq="3h")
    rows = []
    for k in range(119):
        base = 100 + 4 * np.sin(k / 3.0)
        hi = 110.0 if k in (100, 108) else min(base + 1.5, 109.0)
        rows.append((t[k], base, hi, base - 1.5, base + 0.2, 1000.0))
    rows.append((t[119], 108.5, 111.0, 107.0, 108.0, vol_last))
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


STK = dict(symbol="TCS26NOVFUT", token="t", tick=0.05, lot=175)


def test_sweep3h():
    f = sweep_frame()
    i = len(f) - 1
    check("equal highs at 110 are found before the sweep candle", abs(CS.equal_high_at(f, i, float(I.atr(f, 14).iat[i])) - 110.0) < 1e-9)
    st, m = {"day": {}}, []
    CS.on_stock_3h(st, m, "TCS", STK, f, pd.Timestamp("2026-10-20 15:40"), lambda d: "SB", lambda a, b: -0.8)
    r = st["candle_setups"]["open"][0] if st["candle_setups"]["open"] else {}
    check("sweep above equal highs + volume 3× + OI support -> SELL SETUP below the candle low, stop above its high, 1:1",
          len(m) == 1 and "SELL SETUP – TCS FUT (NSE) · 3-HOUR LIQUIDITY SWEEP" in m[0] and r["trigger"] == 107.0 and r["stop"] > 111.0
          and "Target 1R" in m[0] and "OI" in m[0])
    for lab, why, vol, doi in (("low volume", None, 1200.0, -0.8), ("previous day long buildup", "LB", 3000.0, -0.8),
                               ("OI rising during the sweep", "SB", 3000.0, 0.6), ("OI unavailable", "SB", 3000.0, None)):
        st2, m2 = {"day": {}}, []
        CS.on_stock_3h(st2, m2, "TCS", STK, sweep_frame(vol), pd.Timestamp("2026-10-20 15:40"), lambda d, w=why: w, lambda a, b, x=doi: x)
        check(f"no alert when {lab}", not m2 and not st2["candle_setups"]["open"])
    R = r["stop"] - r["trigger"]
    nxt = pd.DataFrame([(f["time"].iat[i] + pd.Timedelta(hours=3), 107.5, 108.0, 106.5, 106.8, 1000.0),
                        (f["time"].iat[i] + pd.Timedelta(hours=6), 106.8, 107.0, 107.0 - R - 0.5, 106.0, 1000.0)], columns=f.columns)
    g = pd.concat([f, nxt], ignore_index=True)
    CS.on_stock_3h(st, m, "TCS", STK, g, pd.Timestamp("2026-10-21 15:40"), lambda d: "SB", lambda a, b: -0.8)
    cl = st["candle_setups"]["closed"]
    check("breaks the low -> TRIGGERED at the trigger, then target 1R -> EXIT +1R",
          any("TRIGGERED" in x for x in m) and cl and cl[0]["exit_reason"].endswith("target 1R") and abs(cl[0]["gross_R"] - 1) < 1e-6)


def test_sweep15():
    t = pd.date_range("2026-10-19 09:15", periods=26, freq="15min").append(pd.date_range("2026-10-20 09:15", periods=26, freq="15min")) \
          .append(pd.date_range("2026-10-21 09:15", periods=12, freq="15min"))
    n = len(t)
    px = 100 + np.sin(np.arange(n) / 4.0)
    f = pd.DataFrame(dict(time=t, open=px, high=px + 0.3, low=px - 0.3, close=px, volume=1000.0, oi=np.linspace(1e6, 1.1e6, n)))
    hi = f["high"].iloc[-21:-1].max()
    f.loc[n - 1, ["open", "high", "low", "close", "volume"]] = [hi - 0.1, hi + 0.8, hi - 0.4, hi - 0.3, 2500.0]
    f.loc[n - 1, "oi"] = f["oi"].iloc[n - 2] * 0.99
    ob, m = {}, []
    CS.sweep15_log(ob, "TCS", None, f, pd.Timestamp("2026-10-21 12:20"), m, 175)
    r = ob.get("sweep15", {}).get("open", [])
    check("15-min SELL sweep with volume + OI falling -> logged AND sent as a SELL SETUP (1:1, ₹ per lot)",
          len(r) == 1 and r[0]["side"] == "SELL" and r[0]["V"] and r[0]["OD"] and r[0]["send"] and len(m) == 1
          and "15-MIN LIQUIDITY SWEEP" in m[0] and "per lot" in m[0])
    g = f.copy(); g.loc[len(g) - 1, "oi"] = g["oi"].iloc[-2] * 1.01
    ob2, m2 = {}, []
    CS.sweep15_log(ob2, "TCS", None, g, pd.Timestamp("2026-10-21 12:20"), m2, 175)
    check("same sweep with OI rising -> logged only, not sent", len(ob2["sweep15"]["open"]) == 1 and not m2)


if __name__ == "__main__":
    test_hammer_flow(); test_gap_through_target(); test_cancellations(); test_contract_change_and_one_at_a_time()
    test_stock_hanging_man_needs_uptrend(); test_ema_cross(); test_hourly_rule(); test_engine_path(); test_sweep3h(); test_sweep15()
    print(f"\nALL {len(OK)} CANDLE-SETUP CHECKS PASSED")
