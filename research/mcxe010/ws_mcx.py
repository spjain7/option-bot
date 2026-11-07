"""MCXE-010: MCX bars from the live bot's WebSocket recordings (branch ws-bars, written by scripts/market_loop.sh –
existing data, no API calls). Loads every file, keeps MCX futures, de-duplicates overlapping exports, resamples 1-minute
bars to 5-minute bars (time = bar start, IST) and validates them against the Angel 5-minute research store on the
overlapping days.  python research/mcxe010/ws_mcx.py  -> research/mcxe010/ws_validation.csv"""
import io
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
MCX7 = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]


def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, check=True).stdout


def load_ws():
    git("fetch", "-q", "origin", "ws-bars")
    files = [x for x in git("ls-tree", "-r", "--name-only", "origin/ws-bars").decode().split("\n") if x.endswith(".csv.gz")]
    parts = []
    for f in files:
        d = pd.read_csv(io.BytesIO(git("show", f"origin/ws-bars:{f}")), compression="gzip")
        d = d[(d.exch == "MCX") & d.symbol.str.endswith("FUT") & d.name.isin(MCX7)]
        if len(d):
            parts.append(d.assign(src=f))
    A = pd.concat(parts, ignore_index=True)
    A["time"] = pd.to_datetime(A.time)
    # overlapping exports: keep the row from the LATEST file for each (symbol, minute) – later exports have complete bars
    A = A.sort_values(["symbol", "time", "src"]).drop_duplicates(["symbol", "time"], keep="last")
    return A


def to5m(A):
    A = A.copy(); A["t5"] = A.time.dt.floor("5min")
    g = A.groupby(["name", "symbol", "expiry", "t5"])
    B = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
              oi=("oi", "last"), minutes=("time", "size")).reset_index().rename(columns={"t5": "time"})
    return B


def validate(B):
    from research.program import liqtl_mcx5 as LM
    rows = []
    for n in MCX7:
        a = LM.load(n, "FIVE_MINUTE"); b = B[B.name == n]
        m = a.merge(b, on="time", suffixes=("_ang", "_ws"))
        m = m[m.minutes == 5]                                    # only complete ws 5-minute bars
        if not len(m):
            rows.append(dict(name=n, overlap_bars=0)); continue
        rel = (m.close_ws / m.close_ang - 1).abs()
        rows.append(dict(name=n, ws_symbol=b.symbol.iat[-1], overlap_bars=len(m), first=m.time.min(), last=m.time.max(),
                         close_match_pct=round(100 * (rel < 1e-6).mean(), 1), close_within_1tick_pct=round(100 * (rel < 2e-4).mean(), 1),
                         median_abs_rel_diff=float(rel.median()), high_match_pct=round(100 * (m.high_ws == m.high_ang).mean(), 1)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    A = load_ws(); B = to5m(A)
    print(A.groupby("name").time.agg(["min", "max", "size"]).to_string())
    # minute coverage per session day (MCX session ~ 09:00-23:30/23:55)
    A["day"] = A.time.dt.normalize()
    print(A.groupby(["name", "day"]).size().unstack(0).to_string())
    print(A.groupby(A.time.dt.hour).size().to_string())
    V = validate(B); print(V.to_string(index=False))
    V.to_csv(ROOT / "research/mcxe010/ws_validation.csv", index=False)
