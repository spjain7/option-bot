"""NSE F&O end-of-day bhavcopy -> OPTION prices (REAL exchange data, contract level) for option-buy backtests (29-Oct-2026).

Same official archive as nse_bhavcopy.py, but keeps option rows: stock options (OPTSTK / STO) and NIFTY / BANKNIFTY index
options (OPTIDX / IDO), nearest 2 expiries per symbol, strikes within ±12 % of that day's near-month futures close,
plus the near-month futures close itself (reference). One CSV per trading day.

Usage:  python -m research.adapters.nse_options 2022-07-01 [end]
Output: research/data/nse_opt/days/YYYYMMDD.csv
  columns: date, symbol, kind (FUT/CE/PE), expiry, strike, open, high, low, close, settle, contracts, oi
"""
import io, sys, time, zipfile, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from research.adapters.nse_bhavcopy import url, UA  # noqa: E402

OUT = ROOT / "data" / "nse_opt"
DAYS = OUT / "days"
BAND = 0.12
INDEX = {"NIFTY", "BANKNIFTY"}
COLS = ["date", "symbol", "kind", "expiry", "strike", "open", "high", "low", "close", "settle", "contracts", "oi"]


def universe():
    from research.search import stock_search as SR
    return set(pd.read_csv(SR.DATA / "manifest_stocks.csv")["name"]) | INDEX


def parse(raw, d, names):
    z = zipfile.ZipFile(io.BytesIO(raw))
    df = pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    if "INSTRUMENT" in df.columns:
        ins = df["INSTRUMENT"].str.strip()
        x = pd.DataFrame({"ins": ins, "symbol": df["SYMBOL"].str.strip(),
                          "expiry": pd.to_datetime(df["EXPIRY_DT"], format="mixed", dayfirst=True),
                          "strike": pd.to_numeric(df["STRIKE_PR"], errors="coerce"), "otype": df["OPTION_TYP"].str.strip(),
                          "open": df["OPEN"], "high": df["HIGH"], "low": df["LOW"], "close": df["CLOSE"], "settle": df["SETTLE_PR"],
                          "contracts": df["CONTRACTS"], "oi": df["OPEN_INT"]})
        fut = x["ins"].isin(["FUTSTK", "FUTIDX"]); opt = x["ins"].isin(["OPTSTK", "OPTIDX"])
    else:
        t = df["FinInstrmTp"].str.strip()
        x = pd.DataFrame({"ins": t, "symbol": df["TckrSymb"].str.strip(), "expiry": pd.to_datetime(df["XpryDt"]),
                          "strike": pd.to_numeric(df["StrkPric"], errors="coerce"), "otype": df["OptnTp"].astype(str).str.strip(),
                          "open": df["OpnPric"], "high": df["HghPric"], "low": df["LwPric"], "close": df["ClsPric"],
                          "settle": df["SttlmPric"], "contracts": df["TtlTradgVol"], "oi": df["OpnIntrst"]})
        fut = x["ins"].isin(["STF", "IDF"]); opt = x["ins"].isin(["STO", "IDO"])
    x = x[x["symbol"].isin(names)]
    f = x[fut[x.index]].sort_values("expiry").groupby("symbol").head(1)
    ref = f.set_index("symbol")["close"]
    o = x[opt[x.index] & x["otype"].isin(["CE", "PE"])].copy()
    o["ref"] = o["symbol"].map(ref)
    o = o[(o["strike"] - o["ref"]).abs() <= BAND * o["ref"]]
    exps = o.groupby("symbol")["expiry"].apply(lambda s: set(sorted(s.unique())[:2]))
    o = o[[e in exps.get(s, set()) for s, e in zip(o["symbol"], o["expiry"])]]
    o["kind"] = o["otype"]
    f = f.assign(kind="FUT", strike=np.nan)
    out = pd.concat([f, o], ignore_index=True)
    out.insert(0, "date", pd.Timestamp(d))
    return out[COLS]


def fetch(args):
    d, names = args
    fp = DAYS / f"{d:%Y%m%d}.csv"
    if fp.exists():
        return d, "cached"
    for i in range(3):
        try:
            r = requests.get(url(d), headers=UA, timeout=90)
            if r.status_code == 404:
                return d, "missing"
            if r.status_code == 200 and r.content[:2] == b"PK":
                parse(r.content, d, names).to_csv(fp, index=False)
                return d, "ok"
            if r.status_code == 200:
                return d, "missing"
        except Exception:
            pass
        time.sleep(2 + 3 * i)
    return d, "error"


def main(start, end=None):
    DAYS.mkdir(parents=True, exist_ok=True)
    names = universe()
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end) if end else dt.date.today() - dt.timedelta(days=1)
    days = [s + dt.timedelta(n) for n in range((e - s).days + 1)]
    days = [(d, names) for d in days if d.weekday() < 5]
    res = {"ok": 0, "cached": 0, "missing": [], "error": []}
    with ThreadPoolExecutor(6) as ex:
        for k, (d, st) in enumerate(ex.map(fetch, days), 1):
            if st in ("missing", "error"):
                res[st].append(f"{d:%Y-%m-%d}")
            else:
                res[st] += 1
            if k % 100 == 0:
                print(f"{k}/{len(days)} ... {d}", flush=True)
    (OUT / "errors.txt").write_text("\n".join(res["error"]))
    print(f"done: ok {res['ok']} cached {res['cached']} holidays/missing {len(res['missing'])} errors {len(res['error'])}")


def load(symbols=None, kinds=("CE", "PE", "FUT")):
    fs = sorted(DAYS.glob("*.csv"))
    df = pd.concat((pd.read_csv(f, parse_dates=["date", "expiry"]) for f in fs), ignore_index=True)
    df = df[df["kind"].isin(kinds)]
    return df[df["symbol"].isin(symbols)] if symbols else df


if __name__ == "__main__":
    main(*sys.argv[1:])
