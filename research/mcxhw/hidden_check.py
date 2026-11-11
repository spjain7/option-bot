"""MCX-HC – stress test of the only MCX survivor from the 10-Nov study: BUY on a 3-hour HIDDEN bullish divergence (price
makes a higher low, MACD / OBV make a lower low), compared with plain higher lows (owner 11-Nov priority 5).
NOT a search: the rule is fixed as found on 10-Nov (pivot K=3, MACD 12/26/9, stop below the 5-bar low + 0.1 ATR,
target 3R, max 40 bars, real MCX costs); only robustness neighbours are shown next to it, nothing is picked from them.
Checks
  1. benchmarks on the same bars, stop and target: buy every 8th bar · any confirmed pivot low · any higher low ·
     higher low WITHOUT a MACD divergence (does the indicator add anything?) · buy-and-hold per commodity
  2. regimes from the commodity's DAILY chart at signal time: bull (close > EMA50 and EMA50 up over 10 days), bear
     (close < EMA50 and EMA50 down), sideways (the rest)
  3. metals (GOLD SILVER COPPER ZINC ALUMINIUM) vs energy (CRUDEOIL NATURALGAS) · per commodity · per calendar year
  4. multiple testing: about 37,800 MCX variants were tried on 9-10 Nov (32,044 + 3,400 + 2,325); Bonferroni at 5 %
     needs a one-sided z of about 4.7 · day-clustered t · day-block bootstrap 95 % interval
  5. placebo: the same number of entries placed at random bars of the same commodity (1,000 draws) – where does the
     real mean R rank? and the same for "higher low with MACD divergence" vs a random subset of plain higher lows
  6. neighbours: pivot K 2 / 3 / 4, MACD 8-21 / 12-26 / 16-34, target 2R / 3R          python -m research.mcxhw.hidden_check"""
import json
from statistics import NormalDist
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD  # noqa: E402
from research.mcxhw.search import bars  # noqa: E402
from research.rsidiv import engine as E  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
METALS = {"GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"}
N_TRIED = 32044 + 3400 + 2325
RNG = np.random.default_rng(11)


def signals(b, K=3, fast=12, slow=26):
    h, l, c, v = (b[x].astype(float).reset_index(drop=True) for x in ("high", "low", "close", "volume"))
    n = len(c); pc = c.shift(1)
    atr = pd.Series(E.wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14))
    macd = c.ewm(span=fast, adjust=False).mean() - c.ewm(span=slow, adjust=False).mean()
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    w = 2 * K + 1
    pl = np.where((l == l.rolling(w, center=True).min()).values)[0]; pl = pl[pl + K < n]
    anyp = np.zeros(n, bool); anyp[pl + K] = True
    p0, p1 = pl[:-1], pl[1:]; ok = (p1 - p0 >= 5) & (p1 - p0 <= 60); p0, p1 = p0[ok], p1[ok]
    hl = l.values[p1] > l.values[p0]
    S = {"any_pivot_low": anyp}
    z = np.zeros(n, bool); z[p1[hl] + K] = True; S["higher_low"] = z
    for name, x in (("macd", macd.values), ("obv", obv.values)):
        dv = hl & (x[p1] < x[p0])
        z = np.zeros(n, bool); z[p1[dv] + K] = True; S[f"{name}_hidden"] = z
        z = np.zeros(n, bool); z[p1[hl & ~dv] + K] = True; S[f"higher_low_no_{name}_div"] = z
    every = np.zeros(n, bool); every[::8] = True; S["every_8th_bar"] = every
    lo5 = l.rolling(5).min()
    risk = (c - lo5 + 0.1 * atr).clip(lower=0.5 * atr, upper=3 * atr).values
    return {("X", k, "none", 1): v for k, v in S.items()}, risk


def regime(b, d1):
    """daily close / EMA50 known at the previous daily close -> label per 3-hour bar."""
    e = d1["close"].ewm(span=50, adjust=False).mean()
    lab = np.where((d1["close"] > e) & (e > e.shift(10)), "bull", np.where((d1["close"] < e) & (e < e.shift(10)), "bear", "sideways"))
    s = pd.Series(lab, index=d1["day"]).shift(1)
    return b["time"].dt.normalize().map(s).fillna("sideways").values


def load(K=3, fast=12, slow=26):
    pool = E.Pool(); reg, bh = [], {}
    for gid, name in enumerate(MD.NAMES):
        d5 = MD.LM.load(name, "FIVE_MINUTE")
        b = bars(d5, 180)
        d1 = d5.assign(day=d5["time"].dt.normalize()).groupby("day").agg(close=("close", "last")).reset_index()
        S, risk = signals(b, K, fast, slow)
        grp = gid * 10000 + np.cumsum(b["sw"].fillna(False).astype(bool).values)          # never across a contract switch
        cf = MD.real_cost(name, float(d5.close.iloc[-1])) / float(d5.close.iloc[-1])
        pool.add(b, S, {1: risk, -1: risk}, grp, np.full(len(b), cf), np.zeros(len(b), np.int64), name)
        reg.append(regime(b, d1))
        # buy-and-hold on the contract-switch-free chain: sum of log returns inside each contract segment
        lr = np.log(b["close"].astype(float)).diff().where(~b["sw"].fillna(False).astype(bool)).fillna(0)
        bh[name] = lr.groupby(b["time"].dt.year).sum().apply(np.expm1).round(3).to_dict()
    pool.freeze(); pool.regime = np.concatenate(reg)
    return pool, bh


CUTS = [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")]


def summary(T):
    r = T.netR.values
    if not len(r):
        return dict(n=0)
    dm = T.groupby(pd.to_datetime(T.entry).dt.normalize()).netR.mean()
    t = dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))) if len(dm) > 2 and dm.std(ddof=1) > 0 else np.nan
    bs = [dm.values[RNG.integers(0, len(dm), len(dm))].mean() for _ in range(1000)]
    w = r > 0
    return dict(n=len(r), win=round(100 * w.mean(), 1), R=round(r.mean(), 3), PF=round(r[w].sum() / -r[~w].sum(), 2) if (~w).any() else 99,
                t_day=round(t, 2), lo95=round(np.percentile(bs, 2.5), 3), hi95=round(np.percentile(bs, 97.5), 3))


NAMES = ("every_8th_bar", "any_pivot_low", "higher_low", "higher_low_no_macd_div", "macd_hidden", "higher_low_no_obv_div", "obv_hidden")


def by(T, col):
    return {str(k): summary(g) for k, g in T.groupby(col)}


def placebo(pool, T, key, draws=1000):
    """same count of entries per commodity at random bars (one trade at a time) -> distribution of the mean R."""
    real = T.netR.mean(); per = T.groupby("name").size()
    names = pool.name
    means = []
    for _ in range(draws):
        idx = []
        for nm, cnt in per.items():
            cand = np.where(names == nm)[0]
            idx.append(RNG.choice(cand, size=min(len(cand), int(cnt * 1.3)), replace=False))
        pool.idx[("P", "placebo", "none", 1)] = np.sort(np.concatenate(idx))
        P = pool.run(("P", "placebo", "none", 1), 3.0, 40)
        means.append(P.netR.mean())
    means = np.array(means)
    return dict(real_R=round(real, 3), placebo_mean_R=round(means.mean(), 3), placebo_p95=round(np.percentile(means, 95), 3),
                share_placebo_at_or_above_real=round(float((means >= real).mean()), 4))


def subset_test(Tall, Tsub, draws=2000):
    """is the divergence subset better than a random subset (same size) of all higher lows?"""
    real = Tsub.netR.mean(); r = Tall.netR.values; m = len(Tsub)
    sims = np.array([r[RNG.choice(len(r), m, replace=False)].mean() for _ in range(draws)])
    return dict(subset_R=round(real, 3), all_higher_low_R=round(r.mean(), 3), share_random_subsets_at_or_above=round(float((sims >= real).mean()), 4))


def main():
    pool, bh = load()
    T = {}
    for nm in NAMES:
        x = pool.run(("X", nm, "none", 1), 3.0, 40)
        x["regime"] = pool.regime[x.i.values]
        x["group"] = np.where(pd.Series(x.name).isin(METALS), "metals", "energy")
        x["period"] = E.periods(x.entry.values, CUTS)
        x["year"] = pd.to_datetime(x.entry).dt.year
        T[nm] = x
    R = {"rule": "BUY next 3h open after a confirmed higher low (pivot K=3) where MACD(12,26) / OBV made a lower low; stop 5-bar low - 0.1 ATR; 3R; 40 bars",
         "variants_tried_on_MCX_9_10_Nov": N_TRIED, "bonferroni_z_5pct": round(NormalDist().inv_cdf(1 - 0.05 / N_TRIED), 2)}
    R["benchmarks_all"] = {nm: summary(x) for nm, x in T.items()}
    R["by_period"] = {nm: by(T[nm], "period") for nm in NAMES}
    R["by_regime"] = {nm: by(T[nm], "regime") for nm in ("every_8th_bar", "higher_low", "macd_hidden", "obv_hidden")}
    R["by_group"] = {nm: by(T[nm], "group") for nm in ("every_8th_bar", "higher_low", "macd_hidden", "obv_hidden")}
    R["by_commodity"] = {nm: {k: v["R"] for k, v in by(T[nm], "name").items()} for nm in ("every_8th_bar", "higher_low", "macd_hidden", "obv_hidden")}
    R["by_year"] = {nm: {k: (v["n"], v["R"]) for k, v in by(T[nm], "year").items()} for nm in ("every_8th_bar", "higher_low", "macd_hidden", "obv_hidden")}
    R["buy_and_hold_by_year"] = bh
    R["placebo_random_entries"] = {nm: placebo(pool, T[nm], nm, 300) for nm in ("higher_low", "macd_hidden", "obv_hidden")}
    R["divergence_vs_random_higher_lows"] = {nm: subset_test(T["higher_low"], T[f"{nm}_hidden"]) for nm in ("macd", "obv")}
    nb = []
    for K in (2, 3, 4):
        for fast, slow in ((8, 21), (12, 26), (16, 34)):
            p2, _ = load(K, fast, slow)
            for tg in (2.0, 3.0):
                for nm in ("higher_low", "macd_hidden"):
                    s_ = summary(p2.run(("X", nm, "none", 1), tg, 40)); nb.append(dict(K=K, macd=f"{fast}-{slow}", target_R=tg, rule=nm, **s_))
    R["neighbours"] = nb
    pd.concat([x.assign(rule=nm) for nm, x in T.items() if nm in ("higher_low", "macd_hidden", "obv_hidden")]).drop(columns=["i"]) \
        .to_csv(OUT / "hidden_check_trades.csv.gz", index=False, compression="gzip")
    json.dump(R, open(OUT / "hidden_check.json", "w"), indent=1, default=str)
    print(json.dumps({k: R[k] for k in ("benchmarks_all", "by_regime", "by_group", "placebo_random_entries", "divergence_vs_random_higher_lows")}, indent=1, default=str))
    print(pd.DataFrame(nb).to_string(index=False))
    print(json.dumps(R["by_year"], default=str)); print(json.dumps(bh))


if __name__ == "__main__":
    main()
