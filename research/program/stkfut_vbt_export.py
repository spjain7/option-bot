"""Exports 1-hour bars and ORB60 trades of 5 stocks for the independent vectorbt cross-check (stkfut_vbt_xcheck.py).
Usage: python research/program/stkfut_vbt_export.py OUTDIR ; then (in a venv with vectorbt==0.28.1, plotly<6)
       python research/program/stkfut_vbt_xcheck.py OUTDIR"""
import sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import reversal as RV, stkfut_cmp as SC  # noqa: E402
from research.search import stock_search as SR  # noqa: E402
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
man = pd.read_csv(SR.DATA / "manifest_stocks.csv").set_index("name")
T = pd.read_csv(ROOT / "research/program/results/stkfut_cmp_trades.csv.gz", parse_dates=["time", "entry_time", "exit_time"])
for nm in ["RELIANCE", "SBIN", "TCS", "INFY", "TATASTEEL"]:
    lot = int(man.loc[nm, "lot"])
    f, _ = SC.prep(RV.stock_1h(nm, lot)[1], lot)
    f[["time", "open", "high", "low", "close", "day"]].to_csv(out / f"{nm}_bars.csv", index=False)
    T[(T.setup == "ORB60") & (T.name == nm)][["entry_time", "exit_time", "side", "entry", "stop", "target", "exit", "why", "gross_R", "R"]] \
        .to_csv(out / f"{nm}_trades.csv", index=False)
