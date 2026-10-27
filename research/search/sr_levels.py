"""SR-001 – see REGISTRY_SR.md.  python -m research.search.sr_levels [MCXIDX|STOCKS]"""
import itertools, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa
from research.search import strategy_search as SS  # noqa
from research.search.pat2 import items, SPLIT  # noqa

OUT = ROOT / "research/search/results_sr"


def levels(d):
    d = d.copy().reset_index(drop=True)
    t = d["time"]
    w, m = t.dt.to_period("W"), t.dt.to_period("M")
    W = d.groupby(w).agg(h=("high", "max"), l=("low", "min"), c=("close", "last"))
    M = d.groupby(m).agg(h=("high", "max"), l=("low", "min"), c=("close", "last"))
    d["pwh"], d["pwl"] = w.map(W["h"].shift(1)).values, w.map(W["l"].shift(1)).values
    d["pmh"], d["pml"] = m.map(M["h"].shift(1)).values, m.map(M["l"].shift(1)).values
    pp = (M["h"] + M["l"] + M["c"]) / 3
    d["mp"] = m.map(pp.shift(1)).values
    d["ms1"] = m.map((2 * pp - M["h"]).shift(1)).values
    d["mr1"] = m.map((2 * pp - M["l"]).shift(1)).values
    # higher-timeframe trend known before today: last COMPLETED week / month
    we = W["c"].ewm(span=20, adjust=False).mean(); me = M["c"].ewm(span=10, adjust=False).mean()
    d["wtr"] = w.map(np.sign(W["c"] - we).shift(1)).values
    d["mtr"] = m.map(np.sign(M["c"] - me).shift(1)).values
    d["atr"] = I.atr(d, 14).values
    v = d["volume"].astype(float); d["volx"] = (v / v.rolling(20).mean().shift(1)).values
    return d


def signals(d):
    c, h, l, pc = d["close"].values, d["high"].values, d["low"].values, d["close"].shift(1).values
    a = d["atr"].values
    S = {}
    with np.errstate(invalid="ignore"):
        S["WB"] = (np.where((c > d.pwh) & (pc <= d.pwh), 1, np.where((c < d.pwl) & (pc >= d.pwl), -1, 0)), "pwh", "pwl", "pmh", "pml")
        S["MB"] = (np.where((c > d.pmh) & (pc <= d.pmh), 1, np.where((c < d.pml) & (pc >= d.pml), -1, 0)), "pmh", "pml", "mr1", "ms1")
        S["WS"] = (np.where((l <= d.pwl + 0.25 * a) & (c > d.pwl), 1, np.where((h >= d.pwh - 0.25 * a) & (c < d.pwh), -1, 0)), "pwl", "pwh", "pwh", "pwl")
        S["MS"] = (np.where((l <= d.pml + 0.25 * a) & (c > d.pml), 1, np.where((h >= d.pmh - 0.25 * a) & (c < d.pmh), -1, 0)), "pml", "pmh", "pmh", "pml")
        S["PS"] = (np.where((l <= d.ms1 + 0.25 * a) & (c > d.ms1), 1, np.where((h >= d.mr1 - 0.25 * a) & (c < d.mr1), -1, 0)), "ms1", "mr1", "mp", "mp")
    return S


def sim(d, sg, lvl_up, lvl_dn, nxt_up, nxt_dn, slk, tgk, swd, cost):
    o, h, l, c, a = (d[x].values for x in ("open", "high", "low", "close", "atr"))
    LU, LD, NU, ND = (d[x].values for x in (lvl_up, lvl_dn, nxt_up, nxt_dn))
    n, out, i = len(d), [], 25
    while i < n - 1:
        s = int(sg[i])
        if s == 0 or swd[i] or not a[i] > 0 or np.isnan(LU[i]):
            i += 1; continue
        e0 = o[i + 1]
        lv = LU[i] if s > 0 else LD[i]
        st = (lv - s * 0.3 * a[i]) if slk == "LV" else e0 - s * 1.5 * a[i]
        risk = s * (e0 - st)
        if not (0 < risk <= 4 * a[i]):
            i += 1; continue
        if tgk == "NX":
            nx_ = NU[i] if s > 0 else ND[i]
            tp = nx_ if (nx_ == nx_ and s * (nx_ - e0) >= 0.5 * risk) else e0 + s * risk
        else:
            tp = e0 + s * float(tgk[1:]) * risk
        px, j = None, i + 1
        while j < n:
            if (o[j] <= st) if s > 0 else (o[j] >= st): px = o[j]; break
            if (l[j] <= st) if s > 0 else (h[j] >= st): px = st; break
            if (h[j] >= tp) if s > 0 else (l[j] <= tp): px = tp; break
            if swd[j] or j - i >= 20: px = c[j]; break
            j += 1
        if px is None: px, j = c[-1], n - 1
        out.append((d["time"].iat[i], s * (px - e0), cost[i]))
        i = j
    return out


def main():
    kind = (sys.argv[1:] or ["MCXIDX"])[0]
    rows = []
    for name, h, sw, costf, mult, oi in items(kind):
        d = levels(SS.daily_from(h))
        day = d["time"].dt.normalize()
        swd = np.array([pd.Timestamp(x) in sw for x in day])
        cost = np.array([costf(p) for p in d["close"]])
        mtf = (np.sign(d["close"].values - 0) * 0 + 1)                    # placeholder, replaced per side below
        oiup = None
        if oi is not None:
            o = oi.groupby(pd.to_datetime(oi["time"].astype(str).str[:10]))["oi"].last()
            oiup = (o.reindex(day).pct_change().values >= 0.02)
        for sn, (sg, lu, ld, nu, nd) in signals(d).items():
            filt = {"none": sg,
                    "vol": np.where(d["volx"].values > 1.5, sg, 0),
                    "mtf": np.where((sg * d["wtr"].values > 0) & (sg * d["mtr"].values > 0), sg, 0)}
            filt["vol+mtf"] = np.where(d["volx"].values > 1.5, filt["mtf"], 0)
            if oiup is not None:
                filt["oi"] = np.where(oiup, sg, 0)
                filt["oi+mtf"] = np.where(oiup, filt["mtf"], 0)
            for fn, fs in filt.items():
                for slk, tgk in itertools.product(("LV", "A1.5"), ("NX", "R0.5", "R1", "R2")):
                    for t0, g, cp in sim(d, fs, lu, ld, nu, nd, slk, tgk, swd, cost):
                        rows.append((name, f"{sn}|{fn}", slk, tgk, t0, (g - cp) * mult, (g - 2 * cp) * mult))
        print(name, flush=True)
    T = pd.DataFrame(rows, columns=["name", "rule", "sl", "tg", "time", "rs", "rs2"])
    T["per"] = np.where(T.time < SPLIT, "design", "holdout")
    res = []
    for (rn, slk, tgk), g in T.groupby(["rule", "sl", "tg"]):
        D, H = g[g.per == "design"], g[g.per == "holdout"]
        share = (H.groupby("name").rs.mean() > 0).mean() * 100 if len(H) else 0
        ok = len(D) >= 40 and len(H) >= 40 and D.rs2.mean() > 0 and H.rs2.mean() > 0 and share >= 60
        res.append(dict(rule=rn, sl=slk, tg=tgk, n_d=len(D), win_d=round((D.rs > 0).mean() * 100, 1) if len(D) else None,
                        rs2_d=round(D.rs2.mean()) if len(D) else None, n_h=len(H), win_h=round((H.rs > 0).mean() * 100, 1) if len(H) else None,
                        rs2_h=round(H.rs2.mean()) if len(H) else None, pos_h=round(share), PASS=ok))
    R = pd.DataFrame(res); OUT.mkdir(parents=True, exist_ok=True); R.to_csv(OUT / f"summary_{kind}.csv", index=False)
    P = R[R.PASS]
    print(kind, "tested", len(R), "PASS", len(P))
    print("PASSING, highest win % first:\n", P.sort_values("win_h", ascending=False).head(15).to_string(index=False))
    print("ALL rules with hold-out win ≥ 75%:\n", R[R.win_h >= 75].sort_values("win_h", ascending=False).head(15).to_string(index=False))


if __name__ == "__main__":
    main()
