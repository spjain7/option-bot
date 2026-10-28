"""STRATEGY-PROGRAM-001 – index / MCX futures breakouts (S1 3-hour, S2 daily, S3 monthly), BUY and SELL separately.
Baseline = live rules. Candidate filters and exits are pre-declared in harness.py and tested one at a time.
python research/program/run_futures.py      (needs research/data, not in git)"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H  # noqa: E402
from research.search import strategy_search as SS  # noqa: E402

OUT = ROOT / "research/program/results"
SPLITS = {"angel": (pd.Timestamp("2024-07-01"), pd.Timestamp("2025-07-01")),
          "nseidx": (pd.Timestamp("2019-01-01"), pd.Timestamp("2022-01-01")),
          "proxy": (pd.Timestamp("2019-01-01"), pd.Timestamp("2022-01-01"))}
JOBS = [("angel", n, ex) for ex, n in SS.NAMES] + [("nseidx", n, "NFO") for n in ("NIFTY", "BANKNIFTY")] + \
       [("proxy", n, "MCX") for n in ("GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ALUMINIUM")]


def frames(ds, name, ex):
    if ds == "angel":
        fr = H.angel(name, ex)
        return [("S1", fr.get("3h")), ("S2", fr.get("1d")), ("S3", fr.get("1d"))]
    df = H.nseidx(name) if ds == "nseidx" else H.proxy(name)
    return [("S2", df), ("S3", df)]


def one(job):
    ds, name, ex = job
    rows = []
    for strat, df in frames(ds, name, ex):
        if df is None or len(df) < 300:
            continue
        f = H.features(df)
        cost = H.cost_series(name, f, ds)
        sig = H.monthly_signal(f) if strat == "S3" else H.bo_signal(f)
        P = H.LIVE[strat]
        start = 60 if strat == "S3" else 210
        for side in (1, -1):
            base = [dict(t, variant="BASE") for t in H.simulate(f, sig, side, P["k"], P["r"], P["maxh"], P["cap"], cost, start)]
            rows += base
            for lab, m in H.F(f, side).items():
                s2 = np.where(np.asarray(m, bool), sig, 0)
                rows += [dict(t, variant=lab) for t in H.simulate(f, s2, side, P["k"], P["r"], P["maxh"], P["cap"], cost, start)]
            for lab, x in H.EXITS.items():
                if x is None:
                    continue
                k, r = x
                rows += [dict(t, variant=lab) for t in H.simulate(f, sig, side, 2.0 if k == "swing" else k, r, P["maxh"], P["cap"], cost,
                                                                  start, swing=(k == "swing"))]
            # regime tags for the baseline trades (known at the signal bar)
            for t in rows:
                if t.get("variant") == "BASE" and "regime" not in t and t["i"] < len(f):
                    i = t["i"]
                    t["regime"] = ("trend" if f["adx"].iat[i] >= 25 else "range") + "/" + \
                                  ("hi-vol" if f["atrp"].iat[i] > f["atrp_med"].iat[i] else "lo-vol")
        rows = [dict(t, dataset=ds, name=name, strat=strat) if "dataset" not in t else t for t in rows]
    return rows


def split(ds, t):
    a, b = SPLITS[ds]
    return np.where(t < a, "1-train", np.where(t < b, "2-valid", "3-test"))


def paired_delta(c, b, n=1000, seed=5):
    m = sorted(set(pd.to_datetime(b["time"]).dt.to_period("M")))
    if len(m) < 6 or len(c) < 5:
        return (np.nan, np.nan)
    cs = c.groupby(pd.to_datetime(c["time"]).dt.to_period("M"))["r1"].agg(["sum", "size"]).reindex(m).fillna(0).values
    bs = b.groupby(pd.to_datetime(b["time"]).dt.to_period("M"))["r1"].agg(["sum", "size"]).reindex(m).fillna(0).values
    rng = np.random.default_rng(seed); d = []
    for _ in range(n):
        ix = rng.integers(0, len(m), len(m))
        x, y = cs[ix].sum(0), bs[ix].sum(0)
        if x[1] and y[1]:
            d.append(x[0] / x[1] - y[0] / y[1])
    return tuple(np.round(np.percentile(d, [2.5, 97.5]), 3)) if d else (np.nan, np.nan)


def md(df):
    return df.to_markdown(index=False) if len(df) else "_none_"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with Pool(8) as p:
        rows = [r for x in p.map(one, JOBS) for r in x]
    T = pd.DataFrame(rows)
    T["time"] = pd.to_datetime(T["time"])
    T["year"] = T["time"].dt.year
    T["split"] = [split(d, pd.Series([t]))[0] for d, t in zip(T["dataset"], T["time"])]
    T.to_csv(OUT / "futures_trades.csv.gz", index=False)
    L = ["# STRATEGY-PROGRAM-001 – index / MCX futures breakouts (generated)\n",
         "Win = trade closed with net R > 0 after costs. exp1/exp2 = mean net R per trade at 1×/2× costs. ci = 95 % month-block "
         "bootstrap. tgt/stop/gap = % of trades exiting at target / stop / gap through stop. invalid = signals cancelled before entry.\n"]
    summary = []
    for (ds, st, side), G in T.groupby(["dataset", "strat", "side"]):
        B = G[G["variant"] == "BASE"]
        L.append(f"\n## {ds} · {st} · {side}\n")
        bt = [dict(split=sp, **H.metrics(B[B["split"] == sp])) for sp in ("1-train", "2-valid", "3-test")] + [dict(split="ALL", **H.metrics(B))]
        L.append("### Baseline (live rules)\n" + md(pd.DataFrame(bt)) + "\n")
        bb = B[B["status"] == "trade"]
        if len(bb):
            L.append("by year: " + "; ".join(f"{y}: n{len(g)} {g.r1.mean():+.2f}R w{(g.r1 > 0).mean() * 100:.0f}%" for y, g in bb.groupby("year")) + "\n")
            L.append("by instrument: " + "; ".join(f"{n}: n{len(g)} {g.r1.mean():+.2f}R" for n, g in bb.groupby("name")) + "\n")
            if "regime" in bb:
                L.append("by regime: " + "; ".join(f"{n}: n{len(g)} {g.r1.mean():+.2f}R w{(g.r1 > 0).mean() * 100:.0f}%" for n, g in bb.groupby("regime")) + "\n")
        res = []
        for v, V in G.groupby("variant"):
            if v == "BASE":
                continue
            r = dict(variant=v)
            for sp in ("1-train", "2-valid", "3-test"):
                c, b = V[(V["split"] == sp) & (V["status"] == "trade")], B[(B["split"] == sp) & (B["status"] == "trade")]
                m = H.metrics(V[V["split"] == sp])
                r[f"{sp[2:]}_n"] = m.get("n", 0); r[f"{sp[2:]}_win"] = m.get("win"); r[f"{sp[2:]}_exp2"] = m.get("exp2")
                r[f"{sp[2:]}_d"] = round(c.r1.mean() - b.r1.mean(), 3) if len(c) and len(b) else np.nan
            ok_train = r["train_n"] >= 20 and (r["train_d"] or -1) > 0 and (r["train_exp2"] or -1) > 0
            ok_valid = ok_train and r["valid_n"] >= 10 and (r["valid_d"] or -1) > 0 and (r["valid_exp2"] or -1) > 0
            ok_test = ok_valid and r["test_n"] >= 10 and (r["test_d"] or -1) > 0 and (r["test_exp2"] or -1) > 0
            r["verdict"] = ("PASS all 3" if ok_test else "pass train+valid, FAIL test" if ok_valid else
                            "pass train, FAIL valid" if ok_train else "FAIL train")
            res.append(r)
            summary.append(dict(dataset=ds, strat=st, side=side, variant=v, **{k: r[k] for k in r if k != "variant"}))
        L.append("### Candidates (Δ = mean R minus baseline in the same split; selection on TRAIN only)\n" + md(pd.DataFrame(res)) + "\n")
    S = pd.DataFrame(summary)
    S.to_csv(OUT / "futures_candidates.csv", index=False)
    (OUT / "futures_tables.md").write_text("\n".join(L))
    print("\n".join(L)[:4000])
    print("\nPASS all 3:\n", S[S.verdict == "PASS all 3"][["dataset", "strat", "side", "variant", "train_d", "valid_d", "test_d", "test_win", "test_exp2"]].to_string())


if __name__ == "__main__":
    main()
