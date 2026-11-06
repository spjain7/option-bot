"""MCXD-003 – per-commodity trial and error (owner: "try one by one, script wise"). For EACH commodity separately:
  DTC  day-trend continuation: checkpoints {12,13,14,15,16,17,18,19,20:00} x k {0.2, 0.3, 0.5} x stop m {0.35, 0.5, 0.75}
  TPB  trend pull-back (from MCXD-001 signals) x exits {target 2R, 2.5 ATR trail, close}
Selection per commodity on DEV only (2025-11-06 … 2026-06-30, >= 20 trades); the chosen variant is then read on VALID
(2026-07 … 11-03) and HIST (2023 … 2025-11-05), never used to choose. Breadth = share of ALL variants of that commodity that
are positive in HIST (luck gives ~ the same share positive and negative; a real edge shows most variants positive).
Realistic MCX costs; 2 x stress reported. python research/program/mcx_percomm.py"""
import sys
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD, mcx_dtc as DT  # noqa: E402

OUT = ROOT / "research/program/results"


def per(x, col="net"):
    p = np.where(x.day < MD.Y0, "hist", np.where(x.day < MD.DEV_END, "dev", "valid"))
    return {q: (x[col][p == q].mean() if (p == q).any() else np.nan) for q in ("dev", "valid", "hist")} | \
           {f"n_{q}": int((p == q).sum()) for q in ("dev", "valid", "hist")}


def main():
    TP = pd.read_csv(OUT / "mcxd_trades.csv.gz", parse_dates=["day"])
    TP = TP[TP.fam == "TPB"]
    rows = []
    for name in MD.NAMES:
        P = MD.prep(name)
        for cp, k, m in product(range(12 * 60, 21 * 60, 60), (0.2, 0.3, 0.5), (0.35, 0.5, 0.75)):
            x = DT.trades(name, P, (cp,), k, m)
            if len(x) < 30:
                continue
            for sd in (1, -1):
                y = x[x.side == sd]
                if len(y) < 20:
                    continue
                r = per(y); s = per(y, "stress")
                rows.append(dict(name=name, fam="DTC", variant=f"{cp // 60}:00 k{k} m{m}", side="BUY" if sd > 0 else "SELL",
                                 **r, stress_dev=s["dev"], stress_valid=s["valid"], stress_hist=s["hist"]))
        for (sd, ex), y in TP[TP.name == name].groupby(["side", "exit"]):
            y = y.rename(columns={"net_R": "net", "stress_R": "stress"})
            r = per(y); s = per(y, "stress")
            rows.append(dict(name=name, fam="TPB", variant=f"exit {ex}", side=sd, **r, stress_dev=s["dev"], stress_valid=s["valid"], stress_hist=s["hist"]))
        print(name, "done", flush=True)
    A = pd.DataFrame(rows); A.to_csv(OUT / "mcxpc_all.csv", index=False)
    pd.set_option("display.width", 250)
    out = []
    for name, g in A.groupby("name"):
        breadth = (g["hist"] > 0).mean()
        cand = g[(g.n_dev >= 20)].sort_values("dev", ascending=False)
        best = cand.iloc[0] if len(cand) else None
        ok = best is not None and best.dev > 0 and best.valid > 0 and best["hist"] > 0 and best.stress_valid > 0 and best.stress_hist > 0
        out.append(dict(commodity=name, variants=len(g), hist_breadth=round(100 * breadth), chosen=f"{best.fam} {best.side} {best.variant}" if best is not None else "-",
                        dev=round(best.dev, 3), n_dev=best.n_dev, valid=round(best.valid, 3), n_valid=best.n_valid, hist=round(best["hist"], 3),
                        n_hist=best.n_hist, verdict="PASS" if ok else "fail"))
    O = pd.DataFrame(out); O.to_csv(OUT / "mcxpc_summary.csv", index=False)
    print(O.to_string(index=False))
    # second view: per commodity and side, DTC family breadth (share of the 81 variants positive in VALID and HIST)
    d = A[A.fam == "DTC"]
    b = d.groupby(["name", "side"]).apply(lambda g: pd.Series(dict(variants=len(g), pos_valid=round(100 * (g.valid > 0).mean()),
                                                                     pos_hist=round(100 * (g["hist"] > 0).mean()), med_hist=round(g["hist"].median(), 3))))
    print("\nDTC breadth per commodity / side (% of variants positive):\n", b.to_string())


if __name__ == "__main__":
    main()
