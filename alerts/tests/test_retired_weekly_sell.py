"""25-Nov-2026 (owner): retired strategies kept in the ledger but left out of scorecards; MCX 3h EMA 13/48 and the stock
3h MACD / EMA 9/21 SELL retired; weekly breakdown SELL live with support / resistance levels.
python -m alerts.tests.test_retired_weekly_sell"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import strategies as ST, scorecard as SCD, rulebook as RB, candle_setups as CS, breakout as BO  # noqa: E402

ok = 0


def check(n, c):
    global ok
    assert c, n
    ok += 1; print("✅", n)


check("retired list holds the 6 strategies", set(ST.RETIRED) == {"STK_HANGMAN", "1-hour BO (EXPERIMENTAL)", "FH_STK_SELL", "3-hour MACD",
                                                                  "3-hour EMAX", "MCX_EMA1348"})
check("MCX 3h EMA 13/48 off: no new setups", ST.S["MCX_EMA1348"][0] == "OFF" and "MCX_EMA1348" in CS.NO_NEW)
check("stock 3h MACD / EMA 9/21 SELL fully off (not even logged)",
      RB.RULES["RB_STK_3h_MACD0_SELL"]["status"] == "OFF" and RB.RULES["RB_STK_3h_EMA921_SELL"]["status"] == "OFF")
check("weekly breakdown SELL is live", ST.S["BO_1w_SELL"][0] == "LIVE" and ("1w", "SELL") not in ST.shadow_bo())
row = lambda key, typ, R: dict(key=key, type=typ, side="SELL", cat="FUTURES", status="CLOSED", entry=100.0, sl=101.0, exit=100.0 - R, note="")
st = {"ledger": [row("STK_HANGMAN|X|1", "x", -1), row("MCX_EMA1348|GOLD|1", "x", -1), row("RB|r|TCS|1", "3-hour MACD", -1),
                 row("SILVER|3h|2026-11-20", "Swing", 2)]}
b = SCD.build(st)
shown = set(b["LIVE"]) | set(b["SHADOW"]) | set(b["PAPER"])
check("scorecard leaves retired strategies out, keeps the rest", "BO_3h_SELL" in shown and not shown & set(ST.RETIRED))
check("retired calls stay in the ledger (record kept)", len(st["ledger"]) == 4)

# weekly SELL levels: SL above the breakdown week's high (capped at 2 daily ATR), target next support or 3R
w = pd.DataFrame(dict(time=pd.date_range("2025-01-06", periods=60, freq="W-MON")))
w["close"] = np.r_[np.linspace(100, 120, 40), np.linspace(119, 104, 20)]
w["high"] = w.close + 2; w["low"] = w.close - 2; w["open"] = w.close; w["volume"] = 1.0
d = pd.DataFrame(dict(time=pd.bdate_range(end="2026-02-27", periods=60)))
d["close"] = 104.0; d["high"] = 105.0; d["low"] = 103.0; d["open"] = 104.0       # daily ATR 2
sig = dict(atr=4.0, close=104.0)
w.loc[10, "low"] = 90.0                                                                  # a support far below
x = BO.weekly_sell_levels(w, d, sig)
check("SL = breakdown week high + 0.1 wATR (106.4 -> 2.4 away, under the 2-daily-ATR cap of 4)", abs(x["k"] * 4.0 - 2.4) < 1e-6)
check("target = 52-week low support when >= 2R away (90 -> 14 / 2.4 = 5.8R)", abs(x["tr"] - 14.0 / 2.4) < 1e-6 and "support" in x["why"])
w2 = w.copy(); w2.loc[w2.index[-1], "high"] = 120.0
x2 = BO.weekly_sell_levels(w2, d, sig)
check("week high too far -> SL capped at 2 daily ATR", abs(x2["k"] * 4.0 - 4.0) < 1e-6 and "daily ATR" in x2["why"])
w3 = w.copy(); w3["low"] = 103.5; w3.loc[w3.index[-1], "low"] = 103.0
x3 = BO.weekly_sell_levels(w3, d, sig)
check("no support 2R away -> 3R target", x3["tr"] == 3.0)
print(f"{ok} checks passed")
