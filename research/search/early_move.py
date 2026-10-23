"""EARLY-MOVE-001 – see REGISTRY_EARLY.md.  python -m research.search.early_move"""
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
OUT = ROOT / "research" / "search" / "results_early"
FLAGS = ["nifty", "oi", "dtrend", "ema200", "vwap", "rsi", "strong"]
EXITS = {"X1": None, "X2": (2.0, 1.0), "X3": (3.0, 1.5)}


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
        h["rsi"] = I.rsi(h["close"], 14)
        tp = (h["high"] + h["low"] + h["close"]) / 3
        h["vwap"] = (tp * v).groupby(h["day"]).cumsum() / v.groupby(h["day"]).cumsum().replace(0, np.nan)
        d = h.groupby("day").agg(o=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
        d["e50"], d["e200"] = I.ema(d["close"], 50), I.ema(d["close"], 200)
        d["h20"], d["l20"] = d["high"].rolling(20).max(), d["low"].rolling(20).min()
        rng = d["high"] - d["low"]
        d["coil"] = (rng <= rng.rolling(7).min()) | ((d["high"] < d["high"].shift(1)) & (d["low"] > d["low"].shift(1)))
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
            O, H, L, C = (g[c].values for c in ("open", "high", "low", "close"))
            got = set()
            for j in range(min(4, len(g) - 1)):
                rj = g.iloc[j]
                mv = (rj.close / o0 - 1) * 100
                if abs(mv) >= 1:
                    continue
                cands = []
                if rj.volx >= 2.5 and rj.close != rj.open:
                    cands.append(("B1", 1 if rj.close > rj.open else -1))
                if y.coil and pd.notna(y.h20):
                    if rj.close >= y.h20 * 0.99:
                        cands.append(("B2", 1))
                    elif rj.close <= y.l20 * 1.01:
                        cands.append(("B2", -1))
                if rj.volx >= 1.5:
                    if rj.close > y.high and C[:j].max(initial=-1e18) <= y.high:
                        cands.append(("B3", 1))
                    elif rj.close < y.low and C[:j].min(initial=1e18) >= y.low:
                        cands.append(("B3", -1))
                for fam, s in cands:
                    if fam in got:
                        continue
                    got.add(fam)
                    rg = max(rj.high - rj.low, 1e-9)
                    nc = nfc.get(rj.time, np.nan)
                    fl = dict(nifty=bool(np.sign(nc - nopen.get(dd, np.nan)) == s), oi=bool(y.lb if s > 0 else y.sb),
                              dtrend=bool(s * (y.close - y.e50) > 0), ema200=bool(s * (y.close - y.e200) > 0),
                              vwap=bool(s * (rj.close - rj.vwap) > 0),
                              rsi=bool(55 <= rj.rsi <= 75) if s > 0 else bool(25 <= rj.rsi <= 45),
                              strong=bool((rj.close - rj.low) / rg >= 0.75) if s > 0 else bool((rj.high - rj.close) / rg >= 0.75))
                    e = O[j + 1]
                    cost = SC.cost_frac(e, r.lot)
                    best = max(H[j + 1:]) / e - 1 if s > 0 else 1 - min(L[j + 1:]) / e
                    for ex, tpsl in EXITS.items():
                        px = None
                        if tpsl:
                            tpp, slp = e * (1 + s * tpsl[0] / 100), e * (1 - s * tpsl[1] / 100)
                            for k in range(j + 1, len(g)):
                                if (L[k] <= slp) if s > 0 else (H[k] >= slp):
                                    px = min(O[k], slp) if s > 0 else max(O[k], slp); break
                                if (H[k] >= tpp) if s > 0 else (L[k] <= tpp):
                                    px = tpp; break
                        if px is None:
                            px = C[-1]
                        g1 = s * (px - e)
                        rows.append(dict(name=r.name, day=dd, side=s, fam=fam, ex=ex, lot=r.lot, price=e,
                                         net=(g1 - cost) / e * 100, net2=(g1 - 2 * cost) / e * 100,
                                         rs=(g1 - cost) * r.lot, reach2=bool(best >= 0.02), **fl))
        print(r.name, flush=True)
    return pd.DataFrame(rows)


def evaluate(T):
    res = {}
    T["ho"] = T["day"] >= SPLIT
    T["hy"] = T["day"].dt.year.astype(str) + "H" + ((T["day"].dt.month > 6) + 1).astype(str)
    combos = [c for k in range(4) for c in itertools.combinations(FLAGS, k)]
    for (fam, ex), F in T.groupby(["fam", "ex"]):
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
            res[f"{fam}|{ex}|{'+'.join(c) or 'none'}"] = dict(
                design=sd, holdout=sh, holdout_2x=round(h2, 3), holdout_rs_per_lot=round(float(Hh["rs"].mean()), 0),
                holdout_reach2=round(float(Hh["reach2"].mean() * 100), 1), per_month=round(len(Hh) / 28, 1),
                halfyears_positive=f"{int((hy > 0).sum())}/{len(hy)}",
                PASS=bool(sh.get("trades", 0) >= 100 and sh["exp_r"] >= 0.05 and h2 > 0 and (hy > 0).sum() >= 3))
    return res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    T = run()
    T.to_pickle(OUT / "trades.pkl")
    base = T.groupby(["fam", "ex"]).agg(n=("net", "size"), win=("net", lambda s: (s > 0).mean() * 100),
                                         net=("net", "mean"), rs=("rs", "mean"), reach2=("reach2", "mean"))
    print("BASE (no filters, all years)\n", base.round(2))
    res = evaluate(T)
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))
    p = {k: v for k, v in res.items() if v["PASS"]}
    print("shortlisted", len(res), "PASS", len(p))
    for k, v in sorted(p.items(), key=lambda kv: -kv[1]["holdout"]["exp_r"])[:20]:
        print("PASS", k, "D", v["design"], "| HO", v["holdout"], "2x", v["holdout_2x"], "Rs/lot", v["holdout_rs_per_lot"],
              "reach2%", v["holdout_reach2"], "per month", v["per_month"], v["halfyears_positive"])


if __name__ == "__main__":
    main()
