"""RSIDIV-CM-CHECK – stress test of the cash result that survived the 11-Nov Holm control: BUY at Monday's open when the
WEEKLY RSI(14) crosses above 75 and the stock is in the bottom third of that week's eligible stocks by 60-session
median turnover (still >= ₹25 cr). Stop 0.1 ATR below the 5-week low (0.5–3 ATR), target 1R, max 10 weeks.
Fixed rule; neighbours shown, nothing picked. Checks: per year · slippage 0.05 → 0.10 / 0.20 / 0.30 % per side
(thin stocks cost more) · neighbours RSI 70 / 75 / 80 × liquidity bottom third / bottom half / all · targets 1-3R ·
market regime · placebo (same count of random eligible stock-weeks, 300 draws).   python -m research.rsidiv.cash_check"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E  # noqa: E402
from research.rsidiv.cash import CUTS  # noqa: E402
from research.cashq import data as D  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
RNG = np.random.default_rng(9)


def s(T):
    r = T.netR.values
    if len(r) < 5:
        return dict(n=len(r))
    dm = T.groupby(pd.to_datetime(T.entry).dt.normalize()).netR.mean(); w = r > 0
    return dict(n=len(r), win=round(100 * w.mean(), 1), R=round(r.mean(), 3), PF=round(r[w].sum() / -r[~w].sum(), 2),
                t_day=round(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))), 2) if len(dm) > 2 else np.nan, pct=round(100 * T.ret.mean(), 3))


def main():
    W = D.daily_panel(); mk = W["market"]["close"]
    Wk = D.weekly(W); del W
    el = Wk["elig"].astype(bool)
    to = Wk["value"].rolling(12, min_periods=8).median().shift(1).where(el)
    tor = to.rank(axis=1, pct=True)
    mkw = mk.resample("W-FRI").last().reindex(Wk["close"].index, method="ffill")
    up = (mkw > mkw.ewm(span=40, adjust=False).mean()).shift(1).fillna(False)
    rsi = {}
    res = {}
    for slip in (0.0005, 0.001, 0.002, 0.003):
        cost = 0.00393 - 2 * 0.0005 + 2 * slip
        P = E.Pool(); idx = Wk["close"].index
        for g, k in enumerate(Wk["close"].columns):
            ok = Wk["close"][k].notna().values
            if ok.sum() < 60:
                continue
            b = pd.DataFrame(dict(time=idx[ok], **{f: Wk[f][k].values[ok] for f in ("open", "high", "low", "close", "volume")}))
            for col in ("open", "high", "low"):
                b[col] = b[col].where(b[col] > 0).fillna(b["close"])
            c = b["close"].astype(float); h, l = b["high"].astype(float), b["low"].astype(float); pc = c.shift(1)
            atr = pd.Series(E.wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14))
            risk = (c - l.rolling(5).min() + 0.1 * atr).clip(lower=0.5 * atr, upper=3 * atr).values
            r = E.rsi_of(c)
            e = el[k].values[ok]; lr = tor[k].values[ok]
            sig = {}
            for lvl in (70, 75, 80):
                x = ((r >= lvl) & (r.shift(1) < lvl)).fillna(False).values & e
                sig[("C", f"rsi{lvl}", "liq_bottom_third", 1)] = x & (lr <= 1 / 3)
                sig[("C", f"rsi{lvl}", "liq_bottom_half", 1)] = x & (lr <= 1 / 2)
                sig[("C", f"rsi{lvl}", "all_eligible", 1)] = x
            sig[("C", "eligible", "any", 1)] = e
            P.add(b, sig, {1: risk, -1: risk}, g, np.full(len(b), cost), np.zeros(len(b), np.int64), str(Wk["symbol"][k]))
        P.freeze()
        T = P.run(("C", "rsi75", "liq_bottom_third", 1), 1.0, 10)
        res[f"slip_{100 * slip:.2f}%"] = s(T)
        if slip == 0.0005:
            T["year"] = pd.to_datetime(T.entry).dt.year
            T["market"] = np.where(up.reindex(pd.to_datetime(T.entry)).fillna(False).astype(bool).values, "market_up", "market_down")
            res["by_period"] = {k: s(g) for k, g in T.groupby(E.periods(T.entry.values, CUTS))}
            res["by_year"] = {int(k): s(g) for k, g in T.groupby("year")}
            res["by_market"] = {k: s(g) for k, g in T.groupby("market")}
            res["top10_stock_share"] = round(float(T.groupby("name").netR.sum().sort_values(ascending=False).head(10).clip(lower=0).sum() / T.netR[T.netR > 0].sum()), 3)
            nb = []
            for lvl in (70, 75, 80):
                for liq in ("liq_bottom_third", "liq_bottom_half", "all_eligible"):
                    for tg in (1.0, 2.0, 3.0):
                        X = P.run(("C", f"rsi{lvl}", liq, 1), tg, 10); lab = E.periods(X.entry.values, CUTS)
                        nb.append(dict(rsi=lvl, liquidity=liq, target_R=tg, **s(X), **{f"{p}_R": round(X.netR[lab == p].mean(), 3) for p, _ in CUTS}))
            res["neighbours"] = nb
            cand = P.idx[("C", "eligible", "any", 1)]; liq_ok = cand[np.isin(P.name[cand], T.name.unique())]
            means = []
            for _ in range(300):
                P.idx[("C", "placebo", "x", 1)] = np.sort(RNG.choice(liq_ok, size=int(len(T) * 1.2), replace=False))
                means.append(P.run(("C", "placebo", "x", 1), 1.0, 10).netR.mean())
            res["placebo"] = dict(real_R=round(T.netR.mean(), 3), placebo_mean_R=round(float(np.mean(means)), 3),
                                  placebo_p99=round(float(np.percentile(means, 99)), 3), share_at_or_above=round(float((np.array(means) >= T.netR.mean()).mean()), 4))
            T.drop(columns=["i"]).to_csv(OUT / "cash_check_trades.csv.gz", index=False, compression="gzip")
        print(slip, res[f"slip_{100 * slip:.2f}%"], flush=True)
    json.dump(res, open(OUT / "cash_check.json", "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in res.items() if k != "neighbours"}, indent=1, default=str))
    print(pd.DataFrame(res["neighbours"]).to_string(index=False))


if __name__ == "__main__":
    main()
