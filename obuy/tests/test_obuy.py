"""Offline tests for the option-buy alert engine. Run: python -m obuy.tests.test_obuy"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from obuy import engine as E
from research.search import obuy_month as RM

ok = fail = 0
def check(c, name):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("FAIL", name)

def market(seed=3, start="2026-09-01", end="2026-10-22"):
    rng = np.random.default_rng(seed); rows = []; px = 1000.0; oi = 1e6
    for d in pd.bdate_range(start, end):
        for k in range(25):
            t = d + pd.Timedelta(hours=9, minutes=15 + 15 * k); o = px
            px *= 1 + rng.normal(0, 0.003); oi *= 1 + rng.normal(0.0003, 0.004)
            rows.append([t, o, max(o, px) * 1.001, min(o, px) * 0.999, px, int(rng.integers(1000, 9000)), oi])
    return pd.DataFrame(rows, columns="time open high low close volume oi".split())

# 1. live intraday check = the backtest's rule, bar for bar
df = RM.features(market())
res = RM.intraday_signals(df, "stock")["I2_vwap_rsi_oi"]
check(len(res) > 0 and all(E.intraday_signal(df, i) == d for i, d in res), f"intraday: live rule matches the backtest ({len(res)} signals)")
check(E.intraday_signal(df, 10) == 0, "intraday: not enough history -> no signal")
late = df.index[df["time"].dt.strftime("%H:%M") == "14:45"][-1]
check(E.intraday_signal(df, late) == 0, "intraday: no entries after 14:30")

# 2. positional rule
d = pd.DataFrame({"day": pd.bdate_range("2026-09-01", periods=25), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                  "volume": 1000.0, "oi": 1e5})
d.loc[24, ["close", "high", "volume", "oi"]] = [103.0, 103.5, 2000.0, 1.05e5]
d["hh20"], d["vol20"] = d["high"].rolling(20).max().shift(1), d["volume"].rolling(20).mean().shift(1)
d["ll20"] = d["low"].rolling(20).min().shift(1); d["chg"], d["oichg"] = d["close"].pct_change(), d["oi"].pct_change()
check(E.positional_signal(d) == 1, "positional: 20-day high + 2x volume + OI up -> BUY CE")
d2 = d.copy(); d2.loc[24, "oi"] = 0.95e5; d2["oichg"] = d2["oi"].pct_change()
check(E.positional_signal(d2) == 0, "positional: OI falling -> no signal")
d3 = d.copy(); d3.loc[24, "volume"] = 1100.0
check(E.positional_signal(d3) == 0, "positional: normal volume -> no signal")

# 3. liquidity
check(E.liquid(*E.option_quote({"ltp": 50, "tradeVolume": 100, "depth": {"buy": [{"price": 49.8}], "sell": [{"price": 50.2}]}}))[0], "liquidity: tight spread ok")
check(not E.liquid(*E.option_quote({"ltp": 50, "tradeVolume": 100, "depth": {"buy": [{"price": 48}], "sell": [{"price": 52}]}}))[0], "liquidity: 8% spread skipped")
check(not E.liquid(*E.option_quote({"ltp": 50, "tradeVolume": 0}))[0], "liquidity: not traded today skipped")

# 4. tracking: SL, target, time exit, costs
class Api:
    def __init__(self, prices): self.p = prices
    def quotes(self, ex): return {t: {"ltp": self.p.get(t, 0), "tradeVolume": 10} for t in ex["NFO"]}
now = pd.Timestamp("2026-10-23 11:02")
base = {"dir": 1, "name": "X", "K": 100, "lot": 100, "kind": "stock", "entry": 100.0, "sl": 70.0, "tg": 160.0, "exit_at": "2026-10-23 15:15", "symbol": "X", "id": 1}
st = {"open": [{**base, "token": "a"}, {**base, "token": "b", "id": 2}, {**base, "token": "c", "id": 3}], "closed": []}
msgs = []
E.manage(Api({"a": 65, "b": 170, "c": 120}), st, now, msgs)
check([a["why_exit"] for a in st["closed"]] == ["stop-loss hit", "target hit"] and len(st["open"]) == 1, "track: SL and target closed, other still open")
check(st["closed"][0]["exit"] == 65 and st["closed"][0]["ret"] < -0.35 and st["closed"][1]["exit"] == 160 and st["closed"][1]["ret"] > 0.5,
      "track: premium gapped below SL exits at the LTP (65, not the SL 70); target at its level; costs reduce returns")
E.manage(Api({"c": 120}), st, pd.Timestamp("2026-10-23 15:17"), msgs)
check(st["closed"][-1]["why_exit"] == "time exit" and not st["open"] and len(msgs) == 3, "track: time exit at 15:15")
check(E.exit_time(pd.Timestamp("2026-10-23 09:32"), "positional") == pd.Timestamp("2026-10-27 15:15"), "positional exit: 3rd session (skips the weekend)")

# 5. end-to-end scan with a fake Angel API: alert sent once, caps, scorecard
master = pd.DataFrame([
    {"name": "ABC", "exch_seg": "NFO", "instrumenttype": "FUTSTK", "expiry_dt": pd.Timestamp("2026-10-27"), "token": "F1", "lotsize": 100, "symbol": "ABC26OCT26FUT", "strike": -1},
    *[{"name": "ABC", "exch_seg": "NFO", "instrumenttype": "OPTSTK", "expiry_dt": pd.Timestamp(e), "token": f"O{e[5:7]}{k}{t}", "lotsize": 100,
       "symbol": f"ABC{e}{k}{t}", "strike": k * 100.0} for e in ("2026-10-27", "2026-11-24") for k in range(800, 1300, 10) for t in ("CE", "PE")]])
fut = market(seed=11, start="2026-10-14", end="2026-10-23")
sig_rows = [i for i, _ in RM.intraday_signals(RM.features(fut), "stock")["I2_vwap_rsi_oi"]]
class FakeApi:
    def quotes(self, ex):
        return {t: {"ltp": 25.0, "opnInterest": 1e6, "tradeVolume": 10, "depth": {"buy": [{"price": 24.9}], "sell": [{"price": 25.1}]}} for t in ex["NFO"]}
    def candles(self, ex, tok, iv, frm, to):
        if iv == "ONE_DAY":
            return None
        return fut[(fut["time"] >= frm) & (fut["time"] + pd.Timedelta(minutes=15) <= to)][["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    def oi_history(self, ex, tok, iv, frm, to):
        return None if iv == "ONE_DAY" else fut[["time", "oi"]]
if sig_rows:
    feats = RM.features(fut)
    t_sig = feats.iloc[sig_rows[-1]]["time"] + pd.Timedelta(minutes=17)
    st = E.new_state()
    st, m1, rep = E.scan(FakeApi(), master, t_sig, st)
    check(any(("CE  ·" in x or "PE  ·" in x) and "BUY" in x for x in m1) and st["open"] and st["open"][0]["expiry"] >= f"{t_sig + pd.Timedelta(days=3):%Y-%m-%d}", "scan: alert sent with an expiry >= 3 days away")
    check("Entry" in m1[0] and "SL" in m1[0] and "Target" in m1[0] and "WHY" in m1[1] and "investment advice" in m1[1],
          "scan: clean call message + separate WHY message")
    st, m2, _ = E.scan(FakeApi(), master, t_sig + pd.Timedelta(minutes=1), st)
    check(not any("BUY CALL" in x or "BUY PUT" in x for x in m2), "scan: same stock not alerted twice in a day")
    st, m3, _ = E.scan(FakeApi(), master, t_sig.normalize() + pd.Timedelta(hours=15, minutes=32), st)
    check(any("SCORECARD" in x for x in m3) and not st["open"], "scan: time exit + daily scorecard after 15:30")
else:
    check(False, "synthetic market produced no signal for the end-to-end test")
print(f"obuy: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
