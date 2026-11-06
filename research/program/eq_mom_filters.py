"""EQ-MOM-003 – market-regime filter variants for the monthly relative-strength portfolio (pre-registered, 5 variants;
choose on 2006-15 by Sharpe, report 2016-26). Rules otherwise unchanged (L=252, vol-adj, top 10).
  F0 none · F1 proxy > MA200 (current) · F2 proxy > MA100 · F3 proxy > MA200 OR (proxy > MA50 and 1-month return > 0)
  (re-entry after a rebound) · F4 breadth: >= 50 % of the liquid universe above its own 200-day average
python research/program/eq_mom_filters.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import eq_momentum as MO, eq_mom_robust as RB  # noqa: E402

OUT = ROOT / "research/program/results"


def main():
    D = MO.Data(*MO.panels())
    mk = pd.Series(D.mkt, index=D.days)
    ma50, ma100, ma200 = (mk.rolling(k).mean().values for k in (50, 100, 200))
    r21 = (mk / mk.shift(21) - 1).values
    C = pd.DataFrame(D.c)
    above = (C > C.rolling(200, min_periods=150).mean()).values
    liquid = D.t >= 25e7
    breadth = np.where(liquid.sum(1) > 0, (above & liquid).sum(1) / np.maximum(liquid.sum(1), 1), np.nan)
    rules = {"F0 none": np.ones(len(mk), bool), "F1 MA200 (current)": D.mkt > ma200, "F2 MA100": D.mkt > ma100,
             "F3 MA200 or rebound": (D.mkt > ma200) | ((D.mkt > ma50) & (r21 > 0)), "F4 breadth >= 50%": breadth >= 0.5}
    rows = []
    orig = (D.mkt.copy(), D.ma.copy())
    for name, on in rules.items():
        D.mkt = np.where(on, 2.0, 0.0); D.ma = np.ones(len(mk))            # backtest checks mkt > ma
        R, _ = RB.run_variant(D)
        D.mkt, D.ma = orig
        for lab, a, b in (("2006-15", "2006", "2016"), ("2016-26 OOS", "2016", "2030")):
            x = R[(R.start >= a) & (R.start < b)]
            rows.append(dict(filter=name, period=lab, **RB.stats(x), invested=round(100 * x.invested.mean())))
    S = pd.DataFrame(rows); S.to_csv(OUT / "eqmom_filters.csv", index=False)
    pd.set_option("display.width", 200); print(S.to_string(index=False))
    tr = S[S.period == "2006-15"].sort_values("sharpe", ascending=False).iloc[0]
    print(f"\nchosen on 2006-15 by Sharpe: {tr['filter']} -> OOS:", S[(S["filter"] == tr["filter"]) & (S.period != "2006-15")].to_dict("records"))


if __name__ == "__main__":
    main()
