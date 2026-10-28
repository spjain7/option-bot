"""Regression tests for the validated trade plan (28-Oct-2026 audit). Deterministic fixtures, no network, no orders.
python -m alerts.tests.test_tradeplan"""
import json, math, os, sys, tempfile
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from alerts import tradeplan as TP, breakout as BO, engine as E, report as RP, optfilter as OF  # noqa

OK = []


def check(name, cond):
    assert cond, name
    OK.append(name)
    print("✅", name)


NOW = pd.Timestamp("2026-10-28 12:17")
BASE = dict(contract="X", signal_time="2026-10-28 09:15", lot=1, mult=1, max_sl_pct=4.0, now=NOW)
CASES = [("NIFTY", "NFO", 22600.0, 60.0, 0.05, 75), ("BANKNIFTY", "NFO", 51200.0, 160.0, 0.05, 35),
         ("TCS", "NFO", 3450.0, 30.0, 0.10, 175), ("GOLD", "MCX", 143454.0, 900.0, 1.0, 1), ("NATURALGAS", "MCX", 288.3, 3.1, 0.10, 1250)]


FRESH = {"exchFeedTime": "28-Oct-2026 12:16:40"}


def plan(**k):
    a = dict(BASE, quote=FRESH); a.update(k)
    return TP.futures_plan(**a)


def test_quote_timestamps():
    b = dict(name="NIFTY", ex="NFO", tf="3h", side="BUY", signal_close=22600.0, atr=60.0, stop_mult=2.0, target_r=2.0, tick=0.05,
             live=22610.0)
    r = lambda q, **k: plan(**dict(b, **k), quote=q)
    check("valid Angel timestamp (40 s old) -> accepted", r({"exchFeedTime": "28-Oct-2026 12:16:20"})["valid"])
    check("exchTradeTime used when exchFeedTime is absent", r({"exchTradeTime": "28-Oct-2026 12:16:00"})["valid"])
    for label, q in (("no quote at all", None), ("quote without timestamp", {"ltp": 22610.0}),
                     ("empty timestamp", {"exchFeedTime": ""})):
        x = r(q)
        check(f"market hours, {label} -> rejected, reason says no timestamp", not x["valid"] and "no exchange timestamp" in x["reason"])
    for raw in ("t", "28-Oct-2026", "99-Abc-2026 12:00:00", "12:16:30", "not a time"):
        x = r({"exchFeedTime": raw})
        check(f"malformed timestamp {raw!r} -> rejected as malformed", not x["valid"] and "malformed" in x["reason"])
    x = r({"exchFeedTime": "28-Oct-2026 12:05:00"})
    check("12-minute-old timestamp -> rejected as stale", not x["valid"] and "stale" in x["reason"])
    x = r({"exchFeedTime": "28-Oct-2026 12:20:00"})
    check("timestamp 3 min in the future -> rejected", not x["valid"] and "future" in x["reason"])
    check(f"timestamp 30 s ahead (inside the {TP.MAX_CLOCK_SKEW_SEC:.0f}s clock-skew tolerance) -> accepted",
          r({"exchFeedTime": "28-Oct-2026 12:17:30"})["valid"])
    check("timestamp a day in the future -> rejected", not r({"exchFeedTime": "29-Oct-2026 12:16:40"})["valid"])
    check("UTC ISO timestamp converted to IST (06:46:40Z = 12:16:40 IST) -> accepted",
          r({"exchFeedTime": "2026-10-28T06:46:40+00:00"})["valid"])
    check("UTC ISO timestamp 06:30Z (= 12:00 IST, 17 min old) -> rejected as stale",
          "stale" in r({"exchFeedTime": "2026-10-28T06:30:00+00:00"})["reason"])
    check("tz-aware 'now' handled the same as naive IST", r(FRESH, now=pd.Timestamp("2026-10-28 06:47", tz="UTC"))["valid"])
    x = r(FRESH, now=None)
    check("market-hours entry without a clock time -> rejected", not x["valid"] and "clock" in x["reason"])
    off = dict(b, live=None, require_live=False)
    check("outside market hours / stock call: no quote needed (waits for next-session validation)", plan(**off, quote=None)["valid"])
    check("outside market hours: a malformed timestamp still rejects", not plan(**off, quote={"exchFeedTime": "junk"})["valid"])
    check("quote_time(): malformed -> None, Angel format parsed",
          TP.quote_time({"exchFeedTime": "junk"}) is None and TP.quote_time(FRESH) == pd.Timestamp("2026-10-28 12:16:40"))


def test_valid_both_sides_all_markets():
    for name, ex, px, atr, tick, lot in CASES:
        for side in ("BUY", "SELL"):
            s = 1 if side == "BUY" else -1
            p = plan(name=name, ex=ex, tf="1d", side=side, signal_close=px, atr=atr, stop_mult=1.5, target_r=3.0, tick=tick,
                     lot=lot, mult=lot, live=px + s * 0.1 * atr)
            on_tick = all(abs(round(v / tick) * tick - v) < 1e-6 for v in (p["entry"], p["sl"], p["target"]))
            sides = (p["sl"] < p["entry"] < p["target"]) if s > 0 else (p["sl"] > p["entry"] > p["target"])
            check(f"{name} {side}: valid, levels on the {tick} tick, SL / target on the correct side, R:R ≥ 1",
                  p["valid"] and on_tick and sides and p["rr"] >= 1.0 and p["risk_lot"] > 0)


def test_invalid_inputs():
    b = dict(name="NIFTY", ex="NFO", tf="3h", side="BUY", stop_mult=2.0, target_r=2.0, tick=0.05, live=22600.0)
    for label, kw in (("zero ATR", dict(signal_close=22600.0, atr=0.0)), ("negative ATR", dict(signal_close=22600.0, atr=-5.0)),
                      ("NaN ATR", dict(signal_close=22600.0, atr=float("nan"))), ("infinite ATR", dict(signal_close=22600.0, atr=math.inf)),
                      ("missing ATR", dict(signal_close=22600.0, atr=None)), ("NaN close", dict(signal_close=float("nan"), atr=60.0)),
                      ("missing close", dict(signal_close=None, atr=60.0))):
        check(f"rejected: {label}", not plan(**b, **kw)["valid"])
    check("rejected: no live price during market hours", not plan(**dict(b, live=None), signal_close=22600.0, atr=60.0)["valid"])
    check("rejected: live price NaN", not plan(**dict(b, live=float("nan")), signal_close=22600.0, atr=60.0)["valid"])
    check("no direction -> rejected", not plan(**dict(b, side=None), signal_close=22600.0, atr=60.0)["valid"])


def test_stale_quote_and_gaps():
    b = dict(name="NIFTY", ex="NFO", tf="3h", side="BUY", signal_close=22600.0, atr=60.0, stop_mult=2.0, target_r=2.0, tick=0.05)
    fresh = plan(**b, live=22610.0, quote={"exchFeedTime": "28-Oct-2026 12:16:30"})
    stale = plan(**b, live=22610.0, quote={"exchFeedTime": "28-Oct-2026 12:05:00"})
    check("fresh quote accepted, 12-minute-old quote rejected as stale", fresh["valid"] and not stale["valid"] and "stale" in stale["reason"])
    check("large favourable gap (price ran 1 ATR past the signal) -> rejected, no chasing",
          not plan(**b, live=22660.0)["valid"])
    check("large adverse gap (BUY but price fell 1 ATR below the signal) -> rejected",
          not plan(**b, live=22540.0)["valid"])
    s = plan(**dict(b, side="SELL"), live=22660.0)
    check("SELL whose price rose 1 ATR above the signal -> rejected", not s["valid"] and "against" in s["reason"])


def test_tick_and_wide_stop():
    p = plan(name="GOLD", ex="MCX", tf="1d", side="SELL", signal_close=143454.4, atr=903.7, stop_mult=1.5, target_r=3.0, tick=1.0, live=143454.4)
    check("GOLD tick ₹1: entry / SL / target are whole rupees and the message shows exactly those numbers",
          p["valid"] and p["entry"] == 143454.0 and float(p["sl"]).is_integer() and float(p["target"]).is_integer()
          and TP.fmt(p["sl"], 1.0) == f"{p['sl']:,.0f}")
    w = plan(name="SILVER", ex="MCX", tf="1d", side="SELL", signal_close=195151.0, atr=9000.0, stop_mult=1.5, target_r=3.0, tick=1.0, live=195151.0)
    check("extremely wide stop (6.9% away, max 4%) -> rejected, the stop is never moved to fit", not w["valid"] and "%" in w["reason"])
    t = plan(name="TCS", ex="NFO", tf="3h", side="BUY", signal_close=100.0, atr=0.02, stop_mult=2.0, target_r=2.0, tick=0.05, live=100.0)
    check("ATR smaller than one tick: risk rounds to a valid tick distance or the plan is rejected – never zero risk",
          (not t["valid"]) or t["risk_unit"] > 0)


def test_option_plan_and_filter():
    o = TP.option_plan(premium=7242.0, sl_pct=0.35, tg_pct=0.80, tick=0.5, lot=30)
    check("option levels on the PREMIUM: 7242 -> SL 4707 / target 13035.5 (tick 0.5), separate from the futures stop",
          o["valid"] and o["sl"] == 4707.0 and o["target"] == 13035.5)
    check("option premium missing -> no option call", not TP.option_plan(premium=None, sl_pct=0.35, tg_pct=0.8)["valid"])

    class Wide:
        def quotes(self, d):
            return {"T": {"ltp": 100.0, "tradeVolume": 5, "depth": {"buy": [{"price": 95.0}], "sell": [{"price": 105.0}]}}}
    r = OF.check(Wide(), "NFO", "TCS", dict(token="T", K=3450.0, typ="CE", expiry=pd.Timestamp("2026-11-25")), 3450.0, None, NOW)
    check("option spread 10% -> no option call", not r[0] and "spread" in r[3])


def test_support_resistance_warning():
    p = plan(name="NIFTY", ex="NFO", tf="3h", side="BUY", signal_close=22600.0, atr=60.0, stop_mult=2.0, target_r=2.0, tick=0.05,
             live=22600.0, levels=dict(resistance=[(22650.0, "swing high")], support=[]))
    check("resistance well before the target is flagged (shown in WHY, call not changed)", p["valid"] and "22,650" in (p.get("warn") or ""))


def _nifty_hourly(days=260):
    d0 = pd.bdate_range(end="2026-10-27", periods=days)
    rows, px = [], 20000.0
    rng = np.random.default_rng(3)
    for d in d0:
        for h in range(7):
            o = px; px = px * (1 + 0.0004 + rng.normal(0, 0.0008)); hi = max(o, px) * 1.0006; lo = min(o, px) * 0.9994
            rows.append((d + pd.Timedelta(hours=9, minutes=15) + pd.Timedelta(hours=h), o, hi, lo, px, 1000.0))
    last = pd.Timestamp("2026-10-28")
    hh = max(r[2] for r in rows[-60:])
    for h, (c, v) in enumerate([(hh * 1.004, 3000.0), (hh * 1.008, 3500.0), (hh * 1.012, 4000.0)]):
        rows.append((last + pd.Timedelta(hours=9, minutes=15) + pd.Timedelta(hours=h), c * 0.999, c * 1.001, c * 0.998, c, v))
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


def test_end_to_end_consistency_duplicates_restart():
    h = _nifty_hourly()
    st = E.new_state(); st["day"] = dict(date="2026-10-28", alerts=0, watches=0, startup_sent=True, eod_sent=False, outcomes=[])
    c = dict(symbol="NIFTY25NOV26FUT", token="1", expiry="2026-11-25", lot=75, tick=0.05)
    live = float(h["close"].iloc[-1]) + 3.0
    q = {"ltp": live, "exchFeedTime": "28-Oct-2026 12:16:50"}
    msgs, info = [], {}
    E._breakouts(st, msgs, info, "NIFTY", "NFO", c, h, None, pd.Timestamp("2026-10-28 12:17"), None, q)
    a = [p for p in st["bo_active"] if p["tf"] == "3h"]
    check("3h breakout fixture produces exactly one NIFTY BUY call", len(a) == 1 and any("BUY  NIFTY FUT" in m for m in msgs))
    p = a[0]; L = [r for r in st["ledger"] if r["key"] == p["key"]][0]
    card = [m for m in msgs if "BUY  NIFTY FUT" in m][0]
    check("message, open-call tracker and report ledger show IDENTICAL entry / SL / target",
          (p["entry"], p["stop"], p["target"]) == (L["entry"], L["sl"], L["target"])
          and f"Entry   : {TP.fmt(p['entry'], 0.05)}" in card and f"SL      : {TP.fmt(p['stop'], 0.05)}" in card
          and f"Target  : {TP.fmt(p['target'], 0.05)}" in card)
    n = len(msgs)
    E._breakouts(st, msgs, info, "NIFTY", "NFO", c, h, None, pd.Timestamp("2026-10-28 12:32"), None, q)
    check("same candle 15 min later -> no duplicate call", len(msgs) == n and len(st["bo_active"]) == len(a) + 0)
    st2 = json.loads(json.dumps(st, default=str))                    # process restart: state saved and restored
    bar = pd.DataFrame(dict(time=[pd.Timestamp("2026-10-28 12:45")], open=[p["entry"]], high=[p["target"] + 1], low=[p["entry"] - 1],
                            close=[p["target"]], volume=[1.0]))
    m2 = []
    BO.manage(st2, m2, "NIFTY", "3h", None, bar, pd.Timestamp("2026-10-28 13:02"))
    check("after a restart the restored call hits its TARGET at the tracked price and the ledger closes at it",
          any("TARGET HIT" in x and TP.fmt(p["target"], 0.05) in x for x in m2)
          and [r for r in st2["ledger"] if r["key"] == p["key"]][0]["exit"] == p["target"])
    c2 = dict(c); st3 = E.new_state(); st3["day"] = dict(st["day"])
    m3 = []
    E._breakouts(st3, m3, {}, "NIFTY", "NFO", c2, h, None, pd.Timestamp("2026-10-28 12:17"), None,
                 {"ltp": live, "exchFeedTime": "28-Oct-2026 11:40:00"})
    check("same signal with a 37-minute-old quote -> no call", not st3["bo_active"] or all(x["tf"] != "3h" for x in st3["bo_active"]))
    m4 = []; st4 = E.new_state(); st4["day"] = dict(st["day"])
    E._breakouts(st4, m4, {}, "NIFTY", "NFO", c2, h, None, pd.Timestamp("2026-10-28 12:17"), None, {"ltp": live - 400, "exchFeedTime": "28-Oct-2026 12:16:50"})
    check("same signal but live price already far below (adverse gap) -> no call", not any(x["tf"] == "3h" for x in st4["bo_active"]))


def test_missing_volume_and_oi():
    d = pd.DataFrame(dict(time=pd.date_range("2026-01-01", periods=260, freq="D"), open=100.0, high=101.0, low=99.0, close=100.0,
                          volume=np.nan))
    d.loc[d.index[-1], ["close", "high"]] = [110.0, 111.0]
    check("missing volume -> no breakout call (volume is required, not assumed)", BO.evaluate(d)["side"] is None)
    from alerts import stocks as STK
    d2 = d.assign(volume=1000.0, oi=np.nan)
    d2.loc[d2.index[-1], "volume"] = 5000.0
    check("stock: missing OI -> no OI-breakout call", STK.evaluate(d2)["side"] is None)


def test_stock_next_open_gap():
    from alerts import stocks as STK
    p = dict(name="TCS", side="BUY", entry=3450.0, stop=3390.0, target=None, risk=60.0, atr=30.0, tick=0.1, last_candle="2026-10-27 09:15:00")
    nx = pd.Timestamp("2026-10-28 09:17")
    check("stock call: same evening -> waits for the next open", STK.validate_pending(p, 3450.0, pd.Timestamp("2026-10-27 15:40"))[0] == "wait")
    check("stock call: next open inside the zone -> ACTIVE", STK.validate_pending(p, 3455.0, nx)[0] == "active")
    check("stock call: big gap UP (+1 ATR) -> CANCELLED (no chasing)", STK.validate_pending(p, 3482.0, nx)[0] == "cancel")
    check("stock call: gap DOWN through the stop -> CANCELLED", STK.validate_pending(p, 3380.0, nx)[0] == "cancel")
    for label, q in (("no timestamp", {"ltp": 3455.0}), ("malformed timestamp", {"exchFeedTime": "x"}),
                     ("stale (yesterday's) quote", {"exchFeedTime": "27-Oct-2026 15:29:59"}),
                     ("future timestamp", {"exchFeedTime": "28-Oct-2026 09:30:00"})):
        v, note = STK.validate_pending(p, 3482.0, nx, quote=q)
        check(f"stock pending + {label} -> keeps WAITING (not activated / cancelled), reason given", v == "wait" and bool(note))
    check("stock pending + fresh quote inside the zone -> ACTIVE",
          STK.validate_pending(p, 3455.0, nx, quote={"exchFeedTime": "28-Oct-2026 09:16:58"})[0] == "active")


def test_telegram_failure_queues():
    from alerts import run as R
    tmp = Path(tempfile.mkdtemp())
    R.SD, R.OUTBOX, R.PENDING = tmp, tmp / "outbox.json", tmp / "pending.json"
    R.OUTBOX.write_text(json.dumps(dict(messages=["m1", "m2"])))
    import crude.run as CR
    orig = CR.telegram
    CR.telegram = lambda m: (False, "HTTP 429")
    os.environ["ALERTS_TELEGRAM"] = "1"
    try:
        R.GAP_SEC = 0
        R.flush()
    finally:
        CR.telegram = orig
    check("Telegram failure -> messages kept in pending.json for the next run (not lost)",
          json.loads(R.PENDING.read_text()) == ["m1", "m2"])
    import notify
    notify.PENDING = tmp / "tg_pending.json"
    notify._queue("sell call")
    check("option-sell message that failed is queued for re-sending", json.loads(notify.PENDING.read_text()) == ["sell call"])


if __name__ == "__main__":
    for t in (test_valid_both_sides_all_markets, test_invalid_inputs, test_quote_timestamps, test_stale_quote_and_gaps, test_tick_and_wide_stop,
              test_option_plan_and_filter, test_support_resistance_warning, test_end_to_end_consistency_duplicates_restart,
              test_missing_volume_and_oi, test_stock_next_open_gap, test_telegram_failure_queues):
        t()
    print(f"\nALL {len(OK)} TRADE-PLAN CHECKS PASSED")
