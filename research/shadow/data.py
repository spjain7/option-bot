"""Shadow-engine data layer – official NSE end-of-day files only (no Angel calls, no orders).
  cash bhavcopy  (EQ / BE rows)            content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
  F&O bhavcopy   (stock + index futures)   content/fo/BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip  (+ lot size, token)
  F&O ban list   (no NEW positions)        archives/fo/sec_ban/fo_secban_DDMMYYYY.csv
  price bands    (cash circuit limits)     content/equities/sec_list.csv  (today's bands only -> stored daily)
History for the indicators: research-nse-cm yearly files (git) + the daily files above, cached in CACHE.
Best-5 depth: the ws-depth branch written by the production collector since 11-Nov-2026 (none before)."""
import datetime as dt
import io
import subprocess
import time
import zipfile
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/data/shadow_cache"
BASE = "https://nsearchives.nseindia.com"
UA = {"User-Agent": "Mozilla/5.0 (research shadow test; end-of-day archive)"}
CM_COLS = ["date", "symbol", "series", "isin", "open", "high", "low", "close", "prevclose", "volume", "value", "trades"]


def _get(url, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code == 404:
                return None, "missing"
            if r.status_code == 200:
                return r.content, "ok"
        except Exception as e:  # network error -> retry
            err = str(e)[:60]
        time.sleep(2 + 3 * i)
    return None, "error"


def parse_cm(raw, d):
    z = zipfile.ZipFile(io.BytesIO(raw)); df = pd.read_csv(z.open(z.namelist()[0])); df.columns = [c.strip() for c in df.columns]
    o = pd.DataFrame({"symbol": df.TckrSymb.str.strip(), "series": df.SctySrs.str.strip(), "isin": df.ISIN, "open": df.OpnPric,
                      "high": df.HghPric, "low": df.LwPric, "close": df.ClsPric, "prevclose": df.PrvsClsgPric, "volume": df.TtlTradgVol,
                      "value": df.TtlTrfVal, "trades": df.get("TtlNbOfTxsExctd", pd.NA)})
    o = o[o.series.isin(["EQ", "BE"])]; o.insert(0, "date", pd.Timestamp(d))
    return o[CM_COLS]


def parse_fo(raw, d):
    z = zipfile.ZipFile(io.BytesIO(raw)); df = pd.read_csv(z.open(z.namelist()[0]), low_memory=False); df.columns = [c.strip() for c in df.columns]
    df = df[df.FinInstrmTp.isin(["STF", "IDF"])]
    return pd.DataFrame({"date": pd.Timestamp(d), "symbol": df.TckrSymb.str.strip(), "kind": df.FinInstrmTp.map({"STF": "STK", "IDF": "IDX"}),
                         "expiry": pd.to_datetime(df.XpryDt), "token": df.FinInstrmId.astype(str), "open": df.OpnPric, "high": df.HghPric,
                         "low": df.LwPric, "close": df.ClsPric, "settle": df.SttlmPric, "contracts": df.TtlTradgVol, "value": df.TtlTrfVal,
                         "oi": df.OpnIntrst, "lot": df.NewBrdLotQty})


def day(kind, d):
    """kind 'cm' / 'fo' -> DataFrame for that trading day or None (holiday / not yet published). Cached as csv.gz."""
    d = pd.Timestamp(d).date(); f = CACHE / kind / f"{d:%Y%m%d}.csv.gz"
    if f.with_suffix(".holiday").exists():
        return None
    if f.exists():
        return pd.read_csv(f, parse_dates=["date"] + (["expiry"] if kind == "fo" else []), dtype={"token": str} if kind == "fo" else None)
    url = f"{BASE}/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip" if kind == "cm" else \
        f"{BASE}/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    raw, st = _get(url)
    if raw is None or raw[:2] != b"PK":
        if st == "missing" and d < dt.date.today() - dt.timedelta(days=3):     # old weekday without a file = holiday
            f.parent.mkdir(parents=True, exist_ok=True); f.with_suffix(".holiday").write_text("no file (holiday)")
        return None
    x = parse_cm(raw, d) if kind == "cm" else parse_fo(raw, d)
    f.parent.mkdir(parents=True, exist_ok=True); x.to_csv(f, index=False, compression="gzip")
    return x


def ban(d):
    """F&O securities in ban on trade date d (no new positions). None = file not available."""
    d = pd.Timestamp(d).date(); f = CACHE / "ban" / f"{d:%Y%m%d}.txt"
    if f.exists():
        return [s for s in f.read_text().split("\n") if s]
    raw, st = _get(f"{BASE}/archives/fo/sec_ban/fo_secban_{d:%d%m%Y}.csv")
    if raw is None or raw[:1] == b"<":
        return None
    names = [ln.split(",")[1].strip() for ln in raw.decode("utf-8", "ignore").splitlines()[1:] if "," in ln]
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text("\n".join(names))
    return names


def bands(d):
    """today's cash price bands (only the current file exists) -> stored per date; returns {symbol: band %} or None."""
    d = pd.Timestamp(d).date(); f = CACHE / "bands" / f"{d:%Y%m%d}.csv"
    if not f.exists():
        if d != dt.date.today():
            return None
        raw, st = _get(f"{BASE}/content/equities/sec_list.csv")
        if raw is None or raw[:1] == b"<":
            return None
        f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(raw)
    x = pd.read_csv(f); x.columns = [c.strip() for c in x.columns]
    return dict(zip(x.Symbol.str.strip(), x.Band.astype(str).str.strip()))


def cm_history(start, end, local=None):
    """cash rows start..end: research-nse-cm yearly files (local copy or git) + daily files for the rest."""
    parts = []
    years = range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1)
    src = Path(local) if local else CACHE / "cm_years"
    for y in years:
        f = src / f"{y}.csv.gz"
        if not f.exists() and not local:
            f.parent.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "--depth", "1", "origin", "research-nse-cm"], check=True)
                blob = subprocess.run(["git", "-C", str(ROOT), "show", f"FETCH_HEAD:research/data/nse_cm/{y}.csv.gz"], check=True, capture_output=True).stdout
                f.write_bytes(blob)
            except Exception:
                continue
        if f.exists():
            parts.append(pd.read_csv(f, parse_dates=["date"], low_memory=False))
    P = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=CM_COLS)
    last = P.date.max() if len(P) else pd.Timestamp(start)
    d = (last + pd.Timedelta(days=1)).date()
    while d <= pd.Timestamp(end).date():
        if d.weekday() < 5:
            x = day("cm", d)
            if x is not None:
                parts.append(x)
        d += dt.timedelta(days=1)
    P = pd.concat(parts, ignore_index=True)
    P = P[(P.date >= pd.Timestamp(start)) & (P.date <= pd.Timestamp(end))]
    return P.drop_duplicates(["date", "symbol", "series"], keep="last").reset_index(drop=True)


def fo_days(start, end):
    out = []
    d = pd.Timestamp(start).date()
    while d <= pd.Timestamp(end).date():
        if d.weekday() < 5:
            x = day("fo", d)
            if x is not None:
                out.append(x)
        d += dt.timedelta(days=1)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def depth_rows(date):
    """Best-5 snapshots recorded by the production collector on that date (ws-depth branch). Empty if none."""
    f = CACHE / "depth" / f"{pd.Timestamp(date):%Y%m%d}.csv.gz"
    if f.exists():
        return pd.read_csv(f, dtype={"token": str})
    try:
        subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "--depth", "1", "origin", "ws-depth"], check=True, capture_output=True)
        names = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", "FETCH_HEAD"], check=True, capture_output=True, text=True).stdout.split()
    except Exception:
        return pd.DataFrame()
    want = [n for n in names if f"depth_{pd.Timestamp(date):%Y%m%d}" in n and n.endswith(".csv.gz")]
    parts = []
    for n in want:
        blob = subprocess.run(["git", "-C", str(ROOT), "show", f"FETCH_HEAD:{n}"], check=True, capture_output=True).stdout
        parts.append(pd.read_csv(io.BytesIO(blob), compression="gzip", dtype={"token": str}))
    x = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if len(x):
        f.parent.mkdir(parents=True, exist_ok=True); x.to_csv(f, index=False, compression="gzip")
    return x
