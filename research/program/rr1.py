"""RR1-001 (28-Oct-2026) – owner's request: the four candle patterns with a 1:1 risk-reward only.
  BUY : hammer after a downtrend, bullish engulfing after a downtrend
  SELL: hanging man after an uptrend, bearish engulfing after an uptrend
Candles / windows: 1-hour and 3-hour → last 2 months (pattern from 22-Aug-2026); daily → last 1 year (from 22-Oct-2025).
Data ends 21/22-Oct-2026. Full 2022-26 history is also reported for comparison.
Rules (same as DCP-001, daily_candles.py): shapes and EMA20/50 trend (T1) as there, also "any trend"; entry on a break of the
pattern candle's high (BUY) / low (SELL) within 3 candles; stop 0.05 ATR beyond the pattern (engulfing: two-candle low/high);
target 1R; time exit after 20 candles; gap through stop or target fills at the open; contract-roll exit; costs 1×.
When one candle touches both stop and target (order unknown) the trade is booked as a stop; the count is reported and the
"best case" win rate treats them as targets.
"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX, daily_candles as DC  # noqa: E402
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
        P, TR = DC.patterns(f)
        o, h, l = f["open"].values, f["high"].values, f["low"].values
        tm = f["time"].values
        for (pat, side), (shape, sref, trig) in P.items():
            for trend in ("T1", "any"):
                sig = shape & (TR[side] if trend == "T1" else True)
                busy = -1
                for i in np.flatnonzero(sig):
                    if i < 60 or i <= busy or i >= len(f) - 2 or f["switch"].iat[i] or not f["atr"].iat[i] > 0:
                        continue
                    t = DC.trade(f, i, side, sref[i], trig[i], "E2", 1.0, cost)
                    if t is None:
                        continue
                    busy = t["j"]
                    j = t["j"]
                    both = (t["why"] == "stop") and ((h[j] >= t["tp"]) if side > 0 else (l[j] <= t["tp"]))
                    win_if = (side * (t["tp"] - t["e0"]) - t["cost"]) / t["R"]
                    rows.append((seg.split()[0], tf, job[1], f"{'BUY' if side > 0 else 'SELL'} {pat}", trend, tm[i], tm[t["j0"]],
                                 t["why"], t["r1"], t["gross"] / t["R"], both, win_if, t["R"] / t["e0"] * 100, j - t["j0"] + 1))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] in ("mi", "stk")]
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(run, J, chunksize=1) for r in x]
    T = pd.DataFrame(rows, columns=["market", "tf", "name", "pattern", "trend", "pattern_time", "entry_time", "exit_reason",
                                    "net_R", "gross_R", "both_touched", "net_R_if_target", "risk_pct", "bars"])
    T["pattern_time"] = pd.to_datetime(T["pattern_time"], format="mixed")
    T.to_csv(OUT / "rr1_trades.csv.gz", index=False)
    print(len(T))


if __name__ == "__main__":
    main()
