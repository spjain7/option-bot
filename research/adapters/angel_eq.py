"""NSE CASH EQUITY history (6-Nov-2026, owner: cash-equity strategy workstream) – research only, no alerts.

Universe : Nifty 500 constituents (+ industry) from niftyindices.com / NSE archives when reachable; fallback = every NSE
           stock with a futures contract (the most liquid names). The universe file records its source and date.
           NOTE survivorship: Angel serves only currently listed symbols and today's index membership – delisted / dropped
           stocks are missing. Research therefore selects the universe point-in-time by trailing turnover from the data
           itself and states the bias.
Daily    : ONE_DAY for every universe stock + NIFTY 50 / NIFTY BANK / NIFTY 500 indices, up to ~20 years (4 pages × 1900 d).
Intraday : FIVE_MINUTE for the futures-eligible (most liquid) stocks + NIFTY 50, EQ_M5_PAGES × 95 days (default 8 ≈ 2 y).
Prices   : Angel cash candles are NOT adjusted for splits / bonuses – research/program/eq_data.py detects and adjusts them.
Output   : research/data/angel/NSE_EQ/<SYMBOL>_<interval>.csv.gz + universe.csv + manifest.csv (resumable: existing files skipped)
python -m research.adapters.angel_eq"""
import io
import os
import sys
import time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "research" / "data" / "angel" / "NSE_EQ"
URLS = ["https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
        "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"]
INDICES = {"NIFTY": "Nifty 50", "BANKNIFTY": "Nifty Bank", "NIFTY500": "Nifty 500", "NIFTY100": "Nifty 100",
           "NIFTYMID100": "NIFTY MIDCAP 100", "NIFTYIT": "Nifty IT", "NIFTYAUTO": "Nifty Auto", "NIFTYPHARMA": "Nifty Pharma",
           "NIFTYMETAL": "Nifty Metal", "NIFTYFMCG": "Nifty FMCG", "NIFTYENERGY": "Nifty Energy", "NIFTYREALTY": "Nifty Realty",
           "NIFTYPSUBANK": "Nifty PSU Bank", "NIFTYFIN": "Nifty Fin Service", "NIFTYMEDIA": "Nifty Media", "NIFTYINFRA": "Nifty Infra"}


def nifty500():
    import requests
    for u in URLS:
        try:
            r = requests.get(u, timeout=30, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"})
            if r.ok and "Symbol" in r.text[:500]:
                d = pd.read_csv(io.StringIO(r.text))
                return d.rename(columns={"Symbol": "symbol", "Industry": "industry", "Company Name": "company"})[
                    ["symbol", "industry", "company"]], u
        except Exception as e:
            print("universe source failed:", u, type(e).__name__, flush=True)
    return None, None


def universe(master):
    fo = sorted(set(master[(master["exch_seg"] == "NFO") & (master["instrumenttype"] == "FUTSTK")]["name"]) - {""})
    fo = [x for x in fo if "NSETEST" not in x]
    n5, src = nifty500()
    if n5 is None:
        n5, src = pd.DataFrame(dict(symbol=fo, industry="", company="")), "fallback: NSE stocks with futures (Angel master)"
    n5["fno"] = n5["symbol"].isin(fo)
    extra = pd.DataFrame(dict(symbol=[s for s in fo if s not in set(n5["symbol"])], industry="", company="", fno=True))
    u = pd.concat([n5, extra], ignore_index=True)
    eq = master[(master["exch_seg"] == "NSE") & master["symbol"].str.endswith("-EQ")].drop_duplicates("name").set_index("name")
    u["token"] = u["symbol"].map(eq["token"].astype(str))
    u = u.dropna(subset=["token"])
    u["source"], u["asof"] = src, pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    return u


def index_tokens(master):
    m = master[(master["exch_seg"] == "NSE") & (master["instrumenttype"] == "AMXIDX")]
    out = {}
    for k, nm in INDICES.items():
        x = m[m["symbol"].str.upper() == nm.upper()]
        if not x.empty:
            out[k] = str(x["token"].iat[0])
    return out


def pull(api, token, iv, pages, days):
    from angel import now_ist
    to, parts = now_ist(), []
    for _ in range(pages):
        frm = to - pd.Timedelta(days=days)
        try:
            part = api.candles("NSE", token, iv, frm, to)
        except Exception as e:
            print("  error", type(e).__name__, e, flush=True); part = None
        if part is None or part.empty:
            break
        parts.append(part)
        to = part["time"].min() - pd.Timedelta(minutes=1)
    return pd.concat(parts).drop_duplicates("time").sort_values("time").reset_index(drop=True) if parts else None


def main():
    from angel import Angel, load_master
    api, master = Angel(), load_master()
    OUT.mkdir(parents=True, exist_ok=True)
    u = universe(master)
    u.to_csv(OUT / "universe.csv", index=False)
    print(f"universe {len(u)} stocks ({u['fno'].sum()} with futures) · source {u['source'].iat[0]}", flush=True)
    jobs = [(k, t, "ONE_DAY") for k, t in index_tokens(master).items()]
    jobs += [("NIFTY", t, "FIVE_MINUTE") for k, t in index_tokens(master).items() if k == "NIFTY"]
    jobs += [(r.symbol, r.token, "ONE_DAY") for r in u.itertuples()]
    jobs += [(r.symbol, r.token, "FIVE_MINUTE") for r in u[u["fno"]].itertuples()]
    pages = {"ONE_DAY": 4, "FIVE_MINUTE": int(os.getenv("EQ_M5_PAGES", "8"))}
    days = {"ONE_DAY": 1900, "FIVE_MINUTE": 95}
    t_end = time.time() + float(os.getenv("EQ_MAX_MIN", "270")) * 60          # stop cleanly before the job timeout
    rows = []
    for sym, tok, iv in jobs:
        f = OUT / f"{sym}_{iv}.csv.gz"
        if f.exists():
            continue
        if time.time() > t_end:
            print("time budget reached – remaining symbols next run", flush=True); break
        df = pull(api, tok, iv, pages[iv], days[iv])
        n = 0 if df is None else len(df)
        if n:
            df.to_csv(f, index=False, compression="gzip")
        rows.append(dict(symbol=sym, token=tok, interval=iv, bars=n, first=df["time"].min() if n else None,
                         last=df["time"].max() if n else None))
        print(sym, iv, n, flush=True)
    man = OUT / "manifest.csv"
    old = pd.read_csv(man) if man.exists() else pd.DataFrame()
    pd.concat([old, pd.DataFrame(rows)], ignore_index=True).drop_duplicates(["symbol", "interval"], keep="last").to_csv(man, index=False)


if __name__ == "__main__":
    main()
