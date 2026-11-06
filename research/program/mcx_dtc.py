"""MCXD-002 – Gold + Silver intraday day-trend continuation (DTC): parameter-stability and walk-forward checks.
Rule (MCXD-001): at a checkpoint, if the 60m trend (EMA20/50) agrees, price is beyond session VWAP and beyond the day's open
by >= k x daily ATR(14, previous days) -> enter at the next 5-minute open in that direction, stop = m x daily ATR, hold to the
23:00 square-off. Realistic cost (fees + 1.5 ticks/side) and 2 x stress. One trade per commodity per checkpoint.
Grid around the base (13:00+17:00, k 0.3, m 0.5): checkpoints {12:00, 13:00, 14:00, 15:00, 16:00, 17:00, 18:00, 19:00},
k {0.2, 0.3, 0.5}, m {0.35, 0.5, 0.75}; also CRUDEOIL / COPPER for transfer.
python research/program/mcx_dtc.py"""
import sys
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD  # noqa: E402

OUT = ROOT / "research/program/results"


def trades(name, P, checkpoints, k, m):
    d5, f15, f30, f60, dd, sw = P
    t5 = d5.time.values
    eod = d5[d5.m <= 23 * 60].groupby("day").apply(lambda g: g.index[-1])
    rows = []
    g15 = f15.set_index("time")
    for cp in checkpoints:
        bar = f15[f15.m == cp - 15]                                   # 15m bar that closes at the checkpoint
        for _, r in bar.iterrows():
            day = r.day
            if day in sw or day not in dd.index or day not in eod.index or not dd.at[day, "atr"] > 0:
                continue
            D = dd.loc[day]
            dayo = d5.open.values[np.searchsorted(t5, np.datetime64(day + pd.Timedelta(hours=9)))]
            for s in (1, -1):
                if r.tr60 == s and s * (r.close - r.vwap) > 0 and s * (r.close - dayo) >= k * D.atr:
                    i0 = np.searchsorted(t5, np.datetime64(r.time + pd.Timedelta(minutes=15)))
                    if i0 >= len(d5) or d5.day.iat[i0] != day or i0 >= eod[day]:
                        continue
                    e = d5.open.iat[i0]; st = e - s * m * D.atr; R = m * D.atr
                    px, mfe, mae = MD.walk(d5, i0, s, e, st, None, 0.0, int(eod[day]))
                    c = MD.real_cost(name, e)
                    rows.append(dict(name=name, cp=cp, side=s, day=day, net=(s * (px - e) - c) / R, stress=(s * (px - e) - 2 * c) / R))
    return pd.DataFrame(rows)


def per(x):
    p = np.where(x.day < MD.Y0, "hist", np.where(x.day < MD.DEV_END, "dev", "valid"))
    return {f"{q}": round(x.net[p == q].mean(), 3) for q in ("dev", "valid", "hist")} | {f"n_{q}": int((p == q).sum()) for q in ("dev", "valid", "hist")}


def main():
    P = {n: MD.prep(n) for n in ("GOLD", "SILVER", "CRUDEOIL", "COPPER")}
    rows = []
    for cps, k, m in product(((13 * 60, 17 * 60), (12 * 60, 16 * 60), (14 * 60, 18 * 60), (15 * 60, 19 * 60), (13 * 60,), (17 * 60,)),
                             (0.2, 0.3, 0.5), (0.35, 0.5, 0.75)):
        x = pd.concat([trades(n, P[n], cps, k, m) for n in ("GOLD", "SILVER")])
        if x.empty:
            continue
        yr = x.groupby(x.day.dt.year).net.mean()
        rows.append(dict(checkpoints="/".join(f"{c // 60}:00" for c in cps), k=k, m=m, n=len(x), net=round(x.net.mean(), 3),
                         stress=round(x.stress.mean(), 3), years_pos=f"{int((yr > 0).sum())}/{len(yr)}", **per(x)))
    G = pd.DataFrame(rows); G.to_csv(OUT / "mcxdtc_grid.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
    print(G.to_string(index=False))
    print("\nshare of the 54 variants positive in hist:", round((G["hist"] > 0).mean(), 2), "· positive in all three periods:", round(((G["dev"] > 0) & (G["valid"] > 0) & (G["hist"] > 0)).mean(), 2))
    for n in ("CRUDEOIL", "COPPER"):
        x = trades(n, P[n], (13 * 60, 17 * 60), 0.3, 0.5)
        print(f"transfer {n} (base rule): n {len(x)} net {x.net.mean():+.3f}", per(x))
    b = pd.concat([trades(n, P[n], (13 * 60, 17 * 60), 0.3, 0.5) for n in ("GOLD", "SILVER")])
    b.to_csv(OUT / "mcxdtc_base_trades.csv", index=False)


if __name__ == "__main__":
    main()
