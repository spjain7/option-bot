"""Offline test of the MCXE-009 incremental Angel mode (fake API, no network, no credentials):
appends only new bars, keeps full history, no duplicates, untouched when the API returns nothing.
python research/mcxe009/test_incremental.py"""
import os
import sys
import tempfile
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.adapters import angel_hist as AH  # noqa: E402


class FakeAPI:
    def __init__(self, new):
        self.new, self.calls = new, []

    def candles(self, exch, token, iv, frm, to):
        self.calls.append((iv, frm, to))
        return self.new[self.new.time >= frm].reset_index(drop=True) if self.new is not None else None


def bars(start, n):
    t = pd.date_range(start, periods=n, freq="5min")
    return pd.DataFrame(dict(time=t, open=1.0, high=2.0, low=0.5, close=1.5, volume=10))


def run(new):
    with tempfile.TemporaryDirectory() as d:
        AH.OUT = Path(d)
        (Path(d) / "MCX").mkdir()
        old = bars("2026-11-03 09:00", 100)
        old.assign(symbol="CRUDEOIL19NOV26FUT", name="CRUDEOIL", expiry="2026-11-19").to_csv(Path(d) / "MCX/CRUDEOIL19NOV26FUT_FIVE_MINUTE.csv", index=False)
        master = pd.DataFrame([dict(token="1", symbol="CRUDEOIL19NOV26FUT", name="CRUDEOIL", exch_seg="MCX", instrumenttype="FUTCOM",
                                    expiry="19NOV2026")])
        AH.contracts = lambda m, names: m.assign(expiry_dt=pd.Timestamp("2026-11-19"))
        import angel
        angel.now_ist = lambda: pd.Timestamp("2026-11-06 23:55")
        os.environ["RESEARCH_INCREMENTAL"] = "1"
        api = FakeAPI(new)
        AH.fetch_all(api, master, ["CRUDEOIL"], intervals=("FIVE_MINUTE",))
        out = pd.read_csv(Path(d) / "MCX/CRUDEOIL19NOV26FUT_FIVE_MINUTE.csv", parse_dates=["time"])
        return old, out, api


old, out, api = run(pd.concat([bars("2026-11-03 09:00", 100).iloc[-10:], bars("2026-11-04 09:00", 50)]))
assert len(api.calls) == 1, api.calls                                    # one call, not 17 pages
assert out.time.is_unique and out.time.is_monotonic_increasing
assert len(out) == 150 and out.time.min() == old.time.min()               # history kept + 50 new bars appended
old, out2, api = run(None)
assert len(out2) == 100                                                   # API empty -> file unchanged
print("ok incremental mode: 1 API call, history kept, 50 new bars appended, no duplicates; empty API leaves file intact")
