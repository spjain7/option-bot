"""Download 1-hour history of NSE STOCK futures (lot size < 3000) for backtesting – research only, read-only API.
Nearest-expiry token per stock (Angel serves a stitched front-month history on it), paged back ~4 years.
  python -m research.adapters.angel_stocks   -> research/data/angel/NFO_STK/<NAME>_ONE_HOUR.csv + manifest_stocks.csv
"""
import sys, time
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "research" / "data" / "angel" / "NFO_STK"


def main():
    from angel import Angel, load_master, now_ist
    from alerts.stocks import universe
    api, master, now = Angel(), load_master(), now_ist()
    uni = universe(master, now)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, c in uni.items():
        parts, to = [], now
        for _ in range(4):
            d = api.candles("NFO", c["token"], "ONE_HOUR", to - pd.Timedelta(days=390), to)
            if d is None or d.empty:
                break
            parts.append(d)
            to = d["time"].min() - pd.Timedelta(minutes=1)
        if parts:
            df = pd.concat(parts).drop_duplicates("time").sort_values("time")
            df.to_csv(OUT / f"{name}_ONE_HOUR.csv", index=False)
            rows.append(dict(name=name, symbol=c["symbol"], lot=c["lot"], bars=len(df), first=df["time"].min(), last=df["time"].max()))
        print(name, sum(len(p) for p in parts), flush=True)
    pd.DataFrame(rows).to_csv(OUT / "manifest_stocks.csv", index=False)


if __name__ == "__main__":
    main()
