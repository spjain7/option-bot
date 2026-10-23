"""OPT-BUY-001: can option BUYING win? Registered in REGISTRY_OPTBUY.md before running. Research only.
Run: python -m research.search.option_buy_search      (needs research/data/angel from the research-data branch)
"""
import itertools, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import greeks as G  # noqa
from research.search import strategy_search as SS  # noqa
from alerts import stats as ST  # noqa

SPLIT = pd.Timestamp("2024-07-01")
HALF_SPREAD = {"MCX": 0.02, "NFO": 0.005}
FIXED = 0.005
IVK, IV_FLOOR, R = 1.15, 0.10, 0.065
MAXH = {"1h": 40, "3h": 30, "1d": 15}
TSTOP = {"1h": 10, "3h": 6, "1d": 5}
OUT = ROOT / "research" / "search" / "results_optbuy"


def atr(df, n=14):
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def signals(df):
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    hh, ll = h.rolling(20).max().shift(), l.rolling(20).min().shift()
    vol_ok = v > 1.5 * v.rolling(20).mean().shift()
    don = np.where(c > hh, 1, np.where(c < ll, -1, 0))
    vb = np.where(vol_ok, don, 0)
    m, sd = c.rolling(20).mean(), c.rolling(20).std()
    up, dn = m + 2 * sd, m - 2 * sd
    w = (up - dn) / m
    sq = (w <= w.rolling(120).min() * 1.0001).rolling(5).max().astype(bool)
    squeeze = np.where(sq & (c > up), 1, np.where(sq & (c < dn), -1, 0))
    a = atr(df)
    rng = h - l
    loc = (c - l) / rng.replace(0, np.nan)
    mom = np.where((rng > 2 * a) & (loc >= 0.75), 1, np.where((rng > 2 * a) & (loc <= 0.25), -1, 0))
    return {"volume_breakout": vb, "donchian": don, "squeeze": squeeze, "momentum_candle": mom}, a.values


def daily_iv(h):
    d = SS.daily_from(h)
    hv = np.log(d["close"]).diff().rolling(20).std() * math.sqrt(252)
    s = pd.Series(hv.shift(1).values, index=d["time"].dt.normalize())            # known before the day starts
    return s


def trades(df, sig, a, ivs, swd, exch, tf, ex, dte_of, ivk=IVK, crush=1.0):
    t, o, c = df["time"].values, df["open"].values, df["close"].values
    out, i, n = [], 0, len(df)
    days = df["time"].dt.normalize().values
    while i < n - 2:
        d = sig[i]
        if d == 0 or swd[i] or swd[i + 1] or np.isnan(a[i]):
            i += 1; continue
        e = i + 1
        hv = ivs.get(pd.Timestamp(days[e]))
        if hv is None or not np.isfinite(hv):
            i += 1; continue
        iv = max(hv * ivk, IV_FLOOR)
        F0, K, t0 = o[e], o[e], pd.Timestamp(t[e])
        typ = "CE" if d > 0 else "PE"
        dte = dte_of(t0) if callable(dte_of) else dte_of
        T = lambda tt: max((dte * 1440 - (pd.Timestamp(tt) - t0).total_seconds() / 60) / (365 * 1440), 1 / (365 * 1440))
        p0 = G.price(F0, K, T(t0), iv, R, typ)
        if p0 <= 0:
            i += 1; continue
        stop, best, k, xi = F0 - d * 2 * a[i], F0, e, None
        for k in range(e, min(n, e + MAXH[tf] + 1)):
            if swd[k] and k > e:                                            # close before a contract roll
                xi = k - 1; break
            if (pd.Timestamp(t[k]) - t0).days >= dte - 1:                     # never hold into expiry
                xi = k; break
            v = G.price(c[k], K, T(t[k]), iv, R, typ) / p0 - 1
            held = k - e + 1
            if ex == "X1":
                best = max(best, c[k]) if d > 0 else min(best, c[k])
                stop = max(stop, best - 3 * a[i]) if d > 0 else min(stop, best + 3 * a[i])
                if (c[k] - stop) * d <= 0:
                    xi = k; break
            elif ex == "X2":
                if v <= -0.40 or v >= 1.0 or held >= TSTOP[tf]:
                    xi = k; break
        if xi is None:
            xi = k
        p1 = G.price(c[xi], K, T(t[xi]), iv * crush, R, typ)
        gross = p1 / p0 - 1
        cost = 2 * HALF_SPREAD[exch] + FIXED
        out.append((t0, d, gross, cost))
        i = max(xi, e) + 1
    return out


def trades_x3(df, sig, a, ivs, swd, exch, tf, dte_of, ivk=IVK, crush=1.0):
    """X3 written out separately (needs a running peak)."""
    t, o, c = df["time"].values, df["open"].values, df["close"].values
    out, i, n = [], 0, len(df)
    days = df["time"].dt.normalize().values
    while i < n - 2:
        d = sig[i]
        if d == 0 or swd[i] or swd[i + 1] or np.isnan(a[i]):
            i += 1; continue
        e = i + 1
        hv = ivs.get(pd.Timestamp(days[e]))
        if hv is None or not np.isfinite(hv):
            i += 1; continue
        iv = max(hv * ivk, IV_FLOOR)
        F0, K, t0 = o[e], o[e], pd.Timestamp(t[e])
        typ = "CE" if d > 0 else "PE"
        dte = dte_of(t0) if callable(dte_of) else dte_of
        T = lambda tt: max((dte * 1440 - (pd.Timestamp(tt) - t0).total_seconds() / 60) / (365 * 1440), 1 / (365 * 1440))
        p0 = G.price(F0, K, T(t0), iv, R, typ)
        if p0 <= 0:
            i += 1; continue
        peak, xi, k = 0.0, None, e
        for k in range(e, min(n, e + TSTOP[tf] + 1)):
            if swd[k] and k > e:
                xi = k - 1; break
            if (pd.Timestamp(t[k]) - t0).days >= dte - 1:
                xi = k; break
            v = G.price(c[k], K, T(t[k]), iv, R, typ) / p0 - 1
            held = k - e + 1
            if v <= -0.35 or (held >= 3 and peak < 0.2 and v < 0.2) or (peak >= 0.5 and v <= 0.2) or held >= TSTOP[tf]:
                xi = k; break
            peak = max(peak, v)
        if xi is None:
            xi = k
        p1 = G.price(c[xi], K, T(t[xi]), iv * crush, R, typ)
        out.append((t0, d, p1 / p0 - 1, 2 * HALF_SPREAD[exch] + FIXED))
        i = max(xi, e) + 1
    return out


def real_dte_fn(name, exch, sw):
    """Days to the option expiry a buyer would really use. NIFTY: next weekly expiry (Thursday, Tuesday from Sep-2025).
    Others (monthly options): options expire about 2 days before the futures roll; if that is under 5 days away,
    the next month's (~30 days later)."""
    rolls = sorted(pd.Timestamp(x) for x in sw)
    def f(t0):
        day = t0.normalize()
        if name == "NIFTY":
            wd = 3 if day < pd.Timestamp("2025-09-01") else 1
            n = (wd - day.weekday()) % 7
            n = n if n >= 1 else 7
            return n + 1
        nxt = [r for r in rolls if (r - day).days - 2 >= 5]
        return ((nxt[0] - day).days - 2) if nxt else 30
    return f


def run_one(df, sig, a, ivs, swd, exch, tf, ex, dte, **kw):
    return trades_x3(df, sig, a, ivs, swd, exch, tf, dte, **kw) if ex == "X3" else trades(df, sig, a, ivs, swd, exch, tf, ex, dte, **kw)


def boot_p5(x, rng=np.random.default_rng(7)):
    x = np.asarray(x)
    if len(x) < 10:
        return np.nan
    return float(np.percentile([rng.choice(x, len(x)).mean() for _ in range(2000)], 5))


def prepared():
    for exch, name in SS.NAMES:
        h = SS.load(exch, name, "ONE_HOUR")
        if h is None:
            continue
        sw = SS.switch_days(name, exch, h)
        ivs = daily_iv(h)
        for tf, df in (("1h", h), ("3h", ST.three_hour_generic(h)), ("1d", SS.daily_from(h))):
            df = df.reset_index(drop=True)
            sigs, a = signals(df)
            swd = np.array([pd.Timestamp(x).normalize() in sw for x in df["time"]])
            rng = np.random.default_rng(abs(hash((name, tf))) % 2**32)
            nvb = int((sigs["volume_breakout"] != 0).sum())
            rnd = np.zeros(len(df), int)
            if nvb:
                idx = rng.choice(np.arange(60, len(df) - 2), size=min(nvb, len(df) - 62), replace=False)
                rnd[idx] = rng.choice([-1, 1], size=len(idx))
            sigs["random_control"] = rnd
            yield exch, name, tf, df, sigs, a, ivs, swd, real_dte_fn(name, exch, sw)


def summarise(T):
    T["net1"] = T["gross"] - T["cost"]; T["net2"] = T["gross"] - 2 * T["cost"]
    T["half"] = np.where(T["time"] < SPLIT, "A", "B")
    rows = []
    for key, g in T.groupby(["tf", "entry", "exit", "dte"]):
        A, B = g[g.half == "A"], g[g.half == "B"]
        top = g.sort_values("net1", ascending=False)
        rows.append(dict(tf=key[0], entry=key[1], exit=key[2], dte=key[3], n=len(g), nA=len(A), nB=len(B),
                         win=(g.net1 > 0).mean(), avg1=g.net1.mean(), avg2_A=A.net2.mean(), avg2_B=B.net2.mean(),
                         p5=boot_p5(g.net1.values), wo_top10=top.net1.iloc[10:].mean() if len(top) > 20 else np.nan,
                         long=g[g.dir > 0].net1.mean(), short=g[g.dir < 0].net1.mean()))
    S = pd.DataFrame(rows)
    ctrl = S[S.entry == "random_control"].set_index(["tf", "exit", "dte"])
    def passes(r):
        if r.entry == "random_control":
            return False
        cc = ctrl.loc[(r.tf, r.exit, r.dte)] if (r.tf, r.exit, r.dte) in ctrl.index else None
        beat = cc is not None and r.avg2_A > cc.avg2_A and r.avg2_B > cc.avg2_B
        return bool(r.nA >= 60 and r.nB >= 60 and r.avg2_A > 0 and r.avg2_B > 0 and r.p5 > 0 and beat and r.wo_top10 > 0)
    S["PASS"] = S.apply(passes, axis=1)
    return S


def main():
    rows = []
    data = list(prepared())
    for exch, name, tf, df, sigs, a, ivs, swd, rdte in data:
        for (en, sig), ex, dte in itertools.product(sigs.items(), ["X1", "X2", "X3"], [7, 20, "real"]):
            for t0, d, g, c in run_one(df, sig, a, ivs, swd, exch, tf, ex, rdte if dte == "real" else dte):
                rows.append((name, tf, en, ex, dte, t0, d, g, c))
        print(name, tf, "done", flush=True)
    T = pd.DataFrame(rows, columns=["name", "tf", "entry", "exit", "dte", "time", "dir", "gross", "cost"])
    S = summarise(T)
    OUT.mkdir(parents=True, exist_ok=True)
    S.round(4).to_csv(OUT / "summary.csv", index=False)
    T.to_csv(OUT / "trades.csv.gz", index=False)
    # sensitivity for anything that passes, or the 5 best non-control combos if nothing passes
    pick = S[S.PASS] if S.PASS.any() else S[S.entry != "random_control"].assign(w=lambda x: x[["avg2_A", "avg2_B"]].min(axis=1)).nlargest(5, "w")
    sens = []
    for r in pick.itertuples():
        for lab, kw in (("IV x1.0", {"ivk": 1.0}), ("IV x1.3", {"ivk": 1.3}), ("IV crush 10%", {"crush": 0.9})):
            xs = []
            for exch, name, tf, df, sigs, a, ivs, swd, rdte in data:
                if tf != r.tf:
                    continue
                xs += [g - 2 * c for _, _, g, c in run_one(df, sigs[r.entry], a, ivs, swd, exch, tf, r.exit, rdte if r.dte == "real" else r.dte, **kw)]
            sens.append(dict(tf=r.tf, entry=r.entry, exit=r.exit, dte=r.dte, case=lab, n=len(xs), avg_2x_costs=np.mean(xs) if xs else np.nan))
    pd.DataFrame(sens).round(4).to_csv(OUT / "sensitivity.csv", index=False)
    by_name = T.assign(net1=T.gross - T.cost).groupby(["tf", "entry", "exit", "dte", "name"]).net1.agg(["size", "mean"]).round(3)
    by_name.to_csv(OUT / "by_instrument.csv")
    cols = ["tf", "entry", "exit", "dte", "nA", "nB", "win", "avg1", "avg2_A", "avg2_B", "p5", "wo_top10", "long", "short", "PASS"]
    print(S.sort_values(["avg2_B"], ascending=False)[cols].round(3).to_string(index=False))
    print("\nSENSITIVITY\n" + pd.DataFrame(sens).round(3).to_string(index=False))
    (OUT / "meta.json").write_text(json.dumps(dict(passed=int(S.PASS.sum()), combos=len(S)), indent=1))


if __name__ == "__main__":
    main()
