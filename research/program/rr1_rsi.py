"""RR1-RSI (28-Oct-2026) – owner's request: make the 1:1 reversal candle trades clearer with RSI and volume.
Base: rr1.py rules (pattern, breakout entry within 3 candles, stop beyond the pattern, target 1R, 20-candle time exit, costs).
Every pattern signal is simulated on its own (overlapping trades allowed), with its features recorded, so each filter is
applied afterwards on the same trades:
  RSI(14) – BUY: lowest RSI of the pattern candle and the 2 before ≤ 30 (or ≤ 25); SELL: highest ≥ 70 (or ≥ 75)
  Volume  – pattern candle volume ≥ 1.5× / 2× its 20-candle average; "selling/buying climax": the candle before the
            pattern had ≥ 1.5× volume; breakout volume cannot be used (the entry happens inside that candle)
  Trend   – EMA20/50 as before, or any
Windows: 1h / 3h from 22-Aug-2026, daily from 22-Oct-2025 (recent); 2022-26 full history; chronological periods
train < Jul-24 ≤ valid < Jul-25 ≤ test for the consistency check.
"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX, daily_candles as DC, reversal as RV  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"


def run(job):
    try:
        fr = EX.frames(job)
    except Exception as e:
        print("skip", job[:2], e); return []
    rows = []
    for seg, f, _od, cost in fr:
        if "NSE" in seg or "proxy" in seg:
            continue
        tf = seg.split()[-1]
        f = f.reset_index(drop=True)
        if len(f) < 120:
            continue
        f["atr"] = I.atr(f, 14)
        r = RV.rsi(f["close"])
        rmin, rmax = r.rolling(3).min().values, r.rolling(3).max().values
        v = f["volume"].astype(float); vx = (v / v.rolling(20).mean().shift(1)).values
        vxp = np.r_[np.nan, vx[:-1]]
        P, TR = DC.patterns(f)
        h, l = f["high"].values, f["low"].values
        tm = f["time"].values
        for (pat, side), (shape, sref, trig) in P.items():
            for i in np.flatnonzero(shape):
                if i < 60 or i >= len(f) - 2 or f["switch"].iat[i] or not f["atr"].iat[i] > 0:
                    continue
                t = DC.trade(f, i, side, sref[i], trig[i], "E2", 1.0, cost)
                if t is None:
                    continue
                j = t["j"]
                both = (t["why"] == "stop") and ((h[j] >= t["tp"]) if side > 0 else (l[j] <= t["tp"]))
                rows.append((seg.split()[0], tf, job[1], f"{'BUY' if side > 0 else 'SELL'} {pat}", tm[i], bool(TR[side][i]),
                             rmin[i] if side > 0 else rmax[i], vx[i], vxp[i], t["why"], t["r1"], both, t["R"] / t["e0"] * 100,
                             f["high"].iat[i], f["low"].iat[i], tm[t["j0"]], t["e0"], t["st"], t["tp"], t["R"], tm[j], t["px"],
                             t["gross"], t["cost"], j - t["j0"] + 1))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] in ("mi", "stk")]
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(run, J, chunksize=1) for r in x]
    T = pd.DataFrame(rows, columns=["market", "tf", "name", "pattern", "time", "trend_ok", "rsi_ext", "volx", "volx_prev",
                                    "exit_reason", "net_R", "both_touched", "risk_pct", "pat_high", "pat_low", "entry_time",
                                    "entry", "stop", "target", "risk_pts", "exit_time", "exit", "gross_pts", "cost_pts", "bars"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T.to_csv(OUT / "rr1_rsi_trades.csv.gz", index=False)
    print(len(T))


if __name__ == "__main__":
    main()
