"""MCXE-003: POINT-IN-TIME NSE stock + index futures, contract level, from the official F&O bhavcopy archive.

Why: research/data/nse_opt/days keeps only today's F&O list (183 names; stocks that left F&O, e.g. DELTACORP, INDIACEM,
ZEEL, are absent) -> survivorship bias. This adapter keeps EVERY FUTSTK / FUTIDX row (all symbols, all expiries) of every
day, so the universe on any date is exactly what traded that day.

Usage:  python -m research.adapters.nse_stkfut_pit 2018-01-01 [end]      (resumable: existing days are skipped)
Output: research/data/nse_fut_pit/days/YYYYMMDD.csv.gz
  columns: date, symbol, kind (STK/IDX), expiry, open, high, low, close, settle, contracts, oi, chg_oi
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from research.adapters.nse_bhavcopy import url, UA  # noqa: E402

OUT = ROOT / "data" / "nse_fut_pit"
DAYS = OUT / "days"
COLS = ["date", "symbol", "kind", "expiry", "open", "high", "low", "close", "settle", "contracts", "oi", "chg_oi"]


def parse(raw, d):
    z = zipfile.ZipFile(io.BytesIO(raw))
    df = pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    if "INSTRUMENT" in df.columns:
        ins = df["INSTRUMENT"].str.strip()
        df = df[ins.isin(["FUTSTK", "FUTIDX"])]
        x = pd.DataFrame({"symbol": df["SYMBOL"].str.strip(), "kind": df["INSTRUMENT"].str.strip().map({"FUTSTK": "STK", "FUTIDX": "IDX"}),
                          "expiry": pd.to_datetime(df["EXPIRY_DT"], format="mixed", dayfirst=True),
                          "open": df["OPEN"], "high": df["HIGH"], "low": df["LOW"], "close": df["CLOSE"], "settle": df["SETTLE_PR"],
                          "contracts": df["CONTRACTS"], "oi": df["OPEN_INT"], "chg_oi": df["CHG_IN_OI"]})
    else:
        t = df["FinInstrmTp"].str.strip()
        df = df[t.isin(["STF", "IDF"])]
        x = pd.DataFrame({"symbol": df["TckrSymb"].str.strip(), "kind": df["FinInstrmTp"].str.strip().map({"STF": "STK", "IDF": "IDX"}),
                          "expiry": pd.to_datetime(df["XpryDt"]), "open": df["OpnPric"], "high": df["HghPric"], "low": df["LwPric"],
                          "close": df["ClsPric"], "settle": df["SttlmPric"], "contracts": df["TtlTradgVol"], "oi": df["OpnIntrst"],
                          "chg_oi": df["ChngInOpnIntrst"]})
    x.insert(0, "date", pd.Timestamp(d))
    return x[COLS]


def fetch(d):
    fp = DAYS / f"{d:%Y%m%d}.csv.gz"
    if fp.exists():
        return d, "cached"
    for i in range(3):
        try:
            r = requests.get(url(d), headers=UA, timeout=90)
            if r.status_code == 404:
                return d, "missing"
            if r.status_code == 200 and r.content[:2] == b"PK":
                parse(r.content, d).to_csv(fp, index=False)
                return d, "ok"
            if r.status_code == 200:
                return d, "missing"
        except Exception:                                         # noqa: BLE001
            pass
        time.sleep(2 + 3 * i)
    return d, "error"


def main(start, end=None):
    DAYS.mkdir(parents=True, exist_ok=True)
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end) if end else dt.date.today() - dt.timedelta(days=1)
    days = [s + dt.timedelta(n) for n in range((e - s).days + 1)]
    days = [d for d in days if d.weekday() < 5]
    res = {"ok": 0, "cached": 0, "missing": [], "error": []}
    with ThreadPoolExecutor(4) as ex:
        for k, (d, st) in enumerate(ex.map(fetch, days), 1):
            if st in ("missing", "error"):
                res[st].append(f"{d:%Y-%m-%d}")
            else:
                res[st] += 1
            if k % 100 == 0:
                print(f"{k}/{len(days)} ... {d}", flush=True)
    (OUT / "errors.txt").write_text("\n".join(res["error"]))
    (OUT / "missing.txt").write_text("\n".join(res["missing"]))
    print(f"done: ok {res['ok']} cached {res['cached']} holidays/missing {len(res['missing'])} errors {len(res['error'])}")


def load(start=None, kinds=("STK",)):
    fs = sorted(DAYS.glob("*.csv.gz"))
    if start:
        fs = [f for f in fs if f.name[:8] >= start.replace("-", "")]
    df = pd.concat((pd.read_csv(f, parse_dates=["date", "expiry"]) for f in fs), ignore_index=True)
    return df[df["kind"].isin(kinds)]


if __name__ == "__main__":
    main(*sys.argv[1:])
