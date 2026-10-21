"""Download test data (Yahoo Finance): python backtest/fetch_data.py   (needs: pip install yfinance)"""
from pathlib import Path
import yfinance as yf
D = Path(__file__).parent / "data"; D.mkdir(exist_ok=True)
T = {"GOLD": "GC=F", "SILVER": "SI=F", "CRUDEOIL": "CL=F", "NATURALGAS": "NG=F", "COPPER": "HG=F", "ALUMINIUM": "ALI=F"}
for n, t in T.items():
    for iv, kw, suf in (("1h", {"period": "730d"}, ""), ("1d", {"start": "2005-01-01"}, "_D")):
        if suf and n == "ALUMINIUM":
            continue
        d = yf.download(t, interval=iv, progress=False, auto_adjust=False, **kw)
        d.columns = [c[0].lower() for c in d.columns]
        if iv == "1h":
            d.index = d.index.tz_convert("Asia/Kolkata").tz_localize(None)
        d = d[["open", "high", "low", "close", "volume"]].dropna()
        d[d.close > 0].to_csv(D / f"{n}{suf}.csv")
        print(n, iv, len(d))
