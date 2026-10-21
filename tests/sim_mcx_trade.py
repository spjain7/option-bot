"""Offline test of Engine C (MCX buy/sell). Run:  python tests/sim_mcx_trade.py"""
import sys, math
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config as C, greeks as G, market, notify, mcx_trade as X

SENT = []
notify.send = lambda text, *a, **k: (SENT.append(text), print("\n" + "─" * 60 + "\n" + text))
CLOCK = {"now": pd.Timestamp("2026-10-21 14:05")}
for mod in (market, X):
    mod.now_ist = lambda: CLOCK["now"]

# name: (price, trend per hour %, option iv) ; trend +: breakout up, -: breakdown, 0: range
UND = {"GOLD": (78000.0, +0.10, 0.15), "CRUDEOIL": (6000.0, -0.06, 0.35), "SILVER": (95000.0, 0, 0.25)}
LIVE = {}


def build_master():
    rows, tok = [], 500000
    for n, (s, _, _) in UND.items():
        tok += 1
        rows.append(dict(token=str(tok), symbol=f"{n}19NOV26FUT", name=n, expiry="19NOV2026", strike="-1",
                         lotsize="1", instrumenttype="FUTCOM", exch_seg="MCX"))
        step = 50 if n == "CRUDEOIL" else 500
        for k in np.arange(s * 0.9, s * 1.1, step):
            k = round(k / step) * step
            for typ in ("CE", "PE"):
                tok += 1
                rows.append(dict(token=str(tok), symbol=f"{n}14NOV26{int(k)}{typ}", name=n, expiry="14NOV2026",
                                 strike=f"{k * 100:.6f}", lotsize="1", instrumenttype="OPTFUT", exch_seg="MCX"))
    m = pd.DataFrame(rows)
    m["expiry_dt"] = pd.to_datetime(m["expiry"], format="%d%b%Y")
    m["strike"] = pd.to_numeric(m["strike"]); m["lotsize"] = pd.to_numeric(m["lotsize"])
    return m


MASTER = build_master()
BY = MASTER.set_index("token").to_dict("index")


def series(name, end):
    s, tr, _ = UND[name]
    t = pd.date_range(end=end, periods=400, freq="h")
    rng = np.random.default_rng(len(name))
    base = s * (1 + tr * np.linspace(-1, 0, 400)) + rng.normal(0, s * 0.0008, 400)
    if tr:                                                       # last candle breaks out of a 5-hour pause
        base[-6:-1] = base[-7]
        base[-1] = base[-7] * (1 + np.sign(tr) * 0.004)
    hi, lo = base * 1.0012, base * 0.9988
    vol = np.full(400, 1000.0); vol[-1] = 2500
    return pd.DataFrame(dict(time=t, open=np.r_[base[0], base[:-1]], high=np.maximum(hi, np.r_[base[0], base[:-1]]),
                             low=np.minimum(lo, np.r_[base[0], base[:-1]]), close=base, volume=vol))


class FakeAngel:
    calls = 0

    def candles(self, ex, tok, interval, frm, to):
        FakeAngel.calls += 1
        n = BY[str(tok)]["name"]
        return series(n, to.floor("h") - pd.Timedelta(hours=1))

    def quotes(self, et):
        out = {}
        for t in et["MCX"]:
            r = BY[str(t)]; n = r["name"]
            F = LIVE.get(n) or float(series(n, CLOCK["now"].floor("h") - pd.Timedelta(hours=1))["close"].iloc[-1])
            if r["instrumenttype"] == "FUTCOM":
                out[str(t)] = {"ltp": F}; continue
            K, typ = r["strike"] / 100, r["symbol"][-2:]
            T = market.time_to_expiry(r["expiry_dt"], "MCX")
            p = max(G.price(F, K, T, UND[n][2], C.RISK_FREE, typ), 0.5)
            out[str(t)] = {"ltp": round(p, 2), "opnInterest": 500,
                           "depth": {"buy": [{"price": round(p * 0.99, 2)}], "sell": [{"price": round(p * 1.01, 2)}]}}
        return out


def main():
    X.STATE_FILE = ROOT / "tests" / "_sim_mcx.json"
    X.STATE_FILE.unlink(missing_ok=True)
    C.MCXT_UNDERLYINGS = {"GOLD": "GOLDM", "CRUDEOIL": "CRUDEOILM", "SILVER": "SILVERM"}
    api = FakeAngel()

    t = X.run(api, MASTER)
    sides = {p["name"]: p["side"] for p in t.s["open"]}
    print("\nsignals:", sides)
    assert sides.get("GOLD") == "BUY", sides
    assert sides.get("CRUDEOIL") == "SELL", sides
    assert "SILVER" not in sides, "range market must not give a call"
    g = next(p for p in t.s["open"] if p["name"] == "GOLD")
    c = next(p for p in t.s["open"] if p["name"] == "CRUDEOIL")
    assert g["sl"] < g["entry"] < g["t1"] < g["t2"] and c["sl"] > c["entry"] > c["t1"] > c["t2"]
    assert g["opt"] and g["opt"]["typ"] == "CE" and c["opt"] and c["opt"]["typ"] == "PE"
    assert g["lots"] >= 0 and g["mini_lots"] >= g["lots"]
    assert any("Option buy" in m and "MCX BUY – GOLD" in m for m in SENT)

    # same candle again -> no duplicate call
    n = len(SENT); X.run(api, MASTER); assert len(SENT) == n, "duplicate alert"

    # GOLD runs to T1 then T2; CRUDEOIL hits SL
    CLOCK["now"] = pd.Timestamp("2026-10-21 14:20")
    LIVE["GOLD"] = g["t1"] + 1
    LIVE["CRUDEOIL"] = c["sl"] + 1
    t = X.run(api, MASTER)
    assert any("T1 hit – GOLD" in m for m in SENT) and any("SL hit" in m and "CRUDEOIL" in m for m in SENT)
    LIVE["GOLD"] = g["t2"] + 1
    CLOCK["now"] = pd.Timestamp("2026-10-21 14:35")
    t = X.run(api, MASTER)
    assert any("T2 hit" in m and "GOLD" in m for m in SENT)
    gc = next(p for p in t.s["closed"] if p["name"] == "GOLD")
    assert gc["pnl_rs_per_lot"] > 0 and "opt_pnl_rs_per_lot" in gc
    cc = next(p for p in t.s["closed"] if p["name"] == "CRUDEOIL")
    assert cc["pnl_rs_per_lot"] < 0

    # end-of-day summary once
    CLOCK["now"] = pd.Timestamp("2026-10-21 23:05")
    LIVE.clear(); n = len(SENT); X.run(api, MASTER); X.run(api, MASTER)
    assert sum("MCX Buy/Sell –" in m for m in SENT[n:]) == 1

    # outside entry window -> no new calls
    t = X.MCXTrader(api, MASTER); assert t.scan() == []
    X.STATE_FILE.unlink(missing_ok=True)
    print("\nMCX BUY/SELL SIMULATION PASSED ✅")


if __name__ == "__main__":
    main()
