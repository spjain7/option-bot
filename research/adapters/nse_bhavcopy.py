"""NSE F&O end-of-day bhavcopy adapter (REAL exchange data, contract level).

Downloads the official daily F&O bhavcopy from NSE archives and keeps index-futures rows only
(OHLC, settle, volume in contracts, open interest - all per contract/expiry).
  * old format (<= 05-Jul-2024): content/historical/DERIVATIVES/YYYY/MON/foDDMONYYYYbhav.csv.zip
  * UDiFF format (>= 08-Jul-2024): content/fo/BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip
A missing file on a weekday is recorded as a non-trading day (holiday) - nothing is filled in.

Usage:  python -m research.adapters.nse_bhavcopy 2011-01-01 [end]
Output: research/data/nse_fut/days/YYYYMMDD.csv (one per trading day) and research/data/nse_fut/missing.txt
"""
import io, sys, time, zipfile, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
import requests

OUT = Path(__file__).resolve().parents[1] / "data" / "nse_fut"
DAYS = OUT / "days"
DAYS.mkdir(parents=True, exist_ok=True)
BASE = "https://nsearchives.nseindia.com/content"
UA = {"User-Agent": "Mozilla/5.0 (research backtest; end-of-day archive)"}
UDIFF_FROM = dt.date(2024, 7, 8)
COLS = ["date", "symbol", "expiry", "open", "high", "low", "close", "settle", "contracts", "oi", "chg_oi"]


def url(d):
    if d >= UDIFF_FROM:
        return f"{BASE}/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    mon = d.strftime("%b").upper()
    return f"{BASE}/historical/DERIVATIVES/{d:%Y}/{mon}/fo{d:%d}{mon}{d:%Y}bhav.csv.zip"


def parse(raw, d):
    z = zipfile.ZipFile(io.BytesIO(raw))
    df = pd.read_csv(z.open(z.namelist()[0]))
    df.columns = [c.strip() for c in df.columns]
    if "INSTRUMENT" in df.columns:                                   # old format
        df = df[df["INSTRUMENT"].str.strip() == "FUTIDX"]
        out = pd.DataFrame({"symbol": df["SYMBOL"].str.strip(), "expiry": pd.to_datetime(df["EXPIRY_DT"], format="mixed", dayfirst=True),
                            "open": df["OPEN"], "high": df["HIGH"], "low": df["LOW"], "close": df["CLOSE"],
                            "settle": df["SETTLE_PR"], "contracts": df["CONTRACTS"], "oi": df["OPEN_INT"],
                            "chg_oi": df["CHG_IN_OI"]})
    else:                                                            # UDiFF
        df = df[df["FinInstrmTp"].str.strip() == "IDF"]
        out = pd.DataFrame({"symbol": df["TckrSymb"].str.strip(), "expiry": pd.to_datetime(df["XpryDt"]),
                            "open": df["OpnPric"], "high": df["HghPric"], "low": df["LwPric"], "close": df["ClsPric"],
                            "settle": df["SttlmPric"], "contracts": df["TtlTradgVol"], "oi": df["OpnIntrst"],
                            "chg_oi": df["ChngInOpnIntrst"]})
    out.insert(0, "date", pd.Timestamp(d))
    return out[COLS]


def fetch(d, tries=3):
    f = DAYS / f"{d:%Y%m%d}.csv"
    if f.exists():
        return d, "cached"
    for i in range(tries):
        try:
            r = requests.get(url(d), headers=UA, timeout=60)
            if r.status_code == 404:
                return d, "missing"
            if r.status_code == 200 and r.content[:2] == b"PK":
                parse(r.content, d).to_csv(f, index=False)
                return d, "ok"
            if r.status_code == 200:                                 # HTML page instead of a zip = no file that day
                return d, "missing"
        except Exception as e:
            err = str(e)[:80]
        time.sleep(2 + 3 * i)
    return d, "error"


def main(start, end=None):
    DAYS.mkdir(parents=True, exist_ok=True)
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end) if end else dt.date.today() - dt.timedelta(days=1)
    days = [s + dt.timedelta(n) for n in range((e - s).days + 1)]
    days = [d for d in days if d.weekday() < 5]
    res = {"ok": 0, "cached": 0, "missing": [], "error": []}
    with ThreadPoolExecutor(6) as ex:
        for k, (d, st) in enumerate(ex.map(fetch, days), 1):
            if st in ("missing", "error"):
                res[st].append(f"{d:%Y-%m-%d}")
            else:
                res[st] += 1
            if k % 250 == 0:
                print(f"{k}/{len(days)} ... last {d}", flush=True)
    (OUT / "missing.txt").write_text("\n".join(res["missing"]))
    (OUT / "errors.txt").write_text("\n".join(res["error"]))
    print(f"done: ok {res['ok']} cached {res['cached']} weekday-holidays/missing {len(res['missing'])} errors {len(res['error'])}")


def load(symbols=None):
    """All downloaded days -> one DataFrame of index-futures contract rows."""
    fs = sorted(DAYS.glob("*.csv"))
    df = pd.concat((pd.read_csv(f, parse_dates=["date", "expiry"]) for f in fs), ignore_index=True)
    return df[df["symbol"].isin(symbols)] if symbols else df


if __name__ == "__main__":
    main(*sys.argv[1:])
