"""Cycle 3 · 4 – index futures 1-hour CONTINUATION BUY on an UNTOUCHED window.
Angel's front-month hourly index futures history was re-fetched on 12-Nov-2026 00:45 IST (outside live hours) with a
higher page limit: NIFTY / BANKNIFTY now start 1-Apr-2016, FINNIFTY Jan-2021, MIDCPNIFTY Jan-2022. Contracts are
identified exactly as before (15:15 close matched to the NSE F&O bhavcopy, which starts 2018), so the usable untouched
window is Jan-2018 -> Jun-2022 (before the Jul-2022 start of every earlier study). FINNIFTY from Jul-2021 and MIDCPNIFTY
from Jul-2023 as before (thin early contracts).
Rules fixed from cycle 2 – no threshold changes: B1 = RSI(14) crosses to >= 75, B2 = S10; BUY next open, structure stop,
2R and 3R, max 21 bars, trades never span a contract or a session (as research/rsidiv/index.py), index-futures costs.
Benchmark: every 10th bar, same exits.          python -m research.cycle3.index_untouched"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E, index as IX, stockfut as SF  # noqa: E402
from research.cycle2 import common as C  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
NEW = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "research/data/angel/NFO_2026-11-12"
CUTS = [("UNTOUCHED", "2018-01-01"), ("DEV", "2022-07-01"), ("VAL", "2024-07-01"), ("OOS", "2025-07-01")]


def main():
    X = IX.idx_rows(); pool = E.Pool()
    old_ang = IX.ANG; IX.ANG = NEW
    for g, name in enumerate(IX.NAMES):
        f = NEW / f"{name}23NOV26FUT_ONE_HOUR.csv"
        if not f.exists():
            continue
        f.rename(NEW / f"{name}27OCT26FUT_ONE_HOUR.csv") if not (NEW / f"{name}27OCT26FUT_ONE_HOUR.csv").exists() else None
        d, x = IX.daily(X, name)
        h = IX.hourly(name, x)
        if h is None or len(h) < 500:
            continue
        b = h.reset_index(drop=True)
        ev, risk, _ = C.base_events(b)
        expid = pd.to_datetime(b["contract"]).values.astype("datetime64[D]").astype(np.int64)
        day = pd.to_datetime(b["time"]).dt.normalize().values.astype("datetime64[D]").astype(np.int64)
        grp = g * 10 ** 6 + (expid - expid.min())
        every = np.zeros(len(b), bool); every[::10] = True
        S = {("B1", "x", "x", 1): ev["B1"], ("B2", "x", "x", 1): ev["B2"], ("EVERY10", "x", "x", 1): every}
        pool.add(b, S, risk["structure"], grp, SF.fut_cost(b["time"].values, slip=0.0001, notional=1.5e6), expid, name)
        print(name, len(b), b.time.iloc[0], b.time.iloc[-1], flush=True)
    IX.ANG = old_ang
    pool.freeze(); res = {}
    for key in (("B1", "x", "x", 1), ("B2", "x", "x", 1), ("EVERY10", "x", "x", 1)):
        for R in (2.0, 3.0):
            T = pool.run(key, R, 21)
            lab = E.periods(T.entry.values, CUTS)
            r = {}
            for p, _ in CUTS:
                x = T.netR.values[lab == p]; w = x > 0
                r[p] = dict(n=int(len(x)), R=round(float(x.mean()), 3) if len(x) else None, win=round(100 * float(w.mean()), 1) if len(x) else None,
                            PF=round(float(x[w].sum() / -x[~w].sum()), 2) if len(x) and (~w).any() else None)
            u = T[lab == "UNTOUCHED"]
            if len(u) > 2:
                dm = u.groupby(pd.to_datetime(u.entry).dt.normalize()).netR.mean()
                r["UNTOUCHED"]["t_day"] = round(float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm)))), 2)
                r["UNTOUCHED_by_index"] = {n: round(float(g.netR.mean()), 3) for n, g in u.groupby("name")}
                r["UNTOUCHED_by_year"] = {int(y): (int(len(g)), round(float(g.netR.mean()), 3)) for y, g in u.groupby(pd.to_datetime(u.entry).dt.year)}
            res[f"{key[0]} {R}R"] = r
    json.dump(res, open(OUT / "index_untouched.json", "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
