"""RSIX-001 transfer test to NSE – the MCX finalist applied UNCHANGED (no re-optimisation): RSI(7) touch <= 30 (>= 70 for SELL),
bullish (bearish) candle, ADX(14) < 20, stop-entry beyond the candle's high (low) for 3 candles, SL 1.5 ATR, exit 3R or 3-ATR trail.
NSE statistics kept separate from MCX. Indices: NIFTY / BANKNIFTY futures daily 2011-26. Stocks: 181 futures daily 2022-26.
python research/program/rsix_nse.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import rsix as RX, harness as H, emax as EX, search_all as SA  # noqa: E402
from crude import indicators as I  # noqa: E402

def run(d, cost, side):
    d = d.reset_index(drop=True)
    o, h, l, c = (d[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
    atr = I.atr(d, 14).values.astype(np.float64)
    sw = d["switch"].fillna(False).values.astype(np.bool_) if "switch" in d else np.zeros(len(d), np.bool_)
    M = RX.setup_masks(d, 7)[(side, "E1", 30, "bull")]
    adx = np.nan_to_num(I.adx(d, 14).values, nan=99) < 20
    idx = (np.flatnonzero((M & adx)[200:]) + 200).astype(np.int64)
    out = {}
    for ex, code in (("3R", 3), ("TR", 0)):
        ii, jj, rr, gg = RX.sim(o, h, l, c, atr, sw, idx, side, 1, 1, code, 20, np.asarray(cost, np.float64))
        out[ex] = pd.DataFrame(dict(time=d.time.values[ii], R=rr))
    return out

def summ(T, cuts):
    if not len(T):
        return "no trades"
    p = np.where(T.time < cuts[0], 0, np.where(T.time < cuts[1], 1, 2))
    per = [f"{T.R[p == k].mean():+.2f}({(p == k).sum()})" for k in range(3)]
    w, ls = T.R[T.R > 0], T.R[T.R <= 0]
    return f"n {len(T)} win {100 * (T.R > 0).mean():.0f}% R {T.R.mean():+.2f} PF {w.sum() / max(1e-9, -ls.sum()):.2f} periods {' '.join(per)}"

if __name__ == "__main__":
    print("INDEX daily 2011-26 (periods <2016 / 2016-20 / 2021+)")
    for nm in ("NIFTY", "BANKNIFTY"):
        d = H.nseidx(nm); cost = H.cost_series(nm, d, "nseidx")
        for side in (1, -1):
            r = run(d, cost, side)
            for ex in r:
                print(f"  {nm:9s} {'BUY ' if side > 0 else 'SELL'} {ex}: {summ(r[ex], (pd.Timestamp('2016'), pd.Timestamp('2021')))}")
    print("\nSTOCKS daily 2022-26 (periods <2024-07 / 2024-07..2025-07 / later)")
    acc = {(s, e): [] for s in (1, -1) for e in ("3R", "TR")}
    for job in [j for j in EX.jobs() if j[0] == "stk"]:
        try:
            res = SA.frames_for(job)
        except Exception:
            continue
        for mk, tf, f, c_, fd in res:
            if tf != "1d" or len(f) < 260:
                continue
            for side in (1, -1):
                r = run(f, c_, side)
                for ex in r:
                    acc[(side, ex)].append(r[ex].assign(name=job[1]))
    for (side, ex), L in acc.items():
        T = pd.concat(L) if L else pd.DataFrame(columns=["time", "R", "name"])
        nm_pos = (T.groupby("name").R.mean() > 0).mean() if len(T) else np.nan
        print(f"  STOCKS {'BUY ' if side > 0 else 'SELL'} {ex}: {summ(T, (pd.Timestamp('2024-07-01'), pd.Timestamp('2025-07-01')))} · "
              f"names positive {100 * nm_pos:.0f}% of {T.name.nunique()}")
