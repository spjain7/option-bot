"""NSE STOCK BREAKOUT / BREAKDOWN on 4-HOUR candles (owner 18-Nov-2026). Angel 5-minute NSE cash candles
(research/data/angel/NSE_EQ, liquid stocks of today -> SURVIVORSHIP bias, 2024-10 .. 2026-11 only). Two candles a day:
09:15-13:15 and 13:15-15:30. Same setups / filters / exits / costs as nse_bo_tf.py; MKT = equal-weight index of these
stocks above its 200-candle (~100-day) average. Halves: H1 to 2025-10, H2 from 2025-11 (shown as DEV / VALID columns;
OOS = both together).
python -m research.cashq.nse_bo_4h -> results/nse_bo_4h.csv"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D  # noqa: E402
from research.cashq import nse_bo_tf as T  # noqa: E402


def bars4(d):
    t = d["time"]; day = t.dt.normalize(); k = ((t.dt.hour * 60 + t.dt.minute) >= 795).astype(int)   # 13:15
    g = d.groupby([day, k])
    o = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
              volume=("volume", "sum")).reset_index(drop=True)
    o["time"] = o["time"].dt.normalize() + np.where(o["time"].dt.hour * 60 + o["time"].dt.minute >= 795, pd.Timedelta(hours=13, minutes=15),
                                                     pd.Timedelta(hours=9, minutes=15))
    return o


def main():
    P = {}
    for s in D.intraday_symbols():
        try:
            d = D.intraday(s)
        except Exception:
            continue
        if len(d) < 5000:
            continue
        P[s] = bars4(d).set_index("time")
    idx = pd.DatetimeIndex(sorted({t for x in P.values() for t in x.index}))
    W = {f: pd.DataFrame({s: x[f] for s, x in P.items()}).reindex(idx) for f in ("open", "high", "low", "close", "volume")}
    W["value"] = W["close"] * W["volume"]; W["elig"] = W["close"].notna() & (W["close"] >= 50)
    ew = (W["close"] / W["close"].bfill().iloc[0]).mean(axis=1); mkt = ew > ew.rolling(200).mean()
    T.MAXH["4h"] = 60; T.HI52["4h"] = 500
    T.per = lambda t: np.where(t < pd.Timestamp("2025-11-01"), "DEV", "VALID")
    rows = T.run_tf(W, "4h", mkt)
    L = pd.DataFrame(rows)
    L.to_csv(T.OUT / "nse_bo_4h.csv", index=False)
    ok = L[(L.DEV_R > L.DEV_rand) & (L.VALID_R > L.VALID_rand) & (L.DEV_R > 0) & (L.VALID_R > 0)]
    pd.set_option("display.width", 260)
    print("4h: positive and better than random in both halves:", len(ok), "of", len(L))
    ok = ok.assign(score=np.minimum(ok.DEV_R - ok.DEV_rand, ok.VALID_R - ok.VALID_rand))
    print(ok.sort_values("score", ascending=False).groupby("side").head(6)[["side", "setup", "filt", "sl_atr", "exit", "trades", "win", "R", "avg_pct",
                                                                             "DEV_n", "DEV_R", "DEV_rand", "VALID_n", "VALID_R", "VALID_rand"]].to_string(index=False))


if __name__ == "__main__":
    main()
