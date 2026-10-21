"""Inspect what Angel One SmartAPI ACTUALLY returns for MCX Crude Oil futures (read-only market data).

  python -m crude.probe        -> prints a JSON report and writes state/crude/probe.json
Checks: candle intervals (15m / 30m / 1h / 1d), volume presence, historical OI (getOIData) and live quote fields
(incl. opnInterest) for the front and next contracts. No orders, no secrets printed.
"""
import json, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def contracts(master, name="CRUDEOIL"):
    from angel import now_ist
    m = master[(master["name"] == name) & (master["exch_seg"] == "MCX") & (master["instrumenttype"] == "FUTCOM")
               & (master["expiry_dt"] >= now_ist().normalize())].sort_values("expiry_dt")
    return m.head(2)


def main():
    from angel import Angel, load_master, now_ist
    api, master, now = Angel(), load_master(), now_ist()
    rep = dict(run_ist=str(now), contracts=[], candles={}, oi_history={}, quote={})
    cs = contracts(master)
    for _, c in cs.iterrows():
        rep["contracts"].append(dict(symbol=c["symbol"], token=str(c["token"]), expiry=str(c["expiry_dt"].date()),
                                     lotsize=float(c["lotsize"]), tick_size=c.get("tick_size")))
    for _, c in cs.iterrows():
        tok, sym = str(c["token"]), c["symbol"]
        for iv, days in (("FIFTEEN_MINUTE", 10), ("THIRTY_MINUTE", 10), ("ONE_HOUR", 30), ("ONE_DAY", 60)):
            try:
                d = api._candles("MCX", tok, iv, now - pd.Timedelta(days=days), now)
                rep["candles"][f"{sym}|{iv}"] = dict(
                    bars=0 if d is None else len(d), first=None if d is None or d.empty else str(d.time.min()),
                    last=None if d is None or d.empty else str(d.time.max()),
                    volume_nonzero_pct=None if d is None or d.empty else round(float((d.volume > 0).mean() * 100), 1),
                    minutes_seen=None if d is None or d.empty else sorted(set(d.time.dt.strftime("%H:%M")))[:6])
            except Exception as e:
                rep["candles"][f"{sym}|{iv}"] = dict(error=f"{type(e).__name__}: {str(e)[:160]}")
        for iv in ("ONE_HOUR", "ONE_DAY"):
            try:
                time.sleep(0.8)
                r = api.api.getOIData({"exchange": "MCX", "symboltoken": tok, "interval": iv,
                                       "fromdate": (now - pd.Timedelta(days=10)).strftime("%Y-%m-%d %H:%M"),
                                       "todate": now.strftime("%Y-%m-%d %H:%M")})
                data = (r or {}).get("data")
                rep["oi_history"][f"{sym}|{iv}"] = dict(status=(r or {}).get("status"), message=(r or {}).get("message"),
                                                        errorcode=(r or {}).get("errorcode"),
                                                        rows=len(data) if isinstance(data, list) else None,
                                                        sample=data[:2] if isinstance(data, list) else None)
            except Exception as e:
                rep["oi_history"][f"{sym}|{iv}"] = dict(error=f"{type(e).__name__}: {str(e)[:160]}")
    try:
        q = api.quotes({"MCX": [str(t) for t in cs["token"]]})
        for tok, v in q.items():
            rep["quote"][tok] = dict(fields=sorted(v.keys()), ltp=v.get("ltp"), opnInterest=v.get("opnInterest"),
                                     tradeVolume=v.get("tradeVolume"), exchFeedTime=v.get("exchFeedTime"),
                                     exchTradeTime=v.get("exchTradeTime"))
    except Exception as e:
        rep["quote"]["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    out = ROOT / "state" / "crude"; out.mkdir(parents=True, exist_ok=True)
    (out / "probe.json").write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
