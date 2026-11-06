"""NSE CASH-MARKET end-of-day bhavcopy (official, every traded security, POINT-IN-TIME incl. later-delisted stocks).

  * old format (<= 05-Jul-2024): content/historical/EQUITIES/YYYY/MON/cmDDMONYYYYbhav.csv.zip
  * UDiFF     (>= 08-Jul-2024): content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
Keeps series EQ / BE / BZ / SM excluded -> EQ and BE only (BE = trade-for-trade, flagged). PREVCLOSE in the file is NSE's
corporate-action-adjusted previous close, so adj factor = PREVCLOSE_t / CLOSE_(t-1) gives exact split / bonus / rights /
dividend adjustment (research/program/eq_bhav.py). No Angel calls – safe to run while the live bot runs.
Usage: python -m research.adapters.nse_cm 2005-01-01 [end]
Output: research/data/nse_cm/YYYY.csv.gz (date, symbol, series, isin, open, high, low, close, prevclose, volume, value, trades)
"""
import io
import sys
import time
import zipfile
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
import requests

OUT = Path(__file__).resolve().parents[1] / "data" / "nse_cm"
TMP = OUT / "days"
BASE = "https://nsearchives.nseindia.com/content"
UA = {"User-Agent": "Mozilla/5.0 (research backtest; end-of-day archive)"}
UDIFF_FROM = dt.date(2024, 7, 8)
COLS = ["date", "symbol", "series", "isin", "open", "high", "low", "close", "prevclose", "volume", "value", "trades"]


def url(d):
    if d >= UDIFF_FROM:
        return f"{BASE}/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    mon = d.strftime("%b").upper()
    return f"{BASE}/historical/EQUITIES/{d:%Y}/{mon}/cm{d:%d}{mon}{d:%Y}bhav.csv.zip"


def parse(raw, d):
    z = zipfile.ZipFile(io.BytesIO(raw))
    df = pd.read_csv(z.open(z.namelist()[0]))
    df.columns = [c.strip() for c in df.columns]
    if "SYMBOL" in df.columns:
        o = pd.DataFrame({"symbol": df.SYMBOL.str.strip(), "series": df.SERIES.str.strip(), "isin": df.get("ISIN", ""),
                          "open": df.OPEN, "high": df.HIGH, "low": df.LOW, "close": df.CLOSE, "prevclose": df.PREVCLOSE,
                          "volume": df.TOTTRDQTY, "value": df.TOTTRDVAL, "trades": df.get("TOTALTRADES", pd.NA)})
    else:
        o = pd.DataFrame({"symbol": df.TckrSymb.str.strip(), "series": df.SctySrs.str.strip(), "isin": df.ISIN,
                          "open": df.OpnPric, "high": df.HghPric, "low": df.LwPric, "close": df.ClsPric, "prevclose": df.PrvsClsgPric,
                          "volume": df.TtlTradgVol, "value": df.TtlTrfVal, "trades": df.get("TtlNbOfTxsExctd", pd.NA)})
    o = o[o.series.isin(["EQ", "BE"])]
    o.insert(0, "date", pd.Timestamp(d))
    return o[COLS]


def fetch(d, tries=4):
    f = TMP / f"{d:%Y%m%d}.csv.gz"
    if f.exists():
        return d, "cached"
    err = ""
    for i in range(tries):
        try:
            r = requests.get(url(d), headers=UA, timeout=60)
            if r.status_code == 404:
                return d, "missing"
            if r.status_code == 200 and r.content[:2] == b"PK":
                parse(r.content, d).to_csv(f, index=False, compression="gzip")
                return d, "ok"
            if r.status_code == 200:
                return d, "missing"
            err = f"http {r.status_code}"
        except Exception as e:
            err = str(e)[:80]
        time.sleep(2 + 3 * i)
    return d, f"error {err}"


def main(start, end=None):
    TMP.mkdir(parents=True, exist_ok=True)
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end) if end else dt.date.today() - dt.timedelta(days=1)
    days = [s + dt.timedelta(n) for n in range((e - s).days + 1) if (s + dt.timedelta(n)).weekday() < 5]
    res = {}
    with ThreadPoolExecutor(6) as ex:
        for d, st in ex.map(fetch, days):
            res.setdefault(st.split()[0], []).append(str(d))
            if st.startswith("error"):
                print(d, st, flush=True)
    print({k: len(v) for k, v in res.items()}, flush=True)
    (OUT / "missing_days.txt").write_text("\n".join(res.get("missing", [])))
    (OUT / "error_days.txt").write_text("\n".join(res.get("error", [])))
    for y in sorted({p.name[:4] for p in TMP.glob("*.csv.gz")}):
        parts = [pd.read_csv(p) for p in sorted(TMP.glob(f"{y}*.csv.gz"))]
        pd.concat(parts).to_csv(OUT / f"{y}.csv.gz", index=False, compression="gzip")
        print("year", y, sum(len(x) for x in parts), "rows", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
