"""Cycle 3 · 3 – MCX 3-hour CONTINUATION BUY: gold, silver and zinc separately, all metals vs energy, against simple
benchmarks, by daily trend regime, plus an UNTOUCHED window.
Rules fixed from cycle 2 (no new tuning): B1 = RSI(14) crosses to >= 75; S10 = RSI >= 75 + ADX >= 25 + close > EMA50 +
20-bar breakout. Benchmarks on the same bars and exits: higher_low (BUY 3 bars after a confirmed higher pivot low),
donchian20 (close above the prior 20-bar high, no RSI), ema_cross (EMA20 crosses above EMA50), every_8th_bar (drift).
Exits: next 3h open, structure stop, 2R and 3R, max 40 bars, never across a contract switch, real MCX costs.
Data: the research periods use 3h bars from the 5-minute files (2023 -> 3-Nov-2026: DEV to 2024, VALID 2025, OOS 2026).
UNTOUCHED = 3h bars built the same way from Angel's front-month HOURLY candles for 15-Jul-2022 -> the day before each
commodity's 5-minute history starts (never used by any earlier study). A consistency check compares hourly- and 5-minute-
built 3h closes where both exist. Per-commodity numbers are reported, but no per-commodity parameter is chosen (samples
are far below 100 trades per commodity per period).
python -m research.cycle3.mcx_metals  ->  results/mcx_metals.csv, results/mcx_metals.json"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD  # noqa: E402
from research.mcxhw.search import bars  # noqa: E402
from research.rsidiv import engine as E  # noqa: E402
from research.rsirev import run as RR  # noqa: E402
from research.cycle2 import common as C, mcx_trend as MT  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
CUTS = [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")]


def signals(b):
    s, conf, reg, risk = RR.strategies(b, 3)
    ev, _, _ = C.base_events(b)
    h, l, c = (b[x].astype(float).reset_index(drop=True) for x in ("high", "low", "close"))
    n = len(c); K = 3; w = 2 * K + 1
    pl = np.where((l == l.rolling(w, center=True).min()).values)[0]; pl = pl[pl + K < n]
    hl = np.zeros(n, bool); p0, p1 = pl[:-1], pl[1:]; ok = (l.values[p1] > l.values[p0]) & (p1 - p0 >= 5) & (p1 - p0 <= 60); hl[p1[ok] + K] = True
    e20, e50 = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    every = np.zeros(n, bool); every[::8] = True
    sig = {"B1": ev["B1"], "S10": s["S10"], "higher_low": hl, "donchian20": (c > h.shift(1).rolling(20).max()).fillna(False).values,
           "ema_cross": ((e20 > e50) & (e20.shift(1) <= e50.shift(1))).fillna(False).values, "every_8th_bar": every}
    return sig, risk["structure"]


def build(src):
    pool = E.Pool(); trends = []
    for g, name in enumerate(MD.NAMES):
        d = MD.LM.load(name, "FIVE_MINUTE" if src == "m5" else "ONE_HOUR")
        if src == "h1":
            first5 = MD.LM.load(name, "FIVE_MINUTE").time.iloc[0].normalize()
            d = d[d.time < first5].reset_index(drop=True)
            if len(d) < 300:
                continue
        b = bars(d, 180)
        sig, risk = signals(b)
        tr = MT.trend(b)
        S = {}
        for k, x in sig.items():
            for tl in ("all", "up", "down", "neutral"):
                S[(k, tl, "x", 1)] = x & (np.ones(len(b), bool) if tl == "all" else (tr == tl))
        cf = MD.real_cost(name, float(d.close.iloc[-1])) / float(d.close.iloc[-1])
        pool.add(b, S, risk, g * 10000 + np.cumsum(b["sw"].fillna(False).astype(bool).values), np.full(len(b), cf), np.zeros(len(b), np.int64), name)
    return pool.freeze()


def stat(r):
    r = np.asarray(r, float)
    if not len(r):
        return dict(n=0)
    w = r > 0
    return dict(n=len(r), win=round(100 * w.mean(), 1), R=round(r.mean(), 3), PF=round(r[w].sum() / -r[~w].sum(), 2) if (~w).any() else None)


def main():
    res, rows = {}, []
    P5, PH = build("m5"), build("h1")
    for R in (2.0, 3.0):
        for key in sorted(k for k in P5.idx):
            T = P5.run(key, R, 40); U = PH.run(key, R, 40) if key in PH.idx else pd.DataFrame(columns=T.columns)
            for grp, sel in (("all", None), ("metals", C.METALS), ("energy", {"CRUDEOIL", "NATURALGAS"}), ("GOLD", {"GOLD"}), ("SILVER", {"SILVER"}),
                             ("ZINC", {"ZINC"}), ("COPPER", {"COPPER"}), ("ALUMINIUM", {"ALUMINIUM"}), ("CRUDEOIL", {"CRUDEOIL"}), ("NATURALGAS", {"NATURALGAS"})):
                X = T if sel is None else T[T.name.isin(sel)]; Y = U if sel is None else U[U.name.isin(sel)]
                lab = E.periods(X.entry.values, CUTS) if len(X) else np.array([])
                row = dict(signal=key[0], trend=key[1], group=grp, target_R=R, **{f"{p}": stat(X.netR.values[lab == p]) for p, _ in CUTS},
                           UNTOUCHED=stat(Y.netR.values) if len(Y) else dict(n=0), ALL=stat(X.netR.values))
                flat = dict(signal=key[0], trend=key[1], group=grp, target_R=R)
                for p in ("DEV", "VAL", "OOS", "UNTOUCHED", "ALL"):
                    for k2, v in row[p].items():
                        flat[f"{p}_{k2}"] = v
                rows.append(flat)
    L = pd.DataFrame(rows)
    # consistency of hourly-built vs 5-minute-built 3h bars on the overlap
    chk = {}
    for name in ("GOLD", "SILVER", "ZINC"):
        h = bars(MD.LM.load(name, "ONE_HOUR"), 180).set_index("time").close
        m = bars(MD.LM.load(name, "FIVE_MINUTE"), 180).set_index("time").close
        j = pd.concat([h.rename("h"), m.rename("m")], axis=1).dropna()
        chk[name] = dict(overlap_bars=len(j), median_abs_diff_pct=round(float((100 * (j.h / j.m - 1)).abs().median()), 4),
                         p99_abs_diff_pct=round(float((100 * (j.h / j.m - 1)).abs().quantile(0.99)), 3))
    res["hourly_vs_5min_3h_close_check"] = chk
    res["untouched_window"] = {n: str(MD.LM.load(n, "FIVE_MINUTE").time.iloc[0].date()) for n in MD.NAMES}
    L.to_csv(OUT / "mcx_metals.csv", index=False)
    json.dump(res, open(OUT / "mcx_metals.json", "w"), indent=1, default=str)
    pd.set_option("display.width", 260)
    cols = ["signal", "trend", "group", "DEV_n", "DEV_R", "VAL_n", "VAL_R", "OOS_n", "OOS_R", "UNTOUCHED_n", "UNTOUCHED_R", "ALL_n", "ALL_R"]
    q = L[(L.target_R == 2.0) & (L.trend.isin(["all", "up"]))]
    print(q[q.group.isin(["metals", "energy", "GOLD", "SILVER", "ZINC"])][cols].to_string(index=False))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
