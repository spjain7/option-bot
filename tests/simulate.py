"""Offline simulation: fake Angel API with Black-Scholes-priced option chains.
Run:  python tests/simulate.py"""
import sys, math
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import greeks as G, config as C, market, positions, runner, notify, strategy, rsi_alert, flow

SENT = []
notify.send = lambda text, *a, **k: (SENT.append(text), print("\n" + "─" * 60 + "\n" + text))
CLOCK = {"now": pd.Timestamp("2026-09-21 11:20")}
for mod in (market, positions, runner, rsi_alert, flow):
    mod.now_ist = lambda: CLOCK["now"]

UND = {  # name: spot, iv, strike step, lot, trend(+1/-1)
    "NIFTY": [25000.0, 0.12, 50, 75, 1], "BANKNIFTY": [55000.0, 0.14, 100, 35, -1],
    "RELIANCE": [1400.0, 0.30, 10, 500, -1], "HDFCBANK": [1900.0, 0.15, 10, 550, 1],
    "CRUDEOIL": [6000.0, 0.35, 50, 100, -1],
    "SENSEX": [82000.0, 0.16, 100, 20, 1],
}
EXPS = {"NIFTY": ["2026-09-22", "2026-09-29", "2026-10-06", "2026-10-27"],
        "BANKNIFTY": ["2026-09-29", "2026-10-27"], "RELIANCE": ["2026-09-29", "2026-10-27"],
        "HDFCBANK": ["2026-09-29", "2026-10-27"], "SENSEX": ["2026-09-24", "2026-10-29"]}
FUT_STATE = {}       # token -> {"ltp","oi","vol"} overrides for flow tests
CRUDE_DROP = [1.0]
SPOT_TOK = {"NIFTY": "99926000", "BANKNIFTY": "99926009", "RELIANCE": "2885", "HDFCBANK": "1333",
            "SENSEX": "99919000"}


def build_master():
    rows, tok = [], 100000
    for n, (s, iv, step, lot, _) in UND.items():
        if n not in EXPS:
            continue
        if n in ("RELIANCE", "HDFCBANK"):
            rows.append(dict(token=SPOT_TOK[n], symbol=f"{n}-EQ", name=n, expiry="", strike="-1", lotsize="1",
                             instrumenttype="", exch_seg="NSE"))
        itype = "IDX" if n in C.INDEX_TOKENS else "STK"
        seg = "BFO" if n == "SENSEX" else "NFO"
        for e in EXPS[n]:
            ed = pd.Timestamp(e)
            if ed == max(x for x in map(pd.Timestamp, EXPS[n]) if x.month == ed.month):
                tok += 1
                rows.append(dict(token=str(tok), symbol=f"{n}{ed:%d%b%y}FUT".upper(), name=n, expiry=ed.strftime("%d%b%Y").upper(),
                                 strike="-1", lotsize=str(lot), instrumenttype="FUT" + itype, exch_seg=seg))
            for k in np.arange(s * 0.85, s * 1.15, step):
                k = round(k / step) * step
                for typ in ("CE", "PE"):
                    tok += 1
                    rows.append(dict(token=str(tok), symbol=f"{n}{ed:%d%b%y}{int(k)}{typ}".upper(), name=n,
                                     expiry=ed.strftime("%d%b%Y").upper(), strike=f"{k*100:.6f}", lotsize=str(lot),
                                     instrumenttype="OPT" + itype, exch_seg=seg))
    rows.append(dict(token="900001", symbol="CRUDEOIL19OCT26FUT", name="CRUDEOIL", expiry="19OCT2026", strike="-1",
                     lotsize="100", instrumenttype="FUTCOM", exch_seg="MCX"))
    for k in range(4800, 7250, 50):                      # MCX crude options (on the Oct future), expiry 15 Oct
        for typ in ("CE", "PE"):
            tok += 1
            rows.append(dict(token=str(tok), symbol=f"CRUDEOIL15OCT26{k}{typ}", name="CRUDEOIL", expiry="15OCT2026",
                             strike=f"{k*100:.6f}", lotsize="1", instrumenttype="OPTFUT", exch_seg="MCX"))
    m = pd.DataFrame(rows).drop_duplicates("token")
    m["expiry_dt"] = pd.to_datetime(m["expiry"], format="%d%b%Y", errors="coerce")
    m["strike"] = pd.to_numeric(m["strike"]); m["lotsize"] = pd.to_numeric(m["lotsize"])
    return m


MASTER = build_master()
BY_TOK = MASTER.set_index("token").to_dict("index")


class FakeAngel:
    def quotes(self, et):
        out = {}
        for ex, toks in et.items():
            for t in toks:
                t = str(t)
                if t == C.VIX_TOKEN:
                    out[t] = {"ltp": 13.5, "close": 13.2}; continue
                name = next((n for n, st in SPOT_TOK.items() if st == t), None)
                if name:
                    out[t] = {"ltp": UND[name][0], "percentChange": 0.6 * UND[name][4]}; continue
                r = BY_TOK[t]; n = r["name"]; s, iv, *_ = UND[n]
                if r["instrumenttype"].startswith("FUT"):
                    f = FUT_STATE.get(t, {})
                    out[t] = {"ltp": f.get("ltp", s), "opnInterest": f.get("oi", 1_050_000),
                              "tradeVolume": f.get("vol", 100000), "percentChange": 0.6 * UND[n][4]}; continue
                K = r["strike"] / 100; typ = r["symbol"][-2:]
                T = market.time_to_expiry(r["expiry_dt"])
                skew = iv * (1 + 0.8 * abs(math.log(K / s)))
                p = max(G.price(s * math.exp(C.RISK_FREE * T), K, T, skew, C.RISK_FREE, typ), 0.05)
                oi = 1e6 * math.exp(-abs(K - s) / (s * 0.02)) * (1.3 if typ == "PE" else 1)
                out[t] = {"ltp": round(p, 2), "opnInterest": oi, "tradeVolume": 5000,
                          "depth": {"buy": [{"price": round(p * 0.995, 2)}], "sell": [{"price": round(p * 1.005, 2)}]}}
        return out

    def candles(self, ex, tok, interval, frm, to):
        if tok == "900001":                                   # MCX crude: flat, then a sharp 6-hour fall
            t = pd.date_range(end=to.floor("h") - pd.Timedelta(hours=1), periods=200, freq="h")
            close = 6000 + np.sin(np.arange(200)) * 15
            close[-6:] = close[-7] - np.arange(1, 7) * 40 * CRUDE_DROP[0]
            return pd.DataFrame(dict(time=t, open=close, high=close + 5, low=close - 5, close=close, volume=100))
        if tok == C.VIX_TOKEN:
            t = pd.bdate_range(end=to.normalize(), periods=250)
            return pd.DataFrame(dict(time=t, open=13, high=14, low=12, close=np.linspace(10, 20, 250), volume=0))
        name = next((n for n, st in SPOT_TOK.items() if st == tok), None)
        if name is None:
            return None
        s, _, _, _, tr = UND[name]
        if interval == "ONE_HOUR":
            t = pd.date_range(end=to.floor("h") - pd.Timedelta(minutes=45), periods=60, freq="h")
        elif interval == "FIFTEEN_MINUTE":
            t = pd.date_range(end=to.floor("15min"), periods=10, freq="15min")
        else:
            t = pd.bdate_range(end=to.normalize(), periods=150)
        close = s * (1 + tr * np.linspace(-0.04, 0, len(t))) + np.sin(np.arange(len(t))) * s * 0.002
        if name == "HDFCBANK" and interval == "ONE_DAY":        # realised vol ~25% > IV 15% -> not rich
            rng = np.random.default_rng(1)
            close = close * np.exp(np.cumsum(rng.normal(0, 0.25 / np.sqrt(252), len(t))))
            close = close / close[-1] * s
        return pd.DataFrame(dict(time=t, open=close, high=close * 1.003, low=close * 0.997, close=close, volume=0))

    def oi_history(self, ex, tok, interval, frm, to):
        t = [to.normalize() - pd.Timedelta(days=d) for d in (3, 2, 1)]
        return pd.DataFrame({"time": t, "oi": [950_000, 980_000, 1_000_000]})


def run_at(ts, fn):
    CLOCK["now"] = pd.Timestamp(ts)
    fn()


def main():
    positions.STATE_FILE = ROOT / "tests" / "_sim_state.json"
    positions.STATE_FILE.unlink(missing_ok=True)
    C.MONTHLY_STOCKS = ["RELIANCE", "HDFCBANK"]
    C.SELL_STYLE, C.CONFIRM_CHECKS, C.INTRADAY_STOCKS, C.GAMMA_BLOCK = "HEDGED", 1, [], "EXTREME"   # part 1: hedged engine
    C.INTRADAY_UNDERLYINGS, C.WEEKLY_UNDERLYINGS = ["NIFTY", "BANKNIFTY"], ["NIFTY"]
    st = positions.Store()
    bot = runner.Bot(FakeAngel(), MASTER, st)

    print("\n=== 11:20 hourly intraday scan ===")
    run_at("2026-09-21 11:20", bot.intraday_scan)
    assert {p["name"] for p in st.open_positions("intraday")} == {"NIFTY", "BANKNIFTY"}
    nifty = st.open_positions("intraday", "NIFTY")[0]
    assert nifty["strategy"] == "Bull Put Spread"
    assert st.open_positions("intraday", "BANKNIFTY")[0]["strategy"] == "Bear Call Spread"
    n0 = len(SENT)
    run_at("2026-09-21 11:35", bot.intraday_scan)           # same hour -> no duplicate
    assert len(SENT) == n0

    print("\n=== 12:50 NIFTY rallies -> put spread decays -> BOOK PROFIT ===")
    UND["NIFTY"][0] = 25250
    run_at("2026-09-21 12:50", bot.monitor)
    assert not st.open_positions("intraday", "NIFTY") and st.s["closed"][-1]["exit_reason"] == "TARGET"

    print("\n=== 13:20 BANKNIFTY rallies toward short call -> ADJUST, then STOP-LOSS ===")
    short_call = [l for l in st.open_positions("intraday", "BANKNIFTY")[0]["legs"] if l["side"] == "SELL"][0]["K"]
    UND["BANKNIFTY"][0] = short_call - 250
    run_at("2026-09-21 13:20", bot.monitor)
    assert "adjust" in st.open_positions("intraday", "BANKNIFTY")[0]["flags"]
    UND["BANKNIFTY"][0] = short_call + 250
    run_at("2026-09-21 13:50", bot.monitor)
    assert st.s["closed"][-1]["exit_reason"] == "SL", st.s["closed"][-1]["exit_reason"]

    print("\n=== 14:45 positional scan (weekly + monthly index + stocks) ===")
    UND["NIFTY"][0], UND["BANKNIFTY"][0] = 25000, 55000
    run_at("2026-09-21 14:45", bot.positional_scan)
    modes = {(p["mode"], p["name"]) for p in st.s["positions"]}
    print(modes)
    assert ("weekly", "NIFTY") in modes and ("monthly", "BANKNIFTY") in modes
    assert ("monthly", "RELIANCE") in modes          # IV 30% rich vs realised
    assert ("monthly", "HDFCBANK") not in modes      # IV 15% not rich enough

    print("\n=== Next day 15:15: intraday none; weekly expiry-day time exit at 14:45 on 22 Sep ===")
    run_at("2026-09-22 14:50", bot.monitor)
    assert not st.open_positions("weekly")

    print("\n=== 15:40 daily report ===")
    run_at("2026-09-25 15:40", bot.report)          # Friday -> weekly summary
    st.save()

    print("\n=== ENGINE B: independent RSI alerts (MCX crude evening) ===")
    rsi_alert.STATE_FILE = ROOT / "tests" / "_sim_rsi.json"; rsi_alert.STATE_FILE.unlink(missing_ok=True)
    C.OPTION_ENGINE_ENABLED = False                       # RSI must still work with options disabled
    n0 = len(SENT)
    run_at("2026-09-21 20:05", lambda: rsi_alert.run(FakeAngel(), MASTER))
    crude = [m for m in SENT[n0:] if "CRUDEOIL" in m]
    assert crude and "OVERSOLD" in crude[0], SENT[n0:]
    n1 = len(SENT)
    run_at("2026-09-21 20:20", lambda: rsi_alert.run(FakeAngel(), MASTER))    # same candle -> no repeat
    assert not [m for m in SENT[n1:] if "CRUDEOIL" in m]
    run_at("2026-09-21 21:05", lambda: rsi_alert.run(FakeAngel(), MASTER))    # next candle -> continuation
    assert [m for m in SENT[n1:] if "CRUDEOIL" in m and "STILL" in m]
    C.OPTION_ENGINE_ENABLED = True

    print("\n=== MCX option selling: on-demand view + hourly scan (evening) ===")
    C.MCX_UNDERLYINGS = ["CRUDEOIL"]
    st.s["positions"].clear()
    n0 = len(SENT)
    def mcx_now():
        assert bot.mcx_open_today()
        bot.mcx_snapshot()
        assert not st.open_positions("intraday", "CRUDEOIL"), "view must never create a call"
        bot.mcx_intraday_scan(force=True)
    run_at("2026-09-21 21:10", mcx_now)
    assert any("MCX VIEW" in m for m in SENT[n0:])
    cr = st.open_positions("intraday", "CRUDEOIL")
    assert cr and cr[0]["exch"] == "MCX" and cr[0]["lot"] == 100, cr
    print("MCX call:", cr[0]["strategy"], [(l["side"], l["K"], l["typ"]) for l in cr[0]["legs"]])
    run_at("2026-09-21 23:05", bot.monitor)                 # MCX intraday exit at 23:00
    assert not st.open_positions("intraday", "CRUDEOIL") and st.s["closed"][-1]["exch"] == "MCX"

    print("\n=== Separation check: engines never import each other ===")
    for f in ("strategy.py", "market.py", "positions.py", "greeks.py"):
        assert "rsi" not in (ROOT / f).read_text().lower(), f
    src = (ROOT / "rsi_alert.py").read_text()
    assert not any(f"import {m}" in src for m in ("strategy", "market", "positions", "greeks"))

    print("\n=== NAKED single-leg sells: confirmation, confidence, clear SL/target ===")
    C.SELL_STYLE, C.CONFIRM_CHECKS, C.GAMMA_BLOCK = "NAKED", 2, "HIGH"
    st.s["positions"].clear(); st.s["bias_hist"] = {}
    n0 = len(SENT)
    run_at("2026-09-23 11:20", bot.intraday_scan)            # 1st hourly check -> only remembered
    assert not st.open_positions("intraday") and len(SENT) == n0, "must not call on first check"
    run_at("2026-09-23 12:20", bot.intraday_scan)            # 2nd check, same direction -> call
    nk = st.open_positions("intraday", "NIFTY")
    assert nk and nk[0]["strategy"] == "Single PE Sell" and len(nk[0]["legs"]) == 1
    p = nk[0]
    gain, loss = p["credit"] - p["target_val"], p["sl_val"] - p["credit"]
    assert gain >= loss - 1e-6 and p["confidence"] >= C.MIN_CONFIDENCE and p["spot_stop"] < p["spot_at_entry"]
    assert any("📍 Support" in m and "Resistance" in m for m in SENT if "SELL NIFTY" in m), "S/R line missing"
    # Crude case from live data: price 8,766 after a big fall -> every support must be BELOW, resistance ABOVE
    txt = runner.sr_text({"F": 8766, "put_wall": 9000, "call_wall": 10000,
                          "pivots": {"S3": 8570, "S2": 8900, "S1": 9071, "P": 9235, "R1": 9400, "R2": 9570, "R3": 9900,
                                     "PDH": 9480, "PDL": 9060}})
    print("Crude S/R:", txt)
    import greeks as _g
    rows = []                                           # NIFTY at 23,414: big far wall 24,500, heavy near 23,500
    for k, oi in [(23450, 2e5), (23500, 9e5), (23600, 6e5), (24500, 1.5e6)]:
        rows.append({"K": k, "typ": "CE", "oi": oi})
    for k, oi in [(23400, 8e5), (23300, 5e5), (22500, 1.4e6)]:
        rows.append({"K": k, "typ": "PE", "oi": oi})
    dfw = pd.DataFrame(rows)
    cw, pw = market._wall(dfw, "CE", 23414, 14, 3 / 365), market._wall(dfw, "PE", 23414, 14, 3 / 365)
    print("NIFTY walls:", pw, cw)
    assert cw == 23500 and pw == 23400
    sup, res = txt.split("|")
    assert "9000" not in sup and "8,570" in sup and "8,900" in res
    print("naked NIFTY:", p["legs"][0]["K"], p["legs"][0]["typ"], "sell", p["credit"], "T", p["target_val"],
          "SL", p["sl_val"], "price stop", p["spot_stop"], "conf", p["confidence"])
    UND["NIFTY"][0] = p["spot_stop"] - 10                    # price falls through the price-stop
    run_at("2026-09-23 12:50", bot.monitor)
    assert st.s["closed"][-1]["exit_reason"] in ("SPOT", "SL")
    assert any("Trade closed" in m and "Today:" in m for m in SENT[-3:]), "P&L tally missing"

    print("\n=== SENSEX (BSE) naked call ===")
    C.INTRADAY_UNDERLYINGS = ["SENSEX"]; st.s["bias_hist"] = {}; UND["NIFTY"][0] = 25000
    run_at("2026-09-22 13:20", bot.intraday_scan); run_at("2026-09-22 14:20", bot.intraday_scan)
    sx = st.open_positions("intraday", "SENSEX")
    assert sx and sx[0]["exch"] == "BFO", "SENSEX call missing"
    print("SENSEX call:", sx[0]["legs"][0]["K"], sx[0]["legs"][0]["typ"], "conf", sx[0]["confidence"])

    print("\n=== ⚡ OI / volume flow alert ===")
    C.INTRADAY_UNDERLYINGS = ["NIFTY", "BANKNIFTY", "SENSEX"]
    fut_tok = MASTER[(MASTER.name == "NIFTY") & (MASTER.instrumenttype == "FUTIDX")].sort_values("expiry_dt").iloc[0]["token"]
    FUT_STATE[fut_tok] = {"ltp": 25000, "oi": 10_000_000, "vol": 50_000}
    run_at("2026-09-23 11:00", lambda: flow.run(bot, True, False))       # first snapshot
    FUT_STATE[fut_tok] = {"ltp": 25200, "oi": 10_400_000, "vol": 350_000}  # +0.8% price, +4% OI, 2.4x volume
    n1 = len(SENT)
    run_at("2026-09-23 12:00", lambda: flow.run(bot, True, False))
    fl = [m for m in SENT[n1:] if "OI / VOLUME ALERT" in m]
    assert fl and "LONG BUILDUP" in fl[0] and "NIFTY" in fl[0], SENT[n1:]
    st_ = flow.status(st.s, fut_tok)
    print("OI status:", st_)
    assert st_["day"] and st_["hour"]

    print("\n=== 🚨 big-move early alert ===")
    FUT_STATE[fut_tok] = {"ltp": 25020, "oi": 10_600_000, "vol": 420_000}    # -0.7% in 15 min
    n2 = len(SENT)
    run_at("2026-09-23 12:15", lambda: flow.run(bot, True, False))
    bm = [m for m in SENT[n2:] if "BIG MOVE ALERT" in m]
    assert bm and "NIFTY" in bm[0] and "fell" in bm[0], SENT[n2:]
    FUT_STATE.clear()
    UND["NIFTY"][0] = 25000
    C.SELL_STYLE = "HEDGED"; st.s["positions"].clear()
    C.EVENT_DATES = {"2026-09-24": "RBI policy"}
    n2 = len(SENT)
    run_at("2026-09-24 11:20", bot.intraday_scan)
    assert len(SENT) == n2 and not st.s["positions"]
    C.EVENT_DATES = {}
    rsi_alert.STATE_FILE.unlink(missing_ok=True)
    print("\nALL SIMULATION CHECKS PASSED ✅")


if __name__ == "__main__":
    main()
