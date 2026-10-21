"""Integrity tests for the research engines (synthetic data). Run: python -m research.tests.test_research"""
import numpy as np
import pandas as pd
from research import continuous as CO, engine_daily as ED, engine_hourly as EH, portfolio as PF
from research.instruments import round_trip_cost_rs, cost_points

OK = []


def check(name, cond):
    assert cond, name
    OK.append(name); print("✅", name)


def synth(n=600, seed=1, drift=0.0008):
    rng = np.random.default_rng(seed)
    c = 20000 * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.002, n))
    h = np.maximum(o, c) * (1 + abs(rng.normal(0, 0.004, n))); l = np.minimum(o, c) * (1 - abs(rng.normal(0, 0.004, n)))
    d = pd.DataFrame(dict(time=pd.bdate_range("2015-01-01", periods=n), open=o, high=h, low=l, close=c,
                          volume=rng.integers(1000, 3000, n).astype(float), oi=rng.integers(1e5, 2e5, n).astype(float)))
    for k in ("open", "high", "low", "close"):
        d["raw_" + k] = d[k]
    d["offset"], d["roll"], d["contract"] = 0.0, False, "X"
    return d


def test_no_lookahead():
    d = ED.add_indicators(synth())
    s1 = ED.signals(d, {**ED.BASE})
    d2 = synth(); d2.loc[400:, ["open", "high", "low", "close", "raw_close"]] *= 1.5     # change the future only
    s2 = ED.signals(ED.add_indicators(d2), {**ED.BASE})
    check("daily signals unchanged when only future bars change", (s1[:400] == s2[:400]).all())
    h = synth(800, 2).assign(time=pd.date_range("2026-01-01 09:00", periods=800, freq="h"))
    hh = EH.indicators(h, EH.BASE); a1 = EH.signals(hh, EH.BASE)
    h2 = h.copy(); h2.loc[600:, ["open", "high", "low", "close"]] *= 0.7
    a2 = EH.signals(EH.indicators(h2, EH.BASE), EH.BASE)
    check("hourly signals unchanged when only future bars change", (a1[:600] == a2[:600]).all())


def test_gap_and_fills():
    d = synth(400, 3)
    d = ED.add_indicators(d)
    t = ED.run("NIFTY", d, {"trend": False, "entry": 20, "exit": 10})
    check("trades produced", len(t) > 5)
    check("entry is next bar after signal", (pd.to_datetime(t.entry_time) > pd.to_datetime(t.signal_time)).all())
    g = t[t.exit_reason == "gap_stop"]
    for _, x in t[t.exit_reason == "stop"].iterrows():
        assert abs(x.exit_px - x.stop_px) < 1e-6
    check("stop exits filled exactly at stop", True)
    check("net R below gross R (costs applied)", (t.net_R < t.gross_R).all())
    # forced gap: open far below stop
    e = synth(300, 4, drift=0.003); e = ED.add_indicators(e)
    t0 = ED.run("NIFTY", e, {"trend": False, "entry": 20, "exit": 10, "sides": (1,)})
    x = t0.iloc[0]; k = e.index[e.time == x.entry_time][0] + 1
    e2 = e.copy(); e2.loc[k, ["open", "high", "low", "close"]] = x.stop_px * 0.9
    e2.loc[k, "raw_close"] = x.stop_px * 0.9
    t1 = ED.run("NIFTY", e2, {"trend": False, "entry": 20, "exit": 10, "sides": (1,)})
    y = t1.iloc[0]
    check("gap through stop fills at the open (worse than stop)", y.exit_reason == "gap_stop" and y.exit_px < y.stop_px)


def test_roll_equivalence():
    """Two contracts with a roll: adjusted-series P&L == sum of real contract legs."""
    days = pd.bdate_range("2020-01-01", periods=40)
    rows = []
    for i, d in enumerate(days):
        for e, base in ((days[20], 100.0), (days[39], 110.0)):
            if d > e:
                continue                                              # expired contracts stop trading
            p = base + i
            rows.append(dict(date=d, symbol="NIFTY", expiry=e, open=p, high=p + 1, low=p - 1, close=p, settle=p,
                             contracts=10, oi=100, chg_oi=0))
    c = CO.build_nse("NIFTY", pd.DataFrame(rows), roll_days=3)
    rd = c[c.roll].iloc[0]
    check("roll happens 3 trading days before expiry", rd.time == days[17])
    # long from day 5 open to day 30 open
    a = c.iloc[5]; b = c.iloc[30]
    adj_pnl = b.open - a.open
    leg1 = c.loc[c.time == days[17], "raw_close"].iloc[0] - a.raw_open           # old contract: entry -> roll close
    new_close_roll = 110.0 + 17
    leg2 = b.raw_open - new_close_roll                                          # new contract: roll close -> exit
    check("adjusted P&L equals contract legs", abs(adj_pnl - (leg1 + leg2)) < 1e-9)


def test_relabel_and_weekly():
    """Exchange re-labels an expiry (29th -> 28th) and lists illiquid weekly futures: keep one monthly series."""
    days = pd.bdate_range("2023-05-01", "2023-07-31")
    rows = []
    for d in days:
        jun = pd.Timestamp("2023-06-29") if d < pd.Timestamp("2023-06-20") else pd.Timestamp("2023-06-28")
        for e in (pd.Timestamp("2023-05-25"), jun, pd.Timestamp("2023-07-27"), pd.Timestamp("2023-06-08")):
            if d <= e:
                rows.append(dict(date=d, symbol="X", expiry=e, open=100, high=101, low=99, close=100, settle=100,
                                 contracts=5, oi=10, chg_oi=0))
    c = CO.build_nse("X", pd.DataFrame(rows), roll_days=3)
    upto = days[days <= pd.Timestamp("2023-07-24")]                  # last contract rolls 3 days before its expiry
    check("no trading days lost to a re-labelled expiry", set(upto) <= set(c.time))
    check("weekly future ignored, one roll per month", c.roll.sum() == 2)


def test_costs():
    rt = round_trip_cost_rs("NIFTY", 25000, 25000)
    check("NIFTY round trip cost between ₹700 and ₹1,500 per lot", 700 < rt < 1500)
    check("2x cost stress doubles cost", abs(cost_points("GOLD", 78000, 2.0) - 2 * cost_points("GOLD", 78000)) < 1e-9)
    s = round_trip_cost_rs("NIFTY", 25000, 24000, side=-1); l = round_trip_cost_rs("NIFTY", 25000, 24000, side=1)
    check("sell-side tax applied to the correct leg", s > l)


def test_portfolio():
    t = pd.DataFrame([dict(instrument="NIFTY", entry_time="2020-01-01", exit_time="2020-02-01", R_pts=600, net_pts=300,
                           net_R=0.5, gross_R=0.55),
                      dict(instrument="NIFTY", entry_time="2020-01-10", exit_time="2020-01-20", R_pts=600, net_pts=-600,
                           net_R=-1, gross_R=-0.95),
                      dict(instrument="GOLD", entry_time="2020-01-05", exit_time="2020-01-25", R_pts=1500, net_pts=1500,
                           net_R=1, gross_R=1.02)])
    p, s = PF.simulate(t, capital=2_500_000, risk_pct=0.02)
    check("portfolio skips a second position in the same instrument", s["skip_held"] == 1)
    check("GOLD sized with mini lots when a main lot exceeds the budget", p.loc[p.instrument == "GOLD", "lot_mult"].iloc[0] == 10)


if __name__ == "__main__":
    for f in (test_no_lookahead, test_gap_and_fills, test_roll_equivalence, test_relabel_and_weekly, test_costs, test_portfolio):
        f()
    print(f"\nALL {len(OK)} RESEARCH CHECKS PASSED")
