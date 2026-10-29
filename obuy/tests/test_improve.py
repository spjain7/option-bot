"""Offline tests for the 29-Oct option-buy improvements (obuy/improve.py + obuy/engine.py). python -m obuy.tests.test_improve"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from obuy import engine as E, improve as IM
from greeks import price

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


EXP = pd.Timestamp("2026-11-26")
master = pd.DataFrame([dict(name="ABC", exch_seg="NFO", instrumenttype="OPTSTK", symbol=f"ABC26NOV{k}{t}", token=f"{t}{k}",
                            strike=k * 100, expiry_dt=EXP, lotsize=500) for k in range(940, 1061, 20) for t in ("CE", "PE")])
chain = IM.strikes(master, "ABC", "CE", "2026-11-26")

# 1. strikes
itm = IM.itm_strike(chain, 1005.0, "CE")
check(itm["K"] == 1000.0, "ITM CE = the nearest strike below the price")
check(IM.itm_strike(IM.strikes(master, "ABC", "PE", "2026-11-26"), 1005.0, "PE")["K"] == 1020.0, "ITM PE = the nearest strike above")

# 2. normal move and projected gain
check(IM.normal_move(20, pd.Timestamp("2026-10-29 10:00"), "positional") == 20, "positional normal move = 1 daily ATR")
mv = IM.normal_move(20, pd.Timestamp("2026-10-29 11:15"), "intraday")
check(abs(mv - 20 * np.sqrt(240 / 375)) < 1e-9, "intraday normal move = ATR × √(minutes left / 375)")
T = 28 / 365
p = price(1000, 1000, T, 0.3, 0.065, "CE")
g_small, g_big = IM.projected_gain(p, 1000, 1000, T, 0.3, "CE", 5, 0.1), IM.projected_gain(p, 1000, 1000, T, 0.3, "CE", 30, 0.1)
check(g_big > g_small > 0, "a bigger move -> a bigger premium gain")
check(IM.projected_gain(p, 1000, 1000, T, 0.3, "CE", 0, 1) < 0, "no move -> time decay loss")
check(IM.projected_gain(p, 1000, 1000, T, 0.3, "PE", 30, 0.1) > 0, "PE gains when the futures fall (move is in the trade direction)")

# 3. OI wall
class QA:
    def __init__(self, oi): self.oi = oi
    def quotes(self, ex): return {t: {"opnInterest": self.oi.get(t, 0)} for t in ex["NFO"]}
check(IM.oi_wall(QA({"CE1000": 100, "CE1020": 350}), chain, 1005, "CE", 20, 1000.0) == (1020.0, 3.5), "OI wall: 3.5× call OI at 1020 detected")
check(IM.oi_wall(QA({"CE1000": 100, "CE1020": 150}), chain, 1005, "CE", 20, 1000.0) is None, "no wall when OI is only 1.5×")

# 4. ban list
st = {}
check(IM.ban_list(st, pd.Timestamp("2026-10-29 09:40"), fetch=lambda: "Sr No,Symbol\n1,RBLBANK\n2,IEX\n") == ["IEX", "RBLBANK"],
      "F&O ban list parsed")
check(IM.ban_list(st, pd.Timestamp("2026-10-29 10:40"), fetch=lambda: 1 / 0) == ["IEX", "RBLBANK"], "ban list fetched once a day (cached)")
check(IM.ban_list({}, pd.Timestamp("2026-10-29 09:40"), fetch=lambda: 1 / 0) is None, "fetch failure -> unknown (None), never invented")

# 5. exits: time stop and VWAP invalidation
class MA:
    def __init__(self, p, df=None): self.p, self.df = p, df
    def quotes(self, ex): return {t: {"ltp": self.p.get(t, 0), "tradeVolume": 10} for t in ex["NFO"]}
    def candles(self, ex, tok, iv, frm, to): return self.df
    def oi_history(self, ex, tok, iv, frm, to): return None
base = {"dir": 1, "name": "X", "K": 100, "lot": 100, "kind": "stock", "entry": 100.0, "sl": 70.0, "tg": 160.0, "mode": "intraday",
        "exit_at": "2026-10-29 15:15", "symbol": "X", "id": 1, "opened": "2026-10-29 10:00", "token": "a"}
s1, m1 = {"open": [dict(base)], "closed": []}, []
E.manage(MA({"a": 105}), s1, pd.Timestamp("2026-10-29 11:05"), m1)
check(s1["closed"] and s1["closed"][0]["why_exit"].startswith("no follow-through"), "time stop: premium +5% after 65 min -> exit")
s2, m2 = {"open": [dict(base)], "closed": []}, []
E.manage(MA({"a": 115}), s2, pd.Timestamp("2026-10-29 11:05"), m2)
check(not s2["closed"], "premium +15% after 65 min -> keep")
t = pd.date_range("2026-10-29 09:15", periods=8, freq="15min")
fdf = pd.DataFrame(dict(time=t, open=1000.0, high=1001.0, low=999.0, close=[1002, 1003, 1004, 1003, 1001, 999, 998, 997.0],
                        volume=1000, oi=1e6))
fdf["vwap"] = 1000.5
s3, m3 = {"open": [dict(base, fut_token="F")], "closed": []}, []
E.fut_frame = lambda api, tok, frm, now: fdf
E.manage(MA({"a": 112}, fdf), s3, pd.Timestamp("2026-10-29 11:17"), m3)
check(s3["closed"] and s3["closed"][0]["why_exit"] == "futures closed back across VWAP" and "EXIT" in m3[0],
      "VWAP invalidation: futures close back below VWAP -> exit message")

# 6. entry: strike choice and the normal-move check (open_alert end to end)
class OA:
    def __init__(self, atr): self.atr = atr
    def quotes(self, ex):
        out = {}
        for tk in ex["NFO"]:
            typ, k = tk[:2], float(tk[2:])
            pr = price(1005.0, k, 28 / 365, 0.28, 0.065, typ)
            out[tk] = {"ltp": round(pr, 2), "tradeVolume": 100, "opnInterest": 1000,
                       "depth": {"buy": [{"price": pr * 0.995}], "sell": [{"price": pr * 1.005}]}}
        return out
    def candles(self, ex, tok, iv, frm, to):
        d = pd.bdate_range(end="2026-10-28", periods=30)
        rng = np.random.default_rng(1); c = 1000 * np.exp(np.cumsum(rng.normal(0, 0.017, len(d))))
        return pd.DataFrame(dict(time=d, open=c, high=c + self.atr / 2, low=c - self.atr / 2, close=c, volume=1000))
E.fut_frame = lambda api, tok, frm, now: None
for atr, want in ((40.0, True), (4.0, False)):
    stt, msgs, rep = {"open": [], "closed": [], "done": {}, "next_id": 1}, [], []
    E.open_alert(OA(atr), master, stt, pd.Timestamp("2026-10-29 10:05"), {"name": "ABC", "token": "F", "kind": "stock", "lot": 500},
                 "intraday", 1, 1005.0, ["test signal"], msgs, rep)
    if want:
        a = stt["open"][0] if stt["open"] else {}
        check(bool(msgs) and a.get("K") in (1000.0, 1020.0) and any("normal move" in x for x in a.get("why", [])),
              f"daily range {atr:g}: alert sent with strike {a.get('K')} and the normal-move line")
    else:
        check(not msgs and any("normal move" in r for r in rep), f"daily range {atr:g}: skipped – a normal move cannot pay the 30% risk")

# 7. option idea for a triggered futures call, judged on the futures stop / target
mst = master.assign(instrumenttype="OPTSTK")
class OQ:
    def __init__(self, F): self.F = F
    def quotes(self, ex):
        out = {}
        for tk in ex["NFO"]:
            typ, k = tk[:2], float(tk[2:])
            pr = price(self.F, k, 28 / 365, 0.28, 0.065, typ)
            out[tk] = {"ltp": round(pr, 2), "tradeVolume": 10, "depth": {"buy": [{"price": pr * 0.997}], "sell": [{"price": pr * 1.003}]}}
        return out
msg = IM.option_for_futures_call(OQ(1000.0), mst, "ABC", -1, 1000.0, 1015.0, 970.0, pd.Timestamp("2026-10-29 15:40"), hold_days=3)
check(msg is not None and "BUY ABC" in msg and "PE" in msg and "If the futures reach the target" in msg,
      "SELL futures call (target 30 pts, stop 15 pts) -> PE option idea with gain/loss at the futures levels")
msg2 = IM.option_for_futures_call(OQ(1000.0), mst, "ABC", -1, 1000.0, 1030.0, 997.0, pd.Timestamp("2026-10-29 15:40"), hold_days=3)
check(msg2 is None, "target only 3 pts away (stop 30) -> the option pays less than it risks -> no idea")

print(f"\nimprove: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
