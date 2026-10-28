"""STKFUT-CMP-001 analysis: variants (setup × side × overlay), chronological periods, multiple-testing control.
Overlays (each from a source repository; all known at the signal close):
  RG regime (nse-trading-lab tape_monitor: BUY in TRENDING/MIXED, SELL in HOSTILE NIFTY tape, previous close)
  V  relative volume ≥ 1.5× same-hour average (kite-algo-bot / intraday-playbook RVOL)
  O  previous-day OI buildup in the trade direction (LB for BUY, SB for SELL) – this bot's own OI data
  N  NIFTY up (BUY) / down (SELL) on the day so far (kite-algo-bot index_confirmation)
  C  signal candle closes in the top / bottom 30 % of its range (nse-algo wick filter / candle confirmation)
  W  close on the trade side of session VWAP (intraday-playbook confluence_gate vwap_aligned)
  NR narrow opening range ≤ 0.5 × daily ATR (intraday-playbook orb nr filter)
PASS: n ≥ 100 / 50 / 50 (train / valid / test), net expectancy (1× costs) > 0 in every period, test PF ≥ 1.1,
and the test-period one-sided p-value (day-block bootstrap) significant after Benjamini–Hochberg at q = 0.10 across
ALL variants tested.
"""
import itertools
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/program/results"
OVL = ["RG", "V", "O", "N", "C", "W", "NR"]


def stats(x):
    if len(x) == 0:
        return dict(n=0)
    r = x["net_R"].values
    gw, gl = r[r > 0].sum(), -r[r <= 0].sum()
    eq = np.cumsum(x.sort_values("time")["net_R"].values)
    return dict(n=len(x), win=round((r > 0).mean() * 100, 1), exp=round(r.mean(), 3), exp2=round(x["net2_R"].mean(), 3),
                gross=round(x["gross_R"].mean(), 3), cost=round(x["cost_R"].mean(), 3), pf=round(gw / gl, 2) if gl > 0 else np.nan,
                dd=round(float((np.maximum.accumulate(eq) - eq).max()), 1), rs=round(x["rs"].mean()))


def boot_p(x, nb=1000, seed=7):
    """One-sided p-value that the mean net R ≤ 0, resampling trading DAYS (trades on the same day are correlated)."""
    if len(x) < 20:
        return 1.0
    g = x.groupby(x["time"].dt.normalize())["net_R"].agg(["sum", "size"])
    s, k = g["sum"].values, g["size"].values
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(nb, len(s)))
    m = s[idx].sum(1) / k[idx].sum(1)
    return float((m <= 0).mean())


def main():
    T = pd.read_csv(OUT / "stkfut_cmp_trades.csv.gz", parse_dates=["time"])
    for c in OVL:
        T[c] = T[c].astype(bool)
    rows = []
    for (st, side), g in T.groupby(["setup", "side"]):
        combos = [()] + ([(o,) for o in OVL] + [("RG", "V"), ("RG", "O"), ("V", "O"), ("N", "V"), ("RG", "N"), ("C", "V"), ("W", "V")]
                         if g["tf"].iat[0] == "1h" else [("RG",)])
        for cb in combos:
            m = np.ones(len(g), bool)
            for o in cb:
                m &= g[o].values
            x = g[m]
            if len(x) < 30:
                continue
            row = dict(setup=st, side="BUY" if side > 0 else "SELL", overlay="+".join(cb) or "none", **stats(x))
            for sp in ("train", "valid", "test"):
                y = x[x["split"] == sp]
                s_ = stats(y)
                row.update({f"{sp}_n": s_.get("n", 0), f"{sp}_exp": s_.get("exp"), f"{sp}_win": s_.get("win"), f"{sp}_pf": s_.get("pf")})
            row["test_p"] = boot_p(x[x["split"] == "test"])
            rows.append(row)
    R = pd.DataFrame(rows)
    # Benjamini–Hochberg over all variants
    p = R["test_p"].values; order = np.argsort(p); m = len(p)
    bh = np.zeros(m, bool)
    thr = 0.10 * (np.arange(1, m + 1) / m)
    ok = p[order] <= thr
    if ok.any():
        bh[order[: np.max(np.flatnonzero(ok)) + 1]] = True
    R["bh_sig"] = bh
    R["consistent"] = (R["train_n"] >= 100) & (R["valid_n"] >= 50) & (R["test_n"] >= 50) & (R["train_exp"] > 0) & \
                      (R["valid_exp"] > 0) & (R["test_exp"] > 0) & (R["test_pf"] >= 1.1)
    R["PASS"] = R["consistent"] & R["bh_sig"]
    R.to_csv(OUT / "stkfut_cmp_variants.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 400); pd.set_option("display.max_columns", 40)
    print("variants", len(R), "consistent", int(R["consistent"].sum()), "BH-significant", int(R["bh_sig"].sum()), "PASS", int(R["PASS"].sum()))
    cols = ["setup", "side", "overlay", "n", "win", "exp", "exp2", "gross", "cost", "pf", "dd", "rs", "train_exp", "valid_exp", "test_exp",
            "test_n", "test_win", "test_pf", "test_p", "consistent", "PASS"]
    print(R[R["overlay"] == "none"][cols].to_string(index=False))
    print("\nTop 25 by test expectancy (n_test ≥ 50):")
    print(R[R["test_n"] >= 50].sort_values("test_exp", ascending=False)[cols].head(25).to_string(index=False))


if __name__ == "__main__":
    main()
