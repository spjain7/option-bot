"""Independent cross-check of STKFUT-CMP-001 ORB60 trades with vectorbt 0.28.1 Portfolio.from_signals (gross, no fees).
Entries are taken from our trade log (same entry candle and side); vectorbt decides the exit from sl_stop / tp_stop
(1:1, relative to the entry price) and an end-of-day exit at the close of the day's last candle."""
import sys
import numpy as np, pandas as pd, vectorbt as vbt
from vectorbt.portfolio.enums import StopEntryPrice, StopExitPrice
D = sys.argv[1]
res = []
for nm in ["RELIANCE", "SBIN", "TCS", "INFY", "TATASTEEL"]:
    b = pd.read_csv(f"{D}/{nm}_bars.csv", parse_dates=["time", "day"]).set_index("time")
    t = pd.read_csv(f"{D}/{nm}_trades.csv", parse_dates=["entry_time", "exit_time"])
    n = len(b); idx = b.index
    le, se, ex = np.zeros(n, bool), np.zeros(n, bool), np.zeros(n, bool)
    sl = np.full(n, np.nan)
    pos = {ts: k for k, ts in enumerate(idx)}
    last = (b["day"] != b["day"].shift(-1)).values
    for r in t.itertuples():
        k = pos[r.entry_time]
        (le if r.side > 0 else se)[k] = True
        sl[k] = r.R / r.entry
    ex[last] = True
    price = np.where(le | se, b["open"].values, b["close"].values)
    pf = vbt.Portfolio.from_signals(close=b["close"], open=b["open"], high=b["high"], low=b["low"], entries=le, exits=ex,
                                    short_entries=se, short_exits=ex, price=price, sl_stop=sl, tp_stop=sl,
                                    stop_entry_price=StopEntryPrice.Price, stop_exit_price=StopExitPrice.StopMarket,
                                    size=1.0, fees=0.0, slippage=0.0, accumulate=False, freq="1h")
    tr = pf.trades.records_readable
    tr["entry_time"] = pd.to_datetime(tr["Entry Timestamp"])
    m = t.merge(tr[["entry_time", "Avg Entry Price", "Avg Exit Price", "Exit Timestamp"]], on="entry_time", how="left")
    m["vbt_R"] = m["side"] * (m["Avg Exit Price"] - m["Avg Entry Price"]) / m["R"]
    m["diff"] = (m["vbt_R"] - m["gross_R"]).abs()
    res.append(m.assign(name=nm))
M = pd.concat(res)
print("trades", len(M), "matched by vectorbt", M["vbt_R"].notna().sum())
print("identical outcome (|ΔR| < 0.01):", (M["diff"] < 0.01).sum(), f"({(M['diff'] < 0.01).mean() * 100:.1f}%)")
print("mean gross R  ours %.4f  vectorbt %.4f" % (M["gross_R"].mean(), M["vbt_R"].mean()))
d = M[M["diff"] >= 0.01]
print("differences by our exit reason:", d["why"].value_counts().to_dict())
print(d[["name", "entry_time", "side", "entry", "stop", "target", "exit", "why", "gross_R", "Avg Exit Price", "vbt_R"]].head(8).to_string(index=False))
M["same_bar"] = M["exit_time"] == M["entry_time"]
print("\nour exit on the ENTRY candle:", M["same_bar"].sum())
print("differences that are same-candle exits:", (M["diff"] >= 0.01)[M["same_bar"]].sum(), "of", (M["diff"] >= 0.01).sum())
u = M[M["vbt_R"].isna()]
print("unmatched:", len(u), "of which previous trade of ours exited on the same candle this one entered:",
      sum(1 for r in u.itertuples() if ((M["name"] == r.name) & (M["exit_time"] == r.entry_time)).any()))
ok = M[~M["same_bar"] & M["vbt_R"].notna()]
print("excluding same-candle exits: identical", (ok["diff"] < 0.01).mean() * 100, "% of", len(ok), "; mean ours %.4f vbt %.4f" % (ok["gross_R"].mean(), ok["vbt_R"].mean()))
big = ok[ok["diff"] >= 0.01]; print(big[["name","entry_time","exit_time","why","gross_R","vbt_R","Exit Timestamp"]].to_string())
print(u[["name","entry_time","side","why","exit_time"]].head(6).to_string())
print(u["entry_time"].dt.strftime("%H:%M").value_counts().to_dict())
