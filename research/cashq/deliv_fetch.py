"""Download NSE security-wise DELIVERY POSITION files (MTO_DDMMYYYY.DAT, nsearchives.nseindia.com/archives/equities/mto) for
every trading day in research/data/nse_cm and save the EQ-series rows as research/data/nse_deliv/<year>.parquet
(columns date, symbol, traded_qty, deliv_qty, deliv_pct). Public NSE archive files, no login. Polite: 4 threads, retries.
python -m research.cashq.deliv_fetch [extra bhav dir with *.csv.gz for days after the nse_cm history]"""
import concurrent.futures as cf
import io
import sys
import time
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CM = ROOT / "research/data/nse_cm"; OUTD = ROOT / "research/data/nse_deliv"
URL = "https://nsearchives.nseindia.com/archives/equities/mto/MTO_{}.DAT"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


def days():
    ds = set()
    for p in sorted(CM.glob("20*.csv.gz")):
        ds |= set(pd.read_csv(p, usecols=["date"]).date.unique())
    if len(sys.argv) > 1:
        for p in Path(sys.argv[1]).glob("*.csv.gz"):
            try:
                ds |= set(pd.read_csv(p, usecols=["date"]).date.unique())
            except Exception:  # noqa: BLE001
                pass
    return sorted(pd.to_datetime(list(ds)))


def one(d, s):
    for k in range(4):
        try:
            r = s.get(URL.format(d.strftime("%d%m%Y")), headers=UA, timeout=30)
            if r.status_code == 404:
                return d, None
            if r.status_code == 200 and r.text.startswith("Security Wise"):
                rows = [x.split(",") for x in r.text.splitlines() if x.startswith("20,")]
                df = pd.DataFrame([x[:7] for x in rows], columns=["rt", "sr", "symbol", "series", "traded_qty", "deliv_qty", "deliv_pct"])
                df = df[df.series.str.strip() == "EQ"]
                out = pd.DataFrame({"date": d, "symbol": df.symbol.str.strip(), "traded_qty": pd.to_numeric(df.traded_qty, errors="coerce"),
                                    "deliv_qty": pd.to_numeric(df.deliv_qty, errors="coerce"), "deliv_pct": pd.to_numeric(df.deliv_pct, errors="coerce")})
                return d, out
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1 + 2 * k)
    return d, "ERR"


def main():
    OUTD.mkdir(parents=True, exist_ok=True)
    D = days(); have = set()
    for p in OUTD.glob("*.parquet"):
        have |= set(pd.read_parquet(p, columns=["date"]).date.unique())
    todo = [d for d in D if d not in have]
    print("days", len(D), "to fetch", len(todo), flush=True)
    by_year = {}; miss = []; s = requests.Session()
    with cf.ThreadPoolExecutor(4) as ex:
        for i, (d, df) in enumerate(ex.map(lambda d: one(d, s), todo)):
            if df is None or isinstance(df, str):
                miss.append((str(d.date()), df or "404")); continue
            by_year.setdefault(d.year, []).append(df)
            if i % 250 == 0:
                print(i, d.date(), len(df), flush=True)
    for y, L in by_year.items():
        p = OUTD / f"{y}.parquet"
        new = pd.concat(L)
        if p.exists():
            new = pd.concat([pd.read_parquet(p), new])
        new.drop_duplicates(["date", "symbol"]).sort_values(["date", "symbol"]).to_parquet(p, index=False)
    (OUTD / "missing.txt").write_text("\n".join(f"{a} {b}" for a, b in miss))
    print("done; missing", len(miss), flush=True)


if __name__ == "__main__":
    main()
