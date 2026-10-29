"""MCX-OI-001 (29-Oct-2026): commodity volume + OI rules on the official MCX bhavcopy (daily, Jul-2022 → Oct-2026).
Front contract per commodity = the expiry with the most volume that day (follows the roll like traders do). Daily signal at the
close of t, trade the next day (entry next open, exit next close, or hold 3 days), result in units of the 14-day ATR, 2× costs.
Labels: LB long buildup (price up, OI up) · SB short buildup (down, OI up) · SC short covering (up, OI down) · LU long unwinding.
Rules: follow the label (LB/SC -> BUY, SB/LU -> SELL) with OI change ≥ 0 / 2 / 5 % and volume ≥ 1 / 1.5 / 2× the 20-day average;
fade the label (opposite); per commodity and pooled. Splits: train < 2024-07 ≤ valid < 2025-07 ≤ test.
python research/program/mcx_oi.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research import instruments as INS  # noqa: E402

NAMES = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM", "CRUDEOILM", "NATGASMINI", "GOLDM", "SILVERM", "ZINCMINI", "ALUMINI"]
fs = sorted((ROOT / "research/data/mcx_bhav/days").glob("*.csv"))
D = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
D = D[(D.instrument == "FUTCOM") & D.symbol.isin(NAMES) & (D.close > 0)]
D["date"] = pd.to_datetime(D["date"]); D["exp"] = pd.to_datetime(D["expiry"], format="%d%b%Y", errors="coerce")
# continuous front series: the most traded expiry each day; OI change measured within the SAME contract
rows = []
for sym, g in D.groupby("symbol"):
    g = g.sort_values(["date", "exp"])
    prev = g.set_index(["date", "exp"])
    days = sorted(g.date.unique())
    for i, d in enumerate(days[1:], 1):
        x = g[g.date == d]
        if x.volume_lots.sum() <= 0:
            continue
        r = x.loc[x.volume_lots.idxmax()]
        p = g[(g.date == days[i - 1]) & (g.exp == r.exp)]
        if p.empty or p.oi_lots.iat[0] <= 0 or p.close.iat[0] <= 0:
            continue
        rows.append(dict(sym=sym, date=d, exp=r.exp, open=r.open, high=r.high, low=r.low, close=r.close, vol=r.volume_lots, oi=r.oi_lots,
                         ret=r.close / p.close.iat[0] - 1, doi=r.oi_lots / p.oi_lots.iat[0] - 1, roll=bool(p.empty)))
S = pd.DataFrame(rows).sort_values(["sym", "date"]).reset_index(drop=True)
out = []
for sym, g in S.groupby("sym"):
    g = g.reset_index(drop=True)
    tr = pd.concat([g.high - g.low, (g.high - g.close.shift()).abs(), (g.low - g.close.shift()).abs()], axis=1).max(axis=1)
    g["atr"] = tr.rolling(14).mean()
    g["volx"] = g.vol / g.vol.rolling(20).mean().shift(1)
    same = g.exp.shift(-1) == g.exp
    g["n_open"] = g.open.shift(-1).where(same); g["n_close"] = g.close.shift(-1).where(same)
    g["c3"] = g.close.shift(-3).where(same & (g.exp.shift(-3) == g.exp))
    base = sym.replace("M", "") if sym in ("CRUDEOILM", "GOLDM", "SILVERM") else sym
    nm = {"NATGASMINI": "NATURALGAS", "ZINCMINI": "ZINC", "ALUMINI": "ALUMINIUM"}.get(sym, base)
    g["cost"] = [INS.cost_points(nm, p, 1.0) if nm in INS.REGISTRY else p * 0.0004 for p in g.close]
    out.append(g)
S = pd.concat(out, ignore_index=True).dropna(subset=["atr", "n_open", "n_close"])
S["lab"] = np.select([(S.ret > 0) & (S.doi > 0), (S.ret < 0) & (S.doi > 0), (S.ret > 0) & (S.doi < 0), (S.ret < 0) & (S.doi < 0)],
                     ["LB", "SB", "SC", "LU"], "NA")
S["split"] = np.where(S.date < "2024-07-01", "train", np.where(S.date < "2025-07-01", "valid", "test"))
S["up_next"] = (S.n_close > S.close).astype(int)
print(f"MCX daily rows {len(S):,} · {S.sym.nunique()} contracts · {S.date.min():%Y-%m-%d} → {S.date.max():%Y-%m-%d}")
print("\nNext day: share of UP closes after each label (all commodities):")
print(S.groupby("lab").agg(n=("up_next", "size"), up_next=("up_next", "mean")).round(3).T.to_string())
res = []
for mode in ("follow", "fade"):
    for oi_min in (0, 0.02, 0.05):
        for vx in (1.0, 1.5, 2.0):
            m = (S.lab != "NA") & (S.doi.abs() >= oi_min) & (S.volx >= vx)
            g = S[m].copy()
            side = np.where(g.lab.isin(["LB", "SC"]), 1, -1) * (1 if mode == "follow" else -1)
            g["r1d"] = (side * (g.n_close - g.n_open) - 2 * g.cost) / g.atr
            g["r3d"] = (side * (g.c3 - g.n_open) - 2 * g.cost) / g.atr
            for (sym), gg in [("ALL", g)] + list(g.groupby("sym")):
                row = dict(mode=mode, oi=oi_min, vol=vx, sym=sym, n=len(gg))
                for sp in ("train", "valid", "test"):
                    x = gg[gg.split == sp]
                    row[f"1d_{sp}"] = x.r1d.mean(); row[f"3d_{sp}"] = x.r3d.mean()
                row["win1d"] = (gg.r1d > 0).mean() * 100
                res.append(row)
R = pd.DataFrame(res)
R.to_csv(ROOT / "research/program/results/mcx_oi_summary.csv", index=False)
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
print("\nPOOLED (all commodities), ATR units after 2× costs, entry next open:")
print(R[R.sym == "ALL"].round(3).to_string(index=False))
ok = R[(R.sym != "ALL") & (R.n >= 60) & (R["1d_train"] > 0) & (R["1d_valid"] > 0)]
print("\nper commodity, positive next-day in train AND valid (n ≥ 60):")
print(ok.sort_values("1d_test", ascending=False).round(3).to_string(index=False) if len(ok) else "none")
