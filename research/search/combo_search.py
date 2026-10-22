"""STRAT-SEARCH-002 – combination grid + walk-forward selection (see REGISTRY_002.md).  python -m research.search.combo_search"""
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research import instruments as INS  # noqa: E402
from crude import indicators as I  # noqa: E402
from research.search import strategy_search as SS  # noqa: E402
from alerts import stats as ST  # noqa: E402

OUT = ROOT / "research" / "search" / "results_002"
ENTRIES = ["don20", "don40", "don55", "ema20_50", "ema10_30", "st10_3"]
FILTERS = ["none", "adx20", "ema200", "daily", "hivol"]
EXITS = ["signal", "trail3", "t2r"]
STOPS = [2.0, 3.0]
TFS = ["1h", "3h", "1d"]
MAX_HOLD = 60
TESTS = [("2024-01-01", "2024-07-01"), ("2024-07-01", "2025-01-01"), ("2025-01-01", "2025-07-01"),
         ("2025-07-01", "2026-01-01"), ("2026-01-01", "2026-11-01")]


def features(df, h):
    c, hi, lo = df["close"], df["high"], df["low"]
    f = dict(o=df["open"].values, h=hi.values, l=lo.values, c=c.values, atr=I.atr(df, 14).values,
             t=df["time"].values, day=df["time"].dt.normalize().values)
    for n in (20, 40, 55):
        f[f"hh{n}"], f[f"ll{n}"] = hi.shift(1).rolling(n).max().values, lo.shift(1).rolling(n).min().values
        f[f"xh{n}"], f[f"xl{n}"] = hi.shift(1).rolling(n // 2).max().values, lo.shift(1).rolling(n // 2).min().values
    for a, b in ((20, 50), (10, 30)):
        f[f"ef{a}"], f[f"es{b}"] = I.ema(c, a).values, I.ema(c, b).values
    f["st"] = SS.supertrend(df)
    f["adx"] = I.adx(df).values
    f["e200"] = I.ema(c, 200).values
    d = SS.daily_from(h)
    de = I.ema(d["close"], 50)
    dtr = pd.Series(np.where(d["close"] > de, 1, -1), index=d["time"].dt.normalize()).where(de.notna(), 0).shift(1)
    f["dtr"] = pd.Series(f["day"]).map(dtr).fillna(0).values
    atrp = pd.Series(f["atr"] / f["c"])
    f["hivol"] = (atrp > atrp.rolling(250, min_periods=100).median()).values
    return f


def entry_sig(f, e, i):
    c = f["c"]
    if e.startswith("don"):
        n = int(e[3:])
        return 1 if c[i] > f[f"hh{n}"][i] else -1 if c[i] < f[f"ll{n}"][i] else 0
    if e.startswith("ema"):
        a, b = e[3:].split("_")
        x, y = f[f"ef{a}"], f[f"es{b}"]
        return 1 if (x[i] > y[i] and x[i - 1] <= y[i - 1]) else -1 if (x[i] < y[i] and x[i - 1] >= y[i - 1]) else 0
    st = f["st"]
    return int(st[i]) if st[i] != st[i - 1] else 0


def filt_ok(f, flt, i, s):
    if flt == "none":
        return True
    if flt == "adx20":
        return f["adx"][i] > 20
    if flt == "ema200":
        return (f["c"][i] > f["e200"][i]) if s > 0 else (f["c"][i] < f["e200"][i])
    if flt == "daily":
        return f["dtr"][i] == s
    return bool(f["hivol"][i])


def sig_exit(f, e, i, s):
    c = f["c"]
    if e.startswith("don"):
        n = int(e[3:])
        return (c[i] < f[f"xl{n}"][i]) if s > 0 else (c[i] > f[f"xh{n}"][i])
    if e.startswith("ema"):
        a, b = e[3:].split("_")
        return (f[f"ef{a}"][i] < f[f"es{b}"][i]) if s > 0 else (f[f"ef{a}"][i] > f[f"es{b}"][i])
    return f["st"][i] != s


def run(f, name, swd, nxt_sw, e, flt, ex, k, cost):
    o, h, l, c, a = f["o"], f["h"], f["l"], f["c"], f["atr"]
    n = len(c)
    out, pos = [], None
    for i in range(210, n - 1):
        if pos is not None:
            s, e0, stop, risk, k0, best = pos
            px = None
            if (o[i] <= stop) if s > 0 else (o[i] >= stop):
                px = o[i]
            elif (l[i] <= stop) if s > 0 else (h[i] >= stop):
                px = stop
            elif ex == "t2r" and ((h[i] >= e0 + 2 * risk) if s > 0 else (l[i] <= e0 - 2 * risk)):
                px = e0 + s * 2 * risk
            elif nxt_sw[i] or i - k0 >= MAX_HOLD or (ex == "signal" and sig_exit(f, e, i, s)):
                px = o[i + 1] if not nxt_sw[i] else c[i]
            if px is not None:
                out.append((f["t"][k0], (s * (px - e0) - cost[k0]) / risk, cost[k0] / risk))
                pos = None
            else:
                best = max(best, c[i]) if s > 0 else min(best, c[i])
                if ex == "trail3":
                    ns = best - s * 3 * a[i]
                    if s * (ns - stop) > 0:
                        stop = ns
                pos = (s, e0, stop, risk, k0, best)
            continue
        if swd[i] or nxt_sw[i] or not a[i] > 0:
            continue
        s = entry_sig(f, e, i)
        if s == 0 or not filt_ok(f, flt, i, s):
            continue
        e0 = o[i + 1]
        risk = k * a[i]
        pos = (s, e0, e0 - s * risk, risk, i + 1, e0)
    return out


def main():
    rows = []
    for exch, name in SS.NAMES:
        h = SS.load(exch, name, "ONE_HOUR")
        if h is None:
            continue
        sw = SS.switch_days(name, exch, h)
        for tf, df in (("1h", h), ("3h", ST.three_hour_generic(h)), ("1d", SS.daily_from(h))):
            df = df.reset_index(drop=True)
            f = features(df, h)
            day = f["day"]
            swd = np.array([pd.Timestamp(x) in sw for x in day])
            nxt_sw = np.r_[swd[1:], False] & (day != np.r_[day[1:], day[-1]])
            cost = np.array([INS.cost_points(name, p, 1.0) for p in f["c"]])
            for e, flt, ex, k in itertools.product(ENTRIES, FILTERS, EXITS, STOPS):
                for t0, r, cr in run(f, name, swd, nxt_sw, e, flt, ex, k, cost):
                    rows.append((name, tf, e, flt, ex, k, 1.0, t0, r))
                    rows.append((name, tf, e, flt, ex, k, 2.0, t0, r - cr))     # 2× costs = one more cost unit
            print(name, tf, "done", len(rows), flush=True)
    T = pd.DataFrame(rows, columns=["name", "tf", "entry", "filter", "exit", "stop", "cost_x", "time", "r"])
    T["time"] = pd.to_datetime(T["time"])
    T["combo"] = T["tf"] + "|" + T["entry"] + "|" + T["filter"] + "|" + T["exit"] + "|" + T["stop"].astype(str)
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_parquet(OUT / "trades.parquet") if _has_parquet() else T.to_csv(OUT / "trades.csv.gz", index=False)
    T1 = T[T["cost_x"] == 1.0]
    picks, oos_single, oos_top5, wins = [], [], [], []
    for a, b in TESTS:
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        tr = T1[(T1["time"] >= a - pd.DateOffset(months=18)) & (T1["time"] < a)]
        g = tr.groupby("combo")["r"].agg(["count", "mean", lambda x: x[x > 0].sum() / max(1e-9, -x[x <= 0].sum())])
        g.columns = ["n", "exp", "pf"]
        g = g[(g["n"] >= 40) & (g["pf"] >= 1.1)].sort_values("exp", ascending=False)
        top = list(g.index[:5])
        te = T[(T["time"] >= a) & (T["time"] < b)]
        s1 = te[(te["combo"] == top[0])] if top else te.iloc[:0]
        s5 = te[te["combo"].isin(top)]
        picks.append(dict(test=f"{a:%Y-%m}…{b:%Y-%m}", top5=[dict(combo=c, train_n=int(g.at[c, "n"]), train_exp=round(float(g.at[c, "exp"]), 3)) for c in top],
                          oos_single=_st(s1[s1["cost_x"] == 1]["r"]), oos_top5=_st(s5[s5["cost_x"] == 1]["r"]),
                          oos_top5_2x=_st(s5[s5["cost_x"] == 2]["r"])))
        oos_single.append(s1); oos_top5.append(s5)
        print(picks[-1]["test"], top[:3], picks[-1]["oos_single"], picks[-1]["oos_top5"], flush=True)
    res = dict(windows=picks)
    for lbl, parts in (("single_best", oos_single), ("top5", oos_top5)):
        X = pd.concat(parts)
        x1, x2 = X[X["cost_x"] == 1]["r"], X[X["cost_x"] == 2]["r"]
        st1 = _st(x1)
        pos_w = sum(1 for p in picks if (p["oos_single" if lbl == "single_best" else "oos_top5"].get("exp") or -1) > 0)
        st1.update(exp_2x=round(float(x2.mean()), 3) if len(x2) else None, positive_windows=f"{pos_w}/{len(picks)}")
        st1["PASS"] = bool(st1.get("n", 0) >= 100 and st1.get("exp", -9) >= 0.10 and (st1.get("pf") or 0) >= 1.2
                           and st1.get("p5", -9) > 0 and (st1["exp_2x"] or -9) > 0 and pos_w >= 3)
        res[lbl] = st1
        print(lbl, st1, flush=True)
    # family view (full period, information only): how many combos are positive in BOTH halves?
    fam = T1.assign(half=np.where(T1["time"] < pd.Timestamp("2024-07-01"), "A", "B")).groupby(["combo", "half"])["r"].agg(["count", "mean"]).unstack()
    fam = fam[(fam[("count", "A")] >= 40) & (fam[("count", "B")] >= 40)]
    both = fam[(fam[("mean", "A")] > 0) & (fam[("mean", "B")] > 0)]
    res["robust_combos_both_halves"] = dict(eligible=int(len(fam)), positive_both=int(len(both)),
        by_tf=both.reset_index()["combo"].str.split("|").str[0].value_counts().to_dict(),
        by_entry=both.reset_index()["combo"].str.split("|").str[1].value_counts().to_dict(),
        examples=[dict(combo=c, A=round(float(both.at[c, ("mean", "A")]), 3), B=round(float(both.at[c, ("mean", "B")]), 3),
                       nA=int(both.at[c, ("count", "A")]), nB=int(both.at[c, ("count", "B")]))
                  for c in both.assign(m=both[("mean", "A")].clip(upper=both[("mean", "B")])).sort_values("m", ascending=False).index[:15]])
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res["robust_combos_both_halves"], indent=1, default=str))


def _has_parquet():
    try:
        import pyarrow  # noqa
        return True
    except Exception:
        return False


def _st(r, rng=np.random.default_rng(7)):
    r = np.asarray(r, float)
    if len(r) == 0:
        return dict(n=0)
    w, l = r[r > 0], r[r <= 0]
    b = rng.choice(r, (3000, len(r))).mean(axis=1)
    return dict(n=int(len(r)), exp=round(float(r.mean()), 3), win=round(float((r > 0).mean() * 100), 1),
                pf=round(float(w.sum() / -l.sum()), 2) if l.sum() < 0 else None, p5=round(float(np.percentile(b, 5)), 3))


if __name__ == "__main__":
    main()
