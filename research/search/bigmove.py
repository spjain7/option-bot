"""BIG-MOVE-001 – see REGISTRY_BIGMOVE.md.  python -m research.search.bigmove"""
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research.search import stock_check as SC, stock_search as SR, strategy_search as SS  # noqa
from alerts.stocks import in_rollover_window  # noqa

SPLIT = pd.Timestamp("2024-07-01")
OUT = ROOT / "research" / "search" / "results_bigmove"
FLAGS = ["nifty", "oi", "dtrend", "ema200", "gap", "nr7", "pdh", "strong", "rsi_ok"]


def run():
    nf = SS.load("NFO", "NIFTY", "ONE_HOUR")
    nf["day"] = nf["time"].dt.normalize()
    nfo = nf.groupby("day").agg(o=("open", "first"))
    nfh = nf[nf.groupby("day").cumcount() == 0].set_index("day")["close"]
    nifty_dir = np.sign(nfh - nfo["o"].reindex(nfh.index))
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    rows = []
    for r in man.itertuples():
        f, fo = SR.DATA / f"{r.name}_ONE_HOUR.csv", SR.DATA / f"{r.name}_OI_ONE_DAY.csv"
        if not f.exists():
            continue
        h = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
        h["day"] = h["time"].dt.normalize()
        v = h["volume"].astype(float)
        key = h["time"].dt.hour * 60 + h["time"].dt.minute
        h["volx"] = v / v.groupby(key).transform(lambda s: s.shift(1).rolling(10, min_periods=5).mean())
        h["atr"] = I.atr(h, 14)
        h["rsi"] = I.rsi(h["close"], 14)
        d = h.groupby("day").agg(o=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
        d["e50"], d["e200"] = I.ema(d["close"], 50), I.ema(d["close"], 200)
        rng = d["high"] - d["low"]
        d["nr7"] = rng <= rng.rolling(7).min()
        if fo.exists():
            oi = pd.read_csv(fo)
            o = oi.groupby(pd.to_datetime(oi["time"].astype(str).str[:10]))["oi"].last().reindex(d.index)
            doi, dp = o.pct_change(), d["close"].pct_change()
            d["lb"], d["sb"] = (dp > 0) & (doi >= 0.02), (dp < 0) & (doi >= 0.02)
        else:
            d["lb"] = d["sb"] = False
        days = list(d.index)
        for i, (dd, g) in enumerate(h.groupby("day")):
            if i == 0 or len(g) < 6 or in_rollover_window(dd):
                continue
            g = g.reset_index(drop=True)
            y = d.iloc[i - 1]
            o0, f0 = g["open"].iat[0], g.iloc[0]
            fh = (f0.close / o0 - 1) * 100
            if abs(fh) < 1.5 or not (f0.volx >= 1.5) or pd.isna(f0.atr):
                continue
            s = 1 if fh > 0 else -1
            frg = max(f0.high - f0.low, 1e-9)
            fl = dict(nifty=bool(nifty_dir.get(dd, 0) == s), oi=bool(y.lb if s > 0 else y.sb),
                      dtrend=bool(s * (y.close - y.e50) > 0), ema200=bool(s * (y.close - y.e200) > 0),
                      gap=bool(s * (o0 / y.close - 1) >= 0.005), nr7=bool(y.nr7),
                      pdh=bool((f0.close > y.high) if s > 0 else (f0.close < y.low)),
                      strong=bool((f0.close - f0.low) / frg >= 0.75) if s > 0 else bool((f0.high - f0.close) / frg >= 0.75),
                      rsi_ok=bool(f0.rsi <= 85) if s > 0 else bool(f0.rsi >= 15))
            O, H, L, C, A = (g[c].values[1:] for c in ("open", "high", "low", "close", "atr"))
            tms = g["time"].values[1:]
            lvl_hi, lvl_lo, mid = f0.high, f0.low, (f0.high + f0.low) / 2
            ents = {"E1": (0, O[0])}
            for k in range(len(O)):                         # E2 break of first-hour extreme
                lv = lvl_hi if s > 0 else lvl_lo
                if (H[k] > lv) if s > 0 else (L[k] < lv):
                    ents["E2"] = (k, max(O[k], lv) if s > 0 else min(O[k], lv)); break
            for k in range(len(O)):                         # E3 pull-back to the midpoint before 13:15
                if pd.Timestamp(tms[k]).hour >= 13:
                    break
                if (L[k] <= mid) if s > 0 else (H[k] >= mid):
                    ents["E3"] = (k, min(O[k], mid) if s > 0 else max(O[k], mid)); break
            stop0 = lvl_lo if s > 0 else lvl_hi
            for en, (k0, e) in ents.items():
                risk = s * (e - stop0)
                cost = SC.cost_frac(e, r.lot)
                for ex in ("X1", "X2", "X3", "X4"):
                    st, best, px = stop0, e, None
                    tp = e + s * 2 * risk if risk > 0 else None
                    for k in range(k0, len(O)):
                        if ex != "X1" and risk > 0:
                            if (L[k] <= st) if s > 0 else (H[k] >= st):
                                px = (min(O[k], st) if s > 0 else max(O[k], st)) if k > k0 else st; break
                            if ex == "X4" and ((H[k] >= tp) if s > 0 else (L[k] <= tp)):
                                px = tp; break
                            if ex == "X3":
                                best = max(best, C[k]) if s > 0 else min(best, C[k])
                                st = max(st, best - A[k]) if s > 0 else min(st, best + A[k])
                    if px is None:
                        px = C[-1]
                    g1 = s * (px - e)
                    rows.append(dict(name=r.name, day=dd, side=s, fh=abs(fh), volx=f0.volx, en=en, ex=ex,
                                     net=(g1 - cost) / e * 100, net2=(g1 - 2 * cost) / e * 100, **fl))
        print(r.name, flush=True)
    return pd.DataFrame(rows)


def evaluate(T):
    res = {}
    T["ho"] = T["day"] >= SPLIT
    combos = [c for k in range(4) for c in itertools.combinations(FLAGS, k)]
    for M, V in itertools.product((1.5, 2, 3), (1.5, 2, 3)):
        B = T[(T["fh"] >= M) & (T["volx"] >= V)]
        for (en, ex), F in B.groupby(["en", "ex"]):
            for c in combos:
                m = np.ones(len(F), bool)
                for x in c:
                    m &= F[x].values
                G = F[m]
                D = G[~G["ho"]]
                if len(D) < 100:
                    continue
                sd = SR.stats(D["net"].values)
                if not (sd["exp_r"] >= 0.10 and D["net2"].mean() > 0 and sd["p5"] > 0):
                    continue
                Hh = G[G["ho"]]
                sh = SR.stats(Hh["net"].values)
                h2 = float(Hh["net2"].mean()) if len(Hh) else -9
                res[f"M{M}|V{V}|{en}|{ex}|{'+'.join(c) or 'none'}"] = dict(
                    design=sd, design_2x=round(float(D["net2"].mean()), 3), holdout=sh, holdout_2x=round(h2, 3),
                    PASS=bool(sh.get("trades", 0) >= 100 and sh["exp_r"] >= 0.05 and h2 > 0))
    return res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    T = run()
    T.to_pickle(OUT / "trades.pkl")
    res = evaluate(T)
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))
    p = {k: v for k, v in res.items() if v["PASS"]}
    print("shortlisted", len(res), "PASS", len(p))
    for k, v in sorted(p.items(), key=lambda kv: -kv[1]["holdout"]["exp_r"])[:25]:
        print("PASS", k, "D", v["design"], "| HO", v["holdout"], "2x", v["holdout_2x"])
    for k, v in sorted(res.items(), key=lambda kv: -kv[1]["holdout"].get("exp_r", -9))[:5]:
        print("top-HO", k, v["design"], v["holdout"])


if __name__ == "__main__":
    main()
