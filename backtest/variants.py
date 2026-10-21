import bt, pandas as pd, numpy as np
SPLIT = pd.Timestamp("2025-10-01")
def evalp(p, names=bt.NAMES):
    t = pd.concat([bt.run(n, p) for n in names])
    return bt.stats(t[t.time < SPLIT]), bt.stats(t[t.time >= SPLIT]), t
V = {
 "baseline (intraday)": {},
 "carry overnight": {"carry": True},
 "carry + T2=3R": {"carry": True, "t2_r": 3.0},
 "carry + trail 2ATR after T1": {"carry": True, "t2_r": 6.0, "trail_atr": 2.0},
 "carry + trail 3ATR, no half-book": {"carry": True, "t2_r": 8.0, "trail_atr": 3.0, "book_half": False},
 "carry + SL 1.5-3 ATR, T2=3R": {"carry": True, "sl_atr": (1.5, 3.0), "t2_r": 3.0},
 "carry + ADX>=25": {"carry": True, "min_adx": 25},
 "carry + no RSI cap": {"carry": True, "rsi_buy": (55, 100), "rsi_sell": (0, 45)},
 "carry + 10-bar breakout": {"carry": True, "brk": 10},
 "intraday, T1/T2 = 0.7/1.5R": {"t1_r": 0.7, "t2_r": 1.5},
}
rows = {}
for k, p in V.items():
    a, b, _ = evalp(p)
    rows[k] = {"IS trades": a["trades"], "IS avgR": a["avg_r"], "IS PF": a["pf"],
               "OOS trades": b["trades"], "OOS avgR": b["avg_r"], "OOS PF": b["pf"], "OOS totR": b["total_r"], "OOS DD": b["max_dd_r"]}
    print(k, rows[k], flush=True)
pd.DataFrame(rows).T.to_csv("variants.csv")
