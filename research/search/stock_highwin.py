"""STOCK-HIGHWIN-001 – trial-and-error for 80-90% accuracy on stock futures (lot < 3000), daily candles.
Entries (long and long+short where meaningful): rsi2_long, bb_long, gap_go_long, nr7_long, vb_long, any_dip (close < EMA20 in uptrend).
Exits: target T×ATR ∈ {0.25,0.5,0.75,1.0}, stop S×ATR ∈ {1.5,2,3,4,6}, max hold H ∈ {3,5,10} days; next-open entries,
stop checked first, full costs. QUALIFY: win ≥ 80% AND expectancy > 0 at 2× costs in BOTH periods (≤Jun-24 / ≥Jul-24),
≥ 100 trades each. Accuracy alone is not a pass.
"""
import itertools, json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from alerts import stocks as STK  # noqa
from research.search import stock_check as SC, stock_search as SR  # noqa

ENT = ["rsi2_long", "bb_long", "gap_go_long", "nr7_long", "vb_long", "dip_ema20"]
TG, SL, HD = [0.25, 0.5, 0.75, 1.0], [1.5, 2.0, 3.0, 4.0, 6.0], [3, 5, 10]


def entries(d):
    c, h, l, o, v = d["close"], d["high"], d["low"], d["open"], d["volume"].astype(float)
    e200, e50, e20 = I.ema(c, 200), I.ema(c, 50), I.ema(c, 20)
    m, sd = c.rolling(20).mean(), c.rolling(20).std()
    rng = h - l
    pos = (c - l) / rng.replace(0, np.nan)
    va = v.rolling(20).mean().shift(1)
    nr7 = (rng <= rng.rolling(7).min()).shift(1).fillna(False).astype(bool)
    return {"rsi2_long": (I.rsi(c, 2) < 10) & (c > e200), "bb_long": (c < m - 2 * sd) & (c > e200),
            "gap_go_long": (o > c.shift(1) * 1.01) & (pos > 0.75), "nr7_long": nr7 & (c > h.shift(1)) & (c > e50),
            "vb_long": (c > h.shift(1).rolling(20).max()) & (v > 1.5 * va) & (c > e200),
            "dip_ema20": (c < e20) & (e20 > e50) & (e50 > e200)}


def main():
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    rows = []
    for r in man.itertuples():
        f = SR.DATA / f"{r.name}_ONE_HOUR.csv"
        if not f.exists():
            continue
        d = SR.daily(pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]).reset_index(drop=True)
        if len(d) < 260:
            continue
        a = I.atr(d, 14).values
        o, h, l, c = (d[k].values for k in ("open", "high", "low", "close"))
        t = d["time"].values
        E = {k: v.fillna(False).values for k, v in entries(d).items()}
        for e, tg, sl, hd in itertools.product(ENT, TG, SL, HD):
            sig = E[e]; i = 210; n = len(d)
            while i < n - 1:
                if not sig[i] or not a[i] > 0:
                    i += 1; continue
                e0 = o[i + 1]; st, tp = e0 - sl * a[i], e0 + tg * a[i]; px = None
                for j in range(i + 1, min(i + 1 + hd, n)):
                    if o[j] <= st: px = o[j]; break
                    if l[j] <= st: px = st; break
                    if h[j] >= tp: px = tp; break
                if px is None:
                    j = min(i + hd, n - 1); px = c[j]
                cp = SC.cost_frac(e0, r.lot)
                rows.append((e, tg, sl, hd, t[i], (px - e0 - cp) / (sl * a[i]), (px - e0 - 2 * cp) / (sl * a[i]), px - e0 - cp > 0))
                i = j + 1
    T = pd.DataFrame(rows, columns=["e", "tg", "sl", "hd", "time", "r1", "r2", "win"])
    T["half"] = np.where(pd.to_datetime(T["time"]) < pd.Timestamp("2024-07-01"), "A", "B")
    g = T.groupby(["e", "tg", "sl", "hd", "half"]).agg(n=("r1", "size"), win=("win", "mean"), e1=("r1", "mean"), e2=("r2", "mean")).unstack()
    g.columns = [f"{a}_{b}" for a, b in g.columns]; g = g.dropna()
    g = g[(g.n_A >= 100) & (g.n_B >= 100)]
    hi = g[(g.win_A >= 0.8) & (g.win_B >= 0.8)]
    q = hi[(hi.e2_A > 0) & (hi.e2_B > 0)]
    print(f"combos {len(g)} · win ≥80% both periods: {len(hi)} · of which profitable at 2× costs both periods: {len(q)}")
    cols = ["n_A", "n_B", "win_A", "win_B", "e1_A", "e1_B", "e2_A", "e2_B"]
    print("\nhighest accuracy:"); print(g.assign(w=g[["win_A", "win_B"]].min(axis=1)).sort_values("w", ascending=False)[cols].head(12).round(3).to_string())
    pp = g[(g.e2_A > 0) & (g.e2_B > 0)]
    print(f"\nprofitable at 2× costs in BOTH periods: {len(pp)}"); print(pp.sort_values("win_B", ascending=False)[cols].head(12).round(3).to_string())
    out = ROOT / "research/search/results_stock_highwin"; out.mkdir(parents=True, exist_ok=True); g.round(4).to_csv(out / "grid.csv")
    (out / "summary.json").write_text(json.dumps(dict(combos=len(g), win80_both=len(hi), win80_and_profitable=len(q),
                                                      qualifying=q.round(3).reset_index().to_dict("records")), indent=1, default=str))


if __name__ == "__main__":
    main()
