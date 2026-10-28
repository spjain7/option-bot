"""RR1-001 per-trade log for the owner to check on charts: 1h/3h calls from 22-Aug-2026, daily calls from 22-Oct-2025,
same rules as rr1.py (target 1R), with every price and time."""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import emax as EX, daily_candles as DC  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
START = {"1h": pd.Timestamp("2026-08-22"), "3h": pd.Timestamp("2026-08-22"), "1d": pd.Timestamp("2025-10-22")}


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
        v = f["volume"].astype(float); vx = (v / v.rolling(20).mean().shift(1)).values
        P, TR = DC.patterns(f)
        o, h, l = f["open"].values, f["high"].values, f["low"].values
        tm = pd.to_datetime(f["time"]).dt.tz_localize(None).values if pd.to_datetime(f["time"]).dt.tz is not None else f["time"].values
        fmt = "%d-%b-%Y" if tf == "1d" else "%d-%b-%Y %H:%M"
        ts = lambda k: pd.Timestamp(tm[k]).strftime(fmt)
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
                    if pd.Timestamp(tm[i]) < START[tf]:
                        continue
                    j = t["j"]
                    both = (t["why"] == "stop") and ((h[j] >= t["tp"]) if side > 0 else (l[j] <= t["tp"]))
                    rows.append({
                        "Timeframe": tf, "Market": seg.split()[0], "Instrument": job[1],
                        "Pattern": f"{'BUY' if side > 0 else 'SELL'} {pat}",
                        "Trend filter": "EMA20/50 trend (as asked)" if trend == "T1" else "any trend",
                        "Pattern candle": ts(i), "Pattern open": f["open"].iat[i], "Pattern high": f["high"].iat[i],
                        "Pattern low": f["low"].iat[i], "Pattern close": f["close"].iat[i], "Volume x avg": round(float(vx[i]), 2),
                        "Entry candle": ts(t["j0"]), "Entry (breakout)": round(t["e0"], 2), "Stop": round(t["st"], 2),
                        "Target 1R": round(t["tp"], 2), "Risk pts": round(t["R"], 2), "Risk %": round(t["R"] / t["e0"] * 100, 2),
                        "Exit candle": ts(j), "Exit price": round(t["px"], 2),
                        "Result": "WIN" if t["r1"] > 0 else "LOSS", "Exit reason": t["why"],
                        "Stop & target in same candle": "yes (booked as stop)" if both else "",
                        "Gross pts": round(t["gross"], 2), "Cost pts": round(t["cost"], 2),
                        "Net pts": round(t["gross"] - t["cost"], 2), "Net R": round(t["r1"], 2),
                        "Candles held": j - t["j0"] + 1})
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] in ("mi", "stk")]
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(run, J, chunksize=1) for r in x]
    T = pd.DataFrame(rows)
    T["_o"] = T["Pattern"].map({"BUY hammer": 0, "BUY bull engulfing": 1, "SELL hanging man": 2, "SELL bear engulfing": 3})
    T = T.sort_values(["Timeframe", "Market", "Instrument", "_o"]).drop(columns="_o")
    T.to_csv(OUT / "rr1_recent_log.csv.gz", index=False)
    print(len(T), T.groupby(["Timeframe", "Trend filter"]).size().to_dict())


if __name__ == "__main__":
    main()
