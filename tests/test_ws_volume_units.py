"""7-Nov-2026: WebSocket NFO volume is in shares, Angel REST candles in lots (6-Nov hourly check: NIFTY ratio 64.99, lot 65;
BPCL 1977.7, lot 1975). WebSocket bars must be converted to REST units before the check and before being joined to REST
history; NFO without a known lot -> REST (never mixed units); MCX unchanged.   python tests/test_ws_volume_units.py"""
import json
import sys
import tempfile
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wsbars as WB  # noqa: E402
import angel as A  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


d = tempfile.mkdtemp()
pd.DataFrame([dict(token="61471", exch="NFO", name="NIFTY", symbol="NIFTY23NOV26FUT", expiry="2026-11-23", lot=65),
              dict(token="573422", exch="MCX", name="CRUDEOIL", symbol="CRUDEOIL19NOV26FUT", expiry="2026-11-19", lot=100)]
             ).to_csv(Path(d) / "tokens.csv", index=False)
# old-format option rows appended without a lot column must not break the reader
with open(Path(d) / "tokens.csv", "a") as f:
    f.write("99999,NFO,NIFTY,NIFTY23NOV2625000CE,2026-11-23\n")

check(WB.lot("61471", d) == 65 and WB.lot("573422", d) == 100, "lot read from the collector's token map")
check(WB.lot("99999", d) is None and WB.lot("12345", d) is None, "unknown / missing lot -> None")

# ---- REST vs WebSocket bars for the same 15-min buckets (NIFTY, shares vs lots) ----
t = pd.date_range("2026-11-09 09:15", periods=4, freq="15min")
rest = pd.DataFrame(dict(time=t, open=24000.0, high=24010.0, low=23990.0, close=24005.0, volume=[1000.0, 1200, 900, 1100]))
ws = rest.copy(); ws["volume"] = rest["volume"] * 65
okv, note = WB.verify_ok(rest, ws)
check(okv is not None and not okv and "volume ratio 65" in note, "unconverted: check fails on 'volume ratio 65' (what 6-Nov logs showed)")
okc, note = WB.verify_ok(rest, WB.rest_units(ws, "61471", "NFO", d))
check(bool(okc) and "volume ratio 1.0" in note, "converted: check passes (ratio 1.0)")
check(WB.rest_units(ws, "99999", "NFO", d) is None, "NFO with unknown lot -> None (REST is used, units never mixed)")
mcx = rest.copy()
check(WB.rest_units(mcx, "573422", "MCX", d).equals(mcx), "MCX bars unchanged (6-Nov CRUDEOIL ratio 1.0)")
check(WB.rest_units(ws, "61471", "NFO", d) is not ws and ws["volume"].iloc[0] == 65000, "input frame not modified")

# ---- end to end through Angel._ws_series: today's WebSocket bars joined to REST history in the same units ----
now = pd.Timestamp("2026-11-09 10:20")
for i, m in enumerate(pd.date_range("2026-11-09 09:15", "2026-11-09 10:19", freq="min")):
    with open(Path(d) / "bars_61471.csv", "a") as f:
        f.write(f"{m:%Y-%m-%d %H:%M},24000,24001,23999,24000,{65 * 10},1000000\n")   # 10 lots / minute in shares
json.dump(dict(start="2026-11-09 09:14:00", tokens=["61471"], last_tick={"NFO": str(now)}), open(Path(d) / "status.json", "w"))


class Api(A.Angel):
    def __init__(self):
        self._setup(cache_dir=tempfile.mkdtemp(), ws_dir=d, ws=True)

    def _now(self):
        return now

    def _candles(self, exch, token, interval, frm, to):      # REST: lots (10 per minute -> 150 per 15 min)
        tt = pd.date_range("2026-11-09 09:15", "2026-11-09 10:00", freq="15min")
        return pd.DataFrame(dict(time=tt, open=24000.0, high=24001.0, low=23999.0, close=24000.0, volume=150.0))

    def _day_hist(self, kind, exch, token, interval, frm, day0):
        return pd.DataFrame(dict(time=[day0 - pd.Timedelta(hours=5)], open=1.0, high=1.0, low=1.0, close=1.0, volume=150.0))


api = Api()
out = api._ws_series("NFO", "61471", "FIFTEEN_MINUTE", now - pd.Timedelta(days=3), now, "candles")
full = out[(out["time"] >= pd.Timestamp("2026-11-09 09:15")) & (out["time"] < pd.Timestamp("2026-11-09 10:15"))]
check(out is not None and api.stats["ws_hits"] == 1, "NFO WebSocket bars accepted after the hourly check (no REST fallback)")
check((full["volume"] == 150).all() and out["volume"].iloc[0] == 150, f"today's bars in lots like the history: {full['volume'].tolist()}")
print(f"{ok} WebSocket volume-unit checks passed")
