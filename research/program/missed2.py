"""MISSED-002 – the 45 missed DOWN moves and 13 missed V-reversal UP moves of MISSED-001, one by one, on 4h candles.
For each move: earliest actionable entry per structure setup (stop-entry below/above the setup candle, structure stop,
3R, 2x costs), immediate breakdown (S_C) vs retest (S_B) vs failed recovery (S_A) vs continuation (S_D); how many of the
same setups FAILED in the 30 sessions before the move (the cost of waiting for it); and the honest precision of each setup
on all its 2022-26 signals. python research/program/missed2.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import rsix as RX, structx as SX  # noqa: E402
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402

M = pd.read_csv(ROOT / "research/program/results/missed_moves.csv")
miss = M[~M.caught].copy()
rows, allsig = [], []
for name in RX.NAMES:
    fr = dict(RX.frames(name)); f = fr["4h"].reset_index(drop=True)
    o, h, l, c = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
    atr = I.atr(f, 14).values.astype(np.float64); sw = f.switch.fillna(False).values.astype(np.bool_)
    cost = np.array([INS.cost_points(name, p, 1.0) for p in c], np.float64)
    t = pd.to_datetime(f.time)
    S = SX.setups(f, "4h")
    res = {}
    for su in ("S_A_FAILREC", "S_B_RETEST", "S_C_MOMO", "S_D_PBCONT", "B_MSS", "B_MOMO", "B_EMA921"):
        side, idx, lv, iv = S[su]
        oi, rr, gg = SX.sim(o, h, l, c, atr, sw, idx.astype(np.int64), np.asarray(lv, float), np.asarray(iv, float), side, 1, 0, 3, 40, 6, cost, 1.5)
        res[su] = (side, idx, dict(zip(oi, rr)))
        allsig += [(name, su, t.iloc[i], r) for i, r in zip(oi, rr) if t.iloc[i] >= pd.Timestamp("2022-08-01")]
    d = RX.daily_long(name)
    for _, mv in miss[miss.name == name].iterrows():
        dr = 1 if mv.dir == "UP" else -1
        t0, t1 = pd.Timestamp(mv.start), pd.Timestamp(mv.end) + pd.Timedelta(hours=23)
        seg = d[(d.time >= t0) & (d.time <= t1)]
        p0, p1 = seg.close.iloc[0], seg.close.iloc[-1]; half = p0 + 0.5 * (p1 - p0)
        th = seg.time[(dr * (seg.close - half)) >= 0].iloc[0] + pd.Timedelta(hours=23)
        rec = dict(name=name, dir=mv.dir, start=mv.start, end=mv.end, move_pct=mv.move_pct)
        for su, (side, idx, rmap) in res.items():
            if side != dr:
                continue
            ti = t.iloc[idx]
            early = [i for i in idx[(ti.values > np.datetime64(t0)) & (ti.values <= np.datetime64(th))] if i in rmap]
            before = [i for i in idx[(ti.values > np.datetime64(t0 - pd.Timedelta(days=45))) & (ti.values <= np.datetime64(t0))] if i in rmap]
            rec[su] = round(rmap[early[0]], 2) if early else np.nan
            rec[su + "_when"] = str(t.iloc[early[0]])[:13] if early else ""
            rec[su + "_failed_before"] = sum(1 for i in before if rmap[i] <= 0)
        rows.append(rec)
R = pd.DataFrame(rows); A = pd.DataFrame(allsig, columns=["name", "setup", "time", "R"])
R.to_csv(ROOT / "research/program/results/missed2_moves.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100)
for dr, sus in (("DOWN", ["S_A_FAILREC", "S_B_RETEST", "S_C_MOMO", "S_D_PBCONT"]), ("UP", ["B_MSS", "B_MOMO", "B_EMA921"])):
    x = R[R.dir == dr]
    print(f"\n=== missed {dr} moves: {len(x)}")
    for su in sus:
        e = x[su].dropna()
        a = A[A.setup == su].R
        print(f"{su:12s} early entry on {len(e):2d}/{len(x)} moves · R on those {e.mean():+.2f} · failed same setups in the 45 days before "
              f"{int(x[su + '_failed_before'].sum()):3d} · ALL its signals 2022-26: n {len(a)} win {100 * (a > 0).mean():.0f}% R {a.mean():+.2f}")
    got = x[sus].notna().any(axis=1)
    print(f"moves with at least one early structure entry: {got.sum()}/{len(x)}")
print("\nper-move detail (DOWN): first-entry R per setup")
print(R[R.dir == "DOWN"][["name", "start", "end", "move_pct", "S_A_FAILREC", "S_B_RETEST", "S_C_MOMO", "S_D_PBCONT"]].to_string(index=False))
print("\nper-move detail (UP reversals)")
print(R[R.dir == "UP"][["name", "start", "end", "move_pct", "B_MSS", "B_MSS_when", "B_MOMO", "B_EMA921"]].to_string(index=False))
