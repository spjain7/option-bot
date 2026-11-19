"""Download NSE participant-wise open interest (fao_participant_oi_DDMMYYYY.csv: Client / DII / FII / Pro long & short
contracts in index futures, stock futures and options) for every trading day in research/data/nse_cm since 2010 ->
research/data/nse_poi/poi.parquet (date, client_type, columns as published). Public NSE archive, no login. 4 threads.
python -m research.cashq.poi_fetch"""
import concurrent.futures as cf
import io
import sys
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
OUTD = ROOT / "research/data/nse_poi"
URL = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{}.csv"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


def days(start="2010-01-01"):
    ds = set()
    for p in sorted((ROOT / "research/data/nse_cm").glob("20*.csv.gz")):
        if int(p.stem[:4]) >= int(start[:4]):
            ds |= set(pd.read_csv(p, usecols=["date"]).date.unique())
    for p in (ROOT / "research/data/nse_cm/days").glob("*.csv.gz"):
        ds |= set(pd.read_csv(p, usecols=["date"]).date.unique())
    return sorted(pd.to_datetime(list(ds)))


def one(d, s):
    for k in range(3):
        try:
            r = s.get(URL.format(d.strftime("%d%m%Y")), headers=UA, timeout=30)
            if r.status_code == 404:
                return d, None
            if r.status_code == 200 and "Client Type" in r.text[:400]:
                t = pd.read_csv(io.StringIO(r.text), skiprows=1)
                t.columns = [c.strip() for c in t.columns]
                t = t[t["Client Type"].astype(str).str.strip().isin(["Client", "DII", "FII", "Pro", "TOTAL"])].copy()
                t.insert(0, "date", d)
                return d, t
        except Exception:  # noqa: BLE001
            pass
    return d, None


def main():
    OUTD.mkdir(parents=True, exist_ok=True)
    f = OUTD / "poi.parquet"
    have = set(pd.read_parquet(f).date.unique()) if f.exists() else set()
    todo = [d for d in days() if d not in have]
    print("to fetch", len(todo), flush=True)
    got = []; s = requests.Session()
    with cf.ThreadPoolExecutor(4) as ex:
        for i, (d, t) in enumerate(ex.map(lambda d: one(d, s), todo)):
            if t is not None:
                got.append(t)
            if i % 300 == 0:
                print(i, d.date(), len(got), flush=True)
    if got:
        new = pd.concat(got, ignore_index=True)
        for c in new.columns[2:]:
            new[c] = pd.to_numeric(new[c], errors="coerce")
        if f.exists():
            new = pd.concat([pd.read_parquet(f), new])
        new.drop_duplicates(["date", "Client Type"]).sort_values(["date", "Client Type"]).to_parquet(f, index=False)
    print("done", len(got), flush=True)


if __name__ == "__main__":
    main()
