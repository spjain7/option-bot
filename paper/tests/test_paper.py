"""Paper engine tests (synthetic data). Run: python -m paper.tests.test_paper"""
import copy, tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from paper import mcx_daily as P
from research import engine_daily as ED

OK = []
CFG0 = copy.deepcopy(P.CFG)


def check(name, cond):
    assert cond, name
    OK.append(name); print("✅", name)


def frame(n=500, seed=3, drift=0.0012, price=60000.0):
    rng = np.random.default_rng(seed)
    c = price * np.exp(np.cumsum(rng.normal(drift, 0.012, n)))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.002, n))
    h = np.maximum(o, c) * (1 + abs(rng.normal(0, 0.004, n))); l = np.minimum(o, c) * (1 - abs(rng.normal(0, 0.004, n)))
    return pd.DataFrame(dict(time=pd.bdate_range("2020-01-01", periods=n), open=o, high=h, low=l, close=c, volume=1000.0))


def fresh(**over):
    P.CFG.clear(); P.CFG.update(copy.deepcopy(CFG0)); P.CFG.update(over)
    d = Path(tempfile.mkdtemp())
    return P.Book(d / "s.json", d / "l.jsonl")


def test_matches_research_engine():
    fresh(rsi_block=False, chase_atr=1e9, risk_pct=1e-4, max_open_risk_pct=1e9, group_risk_pct=1e9,
          max_capital_use=1e9, max_positions=99, daily_loss_pct=1e9, max_stop_pct=9, capital=1e12)
    fr = {"GOLD": frame(), "COPPER": frame(seed=5, price=800.0, drift=-0.0008)}
    book, _ = P.replay(fr, "2020-01-01", sides=(1, -1), state_dir=tempfile.mkdtemp())
    c = pd.DataFrame(book.s["closed"])
    r = []
    for n, f in fr.items():
        g = f.copy()
        for k in ("open", "high", "low", "close"):
            g["raw_" + k] = g[k]
        g["offset"], g["roll"], g["contract"] = 0.0, False, "X"
        r.append(ED.run(n, ED.add_indicators(g), ED.STRATS["C"]))
    r = pd.concat(r); r = r[r.exit_reason != "open_at_end"]
    a = set(zip(c.instrument, c.signal_time)); b = set(zip(r.instrument, pd.to_datetime(r.signal_time).dt.strftime("%Y-%m-%d")))
    check(f"paper engine reproduces research trades ({len(a & b)}/{len(b)})", len(b) > 3 and len(a & b) >= 0.9 * len(b))


def _bar_with_breakout(rsi_hot):
    f = P.indicators(frame(seed=11, drift=0.002))
    i = len(f) - 1
    f.loc[i, "close"] = f.loc[i, "hi_in"] * 1.01
    f.loc[i, "high"] = max(f.loc[i, "high"], f.loc[i, "close"])
    f.loc[i, "rsi"] = 75 if rsi_hot else 60
    return f, i


def test_rsi_rule_blocks_without_reversal():
    book = fresh(capital=1e9)
    f, i = _bar_with_breakout(True)
    e = P.Engine(P.ReplayProvider({}), book)
    e.evaluate("GOLD", f, i, dict(symbol="GOLD05DEC26FUT", expiry="05-Dec-2026", now=f.time.iloc[i]))
    st = [a["state"] for a in e.alerts]
    check("RSI > 70 turns a BUY breakout into NO TRADE", "NO TRADE" in st and "CONFIRMED PAPER SIGNAL" not in st)
    check("blocked BUY is not reversed into a SELL", not book.s["pending"] and all(a["direction"] == "BUY" for a in e.alerts
                                                                                 if a["state"] != "WATCHLIST"))


def test_confirmed_alert_fields_and_dedup():
    book = fresh(capital=1e9)
    f, i = _bar_with_breakout(False)
    e = P.Engine(P.ReplayProvider({}), book)
    ctr = dict(symbol="GOLD05DEC26FUT", expiry="05-Dec-2026", now=f.time.iloc[i])
    e.evaluate("GOLD", f, i, ctr); e.evaluate("GOLD", f, i, ctr)
    conf = [a for a in e.alerts if a["state"] == "CONFIRMED PAPER SIGNAL"]
    check("same candle alerted once (dedup)", len(conf) == 1)
    t = conf[0]["text"]
    need = ["MCX", "GOLD05DEC26FUT", "05-Dec-2026", "1 day", "Signal candle", "Data as of", "BUY", "Entry rule",
            "Estimated entry", "Stop", "Exit condition", "Risk per lot", "Suggested quantity", "round-trip costs", "Why", "⚠️",
            "Not advice"]
    check("confirmed alert shows every required field", all(x in t for x in need))
    check("no guaranteed-target wording", "guaranteed profit" not in t.lower() and "sure shot" not in t.lower())


def test_chase_cancels_entry():
    book = fresh(capital=1e9)
    f, i = _bar_with_breakout(False)
    e = P.Engine(P.ReplayProvider({}), book)
    e.evaluate("GOLD", f, i, dict(symbol="X", expiry="x", now=f.time.iloc[i]))
    nxt = f.iloc[[i]].copy(); nxt["time"] = f.time.iloc[i] + pd.Timedelta(days=1)
    nxt["open"] = f.close.iloc[i] + 2 * f.atr.iloc[i]
    g = pd.concat([f, nxt], ignore_index=True)
    e.on_open("GOLD", g, len(g) - 1)
    check("open > 0.5 ATR beyond signal close -> NO TRADE (chase), no entry",
          not book.s["open"] and any(a["state"] == "NO TRADE" and "chase" in " ".join(a.get("blocks", [])) for a in e.alerts))


def test_stale_and_exposure():
    book = fresh(capital=1e9)
    f, i = _bar_with_breakout(False)
    e = P.Engine(P.ReplayProvider({}), book)
    e.evaluate("GOLD", f, i, dict(symbol="X", expiry="x", now=f.time.iloc[i] + pd.Timedelta(days=10)))
    check("stale data -> NO TRADE", any("stale" in " ".join(a.get("blocks", [])) for a in e.alerts))
    book = fresh(capital=1e9, group_risk_pct=1e-9)
    e = P.Engine(P.ReplayProvider({}), book)
    e.evaluate("GOLD", f, i, dict(symbol="X", expiry="x", now=f.time.iloc[i]))
    check("correlated-group limit -> NO TRADE", any("group risk" in " ".join(a.get("blocks", [])) for a in e.alerts))


if __name__ == "__main__":
    for t in (test_matches_research_engine, test_rsi_rule_blocks_without_reversal, test_confirmed_alert_fields_and_dedup,
              test_chase_cancels_entry, test_stale_and_exposure):
        t()
    P.CFG.clear(); P.CFG.update(CFG0)
    print(f"\nALL {len(OK)} PAPER-ENGINE CHECKS PASSED")
