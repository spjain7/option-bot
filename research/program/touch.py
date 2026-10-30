"""TOUCH-001 (30-Oct-2026, owner: "a 3h candle breaks out mid-candle and we only call at the close – we miss the move").
Question: for the live breakout rules, does entering the moment price CROSSES the level (inside the candle) beat waiting for the
candle CLOSE and entering at the next open?

Rules tested (the live settings):
  MCX 3h BUY    N=10, vol 1.5x, stop 2 ATR, 2R      MCX 4h BUY    N=10, vol 2x, stop 1.5 ATR, 3R
  STK 3h SELL   N=20, vol 1.5x, stop 2 ATR, 2R      STK 4h SELL   N=5,  vol 2x, stop 2 ATR, 2R
  (all: EMA200 trend filter, stop cap 2.5 % MCX / 4 % stocks, max 40 candles, one trade at a time per instrument)

Entry variants (all simulated on the same 1-hour bars, same exit engine, 2x costs):
  CLOSE        today's rule: close beyond the level with full-candle volume ≥ vx, entry at the next candle's open
  TOUCH@lvl    first 1-hour bar inside the candle that crosses the level -> entry AT the level (or the bar's open on a gap);
               ideal instant alert; no volume check (volume not known yet); trend = previous candle's close vs EMA200
  TOUCH@1h     same, but entry at the CLOSE of the 1-hour bar that crossed (realistic: alert within the hour)
  TOUCH+pace   TOUCH@1h and volume so far in the candle ≥ vx × average candle volume × share of the candle elapsed
  TOUCH+cut    TOUCH@lvl, but exit at the candle close if the candle closes back inside the level (false break cut)
Cautious fills: if the entry bar itself touches the stop, the stop is counted.
python research/program/touch.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX  # noqa: E402
from research.program.tf5h import T1, T2  # noqa: E402

RULES = {("MCX", 3): dict(side=1, N=10, vx=1.5, k=2.0, r=2.0), ("MCX", 4): dict(side=1, N=10, vx=2.0, k=1.5, r=3.0),
         ("STOCKS", 3): dict(side=-1, N=20, vx=1.5, k=2.0, r=2.0), ("STOCKS", 4): dict(side=-1, N=5, vx=2.0, k=2.0, r=2.0)}
VARS = ("CLOSE", "TOUCH@lvl", "TOUCH@1h", "TOUCH+pace", "TOUCH+cut")
MAXC = 40


def blocks(f1, market, n):
    if market == "MCX":
        hr = f1["time"].dt.hour
        key = f1["time"].dt.normalize().astype("int64") // 10**9 * 10 + ((hr - 9).clip(lower=0) // n)
    else:
        key = pd.Series(np.arange(len(f1)) // n)
    cid = pd.factorize(key)[0]
    g = f1.groupby(cid, sort=True)
    C = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
              volume=("volume", "sum"), switch=("switch", "max")).reset_index(drop=True)
    return C, cid


def run(f1, cost1, market, n, rule):
    f1 = f1.reset_index(drop=True)
    C, cid = blocks(f1, market, n)
    if len(C) < 260:
        return []
    F = H.features(C); F["switch"] = C["switch"].values
    side, N, vx, k, r = rule["side"], rule["N"], rule["vx"], rule["k"], rule["r"]
    cap = 2.5 if market == "MCX" else 4.0
    lvl = (F.high.shift(1).rolling(N).max() if side > 0 else F.low.shift(1).rolling(N).min()).values
    cl, ema, atr, va, vol = F.close.values, F.ema200.values, F.atr.values, F.va.values, F.volume.values.astype(float)
    o1, h1, l1, c1, v1, sw1 = (f1[x].values.astype(float) for x in ("open", "high", "low", "close", "volume", "switch"))
    first = np.r_[0, np.flatnonzero(np.diff(cid)) + 1]           # first 1h row of each candle
    last = np.r_[first[1:] - 1, len(f1) - 1]
    size = last - first + 1
    out = []
    for var in VARS:
        busy = -1
        for i in range(210, len(C) - 1):
            if not (atr[i - 1] > 0 and np.isfinite(lvl[i])) or F["switch"].iat[i]:
                continue
            if var == "CLOSE":
                ok = side * (cl[i] - lvl[i]) > 0 and vol[i] > vx * va[i] and side * (cl[i] - ema[i]) > 0
                if not ok or F["switch"].iat[i + 1]:
                    continue
                j0 = first[i + 1]
                if j0 <= busy:
                    continue
                e0, R, start = o1[j0], k * atr[i], j0
            else:
                if first[i] <= busy or not side * (cl[i - 1] - ema[i - 1]) > 0:
                    continue
                jj = [j for j in range(first[i], last[i] + 1) if (h1[j] > lvl[i] if side > 0 else l1[j] < lvl[i])]
                if not jj:
                    continue
                j0 = jj[0]
                if var == "TOUCH+pace":
                    done = (j0 - first[i] + 1) / max(n, 1)
                    if not v1[first[i]:j0 + 1].sum() >= vx * va[i] * done:
                        continue
                if var in ("TOUCH@lvl", "TOUCH+cut"):
                    e0 = max(lvl[i], o1[j0]) if side > 0 else min(lvl[i], o1[j0])
                else:
                    e0 = c1[j0]
                    if side * (e0 - lvl[i]) < 0:                     # crossed and fell back inside within the hour – no alert
                        continue
                R, start = k * atr[i - 1], j0
            if R / e0 * 100 > cap:
                continue
            st, tp = e0 - side * R, e0 + side * r * R
            maxh = MAXC * n
            px = why = None
            cut_at = last[i] if var == "TOUCH+cut" else -1
            j = start
            while j < len(f1):
                if j > start and sw1[j]:
                    px, why, j = c1[j - 1], "roll", j - 1; break
                if j > start and ((o1[j] <= st) if side > 0 else (o1[j] >= st)):
                    px, why = o1[j], "stop-gap"; break
                if j > start and ((o1[j] >= tp) if side > 0 else (o1[j] <= tp)):
                    px, why = o1[j], "target-gap"; break
                if (l1[j] <= st) if side > 0 else (h1[j] >= st):
                    px, why = st, "stop"; break
                if j > start and ((h1[j] >= tp) if side > 0 else (l1[j] <= tp)):
                    px, why = tp, "target"; break
                if var != "CLOSE" and j == start and var in ("TOUCH@1h", "TOUCH+pace"):
                    pass
                if j == cut_at and side * (c1[j] - lvl[i]) <= 0:
                    px, why = c1[j], "cut"; break
                if j - start >= maxh:
                    px, why = c1[j], "time"; break
                j += 1
            if px is None:
                px, why, j = c1[-1], "end", len(f1) - 1
            cst = cost1[min(start, len(cost1) - 1)]
            out.append((var, C["time"].iat[i], (side * (px - e0) - 2 * cst) / R, why, side * (e0 - lvl[i]) / atr[i - 1]))
            busy = j
    return out


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return []
    rows = []
    for seg, f0, od, cost in fr:
        market, tf0 = seg.split()[0], seg.split()[-1]
        if tf0 != "1h" or market not in ("MCX", "STOCKS"):
            continue
        c_ = np.interp(np.arange(len(f0)), np.linspace(0, len(f0) - 1, len(cost)), cost)
        for n in (3, 4):
            for x in run(f0, c_, market, n, RULES[(market, n)]):
                rows.append((market, n, job[1]) + x)
    return rows


def main():
    J = [j for j in EX.jobs() if (j[0] == "mi" and j[2] == "MCX") or j[0] == "stk"]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(one, J, chunksize=2) for r in x]
    T = pd.DataFrame(rows, columns=["market", "hours", "name", "var", "time", "r2", "exit", "slip_atr"])
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T["split"] = np.where(T.time < T1, "train", np.where(T.time < T2, "valid", "test"))
    T.to_csv(ROOT / "research/program/results/touch_trades.csv.gz", index=False)
    keys = ["market", "hours", "var"]
    S = T.groupby(keys).agg(n=("r2", "size"), R=("r2", "mean"), win=("r2", lambda s: (s > 0).mean()), slip=("slip_atr", "mean")) \
        .join(T.pivot_table(index=keys, columns="split", values="r2", aggfunc="mean")[["train", "valid", "test"]])
    S["all3"] = (S[["train", "valid", "test"]] > 0).all(axis=1)
    S["totalR"] = S["n"] * S["R"]
    pd.set_option("display.width", 220)
    print(S.round(3).to_string())
    S.reset_index().to_csv(ROOT / "research/program/results/touch_summary.csv", index=False)
    print("\nexit mix:")
    print(T.groupby(keys).exit.value_counts(normalize=True).unstack().round(2).to_string())


if __name__ == "__main__":
    main()
