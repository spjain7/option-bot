"""STOCK-SEARCH-001 – see REGISTRY_STOCKS.md.  python -m research.search.stock_search"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from alerts import breakout as BO, stocks as STK  # noqa
from research.search import stock_check as SC, strategy_search as SS  # noqa

DATA = ROOT / "research" / "data" / "angel" / "NFO_STK"
OUT = ROOT / "research" / "search" / "results_stocksearch"
SPLIT = pd.Timestamp("2024-07-01")
STRATS = ["rsi2_long", "rsi2_both", "pullback_trend", "bb_long", "high250_vol", "vb_market", "vb_rs", "gap_go", "nr7_trend"]


def daily(h):
    h = h[h["time"].dt.hour >= 9]
    g = h.groupby(h["time"].dt.normalize())
    d = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum")).reset_index()
    return d.rename(columns={"time": "time"}).rename(columns={d.columns[0]: "time"})


def nifty_daily():
    h = SS.load("NFO", "NIFTY", "ONE_HOUR")
    d = daily(h)
    d["e50"] = I.ema(d["close"], 50)
    d["ret63"] = d["close"].pct_change(63)
    return d.set_index("time")


def plan(strat, df, nf):
    """Returns entry signal array (+1/-1/0), exit-signal function, stop ATR, target R (None = trail/exit signal), trail ATR."""
    c, h, l, o, v = df["close"], df["high"], df["low"], df["open"], df["volume"].astype(float)
    e200, e50, e5 = I.ema(c, 200), I.ema(c, 50), I.ema(c, 5)
    sig = pd.Series(0, index=df.index)
    if strat in ("rsi2_long", "rsi2_both"):
        r2 = I.rsi(c, 2)
        sig[(r2 < 10) & (c > e200)] = 1
        if strat == "rsi2_both":
            sig[(r2 > 90) & (c < e200)] = -1
        return sig.values, lambda i, s: (c.iat[i] > e5.iat[i]) if s > 0 else (c.iat[i] < e5.iat[i]), 2.5, None, None, 10
    if strat == "pullback_trend":
        r = I.rsi(c, 14)
        sig[(c > e50) & (e50 > e200) & (r > 40) & (r.shift(1) <= 40)] = 1
        sig[(c < e50) & (e50 < e200) & (r < 60) & (r.shift(1) >= 60)] = -1
        return sig.values, lambda i, s: (c.iat[i] < e50.iat[i]) if s > 0 else (c.iat[i] > e50.iat[i]), 2.0, 3.0, None, 30
    if strat == "bb_long":
        m, sd = c.rolling(20).mean(), c.rolling(20).std()
        sig[(c < m - 2 * sd) & (c > e200)] = 1
        return sig.values, lambda i, s: c.iat[i] > m.iat[i], 2.0, None, None, 15
    va = v.rolling(20).mean().shift(1)
    if strat == "high250_vol":
        sig[(c > h.shift(1).rolling(250).max()) & (v > 1.5 * va)] = 1
        return sig.values, None, 2.0, None, 3.0, 40
    if strat in ("vb_market", "vb_rs"):
        mk = nf.reindex(df["time"].values)
        up_mkt, dn_mkt = (mk["close"] > mk["e50"]).values, (mk["close"] < mk["e50"]).values
        hh, ll = h.shift(1).rolling(20).max(), l.shift(1).rolling(20).min()
        b = (c > hh) & (v > 1.5 * va) & (c > e200) & up_mkt
        s = (c < ll) & (v > 1.5 * va) & (c < e200) & dn_mkt
        if strat == "vb_rs":
            rs = c.pct_change(63).values - mk["ret63"].values
            b &= rs > 0; s &= rs < 0
        sig[b] = 1; sig[s] = -1
        return sig.values, None, 2.0, None, 3.0, 40
    if strat == "gap_go":
        pos = (c - l) / (h - l).replace(0, np.nan)
        sig[(o > c.shift(1) * 1.01) & (pos > 0.75)] = 1
        sig[(o < c.shift(1) * 0.99) & (pos < 0.25)] = -1
        return sig.values, None, 1.5, 2.0, None, 10
    if strat == "nr7_trend":
        rng = h - l
        nr7 = (rng <= rng.rolling(7).min()).shift(1).fillna(False).astype(bool)
        sig[nr7 & (c > h.shift(1)) & (c > e50)] = 1
        sig[nr7 & (c < l.shift(1)) & (c < e50)] = -1
        return sig.values, None, 1.5, 2.0, None, 10
    raise ValueError(strat)


def run(df, lot, roll, strat, nf):
    sig, ex, sk, tg, tr, mx = plan(strat, df, nf)
    a = I.atr(df, 14).values
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    day = df["time"].values
    rd = pd.Series(df["time"]).isin(roll).values
    nx = np.r_[rd[1:], False]
    out, pos = [], None
    for i in range(210, len(df) - 1):
        if pos is not None:
            s, e0, st, risk, k0, best, tp = pos
            px = None
            if (o[i] <= st) if s > 0 else (o[i] >= st):
                px = o[i]
            elif (l[i] <= st) if s > 0 else (h[i] >= st):
                px = st
            elif tp is not None and ((h[i] >= tp) if s > 0 else (l[i] <= tp)):
                px = tp
            elif nx[i] or i - k0 >= mx or (ex is not None and ex(i, s)):
                px = c[i] if nx[i] else o[i + 1]
            if px is not None:
                out.append((day[k0], s, s * (px - e0), SC.cost_frac(e0, lot), risk))
                pos = None
            else:
                if tr:
                    best = max(best, c[i]) if s > 0 else min(best, c[i])
                    ns = best - s * tr * a[i]
                    if s * (ns - st) > 0:
                        st = ns
                pos = (s, e0, st, risk, k0, best, tp)
            continue
        if sig[i] == 0 or rd[i] or nx[i] or not a[i] > 0:
            continue
        s = int(sig[i]); e0 = o[i + 1]; risk = sk * a[i]
        pos = (s, e0, e0 - s * risk, risk, i + 1, e0, e0 + s * tg * risk if tg else None)
    return out


def stats(r, rng=np.random.default_rng(7)):
    r = np.asarray(r, float)
    if len(r) == 0:
        return dict(trades=0)
    w, l = r[r > 0], r[r <= 0]
    p5 = float(np.percentile(rng.choice(r, (3000, len(r))).mean(axis=1), 5))
    return dict(trades=int(len(r)), exp_r=round(float(r.mean()), 3), win=round(float((r > 0).mean() * 100), 1),
                pf=round(float(w.sum() / -l.sum()), 2) if l.sum() < 0 else None, p5=round(p5, 3))


def momentum(dailies, nf):
    """S10: weekly top-10 by 126-day return (above EMA200), equal weight, long futures; costs on turnover."""
    closes = pd.DataFrame({n: d.set_index("time")["close"] for n, d in dailies.items()}).sort_index()
    rets = closes.pct_change()
    mom = closes.pct_change(126)
    above = closes > closes.apply(lambda s: I.ema(s.dropna(), 200)).reindex(closes.index)
    fridays = closes.index[closes.index.to_series().dt.weekday == 4]
    hold, rows, prev = [], [], set()
    for k, t in enumerate(closes.index):
        if hold:
            r = rets.loc[t, hold].mean()
            bench = rets.loc[t].mean()
            rows.append((t, r, bench))
        if t in fridays:
            m = mom.loc[t][above.loc[t].fillna(False)].dropna()
            new = list(m.sort_values(ascending=False).index[:10])
            turnover = len(set(new) ^ prev) / 20 if prev else 0.5
            if rows:
                rows[-1] = (rows[-1][0], rows[-1][1] - turnover * 2 * 0.0008, rows[-1][2])
            hold, prev = new, set(new)
    R = pd.DataFrame(rows, columns=["time", "strat", "bench"]).set_index("time")
    out = {}
    for lbl, g in (("design", R[R.index < SPLIT]), ("holdout", R[R.index >= SPLIT])):
        ann = lambda x: float((1 + x).prod() ** (252 / max(1, len(x))) - 1)
        sh = lambda x: float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0
        eq = (1 + g["strat"]).cumprod()
        out[lbl] = dict(days=len(g), strat_ann=round(ann(g["strat"]) * 100, 1), bench_ann=round(ann(g["bench"]) * 100, 1),
                        strat_sharpe=round(sh(g["strat"]), 2), bench_sharpe=round(sh(g["bench"]), 2),
                        max_dd=round(float((eq / eq.cummax() - 1).min() * 100), 1))
    ho = out["holdout"]
    out["PASS"] = bool(ho["strat_ann"] > ho["bench_ann"] and ho["strat_sharpe"] > ho["bench_sharpe"])
    return out


def main():
    nf = nifty_daily()
    man = pd.read_csv(DATA / "manifest_stocks.csv")
    rows, dailies = [], {}
    for r in man.itertuples():
        f = DATA / f"{r.name}_ONE_HOUR.csv"
        if not f.exists():
            continue
        h = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
        d = daily(h).reset_index(drop=True)
        if len(d) < 260:
            continue
        dailies[r.name] = d
        days = pd.Series(d["time"])
        roll = set()
        for y in range(days.min().year, days.max().year + 1):
            for m in range(1, 13):
                e = STK.nfo_expiry(y, m)
                nxt = days[days > e]
                if len(nxt):
                    roll.add(nxt.iloc[0])
        for strat in STRATS:
            for t0, s, g, cp, risk in run(d, r.lot, roll, strat, nf):
                rows.append((r.name, strat, pd.Timestamp(t0), s, (g - cp) / risk, (g - 2 * cp) / risk))
    T = pd.DataFrame(rows, columns=["name", "strat", "time", "side", "r1", "r2"])
    T["period"] = np.where(T["time"] < SPLIT, "design", "holdout")
    res = {}
    for strat, g in T.groupby("strat"):
        d, ho = g[g["period"] == "design"], g[g["period"] == "holdout"]
        sd = stats(d["r1"])
        short = (sd.get("trades", 0) >= 100 and sd["exp_r"] >= 0.10 and (sd["pf"] or 0) >= 1.2 and sd["p5"] > 0 and d["r2"].mean() > 0)
        row = dict(design=sd, design_2x=round(float(d["r2"].mean()), 3), shortlisted=bool(short),
                   design_by_side={("long" if k > 0 else "short"): stats(x["r1"]) for k, x in d.groupby("side")})
        if short:
            sh = stats(ho["r1"])
            row.update(holdout=sh, holdout_2x=round(float(ho["r2"].mean()), 3),
                       holdout_by_year={int(k): round(float(x["r1"].mean()), 3) for k, x in ho.groupby(ho["time"].dt.year)},
                       PASS=bool(sh["trades"] >= 100 and sh["exp_r"] >= 0.05 and (sh["pf"] or 0) >= 1.1 and ho["r2"].mean() > 0))
        res[strat] = row
        print(strat, json.dumps(row, default=str), flush=True)
    res["momentum_top10"] = momentum(dailies, nf)
    print("momentum_top10", json.dumps(res["momentum_top10"]), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))
    T.to_csv(OUT / "trades.csv.gz", index=False)


if __name__ == "__main__":
    main()
