"""INTRA-WIN-002 – see REGISTRY_INTRA_WIN2.md.  python -m research.search.intra_win2"""
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research import instruments as INS  # noqa
from research.search import stock_check as SC, stock_search as SR, strategy_search as SS  # noqa
from research.search.intraday_search import prep, SPLIT  # noqa
from research.search.intra_win import entries, simulate, STOPS, TGTS  # noqa

OUT = ROOT / "research" / "search" / "results_intra_win2"
FLAGS = ["adx", "with", "ema200", "room", "snap", "vol", "oi", "early", "calm"]
EX = [f"S{s}_T{t}" for s in STOPS for t in TGTS]


def daily_ctx(hp):
    d = hp.groupby("day").agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    d["adx_y"] = I.adx(d, 14).shift(1)
    d["e200_y"] = np.sign(d["close"] - I.ema(d["close"], 200)).shift(1)
    return d


def run(items, kind):
    rows = []
    for name, h, lot, oi in items:
        hp = prep(h, oi)
        hp["atrp"] = hp["atr"] / hp["close"]
        hp["calm"] = hp["atrp"] < hp["atrp"].rolling(200, min_periods=100).median().shift(1)
        dc = daily_ctx(hp)
        for day, g in hp.groupby("day"):
            g = g.reset_index(drop=True)
            if day not in dc.index:
                continue
            adx_y, e200 = dc.at[day, "adx_y"], dc.at[day, "e200_y"]
            for f, i, s in entries(g, oi is not None):
                if i + 1 >= len(g):
                    continue
                e0, a, res = simulate(g, i, s)
                cp = SC.cost_frac(e0, lot) if kind == "STOCKS" else INS.cost_points(name, e0)
                r = g.iloc[i]
                fl = dict(adx=bool(adx_y > 25), with_=bool(s == r.trend), ema200=bool(s == e200),
                          room=bool(r.rsi < 70 if s > 0 else r.rsi > 30), snap=bool(r.rsi < 35 if s > 0 else r.rsi > 65),
                          vol=bool(r.volx > 1.5), oi=bool((r.lb_y if s > 0 else r.sb_y)) if oi is not None else False,
                          early=bool(r.time.hour < 12), calm=bool(r.calm))
                rr = {}
                for (sm, tm), p in res.items():
                    R = sm * a
                    rr[f"S{sm}_T{tm}"] = (p - cp) / R
                    rr[f"S{sm}_T{tm}_2x"] = (p - 2 * cp) / R
                rows.append(dict(name=name, fam=f, time=r.time, side=s, **fl, **rr))
        print(kind, name, flush=True)
    T = pd.DataFrame(rows).rename(columns={"with_": "with"})
    return T


def search(T, label):
    out = {}
    T["ho"] = T["time"] >= SPLIT
    combos = [c for k in range(4) for c in itertools.combinations(FLAGS, k)]
    for fam, F in T.groupby("fam"):
        for c in combos:
            m = np.ones(len(F), bool)
            for fl in c:
                m &= F[fl].values
            G = F[m]
            D = G[~G["ho"]]
            if len(D) < 100:
                continue
            for ex in EX:
                r = D[ex].values
                win = (r > 0).mean() * 100
                if win < 80 or r.mean() < 0.05 or D[ex + "_2x"].mean() <= 0:
                    continue
                sd = SR.stats(r)
                if (sd["pf"] or 0) < 1.15 or sd["p5"] <= 0:
                    continue
                Hh = G[G["ho"]]
                sh = SR.stats(Hh[ex].values)
                h2 = float(Hh[ex + "_2x"].mean()) if len(Hh) else None
                ok = bool(sh.get("trades", 0) >= 50 and sh["win"] >= 75 and sh["exp_r"] > 0 and h2 > 0)
                out[f"{label}|{fam}|{'+'.join(c) or 'none'}|{ex}"] = dict(design=sd, design_2x=round(float(D[ex + '_2x'].mean()), 3),
                                                                          holdout=sh, holdout_2x=None if h2 is None else round(h2, 3), PASS=ok)
    return out


def main():
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    stocks = []
    for r in man.itertuples():
        f, fo = SR.DATA / f"{r.name}_ONE_HOUR.csv", SR.DATA / f"{r.name}_OI_ONE_DAY.csv"
        if f.exists():
            h = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
            stocks.append((r.name, h, r.lot, pd.read_csv(fo) if fo.exists() else None))
    idx = [(n, SS.load("NFO", n, "ONE_HOUR"), None, None) for n in ("NIFTY", "BANKNIFTY")]
    mcx = [(n, SS.load("MCX", n, "ONE_HOUR"), None, None) for n in ("CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM")]
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for label, items in (("INDEX", idx), ("MCX", mcx), ("STOCKS", stocks)):
        T = run([x for x in items if x[1] is not None], label)
        T.to_csv(OUT / f"trades_{label}.csv.gz", index=False)
        res.update(search(T, label))
        (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))
        print(label, "shortlisted:", sum(k.startswith(label) for k in res), "PASS:", sum(v["PASS"] for k, v in res.items() if k.startswith(label)), flush=True)
    for k, v in sorted(res.items(), key=lambda kv: -kv[1]["holdout"].get("exp_r", -9)):
        print(k, v["design"], "| HO", v["holdout"], v["holdout_2x"], "PASS" if v["PASS"] else "")


if __name__ == "__main__":
    main()
