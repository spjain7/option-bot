"""RSI-SELL-001 – see REGISTRY_RSISELL.md.  python -m research.search.rsi_sell"""
import itertools, json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research.search import strategy_search as SS, stock_search as SR  # noqa
from alerts.stocks import in_rollover_window  # noqa

SPLIT = pd.Timestamp("2024-07-01")
FL = ["vol", "oi", "sr", "against"]
OUT = ROOT / "research/search/results_rsisell"


def study(name, h, oi, bad_days):
    h = h.sort_values("time").reset_index(drop=True)
    h["day"] = h["time"].dt.normalize()
    h["rsi"] = I.rsi(h["close"], 14)
    v = h["volume"].astype(float)
    key = h["time"].dt.hour
    h["volx"] = v / v.groupby(key).transform(lambda s: s.shift(1).rolling(10, min_periods=5).mean())
    d = h.groupby("day").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    d["atr"] = I.atr(d, 14).shift(1)
    d["e50"] = I.ema(d["close"], 50).shift(1)
    d["pc"] = d["close"].shift(1)
    d["h20"], d["l20"] = d["high"].rolling(20).max().shift(1), d["low"].rolling(20).min().shift(1)
    if oi is not None:
        o = oi.groupby(pd.to_datetime(oi["time"].astype(str).str[:10]))["oi"].last().reindex(d.index)
        doi, dp = o.pct_change(), d["close"].pct_change()
        d["weak_up"], d["weak_dn"] = ((dp > 0) & (doi < 0)).shift(1), ((dp < 0) & (doi < 0)).shift(1)
    else:
        d["weak_up"] = d["weak_dn"] = False
    days = list(d.index); pos = {x: i for i, x in enumerate(days)}
    rows, done = [], set()
    for r in h.itertuples():
        if r.day in done or pd.isna(r.rsi) or r.day not in pos:
            continue
        i = pos[r.day]
        if i + 5 >= len(days) or i < 25:
            continue
        sig = -1 if r.rsi > 80 else 1 if r.rsi < 25 else 0            # -1 = sell CE, +1 = sell PE
        base = r.time.hour == 11                                       # baseline sample: every day at 11:xx
        if not sig and not base:
            continue
        span = days[i:i + 6]
        if any(x in bad_days for x in span):
            continue
        dr = d.iloc[i]
        if pd.isna(dr.atr):
            continue
        after = h[(h["time"] > r.time) & (h["day"] <= days[i + 5])]
        fl = {}
        if sig:
            done.add(r.day)
            fl = dict(vol=bool(r.volx > 1.5),
                      oi=bool(d.iloc[i]["weak_up"] if sig < 0 else d.iloc[i]["weak_dn"]),
                      sr=bool((r.close >= dr.h20 - 0.5 * dr.atr) if sig < 0 else (r.close <= dr.l20 + 0.5 * dr.atr)),
                      against=bool((dr.pc < dr.e50) if sig < 0 else (dr.pc > dr.e50)))
        for side in ([sig] if sig else [-1, 1]):
            for k in (0.5, 1.0):
                strike = r.close + (-side) * k * dr.atr                # CE above (side -1), PE below (side +1)
                for hz, n in (("H1", 1), ("H3", 3), ("H5", 5)):
                    seg = after[after["day"] <= days[i + n]]
                    if seg.empty:
                        continue
                    end = seg["close"].iloc[-1]
                    if side < 0:
                        win, safe = end < strike, seg["high"].max() < strike
                    else:
                        win, safe = end > strike, seg["low"].min() > strike
                    rows.append(dict(name=name, time=r.time, kind="sig" if sig else "base", side=side, k=k, hz=hz,
                                     win=bool(win), safe=bool(safe), **fl))
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    allrows = {"INDEX": [], "MCX": [], "STOCKS": []}
    for exch, name in SS.NAMES:
        h = SS.load(exch, name, "ONE_HOUR")
        sw = SS.switch_days(name, exch, h)
        bad = set()
        for x in sw:
            for dd in range(-3, 2):
                bad.add(pd.Timestamp(x) + pd.Timedelta(days=dd))
        allrows["INDEX" if exch == "NFO" else "MCX"] += study(name, h[["time", "open", "high", "low", "close", "volume"]], None, bad)
        print(name, flush=True)
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    for r in man.itertuples():
        f, fo = SR.DATA / f"{r.name}_ONE_HOUR.csv", SR.DATA / f"{r.name}_OI_ONE_DAY.csv"
        if not f.exists():
            continue
        h = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
        bad = {x for x in pd.unique(h["time"].dt.normalize()) if in_rollover_window(pd.Timestamp(x))}
        allrows["STOCKS"] += study(r.name, h, pd.read_csv(fo) if fo.exists() else None, bad)
    res = []
    for u, rows in allrows.items():
        T = pd.DataFrame(rows)
        T["per"] = np.where(T["time"] < SPLIT, "design", "holdout")
        B = T[T.kind == "base"]; S = T[T.kind == "sig"]
        for (side, k, hz), G in S.groupby(["side", "k", "hz"]):
            bb = B[(B.side == side) & (B.k == k) & (B.hz == hz)]
            for c in [()] + [(x,) for x in FL] + list(itertools.combinations(FL, 2)):
                m = np.ones(len(G), bool)
                for x in c:
                    m &= G[x].fillna(False).values.astype(bool)
                g = G[m]
                row = dict(u=u, sell="CE" if side < 0 else "PE", k=k, hz=hz, filt="+".join(c) or "none")
                ok = True
                for per in ("design", "holdout"):
                    gp, bp = g[g.per == per], bb[bb.per == per]
                    w, b = (gp.win.mean() * 100 if len(gp) else np.nan), bp.win.mean() * 100
                    row.update({f"n_{per}": len(gp), f"win_{per}": round(w, 1), f"safe_{per}": round(gp.safe.mean() * 100, 1) if len(gp) else None,
                                f"base_{per}": round(b, 1)})
                    ok &= len(gp) >= 60 and w >= 80 and w >= b + 5
                row["PASS"] = bool(ok)
                res.append(row)
    R = pd.DataFrame(res)
    R.to_csv(OUT / "summary.csv", index=False)
    print("PASS:", int(R.PASS.sum()), "of", len(R))
    cols = ["u", "sell", "k", "hz", "filt", "n_design", "win_design", "base_design", "safe_design", "n_holdout", "win_holdout", "base_holdout", "safe_holdout"]
    print(R[R.PASS].sort_values("win_holdout", ascending=False)[cols].head(30).to_string(index=False))
    print("\nno-filter rows:")
    print(R[R.filt == "none"][cols].to_string(index=False))


if __name__ == "__main__":
    main()
