"""HAM-001 trade log (owner's request, 28-Oct-2026): every 1-hour hammer-breakout BUY / hanging-man-breakdown SELL with what
price did after the breakout, so the owner can judge each call.

Rule logged (one version, the most common reading of the owner's setup):
  trend T1 (BUY: EMA20 < EMA50 and previous close < EMA50 = downtrend; SELL: mirror = uptrend) · hammer / hanging-man shape
  (lower wick ≥ 2× body, upper wick ≤ 0.3× range) · entry when a candle within the next 3 breaks the pattern's high (BUY) /
  low (SELL), fill at that level or at the open if it gaps beyond · stop 0.05 ATR beyond the pattern's low (BUY) / high (SELL)
  · target 2R · time exit after 20 candles · one trade at a time per instrument (same as the backtest).
Extra columns (not used by the rule): swing trend T2, volume ×, the move after entry until the stop was touched (≤ 40 candles).
"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import reversal as RV, hammer as HM  # noqa: E402

OUT = ROOT / "research/program/results"
TGT, MAXB, WATCH = 2.0, 20, 40


def log(job):
    kind, a, b = job
    try:
        d = RV.mcx_index_1h(a, b) if kind == "mi" else RV.stock_1h(a, b)
    except Exception as e:
        print("skip", job, e); return []
    if d is None:
        return []
    seg, f, cost, _ = d
    shape, T, X = HM.feats(f)
    o, h, l, c, at, sw = (f[x].values for x in ("open", "high", "low", "close", "atr", "switch"))
    tm, n, rows = f["time"].values, len(c), []
    for side in (1, -1):
        sig = shape & T[side]["T1"]
        busy = -1
        for i in np.flatnonzero(sig):
            if i < 210 or i <= busy or i >= n - 2 or sw[i] or not at[i] > 0:
                continue
            st = l[i] - 0.05 * at[i] if side > 0 else h[i] + 0.05 * at[i]
            lvl = h[i] if side > 0 else l[i]
            j0 = None
            for j in range(i + 1, min(i + 4, n)):
                if sw[j]:
                    break
                if side * (o[j] - lvl) > 0:
                    j0, e0 = j, o[j]; break
                if (l[j] <= st) if side > 0 else (h[j] >= st):
                    break
                if (h[j] > lvl) if side > 0 else (l[j] < lvl):
                    j0, e0 = j, lvl; break
            if j0 is None:
                continue
            R = side * (e0 - st)
            if not R > 0:
                continue
            tp = e0 + side * TGT * R
            # rule exit
            px, why, j = None, None, j0
            while j < n:
                if j > j0 and sw[j]:
                    px, why, j = c[j - 1], "contract roll", j - 1; break
                if j > j0 and side * (o[j] - st) <= 0:
                    px, why = o[j], "stop (gap)"; break
                if (l[j] <= st) if side > 0 else (h[j] >= st):
                    px, why = st, "stop"; break
                if (h[j] >= tp) if side > 0 else (l[j] <= tp):
                    px, why = (o[j] if j > j0 and side * (o[j] - tp) > 0 else tp), "target 2R"; break
                if j - j0 >= MAXB - 1:
                    px, why = c[j], "time (20 candles)"; break
                j += 1
            if px is None:
                px, why, j = c[n - 1], "open (data ends)", n - 1
            # excursion until the stop is touched (≤ 40 candles; the stop candle's own favourable extreme is not counted)
            best, bt, worst_before_best, worst = e0, j0, e0, e0
            k, stop_t = j0, None
            while k < n and k - j0 < WATCH:
                if k > j0 and sw[k]:
                    break
                hit = (l[k] <= st) if side > 0 else (h[k] >= st)
                if hit:
                    stop_t = tm[k]; worst = st; break
                fav = h[k] if side > 0 else l[k]
                adv = l[k] if side > 0 else h[k]
                if side * (adv - worst) < 0:
                    worst = adv
                if side * (fav - best) > 0:
                    best, bt, worst_before_best = fav, k, worst
                k += 1
            gross = side * (px - e0)
            rows.append(dict(
                segment=seg.replace(" 1h", ""), instrument=a, call="BUY (hammer breakout)" if side > 0 else "SELL (hanging-man breakdown)",
                pattern_time=tm[i], pat_open=o[i], pat_high=h[i], pat_low=l[i], pat_close=c[i],
                pat_range_atr=round((h[i] - l[i]) / at[i], 2), volume_x=round(float(f["volx"].iat[i]), 2),
                swing_trend_T2=bool(T[side]["T2"][i]),
                entry_time=tm[j0], entry=round(e0, 2), stop=round(st, 2), target_2R=round(tp, 2),
                risk_pts=round(R, 2), risk_pct=round(R / e0 * 100, 2), risk_atr=round(R / at[i], 2),
                exit_time=tm[j], exit=round(px, 2), exit_reason=why,
                gross_pts=round(gross, 2), cost_pts=round(cost[i], 2), net_pts=round(gross - cost[i], 2),
                net_R=round((gross - cost[i]) / R, 2), cost_as_R=round(cost[i] / R, 2),
                best_after_entry=round(best, 2), best_time=tm[bt], best_move_pts=round(side * (best - e0), 2),
                best_move_pct=round(side * (best - e0) / e0 * 100, 2), best_move_R=round(side * (best - e0) / R, 2),
                worst_before_best=round(worst_before_best, 2), worst_before_best_R=round(side * (worst_before_best - e0) / R, 2),
                stop_touched_time=stop_t, reached_1R=side * (best - e0) >= R, reached_2R=side * (best - e0) >= 2 * R,
                reached_3R=side * (best - e0) >= 3 * R))
            busy = j
    return rows


def main():
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(log, HM.jobs(), chunksize=1) for r in x]
    T = pd.DataFrame(rows).sort_values(["segment", "instrument", "pattern_time"])
    T.to_csv(OUT / "ham_log_all.csv.gz", index=False)
    print(len(T), T["pattern_time"].max())


if __name__ == "__main__":
    main()
