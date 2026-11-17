"""Offline tests (17-Nov-2026): after-close calls are held until the next open; live-triggered setups are trades; high / low
backfill. python -m alerts.tests.test_after_close_hold"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import four_hour as FH, report as RP, strategies as ST, candle_setups as CS

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


class Api:
    def __init__(self, q, candles=None):
        self.q, self.c = q, candles

    def quotes(self, req):
        return {t: self.q[t] for toks in req.values() for t in toks if t in self.q}

    def candles(self, ex, tok, iv, a, b):
        return self.c


def is_open(ex, now):
    return 9 * 60 + 15 <= now.hour * 60 + now.minute < 15 * 60 + 30 and now.weekday() < 5


def new_call(state, msgs, name="POLYCAB", token="1"):
    """what _on_candles / rulebook.run leave behind for one after-close call."""
    n0 = len(msgs)
    r = dict(name=name, ex="NFO", token=token, contract=f"{name}23NOV26FUT", expiry="2026-11-25", side="SELL", entry=7730.0, stop=7955.0, target=7280.0,
             risk=225.0, tick=0.05, mult=125, opened="2026-11-17 15:32:01", days=["2026-11-17"], key=f"3H|{name}|x", max_days=20,
             tfl="3-hour", await_open=True, atr=150.0)
    state.setdefault("fourh", dict(open=[], closed=[], last={}, await_v=1))["open"].append(r)
    msgs += [f"🔴 SELL  {name} FUT  ·  SWING (3-hour candles)\nEntry   : 7,730.00", f"📌 WHY – {name} SELL (3-hour)"]
    RP.add(state, key=r["key"], mark_key=token, seg="NSE", cat="FUTURES", name=name, symbol=r["contract"], type="3-hour EMAX",
           side="SELL", entry=7730.0, sl=7955.0, target=7280.0, lot=125, mult=125, time=r["opened"])
    state.setdefault("day", {})["alerts"] = state.get("day", {}).get("alerts", 0) + 1
    FH.hold(state, msgs, n0)
    return r


st = dict(day={}, ledger=[]); msgs = ["other message"]
r = new_call(st, msgs)
check(msgs == ["other message"] and len(r["held_msgs"]) == 2, "after-close call: nothing sent in the evening, messages held")
check(st["ledger"][0]["status"] == "WAITING" and st["day"]["alerts"] == 0, "report row waits; not counted as sent")
check(not [x for x in RP.rows_for(st, "NSE", "2026-11-17", {}) if x["name"] == "POLYCAB"], "held call not in the evening report")
check(ST.conflict(st, "POLYCAB", "BUY", "3h") is not None, "duplicate / contradiction guard still sees the held call")

# next open inside the zone -> NEW CALL + held messages + ACTIVE; issued time = the open
m = []
FH.track(st, m, Api({"1": dict(ltp=7712.0, open=7715.0)}), pd.Timestamp("2026-11-18 09:17"), is_open)
check(len(m) == 4 and m[0].startswith("📢 NEW CALL – POLYCAB FUT SELL") and m[1].startswith("🔴 SELL  POLYCAB") and m[3].startswith("✅ ACTIVE"),
      "released at the open: NEW CALL header, the call, WHY, ACTIVE line")
L = st["ledger"][0]
check(L["status"] == "OPEN" and L["time"] == "2026-11-18 09:17:00" and L["entry"] == 7715.0, "report row: issued at the open, entry = open")
check(st["day"]["alerts"] == 1, "counted as one call when released")

# next open past the entry -> never published, no message, row VOID
st2 = dict(day={}, ledger=[]); m2 = []
new_call(st2, m2, "BDL", "2")
m2 = []
FH.track(st2, m2, Api({"2": dict(ltp=7500.0, open=7520.0)}), pd.Timestamp("2026-11-18 09:17"), is_open)
check(m2 == [] and st2["ledger"][0]["status"] == "VOID" and not st2["fourh"]["open"], "skipped at the open: never published, no message")
check(not RP.history_nse(st2) and not RP.rows_for(st2, "NSE", "2026-11-18", {}), "never-published call not in report or history")

# old-style call sent in the evening (before this change): still ACTIVE / SKIPPED at the open (no NEW CALL header)
st3 = dict(day={}, ledger=[], fourh=dict(open=[dict(new_call(dict(day={}, ledger=[]), []), held_msgs=None)], closed=[], last={}, await_v=1))
st3["fourh"]["open"][0].pop("held_msgs")
st3["ledger"] = [dict(key="3H|POLYCAB|x", status="OPEN", entry=7730.0, seg="NSE", cat="FUTURES", name="POLYCAB")]
m3 = []
FH.track(st3, m3, Api({"1": dict(ltp=7712.0, open=7715.0)}), pd.Timestamp("2026-11-18 09:17"), is_open)
check(len(m3) == 1 and m3[0].startswith("✅ ACTIVE"), "already-sent evening call: ACTIVE line only")

# live-triggered setup (SONACOMS 4-Nov): recorded as a stop-loss trade
cs = dict(ledger=[], candle_setups=dict(open=[], closed=[dict(setup="STK_HANGMAN", name="SONACOMS", contract="SONACOMS23NOV26FUT",
          token="61711", side="SELL", status="closed", trigger=893.5, stop=916.25, tick=0.05, mult=1225, lot=1225,
          key="STK_HANGMAN|SONACOMS|2026-11-02", live=dict(trigger="2026-11-04 12:17:02", stop="2026-11-05 12:02:01"), entry=None,
          exit=None, exit_reason="stop level touched before the breakout")]))
check(CS.heal_live(cs) == 1 and CS.heal_live(cs) == 0, "live-triggered setup re-created once")
h = RP.history_nse(cs)
check(len(h) == 1 and h[0]["name"] == "SONACOMS" and h[0]["pnl"] == round(-(916.25 - 893.5) * 1225) and "Stop-loss" in RP.result_label(h[0]),
      "SONACOMS in the closed history as a stop-loss, P&L −22.75 pts x 1,225")

# forward: the daily candle cannot overrule a LIVE trigger
r = dict(setup="STK_HANGMAN", name="X", side="SELL", status="pending", trigger=100.0, stop=104.0, target_r=2.0, pattern_time="2026-11-10 09:15",
         last_bar="2026-11-10 09:15", key="k", contract="XFUT", token="9", tick=0.05, mult=10, lot=10,
         live=dict(trigger="2026-11-11 12:00:00"))
bars = pd.DataFrame(dict(time=pd.to_datetime(["2026-11-11"]), open=101.0, high=105.0, low=99.0, close=100.5))
done, px, t, why = CS._step_pattern(dict(ledger=[]), [], r, bars, bars, pd.Timestamp("2026-11-11 16:00"))
check(done and px == 104.0 and why == "stop-loss" and r["entry"] == 100.0, "live-triggered day: entered at the trigger, stop-loss (not 'never triggered')")

# high / low backfill from 15-minute candles
bf = dict(ledger=[dict(key="L", mark_key="5", seg="NSE", cat="FUTURES", name="LTM", side="SELL", entry=4258.9, time="2026-11-11 09:15:00",
                       status="OPEN")])
c15 = pd.DataFrame(dict(time=pd.date_range("2026-11-11 09:15", periods=8, freq="15min"), open=4250.0, high=[4300, 4280, 4260, 4250, 4240, 4230, 4220, 4210.0],
                        low=[4200, 4190, 4180, 4170, 4160, 4150, 4140, 4100.0], close=4110.0))
check(RP.backfill_hilo(bf, Api({}, c15), pd.Timestamp("2026-11-17 10:00")) == 1 and bf["ledger"][0]["uhi"] == 4300 and bf["ledger"][0]["ulo"] == 4100,
      "open call with no high / low filled from candles since the call")
check(RP.backfill_hilo(bf, Api({}, c15), pd.Timestamp("2026-11-17 10:15")) == 0, "backfill runs once per row")

# calls issued after the close are not listed until they are active
lst = dict(ledger=[])
RP.add(lst, key="A", mark_key="1", seg="NSE", cat="FUTURES", name="POLYCAB", symbol="POLYCAB23NOV26FUT", type="3-hour EMAX", side="SELL",
       entry=7730.0, sl=7955.0, target=7280.0, lot=125, mult=125, time="2026-11-17 15:32:01")
RP.add(lst, key="B", mark_key="2", seg="NSE", cat="FUTURES", name="GLENMARK", symbol="GLENMARK23NOV26FUT", type="Positional", side="BUY",
       entry=2509.0, sl=2365.0, target=None, lot=375, mult=375, time="2026-11-04 15:32")
RP.add(lst, key="C", mark_key="3", seg="NSE", cat="FUTURES", name="INDIANB", symbol="INDIANB23NOV26FUT", type="Positional", side="BUY",
       entry=942.0, sl=895.0, target=None, lot=1000, mult=1000, time="2026-11-17 15:32")
names = [r["name"] for r in RP.rows_for(lst, "NSE", "2026-11-17", {})]
check(names == ["GLENMARK"], "after-close calls of today hidden (POLYCAB 3h, daily OI INDIANB); older calls still listed")
pf = dict(lst, day={}, fourh=dict(open=[dict(name="POLYCAB", ex="NFO", token="1", contract="POLYCAB23NOV26FUT", expiry="2026-11-25",
          side="SELL", entry=7730.0, stop=7955.0, target=7280.0, risk=225.0, tick=0.05, mult=125, opened="2026-11-17 15:32:01",
          days=["2026-11-17"], key="A", max_days=20, tfl="3-hour", await_open=True, atr=150.0)], closed=[], last={}, await_v=1))
m5 = []
FH.track(pf, m5, Api({"1": dict(ltp=7712.0, open=7715.0)}), pd.Timestamp("2026-11-18 09:17"), is_open)
row = [r for r in RP.rows_for(pf, "NSE", "2026-11-18", {}) if r["name"] == "POLYCAB"]
check(len(row) == 1 and row[0]["time"] == "2026-11-18 09:17:00" and m5[0].startswith("✅ ACTIVE"), "listed after activation, issued = the open")

# owner: FORTIS 13-Nov not traded -> not in the list or the history
fx = dict(ledger=[dict(key="F", mark_key="7", seg="NSE", cat="FUTURES", name="FORTIS", side="SELL", entry=767.65, sl=793.65, target=686.6,
                       lot=550, mult=550, time="2026-11-16 09:47:01", date="2026-11-13", status="CLOSED", exit=793.65, note="stop-loss",
                       closed="2026-11-16 11:17")])
fx["ledger"][0]["time"] = "2026-11-13 15:32:01"
check(not RP.history_nse(fx) and not RP.rows_for(fx, "NSE", "2026-11-16", {}), "FORTIS (owner: not traded) removed from list and history")

# closed row without high / low (re-created SONACOMS) gets them from candles between entry and exit
cl = dict(ledger=[dict(key="S", mark_key="61711", seg="NSE", cat="FUTURES", name="SONACOMS", side="SELL", entry=893.5, sl=916.25,
                       lot=1225, mult=1225, time="2026-11-04 12:17:02", status="CLOSED", exit=916.25, note="stop-loss",
                       closed="2026-11-05 12:02:01")])
c2 = pd.DataFrame(dict(time=pd.date_range("2026-11-04 09:15", "2026-11-05 15:15", freq="15min"), open=900.0, high=905.0, low=880.0, close=900.0))
check(RP.backfill_hilo(cl, Api({}, c2), pd.Timestamp("2026-11-17 10:00")) == 1 and cl["ledger"][0]["uhi"] == 916.25 and cl["ledger"][0]["ulo"] == 880.0,
      "closed call: high / low filled from candles (exit price included)")
h2 = RP.history_nse(cl)[0]
check(h2["best"] == round((893.5 - 880.0) * 1225) and h2["worst"] == round(-(916.25 - 893.5) * 1225), "closed call: best / worst filled")

# LTM: entered on its live day -> issued = live time, high / low re-measured from then
lt = dict(ledger=[dict(key="STK_HANGMAN|LTM|x", mark_key="61635", seg="NSE", cat="FUTURES", name="LTM", side="SELL", entry=4258.9,
                       time="2026-11-11 09:15:00", status="OPEN")],
          candle_setups=dict(open=[dict(setup="STK_HANGMAN", name="LTM", key="STK_HANGMAN|LTM|x", status="open", entry=4258.9,
                                        entry_time="2026-11-11 09:15:00", live=dict(trigger="2026-11-11 13:17:02"))], closed=[]))
CS.heal_live(lt)
check(lt["ledger"][0]["time"] == "2026-11-11 13:17:02", "LTM issued time = live trigger 13:17 (not the 09:15 daily bar)")

# one-time: index rulebook call fired after the close (BANKNIFTY 16-Nov 15:32) -> decided at 17-Nov's real open from candles
def bn(**k):
    r = dict(name="BANKNIFTY", ex="NFO", token="61466", contract="BANKNIFTY23NOV26FUT", expiry="2026-11-25", side="BUY", entry=61480.0,
             stop=60163.0, target=64114.0, risk=1317.0, tick=0.05, mult=30, opened="2026-11-16 15:32:00", days=["2026-11-16", "2026-11-17"],
             key="RB|RB_IDX_1d_BO10_BUY|BANKNIFTY|x", max_days=10, tfl="daily", rule="RB_IDX_1d_BO10_BUY")
    r.update(k); return r
cbn = pd.DataFrame(dict(time=pd.date_range("2026-11-17 09:15", periods=4, freq="15min"), open=[61620.0, 61700, 61800, 61900],
                        high=61950.0, low=61500.0, close=61900.0))
sb = dict(ledger=[dict(key="RB|RB_IDX_1d_BO10_BUY|BANKNIFTY|x", status="OPEN", entry=61480.0, time="2026-11-16 15:32:00", seg="NSE",
                       cat="FUTURES", name="BANKNIFTY")], fourh=dict(open=[bn()], closed=[], last={}))
mb = []
FH.late_activate(sb, mb, Api({}, cbn), pd.Timestamp("2026-11-17 18:00"))
rb = sb["fourh"]["open"][0]
check(rb["entry"] == 61620.0 and rb["call_entry"] == 61480.0 and sb["ledger"][0]["time"] == "2026-11-17 09:15:00" and mb and "ACTIVE" in mb[0],
      "BANKNIFTY: entry corrected to 17-Nov open, issued = 09:15, one correction message")
mb = []
FH.late_activate(sb, mb, Api({}, cbn), pd.Timestamp("2026-11-17 18:15"))
check(not mb, "late activation runs once")
sk = dict(ledger=[dict(key="RB|RB_IDX_1d_BO10_BUY|BANKNIFTY|x", status="OPEN", entry=61480.0, time="2026-11-16 15:32:00")],
          fourh=dict(open=[bn()], closed=[], last={}))
mk = []
FH.late_activate(sk, mk, Api({}, cbn.assign(open=[62400.0, 62400, 62400, 62400])), pd.Timestamp("2026-11-17 18:00"))
check(not sk["fourh"]["open"] and "NO TRADE" in mk[0] and sk["ledger"][0]["note"] == "skipped – gap", "gapped > 0.5 ATR above: no trade")
old_ = dict(ledger=[], fourh=dict(open=[bn(opened="2026-11-06 15:32:00")], closed=[], last={}))
FH.late_activate(old_, [], Api({}, cbn), pd.Timestamp("2026-11-17 18:00"))
check(old_["fourh"]["open"][0]["entry"] == 61480.0, "older calls untouched")

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
