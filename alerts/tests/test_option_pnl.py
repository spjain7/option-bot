"""Option-buy P&L: premium-based tracking, estimated-vs-quoted labels, costs, missing prices (28-Oct-2026 audit, task B).
Deterministic fixtures, no network, no orders.   python -m alerts.tests.test_option_pnl"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from alerts import report as RP, breakout as BO  # noqa

OK = []
RP.OPT_STATE_CANDIDATES, RP.OBUY_STATE = [], "/nonexistent/obuy.json"     # only the fixture ledger, not live state files


def check(name, cond):
    assert cond, name
    OK.append(name)
    print("✅", name)


NOW = pd.Timestamp("2026-10-28 12:17")
TS = "28-Oct-2026 12:16:40"
OPEN = lambda ex, now: True                     # noqa: E731


class Api:
    def __init__(self, q):
        self.q, self.calls = q, 0

    def quotes(self, req):
        self.calls += 1
        return {t: self.q[t] for toks in req.values() for t in toks if t in self.q}


def row(**k):
    r = dict(key="NIFTY|3h|x|OPT", cat="OPTION BUY", seg="NSE", name="NIFTY", symbol="NIFTY25NOV2622600CE", type="Positional", side="BUY",
             entry=100.0, sl=65.0, target=180.0, tick=0.05, lot=75, mult=75, time=str(NOW), status="OPEN", date="2026-10-28",
             und_entry=22600.0, und_side="BUY", opt_token="O1", opt_ex="NFO", mark_key="O1", kind="index", spread=0.004,
             basis=RP.BASIS_QUOTE)
    r.update(k)
    return r


def test_costs():
    flat = RP.option_pnl(100.0, 100.0, 75, "index", 0.004)
    check("option P&L: same entry and exit premium -> a LOSS (spread + fees + ₹40 brokerage)", flat < -40)
    a = RP.option_pnl(100.0, 150.0, 75, "index", 0.004)
    gross = (150 - 100) * 75
    check("option P&L: +50 premium × 75 lot is less than the gross ₹3,750 after costs", 0 < a < gross)
    check("option P&L: wider stock spread (model 1% half-spread) costs more than index",
          RP.option_pnl(100.0, 150.0, 75, "stock") < RP.option_pnl(100.0, 150.0, 75, "index"))
    check("option P&L: missing exit price -> None (never a made-up number)", RP.option_pnl(100.0, None, 75, "index") is None)


def test_track_on_premium():
    st = {"ledger": [row(), row(key="b|OPT", opt_token="O2", mark_key="O2"), row(key="c|OPT", opt_token="O3", mark_key="O3"),
                     row(key="d|OPT", opt_token="O4", mark_key="O4"), row(key="e|OPT", opt_token="O5", mark_key="O5")]}
    api = Api({"O1": {"ltp": 60.0, "exchFeedTime": TS},                       # gapped below SL 65
               "O2": {"ltp": 185.0, "exchFeedTime": TS},                      # above target 180
               "O3": {"ltp": 120.0, "exchFeedTime": TS},                      # in between
               "O4": {"ltp": 50.0, "exchFeedTime": "28-Oct-2026 11:40:00"},   # stale
               "O5": {"ltp": 50.0}})                                          # no timestamp
    n = RP.track_options(api, st, NOW, OPEN)
    L = {r["key"]: r for r in st["ledger"]}
    check("premium below SL -> closed at the LTP 60 (worse than SL 65), basis = premium quote",
          L["NIFTY|3h|x|OPT"]["status"] == "CLOSED" and L["NIFTY|3h|x|OPT"]["exit"] == 60.0 and L["NIFTY|3h|x|OPT"]["basis"] == RP.BASIS_QUOTE)
    check("premium above target -> closed at the target 180", L["b|OPT"]["status"] == "CLOSED" and L["b|OPT"]["exit"] == 180.0)
    check("premium in between -> stays open, last premium recorded", L["c|OPT"]["status"] == "OPEN" and L["c|OPT"]["last_prem"] == 120.0)
    check("stale premium quote -> ignored (row not closed, no premium recorded)", L["d|OPT"]["status"] == "OPEN" and "last_prem" not in L["d|OPT"])
    check("premium quote without timestamp -> ignored", L["e|OPT"]["status"] == "OPEN" and "last_prem" not in L["e|OPT"])
    check("exactly 2 rows closed", n == 2)
    st2 = {"ledger": [row()]}
    RP.track_options(Api({"O1": {"ltp": 10.0, "exchFeedTime": TS}}), st2, NOW, lambda ex, now: False)
    check("market closed -> premium not used, row untouched", st2["ledger"][0]["status"] == "OPEN")


def test_close_with_futures():
    st = {"ledger": [dict(key="K", cat="FUTURES", seg="NSE", name="NIFTY", side="BUY", entry=22600.0, status="OPEN", mult=75, lot=75, date="2026-10-28", type="Positional"),
                     row(key="K|OPT", last_prem=140.0, last_prem_time=str(NOW - pd.Timedelta(minutes=10)))]}
    BO.close_ledger(st, "K", 22800.0, "🎯 target", NOW)
    o = st["ledger"][1]
    check("futures call closes -> option row exits at the recently QUOTED premium (140), basis premium quote",
          o["status"] == "CLOSED" and o["exit"] == 140.0 and o["basis"] == RP.BASIS_QUOTE)
    st = {"ledger": [dict(key="K", cat="FUTURES", seg="NSE", name="NIFTY", side="BUY", entry=22600.0, status="OPEN", mult=75, lot=75, date="2026-10-28", type="Positional"),
                     row(key="K|OPT", last_prem=140.0, last_prem_time=str(NOW - pd.Timedelta(hours=3)))]}
    BO.close_ledger(st, "K", 22800.0, "target", NOW)
    o = st["ledger"][1]
    check("no recent premium -> exit = entry + 0.5 × futures move (200) = 200, labelled ESTIMATED",
          o["exit"] == 200.0 and o["basis"] == RP.BASIS_EST)
    st = {"ledger": [dict(key="K", cat="FUTURES", seg="NSE", name="NIFTY", side="BUY", entry=22600.0, status="OPEN", mult=75, lot=75, date="2026-10-28", type="Positional"),
                     row(key="K|OPT", und_entry=None)]}
    BO.close_ledger(st, "K", 22800.0, "stop", NOW)
    o = st["ledger"][1]
    check("no premium and no futures reference -> exit price missing, marked unverified", o["exit"] is None and "unverified" in o["basis"])
    r = RP.rows_for(st, "NSE", "2026-10-28", {})
    oo = [x for x in r if x["cat"] == "OPTION BUY"][0]
    check("missing exit price -> P&L None, shown as 'unverified', excluded from the total",
          oo["pnl"] is None and RP._pnl_cell(oo) == "unverified" and RP.totals([oo]) == (0, 0))


def test_report_labels_and_consistency():
    old = dict(key="old|OPT", cat="OPTION BUY", seg="NSE", name="TCS", symbol="TCS CE", type="Positional", side="BUY", entry=50.0, sl=32.5,
               target=90.0, lot=175, mult=175, status="OPEN", date="2026-10-28", time=str(NOW), und_entry=3450.0, und_side="BUY",
               mark_key="FUT1")
    new = row()
    fut = dict(key="f", cat="FUTURES", seg="NSE", name="NIFTY", symbol="NIFTY FUT", type="Positional", side="SELL", entry=22600.0, sl=22700.0,
               target=22400.0, lot=75, mult=75, status="OPEN", date="2026-10-28", time=str(NOW), mark_key="FUT2")
    canc = row(key="c|OPT", status="CLOSED", exit=100.0, note="cancelled – gap")
    st = {"ledger": [old, new, fut, canc]}
    rows = {r["key"]: r for r in RP.rows_for(st, "NSE", "2026-10-28", {"FUT1": 3470.0, "O1": 112.0, "FUT2": 22550.0})}
    check("older option row (only futures known) -> marked with the estimate and labelled ≈",
          rows["old|OPT"]["basis"] == RP.BASIS_EST and RP._pnl_cell(rows["old|OPT"]).startswith("≈"))
    check("new option row -> marked on its own premium 112 with costs (no ≈)",
          rows["NIFTY|3h|x|OPT"]["basis"] == RP.BASIS_QUOTE and rows["NIFTY|3h|x|OPT"]["pnl"] == RP.option_pnl(100.0, 112.0, 75, "index", 0.004)
          and not RP._pnl_cell(rows["NIFTY|3h|x|OPT"]).startswith("≈"))
    check("futures SELL marked at 22,550 -> +50 × 75 = ₹3,750", rows["f"]["pnl"] == 3750)
    check("cancelled call (no entry) -> P&L 0", rows["c|OPT"]["pnl"] == 0)
    for k in ("NIFTY|3h|x|OPT", "f"):
        r, L = rows[k], [x for x in st["ledger"] if x["key"] == k][0]
        check(f"{k}: report row entry / SL / target identical to the ledger", (r["entry"], r["sl"], r["target"]) == (L["entry"], L["sl"], L["target"]))
    txt = RP.text_table(list(rows.values()), "t")
    check("text report says P&L is from quoted prices, not broker fills, and shows the estimated share",
          "not broker fills" in txt and "estimated" in txt)


if __name__ == "__main__":
    for t in (test_costs, test_track_on_premium, test_close_with_futures, test_report_labels_and_consistency):
        t()
    print(f"\nALL {len(OK)} OPTION-P&L CHECKS PASSED")
