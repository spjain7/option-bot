"""Nightly NSE F&O bhavcopy (official, end of day: every futures & options contract – OHLC, volume, OI) saved as the
original zip to research/data/nse_bhav_raw/YYYYMMDD.zip (30-Oct-2026). From NSE's public archive – no Angel calls.
Fetches the last 7 calendar days that are missing (fills gaps after a skipped night).
python -m research.adapters.nse_daily"""
import datetime as dt
import sys
from pathlib import Path
import requests
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.adapters.nse_bhavcopy import url, UA  # noqa: E402

OUT = ROOT / "research" / "data" / "nse_bhav_raw"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    for k in range(7, -1, -1):
        d = today - dt.timedelta(days=k)
        f = OUT / f"{d:%Y%m%d}.zip"
        if d.weekday() >= 5 or f.exists():
            continue
        try:
            r = requests.get(url(d), headers=UA, timeout=90)
        except Exception as e:
            print(d, "error", type(e).__name__); continue
        if r.status_code == 200 and r.content[:2] == b"PK":
            f.write_bytes(r.content); print(d, "saved", len(r.content), "bytes")
        else:
            print(d, "not available", r.status_code)


if __name__ == "__main__":
    main()
