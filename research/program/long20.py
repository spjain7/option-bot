"""LONG20-001 (6-Nov-2026, master instruction §9 / round-2 phase 4): is the commodity BUY-only edge a 2022-26 bull-market
artifact, and does any SELL work in bear years? Every SEARCH-V2 / SEARCH-ALL family on 20 years of MCX front-month stitched
DAILY candles (2006-2026, 7 commodities; NATURALGAS from 2016) and NIFTY / BANKNIFTY futures daily (2011-2026), both sides,
4 exits, 2x costs, periods 2006-12 / 2013-19 / 2020-26, and a regime split by the commodity's own 200-day trend
(bull: close > EMA200, bear: below). python research/program/long20.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, search_all as SA, search_v2 as SV, wkmo as WK  # noqa: E402
from research import instruments as INS  # noqa: E402

rows = []
for ex, nm in WK.INST:
    d = WK.daily(ex, nm)
    d["switch"] = False
    f = H.features(d); f["switch"] = False
    cost = np.array([INS.cost_points(nm, p, 1.0) if ex == "MCX" else p * 0.0004 for p in f.close.values])
    dtr = SA.daily_trend(d)
    bull = (f.close > f.ema200).values
    sets = SV.signal_sets(f, dtr, "1d") + SA.signal_sets(f, dtr)
    for fam, par, fn, b, s in sets:
        for side, m in ((1, b), (-1, s)):
            sig = np.where(np.nan_to_num(np.asarray(m, float)) > 0, side, 0)
            if not sig.any():
                continue
            for k, r in SA.EXITS:
                for x in H.simulate(f, sig, side, k, r, 20, 0, cost, start=210):
                    if x["status"] == "trade":
                        rows.append(("MCX" if ex == "MCX" else "INDEX", fam, par, fn, "BUY" if side > 0 else "SELL", f"{k:g}ATR/{r:g}R",
                                     nm, x["time"], x["r2"], "bull" if bull[x["i"]] else "bear"))
T = pd.DataFrame(rows, columns=["grp", "fam", "par", "filt", "side", "exit", "name", "time", "r", "reg"])
T["per"] = T.time.map(WK.per)
K = ["grp", "fam", "par", "filt", "side", "exit"]
g = T.groupby(K).r
S = pd.DataFrame(dict(n=g.size(), win=g.apply(lambda s: (s > 0).mean() * 100), R=g.mean(),
                      PF=g.apply(lambda s: s[s > 0].sum() / max(-s[s <= 0].sum(), 1e-9))))
S = S.join(T.pivot_table(index=K, columns="per", values="r", aggfunc="mean"))
S = S.join(T.pivot_table(index=K, columns="reg", values="r", aggfunc="mean").add_prefix("R_"))
S = S.join(T.groupby(K + ["name"]).r.mean().gt(0).groupby(level=list(range(len(K)))).mean().rename("names_pos"))
from scipy import stats as SS  # noqa: E402
sd = g.std(); S["t"] = S.R / (sd / np.sqrt(S.n)); S["p"] = 1 - SS.t.cdf(S.t, np.maximum(S.n - 1, 1))
rank = S.p.rank(method="first"); S["q"] = (S.p * len(S) / rank).sort_values(ascending=False).cummin().reindex(S.index).clip(upper=1)
S["all3"] = (S[["2006-12", "2013-19", "2020-26"]].fillna(-1) > 0).all(axis=1)
S["robust"] = S.all3 & (S.n >= 60) & (S.q < 0.10) & (S.names_pos >= 0.55)
S = S.reset_index(); S.to_csv(ROOT / "research/program/results/long20_summary.csv", index=False)
pd.set_option("display.width", 240); pd.set_option("display.max_rows", 200)
c = ["grp", "fam", "par", "filt", "side", "exit", "n", "win", "R", "PF", "2006-12", "2013-19", "2020-26", "R_bull", "R_bear", "names_pos", "q"]
print(f"combinations {len(S)} · robust {int(S.robust.sum())}")
for (gp, sd_), x in S[S.robust].groupby(["grp", "side"]):
    print(f"\n=== {gp} {sd_} robust: {len(x)}"); print(x.sort_values("R", ascending=False).head(12)[c].round(2).to_string(index=False))
print("\nMCX SELL best by 2013-19 (metals bear years), n >= 60:")
y = S[(S.grp == "MCX") & (S.side == "SELL") & (S.n >= 60)].sort_values("2013-19", ascending=False)
print(y.head(8)[c].round(2).to_string(index=False))
print("\nMCX BUY rules similar to the live ones (2013-19 column = bear-market years):")
z = S[(S.grp == "MCX") & (S.side == "BUY") & S.fam.isin(["BO", "RETEST", "EMAX", "MACD", "MOMO"]) & (S.n >= 60)].sort_values("R", ascending=False)
print(z.head(12)[c].round(2).to_string(index=False))
