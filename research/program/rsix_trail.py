"""RSIX-TRAIL-001 – independent check (plain-Python simulator written separately from rsix.sim) of the live RSIX rule with
its current 3R target vs a 3-ATR chandelier trailing stop, on the roll-ADJUSTED daily series (rollcheck.adjust).
Semantics identical to what live can do: setup on the completed daily candle; buy-stop at its high for 3 sessions (cancelled
if its low trades first); entry = max(trigger, open); SL entry - 1.5 ATR(setup); trailing stop recomputed after each daily
close = highest high since entry - 3 ATR(14, that day), only ratchets up, applies from the next session; time exit 20
sessions; 2x MCX costs. python research/program/rsix_trail.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import rsix as RX  # noqa: E402
from research.program.rollcheck import adjust  # noqa: E402
from research.program.missed import RB  # noqa: E402
from research import instruments as INS  # noqa: E402

def run(name, mode):
    d = adjust(RX.daily_long(name)).reset_index(drop=True)
    ff = RB.features(d); b, _ = RB.raw(ff, "RSIX", "7/30")
    o, h, l, c, a = d.open.values, d.high.values, d.low.values, d.close.values, ff.atr.values
    out, i, n = [], 220, len(d)
    while i < n - 2:
        if not b[i]:
            i += 1; continue
        trig, inv, j = h[i], l[i], None
        for t in range(i + 1, min(i + 4, n)):
            if o[t] < inv or (l[t] < inv and h[t] <= trig):
                break
            if h[t] > trig:
                j = t; break
        if j is None:
            i += 1; continue
        e = max(trig, o[j]); risk = 1.5 * a[i]; st = e - risk; tgt = e + 3 * risk; best = e
        cost = 2 * INS.cost_points(name, e, 1.0)
        px, k = None, j
        while k < n:
            if k > j and o[k] <= st:
                px, why = o[k], "gap stop"; break
            if l[k] <= st:
                px, why = st, "stop" if st < e else ("trail" if st > e else "stop"); break
            if mode == "3R" and h[k] >= tgt and (k > j):
                px, why = (o[k] if o[k] >= tgt else tgt), "target"; break
            if mode == "TR":
                best = max(best, h[k]); st = max(st, best - 3 * a[k])
            if k - j >= 20:
                px, why = c[k], "time"; break
            k += 1
        if px is None:
            px, why, k = c[n - 1], "open", n - 1
        out.append(dict(name=name, time=d.time[i], R=(px - e - cost) / risk, bars=k - j, why=why))
        i = k + 1
    return out

def stats(T):
    w, ls = T.R[T.R > 0], T.R[T.R <= 0]; eq = T.sort_values("time").R.cumsum()
    return dict(n=len(T), win=round(100 * (T.R > 0).mean(), 1), R=round(T.R.mean(), 3), PF=round(w.sum() / -ls.sum(), 2),
                avg_win=round(w.mean(), 2), avg_loss=round(ls.mean(), 2), maxDD=round((eq.cummax() - eq).max(), 1),
                bars=round(T.bars.mean(), 1), **{f"p{k}": round(T.R[(T.time >= s) & (T.time < e_)].mean(), 3) for k, (s, e_) in
                enumerate((("2006", "2013"), ("2013", "2020"), ("2020", "2027")), 1)}, names_pos=int((T.groupby("name").R.mean() > 0).sum()))

if __name__ == "__main__":
    res = {}
    for mode in ("3R", "TR"):
        T = pd.DataFrame([x for nm in RX.NAMES for x in run(nm, mode)])
        res[mode] = T
        print(mode, stats(T))
        print("   exit reasons:", T.why.value_counts().to_dict())
    # walk-forward: rolling 5-year windows, which exit wins
    A, B = res["3R"].set_index("time").R, res["TR"].set_index("time").R
    print("\nrolling 5-year windows (3R vs TR):")
    for y in range(2006, 2023, 2):
        s, e = pd.Timestamp(f"{y}"), pd.Timestamp(f"{y + 5}")
        a_, b_ = A[(A.index >= s) & (A.index < e)], B[(B.index >= s) & (B.index < e)]
        print(f"  {y}-{y + 4}: 3R {a_.mean():+.2f} ({len(a_)})  TR {b_.mean():+.2f} ({len(b_)})")
    yr = pd.DataFrame({"3R": A.groupby(A.index.year).sum(), "TR": B.groupby(B.index.year).sum()})
    print("\nyears TR better:", int((yr.TR > yr["3R"]).sum()), "of", len(yr))
    # bootstrap the difference (paired by setup date)
    m = res["3R"].merge(res["TR"], on=["name", "time"], suffixes=("_3", "_t"))
    diff = (m.R_t - m.R_3).values; rng = np.random.default_rng(1)
    bs = [rng.choice(diff, len(diff)).mean() for _ in range(5000)]
    print(f"paired setups {len(m)}: TR - 3R = {diff.mean():+.3f}R, 90% CI [{np.percentile(bs, 5):+.3f}, {np.percentile(bs, 95):+.3f}]")
    pd.concat([res["3R"].assign(exit="3R"), res["TR"].assign(exit="TR")]).to_csv(ROOT / "research/program/results/rsix_trail_trades.csv", index=False)
