"""PORTFOLIO-001 (6-Nov-2026, owner master instruction §2/§7: expectancy, profit factor, drawdown, losing streak, overlap).
Trade-level re-simulation of the LIVE rule set that has research code (rulebook rules + breakout family), 2022-26, 2x costs,
next-open entry, stop first. Portfolio rule = the live conflict rule: one open call per instrument and direction – a signal
while a call on the same instrument/direction is open is dropped (whatever rule produced it).
Metrics in R (1R = the risk of each call): trades, win %, expectancy, profit factor, max drawdown, longest losing streak,
by year / market / timeframe / rule, and a simple baseline (same instruments, random-direction-free 'buy every 20th candle').
python research/program/portfolio.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402

OUT = ROOT / "research/program/results"
# (id, mkt, tf, fam, par, filt, side, k, r) – live rules with research code
LIVE = [
    ("RB_MCX_4h_EMA1348_BUY", "MCX", "4h", "EMAX", "13/48", "DT", 1, 2.0, 3.0),
    ("RB_MCX_4h_MACD0_BUY", "MCX", "4h", "MACD", "zero", "DT", 1, 1.5, 2.0),
    ("RB_MCX_2h_MOMO_BUY", "MCX", "2h", "MOMO", "1.5ATR", "DT", 1, 2.0, 3.0),
    ("RB_MCX_2h_EMA921_BUY", "MCX", "2h", "EMAX", "9/21", "DT", 1, 3.0, 6.0),
    ("RB_MCX_1d_RETEST_BUY", "MCX", "1d", "RETEST", "20/5", "DT", 1, 2.0, 3.0),
    ("RB_MCX_1h_MACD_BUY", "MCX", "1h", "MACD", "signal", "DT", 1, 3.0, 6.0),
    ("RB_STK_3h_MACD0_SELL", "STOCKS", "3h", "MACD", "zero", "DT", -1, 1.5, 2.0),
    ("RB_STK_3h_EMA921_SELL", "STOCKS", "3h", "EMAX", "9/21", "DT", -1, 2.0, 3.0),
    ("RB_STK_1d_RSI80_BUY", "STOCKS", "1d", "RSICONT", "80/20", "DT", 1, 2.0, 3.0),
    ("BO_MCX_3h_BUY", "MCX", "3h", "BO", "N10 vol1.5", "EMA200", 1, 2.0, 2.0),
    ("FH_MCX_4h_BUY", "MCX", "4h", "BO", "N10 vol1.5", "DT", 1, 2.0, 3.0),
    ("BO_MCX_1d_BUY", "MCX", "1d", "BO", "N20 vol0", "ADX25", 1, 1.5, 2.0),
    ("FH_STK_3h_SELL", "STOCKS", "3h", "BO", "N5 vol2", "DT", -1, 1.5, 2.0),
]


def one(job):
    rows = []
    for mk, tf, f0, cost, fd in SV.frames_for(job):
        rules = [r for r in LIVE if r[1] == mk and r[2] == tf]
        if not rules or len(f0) < 300:
            continue
        f = H.features(f0)
        f["switch"] = f0["switch"].values if "switch" in f0 else np.zeros(len(f0), bool)
        dtr = SA.daily_trend(fd) if fd is not None else pd.Series(dtype=float)
        sets = {(a, b, c): (x, y) for a, b, c, x, y in SV.signal_sets(f, dtr, tf)}
        sets.update({(a, b, c): (x, y) for a, b, c, x, y in SA.signal_sets(f, dtr)})
        t = pd.to_datetime(f["time"]).values
        for rid, _, _, fam, par, flt, side, k, r in rules:
            b, s = sets[(fam, par, flt)]
            sig = np.where(np.nan_to_num(np.asarray(b if side > 0 else s, float)) > 0, side, 0)
            for x in H.simulate(f, sig, side, k, r, SV.MAXH[tf], 0, np.asarray(cost, float), start=210):
                if x["status"] == "trade":
                    j = min(x["i"] + x["bars"], len(t) - 1)
                    rows.append((rid, mk, tf, job[1], side, t[x["i"]], t[j], x["r2"]))
    return rows


def stats(r):
    r = np.asarray(r, float)
    if not len(r):
        return dict(n=0)
    eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    ls = cur = 0
    for v in r:
        cur = cur + 1 if v <= 0 else 0; ls = max(ls, cur)
    gw, gl = r[r > 0].sum(), -r[r <= 0].sum()
    return dict(n=len(r), win=round((r > 0).mean() * 100, 1), expR=round(r.mean(), 3), PF=round(gw / gl, 2) if gl > 0 else np.inf,
                totalR=round(r.sum(), 1), maxDD_R=round(dd, 1), lose_streak=ls, avg_win=round(r[r > 0].mean(), 2) if (r > 0).any() else 0,
                avg_loss=round(r[r <= 0].mean(), 2) if (r <= 0).any() else 0)


def main():
    J = [j for j in EX.jobs() if (j[0] == "mi" and j[2] == "MCX") or j[0] == "stk"]
    with Pool(2) as p:
        rows = [r for x in p.imap_unordered(one, J, chunksize=2) for r in x]
    T = pd.DataFrame(rows, columns=["rule", "mkt", "tf", "name", "side", "t_in", "t_out", "r"]).sort_values("t_in").reset_index(drop=True)
    # portfolio conflict rule: one open call per instrument + direction
    keep, open_until = [], {}
    for i, x in T.iterrows():
        k = (x["name"], x["side"])
        if k in open_until and x["t_in"] <= open_until[k]:
            continue
        open_until[k] = x["t_out"]; keep.append(i)
    P = T.loc[keep].reset_index(drop=True)
    T.to_csv(OUT / "portfolio_trades_all.csv.gz", index=False); P.to_csv(OUT / "portfolio_trades.csv.gz", index=False)
    pd.set_option("display.width", 220)
    print(f"all rule trades {len(T):,} · after the one-call-per-instrument/direction rule {len(P):,} "
          f"({len(P) / len(T) * 100:.0f} %)")
    days = (P.t_in.max() - P.t_in.min()).days / 365 * 250
    print(f"calls per trading day ≈ {len(P) / days:.1f} (MCX {len(P[P.mkt == 'MCX']) / days:.1f}, stocks {len(P[P.mkt == 'STOCKS']) / days:.1f})")
    print("\nPORTFOLIO:", stats(P.r))
    rows = []
    for key, g in (("market", "mkt"), ("timeframe", "tf"), ("rule", "rule"), ("year", P.t_in.dt.year)):
        for v, x in P.groupby(g):
            rows.append(dict(by=key, value=v, **stats(x.r)))
    R = pd.DataFrame(rows); R.to_csv(OUT / "portfolio_summary.csv", index=False)
    print(R.to_string(index=False))
    print("\nSTANDALONE per rule (before overlap removal):")
    print(pd.DataFrame([dict(rule=k, **stats(g.r)) for k, g in T.groupby("rule")]).to_string(index=False))


if __name__ == "__main__":
    main()
