"""META-001 (4-Nov-2026) – meta-labeling (Lopez de Prado) on MCX futures: a 2nd model decides which base signals to TAKE.

Base signals (MCX 7, 1h and 3h, both sides, one trade at a time per commodity/side/base):
  ITG   : MACD(12,26) crosses its 9-SMA signal + TEMA(14) slope agrees   (owner's TradingView script)
  DON   : close beyond the 20-candle high / low
  PB    : trend pull-back – c > EMA50 > EMA200, low touches EMA20, close back above EMA20 (mirror for SELL)
Trade (triple barrier): entry next open, stop 2 x ATR14, targets 1R and 2R, max 40 candles, costs 0.1R, roll-adjusted.
Label = the 1R trade wins (+1R before the stop).
Features (known at the signal close, no look-ahead): RSI14 and its 3-bar change, ADX, DI spread, distance to EMA20/50/200 in
  ATR, EMA50/200 slope, ATR % and its 1-year percentile, volume ratio, candle body % and close position, returns 5/20 bars,
  distance to the 20-bar high/low in ATR, previous-day trend vs daily EMA50, hour, weekday, commodity, side, base, timeframe.
Model: sklearn HistGradientBoosting, WALK-FORWARD: for every quarter Q1-2024 .. Q4-2026 train on all events that EXITED
  before the quarter starts (purged), predict the quarter. Only these out-of-sample predictions are reported.
Take a signal when P(win) >= threshold (0.50 / 0.55 / 0.60 / 0.65 all shown – choose BEFORE going live, judged on 2025-26).

  python -m research.search.meta_label_mcx   -> research/search/results_meta/*
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.search import hit80_search as H  # noqa: E402

OUT = ROOT / "research/search/results_meta"
MAXH = 40
THR = (0.50, 0.55, 0.60, 0.65)
NAMES = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM"]


def ema(x, n):
    return x.ewm(span=n, adjust=False).mean()


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def feats(df):
    o, h, l, c, v = (df[k].astype(float) for k in ("open", "high", "low", "close", "volume"))
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1 / 14, adjust=False).mean()
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    upm, dnm = h.diff(), -l.diff()
    pdm = pd.Series(np.where((upm > dnm) & (upm > 0), upm, 0.0)).ewm(alpha=1 / 14, adjust=False).mean()
    mdm = pd.Series(np.where((dnm > upm) & (dnm > 0), dnm, 0.0)).ewm(alpha=1 / 14, adjust=False).mean()
    pdi, mdi = 100 * pdm / a.values, 100 * mdm / a.values
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / 14, adjust=False).mean()
    r = rsi(c)
    rg = (h - l).replace(0, np.nan)
    day = df["time"].dt.normalize()
    dly = df.groupby(day)["close"].last()
    dtr = ((dly - ema(dly, 50)) / dly).shift(1)                      # previous completed day only
    atrp = a / c
    X = pd.DataFrame(dict(
        rsi=r, rsi_ch=r.diff(3), adx=adx.values, di=(pdi - mdi).values,
        d20=(c - e20) / a, d50=(c - e50) / a, d200=(c - e200) / a,
        s50=(e50 - e50.shift(10)) / a, s200=(e200 - e200.shift(20)) / a,
        atrp=atrp, atr_pct=atrp.rolling(1000, min_periods=200).rank(pct=True),
        volx=v / v.rolling(20).mean().shift(1), body=(c - o).abs() / rg, cpos=(c - l) / rg,
        r5=(c / c.shift(5) - 1) / atrp, r20=(c / c.shift(20) - 1) / atrp,
        dhi=(h.rolling(20).max() - c) / a, dlo=(c - l.rolling(20).min()) / a,
        dtrend=day.map(dtr).values, hour=df["time"].dt.hour, wd=df["time"].dt.weekday))
    e1 = ema(c, 14); e2 = ema(e1, 14); e3 = ema(e2, 14); tema = 3 * (e1 - e2) + e3
    m = ema(c, 12) - ema(c, 26); s = m.rolling(9).mean()
    base = {
        "ITG": (((m > s) & (m.shift() <= s.shift()) & (tema > tema.shift())).values,
                ((m < s) & (m.shift() >= s.shift()) & (tema < tema.shift())).values),
        "DON": ((c > h.rolling(20).max().shift(1)).values, (c < l.rolling(20).min().shift(1)).values),
        "PB": (((c > e50) & (e50 > e200) & (l <= e20) & (c > e20)).values,
               ((c < e50) & (e50 < e200) & (h >= e20) & (c < e20)).values)}
    return X, base


def events():
    rows = []
    for seg, tf, name, df in H.datasets():
        if seg == "STK":
            break
        if seg != "MCX" or tf not in ("1h", "3h"):
            continue
        df = df.reset_index(drop=True)
        X, base = feats(df)
        F = H.features(df, "1h")
        for side in (1, -1):
            valid, res = H.outcomes(df, F, side, "2.0", MAXH)
            for b, (lb, sb) in base.items():
                sig = (lb if side > 0 else sb) & valid
                sig[:250] = False
                for i in H.sequential(sig, res[1.0]["ex"]):
                    ex = max(res[1.0]["ex"][i], res[2.0]["ex"][i])
                    r = dict(X.iloc[i]); r.update(name=name, tf=tf, side=side, base=b, time=df["time"].iloc[i],
                                                  exit_time=df["time"].iloc[min(ex, len(df) - 1)],
                                                  y=int(res[1.0]["win"][i]), R1=res[1.0]["r"][i], R2=res[2.0]["r"][i])
                    if side < 0:                                   # mirror direction-dependent features
                        for k in ("rsi_ch", "di", "d20", "d50", "d200", "s50", "s200", "r5", "r20", "dtrend"):
                            r[k] = -r[k]
                        r["rsi"] = 100 - r["rsi"]; r["cpos"] = 1 - r["cpos"]; r["dhi"], r["dlo"] = r["dlo"], r["dhi"]
                    rows.append(r)
        print(name, tf, "events so far", len(rows), flush=True)
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    E = events().sort_values("time").reset_index(drop=True)
    E["name_id"] = E["name"].map({n: i for i, n in enumerate(NAMES)})
    E["base_id"] = E["base"].map({"ITG": 0, "DON": 1, "PB": 2}); E["tf_id"] = (E["tf"] == "3h").astype(int)
    cols = ["rsi", "rsi_ch", "adx", "di", "d20", "d50", "d200", "s50", "s200", "atrp", "atr_pct", "volx", "body", "cpos",
            "r5", "r20", "dhi", "dlo", "dtrend", "hour", "wd", "name_id", "side", "base_id", "tf_id"]
    E["p"] = np.nan
    qs = pd.date_range("2024-01-01", "2027-01-01", freq="QS")
    for q0, q1 in zip(qs[:-1], qs[1:]):
        tr = E[E["exit_time"] < q0]; te = (E["time"] >= q0) & (E["time"] < q1)
        if te.sum() == 0:
            continue
        m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, min_samples_leaf=80,
                                           l2_regularization=1.0, categorical_features=[cols.index("name_id"), cols.index("base_id")],
                                           random_state=0)
        m.fit(tr[cols].values, tr["y"].values)
        E.loc[te, "p"] = m.predict_proba(E.loc[te, cols].values)[:, 1]
        print(f"fold {q0:%Y-%m}: train {len(tr)}, test {te.sum()}", flush=True)
    E.to_csv(OUT / "events.csv.gz", index=False)
    T = E[E.p.notna()].copy(); T["period"] = np.where(T.time < "2025-01-01", "2024", "2025-26")

    def st(g):
        def pf(x):
            gg, ll = x[x > 0].sum(), -x[x < 0].sum(); return round(gg / ll, 2) if ll else np.nan
        return pd.Series(dict(n=len(g), win1R=round(g.y.mean(), 3), avgR_1R=round(g.R1.mean(), 3), pf_1R=pf(g.R1),
                              win2R=round((g.R2 > 0).mean(), 3), avgR_2R=round(g.R2.mean(), 3), pf_2R=pf(g.R2)))
    out = []
    for per, g in T.groupby("period"):
        out.append(dict(period=per, filter="ALL base signals", **st(g)))
        for th in THR:
            out.append(dict(period=per, filter=f"P>={th:.2f}", **st(g[g.p >= th])))
    R = pd.DataFrame(out)
    R.to_csv(OUT / "summary.csv", index=False)
    pd.set_option("display.width", 220)
    print(R.to_string(index=False))
    d = T[T.period == "2025-26"]
    for th in (0.55, 0.60):
        k = d[d.p >= th]
        print(f"\n2025-26 P>={th}: by commodity / side / base")
        print(k.groupby(["name"]).apply(st).to_string())
        print(k.groupby(["side", "base", "tf"]).apply(st).to_string())
    # deciles: does a higher P really mean more wins? (calibration, 2025-26)
    d = d.assign(dec=pd.qcut(d.p, 10, labels=False, duplicates="drop"))
    print("\n2025-26 by P decile:\n", d.groupby("dec").apply(lambda g: pd.Series(dict(p=round(g.p.mean(), 3), n=len(g),
                                                                                       win=round(g.y.mean(), 3), avgR1=round(g.R1.mean(), 3)))).to_string())


if __name__ == "__main__":
    main()
