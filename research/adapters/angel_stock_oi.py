"""Historical OI for NSE stock futures (read-only). MODE=probe -> test range limits on 2 stocks; MODE=fetch -> all stocks.
Output: research/data/angel/NFO_STK/<NAME>_OI_ONE_HOUR.csv"""
import os, sys, time
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
OUT = ROOT / "research" / "data" / "angel" / "NFO_STK"


def oi(api, tok, iv, frm, to):
    time.sleep(0.8)
    try:
        r = api.api.getOIData({"exchange": "NFO", "symboltoken": tok, "interval": iv,
                               "fromdate": frm.strftime("%Y-%m-%d %H:%M"), "todate": to.strftime("%Y-%m-%d %H:%M")})
    except Exception as e:
        return None, f"{type(e).__name__}"
    d = (r or {}).get("data")
    return (pd.DataFrame(d) if isinstance(d, list) and d else None), f"{(r or {}).get('message')} {(r or {}).get('errorcode')}"


def main():
    from angel import Angel, load_master, now_ist
    from alerts.stocks import universe
    api, master, now = Angel(), load_master(), now_ist()
    uni = universe(master, now)
    OUT.mkdir(parents=True, exist_ok=True)
    if os.getenv("MODE", "probe") == "probe":
        for name in list(uni)[:2]:
            for iv in ("ONE_HOUR", "ONE_DAY"):
                for days in (30, 60, 100, 200, 400, 1000):
                    d, msg = oi(api, uni[name]["token"], iv, now - pd.Timedelta(days=days), now)
                    print(name, iv, days, "rows", 0 if d is None else len(d), "first", None if d is None else d.iloc[0].to_dict(), msg, flush=True)
        return
    rows = []
    for name, c in uni.items():
        parts, to = [], now
        for _ in range(int(os.getenv("PAGES", "8"))):
            d, msg = oi(api, c["token"], os.getenv("IV", "ONE_DAY"), to - pd.Timedelta(days=int(os.getenv("DAYS", "1000"))), to)
            if d is None:
                break
            d["time"] = pd.to_datetime(d["time"])
            if d["time"].dt.tz is not None:
                d["time"] = d["time"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
            parts.append(d)
            to = d["time"].min() - pd.Timedelta(minutes=1)
        if parts:
            df = pd.concat(parts).drop_duplicates("time").sort_values("time")
            df.to_csv(OUT / f"{name}_OI_{os.getenv('IV', 'ONE_DAY')}.csv", index=False)
            rows.append(dict(name=name, rows=len(df), first=df["time"].min(), last=df["time"].max()))
        print(name, sum(len(p) for p in parts), flush=True)
    pd.DataFrame(rows).to_csv(OUT / "manifest_oi.csv", index=False)


if __name__ == "__main__":
    main()
