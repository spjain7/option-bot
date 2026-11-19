"""RSIDIV-SF-CHECK – stress test of the only stock-futures result that survived the 11-Nov multiple-testing control:
SELL the stock future at the next open when, within the last 10 sessions, daily RSI(14) was <= 25 and today's close is
above the prior 5-session high ("short the first bounce after an oversold fall"). Stop 0.1 ATR beyond the 5-session high
(0.5–3 ATR), target 3R, max 15 sessions. NOT a search – the rule is fixed; neighbours are shown, nothing is picked.
Checks: per year · without Mar–Apr 2020 · market regime (EW market above / below its EMA200) · per sector ·
slippage 0.03 → 0.10 % per side · neighbours RSI 20 / 25 / 30 × look-back 5 / 10 / 15 × break 3 / 5 / 10 ·
placebo: the same number of SELL entries at random F&O stock-days (300 draws).      python -m research.rsidiv.sf_check"""
import json
import pickle
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E, stockfut as SF  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
RNG = np.random.default_rng(5)


def load():
    A = pickle.loads(SF.CM_PKL.read_bytes())
    F = SF.fut_daily(SF.fut_rows("STK"))
    sk = pd.concat([pd.DataFrame(dict(date=a["time"], symbol=a["symbol"].astype(str), key=k)) for k, a in A.items()], ignore_index=True)
    F = F.merge(sk, on=["date", "symbol"], how="inner")
    out = []
    for key, f in F.groupby("key"):
        a = A[key].copy(); a["time"] = pd.to_datetime(a["time"]); a = a[a["time"] >= "2016-01-01"].reset_index(drop=True)
        j = a.set_index("time"); f = f.set_index("date")
        to60 = j["value"].rolling(60, min_periods=40).median().shift(1)
        live = j.index.isin(f.index) & (to60 >= 25e7).values & (j["close"] >= 50).values
        b = a[["time", "open", "high", "low", "close", "volume"]].copy(); b["live"] = live
        b["exp"] = f["expiry"].reindex(j.index).values; b["name"] = str(a["symbol"].iloc[-1])
        if live.any() and len(b) > 300:
            out.append(b)
    return out


def rule(b, lvl=25, look=10, brk=5):
    h, l, c = (b[x].astype(float).reset_index(drop=True) for x in ("high", "low", "close"))
    r = E.rsi_of(c)
    was = (r <= lvl).rolling(look).max() > 0
    return (was & (c > h.shift(1).rolling(brk).max())).fillna(False).values & b["live"].values


def pool_of(stocks, lvl=25, look=10, brk=5, slip=0.0003):
    P = E.Pool(); imap = dict(pd.read_csv(ROOT / "research/data/angel/NSE_EQ/universe.csv")[["symbol", "industry"]].fillna("").values)
    for g, b in enumerate(stocks):
        h, l, c = (b[x].astype(float).reset_index(drop=True) for x in ("high", "low", "close"))
        pc = c.shift(1); atr = pd.Series(E.wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14))
        risk = (h.rolling(5).max() - c + 0.1 * atr).clip(lower=0.5 * atr, upper=3 * atr).values
        e = pd.Series(b["exp"]).astype("datetime64[ns]")
        expid = np.where(e.notna(), e.values.astype("datetime64[D]").astype(np.int64), -1)
        P.add(b, {("R", "rule", "none", -1): rule(b, lvl, look, brk), ("R", "live", "none", -1): b["live"].values}, {1: risk, -1: risk}, g,
              SF.fut_cost(b["time"].values, slip=slip), expid, b["name"].iloc[0])
    P.freeze(); P.sector = np.array([imap.get(n, "") for n in P.name])
    return P


def s(T):
    r = T.netR.values
    if len(r) < 5:
        return dict(n=len(r))
    dm = T.groupby(pd.to_datetime(T.entry).dt.normalize()).netR.mean()
    w = r > 0
    return dict(n=len(r), win=round(100 * w.mean(), 1), R=round(r.mean(), 3), PF=round(r[w].sum() / -r[~w].sum(), 2),
                t_day=round(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))), 2) if len(dm) > 2 else np.nan, pct=round(100 * T.ret.mean(), 3))


def main():
    stocks = load()
    P = pool_of(stocks)
    T = P.run(("R", "rule", "none", -1), 3.0, 15)
    T["year"] = pd.to_datetime(T.entry).dt.year; T["sector"] = P.sector[T.i.values]
    # market regime: equal-weight F&O market from the same stocks
    cl = pd.concat([b.set_index("time")["close"].rename(k) for k, b in enumerate(stocks)], axis=1)
    mk = cl.pct_change(fill_method=None).mean(axis=1).fillna(0).add(1).cumprod(); ema = mk.ewm(span=200, adjust=False).mean()
    up = (mk > ema).shift(1)
    T["market"] = np.where(pd.to_datetime(T.entry).dt.normalize().map(up).fillna(False).astype(bool), "market_up", "market_down")
    R = dict(rule="SELL next open: RSI(14) <= 25 within 10 sessions and close > prior 5-session high; stop 5-session high + 0.1 ATR; 3R; 15 sessions",
             all=s(T), by_period={k: s(g) for k, g in T.groupby(E.periods(T.entry.values, SF.CUTS))},
             by_year={int(k): s(g) for k, g in T.groupby("year")},
             without_mar_apr_2020=s(T[~((pd.to_datetime(T.entry) >= "2020-03-01") & (pd.to_datetime(T.entry) < "2020-05-01"))]),
             by_market=({k: s(g) for k, g in T.groupby("market")}),
             by_sector={k or "unknown": s(g) for k, g in T.groupby("sector")},
             top10_stock_share=round(float(T.groupby("name").netR.sum().sort_values(ascending=False).head(10).clip(lower=0).sum() / max(T.netR[T.netR > 0].sum(), 1e-9)), 3))
    R["slippage"] = {}
    for sl in (0.0005, 0.001):
        R["slippage"][f"{100 * sl:.2f}%/side"] = s(pool_of(stocks, slip=sl).run(("R", "rule", "none", -1), 3.0, 15))
    nb = []
    for lvl in (20, 25, 30):
        for look in (5, 10, 15):
            for brk in (3, 5, 10):
                X = pool_of(stocks, lvl, look, brk).run(("R", "rule", "none", -1), 3.0, 15)
                lab = E.periods(X.entry.values, SF.CUTS)
                nb.append(dict(rsi=lvl, lookback=look, brk=brk, **s(X), **{f"{p}_R": round(X.netR[lab == p].mean(), 3) for p, _ in SF.CUTS}))
    R["neighbours"] = nb
    live_idx = P.idx[("R", "live", "none", -1)]; per = T.groupby("name").size(); means = []
    for _ in range(300):
        pick = []
        for nm, cnt in per.items():
            cand = live_idx[P.name[live_idx] == nm]
            pick.append(RNG.choice(cand, size=min(len(cand), int(cnt * 1.2)), replace=False))
        P.idx[("R", "placebo", "none", -1)] = np.sort(np.concatenate(pick))
        means.append(P.run(("R", "placebo", "none", -1), 3.0, 15).netR.mean())
    means = np.array(means)
    R["placebo"] = dict(real_R=R["all"]["R"], placebo_mean_R=round(means.mean(), 3), placebo_p99=round(np.percentile(means, 99), 3),
                        share_at_or_above_real=round(float((means >= R["all"]["R"]).mean()), 4))
    T.drop(columns=["i"]).to_csv(OUT / "sf_check_trades.csv.gz", index=False, compression="gzip")
    json.dump(R, open(OUT / "sf_check.json", "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in R.items() if k != "neighbours"}, indent=1, default=str))
    print(pd.DataFrame(nb).to_string(index=False))


if __name__ == "__main__":
    main()
