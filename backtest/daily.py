"""Daily-timeframe commodity strategies, 2005-2026. Results in R (1R = initial stop distance).
In-sample 2005-2017, out-of-sample 2018-2026. Entry next day's open; stop checked on daily high/low
(gap through stop -> exit at open). Costs + slippage 0.05% per side."""
from pathlib import Path
import numpy as np, pandas as pd

DATA = Path(__file__).parent / "data"
NAMES = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER"]
SPLIT = pd.Timestamp("2018-01-01")
COST = 0.05


def load(n):
    d = pd.read_csv(DATA / f"{n}_D.csv", index_col=0, parse_dates=True)
    c, h, l = d["close"], d["high"], d["low"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(20).mean()
    d["sma200"], d["sma5"] = c.rolling(200).mean(), c.rolling(5).mean()
    dd = c.diff(); u = dd.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    v = (-dd.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    d["rsi2"] = 100 - 100 / (1 + u / v.replace(0, 1e-9))
    return d


def donchian(d, n_in=20, n_out=10, stop_atr=2.0, trend=False, trail_atr=None):
    c, h, l = d["close"].values, d["high"].values, d["low"].values
    o, a, s200 = d["open"].values, d["atr"].values, d["sma200"].values
    hi_in = d["high"].shift(1).rolling(n_in).max().values; lo_in = d["low"].shift(1).rolling(n_in).min().values
    hi_out = d["high"].shift(1).rolling(n_out).max().values; lo_out = d["low"].shift(1).rolling(n_out).min().values
    out, i, n = [], 210, len(d)
    while i < n - 1:
        s = 1 if c[i] > hi_in[i] else -1 if c[i] < lo_in[i] else 0
        if s and trend and s * (c[i] - s200[i]) <= 0:
            s = 0
        if not s or np.isnan(a[i]):
            i += 1; continue
        j = i + 1; e = o[j]; R = stop_atr * a[i]; stop = e - s * R; best = e; k = j; x = None
        while k < n:
            if s * (o[k] - stop) <= 0 and k > j:                      # gap through stop
                x = o[k]; break
            if s * ((l[k] if s > 0 else h[k]) - stop) <= 0:
                x = stop; break
            if s * (c[k] - (lo_out[k] if s > 0 else hi_out[k])) < 0:    # opposite channel -> exit at close
                x = c[k]; break
            if trail_atr:
                best = max(best, c[k]) if s > 0 else min(best, c[k])
                stop = max(stop, best - trail_atr * a[k]) if s > 0 else min(stop, best + trail_atr * a[k])
            k += 1
        if x is None:
            break
        out.append(dict(time=d.index[i], side=s, r=s * (x - e) / R - COST / 100 * 2 * e / R, days=k - j + 1))
        i = k
    return pd.DataFrame(out)


def rsi2(d, lo=10, hi=90, max_days=10, stop_atr=3.0):
    c, h, l, o = (d[k].values for k in ("close", "high", "low", "open"))
    a, s200, s5, r2 = d["atr"].values, d["sma200"].values, d["sma5"].values, d["rsi2"].values
    out, i, n = [], 210, len(d)
    while i < n - 1:
        s = 1 if (c[i] > s200[i] and r2[i] < lo) else -1 if (c[i] < s200[i] and r2[i] > hi) else 0
        if not s or np.isnan(a[i]):
            i += 1; continue
        j = i + 1; e = o[j]; R = stop_atr * a[i]; stop = e - s * R; k = j; x = None
        while k < n:
            if s * ((l[k] if s > 0 else h[k]) - stop) <= 0:
                x = o[k] if s * (o[k] - stop) <= 0 else stop; break
            if s * (c[k] - s5[k]) > 0 or k - j + 1 >= max_days:
                x = c[k]; break
            k += 1
        if x is None:
            break
        out.append(dict(time=d.index[i], side=s, r=s * (x - e) / R - COST / 100 * 2 * e / R, days=k - j + 1))
        i = k
    return pd.DataFrame(out)


def stats(t):
    if t.empty:
        return dict(trades=0)
    r = t["r"]; eq = r.cumsum(); w, l_ = r[r > 0], r[r <= 0]
    yrs = max((t["time"].max() - t["time"].min()).days / 365, 1)
    return dict(trades=len(r), per_year=round(len(r) / yrs, 1), win=round((r > 0).mean() * 100),
                avg_r=round(r.mean(), 3), total_r=round(r.sum(), 1),
                pf=round(w.sum() / -l_.sum(), 2) if l_.sum() else np.inf, max_dd_r=round((eq - eq.cummax()).min(), 1),
                avg_days=round(t["days"].mean(), 1))


STRATS = {
    "Donchian 20/10, 2ATR stop": lambda d: donchian(d),
    "Donchian 20/10 + 200d trend": lambda d: donchian(d, trend=True),
    "Donchian 55/20 + 200d trend": lambda d: donchian(d, 55, 20, trend=True),
    "Donchian 20/10 + trend + 3ATR trail": lambda d: donchian(d, trend=True, trail_atr=3.0),
    "RSI(2) pullback in 200d trend": lambda d: rsi2(d),
}

if __name__ == "__main__":
    D = {n: load(n) for n in NAMES}
    rows = {}
    for k, f in STRATS.items():
        t = pd.concat([f(D[n]).assign(name=n) for n in NAMES])
        a, b = stats(t[t.time < SPLIT]), stats(t[t.time >= SPLIT])
        rows[k] = {"IS avgR": a["avg_r"], "IS PF": a["pf"], "OOS trades": b["trades"], "OOS/yr": b["per_year"],
                   "OOS win%": b["win"], "OOS avgR": b["avg_r"], "OOS PF": b["pf"], "OOS totR": b["total_r"],
                   "OOS DD": b["max_dd_r"], "days": b["avg_days"]}
        per = {n: stats(t[(t.name == n) & (t.time >= SPLIT)])["avg_r"] for n in NAMES}
        print(k, "| OOS avgR by name:", per, flush=True)
    r = pd.DataFrame(rows).T
    print(r.to_string()); r.to_csv(Path(__file__).parent / "daily_results.csv")
