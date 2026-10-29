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
        fut = fut.assign(_e=pd.to_datetime(fut["expiry"], format="%d%b%Y", errors="coerce"))
        print(fut.sort_values("_e").groupby("symbol").head(1)[["date", "symbol", "expiry", "close", "volume_lots", "oi_lots"]].to_string(index=False))


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


# from the page's own script (assets/customjs/BhavCopy.js, 29-Oct-2026):
#   GetData("/GetDateWiseBhavCopy", "GET", {InstrumentName, fromDate}) -> response.Data
FORMATS = ["%Y%m%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d%b%Y"]
CANDIDATES = [("GET", "/GetDateWiseBhavCopy", f) for f in FORMATS]


def _ask(s, how, path, fmt, d):
    h = {"Accept": "application/json, text/javascript, */*; q=0.01", "X-Requested-With": "XMLHttpRequest",
         "Referer": f"{BASE}/market-data/bhavcopy"}
    r = s.get(BASE + path, params={"InstrumentName": "ALL", "fromDate": d.strftime(fmt).upper() if "%b" in fmt else d.strftime(fmt)},
              headers=h, timeout=40)
    t = r.text.strip()
    rows = None
    if r.status_code == 200 and t[:1] in "{[":
        try:
            rows = _rows(r.json())
        except Exception:
            rows = None
    return r, rows


def probe(s):
    """Print the endpoint names the bhavcopy page's own scripts use (to find the date-wise call when MCX changes it)."""
    r = s.get(f"{BASE}/market-data/bhavcopy", timeout=30)
    names = set(re.findall(r"['\"/]((?:backpage\.aspx/)?Get[A-Za-z]*Bhav[A-Za-z]*)", r.text, re.I))
    for m in re.finditer(r"Get(DateWise|Commoditywise)BhavCopy", r.text):
        print("   page:", r.text[max(0, m.start() - 300):m.end() + 300].replace("\n", " ")[:620])
    js = re.findall(r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)', r.text)
    for u in js[:25]:
        try:
            jt = s.get(u if u.startswith("http") else BASE + ("" if u.startswith("/") else "/") + u, timeout=30).text
            for m in re.findall(r"['\"/]((?:backpage\.aspx/)?Get[A-Za-z]*Bhav[A-Za-z]*)", jt, re.I):
                names.add(m)
            for m in list(re.finditer(r"Get(DateWise|Commoditywise)BhavCopy", jt))[:3]:
                print("   js:", u[-50:], "…", jt[max(0, m.start() - 300):m.end() + 300].replace("\n", " ")[:620])
        except Exception:
            pass
    print("bhavcopy endpoint names seen on the page / its scripts:", sorted(names) or "none")


def backfill(start, end=None):
    s, _ = session()
    d0 = dt.date.fromisoformat(start)
    d1 = dt.date.fromisoformat(end) if end else dt.date.today() - dt.timedelta(days=1)
    test_day = dt.date(2026, 10, 27)                      # a recent trading day with data
    use = None
    for how, path, mode in CANDIDATES:
        try:
            r, rows = _ask(s, how, path, mode, test_day)
            print(f"try {how} {path} fromDate {test_day.strftime(mode)}: HTTP {r.status_code}, {len(r.text)} bytes, rows {None if rows is None else len(rows)}, "
                  f"reply starts {r.text.strip()[:90]!r}")
            if rows:
                use = (how, path, mode); break
        except Exception as e:
            print(f"try {how} {path}: {type(e).__name__} {str(e)[:100]}")
    if use is None:
        probe(s)
        raise SystemExit("no date-wise bhavcopy endpoint answered – history builds from the daily 'today' run only")
    print("using", use)
    ok = miss = err = 0
    d = d0
    while d <= d1:
        if d.weekday() < 5 and not (OUT / f"{d:%Y%m%d}.csv").exists():
            try:
                r, rows = _ask(s, *use, d)
                df = clean(rows or [])
                if len(df):
                    if "date" not in df or df["date"].isna().all():
                        df["date"] = f"{d:%Y-%m-%d}"
                    save(df); ok += 1
                else:
                    miss += 1
            except Exception as e:
                err += 1
                print(f"{d}: {type(e).__name__} {str(e)[:120]}")
                if err > 25:
                    print("too many errors – stopping"); break
                time.sleep(5)
                try:
                    s, _ = session()
                except Exception:
                    pass
            time.sleep(1.2)
            if (ok + miss) % 100 == 0 and ok + miss:
                print(f"... {d}: saved {ok}, empty {miss}", flush=True)
        d += dt.timedelta(days=1)
    print(f"backfill done: saved {ok} days, empty/holiday {miss}, errors {err}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "today"
    today() if mode == "today" else backfill(*sys.argv[2:])
