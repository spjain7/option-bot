"""INTRA-CLUE-001 – see REGISTRY_CLUE.md.  python -m research.search.clue_search"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research import instruments as INS  # noqa
from research.search import stock_check as SC, stock_search as SR, strategy_search as SS  # noqa
from research.search.intraday_search import prep  # noqa

D_END, V_END = pd.Timestamp("2024-01-01"), pd.Timestamp("2024-07-01")
OUT = ROOT / "research" / "search" / "results_clue"
EXITS = {"A": (1.0, 1.5), "B": (1.5, 0.75)}
K = 16


def patterns(o, h, l, c, p=""):
    rng = (h - l).replace(0, np.nan)
    body = (c - o).abs()
    up, lo = h - np.maximum(o, c), np.minimum(o, c) - l
    po, pc = o.shift(1), c.shift(1)
    f = {}
    f[p + "bull_engulf"] = (c > o) & (pc < po) & (c >= po) & (o <= pc)
    f[p + "bear_engulf"] = (c < o) & (pc > po) & (c <= po) & (o >= pc)
    f[p + "hammer"] = (lo >= 2 * body) & (up <= 0.3 * rng)
    f[p + "star"] = (up >= 2 * body) & (lo <= 0.3 * rng)
    f[p + "doji"] = body <= 0.1 * rng
    f[p + "bull_maru"] = (c > o) & (body >= 0.8 * rng)
    f[p + "bear_maru"] = (c < o) & (body >= 0.8 * rng)
    f[p + "inside"] = (h < h.shift(1)) & (l > l.shift(1))
    f[p + "nr4"] = rng <= rng.rolling(4).min()
    b2 = (c.shift(2) - o.shift(2))
    small1 = body.shift(1) <= 0.3 * rng.shift(1)
    f[p + "morning_star"] = (b2 < 0) & small1 & (c > o) & (c > (o.shift(2) + c.shift(2)) / 2)
    f[p + "evening_star"] = (b2 > 0) & small1 & (c < o) & (c < (o.shift(2) + c.shift(2)) / 2)
    f[p + "piercing"] = (pc < po) & (c > o) & (o < pc) & (c > (po + pc) / 2) & (c < po)
    f[p + "dark_cloud"] = (pc > po) & (c < o) & (o > pc) & (c < (po + pc) / 2) & (c > po)
    return pd.DataFrame({k: v.fillna(False).astype(int) for k, v in f.items()})


def features(h, oi):
    g = prep(h, oi)
    a = g["atr"]
    X = pd.DataFrame(index=g.index)
    X["trend"] = g["trend"]
    d = g.groupby("day").agg(o=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    d["e200"] = np.sign(d["close"] - I.ema(d["close"], 200)).shift(1)
    d["adx"] = I.adx(d, 14).shift(1)
    dp = patterns(d["o"], d["high"], d["low"], d["close"], "d_").shift(1).fillna(0)
    rngd = d["high"] - d["low"]
    dp["d_nr7"] = (rngd <= rngd.rolling(7).min()).shift(1).fillna(False).astype(int)
    dp.index = d.index
    X["e200"], X["adx_d"] = g["day"].map(d["e200"]), g["day"].map(d["adx"])
    X = X.join(dp.reindex(g["day"]).reset_index(drop=True))
    X["vs_vwap"] = (g["close"] - g["vwap"]) / a
    dh, dl = g.groupby("day")["high"].cummax(), g.groupby("day")["low"].cummin()
    X["day_pos"] = (g["close"] - dl) / (dh - dl).replace(0, np.nan)
    X["from_open"] = (g["close"] - g["o"]) / a
    X["vs_pdh"], X["vs_pdl"] = (g["close"] - g["ph"]) / a, (g["close"] - g["pl"]) / a
    X["gap"] = (g["o"] - g["pc"]) / a
    X["volx"] = g["volx"]
    v = g["volume"].astype(float)
    X["dayvol"] = (v.groupby(g["day"]).cumsum()) / (v.groupby(g["day"]).sum().rolling(10).mean().shift(1)).reindex(g["day"]).values
    X["rsi"], X["rsi_slope"] = g["rsi"], g["rsi"] - g["rsi"].shift(2)
    X["ema_fast"] = (I.ema(g["close"], 20) - I.ema(g["close"], 50)) / a
    X["candle_r"] = (g["high"] - g["low"]) / a
    X["body"] = (g["close"] - g["open"]) / a
    X["atrp"] = a / g["close"]
    X["atrp_rel"] = X["atrp"] / X["atrp"].rolling(200, min_periods=50).median()
    X = X.join(patterns(g["open"], g["high"], g["low"], g["close"]))
    if oi is not None:
        X["oi_lb"], X["oi_sb"] = g["lb_y"].astype(int), g["sb_y"].astype(int)
        X["doi_y"] = g["day"].map(g.groupby("day")["doi"].first().shift(1))
    else:
        X["oi_lb"] = X["oi_sb"] = 0
        X["doi_y"] = np.nan
    X["hour"] = g["k"]
    X["wday"] = g["time"].dt.weekday
    return g, X


def outcomes(g, sm, tm):
    """R for long and short entered at the next open, same-day exit (stop first inside a candle)."""
    n = len(g)
    day = g["day"].values
    O, H, L, C, A = (g[c].values for c in ("open", "high", "low", "close", "atr"))
    idx = np.arange(n)[:, None] + 1 + np.arange(K)[None, :]
    valid = idx < n
    idx = np.minimum(idx, n - 1)
    valid &= day[idx] == day[:, None]
    e0 = np.where(valid[:, 0], O[idx[:, 0]], np.nan)
    last = np.array(pd.Series(C).groupby(day).transform("last"))
    res = {}
    for s in (1, -1):
        st = e0 - s * sm * A
        tp = e0 + s * tm * A
        Hh, Ll, Oo = np.where(valid, H[idx], np.nan), np.where(valid, L[idx], np.nan), O[idx]
        hs = (Ll <= st[:, None]) if s > 0 else (Hh >= st[:, None])
        ht = (Hh >= tp[:, None]) if s > 0 else (Ll <= tp[:, None])
        ks = np.where(hs.any(1), hs.argmax(1), 999)
        kt = np.where(ht.any(1), ht.argmax(1), 999)
        so = Oo[np.arange(n), np.minimum(ks, K - 1)]
        sfill = np.minimum(so, st) if s > 0 else np.maximum(so, st)
        pnl = np.where((ks == 999) & (kt == 999), s * (last - e0),
                       np.where(ks <= kt, s * (sfill - e0), tm * A))
        res[s] = pnl
    return e0, res


def build(items, kind):
    parts = []
    for name, h, lot, oi in items:
        g, X = features(h, oi)
        X["name"], X["time"], X["day"] = name, g["time"], g["day"]
        X["ok"] = (g["k"] >= 1).values
        for ex, (sm, tm) in EXITS.items():
            e0, res = outcomes(g, sm, tm)
            cp = SC.cost_frac(e0, lot) if kind == "STOCKS" else np.array([INS.cost_points(name, x) if x == x else np.nan for x in e0])
            R = sm * g["atr"].values
            for s, lab in ((1, "L"), (-1, "S")):
                X[f"r_{ex}{lab}"] = (res[s] - cp) / R
                X[f"r2_{ex}{lab}"] = (res[s] - 2 * cp) / R
        X = X[X["ok"] & X["r_AL"].notna() & g["atr"].notna().values]
        parts.append(X)
        print(kind, name, len(X), flush=True)
    return pd.concat(parts, ignore_index=True)


FEATS = None


def clue_table(T, ex):
    D = T[T["time"] < D_END]
    rows = []
    bin_cols = [c for c in T.columns if T[c].dropna().isin([0, 1]).all() and c not in ("ok",) and not c.startswith("r")]
    for side in ("L", "S"):
        r = D[f"r_{ex}{side}"]
        base = dict(win=(r > 0).mean() * 100, exp=r.mean())
        for c in bin_cols:
            m = D[c] == 1
            if m.sum() < 300:
                continue
            rr = r[m]
            rows.append(dict(side=side, clue=c, n=int(m.sum()), win=round((rr > 0).mean() * 100, 1), exp=round(rr.mean(), 3),
                             lift=round((rr > 0).mean() * 100 - base["win"], 1)))
        rows.append(dict(side=side, clue="BASE", n=len(r), win=round(base["win"], 1), exp=round(base["exp"], 3), lift=0))
    return pd.DataFrame(rows).sort_values(["side", "exp"], ascending=[True, False])


def model(T, ex, label):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.tree import DecisionTreeClassifier, export_text
    feats = [c for c in T.columns if c not in ("name", "time", "day", "ok") and not c.startswith("r_") and not c.startswith("r2_")]
    out = {}
    for side in ("L", "S"):
        y = (T[f"r_{ex}{side}"] > 0).astype(int)
        D, V, Hm = T["time"] < D_END, (T["time"] >= D_END) & (T["time"] < V_END), T["time"] >= V_END
        feats = [c for c in feats if T.loc[D, c].nunique(dropna=True) > 1]
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200,
                                             l2_regularization=1.0, random_state=7)
        clf.fit(T.loc[D, feats], y[D])
        p = pd.Series(clf.predict_proba(T[feats])[:, 1], index=T.index)
        best = None
        for q in (0.90, 0.95, 0.98):
            thr = float(p[D].quantile(q))
            pick = first_per_day(T[V & (p >= thr)])
            r = pick[f"r_{ex}{side}"]
            sc = r.mean() if len(r) >= 30 else -9
            if best is None or sc > best[0]:
                best = (sc, q, thr)
        _, q, thr = best
        res = {}
        for nm, m in (("design", D), ("valid", V), ("holdout", Hm)):
            pick = first_per_day(T[m & (p >= thr)])
            st = SR.stats(pick[f"r_{ex}{side}"])
            st["exp_2x"] = round(float(pick[f"r2_{ex}{side}"].mean()), 3) if len(pick) else None
            res[nm] = st
        h = res["holdout"]
        res["PASS"] = bool(h.get("trades", 0) >= 100 and h["exp_r"] > 0 and (h["exp_2x"] or -1) > 0)
        res["top_q"] = q
        tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=500, random_state=7).fit(T.loc[D, feats].fillna(-99), y[D])
        res["rules"] = export_text(tree, feature_names=feats, show_weights=True)
        out[f"{label}|{ex}|{'LONG' if side == 'L' else 'SHORT'}"] = res
        print(label, ex, side, "q", q, {k: res[k] for k in ("design", "valid", "holdout")}, "PASS" if res["PASS"] else "", flush=True)
    return out


def first_per_day(P):
    return P.sort_values("time").groupby(["name", "day"]).head(1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    stocks = []
    for r in man.itertuples():
        f, fo = SR.DATA / f"{r.name}_ONE_HOUR.csv", SR.DATA / f"{r.name}_OI_ONE_DAY.csv"
        if f.exists():
            h = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
            stocks.append((r.name, h, r.lot, pd.read_csv(fo) if fo.exists() else None))
    idx = [(n, SS.load("NFO", n, "ONE_HOUR"), None, None) for n in ("NIFTY", "BANKNIFTY")]
    mcx = [(n, SS.load("MCX", n, "ONE_HOUR"), None, None) for n in ("CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM")]
    res = {}
    for label, items in (("INDEX", idx), ("MCX", mcx), ("STOCKS", stocks)):
        T = build([x for x in items if x[1] is not None], label)
        T.to_pickle(OUT / f"table_{label}.pkl")
        for ex in EXITS:
            ct = clue_table(T, ex)
            ct.to_csv(OUT / f"clues_{label}_{ex}.csv", index=False)
            print(label, ex, "TOP CLUES\n", ct.groupby("side").head(6).to_string(index=False), flush=True)
            res.update(model(T, ex, label))
        (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
