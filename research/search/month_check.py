"""INTRA-MONTH-001 – see REGISTRY_MONTH.md. Needs trades_*.csv.gz from intra_win2 (re-run saves them)."""
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.search.intra_win2 import FLAGS, EX, OUT  # noqa

M0, M1, Q0 = pd.Timestamp("2026-10-01"), pd.Timestamp("2026-10-23"), pd.Timestamp("2026-07-01")


def st(r):
    r = np.asarray(r, float)
    return dict(n=len(r), win=round((r > 0).mean() * 100, 1) if len(r) else None, exp=round(r.mean(), 3) if len(r) else None)


def main():
    res = []
    combos = [c for k in range(4) for c in itertools.combinations(FLAGS, k)]
    for u in ("INDEX", "MCX", "STOCKS"):
        T = pd.read_csv(OUT / f"trades_{u}.csv.gz", parse_dates=["time"])
        for fam, F in T.groupby("fam"):
            for c in combos:
                m = np.ones(len(F), bool)
                for fl in c:
                    m &= F[fl].values.astype(bool)
                G = F[m]
                oc = G[(G.time >= M0) & (G.time < M1)]
                if len(oc) < 15:
                    continue
                q = G[(G.time >= Q0) & (G.time < M0)]
                full = G[G.time < M0]
                for ex in EX:
                    o = st(oc[ex])
                    if o["win"] < 80 or o["exp"] <= 0:
                        continue
                    qq, ff = st(q[ex]), st(full[ex])
                    f2 = float(full[ex + "_2x"].mean())
                    keep = bool(qq["n"] >= 30 and qq["win"] >= 70 and qq["exp"] > 0 and ff["n"] >= 100 and f2 > 0)
                    res.append(dict(rule=f"{u}|{fam}|{'+'.join(c) or 'none'}|{ex}", oct=o, julsep=qq, full=ff, full_2x=round(f2, 3), KEEP=keep))
    res.sort(key=lambda x: (-x["KEEP"], -(x["julsep"]["exp"] or -9)))
    (OUT / "month_check.json").write_text(json.dumps(res, indent=1))
    print("Oct winners:", len(res), "KEEP:", sum(r["KEEP"] for r in res))
    for u in ("INDEX", "MCX", "STOCKS"):
        print(u, "Oct winners:", sum(r["rule"].startswith(u) for r in res), "KEEP:", sum(r["KEEP"] for r in res if r["rule"].startswith(u)))
    for r in res[:15]:
        print(r)


if __name__ == "__main__":
    main()
