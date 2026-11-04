"""MFE / MAE tracking on the live ledger (alerts/report.track_excursions)."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from alerts import report as RP  # noqa: E402

st = {}
RP.add(st, key="k1", mark_key="111", cat="FUTURES", name="GOLD", side="BUY", entry=100.0, sl=98.0, target=104.0, time="2026-11-04 10:00")
RP.add(st, key="k2", mark_key="111", cat="FUTURES", name="GOLD", side="SELL", entry=100.0, sl=101.0, target=98.0, time="2026-11-04 10:00")
RP.add(st, key="k3", mark_key="222", cat="FUTURES", name="ZINC", side="BUY", entry=50.0, sl=49.0, target=None, time="2026-11-04 10:00")
bars = pd.DataFrame(dict(time=pd.to_datetime(["2026-11-04 09:45", "2026-11-04 10:00", "2026-11-04 10:15"]),
                         open=[99, 100, 101], high=[110, 101.5, 103], low=[90, 99.2, 100.5], close=[100, 101, 102.5]))
assert RP.track_excursions(st, "111", bars, "15-min candle highs/lows") == 2
b, s_ = st["ledger"][0], st["ledger"][1]
assert b["best_px"] == 103 and b["worst_px"] == 99.2, "bars before the call time are ignored"
assert b["mfe_R"] == 1.5 and b["mae_R"] == -0.4 and not b["t1_hit"] and not b["stop_touched"], b
assert s_["mfe_R"] == 0.8 and s_["mae_R"] == -3.0 and s_["stop_touched"], s_
more = pd.DataFrame(dict(time=pd.to_datetime(["2026-11-04 10:30"]), open=[102.5], high=[104.2], low=[102], close=[104]))
RP.track_excursions(st, "111", more, "15-min candle highs/lows")
assert b["best_px"] == 104.2 and b["worst_px"] == 99.2 and b["t1_hit"], "running extremes kept across scans"
assert b["excursion_measure"] == "15-min candle highs/lows"
assert "mfe_R" not in st["ledger"][2], "other contracts untouched"
st["ledger"][0]["status"] = "CLOSED"
RP.track_excursions(st, "111", pd.DataFrame(dict(time=pd.to_datetime(["2026-11-04 11:00"]), open=[1], high=[200], low=[1], close=[1])), "x")
assert b["best_px"] == 104.2, "closed rows are frozen"
assert RP.track_excursions(st, "111", None, "x") == 0
print("ALL EXCURSION CHECKS PASSED")
