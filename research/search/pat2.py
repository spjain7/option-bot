"""PAT-002 – see REGISTRY_PAT2.md.  python -m research.search.pat2 [MCXIDX|STOCKS]"""
import itertools, json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research import instruments as INS  # noqa
from research.search import strategy_search as SS, stock_search as SR, stock_check as SC  # noqa
from research.search.inst_patterns import signals as PAT  # noqa
from alerts import stats as ST  # noqa
from alerts.stocks import in_rollover_window  # noqa

SPLIT = pd.Timestamp("2024-07-01")
OUT = ROOT / "research/search/results_pat2"
SLS = ("A1.5", "A2", "A3", "SW")
TGS = ("R0.5", "R1", "R2", "R3", "R5", "SR")


def weekly(d):
    w = d.copy(); w["wk"] = w["time"].dt.to_period("W")
    g = w.groupby("wk")
    return g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"), low=("low", "min"),
                 close=("close", "last"), volume=("volume", "sum")).reset_index(drop=True)


def feats(df):
    o, h, l, c = (df[x].values.astype(float) for x in ("open", "high", "low", "close"))
    f = dict(o=o, h=h, l=l, c=c, atr=I.atr(df, 14).values, t=df["time"].values, day=df["time"].dt.normalize().values)
    f["e200"] = I.ema(df["close"], 200).values
    return f


def simulate(f, sig, slkind, tgkind, swd, nx, cost, maxhold, start):
    o, h, l, c, a = f["o"], f["h"], f["l"], f["c"], f["atr"]
    n = len(c); out = []
    i = start
    while i < n - 1:
        s = int(sig[i])
        if s == 0 or swd[i] or nx[i] or not a[i] > 0:
            i += 1; continue
        e0 = o[i + 1]
        if slkind == "SW":
            st = (l[max(0, i - 9):i + 1].min() - 0.2 * a[i]) if s > 0 else (h[max(0, i - 9):i + 1].max() + 0.2 * a[i])
        else:
            st = e0 - s * float(slkind[1:]) * a[i]
        risk = s * (e0 - st)
        if risk <= 0 or risk > 4 * a[i]:
            i += 1; continue
        if tgkind == "SR":
            lo_ = max(0, i - 60)
            lvl = h[lo_:i - 19].max() if s > 0 and i - 19 > lo_ else (l[lo_:i - 19].min() if i - 19 > lo_ else np.nan)
            tp = lvl if (lvl == lvl and s * (lvl - e0) >= risk) else e0 + s * 2 * risk
        else:
            tp = e0 + s * float(tgkind[1:]) * risk
        px = None; j = i + 1
        while j < n:
            if (o[j] <= st) if s > 0 else (o[j] >= st): px = o[j]; break
            if (l[j] <= st) if s > 0 else (h[j] >= st): px = st; break
            if (h[j] >= tp) if s > 0 else (l[j] <= tp): px = tp; break
            if nx[j] or j - (i + 1) >= maxhold: px = c[j]; break
            j += 1
        if px is None:
            px = c[n - 1]; j = n - 1
        out.append((f["t"][i], s * (px - e0), cost[i]))
        i = j                                            # one position at a time
    return out


def rules(df, f, tf, oi_ok):
    c, hi, lo, v = df["close"], df["high"], df["low"], df["volume"].astype(float)
    va = v.rolling(20).mean().shift(1).values
    trend_ema = I.ema(c, 50 if tf == "1w" else 200).values
    S = PAT(df, f)
    bo = np.where(c > hi.shift(1).rolling(20).max(), 1, np.where(c < lo.shift(1).rolling(20).min(), -1, 0))
    ent = {"breakout": bo, "flag": S["flag"], "hs": S["hs"], "double": S["double"], "squeeze": S["squeeze"]}
    vol = v.values > 1.5 * va
    trd = np.sign(c.values - trend_ema)
    flt = {"none": None, "vol": vol, "trend": "trend", "vol+trend": "both"}
    if oi_ok is not None:
        flt.update({"oi": "oi", "oi+trend": "oitrend", "oi+vol": "oivol"})
    out = {}
    for en, sg in ent.items():
        for fn, fv in flt.items():
            x = sg.copy()
            if fn in ("vol", "vol+trend", "oi+vol"): x = np.where(vol, x, 0)
            if fn in ("trend", "vol+trend", "oi+trend"): x = np.where(x * trd > 0, x, 0)
            if fn.startswith("oi"): x = np.where(oi_ok(x), x, 0)
            out[f"{en}|{fn}"] = x
    return out


def items(kind):
    if kind == "MCXIDX":
        for exch, name in SS.NAMES:
            h = SS.load(exch, name, "ONE_HOUR"); sw = SS.switch_days(name, exch, h); mult = INS.REGISTRY[name]["mult"]
            yield name, h, sw, (lambda p, n=name: INS.cost_points(n, p, 1.0)), mult, None
    else:
        man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
        for r in man.itertuples():
            f1, fo = SR.DATA / f"{r.name}_ONE_HOUR.csv", SR.DATA / f"{r.name}_OI_ONE_DAY.csv"
            if not f1.exists():
                continue
            h = pd.read_csv(f1, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
            sw = {x for x in pd.unique(h["time"].dt.normalize()) if in_rollover_window(pd.Timestamp(x))}
            oi = pd.read_csv(fo) if fo.exists() else None
            yield r.name, h, sw, (lambda p, L=r.lot: SC.cost_frac(p, L)), r.lot, oi


def main():
    kind = (sys.argv[1:] or ["MCXIDX"])[0]
    tfs = ("3h", "1d", "1w") if kind == "MCXIDX" else ("1d", "1w")
    rows = []
    for name, h, sw, costf, mult, oi in items(kind):
        d = SS.daily_from(h)
        for tf in tfs:
            df = (ST.three_hour_generic(h) if tf == "3h" else d if tf == "1d" else weekly(d)).reset_index(drop=True)
            if len(df) < 80:
                continue
            f = feats(df)
            day = pd.to_datetime(f["day"])
            if tf == "1w":
                swd = np.zeros(len(df), bool); nx = np.zeros(len(df), bool)
            else:
                swd = np.array([pd.Timestamp(x) in sw for x in day]); nx = np.r_[swd[1:], False] & (f["day"] != np.r_[f["day"][1:], f["day"][-1]])
            cost = np.array([costf(p) for p in f["c"]])
            oi_ok = None
            if oi is not None and tf != "3h":
                o = oi.groupby(pd.to_datetime(oi["time"].astype(str).str[:10]))["oi"].last()
                dd = d.set_index(d["time"].dt.normalize())
                doi = o.reindex(dd.index).pct_change(5 if tf == "1w" else 1)
                if tf == "1w":
                    wdoi = doi.groupby(doi.index.to_period("W")).last()
                    arr = day.dt.to_period("W").map(wdoi).astype(float).values
                else:
                    arr = doi.reindex(day).values
                oi_ok = (lambda x, arr=arr: (np.nan_to_num(arr) >= 0.02) & (x != 0))
            start = 60 if tf == "1w" else 210
            for rn, sg in rules(df, f, tf, oi_ok).items():
                for slk, tgk in itertools.product(SLS, TGS):
                    for t0, g, cp in simulate(f, sg, slk, tgk, swd, nx, cost, 26 if tf == "1w" else 40, start):
                        rows.append((name, tf, rn, slk, tgk, t0, (g - cp) * mult, (g - 2 * cp) * mult))
        print(name, flush=True)
    T = pd.DataFrame(rows, columns=["name", "tf", "rule", "sl", "tg", "time", "rs", "rs2"])
    T["per"] = np.where(pd.to_datetime(T.time) < SPLIT, "design", "holdout")
    OUT.mkdir(parents=True, exist_ok=True)
    res = []
    for (tf, rn, slk, tgk), g in T.groupby(["tf", "rule", "sl", "tg"]):
        D, H = g[g.per == "design"], g[g.per == "holdout"]
        mn = 20 if tf == "1w" else 40
        share = (H.groupby("name").rs.mean() > 0).mean() * 100 if len(H) else 0
        ok = len(D) >= mn and len(H) >= mn and D.rs2.mean() > 0 and H.rs2.mean() > 0 and share >= 60
        res.append(dict(tf=tf, rule=rn, sl=slk, tg=tgk, n_d=len(D), win_d=round((D.rs > 0).mean() * 100, 1) if len(D) else None,
                        rs2_d=round(D.rs2.mean()) if len(D) else None, n_h=len(H), win_h=round((H.rs > 0).mean() * 100, 1) if len(H) else None,
                        rs2_h=round(H.rs2.mean()) if len(H) else None, pos_h=round(share), PASS=ok))
    R = pd.DataFrame(res); R.to_csv(OUT / f"summary_{kind}.csv", index=False)
    print(kind, "tested", len(R), "PASS", int(R.PASS.sum()))
    P = R[R.PASS].copy()
    for tf in tfs:
        x = P[P.tf == tf].sort_values("rs2_h", ascending=False)
        print(f"\n== {tf}: {len(x)} pass; top by hold-out ₹ / top by win%")
        print(x.head(8).to_string(index=False))
        print(x.sort_values("win_h", ascending=False).head(8).to_string(index=False))


if __name__ == "__main__":
    main()
