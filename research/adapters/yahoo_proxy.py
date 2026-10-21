"""Yahoo Finance PROXY data (not MCX / not futures prices).

- Commodities: international front-month continuous futures (COMEX/NYMEX). MCX prices follow them x USD/INR,
  but this series is NOT back-adjusted and roll dates are not published, so roll jumps can create false signals.
- Index hourly: the CASH index (^NSEI, ^NSEBANK), not the futures contract.
Usage: python -m research.adapters.yahoo_proxy
Output: research/data/proxy/<NAME>_1d.csv and <NAME>_1h.csv (hourly timestamps converted to IST)
"""
from pathlib import Path
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "proxy"


def _get(ticker, **kw):
    import yfinance as yf
    d = yf.download(ticker, progress=False, auto_adjust=False, **kw)
    if d.empty:
        return d
    d.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in d.columns]
    d = d[["open", "high", "low", "close", "volume"]].dropna()
    return d[d["close"] > 0]


def main():
    from research.instruments import REGISTRY
    OUT.mkdir(parents=True, exist_ok=True)
    fx = _get("INR=X", start="2005-01-01", interval="1d"); fx.index.name = "time"
    fx.to_csv(OUT / "USDINR_1d.csv"); print("USDINR", len(fx))
    for name, r in REGISTRY.items():
        jobs = []
        if r.get("proxy"):
            jobs += [(r["proxy"], "1d", dict(start="2005-01-01", interval="1d")),
                     (r["proxy"], "1h", dict(period="730d", interval="1h"))]
        if r.get("hourly_proxy"):
            jobs += [(r["hourly_proxy"], "1h", dict(period="730d", interval="1h"))]
        for t, tag, kw in jobs:
            d = _get(t, **kw)
            if d.empty:
                print(name, t, tag, "NO DATA"); continue
            if tag == "1h":
                d.index = d.index.tz_convert("Asia/Kolkata").tz_localize(None)
            d.index.name = "time"
            d.to_csv(OUT / f"{name}_{tag}.csv")
            print(name, t, tag, len(d), d.index[0], d.index[-1], flush=True)


if __name__ == "__main__":
    main()
