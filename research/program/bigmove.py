"""BIGMOVE-001 (29-Oct-2026, owner: "every big move leaves a footprint before it – find it").
Question 1: which footprints at day t's close make a BIG move on day t+1 more likely (vs the base rate)?
Question 2: do they also tell the DIRECTION?
Question 3: walk-forward – trained on 2022-07…2024-12, tested on 2025-01…2026-10, how well can a model rank tomorrow's big movers?

Data: NSE F&O bhavcopy (real, end of day) Jul-2022 → Oct-2026, ~180 stocks: near-month futures OHLC / contracts / OI and the
options chain (ATM implied volatility from real option closes, put-call OI ratio).
Big move (t+1): |close(t+1)/close(t) − 1| ≥ 2 × the stock's 20-day average absolute daily move  (≈ top 5 % of days)
  also 'gap' big move: |open(t+1)/close(t) − 1| ≥ 1.5 × that average.
Footprints (all known at the close of t): range compression (ATR5/ATR20), NR7, inside day, volume dry-up / spike (contracts vs 20d),
OI change 1d / 5d and buildup label, ATM IV, IV rank (60d), IV change 1d / 5d, IV ÷ HV20, PCR and its change, distance to the
20-day high / low, 5-day return, close location in the day's range, day of week, days to expiry.
python research/program/bigmove.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from greeks import implied_vol  # noqa: E402

DAYS = ROOT / "research/data/nse_opt/days"
OUT = ROOT / "research/program/results"


def one_day(p):
    d = pd.read_csv(p, parse_dates=["date", "expiry"])
    day = d["date"].iat[0]
    fut = d[d["kind"] == "FUT"].set_index("symbol")
    rows = []
    for sym, g in d[d["kind"] != "FUT"].groupby("symbol"):
        if sym not in fut.index:
            continue
        f = fut.loc[sym]
        F = float(f["close"])
        g = g[g["expiry"] >= day + pd.Timedelta(days=5)]
        if g.empty or F <= 0:
            continue
        e = g["expiry"].min(); g = g[g["expiry"] == e]
        T = max((e - day).days, 1) / 365
        ivs = []
        for typ in ("CE", "PE"):
            x = g[(g["kind"] == typ) & (g["close"] > 0)]
            if x.empty:
                continue
            r = x.iloc[(x["strike"] - F).abs().argsort().iloc[0]]
            iv = implied_vol(float(r["close"]), F, float(r["strike"]), T, 0.065, typ)
            if iv and 0.03 < iv < 3:
                ivs.append(iv)
        ce_oi, pe_oi = g.loc[g["kind"] == "CE", "oi"].sum(), g.loc[g["kind"] == "PE", "oi"].sum()
        rows.append(dict(date=day, symbol=sym, open=f["open"], high=f["high"], low=f["low"], close=F, contracts=f["contracts"],
                         oi=f["oi"], fexp=f["expiry"], iv=np.mean(ivs) if ivs else np.nan, pcr=pe_oi / ce_oi if ce_oi > 0 else np.nan))
    return rows


def panel():
    cache = OUT / "bigmove_panel.csv.gz"
    if cache.exists():
        return pd.read_csv(cache, parse_dates=["date", "fexp"])
    fs = sorted(DAYS.glob("*.csv"))
    with Pool(3) as pool:
        rows = [r for x in pool.imap(one_day, fs, chunksize=8) for r in x]
    P = pd.DataFrame(rows).sort_values(["symbol", "date"]).reset_index(drop=True)
    P.to_csv(cache, index=False)
    return P


def features(P):
    out = []
    for sym, g in P.groupby("symbol"):
        g = g.sort_values("date").reset_index(drop=True)
        if len(g) < 120:
            continue
        c, h, l, o = g["close"], g["high"], g["low"], g["open"]
        roll = g["fexp"] != g["fexp"].shift(1)                       # contract change -> OI / returns jump
        ret = c.pct_change().where(~roll)
        g["absmv20"] = ret.abs().rolling(20, min_periods=15).mean()
        g["ret_next"] = ret.shift(-1)
        g["gap_next"] = (o.shift(-1) / c - 1).where(~roll.shift(-1, fill_value=False))
        g["big"] = (g["ret_next"].abs() >= 2 * g["absmv20"]).astype(float).where(g["ret_next"].notna())
        g["big_gap"] = (g["gap_next"].abs() >= 1.5 * g["absmv20"]).astype(float).where(g["gap_next"].notna())
        g["up_next"] = (g["ret_next"] > 0).astype(float).where(g["ret_next"].notna())
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        g["comp"] = tr.rolling(5).mean() / tr.rolling(20).mean()
        rng = h - l
        g["nr7"] = (rng <= rng.rolling(7).min()).astype(int)
        g["inside"] = ((h <= h.shift()) & (l >= l.shift())).astype(int)
        g["volx"] = g["contracts"] / g["contracts"].rolling(20).mean().shift(1)
        oic = g["oi"].pct_change().where(~roll)
        g["oi1"] = oic
        g["oi5"] = (g["oi"] / g["oi"].shift(5) - 1).where(~roll.rolling(5).max().astype(bool))
        g["buildup"] = np.select([(ret > 0) & (oic > 0), (ret < 0) & (oic > 0), (ret > 0) & (oic < 0), (ret < 0) & (oic < 0)],
                                 ["LB", "SB", "SC", "LU"], "NA")
        g["ret1"], g["ret5"] = ret, c / c.shift(5) - 1
        g["iv_rank"] = (g["iv"] - g["iv"].rolling(60, min_periods=30).min()) / (g["iv"].rolling(60, min_periods=30).max() - g["iv"].rolling(60, min_periods=30).min())
        g["iv1"], g["iv5"] = g["iv"] / g["iv"].shift(1) - 1, g["iv"] / g["iv"].shift(5) - 1
        hv = ret.rolling(20, min_periods=15).std() * np.sqrt(252)
        g["iv_hv"] = g["iv"] / hv
        g["pcr1"] = g["pcr"] - g["pcr"].shift(1)
        g["d_hi20"] = (h.rolling(20).max() - c) / (g["absmv20"] * c)
        g["d_lo20"] = (c - l.rolling(20).min()) / (g["absmv20"] * c)
        g["clv"] = ((c - l) / rng.replace(0, np.nan))
        g["dow"] = g["date"].dt.dayofweek
        g["dte"] = (g["fexp"] - g["date"]).dt.days
        out.append(g)
    return pd.concat(out, ignore_index=True)


FEATS = ["comp", "nr7", "inside", "volx", "oi1", "oi5", "iv", "iv_rank", "iv1", "iv5", "iv_hv", "pcr", "pcr1", "d_hi20", "d_lo20",
         "ret1", "ret5", "clv", "dow", "dte"]


def lift_table(X, target="big"):
    base = X[target].mean()
    rows = []
    for f in FEATS:
        x = X[[f, target, "up_next"]].dropna()
        if x[f].nunique() <= 7:
            groups = x.groupby(f)
        else:
            groups = x.groupby(pd.qcut(x[f], 10, duplicates="drop"), observed=True)
        for k, gg in groups:
            if len(gg) < 300:
                continue
            bigs = gg[gg[target] == 1]
            rows.append(dict(feature=f, bucket=str(k), n=len(gg), p_big=gg[target].mean(), lift=gg[target].mean() / base,
                             up_share_of_big=bigs["up_next"].mean() if len(bigs) else np.nan))
    return pd.DataFrame(rows), base


def main():
    P = panel()
    X = features(P)
    X = X[X["absmv20"].notna() & X["big"].notna()]
    X.to_csv(OUT / "bigmove_features.csv.gz", index=False)
    print(f"stock-days {len(X):,} · stocks {X['symbol'].nunique()} · {X['date'].min():%Y-%m-%d} → {X['date'].max():%Y-%m-%d}")
    L, base = lift_table(X)
    print(f"\nbase rate: big move next day = {base * 100:.1f} % of stock-days\n")
    L = L.sort_values("lift", ascending=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
    print("strongest footprints (lift = how many times more likely than normal; up_share = % of those big moves that went UP):")
    print(L.head(25).round(3).to_string(index=False))
    print("\nweakest buckets (big move LESS likely):")
    print(L.tail(8).round(3).to_string(index=False))
    # buildup label
    b = X.groupby("buildup").agg(n=("big", "size"), p_big=("big", "mean"), up_next=("up_next", "mean"))
    print("\nOI buildup today -> tomorrow:"); print(b.round(3).to_string())
    # walk-forward model
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    tr = X[X["date"] < "2025-01-01"]; te = X[X["date"] >= "2025-01-01"]
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0)
    m.fit(tr[FEATS], tr["big"])
    pt = m.predict_proba(te[FEATS])[:, 1]
    te = te.assign(p=pt)
    auc = roc_auc_score(te["big"], pt)
    top = te.sort_values("p", ascending=False).groupby("date").head(5)
    print(f"\nWALK-FORWARD (train 2022-07…2024-12, test 2025-01…2026-10): AUC {auc:.3f} (0.5 = guessing, 1 = perfect)")
    print(f"  each day's top-5 predicted stocks: big move next day {top['big'].mean() * 100:.1f} % (base {te['big'].mean() * 100:.1f} %),"
          f" lift {top['big'].mean() / te['big'].mean():.2f}×")
    dec = te.groupby(pd.qcut(te["p"], 10, labels=False, duplicates="drop"))["big"].mean() * 100
    print("  big-move % by predicted decile (low→high):", " ".join(f"{v:.1f}" for v in dec.values))
    # direction model on big-move days
    td, sd = tr[tr["big"] == 1], te[te["big"] == 1]
    md = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0)
    md.fit(td[FEATS], td["up_next"])
    pdir = md.predict_proba(sd[FEATS])[:, 1]
    acc = ((pdir > 0.5) == (sd["up_next"] == 1)).mean()
    print(f"\nDIRECTION of big moves (test): accuracy {acc * 100:.1f} % (always guessing the majority side: "
          f"{max(sd['up_next'].mean(), 1 - sd['up_next'].mean()) * 100:.1f} %), AUC {roc_auc_score(sd['up_next'], pdir):.3f}")
    conf = sd.assign(p=pdir)
    hi = conf[(conf["p"] > 0.6) | (conf["p"] < 0.4)]
    print(f"  only confident calls (p > 0.6 or < 0.4): {len(hi)} of {len(sd)}, accuracy {((hi['p'] > 0.5) == (hi['up_next'] == 1)).mean() * 100:.1f} %")
    imp = pd.Series(dict(zip(FEATS, [0] * len(FEATS))))
    try:
        from sklearn.inspection import permutation_importance
        pi = permutation_importance(m, te[FEATS].iloc[:40000], te["big"].iloc[:40000], n_repeats=3, random_state=1, scoring="roc_auc")
        imp = pd.Series(pi.importances_mean, index=FEATS).sort_values(ascending=False)
    except Exception:
        pass
    print("\nwhat the big-move model uses most (AUC drop when the feature is shuffled):")
    print(" · ".join(f"{k} {v:.3f}" for k, v in imp.head(10).items()))
    L.to_csv(OUT / "bigmove_lift.csv", index=False)


if __name__ == "__main__":
    main()
