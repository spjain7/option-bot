"""TREND-002 + PAIRS-001 (4-Nov-2026) – ideas from pysystemtrade / PyTrendFollow (multi-speed trend) and pairs trading.

Data: MCX 7 daily, back-adjusted stitched front month 2006 -> Oct-2026 (+ NIFTY / BANKNIFTY for comparison).
Carry (near vs next contract) is NOT testable: only the current contracts' history exists for the 2nd month.

A. EWMAC trend (Carver): forecasts for EMA pairs (8,32) (16,64) (32,128) (64,256), raw = (fast - slow) / price-vol,
   fixed scalars 5.3 / 3.75 / 2.65 / 1.87, capped ±20, averaged (x1.1 diversification).
   A1 continuous system: position = forecast / 10 / annualised vol (vol-targeted), costs 0.03 % per unit turnover -> Sharpe.
   A2 CALL version (what the bot would send): BUY when the forecast crosses above +E (SELL below -E), exit when it falls back
       through 0 OR a trailing stop of K x ATR20 from the best close is hit (next open). E = 5 / 10, K = 3 / 4.
B. Pairs: log(A / B) z-score over 60 days; enter |z| >= 2 (sell the rich leg, buy the cheap one, equal rupees), exit at z = 0,
   stop |z| >= 3.5 or 40 days. GOLD/SILVER, CRUDEOIL/NATURALGAS, COPPER/ZINC, ZINC/ALUMINIUM, COPPER/ALUMINIUM.
Everything is fixed in advance; periods 2006-14, 2015-24, 2025-26 reported separately.

  python -m research.search.trend_pairs_mcx   -> research/search/results_trend2/*
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.search import hit80_search as H  # noqa: E402

OUT = ROOT / "research/search/results_trend2"
SPEEDS = ((8, 32, 5.3), (16, 64, 3.75), (32, 128, 2.65), (64, 256, 1.87))
COST = 0.03   # % per unit traded (MCX futures, both sides incl. slippage)


def period(t):
    y = pd.Timestamp(t).year
    return "2006-14" if y <= 2014 else "2015-24" if y <= 2024 else "2025-26"


def load():
    out = {}
    for seg, tf, name, df in H.datasets():
        if seg == "STK":
            break
        if tf == "1d":
            out[name] = df.reset_index(drop=True)
    return out


def forecast(c):
    pv = c.diff().ewm(span=36, adjust=False).std()
    fs = []
    for f, s, k in SPEEDS:
        raw = (c.ewm(span=f, adjust=False).mean() - c.ewm(span=s, adjust=False).mean()) / pv
        fs.append((raw * k).clip(-20, 20))
    return (sum(fs) / len(fs) * 1.1).clip(-20, 20)


def continuous(df):
    c = df["close"]
    f = forecast(c)
    ret = c.pct_change()
    vol = ret.ewm(span=36, adjust=False).std() * np.sqrt(256)
    pos = (f / 10 / vol.replace(0, np.nan)).shift(1).clip(-5, 5) * 0.2      # 20 % vol target at forecast 10
    pnl = pos * ret - pos.diff().abs() * COST / 100
    pnl[df["switch"].values.astype(bool)] = 0
    return pnl.fillna(0), f


def calls(df, f, E, K):
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    tr = pd.concat([df.high - df.low, (df.high - df.close.shift()).abs(), (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1 / 20, adjust=False).mean().values
    fv = f.values; n = len(c); out = []; i = 300
    while i < n - 1:
        s = 1 if fv[i] >= E and fv[i - 1] < E else -1 if fv[i] <= -E and fv[i - 1] > -E else 0
        if s == 0:
            i += 1; continue
        e = o[i + 1]; best = c[i + 1]; R = K * a[i]; j = i + 1
        while j < n - 1:
            best = max(best, c[j]) if s > 0 else min(best, c[j])
            stop = best - s * K * a[j]
            if (s > 0 and (c[j] < stop or fv[j] <= 0)) or (s < 0 and (c[j] > stop or fv[j] >= 0)) or df["switch"].iat[j + 1]:
                break
            j += 1
        x = o[min(j + 1, n - 1)]
        out.append(dict(time=df["time"].iat[i], side=s, ret=s * (x / e - 1) * 100 - COST, R=s * (x - e) / R, days=j + 1 - i))
        i = j + 1
    return out


def pairs(D):
    out = []
    for A, B in (("GOLD", "SILVER"), ("CRUDEOIL", "NATURALGAS"), ("COPPER", "ZINC"), ("ZINC", "ALUMINIUM"), ("COPPER", "ALUMINIUM")):
        a = D[A].set_index(D[A]["time"].dt.normalize())["close"]; b = D[B].set_index(D[B]["time"].dt.normalize())["close"]
        x = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
        lr = np.log(x.a / x.b)
        z = (lr - lr.rolling(60).mean()) / lr.rolling(60).std()
        ra, rb = x.a.pct_change().values, x.b.pct_change().values
        zv = z.values; n = len(x); i = 70
        while i < n - 1:
            if abs(zv[i]) < 2 or np.isnan(zv[i]):
                i += 1; continue
            s = -np.sign(zv[i])                            # +1: long A short B
            pnl, j = 0.0, i + 1
            while j < n:
                pnl += 0.5 * s * (ra[j] - rb[j]) * 100
                if (s > 0 and zv[j] >= 0) or (s < 0 and zv[j] <= 0) or abs(zv[j]) >= 3.5 or j - i >= 40:
                    break
                j += 1
            out.append(dict(pair=f"{A}/{B}", time=x.index[i], ret=pnl - 2 * COST, days=j - i))
            i = j + 1
    return pd.DataFrame(out)


def pf(x):
    g, ls = x[x > 0].sum(), -x[x < 0].sum()
    return round(g / ls, 2) if ls else np.nan


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 400)
    D = load()
    sh, cl = [], []
    for name, df in D.items():
        pnl, f = continuous(df)
        p = pd.Series(pnl.values, index=df["time"]).loc["2007":]
        for per, g in p.groupby(p.index.map(period)):
            sh.append(dict(name=name, period=per, sharpe=round(g.mean() / g.std() * 16, 2) if g.std() > 0 else np.nan,
                           ann_ret=round(g.mean() * 256 * 100, 1)))
        for E in (5, 10):
            for K in (3, 4):
                for t in calls(df, f, E, K):
                    cl.append(dict(name=name, E=E, K=K, **t))
    S = pd.DataFrame(sh); C = pd.DataFrame(cl); C["period"] = C.time.map(period)
    S.to_csv(OUT / "continuous_sharpe.csv", index=False); C.to_csv(OUT / "calls.csv.gz", index=False)
    print("=== A1 continuous trend system: Sharpe by commodity / period ===")
    print(S.pivot(index="name", columns="period", values="sharpe").to_string())
    agg = lambda g: pd.Series(dict(trades=len(g), win=round((g.ret > 0).mean(), 2), avg_pct=round(g.ret.mean(), 2),
                                   pf=pf(g.ret), avg_days=round(g.days.mean(), 1)))
    print("\n=== A2 trend CALLS, all MCX together ===")
    print(C[C.name.isin(H.SS.NAMES and [n for _, n in H.SS.NAMES if _ == "MCX"])].groupby(["E", "K", "period"]).apply(agg).to_string())
    m = C[(C.E == 10) & (C.K == 4)]
    print("\n=== A2 calls E=10 K=4 by commodity / period ===")
    print(m.groupby(["name", "period"]).apply(agg).to_string())
    print("\n=== A2 E=10 K=4 by side (MCX) ===")
    print(m[~m.name.isin(["NIFTY", "BANKNIFTY"])].groupby(["side", "period"]).apply(agg).to_string())
    P = pairs(D); P["period"] = P.time.map(period)
    P.to_csv(OUT / "pairs.csv.gz", index=False)
    print("\n=== B pairs ===")
    print(P.groupby(["pair", "period"]).apply(agg).to_string())


if __name__ == "__main__":
    main()
