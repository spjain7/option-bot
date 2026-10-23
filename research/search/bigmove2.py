"""BIG-MOVE-002 – see REGISTRY_BIGMOVE2.md.  python -m research.search.bigmove2"""
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
OUT = ROOT / "research" / "search" / "results_bigmove2"
FLAGS = ["nifty", "oi", "dtrend", "ema200", "gap", "nr7", "pdh", "strong", "rsi_ok", "late"]


def run():
    nf = SS.load("NFO", "NIFTY", "ONE_HOUR")
    nf["day"] = nf["time"].dt.normalize()
    nopen = nf.groupby("day")["open"].first()
    nfc = nf.set_index("time")["close"]
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
        h["atr"], h["rsi"] = I.atr(h, 14), I.rsi(h["close"], 14)
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
        for i, (dd, g) in enumerate(h.groupby("day")):
            if i == 0 or len(g) < 6 or in_rollover_window(dd):
                continue
            g = g.reset_index(drop=True)
            y = d.iloc[i - 1]
            o0 = g["open"].iat[0]
            mv = (g["close"] / o0 - 1) * 100
            O, H, L, C, A = (g[c].values for c in ("open", "high", "low", "close", "atr"))
            done = set()
            for j in range(len(g) - 1):
                endt = g["time"].iat[j] + pd.Timedelta(hours=1)
                if endt.hour * 60 + endt.minute > 14 * 60 + 15:
                    break
                for M in (1.5, 2, 3):
                    if M in done or abs(mv.iat[j]) < M:
                        continue
                    done.add(M)
                    rj = g.iloc[j]
                    if not (rj.volx >= 1.5) or pd.isna(rj.atr):
                        continue
                    s = 1 if mv.iat[j] > 0 else -1
                    nc = nfc.get(rj.time, np.nan)
                    rg = max(rj.high - rj.low, 1e-9)
                    fl = dict(nifty=bool(np.sign(nc - nopen.get(dd, np.nan)) == s), oi=bool(y.lb if s > 0 else y.sb),
                              dtrend=bool(s * (y.close - y.e50) > 0), ema200=bool(s * (y.close - y.e200) > 0),
                              gap=bool(s * (o0 / y.close - 1) >= 0.005), nr7=bool(y.nr7),
                              pdh=bool((rj.close > y.high) if s > 0 else (rj.close < y.low)),
                              strong=bool((rj.close - rj.low) / rg >= 0.75) if s > 0 else bool((rj.high - rj.close) / rg >= 0.75),
                              rsi_ok=bool(rj.rsi <= 85) if s > 0 else bool(rj.rsi >= 15), late=bool(j >= 2))
                    e = O[j + 1]
                    stop0 = rj.low if s > 0 else rj.high
                    risk = s * (e - stop0)
                    cost = SC.cost_frac(e, r.lot)
                    for ex in ("X1", "X2", "X3", "X4"):
                        st, best, px = stop0, e, None
                        tp = e + s * 2 * risk
                        for k in range(j + 1, len(g)):
                            if ex != "X1" and risk > 0:
                                if (L[k] <= st) if s > 0 else (H[k] >= st):
                                    px = min(O[k], st) if s > 0 else max(O[k], st); break
                                if ex == "X4" and ((H[k] >= tp) if s > 0 else (L[k] <= tp)):
                                    px = tp; break
                                if ex == "X3":
                                    best = max(best, C[k]) if s > 0 else min(best, C[k])
                                    st = max(st, best - A[k]) if s > 0 else min(st, best + A[k])
                        if px is None:
                            px = C[-1]
                        g1 = s * (px - e)
                        rows.append(dict(name=r.name, day=dd, side=s, M=M, volx=rj.volx, ex=ex,
                                         net=(g1 - cost) / e * 100, net2=(g1 - 2 * cost) / e * 100, **fl))
        print(r.name, flush=True)
    return pd.DataFrame(rows)


def evaluate(T):
    res = {}
    T["ho"] = T["day"] >= SPLIT
    T["hy"] = T["day"].dt.year.astype(str) + "H" + ((T["day"].dt.month > 6) + 1).astype(str)
    combos = [c for k in range(4) for c in itertools.combinations(FLAGS, k)]
    for M, V in itertools.product((1.5, 2, 3), (1.5, 2, 3)):
        B = T[(T["M"] == M) & (T["volx"] >= V)]
        for ex, F in B.groupby("ex"):
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
                hy = Hh.groupby("hy")["net"].mean()
                stable = int((hy > 0).sum())
                res[f"M{M}|V{V}|{ex}|{'+'.join(c) or 'none'}"] = dict(
                    design=sd, design_2x=round(float(D["net2"].mean()), 3), holdout=sh, holdout_2x=round(h2, 3),
                    halfyears_positive=f"{stable}/{len(hy)}", by_side=Hh.groupby("side")["net"].mean().round(3).to_dict(),
                    PASS=bool(sh.get("trades", 0) >= 100 and sh["exp_r"] >= 0.05 and h2 > 0 and stable >= 3))
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
        print("PASS", k, "D", v["design"], "| HO", v["holdout"], "2x", v["holdout_2x"], v["halfyears_positive"], v["by_side"])


if __name__ == "__main__":
    main()
