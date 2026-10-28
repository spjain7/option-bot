"""28-Oct option-sell rule changes (approved): intraday DTE window, MCX near-expiry skip, flip needs OI backing,
no PE sell just under resistance / CE sell just above support; futures alerts skip zero-volume contracts.
python -m tests.test_sell_rules"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
import runner as R  # noqa: E402
import market as M  # noqa: E402

ok = 0


def check(c, name):
    global ok
    assert c, name
    ok += 1
    print("✅", name)


# rule 3 – flip from sideways must be backed by positioning (28-Oct GOLD: Short buildup, OI +0.33 %)
f, why = R.flip_confirmed("BULLISH", "NEUTRAL", {"label": "Short buildup", "oi_chg": 0.33})
check(not f and "Long buildup" in why, "GOLD 28-Oct replay: sideways -> bullish on Short buildup OI +0.33 % -> blocked")
check(not R.flip_confirmed("BULLISH", "NEUTRAL", {"label": "Long buildup", "oi_chg": 0.4})[0], "bullish flip, Long buildup but OI only +0.4 % -> blocked")
check(R.flip_confirmed("BULLISH", "NEUTRAL", {"label": "Long buildup", "oi_chg": 1.3})[0], "bullish flip with Long buildup OI +1.3 % -> allowed")
check(R.flip_confirmed("BEARISH", "NEUTRAL", {"label": "Short buildup", "oi_chg": 1.0})[0], "bearish flip with Short buildup OI +1.0 % -> allowed")
check(R.flip_confirmed("BULLISH", "BULLISH", None)[0], "an established direction (not a fresh flip) is not affected")
check(not R.flip_confirmed("BEARISH", "NEUTRAL", None)[0], "fresh flip with no OI data -> blocked")

# rule 2 – support / resistance proximity (0.3 %)
ch = {"pivots": {"P": 143501.0, "PDH": 144265.0, "R1": 144600.0}, "call_wall": 145000, "put_wall": 140000}
check(R.near_level(ch, 144142.0, "BULLISH") is not None, "GOLD 28-Oct replay: PE sell at 144,142 just under prev high 144,265 (0.09 %) -> blocked")
check(R.near_level(ch, 143700.0, "BULLISH") is None, "PE sell 0.4 % below resistance -> allowed")
ng = {"pivots": {"P": 288.0}, "call_wall": 300, "put_wall": 290}
check(R.near_level(ng, 292.0, "BEARISH") is None, "NG CE sell at 292 with support 290 (0.7 % away) -> allowed")
check(R.near_level(ng, 290.5, "BEARISH") is not None, "CE sell at 290.5 just above support 290 -> blocked")

# rule 1 / MCX near expiry – config + try_open gate
check(C.INTRADAY_MAX_DTE == 7 and C.MCX_MIN_DTE == 3, "intraday window: expiry 3..7 days for MCX, ≤ 7 days for all intraday sells")


class St:
    s = {"positions": [], "closed": []}


bot = object.__new__(R.Bot)
bot.st = St()
msgs = []
bot.why = lambda n, w: msgs.append(w)
bot.blocked = lambda mode: None
bot.view = lambda *a, **k: msgs.append("VIEW") or None
far = (pd.Timestamp.now().normalize() + pd.Timedelta(days=23)).strftime("%Y-%m-%d")
near = (pd.Timestamp.now().normalize() + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
bot.try_open("NATURALGAS", "intraday", far, "ONE_HOUR", exch="MCX")
check(msgs and "too little time decay" in msgs[-1] and "VIEW" not in msgs,
      "NG 28-Oct replay: intraday sell on a 23-day option -> not sent (reason logged)")
msgs.clear()
bot.try_open("NATURALGAS", "intraday", near, "ONE_HOUR", exch="MCX")
check(msgs == ["VIEW"], "intraday sell on a 5-day option -> goes on to the normal checks")
msgs.clear()
bot.try_open("NIFTY", "monthly", far, "ONE_DAY")
check(msgs == ["VIEW"], "positional (monthly) sells are not affected by the intraday DTE window")

# futures alerts: zero-volume contracts
from alerts import engine as E  # noqa: E402
h = pd.DataFrame(dict(time=pd.date_range("2026-10-01 09:00", periods=150, freq="h"), open=1.0, high=1.0, low=1.0, close=1.0, volume=0.0))
info = {}
E._breakouts(E.new_state(), [], info, "ZINC", "MCX", {}, h, None, pd.Timestamp("2026-10-28 12:00"), None, None)
check(info.get("not_traded") and "zero volume" in info["breakout"], "ZINC / ALUMINIUM mega contract with zero volume -> skipped with a clear reason")
rep = {"instruments": {"ZINC": dict(contract="Z", not_traded=True), "GOLD": dict(contract="G")}, "errors": []}
m = E.startup_msg(pd.Timestamp("2026-10-29 09:00"), rep)
check("Not traded (zero volume, no calls possible): ZINC" in m and "with data now: GOLD" in m, "startup message lists zero-volume contracts separately")
print(f"sell-rules: {ok} passed")
