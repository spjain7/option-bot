"""MCX daily bhavcopy WITH OPEN INTEREST (official, free) -> research/data/mcx_bhav/days/YYYYMMDD.csv  (29-Oct-2026)

Why: Angel serves no MCX OI history, so commodity OI rules (long buildup / short covering ...) could not be backtested.
MCX publishes every futures / options contract's daily OHLC, volume and OI (lots) on https://www.mcxindia.com/market-data/bhavcopy.
The site is behind an Akamai firewall: a Chrome-TLS session (curl_cffi, as the mcx-data package does) is used.

  python -m research.adapters.mcx_bhav today                 # the day shown on the bhavcopy page (run after the MCX close)
  python -m research.adapters.mcx_bhav backfill 2022-07-01 [end]   # date-wise history (MCX backpage endpoint; best effort)
Keeps futures (FUTCOM) and options on futures (OPTFUT) of the followed commodities (+ their MINI contracts). Research only.
"""
import json
import re
import sys
import time
import datetime as dt
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "data" / "mcx_bhav" / "days"
BASE = "https://www.mcxindia.com"
NAMES = {"CRUDEOIL", "CRUDEOILM", "NATURALGAS", "NATGASMINI", "GOLD", "GOLDM", "GOLDPETAL", "GOLDGUINEA", "SILVER", "SILVERM",
         "SILVERMIC", "COPPER", "ZINC", "ZINCMINI", "ALUMINIUM", "ALUMINI", "LEAD", "LEADMINI", "NICKEL"}
HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9", "Referer": f"{BASE}/market-data/bhavcopy"}
COLS = {"Date": "date", "Symbol": "symbol", "InstrumentName": "instrument", "ExpiryDate": "expiry", "StrikePrice": "strike",
        "OptionType": "opt", "Open": "open", "High": "high", "Low": "low", "Close": "close", "PreviousClose": "prev_close",
        "Volume": "volume_lots", "VolumeInThousands": "volume_k", "Value": "value_lakh", "OpenInterest": "oi_lots"}


def session():
    from curl_cffi.requests import Session
    s = Session(impersonate="chrome124")
    s.headers.update(HEAD)
    r = s.get(f"{BASE}/market-data/bhavcopy", timeout=30)        # warm-up: cookies from the firewall
    return s, r


def clean(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.rename(columns={k: v for k, v in COLS.items() if k in df.columns})
    keep = [v for v in COLS.values() if v in df.columns]
    df = df[keep].copy()
    df["symbol"] = df["symbol"].astype(str).str.strip()
    df["instrument"] = df["instrument"].astype(str).str.strip()
    df = df[df["instrument"].isin(["FUTCOM", "OPTFUT"]) & df["symbol"].isin(NAMES)]
    if "date" in df:
        d = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")
        df["date"] = d.fillna(pd.to_datetime(df["date"], errors="coerce")).dt.strftime("%Y-%m-%d")
    return df.reset_index(drop=True)


def save(df):
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for d, g in df.groupby("date"):
        g.to_csv(OUT / f"{d.replace('-', '')}.csv", index=False); n += 1
    return n


def today():
    s, r = session()
    if r.status_code != 200:
        raise SystemExit(f"bhavcopy page HTTP {r.status_code} (firewall?)")
    m = re.search(r'<div[^>]+id=["\']bhavcopy-data["\'][^>]*>(.*?)</div>', r.text, re.DOTALL)
    if not m:
        raise SystemExit("bhavcopy page has no preloaded data block – page layout changed?")
    df = clean(json.loads(m.group(1).strip() or "[]"))
    print(f"today: {len(df)} rows, dates {sorted(df['date'].unique()) if len(df) else []}, saved {save(df)} day file(s)")
    fut = df[df["instrument"] == "FUTCOM"] if len(df) else df
    if len(fut):
        print(fut.sort_values("expiry").groupby("symbol").head(1)[["date", "symbol", "expiry", "close", "volume_lots", "oi_lots"]].to_string(index=False))


def _rows(js):
    """Find the list of bhavcopy rows anywhere in an ASP.NET JSON reply ({'d': {...'Data': [...]}} or similar)."""
    if isinstance(js, list) and js and isinstance(js[0], dict):
        return js
    if isinstance(js, dict):
        for v in js.values():
            r = _rows(v)
            if r is not None:
                return r
    if isinstance(js, str):
        try:
            return _rows(json.loads(js))
        except Exception:
            return None
    return None


def backfill(start, end=None):
    s, _ = session()
    d0 = dt.date.fromisoformat(start)
    d1 = dt.date.fromisoformat(end) if end else dt.date.today() - dt.timedelta(days=1)
    ok = miss = err = 0
    tried_first = False
    d = d0
    while d <= d1:
        if d.weekday() < 5 and not (OUT / f"{d:%Y%m%d}.csv").exists():
            try:
                r = s.post(f"{BASE}/backpage.aspx/GetDateWiseBhavCopy",
                           json={"Date": f"{d:%Y%m%d}", "InstrumentName": "ALL"},
                           headers={"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"}, timeout=40)
                rows = _rows(r.json()) if r.status_code == 200 and r.text.strip().startswith("{") else None
                if not tried_first:
                    tried_first = True
                    print(f"first request {d}: HTTP {r.status_code}, {len(r.text)} bytes, rows {None if rows is None else len(rows)}; "
                          f"start of reply: {r.text[:200]!r}")
                    if r.status_code != 200 or rows is None:
                        raise SystemExit("date-wise endpoint not usable from here – only the daily 'today' mode will build history")
                df = clean(rows or [])
                if len(df):
                    if "date" not in df or df["date"].isna().all():
                        df["date"] = f"{d:%Y-%m-%d}"
                    save(df); ok += 1
                else:
                    miss += 1
            except SystemExit:
                raise
            except Exception as e:
                err += 1
                print(f"{d}: {type(e).__name__} {str(e)[:120]}")
                if err > 20:
                    print("too many errors – stopping"); break
                time.sleep(5)
            time.sleep(1.5)
        d += dt.timedelta(days=1)
    print(f"backfill done: saved {ok} days, empty/holiday {miss}, errors {err}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "today"
    today() if mode == "today" else backfill(*sys.argv[2:])
