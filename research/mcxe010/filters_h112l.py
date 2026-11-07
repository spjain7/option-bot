"""MCXE-010 exploratory filter screen for H1.12L (DEV + VALID trades only – OOS and forward trades are excluded; VALID is
not fresh, so a filter that helps here is only a hypothesis for forward tracking). Trade list = the tracker ledger
(research fills). Subsets approximate a filtered strategy (a removed trade could have freed the slot for another).
Filters (all known at the signal close): daily trend (previous day EMA20 vs EMA50 of daily closes), equal-weight
indicator score (MCXE-009 components) >= 0 / >= 0.4, session (Indian hours 09-17 vs US hours 17-24).
python research/mcxe010/filters_h112l.py -> research/mcxe010/filters_h112l.csv"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe007.shadow import h112l_tracker as TR  # noqa: E402
from research.mcxe009 import weighted as WT  # noqa: E402
from research.mcxe007 import engine7 as E7  # noqa: E402


def main():
    L = pd.read_csv(ROOT / "research/mcxe007/shadow/ledger_h112l.csv", parse_dates=["signal_time"])
    T = L[(L.status == "trade") & (L.side == "BUY") & (L.period.isin(["DEV", "VALID"]))].copy()
    feats = []
    for name, g in T.groupby("commodity"):
        f1, _ = TR.frame(name)
        S = WT.components(f1); sc = WT.score(S, WT.FAMILIES["equal"])
        d = f1.groupby(f1.time.dt.normalize()).close.last()
        e20, e50 = d.ewm(span=20, adjust=False).mean(), d.ewm(span=50, adjust=False).mean()
        tr = pd.Series(np.where(e20 > e50, 1, -1), index=d.index).shift(1)
        pos = pd.Series(np.arange(len(f1)), index=f1.time)
        for r in g.itertuples():
            i = pos[r.signal_time]
            feats.append(dict(idx=r.Index, score=sc[i], dtrend=tr.get(r.signal_time.normalize(), np.nan)))
    F = pd.DataFrame(feats).set_index("idx"); T = T.join(F)
    T["hour"] = T.signal_time.dt.hour
    T = T.rename(columns={"signal_time": "date"})
    subsets = {"all (baseline H1.12L)": T, "daily trend up": T[T.dtrend == 1], "daily trend down": T[T.dtrend == -1],
               "equal score >= 0": T[T.score >= 0], "equal score >= 0.4": T[T.score >= 0.4],
               "Indian hours (signal 09-16h)": T[T.hour < 17], "US hours (signal 17-23h)": T[T.hour >= 17]}
    rows = []
    for k, x in subsets.items():
        for P in ("DEV", "VALID"):
            y = x[x.period == P].assign(r2=lambda z: z.net_R_2x)
            m = E7.metrics(y, "r2", B=1000)
            rows.append(dict(filter=k, period=P, n=m.get("n", 0), dates=m.get("dates", 0), win=m.get("win"), exp2=m.get("exp"), pf=m.get("pf"),
                             ci_lo=m.get("ci_lo"), ci_hi=m.get("ci_hi")))
    R = pd.DataFrame(rows)
    R.to_csv(ROOT / "research/mcxe010/filters_h112l.csv", index=False)
    print(R.pivot_table(index="filter", columns="period", values=["n", "exp2", "win"]).round(3).to_string())


if __name__ == "__main__":
    main()
