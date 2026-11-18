import sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/option-bot")
from research.cashq import data as D, ind as I
SC = "/tmp/claude-0/-home-claude/9dfb3327-26db-5f33-89ad-b39b1ae569a9/scratchpad"
D.CM_PKL = Path(f"{SC}/scan/_adjusted_ext.pkl")
from research.cashq import nse_bo_trades as NT, nse_bo_tf as T
W = D.daily_panel(); mk = W["market"]["close"]; mkt = mk > mk.rolling(200).mean(); sym = W["symbol"]
c, h, l, v = (W[x].astype("float64") for x in ("close", "high", "low", "volume")); e = W["elig"].fillna(False)
ema200 = c.ewm(span=200, adjust=False, min_periods=200).mean()
FD = {"ext200": c / ema200 - 1, "ret20": c / c.shift(20) - 1, "adx": I.adx(h, l, c, 14), "atr_pct": I.atr(h, l, c, 14) / c,
      "rs126": (c / c.shift(126) - 1).where(e).rank(axis=1, pct=True)}
g = c.index.to_period("W-FRI"); wk_ath = (c >= c.cummax()) & (c == c.groupby(g).transform("max"))
print("data to", c.index[-1].date(), "market above 200-day avg:", bool(mkt.iloc[-1]))
panels = {"1d": W, "1w": D.weekly(W), "1M": T.monthly(W)}
out = []
for sid in ("M_ATH", "M_MY60", "W_ATH", "W_MY260", "W_MARU"):
    tf, label, k = NT.SETUPS[sid]
    P = panels[tf]
    s, o, hh, ll, cc, atr = NT.signals(P, tf, sid, mkt)
    for back, status in ((1, "CONFIRMED (candle closed)"), (0, "PROVISIONAL (candle still open)")):
        i = len(s.index) - 1 - back
        if i < 0: continue
        row = s.iloc[i]; d = s.index[i]
        if tf == "1M" and back == 1:   # last complete month = October: entry was 2-Nov open, show for reference
            status = "CONFIRMED at Oct month-end (entry was the 2-Nov open)"
        if tf == "1w" and back == 1:
            status = f"CONFIRMED week to {d.date()} (entry {('Mon 16-Nov open')})"
        for kk in row.index[row.values]:
            di = c.index.get_loc(d) if d in c.index else None
            f = {n: float(FD[n][kk].iloc[di]) for n in FD} if di is not None else {}
            px = float(cc[kk].iloc[i]); a = float(atr[kk].iloc[i])
            conf = []
            if sid == "M_ATH":
                if f["ext200"] <= .30 and f["ret20"] <= .05: conf.append("✅ not extended + no run-up (59 % win setup)")
                if f["adx"] >= 30 and f["ext200"] <= .20: conf.append("✅ ADX>=30 + not extended (62 % win setup)")
            if sid == "W_MARU" and f["atr_pct"] <= .025 and bool(wk_ath[kk].iloc[di]): conf.append("✅ calm + weekly ATH (62 % win setup)")
            out.append(dict(setup=label, status=status, symbol=str(sym[kk]), candle=str(d.date()), close=round(px, 2),
                            sl=round(px - k * a, 2), target=round(px + 3 * k * a, 2), risk_pct=round(100 * k * a / px, 1),
                            ext200_pct=round(100 * f.get("ext200", np.nan), 1), ret20_pct=round(100 * f.get("ret20", np.nan), 1),
                            adx=round(f.get("adx", np.nan), 0), atr_pct=round(100 * f.get("atr_pct", np.nan), 2), rs=round(f.get("rs126", np.nan), 2),
                            confirmations="; ".join(conf)))
O = pd.DataFrame(out); O.to_csv(f"{SC}/scan/today_scan.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300); pd.set_option("display.max_colwidth", 50)
for (st, stt), G in O.groupby(["setup", "status"]):
    print(f"\n== {st} · {stt}: {len(G)}")
    print(G[["symbol", "close", "sl", "target", "risk_pct", "ext200_pct", "ret20_pct", "adx", "atr_pct", "rs", "confirmations"]].to_string(index=False))
