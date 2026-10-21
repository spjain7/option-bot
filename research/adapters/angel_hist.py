"""Angel One SmartAPI history adapter (REAL exchange prices, contract level) - research only.

Pulls daily and 1-hour candles for every CURRENTLY LISTED futures contract of the registry
instruments (MCX commodities and NSE index futures). Angel serves no data for expired contracts,
so history is limited to the life of contracts that are still trading; MCX OI history is not
served at all (error AB1012). Nothing is filled in or extrapolated.

Needs the same secrets as the live bot (ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PIN, ANGEL_TOTP_SECRET).
Run from the repo root:  python -m research.adapters.angel_hist
Output: research/data/angel/<exch>/<SYMBOL>_<interval>.csv and research/data/angel/manifest.csv
Run it through the manual "Research data" workflow (same concurrency group as the live bot, so it
never competes with live alerts for the API quota).
"""
import sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "research" / "data" / "angel"
LIMIT_DAYS = {"ONE_DAY": 1900, "ONE_HOUR": 390}       # Angel per-request window limits (kept under)
MAX_PAGES = 4                                        # up to ~20 years daily / ~4 years hourly


def contracts(master, names):
    m = master[master["name"].isin(names) & master["instrumenttype"].isin(["FUTCOM", "FUTIDX"])
               & master["exch_seg"].isin(["MCX", "NFO"])]
    return m.sort_values(["name", "expiry_dt"])


def fetch_all(api, master, names, intervals=("ONE_DAY", "ONE_HOUR")):
    from angel import now_ist
    now = now_ist()
    rows = []
    cs = contracts(master, names)
    nearest = set(cs[cs["expiry_dt"] >= now.normalize()].groupby("name")["token"].first().astype(str))
    for _, c in cs.iterrows():
        for iv in intervals:
            # Angel serves a vendor-stitched FRONT-MONTH history on the nearest contract's token
            # (verified against NSE bhavcopy: same close as the front contract on 96% of days).
            # Page backwards for that token; other contracts only have their own short life.
            pages = MAX_PAGES if str(c["token"]) in nearest else 1
            parts, to = [], now
            for _ in range(pages):
                frm = to - pd.Timedelta(days=LIMIT_DAYS[iv])
                part = api.candles(c["exch_seg"], c["token"], iv, frm, to)
                if part is None or part.empty:
                    break
                parts.append(part)
                to = part["time"].min() - pd.Timedelta(minutes=1)
            df = pd.concat(parts).drop_duplicates("time").sort_values("time").reset_index(drop=True) if parts else None
            n = 0 if df is None else len(df)
            if n:
                d = OUT / c["exch_seg"]; d.mkdir(parents=True, exist_ok=True)
                df.assign(symbol=c["symbol"], name=c["name"], expiry=c["expiry_dt"]).to_csv(
                    d / f"{c['symbol']}_{iv}.csv", index=False)
            rows.append(dict(exch=c["exch_seg"], name=c["name"], symbol=c["symbol"], expiry=c["expiry_dt"],
                             interval=iv, bars=n, front_stitched=str(c["token"]) in nearest, first=None if not n else df["time"].min(),
                             last=None if not n else df["time"].max()))
            print(c["symbol"], iv, n, flush=True)
    man = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    old = OUT / "manifest.csv"
    if old.exists():                                   # partial re-fetch: keep rows of instruments not re-fetched
        prev = pd.read_csv(old)
        man = pd.concat([prev[~prev["name"].isin(man["name"].unique())], man], ignore_index=True)
    man.to_csv(OUT / "manifest.csv", index=False)
    return man


def main():
    from angel import Angel, load_master
    from research.instruments import REGISTRY
    import os
    names = [k for k, v in REGISTRY.items() if v["exchange"] in ("MCX", "NSE")]
    only = [x.strip() for x in os.getenv("RESEARCH_NAMES", "").split(",") if x.strip()]
    names = [n for n in names if n in only] if only else names
    fetch_all(Angel(), load_master(), names)


if __name__ == "__main__":
    main()
