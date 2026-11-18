"""18-Nov-2026 cash setups (owner chose A + C): 52-week high on volume (HI52VOL) and momentum burst in strong stocks
(MOMBURST) – signals, one call per stock, priority BO50 > HI52VOL > MOMBURST, messages labelled EXPERIMENTAL with the
backtest record, same entry / stop / exit as the 50-day breakout, CASHSTOCK_SETUPS switch. python tests/test_cash_setups.py"""
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cashstock import breakout as B  # noqa: E402

ok = 0


def check(c, n):
    global ok
    assert c, n
    ok += 1; print("✅", n)


days = pd.bdate_range("2025-01-01", periods=340)
r = np.random.default_rng(7)


def stock(sym, c, vol):
    return pd.DataFrame(dict(time=days[:len(c)], open=c * 0.999, high=c * 1.003, low=c * 0.99, close=c, volume=vol, symbol=sym))


def panel(n):
    A = {}
    # HHH: flat ~100 for 320 sessions, then a new 52-week closing high on 2.5x volume on session 320
    c = np.r_[100 + r.normal(0, 0.3, 320), [103.0], np.full(19, 103.2)][:n]
    v = np.r_[np.full(320, 3e6), [7.5e6], np.full(19, 3e6)][:n]
    A["HHH"] = stock("HHH", c, v)
    # MMM: old peak 150, fell to 90, steady rise to ~121 (strong 6-month return, below the 52-week high), then +5 % on volume
    base = np.r_[np.linspace(140, 150, 60), np.linspace(150, 90, 130), np.linspace(90, 121, 130)]
    c2 = np.r_[base + r.normal(0, 0.15, 320), [127.5], np.full(19, 127.0)][:n]
    v2 = np.r_[np.full(319, 3e6), [3.3e6, 7.2e6], np.full(19, 3e6)][:n]
    d2 = stock("MMM", c2, v2); d2.loc[320, ["open", "low", "high"]] = [121.5, 121.3, 127.9]
    A["MMM"] = d2
    for i in range(10):                                         # flat / slightly falling liquid stocks for the RS ranking
        cc = 60 + i - 0.01 * np.arange(n) + r.normal(0, 0.1, n)
        A[f"K{i}"] = stock(f"S{i}", cc, np.full(n, 2e7))
    return B.features(B.wide(A))


F = panel(321)
h = B.candidates(F, setup="HI52VOL"); mb = B.candidates(F, setup="MOMBURST")
check([c["symbol"] for c in h] == ["HHH"] and h[0]["volx"] >= 1.5, "HI52VOL: new 52-week closing high on 1.5x+ volume")
check([c["symbol"] for c in mb] == ["MMM"] and mb[0]["day_ret"] >= 0.04 and mb[0]["rs126"] >= 0.85, "MOMBURST: +4 % on volume, top-15 % RS, below the 52-week high")
check("MMM" not in [c["symbol"] for c in h], "MMM is not a 52-week high (old peak 150)")

st, m = {}, []
B.step(st, F, m)
syms = sorted(p["symbol"] for p in st["pending"])
check(syms == ["HHH", "MMM"] and len(m) == 4, "two calls (card + WHY each)")
txt = "\n".join(m)
check("52-week high on volume" in txt and "momentum burst" in txt and txt.count("EXPERIMENTAL") >= 2 and "4,051 trades" in txt and "2,054 trades" in txt,
      "labelled by setup, EXPERIMENTAL, with the backtest record")
check(all("3 ATR" in x for x in m[0::2]) and "close below the 50-day EMA" in txt, "same stop (3 ATR) and exit (close below EMA50) as the breakout")
m2 = []; B.step(st, F, m2)
check(not m2, "run again the same evening -> nothing new")

# entry next session at the open, as the breakout
F2 = panel(322); m3 = []; B.step(st, F2, m3)
check(len(st["open"]) == 2 and all("ENTRY" in x for x in m3[:2]), "entries at the next open")

# one call per stock: a stock firing two setups the same day gets the higher-priority call only
st2 = {}; m4 = []
B.MIN_SCORE, keep = 0, B.MIN_SCORE
B.step(st2, F, m4)
B.MIN_SCORE = keep
per = {}
for p in st2["pending"]:
    per.setdefault(p["symbol"], []).append(p["setup"])
check(all(len(v) == 1 for v in per.values()), f"one call per stock per day ({per})")

# switch: only the 50-day breakout
os.environ["CASHSTOCK_SETUPS"] = "BO50"
st3, m5 = {}, []; B.step(st3, F, m5)
check(not [p for p in st3["pending"] if p["setup"] != "BO50"], "CASHSTOCK_SETUPS=BO50 turns the two new setups off")
del os.environ["CASHSTOCK_SETUPS"]

# research parity: a second HI52VOL signal while the first trade would still run is busy
check(bool(B.busy_mask(F2, "sig_HI52VOL")["HHH"].iloc[321]) and not bool(B.busy_mask(F2, "sig_HI52VOL")["HHH"].iloc[320]),
      "one position per stock per setup (busy mask) as in the research")
print(f"{ok} cash-setup checks passed")
