"""MCXD-005 – matched controls for the Gold/Silver day-trend continuation (shadow strategy), same standard as MCXE-002.
ACTUAL = base rule trades (13:00 / 17:00, k 0.3, stop 0.5 daily ATR, hold to 23:00). PERM = each trade moved to a random OTHER
trading day of the same quarter at the SAME checkpoint, same side, same stop rule (0.5 x that day's ATR), same exit.
BLOCK = all trades of a quarter shifted by one common random number of days. 500 permutations, stable seed.
Periods: HIST < 2025-11-06 · DEV · VALID (2026-07-01 … 11-03).   python research/program/mcx_dtc_controls.py"""
import sys
import zlib
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD, mcx_dtc as DT, mcx_engine as E  # noqa: E402

N = 500


def main():
    out = []
    for name in ("GOLD", "SILVER"):
        P = MD.prep(name); d5, f15, f30, f60, dd, sw = P
        T = DT.trades(name, P, (13 * 60, 17 * 60), 0.3, 0.5)
        t5 = d5.time.values
        eod = d5[d5.m <= 23 * 60].groupby("day").apply(lambda g: g.index[-1])
        days = sorted(set(eod.index) - set(sw))
        days = [d for d in days if d in dd.index and dd.at[d, "atr"] > 0]
        T["qq"] = pd.PeriodIndex(T.day, freq="Q").astype(str)
        dq = pd.Series(days, index=pd.PeriodIndex(days, freq="Q").astype(str))
        rng = np.random.default_rng((E.SEED + zlib.crc32(name.encode())) % 2 ** 32)

        def pnl(day, cp, s):
            i0 = np.searchsorted(t5, np.datetime64(day + pd.Timedelta(minutes=cp)))
            if i0 >= len(d5) or d5.day.iat[i0] != day or i0 >= eod[day]:
                return np.nan
            e = d5.open.iat[i0]; R = 0.5 * dd.at[day, "atr"]
            px, _, _ = MD.walk(d5, i0, s, e, e - s * R, None, 0.0, int(eod[day]))
            return (s * (px - e) - MD.real_cost(name, e)) / R
        for r in T.itertuples():
            out.append(dict(name=name, kind="ACTUAL", perm=-1, day=r.day, net=r.net))
        for p in range(N):
            for q, g in T.groupby("qq"):
                qd = list(dq.get(q, pd.Series(dtype=object)).values) if q in dq.index else []
                if len(qd) < 3:
                    continue
                off = rng.integers(1, len(qd))
                for r in g.itertuples():
                    nd = qd[rng.integers(len(qd))]
                    while nd == r.day:
                        nd = qd[rng.integers(len(qd))]
                    out.append(dict(name=name, kind="PERM", perm=p, day=r.day, net=pnl(nd, r.cp, r.side)))
                    k = qd.index(r.day) if r.day in qd else 0
                    out.append(dict(name=name, kind="BLOCK", perm=p, day=r.day, net=pnl(qd[(k + off) % len(qd)], r.cp, r.side)))
        print(name, "done", flush=True)
    X = pd.DataFrame(out).dropna()
    X["per"] = np.where(X.day < MD.Y0, "hist", np.where(X.day < MD.DEV_END, "dev", "valid"))
    rows = []
    for (nm, per), g in list(X.groupby(["name", "per"])) + [(("BOTH", p), X[X.per == p]) for p in ("hist", "dev", "valid")] + [(("BOTH", "all"), X)]:
        a = g[g.kind == "ACTUAL"].net.values
        rng = np.random.default_rng(1)
        boot = [rng.choice(a, len(a)).mean() for _ in range(2000)]
        row = dict(name=nm, period=per, n=len(a), actual=a.mean(), ci_lo=np.percentile(boot, 2.5), ci_hi=np.percentile(boot, 97.5))
        for k in ("PERM", "BLOCK"):
            m = g[g.kind == k].groupby("perm").net.mean()
            row.update({f"{k.lower()}_mean": m.mean(), f"{k.lower()}_p95": np.percentile(m, 95), f"{k.lower()}_rank": (m < a.mean()).mean()})
        rows.append(row)
    R = pd.DataFrame(rows).round(3)
    R.to_csv(ROOT / "research/program/results/mcxdtc_controls.csv", index=False)
    pd.set_option("display.width", 220); print(R.to_string(index=False))


if __name__ == "__main__":
    main()
