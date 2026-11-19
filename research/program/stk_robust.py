"""STK-ROBUST-001 (19-Nov-2026): robustness tests from marketcalls/vectorbt-backtesting-skills (robustness-testing.md) applied
to the LIVE stock SELL rules (stk_call_audit.LIVE, live gate: one call per stock, max 5 a day, 5-session cooldown):
  1 MONTE CARLO   shuffle the order of the gated portfolio's trades 2,000x -> 5th percentile total R, worst-5 % drawdown
  2 NOISE         add +-0.1 % random noise to every 1-hour price (5 seeds) and re-run signals + exits
  3 DELAY         enter 1 and 2 candles later than the signal
  4 NEIGHBOURS    stop 1.0 / 1.5 / 2.0 / 2.5 ATR x target 1.5 / 2 / 3R around each rule's live setting
  5 CROSS-SYMBOL  share of stocks with a positive total R
A rule is ROBUST when noise runs stay positive in >= 80 %, delayed entries stay positive, >= 70 % of neighbours positive.
python research/program/stk_robust.py -> results/stk_robust_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.stk_call_audit import LIVE, PRI, portfolio, stats  # noqa: E402

OUT = ROOT / "research/program/results"
KS, RS = (1.0, 1.5, 2.0, 2.5), (1.5, 2.0, 3.0)


def variants():
    v = [("base", 0, 0, None)]
    v += [(f"noise{s}", s, 0, None) for s in (1, 2, 3, 4, 5)]
    v += [("delay1", 0, 1, None), ("delay2", 0, 2, None)]
    v += [(f"k{k}_r{r}", 0, 0, (k, r)) for k in KS for r in RS]
    return v


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in fr}
    if "STOCKS 1h" not in seg or "STOCKS 1d" not in seg:
        return None
    f1o, c1 = seg["STOCKS 1h"]; fd = seg["STOCKS 1d"][0]
    c1 = np.interp(np.arange(len(f1o)), np.linspace(0, len(f1o) - 1, len(c1)), c1) if len(c1) != len(f1o) else c1
    dtr = SA.daily_trend(fd)
    def prep(f1):
        out = []
        f3 = EX.three(f1[["time", "open", "high", "low", "close", "volume", "switch"]])
        fr_ = {"3h": (f3, np.interp(np.arange(len(f3)), np.linspace(0, len(f3) - 1, len(c1)), c1))}
        for hrs, tf in ((2, "2h"), (4, "4h")):
            C, first = anchored(f1, hrs)
            fr_[tf] = (C, c1[first[:len(C)]])
        for tf, (C, cost) in fr_.items():
            if len(C) < 300:
                continue
            f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
            sets = {(a, b, cc): (x, y) for a, b, cc, x, y in SV.signal_sets(f, dtr, tf)}
            sets.update({(a, b, cc): (x, y) for a, b, cc, x, y in SA.signal_sets(f, dtr)})
            out.append((tf, f, np.asarray(cost, float), sets, pd.to_datetime(f["time"]).values))
        return out

    def run(vname, pre, delay=0, kr=None):
        rows = []
        for tf, f, cost, sets, t in pre:
            for rid, _, fam, par, flt, k, r, _ in [x for x in LIVE if x[1] == tf]:
                if (fam, par, flt) not in sets:
                    continue
                s = np.nan_to_num(np.asarray(sets[(fam, par, flt)][1], float)) > 0
                if delay:
                    s = np.r_[np.zeros(delay, bool), s[:-delay]]
                kk, rr = kr if kr else (k, r)
                for x in H.simulate(f, np.where(s, -1, 0), -1, kk, rr, SV.MAXH[tf], 0, cost, start=210):
                    if x["status"] == "trade":
                        j = min(x["i"] + x["bars"], len(t) - 1)
                        rows.append((vname, rid, tf, job[1], t[x["i"]], t[j], x["r2"], x["exit"]))
        return rows

    rows = []
    pre = prep(f1o)
    for vname, seed, delay, kr in variants():
        if seed:
            f1 = f1o.copy(); rng = np.random.default_rng(seed * 7919 + sum(map(ord, job[1])))
            for col in ("open", "high", "low", "close"):
                f1[col] = f1[col] * (1 + rng.normal(0, 0.001, len(f1)))
            f1["high"] = f1[["open", "high", "low", "close"]].max(axis=1); f1["low"] = f1[["open", "high", "low", "close"]].min(axis=1)
            rows += run(vname, prep(f1))
        else:
            rows += run(vname, pre, delay, kr)
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        T = pd.DataFrame([r for x in p.imap_unordered(one, J, chunksize=2) if x for r in x],
                         columns=["var", "rule", "tf", "name", "t_in", "t_out", "r", "exit"])
    T["day"] = pd.to_datetime(T.t_in).dt.normalize(); T["pri"] = T.rule.map(PRI)
    tv = T.t_in.values.astype("datetime64[ns]"); T["split"] = np.where(tv < SV.P1, "p1", np.where(tv < SV.P2, "p2", "p3"))
    out = []
    for (v, rid), g in T.groupby(["var", "rule"]):
        s = stats(g.sort_values("t_in").r)
        out.append(dict(var=v, rule=rid, **s, **{f"{sp}_R": round(g[g.split == sp].r.mean(), 3) for sp in ("p1", "p2", "p3")}))
    L = pd.DataFrame(out); L.to_csv(OUT / "stk_robust_summary.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 300)
    # verdict per rule
    V = []
    for rid in sorted(L.rule.unique()):
        g = L[L.rule == rid].set_index("var")
        noise = g[g.index.str.startswith("noise")]; nb = g[g.index.str.startswith("k")]
        V.append(dict(rule=rid, base_R=g.loc["base", "expR"], base_win=g.loc["base", "win"],
                      noise_pos_share=round((noise.expR > 0).mean(), 2), noise_avgR=round(noise.expR.mean(), 3),
                      delay1_R=g.loc["delay1", "expR"] if "delay1" in g.index else None, delay2_R=g.loc["delay2", "expR"] if "delay2" in g.index else None,
                      neighbours_pos_share=round((nb.expR > 0).mean(), 2), neighbours_min_R=round(nb.expR.min(), 3)))
    V = pd.DataFrame(V)
    V["robust"] = (V.noise_pos_share >= .8) & (V.delay1_R > 0) & (V.neighbours_pos_share >= .7)
    # names positive (base)
    B = T[T["var"] == "base"]
    V["stocks_positive_share"] = V.rule.map(B.groupby(["rule", "name"]).r.sum().gt(0).groupby("rule").mean().round(2))
    print(V.to_string(index=False))
    # Monte Carlo on the gated live portfolio
    P = portfolio(B, per_tf=False, cap=5, cooldown=5).sort_values("t_in")
    r = P.r.values; rng = np.random.default_rng(42); tot, dd = [], []
    for _ in range(2000):
        x = rng.permutation(r); eq = np.cumsum(x); tot.append(eq[-1]); dd.append((np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max())
    mc = dict(trades=len(r), totalR=round(r.sum(), 1), mc_total_p5=round(np.percentile(tot, 5), 1), mc_maxDD_median=round(np.median(dd), 1),
              mc_maxDD_worst5pct=round(np.percentile(dd, 95), 1), actual_maxDD=round(stats(r)["maxDD_R"], 1))
    print("\nMONTE CARLO (gated live portfolio, 2,000 shuffles):", mc)
    V.to_csv(OUT / "stk_robust_verdict.csv", index=False)
    pd.Series(mc).to_csv(OUT / "stk_robust_montecarlo.csv")


if __name__ == "__main__":
    main()
