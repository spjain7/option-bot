"""NSE-FUT-001 (26-Nov-2026, owner: "permanent solution ... we have to do many more research on market setup").
Years of official NSE futures end-of-day data (every stock + index future: OHLC, settle, contracts, turnover, OPEN INTEREST)
from NSE's public archive – no Angel calls, so it never competes with the live bot and is not limited to live contracts.
Saved compact (futures rows only) as research/data/nse_fut/YYYY.parquet; days NSE has no file for (holidays) are listed
in _nofile.txt so they are not asked again. Resumable.
  python -m research.adapters.nse_fut_hist backfill 2015-01-01 [2026-11-26]
  python -m research.adapters.nse_fut_hist today            (last 10 calendar days)
Columns: date, kind (STK / IDX), symbol, expiry, open, high, low, close, settle, contracts, turnover (Rs), oi, chg_oi
(oi / chg_oi in shares / units, as NSE publishes them; turnover in rupees)."""
import datetime as dt
import io
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.adapters.nse_bhavcopy import url, UA  # noqa: E402

OUT = ROOT / "research" / "data" / "nse_fut"
NOFILE = OUT / "_nofile.txt"
COLS = ["date", "kind", "symbol", "expiry", "open", "high", "low", "close", "settle", "contracts", "turnover", "oi", "chg_oi"]


def parse(raw, d):
    z = zipfile.ZipFile(io.BytesIO(raw))
    df = pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
    df.columns = [str(c).strip() for c in df.columns]
    if "INSTRUMENT" in df.columns:                                    # old format (before 8-Jul-2024)
        ins = df["INSTRUMENT"].astype(str).str.strip()
        df = df[ins.isin(["FUTSTK", "FUTIDX"])]
        out = pd.DataFrame({"kind": df["INSTRUMENT"].str.strip().map({"FUTSTK": "STK", "FUTIDX": "IDX"}),
                            "symbol": df["SYMBOL"].astype(str).str.strip(),
                            "expiry": pd.to_datetime(df["EXPIRY_DT"].astype(str).str.strip(), format="mixed", dayfirst=True),
                            "open": df["OPEN"], "high": df["HIGH"], "low": df["LOW"], "close": df["CLOSE"], "settle": df["SETTLE_PR"],
                            "contracts": df["CONTRACTS"], "turnover": pd.to_numeric(df["VAL_INLAKH"], errors="coerce") * 1e5,
                            "oi": df["OPEN_INT"], "chg_oi": df["CHG_IN_OI"]})
    else:                                                             # UDiFF
        tp = df["FinInstrmTp"].astype(str).str.strip()
        df = df[tp.isin(["STF", "IDF"])]
        out = pd.DataFrame({"kind": df["FinInstrmTp"].str.strip().map({"STF": "STK", "IDF": "IDX"}),
                            "symbol": df["TckrSymb"].astype(str).str.strip(), "expiry": pd.to_datetime(df["XpryDt"]),
                            "open": df["OpnPric"], "high": df["HghPric"], "low": df["LwPric"], "close": df["ClsPric"],
                            "settle": df["SttlmPric"], "contracts": df["TtlTradgVol"], "turnover": df["TtlTrfVal"],
                            "oi": df["OpnIntrst"], "chg_oi": df["ChngInOpnIntrst"]})
    out.insert(0, "date", pd.Timestamp(d))
    return out[COLS].reset_index(drop=True)


def _load_year(y):
    f = OUT / f"{y}.parquet"
    return pd.read_parquet(f) if f.exists() else pd.DataFrame(columns=COLS)


def _save_year(y, df):
    OUT.mkdir(parents=True, exist_ok=True)
    df = df.drop_duplicates(["date", "symbol", "expiry"], keep="last").sort_values(["date", "kind", "symbol", "expiry"])
    df.reset_index(drop=True).to_parquet(OUT / f"{y}.parquet", index=False)


def run(d0, d1, budget_s=None, pause=0.6):
    OUT.mkdir(parents=True, exist_ok=True)
    nof = set(NOFILE.read_text().split()) if NOFILE.exists() else set()
    t0, got, miss = time.monotonic(), 0, 0
    y, cur, have, dirty = None, None, set(), False
    d = d0
    while d <= d1:
        if budget_s and time.monotonic() - t0 > budget_s:
            print("time budget used – stopping (resumable)"); break
        if d.year != y:
            if dirty:
                _save_year(y, cur)
            y, dirty = d.year, False
            cur = _load_year(y)
            have = set(pd.to_datetime(cur["date"]).dt.date) if len(cur) else set()
        if d.weekday() < 5 and d not in have and f"{d:%Y%m%d}" not in nof and d < dt.date.today() + dt.timedelta(days=1):
            try:
                r = requests.get(url(d), headers=UA, timeout=60)
            except Exception as e:
                print(d, "error", type(e).__name__); r = None
            if r is not None and r.status_code == 200 and r.content[:2] == b"PK":
                try:
                    p = parse(r.content, d)
                    cur = pd.concat([cur, p], ignore_index=True) if len(cur) else p
                    got += 1; dirty = True
                    if got % 50 == 0:
                        _save_year(y, cur); dirty = False; print(d, "saved", got, "days so far")
                except Exception as e:
                    print(d, "parse error", type(e).__name__, e)
            elif r is not None and r.status_code == 404 and d < dt.date.today() - dt.timedelta(days=3):
                nof.add(f"{d:%Y%m%d}"); miss += 1                  # holiday / no file (recent days are retried)
            time.sleep(pause)
        d += dt.timedelta(days=1)
    if dirty:
        _save_year(y, cur)
    NOFILE.write_text("\n".join(sorted(nof)))
    print(f"done: {got} new days, {miss} days without a file")
    return got


def main(argv):
    if argv[:1] == ["backfill"]:
        d0 = dt.date.fromisoformat(argv[1]); d1 = dt.date.fromisoformat(argv[2]) if len(argv) > 2 else dt.date.today()
        run(d0, d1, budget_s=float(argv[3]) if len(argv) > 3 else None)
    elif argv[:1] == ["today"]:
        run(dt.date.today() - dt.timedelta(days=10), dt.date.today())
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
