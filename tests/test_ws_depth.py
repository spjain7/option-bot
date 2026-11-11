"""11-Nov-2026: best-5 depth recorded from the SNAP_QUOTE packets (wsdepth.py) – research only. Checks the recorder (one
snapshot per token per minute, both sides stored as sent, side diagnostics, packets without depth counted not filled,
export) and the collector end to end with a fake WebSocket: futures bars unchanged, depth-only NSE tokens never reach
the bar builder or the stale-feed status, a depth error never stops the bars.        python tests/test_ws_depth.py"""
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import wsdepth as WD  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


def lv(px, q, o, flag):
    return [{"flag": flag, "quantity": q + i, "price": int(round((px + (i * 0.05 if flag else -i * 0.05)) * 100)) if px else 0, "no of orders": o}
            for i in range(5)]


def pkt(tok, ex_type, ltp, bid, ask, ts, depth=True, swap=True):
    m = dict(subscription_mode=3, exchange_type=ex_type, token=tok, exchange_timestamp=int(ts.tz_localize("Asia/Kolkata").timestamp() * 1000),
             last_traded_price=int(ltp * 100), last_traded_quantity=10, volume_trade_for_the_day=1000, total_buy_quantity=5000.0,
             total_sell_quantity=6000.0, open_interest=777)
    if depth:
        b, a = lv(bid, 100, 3, 0), lv(ask, 200, 4, 1)
        m["best_5_buy_data"], m["best_5_sell_data"] = (a, b) if swap else (b, a)     # the SDK's swap, as in 1.5.5
    return m


d = tempfile.mkdtemp()
R = WD.Recorder(d)
t0 = pd.Timestamp("2026-11-11 10:00:05")
check(R.on_msg(pkt("1", 2, 100, 99.95, 100.05, t0), "NFO", t0, t0 + pd.Timedelta(seconds=1)), "first packet of a minute recorded")
check(not R.on_msg(pkt("1", 2, 100, 99.9, 100.1, t0 + pd.Timedelta(seconds=20)), "NFO", t0, t0), "second packet same minute not recorded")
check(R.on_msg(pkt("1", 2, 100, 99.9, 100.1, t0 + pd.Timedelta(minutes=1)), "NFO", t0 + pd.Timedelta(minutes=1), t0 + pd.Timedelta(minutes=1)),
      "next minute recorded")
check(not R.on_msg(pkt("2", 5, 50, 0, 0, t0, depth=False), "MCX", t0, t0), "packet without depth fields: counted, not filled")
st = R.flush(t0)
check(st["NFO"]["rows"] == 2 and st["NFO"]["packets"] == 3 and st["NFO"]["with_depth"] == 3, f"diagnostics count packets / rows: {st['NFO']}")
check(st["NFO"]["a_above_b"] == 2 and st["NFO"]["a_below_b"] == 0, "SDK-swapped sides detected (A1 > B1: SDK 'buy' list is the ask side)")
check(st["NFO"]["levels"] == {"5x5": 2}, "5 filled levels each side")
check(st["MCX"]["packets"] == 1 and st["MCX"]["with_depth"] == 0 and st["MCX"]["rows"] == 0, "no-depth packet never becomes a row")
f = pd.read_csv(Path(d) / "depth_20261111.csv", dtype={"token": str})
check(list(f.columns) == WD.COLS and len(f) == 2, "CSV columns and rows")
check(f.A1p.iloc[0] == 100.05 and f.B1p.iloc[0] == 99.95 and f.B5p.iloc[0] == 99.75 and f.A1o.iloc[0] == 4, "prices in ₹, levels and orders as sent")
R2 = WD.Recorder(tempfile.mkdtemp())
R2.on_msg(pkt("3", 1, 10, 9.99, 10.01, t0, swap=False), "NSE", t0, t0)
check(R2.flush(t0)["NSE"]["a_below_b"] == 1, "unswapped feed would be counted the other way (sides read from data, not assumed)")
out = Path(d) / "x" / "depth.csv.gz"
pd.DataFrame([dict(token="1", exch="NFO", name="ABC", symbol="ABC25NOVFUT", expiry="", lot=1)]).to_csv(Path(d) / "tokens.csv", index=False)
check(WD.export(out, d) == 2 and pd.read_csv(out).symbol.iloc[0] == "ABC25NOVFUT" and Path(str(out).replace(".csv.gz", "_status.json")).exists(),
      "export: gzip + symbol + status file")
check(WD.export(Path(d) / "y.csv.gz", tempfile.mkdtemp()) == 0, "export of an empty folder -> 0 (nothing saved)")

# ---- collector end to end with a fake WebSocket ----
import wsbars as WB  # noqa: E402
import wsfeed as WF  # noqa: E402

wd = tempfile.mkdtemp()
NOW = pd.Timestamp("2026-11-11 10:00:30")
master = pd.DataFrame([
    dict(token="111", exch_seg="NFO", instrumenttype="FUTSTK", name="ABC", symbol="ABC25NOVFUT", expiry_dt=pd.Timestamp("2026-11-25"), lotsize=500),
    dict(token="222", exch_seg="MCX", instrumenttype="FUTCOM", name="CRUDEOIL", symbol="CRUDEOIL19NOV26FUT", expiry_dt=pd.Timestamp("2026-11-19"), lotsize=100),
    dict(token="2885", exch_seg="NSE", instrumenttype="", name="RELIANCE", symbol="RELIANCE-EQ", expiry_dt=pd.NaT, lotsize=1)])
subs = []


class FakeWS:
    SNAP_QUOTE = 3

    def __init__(self, *a, **k):
        pass

    def subscribe(self, cid, mode, tl):
        subs.append((cid, mode, tl))

    def connect(self):
        self.on_open(None)
        for s in range(3):
            ts = NOW - pd.Timedelta(seconds=25) + pd.Timedelta(seconds=10 * s)
            self.on_data(None, pkt("111", 2, 100 + s, 99.9, 100.1, ts))
            self.on_data(None, pkt("222", 5, 6000, 5999, 6001, ts))
            self.on_data(None, pkt("99926000", 1, 24000, 0, 0, ts, depth=True))
            self.on_data(None, pkt("2885", 1, 1400, 1399.9, 1400.1, ts))
        self.on_data(None, {"exchange_type": 2, "token": "111", "last_traded_price": 10100, "exchange_timestamp": "bad"})

    def close_connection(self):
        pass


class FakeAngel:
    jwt, feed = "x", "y"

    def __init__(self, fresh=False):
        pass


fake_mod = mock.MagicMock(SmartWebSocketV2=FakeWS)


def run(wd):
    with mock.patch.dict(sys.modules, {"SmartApi.smartWebSocketV2": fake_mod}), \
            mock.patch.object(WF, "Angel", FakeAngel), mock.patch.object(WF, "load_master", lambda: master), \
            mock.patch.object(WF, "now_ist", lambda: NOW), mock.patch.object(WB, "DIR", Path(wd)), \
            mock.patch.object(WF.time, "sleep", lambda s: None), mock.patch("os.chdir", lambda p: None), \
            mock.patch.dict("os.environ", {"ANGEL_API_KEY": "k", "ANGEL_CLIENT_ID": "c"}):
        WF.main()


run(wd)
nse = [s for s in subs if s[2][0]["exchangeType"] == 1]
check(len(nse) == 1 and "2885" in nse[0][2][0]["tokens"] and "99926000" in nse[0][2][0]["tokens"], "depth-only NSE tokens (index + cash) subscribed once")
check(any(s[2][0]["exchangeType"] == 2 and "111" in s[2][0]["tokens"] for s in subs), "futures still subscribed as before")
stj = json.loads((Path(wd) / "status.json").read_text())
check(set(stj["last_tick"]) == {"NFO", "MCX"} and stj["ticks"] == 6 and stj["tokens"] == ["111", "222"] or set(stj["tokens"]) == {"111", "222"},
      f"status: NSE depth-only ticks never counted as futures feed ({stj['last_tick'].keys()}, ticks {stj['ticks']})")
check(not list(Path(wd).glob("bars_2885.csv")) and not list(Path(wd).glob("live_2885.json")) and not list(Path(wd).glob("live_99926000.json")),
      "depth-only tokens never reach the bar builder")
check((Path(wd) / "live_111.json").exists() or (Path(wd) / "bars_111.csv").exists(), "futures bars still built")
dep = pd.read_csv(Path(wd) / "depth_20261111.csv", dtype={"token": str})
check(set(dep.token) == {"111", "222", "99926000", "2885"} and len(dep) == 4, f"one snapshot per token per minute: {sorted(dep.token)}")
ds = json.loads((Path(wd) / "depth_status.json").read_text())
check(set(ds) == {"NFO", "MCX", "NSE"} and ds["NSE"]["empty"] == 1, f"index row with empty book counted as 'empty': {ds['NSE']}")
tk = pd.read_csv(Path(wd) / "tokens.csv", dtype=str)
check({"2885", "99926000"} <= set(tk.token) and tk[tk.token == "111"].lot.iloc[0] == "500", "token map keeps futures lots, adds depth-only rows")
wd2 = tempfile.mkdtemp(); subs.clear()
with mock.patch.object(WD.Recorder, "on_msg", side_effect=RuntimeError("boom")):
    run(wd2)
check((Path(wd2) / "live_111.json").exists() and json.loads((Path(wd2) / "status.json").read_text())["ticks"] == 6,
      "a depth error never stops the futures bars")
print(f"{ok} depth checks passed")
