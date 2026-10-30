"""Offline test: daily call report – all open calls + closed today, high / low after the call, CMP, best / worst, P&L per lot.
python -m alerts.tests.test_report"""
import json, sys, tempfile
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import report as RP

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


NOW = pd.Timestamp("2026-10-30 15:40")
st = {}
RP.add(st, key="A", mark_key="1", seg="NSE", cat="FUTURES", name="TITAN", symbol="TITAN25NOV26FUT", type="Positional", side="BUY",
       entry=3300.0, sl=3250.0, target=3400.0, lot=175, mult=175, time="2026-10-28 15:35")
RP.add(st, key="A|OPT", mark_key="1", seg="NSE", cat="OPTION BUY", name="TITAN", symbol="TITAN25NOV263300CE", type="Positional",
       side="BUY", entry=60.0, sl=39.0, target=108.0, lot=175, mult=175, time="2026-10-28 15:35", und_entry=3300.0, und_side="BUY")
RP.add(st, key="B", mark_key="2", seg="NSE", cat="FUTURES", name="HAL", symbol="HAL25NOV26FUT", type="Positional", side="SELL",
       entry=4800.0, sl=4900.0, target=4600.0, lot=150, mult=150, time="2026-10-29 15:35")
RP.add(st, key="C", mark_key="3", seg="NSE", cat="FUTURES", name="SBIN", symbol="SBIN", type="Positional", side="BUY",
       entry=900.0, sl=880.0, target=940.0, lot=750, mult=750, time="2026-10-20 15:35")
st["ledger"][-1].update(status="CLOSED", exit=880.0, closed="2026-10-27 11:00")          # closed earlier -> not shown
# scans during the day
RP.track(st, {"1": {"ltp": 3320.0, "high": 3355.0, "low": 3290.0}, "2": {"ltp": 4790.0, "high": 4830.0, "low": 4760.0}},
         pd.Timestamp("2026-10-30 10:02"))
RP.track(st, {"1": {"ltp": 3340.0, "high": 3355.0, "low": 3290.0}, "2": {"ltp": 4750.0, "high": 4830.0, "low": 4740.0}},
         pd.Timestamp("2026-10-30 13:02"))
from alerts import breakout as BO
BO.close_ledger(st, "B", 4740.0, "manual test exit", pd.Timestamp("2026-10-30 13:05"))
RP.OBUY_STATE = str(Path(tempfile.mkdtemp()) / "none.json"); RP.OPT_STATE_CANDIDATES = []
rows = RP.rows_for(st, "NSE", "2026-10-30", {"1": {"ltp": 3345.0}})
by = {(r["symbol"]): r for r in rows}
check(set(by) == {"TITAN25NOV26FUT", "TITAN25NOV263300CE", "HAL25NOV26FUT"}, "open calls of earlier days + closed today shown; closed earlier hidden")
t = by["TITAN25NOV26FUT"]
check(t["hi"] == 3355.0 and t["lo"] == 3290.0, "futures high / low after the call (day high / low of later days)")
check(t["cmp"] == 3345.0 and t["pnl"] == round(45 * 175), "open call at CMP: P&L per lot")
check(t["best"] == round(55 * 175) and t["worst"] == round(-10 * 175), "best / worst ₹ per lot")
o = by["TITAN25NOV263300CE"]
check(abs(o["hi"] - (60 + 0.5 * 55)) < 1e-6 and abs(o["lo"] - (60 - 0.5 * 10)) < 1e-6, "option row: premium high / low ≈ 0.5 × futures move")
h = by["HAL25NOV26FUT"]
check(h["status"] == "CLOSED" and h["cmp"] == 4740.0 and h["pnl"] == round(60 * 150), "closed today: exit price and P&L")
check(h["best"] == round((4800 - 4740) * 150) and h["worst"] == round((4800 - 4830) * 150), "SELL call: best = low, worst = high")
txt = RP.text_table(sorted(rows, key=lambda r: r["status"] != "OPEN"), "test")
check("high 3,355" in txt and "CMP 3,345" in txt and "worst" in txt, "text report lists high / low / CMP / best / worst")
png = RP.render(rows, "test", Path(tempfile.mkdtemp()) / "r.png")
check(png is None or Path(png).exists(), "table image renders")
# option-buy engine rows (premium tracked)
ob = {"open": [dict(name="BSE", symbol="BSE25NOV263450CE", mode="intraday", entry=150.0, sl=105.0, tg=240.0, lot=200,
                    opened="2026-10-30 10:50", hi=171.0, lo=140.0, last=165.0)], "closed": [], "sweep15": {"open": [], "closed": [
          dict(name="PNB", contract="PNB25NOV26FUT", side="SELL", send=True, status="closed", entry=125.0, exit=123.5, stop=126.0,
               target=124.0, lot=8000, entry_time="2026-10-30 10:15:00", closed="2026-10-30 11:00", exit_reason="target", hi=125.4, lo=123.4)]}}
f = Path(tempfile.mkdtemp()) / "obuy.json"; f.write_text(json.dumps(ob)); RP.OBUY_STATE = str(f)
x = {r["symbol"]: r for r in RP.option_buys("2026-10-30")}
check(x["BSE25NOV263450CE"]["pnl"] == 15 * 200 and x["BSE25NOV263450CE"]["hi"] == 171.0, "option-buy engine: premium high / low and P&L at CMP")
check(x["PNB25NOV26FUT"]["pnl"] == round(1.5 * 8000) and x["PNB25NOV26FUT"]["lo"] == 123.4, "15-min sweep call: high / low and P&L")
print(f"\nreport: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
