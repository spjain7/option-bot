"""Stock-futures data quality (STOCK-DQ-001): corporate actions, OI validation, rollover, price continuity, shadow log.
Deterministic fixtures, no network, no orders.   python -m alerts.tests.test_dataquality"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from alerts import dataquality as DQ, stocks as STK, engine as E  # noqa: E402
from crude import indicators as I  # noqa: E402
from crude.tests import fake as F  # noqa: E402

OK = []


def check(name, cond):
    assert cond, name
    OK.append(name)
    print("✅", name)


# gaps measured in the stored Angel history (STOCK-OI-BUY-001 data audit) – the verified factors must explain them
OBSERVED = {("DRREDDY", "2024-10-28"): 0.201, ("BPCL", "2024-06-21"): 0.503, ("BSE", "2025-05-23"): 0.333, ("MCX", "2026-01-02"): 0.201,
            ("HDFCAMC", "2025-11-26"): 0.505, ("CAMS", "2025-12-05"): 0.2, ("NESTLEIND", "2024-01-05"): 0.1,
            ("NESTLEIND", "2025-08-08"): 0.499, ("PIDILITIND", "2025-09-23"): 0.503, ("RELIANCE", "2024-10-28"): 0.502,
            ("SHRIRAMFIN", "2025-01-10"): 0.2, ("COFORGE", "2025-06-04"): 0.202, ("BEL", "2022-09-15"): 0.335,
            ("TATASTEEL", "2022-07-28"): 0.102, ("KOTAKBANK", "2026-01-14"): 0.2, ("LICI", "2026-05-29"): 0.504,
            ("HINDPETRO", "2024-06-21"): 0.662, ("HDFCBANK", "2025-08-26"): 0.497, ("PATANJALI", "2025-09-11"): 0.334,
            ("SIEMENS", "2025-04-07"): 0.541, ("BAJFINANCE", "2025-06-16"): 0.102, ("TRENT", "2026-06-04"): 0.664,
            ("NAUKRI", "2025-05-07"): 0.199, ("VEDL", "2026-04-30"): 0.369, ("PERSISTENT", "2024-03-28"): 0.501,
            ("BAJAJFINSV", "2022-09-13"): 0.101, ("HAL", "2023-09-28"): 0.497, ("ANGELONE", "2026-02-26"): 0.1}


def series(ex, ratio, n_before=260, n_after=60, px=1000.0, seed=0, oi0=1e6):
    """Daily futures bars with a corporate-action gap of `ratio` at the ex-date (unadjusted, like Angel's history)."""
    rng = np.random.default_rng(seed)
    days = list(pd.bdate_range(end=pd.Timestamp(ex) - pd.Timedelta(days=1), periods=n_before)) + \
        list(pd.bdate_range(start=ex, periods=n_after))
    c = px * np.cumprod(1 + rng.normal(0.0005, 0.01, len(days)))
    k = n_before
    c[k:] *= ratio
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.002, len(days)))
    o[k] = c[k - 1] * ratio * 1.003                         # small genuine move on the ex-date on top of the gap
    hi, lo = np.maximum(o, c) * 1.004, np.minimum(o, c) * 0.996
    vol = np.full(len(days), 1000.0); vol[k:] /= ratio
    oi = np.full(len(days), oi0); oi[k:] /= ratio
    d = pd.DataFrame(dict(time=pd.to_datetime(days) + pd.Timedelta(hours=9, minutes=15), open=o, high=hi, low=lo, close=c, volume=vol, oi=oi))
    return d


def test_registry():
    reg = DQ.load_registry()
    ev = [e for v in reg.values() for e in v]
    check("registry holds the 28 identified corporate actions, each with ex-date, ratio text and a source link",
          len(ev) == 28 and all(e.get("source", "").startswith("https://") and e.get("ratio") for e in ev))
    keys = {(e["symbol"], e["ex_date"]) for e in ev}
    check("registry covers exactly the 28 gaps found in the data audit", keys == set(OBSERVED))
    dem = [e for e in ev if e["type"] == "demerger"]
    check("2 demergers (SIEMENS, VEDL) carry NO price factor – nothing invented",
          sorted(e["symbol"] for e in dem) == ["SIEMENS", "VEDL"] and all(e["price_factor"] is None for e in dem))
    bad = [(e["symbol"], e["ex_date"]) for e in ev if e["price_factor"] is not None
           and abs(OBSERVED[(e["symbol"], e["ex_date"])] / e["price_factor"] - 1) > DQ.GAP_TOL]
    check("all 26 verified split / bonus factors explain the observed price gap (within the ex-date move tolerance)", not bad)


def test_each_corporate_action():
    reg = DQ.load_registry()
    for (sym, exd), r in sorted(OBSERVED.items()):
        e = [x for x in reg[sym] if x["ex_date"] == exd][0]
        d = series(exd, r, seed=hash(sym) % 1000)
        h = d.copy()
        out, h2, info = DQ.reconcile(sym, d, h, registry={sym: [e]})
        ex = pd.Timestamp(exd)
        if e["price_factor"] is None:
            check(f"{sym} {exd} demerger: pre-event history dropped, call suppressed until enough new history",
                  info["truncated"] == ex and out["time"].dt.normalize().min() == ex and not info["holds"]
                  and STK.evaluate(out)["why"] == "not enough daily history")
            continue
        i = int(np.flatnonzero(out["time"].dt.normalize().values == np.datetime64(ex))[0])
        jump = out["open"].iat[i] / out["close"].iat[i - 1]
        e200 = I.ema(out["close"], 200)
        check(f"{sym} {exd} ×{e['price_factor']:g}: adjusted, price continuous at the ex-date (×{jump:.3f}), current price "
              f"unchanged, EMA200 consistent with today's price, OI/volume rescaled",
              info["applied"] == [(ex, e["price_factor"])] and not info["holds"] and abs(jump - 1) < DQ.GAP_TOL
              and out["close"].iat[-1] == d["close"].iat[-1] and abs(e200.iat[-1] / out["close"].iat[-1] - 1) < 0.25
              and abs(out["oi"].iat[i - 1] / out["oi"].iat[i] - 1) < 0.03 and abs(out["volume"].iat[i - 1] / out["volume"].iat[i] - 1) < 0.03
              and np.allclose(h2["close"].values, out["close"].values))
    d = series("2025-06-16", 0.102)
    raw_e = I.ema(d["close"], 200).iat[-1] / d["close"].iat[-1]
    check(f"without adjustment the same history puts EMA200 at {raw_e:.1f}× the current price (the defect being fixed)", raw_e > 3)


def test_holds_and_genuine_moves():
    d = series("2025-03-03", 0.5)
    _, _, info = DQ.reconcile("XYZ", d, registry={})
    check("large gap with NO verified event -> HOLD (signals suppressed, reason logged)",
          len(info["holds"]) == 1 and "unexplained price gap ×0.50" in info["holds"][0])
    e = dict(symbol="XYZ", ex_date="2025-03-03", ex=pd.Timestamp("2025-03-03"), type="split", price_factor=0.2)
    _, _, info = DQ.reconcile("XYZ", d, registry={"XYZ": [e]})
    check("verified factor that does not match the data gap (×0.2 vs ×0.5) -> HOLD, never forced",
          any("does not match" in x for x in info["holds"]) and not info["applied"])
    adj = series("2025-03-03", 1.0)
    e2 = dict(e, price_factor=0.5)
    out, _, info = DQ.reconcile("XYZ", adj, registry={"XYZ": [e2]})
    check("history already adjusted by the data vendor -> factor NOT applied twice, no hold",
          not info["applied"] and not info["holds"] and info["skipped"] and out["close"].iat[0] == adj["close"].iat[0])
    crash = series("2025-03-03", 0.82)
    _, _, info = DQ.reconcile("XYZ", crash, registry={})
    check("genuine −18 % gap (inside the normal range) -> no hold, no adjustment", not info["holds"] and not info["applied"])
    big = series("2025-03-03", 0.65)
    mk = dict(symbol="XYZ", ex_date="2025-03-03", ex=pd.Timestamp("2025-03-03"), type="market", price_factor=None)
    _, _, info = DQ.reconcile("XYZ", big, registry={"XYZ": [mk]})
    check("a verified genuine −35 % move (type 'market') releases the hold without any price change",
          not info["holds"] and not info["applied"] and info["truncated"] is None)


def test_oi_validation():
    c = DQ.oi_check
    check("normal OI change +3 % is valid", abs(c(1030, 1000, 990)[0] - 0.03) < 1e-12 and c(1030, 1000, 990)[1] is None)
    for lab, args, word in (("missing today", (None, 1000, 990), "missing"), ("NaN previous", (1000, float("nan"), 990), "missing"),
                            ("infinite", (float("inf"), 1000, 990), "not finite"), ("negative", (-5, 1000, 990), "negative"),
                            ("zero baseline", (1000, 0, 990), "zero baseline"), ("zero today", (0, 1000, 990), "zero today"),
                            ("text value", ("abc", 1000, 990), "missing")):
        doi, why, _ = c(*args)
        check(f"OI {lab} -> rejected ({why})", doi is None and word in why)
    doi, why, _ = c(1045, 10, 1030)
    check("bad tick: previous day 10 (−99 %) and today back at the old level -> corrupt baseline, rejected (no +10,350 % 'confirmation')",
          doi is None and "corrupt" in why)
    doi, why, _ = c(1045, 74000, 1030)
    check("bad tick upwards (×72 then back) -> corrupt baseline, rejected", doi is None and "corrupt" in why)
    doi, why, fl = c(2500, 1000, 980)
    check("genuine +150 % OI jump (no reversal evidence) -> ACCEPTED, only flagged as extreme",
          abs(doi - 1.5) < 1e-12 and why is None and any("extreme" in f for f in fl))
    doi, why, fl = c(1400, 1000, 400)
    check("genuine sustained build-up (×2.5 then +40 %) is not mistaken for a bad tick", abs(doi - 0.4) < 1e-12 and why is None)
    doi, why, fl = c(1030, 1000, 990, quote_oi=1200)
    check("daily OI vs live quote OI differs 14 % -> flagged, not rejected", why is None and any("live quote" in f for f in fl))
    doi, why, _ = c(1500, 1000, 990, ca_day=True)
    check("corporate-action day -> OI change rejected", doi is None and "corporate-action" in why)


def _breakout(oi_last, oi_prev=1.0e6, oi_prev2=1.0e6, day="2026-10-15"):
    days = list(pd.bdate_range("2025-09-01", day))
    rows, px = [], 1000.0
    for dd in days:
        px *= 1.0021
        rows.append(dict(time=dd + pd.Timedelta(hours=9, minutes=15), open=px, high=px * 1.002, low=px * 0.998, close=px, volume=1000.0))
    d = pd.DataFrame(rows)
    d.loc[d.index[-1], ["close", "high"]] = [px * 1.06, px * 1.061]
    d.loc[d.index[-1], "volume"] = 4000.0
    d["oi"] = 1.0e6
    d.loc[d.index[-3], "oi"] = oi_prev2
    d.loc[d.index[-2], "oi"] = oi_prev
    d.loc[d.index[-1], "oi"] = oi_last
    return d


def test_signal_rule_unchanged():
    check("live thresholds unchanged (20-day high, volume 1.5×, OI ≥ +2 %, EMA200, stop 2 ATR, trail 3 ATR, 40 days)",
          STK.CFG == dict(N=20, vol_x=1.5, oi_up=0.02, ema=200, stop_atr=2.0, trail_atr=3.0, max_days=40))
    d = DQ.validate_daily_oi(_breakout(1.02e6))
    check("valid OI exactly +2 % -> BUY (threshold unchanged)", STK.evaluate(d)["side"] == "BUY")
    raw = _breakout(1.02e6)
    check("same result as the old (unvalidated) path when the OI data is clean", STK.evaluate(raw)["side"] == "BUY")
    d = DQ.validate_daily_oi(_breakout(1.03e6, oi_prev=1.0e4, oi_prev2=1.0e6))
    s = STK.evaluate(d)
    check("corrupt OI baseline -> no BUY; logged as a blocked breakout with the reason",
          s["side"] is None and s.get("oi_blocked") and "corrupt" in s["why"])
    raw = _breakout(1.03e6, oi_prev=1.0e4, oi_prev2=1.0e6)
    check("…the old path would have confirmed it with a +10,200 % OI 'jump' (the defect)", STK.evaluate(raw)["side"] == "BUY")
    d = DQ.validate_daily_oi(_breakout(float("nan")))
    check("missing OI today -> no BUY, reason 'missing'", STK.evaluate(d)["side"] is None and "missing" in STK.evaluate(d)["why"])
    d = DQ.validate_daily_oi(_breakout(1.02e6, day="2026-10-26"))
    s = STK.evaluate(d)
    check("rollover window: valid OI but inside the window -> no signal (exclusion kept)", s["side"] is None and "rollover" in s["why"])


def test_shadow_log():
    st = {}
    sig = dict(side="BUY", candle="2026-10-15 09:15:00", close=1060.0, hh=1050.0, atr=10.0, doi=0.03)
    plan = dict(entry=1060.0, sl=1040.0, risk_unit=20.0)
    r = DQ.shadow_add(st, key="A|1dSTK|2026-10-15 09:15:00", name="A", sig=sig, plan=plan, lot=500, now=pd.Timestamp("2026-10-15 15:40"))
    r2 = DQ.shadow_add(st, key="B|1dSTK|2026-10-15 09:15:00", name="B", sig=dict(sig, doi=0.06), plan=plan, lot=500,
                       now=pd.Timestamp("2026-10-15 15:40"), oi_flags="no live quote OI to cross-check")
    check("shadow label: OI +3 % -> inside +2–4 %, +6 % -> outside; extension and estimated cost recorded",
          r["band_2_4"] and not r2["band_2_4"] and r["ext"] == 1.0 and r["cost_est"] > 0 and r2["flags"] == ["no live quote OI to cross-check"])
    DQ.shadow_event(st, r["key"], pd.Timestamp("2026-10-16 09:17"), status="active", entry_fill=1062.0, entry_time="2026-10-16 09:17")
    DQ.shadow_event(st, r["key"], pd.Timestamp("2026-10-20 15:40"), status="closed", exit_price=1102.0, exit_time="2026-10-20 15:40",
                    exit_reason="expiry/time exit")
    check("closed shadow trade: gross +2.0R from the recorded entry fill, net R after costs lower, events time-stamped",
          r["r_gross"] == 2.0 and r["r_net"] < 2.0 and len(r["events"]) == 2 and r["events"][0]["time"] == "2026-10-16 09:17:00")
    DQ.shadow_event(st, r2["key"], pd.Timestamp("2026-10-20 15:40"), status="closed", exit_price=1000.0, exit_time="x")
    check("no recorded entry fill -> no R computed (never invented)", r2.get("r_net") is None)
    sm = DQ.shadow_summary(st)
    check("summary compares baseline and the +2–4 % label on IDENTICAL signals", sm["baseline"]["n"] == 1 and sm["OI +2-4% label"]["n"] == 1)


def test_open_call_rescale():
    reg = {"DRREDDY": [dict(symbol="DRREDDY", ex_date="2024-10-28", ex=pd.Timestamp("2024-10-28"), type="split", price_factor=0.2)],
           "VEDL": [dict(symbol="VEDL", ex_date="2026-04-30", ex=pd.Timestamp("2026-04-30"), type="demerger", price_factor=None)]}
    st = dict(active=[dict(name="DRREDDY", side="BUY", entry=6500.0, stop=6300.0, best=6550.0, risk=200.0, target=None, atr=100.0,
                           key="DRREDDY|1dSTK|2024-10-22 09:15:00", token="1"),
                      dict(name="VEDL", side="BUY", entry=500.0, stop=480.0, best=500.0, risk=20.0, key="VEDL|1dSTK|2026-04-27 09:15:00", token="2")])
    state = dict(ledger=[dict(key="VEDL|1dSTK|2026-04-27 09:15:00", status="OPEN", entry=500.0)])
    msgs = []
    STK.rescale_for_corporate_actions(st, state, msgs, pd.Timestamp("2024-10-28 09:20"), registry=reg)
    p = st["active"][0]
    check("open call across a 1:5 split: entry / SL rescaled once (6500 -> 1300, 6300 -> 1260) before any stop check",
          p["entry"] == 1300.0 and p["stop"] == 1260.0 and p["risk"] == 40.0 and any("rescaled" in m for m in msgs))
    STK.rescale_for_corporate_actions(st, state, msgs, pd.Timestamp("2024-10-29 09:20"), registry=reg)
    check("…and never twice", st["active"][0]["entry"] == 1300.0)
    STK.rescale_for_corporate_actions(st, state, msgs, pd.Timestamp("2026-04-30 09:20"), registry=reg)
    check("open call across a demerger (no official factor): tracking stopped with a message, ledger closed without an invented exit",
          all(x["name"] != "VEDL" for x in st["active"]) and state["ledger"][0]["exit"] is None and any("demerger" in m for m in msgs))


def test_scan_hold_end_to_end():
    m = pd.DataFrame([dict(name="TCS", exch_seg="NFO", instrumenttype="FUTSTK", symbol="TCS27OCT26FUT", token="1", lotsize=175,
                           expiry_dt=pd.Timestamp("2026-10-27"))])
    days = list(pd.bdate_range("2025-09-01", "2026-10-15"))
    rows, px = [], 1000.0
    for d in days:
        for hh, mm in ((9, 15), (10, 15), (11, 15), (12, 15), (13, 15), (14, 15), (15, 15)):
            px *= 1.0003
            rows.append(dict(time=d + pd.Timedelta(hours=hh, minutes=mm), open=px, high=px * 1.002, low=px * 0.998, close=px, volume=1000.0))
    h = pd.DataFrame(rows)
    last = h["time"].dt.normalize() == pd.Timestamp("2026-10-15")
    h.loc[last, ["close", "high"]] = [px * 1.06, px * 1.061]
    h.loc[last, "volume"] = 4000.0
    oi = pd.DataFrame(dict(time=[d for d in days[-60:]], oi=[1e6] * 59 + [1.05e6]))

    class Api(F.FakeAngel):
        def __init__(self, oi_df, **k):
            super().__init__(**k); self.oi_df = oi_df
        def oi_history(self, ex, tok, iv, frm, to):
            return self.oi_df
    now = pd.Timestamp("2026-10-15 15:32")
    st = E.new_state(); st["day"] = dict(date="2026-10-15", alerts=0, watches=0, startup_sent=True, eod_sent=False, outcomes=[])
    msgs, rep = [], dict(errors=[])
    STK.scan(Api(oi, series={("1", "ONE_HOUR"): h}, now=now), m, now, st, msgs, rep, sys.modules["alerts.engine"])
    sh = st["stk"].get("shadow", [])
    check("clean data: the same BUY call as before + one shadow record (label only, OI +5 % -> outside +2–4 %)",
          any("BUY  TCS FUT" in x for x in msgs) and len(sh) == 1 and sh[0]["band_2_4"] is False and sh[0]["status"] == "pending")
    h2 = h.copy()
    cut = h2["time"] < pd.Timestamp("2026-06-01")
    h2.loc[cut, ["open", "high", "low", "close"]] *= 2.0                # an unadjusted 1:1 bonus nobody verified
    st2 = E.new_state(); st2["day"] = dict(st["day"])
    m2, rep2 = [], dict(errors=[])
    STK.scan(Api(oi, series={("1", "ONE_HOUR"): h2}, now=now), m, now, st2, m2, rep2, sys.modules["alerts.engine"])
    check("unverified ×0.5 gap in the history -> NO call, data hold logged with the reason",
          not any("TCS FUT" in x for x in m2) and any("data hold" in x and "unexplained" in x for x in rep2.get("stock_skips", []))
          and "TCS" in st2["stk"]["dq_holds"])
    oi3 = oi.copy(); oi3.loc[oi3.index[-2], "oi"] = 1.0e4
    st3 = E.new_state(); st3["day"] = dict(st["day"])
    m3, rep3 = [], dict(errors=[])
    STK.scan(Api(oi3.assign(oi=list(oi3["oi"][:-1]) + [1.03e6]), series={("1", "ONE_HOUR"): h}, now=now), m, now, st3, m3, rep3,
             sys.modules["alerts.engine"])
    check("corrupt OI baseline -> no call; 'breakout not confirmed – corrupt OI' logged",
          not any("TCS FUT" in x for x in m3) and any("corrupt" in x for x in rep3.get("stock_skips", [])))


if __name__ == "__main__":
    for t in (test_registry, test_each_corporate_action, test_holds_and_genuine_moves, test_oi_validation, test_signal_rule_unchanged,
              test_shadow_log, test_open_call_rescale, test_scan_hold_end_to_end):
        t()
    print(f"\nALL {len(OK)} DATA-QUALITY CHECKS PASSED")
