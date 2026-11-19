"""Extend research/data/nse_cm/_adjusted.pkl (to 5-Nov) with the NSE bhavcopies 6..17-Nov (raw), chained with PREVCLOSE so
splits / bonuses in between stay adjusted. Writes an extended pickle to the scratchpad (repo data untouched)."""
import pickle, glob, sys
import numpy as np, pandas as pd
SC = "/tmp/claude-0/-home-claude/9dfb3327-26db-5f33-89ad-b39b1ae569a9/scratchpad"
A = pickle.load(open("/home/claude/option-bot/research/data/nse_cm/_adjusted.pkl", "rb"))
new = pd.concat([pd.read_csv(f, parse_dates=["date"]) for f in sorted(glob.glob(f"{SC}/bhav/2026*.csv.gz"))], ignore_index=True)
new = new[new.series.isin(["EQ", "BE", "BZ", "SM", "ST"])].sort_values("date")
by_sym = {str(d["symbol"].iloc[-1]): k for k, d in A.items()}
last = max(d["time"].max() for d in A.values())
added = 0
for sym, g in new.groupby("symbol"):
    k = by_sym.get(sym)
    if k is None:
        continue
    d = A[k]
    if d["time"].max() < last - pd.Timedelta(days=10):          # stopped trading long ago
        continue
    adj_prev = float(d["close"].iloc[-1]); rows = []
    for _, r in g.iterrows():
        if r.date <= d["time"].max():
            continue
        ac = adj_prev * float(r.close) / float(r.prevclose) if r.prevclose > 0 else float(r.close)
        f = ac / float(r.close)
        rows.append(dict(time=r.date, open=r.open * f, high=r.high * f, low=r.low * f, close=ac, volume=r.volume, value=r.value,
                         symbol=sym, series=r.series, factor=1.0))
        adj_prev = ac
    if rows:
        A[k] = pd.concat([d, pd.DataFrame(rows)], ignore_index=True); added += len(rows)
pickle.dump(A, open(f"{SC}/scan/_adjusted_ext.pkl", "wb"))
print("rows added", added, "last day", max(d["time"].max() for d in A.values()))
