import pandas as pd
import share


def test_nearest_and_rows():
    m = pd.DataFrame([
        {"exch_seg": "MCX", "instrumenttype": "FUTCOM", "name": "GOLD", "token": "1", "symbol": "GOLD05OCT26FUT", "expiry_dt": pd.Timestamp("2026-10-05")},
        {"exch_seg": "MCX", "instrumenttype": "FUTCOM", "name": "GOLD", "token": "2", "symbol": "GOLD04DEC26FUT", "expiry_dt": pd.Timestamp("2026-12-04")},
        {"exch_seg": "MCX", "instrumenttype": "FUTCOM", "name": "GOLDM", "token": "3", "symbol": "GOLDM03NOV26FUT", "expiry_dt": pd.Timestamp("2026-11-03")},
    ])
    assert share.nearest(m, "GOLD", pd.Timestamp("2026-10-28 10:00")) == ("2", "GOLD04DEC26FUT", "2026-12-04")
    assert share.nearest(m, "SILVER", pd.Timestamp("2026-10-28")) is None
    meta = {("MCX", "2"): ("mcx-gold", "GOLD04DEC26FUT", "2026-12-04"), ("NSE", "99926000"): ("nifty-50", None, None)}
    got = share.rows([{"exchange": "MCX", "symbolToken": "2", "ltp": 143000, "close": 142000, "high": 1, "low": 1, "exchFeedTime": "t"},
                      {"exchange": "NSE", "symbolToken": "99926000", "ltp": 24000, "close": 23900},
                      {"exchange": "NSE", "symbolToken": "999", "ltp": 5}], meta)
    assert [g["key"] for g in got] == ["mcx-gold", "nifty-50"] and got[0]["prev_close"] == 142000


def test_push_off_without_secrets(monkeypatch):
    monkeypatch.delenv("PR_FEED_URL", raising=False); monkeypatch.delenv("PR_FEED_KEY", raising=False)
    assert share.push(None, None, None) == "off"
