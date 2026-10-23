"""Offline tests for the Telegram trading-call engine (calls/). Run: python tests/test_calls.py"""
import sys, re, tempfile, json
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import calls.engine as E
from calls import rules as R, options as O
import market as M

OK, SENT = [], []
E.STATE_FILE = Path(tempfile.mkdtemp()) / "calls.json"


def check(name, cond):
    assert cond, name
    OK.append(name); print("✅", name)


def hourly(n=330, drift=0.0004, end=pd.Timestamp("2026-10-21 13:00"), price=6000.0, seed=4, breakout=True, hours=range(9, 23), noise=0.003):
    rng = np.random.default_rng(seed)
    times = [t for t in pd.date_range(end - pd.Timedelta(days=60), end, freq="h") if t.hour in hours and t.weekday() < 5][-n:]
    c = price * np.exp(np.cumsum(rng.normal(drift, noise, len(times))))
    if breakout:
        c[-6:-1] = c[-7]; c[-1] = c[-7] * (1.004 if drift > 0 else 0.996)
    o = np.r_[c[0], c[:-1]]
    vol = np.full(len(c), 1000.0); vol[-1] = 3000
    return pd.DataFrame(dict(time=times, open=o, high=np.maximum(o, c) * 1.001, low=np.minimum(o, c) * 0.999, close=c, volume=vol))


def daily(n=300, drift=0.002, end=pd.Timestamp("2026-10-20"), price=6000.0, seed=2, kick=1.01):
    rng = np.random.default_rng(seed)
    t = pd.bdate_range(end=end, periods=n)
    c = price * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
    c[-1] = max(c[-56:-1].max() * kick, c[-1]) if drift > 0 else min(c[-56:-1].min() / kick, c[-1])
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame(dict(time=t, open=o, high=np.maximum(o, c) * 1.002, low=np.minimum(o, c) * 0.998, close=c, volume=1000.0))


MASTER = pd.DataFrame([
    dict(name="CRUDEOIL", exch_seg="MCX", instrumenttype="FUTCOM", symbol="CRUDEOIL19NOV26FUT", token="11", lotsize=100,
         expiry_dt=pd.Timestamp("2026-11-19")),
    dict(name="CRUDEOIL", exch_seg="MCX", instrumenttype="FUTCOM", symbol="CRUDEOIL18DEC26FUT", token="12", lotsize=100,
         expiry_dt=pd.Timestamp("2026-12-18")),
    dict(name="NIFTY", exch_seg="NFO", instrumenttype="FUTIDX", symbol="NIFTY27OCT26FUT", token="21", lotsize=65,
         expiry_dt=pd.Timestamp("2026-10-27")),
    dict(name="NIFTY", exch_seg="NFO", instrumenttype="FUTIDX", symbol="NIFTY24NOV26FUT", token="22", lotsize=65,
         expiry_dt=pd.Timestamp("2026-11-24"))])


class Fake:
    def __init__(self, h=None, d=None, ltp=None):
        self.h, self.d, self.ltp = h or {}, d or {}, ltp or {}

    def candles(self, ex, tok, iv, frm, to):
        src = self.h if iv == "ONE_HOUR" else self.d
        x = src.get(str(tok))
        return None if x is None else x[(x.time >= frm) & (x.time <= to)].copy()

    def quotes(self, et):
        return {t: {"ltp": self.ltp[t]} for toks in et.values() for t in toks if t in self.ltp}


def run(api, now):
    SENT.clear()
    return E.run(api, MASTER, now=pd.Timestamp(now), send=lambda m: SENT.append(m))


def reset():
    E.STATE_FILE.unlink(missing_ok=True)


def test_intraday_call_and_followups():
    reset(); E.SET["options"] = False; E.MCX[:] = ["CRUDEOIL"]; E.NSE[:] = []
    h = hourly()
    api = Fake(h={"11": h}, ltp={"11": float(h.close.iloc[-1])})
    e = run(api, "2026-10-21 14:05")
    calls = [m for m in SENT if "BUY CRUDEOIL FUT • Intraday" in m]
    check("intraday BUY call sent with entry, SL, T1, T2, qty and warning",
          calls and all(x in calls[0] for x in ("Entry:", "Stop-loss:", "Target 1:", "Target 2:", "Risk per lot", "Square off", "Unproven")))
    check("call names the traded contract and its expiry (>5 trading days left)", "CRUDEOIL19NOV26FUT" in calls[0] and "19-Nov-2026" in calls[0])
    run(api, "2026-10-21 14:20")
    check("same candle never alerted twice", not any("• Intraday #" in m for m in SENT))
    c = e.s["open"][0]
    api.ltp["11"] = c["t1"] + 1; run(api, "2026-10-21 14:35")
    check("T1 follow-up moves SL to cost", any("TARGET 1 HIT" in m and "cost" in m for m in SENT))
    api.ltp["11"] = c["entry"] - 1; run(api, "2026-10-21 14:50")
    check("exit at cost after T1", any("Exit at cost" in m for m in SENT))


def test_sell_allowed_and_rsi_rule():
    reset(); E.MCX[:] = ["CRUDEOIL"]; E.NSE[:] = []
    h = hourly(drift=-0.0004)
    api = Fake(h={"11": h}, ltp={"11": float(h.close.iloc[-1])})
    run(api, "2026-10-21 14:05")
    sig, why = R.intraday(h)
    if sig and sig.get("blocked"):
        check("RSI < 30 turns a SELL into NO TRADE (not reversed)", any("NO TRADE • SELL" in m for m in SENT)
              and not any("BUY CRUDEOIL FUT" in m for m in SENT))
    else:
        check("intraday SELL call allowed (both directions)", any("SELL CRUDEOIL FUT • Intraday" in m for m in SENT))
    hot = hourly(drift=0.004, seed=5, noise=0.001)
    s2, _ = R.intraday(hot)
    check("RSI > 70 never produces a BUY call and is not reversed",
          s2 is None or (s2.get("blocked") and s2["side"] == "BUY") or s2["rsi"] <= 70)


def test_squareoff():
    reset(); E.MCX[:] = ["CRUDEOIL"]; E.NSE[:] = []
    h = hourly(); api = Fake(h={"11": h}, ltp={"11": float(h.close.iloc[-1])})
    e = run(api, "2026-10-21 14:05")
    api.ltp["11"] = e.s["open"][0]["entry"] + 0.1
    run(api, "2026-10-21 23:01")
    check("intraday call squared off at 23:00 (MCX)", any("Square-off" in m for m in SENT))


def test_positional_flow():
    reset(); E.MCX[:] = ["CRUDEOIL"]; E.NSE[:] = []
    d = daily()
    api = Fake(d={"11": d}, ltp={})
    e = run(api, "2026-10-21 09:01")                                   # yesterday's candle closed
    calls = [m for m in SENT if "BUY CRUDEOIL FUT • Positional" in m]
    check("positional BUY call for the next open with chase limit, SL rule and channel exit",
          calls and all(x in calls[0] for x in ("next session open", "≤", "2×ATR", "20-day", "Unproven")))
    p = e.s["pending"][0]
    api.ltp["11"] = p["signal_close"] + 0.1 * p["atr"]
    e = run(api, "2026-10-21 09:20")
    check("entry activated at the live price with SL recalculated from it",
          any("ENTRY ACTIVE" in m for m in SENT) and abs(e.s["open"][0]["sl"] - (api.ltp["11"] - 2 * p["atr"])) < 1e-6)
    api.ltp["11"] = e.s["open"][0]["sl"] - 1
    run(api, "2026-10-21 11:00")
    check("positional SL follow-up", any("SL hit (positional)" in m for m in SENT))
    reset(); e = run(Fake(d={"11": d}), "2026-10-21 09:01"); p = e.s["pending"][0]
    api2 = Fake(d={"11": d}, ltp={"11": p["signal_close"] + 2 * p["atr"]})
    run(api2, "2026-10-21 09:20")
    check("positional call cancelled when price ran too far (chase)", any("CANCELLED" in m and "chase" in m for m in SENT))


def test_nifty_both_markets():
    reset(); E.MCX[:] = []; E.NSE[:] = ["NIFTY"]
    h = hourly(price=25000.0, end=pd.Timestamp("2026-10-21 13:00"), hours=range(9, 16))
    h["time"] = h["time"] + pd.Timedelta(minutes=15)
    api = Fake(h={"22": h, "21": h}, ltp={"22": float(h.close.iloc[-1]), "21": float(h.close.iloc[-1])})
    run(api, "2026-10-21 14:20")
    m = [x for x in SENT if "NIFTY" in x and ("• Intraday" in x or "NO TRADE" in x)]
    check("NIFTY futures intraday handled (NSE F&O, lot 65, contract with >2 trading days)",
          m and "NSE F&O" in m[0] and "NIFTY27OCT26FUT" in m[0])
    E.MCX[:] = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]; E.NSE[:] = ["NIFTY", "BANKNIFTY"]


def test_option_idea():
    def fake_chain(api, master, name, expiry, spot, width_pct=0.08, exch="NFO"):
        ks = np.arange(spot * 0.97, spot * 1.03, 50)
        rows = [dict(K=k, typ=t, token=f"{t}{int(k)}", symbol=f"{name}{int(k)}{t}", ltp=100, bid=99, ask=101, mid=100, ba_pct=2,
                     oi=1000, volume=100, lotsize=65, iv=15, delta=(0.5 - (k - spot) / spot * 10) * (1 if t == "CE" else -1),
                     gamma=0.001, theta=-1, vega=1) for k in ks for t in ("CE", "PE")]
        return dict(df=pd.DataFrame(rows), expiry=expiry, lot=65)
    M.build_chain, M.expiries = fake_chain, lambda master, name, exch="NFO": [pd.Timestamp("2026-11-24"), pd.Timestamp("2026-12-29")]
    M.dte = lambda e: (pd.Timestamp(e) - pd.Timestamp("2026-10-21")).days
    o = O.idea(None, None, "NIFTY", "NFO", "BUY", 25000.0, 100, 100, 200, "intraday", 5000)
    check("option idea: CE for a BUY, ~0.55 delta, SL/T1/T2, cost and lots", o["typ"] == "CE" and abs(o["delta"] - 0.55) < 0.1
          and o["sl"] < o["entry"] < o["t1"] < o["t2"] and "lots" in o)
    p = O.idea(None, None, "NIFTY", "NFO", "SELL", 25000.0, 100, None, None, "positional", 5000)
    check("option idea: PE for a SELL on a monthly expiry ≥15 days for positional", p["typ"] == "PE" and p["expiry"] == "24-Nov-2026")


def test_no_orders_and_flags():
    src = "\n".join(f.read_text() for f in (ROOT / "calls").glob("*.py"))
    check("calls package uses no order API", not re.search(r"placeOrder|modifyOrder|cancelOrder|place_order", src))
    import config, runner
    run_src = (ROOT / "runner.py").read_text()
    check("engine D has its own flag guarding its only call site", config.CALLS_ENABLED is True
          and len(re.findall(r"calls_engine\.run\(", run_src)) == 1 and "if C.CALLS_ENABLED and mode in" in run_src)
    check("hourly Engine C stays disabled", config.MCXT_ENABLED is False)


if __name__ == "__main__":
    for t in (test_intraday_call_and_followups, test_sell_allowed_and_rsi_rule, test_squareoff, test_positional_flow,
              test_nifty_both_markets, test_option_idea, test_no_orders_and_flags):
        t()
    print(f"\nALL {len(OK)} TRADING-CALL CHECKS PASSED")
