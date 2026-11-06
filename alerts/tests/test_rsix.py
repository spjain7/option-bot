"""6-Nov RSIX-001: daily RSI(7) oversold + bullish candle + ADX<20 -> BUY-STOP above the candle high.
Parity with research/program/rsix.py masks; pending -> triggered -> target; cancel; expiry.   python alerts/tests/test_rsix.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from alerts import rulebook as RB, four_hour as FH  # noqa: E402
from crude import indicators as I  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


def daily(n=700, seed=5):
    r = np.random.default_rng(seed)
    t = pd.bdate_range("2023-01-02", periods=n)
    c = 100 * np.exp(np.cumsum(r.normal(0, 0.015, n)))
    o = c * (1 + r.normal(0, 0.006, n))
    return pd.DataFrame(dict(time=t, open=o, high=np.maximum(o, c) * (1 + abs(r.normal(0, 0.006, n))),
                             low=np.minimum(o, c) * (1 - abs(r.normal(0, 0.006, n))), close=c, volume=1000.0))


d = daily()
ff = RB.features(d)
b, s = RB.raw(ff, "RSIX", "7/30")
# research definition (rsix.setup_masks E1 L30 'bull' & filter ADXL), written out independently
o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
r7 = I.rsi(d["close"], 7).values
pos = (c - l) / np.where(h - l > 0, h - l, np.nan)
res = (pd.Series(r7).rolling(3).min().values <= 30) & (c > o) & (pos >= 0.5) & (np.nan_to_num(I.adx(d, 14).values, nan=99) < 20)
check(b.sum() > 3 and np.array_equal(b, res), f"live RSIX mask == research mask ({int(b.sum())} setups)")

i = int(np.flatnonzero(b[220:])[-1]) + 220
fr = d.iloc[:i + 1].reset_index(drop=True)
NOW = fr["time"].iloc[-1] + pd.Timedelta(days=1, hours=10)
C = dict(symbol="ZINC28NOV26FUT", token="9", expiry="2026-12-28", lot=5000, tick=0.05)
H, Lw, A = float(fr["high"].iloc[-1]), float(fr["low"].iloc[-1]), float(RB.features(fr)["atr"].iloc[-1])
keep = dict(RB.RULES)
RB.RULES = {"RB_MCX_1d_RSIX_BUY": keep["RB_MCX_1d_RSIX_BUY"]}
q = {"ltp": (H + Lw) / 2}
st, m = {"day": {"date": str(NOW.date())}}, []
out = RB.run(st, m, None, "ZINC", "MCX", C, {"1d": fr}, fr, q, NOW, 5000, "MCX")
rec = st["fourh"]["open"][0]
check(out["RB_MCX_1d_RSIX_BUY"].startswith("SENT (pending") and "BUY ABOVE" in m[0] and rec["pending"], "price below trigger -> BUY ABOVE call, pending")
check(abs(rec["trigger"] - H) < 0.06 and abs((rec["entry"] - rec["stop"]) - 1.5 * A) < 0.1
      and abs((rec["target"] - rec["entry"]) - 3 * 1.5 * A) < 0.2, "trigger = candle high · SL 1.5 ATR · T2 3R")
check(not st.get("ledger"), "no ledger row until triggered")


class Api:
    def __init__(self, ltp): self.ltp = ltp
    def quotes(self, dd): return {"9": {"ltp": self.ltp}}


op = lambda ex, now: True  # noqa: E731
m2 = []
FH.track(st, m2, Api(rec["trigger"] + 0.05), NOW + pd.Timedelta(hours=2), op)
check(not rec["pending"] and "TRIGGERED" in m2[0] and st["ledger"][0]["status"] == "OPEN", "price through trigger -> TRIGGERED + ledger row")
m3 = []
FH.track(st, m3, Api(rec["target"] + 0.1), NOW + pd.Timedelta(days=1), op)
check(m3 and "target" in m3[0] and st["fourh"]["closed"][-1]["result_R"] > 2.9, "then target -> exit +3R")

st2, m4 = {"day": {"date": str(NOW.date())}}, []
RB.run(st2, m4, None, "ZINC", "MCX", C, {"1d": fr}, fr, q, NOW, 5000, "MCX")
m5 = []
FH.track(st2, m5, Api(Lw - 0.1), NOW + pd.Timedelta(hours=1), op)
check(not st2["fourh"]["open"] and "cancelled" in m5[0], "low of the setup candle breaks first -> cancelled, no trade")

st3, m6 = {"day": {"date": str(NOW.date())}}, []
RB.run(st3, m6, None, "ZINC", "MCX", C, {"1d": fr}, fr, q, NOW, 5000, "MCX")
for k in range(1, 4):
    m7 = []
    FH.track(st3, m7, Api((H + Lw) / 2), NOW + pd.Timedelta(days=k), op)
check(not st3["fourh"]["open"] and "expired" in m7[0], "trigger not reached in 3 sessions -> expired")

st4, m8 = {"day": {"date": str(NOW.date())}}, []
o4 = RB.run(st4, m8, None, "ZINC", "MCX", C, {"1d": fr}, fr, {"ltp": H + 2 * A}, NOW, 5000, "MCX")
check(not m8 and "ran" in o4["RB_MCX_1d_RSIX_BUY"], "already > 0.5 ATR past the trigger -> no chase")
check("CONFIRMED SETUP" in m[0] and "ACTIONABLE CALL" in m2[0] and "INVALIDATED" in m5[0], "lifecycle: confirmed setup -> actionable -> invalidated")
fn = st["funnel"][str(NOW.date())]["RB_MCX_1d_RSIX_BUY"]
check(fn["setup"] == 1 and fn["triggered"] == 1 and fn["sent"] == 0, "funnel: setup and actionable counted separately")
from alerts import funnel as FN  # noqa: E402
check("[reversal BUY]" in FN.summary(st), "daily summary separates reversal BUY statistics")
# early warning: RSI extreme + ADX<20 but no bullish candle -> info message only
ffw = RB.features(d); b7, _ = RB.raw(ffw, "RSIX", "7/30")
r7s = I.rsi(d["close"], 7); adxv = ffw["adx"].values
cand = [k for k in range(240, len(d)) if r7s.iloc[k - 2:k + 1].min() <= 30 and adxv[k] < 20 and not b7[k]]
if cand:
    fe = d.iloc[:cand[-1] + 1].reset_index(drop=True)
    st5, m9 = {"day": {"date": str(NOW.date())}}, []
    RB.run(st5, m9, None, "ZINC", "MCX", C, {"1d": fe}, fe, q, NOW, 5000, "MCX")
    check(len(m9) == 1 and "EARLY WARNING" in m9[0] and "NOT a trade" in m9[0] and not st5.get("ledger")
          and not st5.get("fourh", {}).get("open"), "early warning: info line only, no record, no ledger")
RB.RULES = keep
print(f"\n{ok} checks passed")
