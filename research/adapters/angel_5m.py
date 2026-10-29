"""5-MIN-001 (29-Oct-2026, owner: "find what volume / OI do before every 1-2 % move; also 5-min intraday calls").
Fetches 5-minute data for all stock F&O names (research only, no alerts):
  eq_<NAME>.csv   NSE cash 5-min OHLCV, last ~95 days (Angel keeps equity history; no OI in cash)
  fut_<NAME>.csv  current-month futures 5-min OHLCV + 5-min OI (Angel serves only live contracts -> since listing)
Resumable (existing files are skipped), gentle on Angel's rate limit (waits out blocks).
python -m research.adapters.angel_5m"""
import sys, time
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from angel import Angel, load_master, now_ist  # noqa: E402

OUT = ROOT / "research" / "data" / "m5"


def get(api, fn, *a, tries=6):
    for k in range(tries):
        r = fn(*a)
        if r is not None and len(r):
            return r
        if hasattr(api, "failfast") and api.failfast():
            api.wait_clear(max_s=120) if hasattr(api, "wait_clear") else time.sleep(60)
        else:
            time.sleep(3 + 3 * k)
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    api, master, now = Angel(), load_master(), now_ist()
    api._ws_on = False                                  # research: plain REST only
    fut = master[(master["exch_seg"] == "NFO") & (master["instrumenttype"] == "FUTSTK") & (master["expiry_dt"] >= now.normalize())]
    fut = fut.sort_values("expiry_dt").groupby("name").head(1)
    eq = master[(master["exch_seg"] == "NSE") & master["symbol"].str.endswith("-EQ")].set_index("name")["token"].astype(str).to_dict()
    ok = miss = 0
    for r in fut.itertuples():
        name = r.name
        fe, ff = OUT / f"eq_{name}.csv", OUT / f"fut_{name}.csv"
        if not fe.exists() and name in eq:
            c = get(api, api.candles, "NSE", eq[name], "FIVE_MINUTE", now - pd.Timedelta(days=95), now)
            if c is not None:
                c.to_csv(fe, index=False)
        if not ff.exists():
            c = get(api, api.candles, "NFO", str(r.token), "FIVE_MINUTE", now - pd.Timedelta(days=95), now)
            if c is not None:
                oi = get(api, api.oi_history, "NFO", str(r.token), "FIVE_MINUTE", now - pd.Timedelta(days=95), now, tries=3)
                c = c.merge(oi[["time", "oi"]], on="time", how="left") if oi is not None else c.assign(oi=float("nan"))
                c.assign(symbol=r.symbol).to_csv(ff, index=False)
        got = fe.exists() and ff.exists()
        ok += got; miss += not got
        print(f"{name}: eq {'ok' if fe.exists() else '-'} fut {'ok' if ff.exists() else '-'}", flush=True)
    print(f"done: complete {ok}, incomplete {miss}")


if __name__ == "__main__":
    main()
