"""Offline tests: 17-Nov owner layout of the INDEX + STOCK report, ledger self-heal, rulebook describe() for every rule.
python -m alerts.tests.test_report_layout"""
import sys
import tempfile
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import report as RP, rulebook as RB

ok = fail = 0


def check(c, name):
    global ok, fail
    if c:
        ok += 1; print("✅", name)
    else:
        fail += 1; print("FAIL", name)


# describe() never raises (the RSIX entry crashed every rule whose parameter has no "/")
bad = []
for k, r in RB.RULES.items():
    try:
        RB.describe(r)
    except Exception:
        bad.append(k)
check(not bad, f"describe() works for all {len(RB.RULES)} rules")
check(RB.describe(RB.RULES["RB_STK_4h_MACD0_SELL"]).startswith("MACD zero cross"), "MACD zero rule described")

# ledger self-heal from open call records
st = dict(ledger=[], fourh=dict(open=[
    dict(name="ONGC", ex="NFO", token="9", contract="ONGC23NOV26FUT", side="SELL", entry=225.6, stop=230.55, target=216.85, tick=0.05,
         mult=2250, opened="2026-11-13 17:17:00", key="RB|RB_STK_4h_MACD0_SELL|ONGC|x", tfl="4-hour", rule="RB_STK_4h_MACD0_SELL"),
    dict(name="X", ex="NFO", token="8", side="BUY", entry=1, stop=0.5, target=2, mult=1, opened="2026-11-13 10:00", key="k2", shadow=True),
    dict(name="Y", ex="NFO", token="7", side="BUY", entry=1, stop=0.5, target=2, mult=1, opened="2026-11-13 10:00", key="k3", pending=True)],
    closed=[]))
check(RP.heal(st) == 1 and st["ledger"][0]["key"].startswith("RB|RB_STK_4h_MACD0_SELL|ONGC") and st["ledger"][0]["lot"] == 2250,
      "missing open call re-added to the report ledger (shadow / pending skipped)")
check(RP.heal(st) == 0, "heal is idempotent")

# layout
RP.OBUY_STATE = str(Path(tempfile.mkdtemp()) / "none.json"); RP.OPT_STATE_CANDIDATES = []
s = {}
RP.add(s, key="A", mark_key="1", seg="NSE", cat="FUTURES", name="GLENMARK", symbol="GLENMARK23NOV26FUT", type="Positional", side="BUY",
       entry=2509.0, sl=2365.0, target=None, lot=375, mult=375, time="2026-11-04 15:32")
RP.add(s, key="B", mark_key="2", seg="NSE", cat="FUTURES", name="GRASIM", symbol="GRASIM23NOV26FUT", type="Swing (4-hour)", side="SELL",
       entry=3030.0, sl=3129.0, target=2842.0, lot=250, mult=250, time="2026-11-13 17:32")
RP.add(s, key="C", mark_key="3", seg="NSE", cat="FUTURES", name="SBIN", symbol="SBIN23NOV26FUT", type="3-hour EMAX", side="SELL",
       entry=767.65, sl=793.65, target=686.6, lot=550, mult=550, time="2026-11-13 15:32")
RP.add(s, key="D", mark_key="4", seg="NSE", cat="FUTURES", name="TMPV", symbol="TMPV23NOV26FUT", type="Swing (4-hour)", side="SELL",
       entry=288.5, sl=299.05, target=267.5, lot=1600, mult=1600, time="2026-11-13 17:32")
s["ledger"][2].update(status="CLOSED", exit=794.0, note="stop-loss", closed="2026-11-17 11:17", hi=795.0, lo=760.0)
s["ledger"][3].update(status="CLOSED", exit=288.5, note="skipped – gap", closed="2026-11-16 09:17", hi=268.0, lo=268.0)
RP.track(s, {"1": {"ltp": 2606.0}, "2": {"ltp": 3059.0}}, pd.Timestamp("2026-11-17 10:00"))
d = tempfile.mkdtemp()
out = RP.build(s, "NSE", pd.Timestamp("2026-11-17 15:40"), {"1": {"ltp": 2606.0}, "2": {"ltp": 3059.0}}, d)
txt = "\n\n".join(m for m in out if not m.startswith("PHOTO::"))
check(out[0].startswith("PHOTO::"), "image first")
check("🟢 OPEN CALLS" in txt and "📕 CLOSED TODAY" in txt and txt.index("OPEN CALLS") < txt.index("CLOSED TODAY"), "open and closed in separate sections")
blk = txt[txt.index("GLENMARK FUT"):].split("\n\n")[0].split("\n")
check(blk[1].startswith("🗓 Issued : 04-Nov 15:32") and "Basis" not in txt.split("🔒 INTERNAL")[0], "issued date on its own line, no basis in the client text")
check([x.split(":")[0].strip() for x in blk[2:]] == ["💰 Entry", "🛑 SL", "📈 High", "📉 Low", "💹 CMP", "✅ Best profit", "⚠️ Highest loss",
                                                      "🟢 In profit"], "one value per line: entry, SL/target, high, low, CMP, best, worst, status")
intl = [m for m in out if m.startswith("🔒 INTERNAL")]
check(len(intl) == 1 and "GRASIM FUT SELL · 13-Nov 17:32 · Swing · 4-hour chart" in intl[0] and "SBIN FUT SELL" in intl[0],
      "basis in a separate internal message, one line per script")
check("🛑 Stop-loss hit : −₹" in txt and "SBIN FUT" in txt.split("CLOSED TODAY")[1], "closed call with result line")
check(all(len(m) <= 4000 for m in out), "every message under Telegram's 4,000-character cut")
H = RP.history_nse(s)
check([h["name"] for h in H] == ["SBIN"], "closed history: futures only, never-active (no-trade) calls left out")
check(Path(out[0].split("::")[1]).exists(), "image with open table + closed-call history renders")
cells = RP._cells_nse([r for r in RP.rows_for(s, "NSE", "2026-11-17", {}) if r["name"] == "GRASIM"][0])
check(len(cells) == len(RP.HEAD_NSE) and "Swing (4-hour)" not in cells, "image has no call-type / category column")
big = [dict(r, time="2026-11-04 15:32") for r in [RP.rows_for(s, "NSE", "2026-11-17", {"1": {"ltp": 2606.0}})[0]] * 40]
parts = RP.text_nse(big, "T")
check(len(parts) > 1 and all(len(p) <= RP.TEXT_LIMIT for p in parts), "long reports split into several messages")
# MCX report unchanged (old one-table format)
s["ledger"].append(dict(key="M", mark_key="5", seg="MCX", cat="FUTURES", name="ZINC", symbol="ZINC", type="1-hour BO", side="BUY",
                        entry=400.0, sl=395.0, target=410.0, lot=None, mult=5000, time="2026-11-17 10:00", status="OPEN", date="2026-11-17"))
mo = RP.build(s, "MCX", pd.Timestamp("2026-11-17 23:45"), {}, d)
check(mo[-1].startswith("📊 MCX CALLS"), "MCX report keeps its format")

print(f"\nreport layout: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
