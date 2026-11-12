"""Offline checks for the shadow engine: signal detection, duplicate prevention, immutability guard, price tracking,
costs, outcome calculation and the not-executable reasons.     python -m research.shadow.tests.test_shadow"""
import json
import sys
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.shadow import rules as RU, engine as EN, run as RN  # noqa: E402
from research.rsidiv import engine as E  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


# ---- walk() == research simulator on random paths (both sides, every exit type) ----
rng = np.random.default_rng(1); agree = 0; total = 0
for side in (1, -1):
    for _ in range(300):
        n = 40; c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n))); o = c * (1 + rng.normal(0, 0.006, n))
        h = np.maximum(o, c) * (1 + abs(rng.normal(0, 0.008, n))); l = np.minimum(o, c) * (1 - abs(rng.normal(0, 0.008, n)))
        sig = np.zeros(n, bool); sig[3] = True; risk = np.full(n, 2.0)
        ei, xi, nr, gr, cr = E.sim(o, h, l, c, sig, side, risk, 3.0, np.zeros(n, np.int64), 15, np.zeros(n), np.zeros(n, np.int64))
        w = RU.walk(o, h, l, c, 4, side, 2.0, 3.0, 15)
        total += 1; agree += int(len(ei) == 1 and xi[0] == w["exit_i"] and abs(gr[0] - w["gross_R"]) < 1e-9)
check(agree == total, f"walk() reproduces the research simulator exactly ({agree}/{total} random trades)")
w = RU.walk(np.array([100., 100, 97]), np.array([100., 100.5, 98]), np.array([100., 99.8, 96]), np.array([100., 100, 97]), 1, 1, 1.0, 1.0, 10)
check(w["reason"] == "stop (gap)" and abs(w["gross_R"] + 3) < 1e-9 and w["mae_R"] >= 3, "gap through the stop: filled at the open, MAE >= 3R")
w = RU.walk(np.array([100., 100, 100]), np.array([100., 103, 100]), np.array([100., 98.5, 100]), np.array([100., 100, 100]), 1, 1, 1.0, 2.0, 10)
check(w["reason"] == "stop" and w["mfe_R"] <= 2.0, "stop and target in one bar: stop first, MFE capped at the target")
w = RU.walk(np.array([100.] * 5), np.array([100.5] * 5), np.array([99.5] * 5), np.array([100.] * 5), 0, -1, 1.0, 3.0, 10)
check(not w["done"] and w["reason"] == "open", "not enough bars -> trade stays open (never closed early)")

# ---- SF signal on a synthetic stock: RSI <= 25 then a close above the prior 5-session high ----
px = np.r_[np.full(40, 100.0), 100 - np.arange(1, 16) * 2.5, [64, 63.5, 64.5, 63, 70]]
t = pd.bdate_range("2026-10-01", periods=len(px))
b = pd.DataFrame(dict(time=t, open=px, high=px + 0.3, low=px - 0.3, close=px, live=True))
sig, risk, r, a = RU.sf_signal(b)
check(sig[-1] and sig.sum() == 1, "SF: fires on the bounce close above the prior 5-session high after RSI <= 25")
check(not RU.sf_signal(b.assign(live=False))[0].any(), "SF: no signal outside the universe (no future / turnover / price)")
b2 = b.copy(); b2.loc[b2.index[-1], ["close", "high"]] = [64.4, 64.7]
check(not RU.sf_signal(b2)[0][-1], "SF: no signal when the close is not above the prior 5-session high")

# ---- CM signal: weekly RSI crosses 75, eligible, bottom-third liquidity ----
wk = np.r_[np.full(30, 100.0) + rng.normal(0, 0.5, 30), 100 + np.arange(1, 9) * 4.0]
bw = pd.DataFrame(dict(time=pd.date_range("2026-01-02", periods=len(wk), freq="W-FRI"), open=wk - 1, high=wk + 1, low=wk - 2, close=wk,
                       elig=True, liq_rank=0.2))
s1 = RU.cm_signal(bw)[0]
r1 = RU.rsi(wk)
check(s1.sum() == 1 and r1[np.argmax(s1)] >= 75 and r1[np.argmax(s1) - 1] < 75, "CM: fires once, on the week RSI crosses 75")
check(not RU.cm_signal(bw.assign(liq_rank=0.5))[0].any() and not RU.cm_signal(bw.assign(elig=False))[0].any(),
      "CM: no signal for liquid (top two-thirds) or ineligible stocks")

# ---- ledger: duplicates prevented, immutability guard ----
d = Path(tempfile.mkdtemp())
new = pd.DataFrame([dict(strategy="SF-CONT-SELL-v1", signal_date=pd.Timestamp("2026-11-12"), symbol="ABC", key="X", close=10.0)])
L1, n1 = RN.append(d, "SF-CONT-SELL-v1", new, pd.Timestamp("2026-11-12"))
L2, n2 = RN.append(d, "SF-CONT-SELL-v1", new, pd.Timestamp("2026-11-13"))
check(n1 == 1 and n2 == 0 and len(L2) == 1 and str(L2.detected_on.iloc[0])[:10] == "2026-11-12",
      "same signal seen on a later run is not added again (first detection date kept)")
RN.guard(d)
m = json.loads((d / "meta.json").read_text()); m["SF-CONT-SELL-v1"]["rule_hash"] = "changed"; (d / "meta.json").write_text(json.dumps(m))
try:
    RN.guard(d); raised = False
except SystemExit:
    raised = True
check(raised, "a changed rule cannot continue an existing ledger (new version id required)")
check(RU.rule_hash("SF-CONT-SELL-v1") != RU.rule_hash("CM-CONT-BUY-v1"), "each strategy has its own rule hash")

# ---- costs ----
c25, c26 = EN.fut_cost("2025-06-02", 0.0003), EN.fut_cost("2026-06-01", 0.0003)
check(abs((c26 - c25) - 0.0003) < 1e-9, "futures STT 0.02 % -> 0.05 % from 1-Apr-2026 (sell side, once per round trip)")

# ---- lifecycle on synthetic data: overlap, ban, executed trade with futures path and roll cost ----
days = pd.bdate_range("2026-11-11", periods=25)
cp = np.r_[100, 99, 98.6, 98.4, 98.2, 98.0, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 84, 83, 82, 81, 80, 79, 78, 77.0]
A = {"K1": pd.DataFrame(dict(time=days, open=cp, high=cp + 0.5, low=cp - 0.5, close=cp, symbol="ABC", value=5e8)),
     "K2": pd.DataFrame(dict(time=days, open=cp, high=cp + 0.5, low=cp - 0.5, close=cp, symbol="BANNED", value=5e8))}
fo = []
for i, dd in enumerate(days):
    for sym in ("ABC", "BANNED"):
        fo.append(dict(date=dd, symbol=sym, kind="STK", expiry=pd.Timestamp("2026-11-24"), token="1" if sym == "ABC" else "2", open=cp[i] * 1.002,
                       high=cp[i] * 1.002 + 0.5, low=cp[i] * 1.002 - 0.5, close=cp[i] * 1.002, settle=cp[i], contracts=100, value=1e7, oi=1e6, lot=500))
        fo.append(dict(date=dd, symbol=sym, kind="STK", expiry=pd.Timestamp("2026-12-29"), token="3" if sym == "ABC" else "4", open=cp[i] * 1.006,
                       high=cp[i] * 1.006 + 0.5, low=cp[i] * 1.006 - 0.5, close=cp[i] * 1.006, settle=cp[i], contracts=50, value=1e7, oi=1e5, lot=500))
fo = pd.DataFrame(fo)
L = pd.DataFrame([dict(strategy="SF-CONT-SELL-v1", signal_date=days[0], symbol="ABC", key="K1", close=100.0, risk=2.0, risk_pct=0.02,
                       detected_on=days[0], signal_id="a"),
                  dict(strategy="SF-CONT-SELL-v1", signal_date=days[2], symbol="ABC", key="K1", close=98.6, risk=2.0, risk_pct=0.02,
                       detected_on=days[2], signal_id="b"),
                  dict(strategy="SF-CONT-SELL-v1", signal_date=days[0], symbol="BANNED", key="K2", close=100.0, risk=2.0, risk_pct=0.02,
                       detected_on=days[0], signal_id="c")])
reg = pd.DataFrame(dict(up=True, r20=0.01), index=days)
bans = {dd: (["BANNED"] if dd == days[1] else []) for dd in days}
T = EN.lifecycle_sf(L, A, fo, days, reg, {}, days[-1], bans).set_index("signal_id")
check(T.loc["b", "status"].startswith("OVERLAP"), "second signal while the first trade is open: OVERLAP, not taken")
check(T.loc["c", "status"].startswith("NOT EXECUTABLE – stock in F&O ban"), "stock in F&O ban on the entry day: NOT EXECUTABLE with reason")
a_ = T.loc["a"]
check(a_["status"].startswith(("TARGET", "STOP", "TIME")) and a_["entry_date"] == days[1] and a_["contract"].endswith("24-Nov-2026"),
      f"executed on the next session in the near contract: {a_['status']}")
check(a_["rolls"] == 1 if pd.Timestamp(a_["exit_date"]) > pd.Timestamp("2026-11-24") else a_["rolls"] == 0, "roll counted when held over the expiry")
exp_fill = round(fo[(fo.date == days[1]) & (fo.token == "1")].open.iloc[0] * (1 - 0.0003), 2)
check(abs(a_["entry_px"] - exp_fill) < 0.011, "SELL fill = futures open minus 0.03 % slippage")
check(a_["exec_R"] < a_["research_R"] + 0.5 and np.isfinite(a_["mfe_R"]) and np.isfinite(a_["mae_R"]), "execution R, MFE and MAE recorded")
# ---- CM lifecycle: locked upper circuit, executed trade on weekly research rules + daily path ----
dd = pd.bdate_range("2026-11-02", periods=70)
cp2 = 100 + np.arange(70) * 0.5
A2 = {k: pd.DataFrame(dict(time=dd, open=cp2, high=cp2 + 1, low=cp2 - 1, close=cp2, symbol=k, value=3e8, volume=1e6)) for k in ("UP", "LOCK")}
EN.WEEKLY = EN.weekly_panels(A2)
sd = EN.WEEKLY["close"].index[0]
e = dd[dd > sd][0]
EN.P_RAW.clear(); EN.P_RAW[(e, "UP")] = (cp2[5], cp2[5] + 1, cp2[5] - 1, cp2[4], 3e8); EN.P_RAW[(e, "LOCK")] = (110.0, 110.0, 110.0, 100.0, 3e8)
L2 = pd.DataFrame([dict(strategy="CM-CONT-BUY-v1", signal_date=sd, symbol=k, key=k, close=float(cp2[4]), risk=3.0, risk_pct=0.03,
                        detected_on=sd, signal_id=k) for k in ("UP", "LOCK")])
T2 = EN.lifecycle_cm(L2, A2, dd, reg.reindex(dd).fillna(True), {}, dd[-1], {}, {"UP"}).set_index("signal_id")
check(T2.loc["LOCK", "status"].startswith("NOT EXECUTABLE – locked at the upper circuit"), "cash: open = high = low above the previous close -> NOT EXECUTABLE")
u = T2.loc["UP"]
check(u["status"].startswith("TARGET") and u["entry_date"] == e and bool(u["in_momentum_portfolio"]), f"cash: executed next session, {u['status']}, momentum overlap flagged")
check(abs(u["entry_px"] - round(cp2[5] * 1.0005, 2)) < 0.011 and abs(u["participation_pct"] - 100 * 5e5 / 3e8) < 1e-3,
      "cash: BUY fill = open + 0.05 % slippage; ₹5 lakh order participation recorded")
print(f"{ok} shadow checks passed")
