"""TFLOG-003 (30-Oct-2026): 3-month trade logs – 2-hour volume-3× rules vs the 4-hour rules and the live MCX 3h BUY.
Same execution and columns as tf_log2.py."""
import json, sys
from multiprocessing import Pool
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import tf_log2 as L  # noqa: E402
from research.program import emax as EX  # noqa: E402

L.RULES = {"MCX 2h BUY (vol 3×)": ("MCX", 2, 1, 10, 3.0, 2.5, 2.5, 2.5), "STOCK 2h SELL (vol 3×)": ("STOCKS", 2, -1, 10, 3.0, 2.5, 2.5, 4.0),
           "MCX 4h BUY": ("MCX", 4, 1, 10, 2.0, 1.5, 3.0, 2.5), "STOCK 4h SELL": ("STOCKS", 4, -1, 5, 2.0, 2.0, 2.0, 4.0),
           "MCX 3h BUY (live)": ("MCX", 3, 1, 10, 1.5, 2.0, 2.0, 2.5)}


def main():
    J = [j for j in EX.jobs() if (j[0] == "mi" and j[2] == "MCX") or j[0] == "stk"]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(L.one, J, chunksize=2) for r in x]
    rows.sort(key=lambda r: r["entry_time"])
    (ROOT / "research/program/results/tf_log3.json").write_text(json.dumps(rows))
    T = pd.DataFrame(rows); sl = T[T.why.str.startswith("stop")]
    S = T.groupby("rule").agg(calls=("pnl", "size"), wins=("pnl", lambda s: (s > 0).mean() * 100), pnl=("pnl", "sum"),
                              pnl_be=("pnl_be", "sum"), sl_hits=("why", lambda s: s.str.startswith("stop").sum()))
    S = S.join(sl.groupby("rule").agg(sl_best_med_pct=("best_pct", "median"), sl_reached_1R=("mfe_R", lambda s: (s >= 1).mean() * 100)))
    print(S.round(1).to_string())


if __name__ == "__main__":
    main()
