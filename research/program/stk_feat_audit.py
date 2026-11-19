"""STK-FEAT-001 (19-Nov-2026, owner: "can OI change, volume or anything else help? did they fire without support / resistance
nearby?"). The live stock SELL rules (stk_call_audit.LIVE), trade by trade on the research data (181 F&O stocks 2022-26, 2x
costs, next-open entry), with what was KNOWN at the signal candle:
  oi_lab    1-hour OI label at the signal (SB short build-up · LU long unwinding · LB long build-up · SC short covering · none)
  doi_prev  previous session's daily OI change (%)
  volx      signal-candle volume / average of the previous 20 candles
  sup_R     room to the nearest SUPPORT below (daily swing low of the last 120 sessions, confirmed 2 days later) in R
            (1R = the call's stop distance) – a SELL whose target is beyond a nearby support must break it first
  res_R     distance to the nearest RESISTANCE above (daily swing high) in R – a resistance inside the stop distance shields the stop
  pdl       the signal candle closed below the previous day's low (yes / no)
Each bucket is judged by win % and R per call in p1 / p2 / p3 (all three must agree before anything is used).
python research/program/stk_feat_audit.py -> results/stk_feat_trades.csv.gz, results/stk_feat_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV, reversal as RV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.stk_call_audit import LIVE, PRI  # noqa: E402
from research.search import stock_oi_buy_run as RN  # noqa: E402

OUT = ROOT / "research/program/results"


def swings(fd):
    lo, hi = fd["low"].values, fd["high"].values; n = len(lo)
    sl = np.zeros(n, bool); sh = np.zeros(n, bool)
    for j in range(2, n - 2):
        sl[j] = lo[j] < min(lo[j - 2], lo[j - 1], lo[j + 1], lo[j + 2])
        sh[j] = hi[j] > max(hi[j - 2], hi[j - 1], hi[j + 1], hi[j + 2])
    return sl, sh


def one(job):
    try:
        S = RN.load_stock(job[1], job[2]); x1 = RV.stock_1h(job[1], job[2]); fr = EX.frames(job)
    except Exception:
        return None
    if S is None or x1 is None:
        return None
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in fr}
    if "STOCKS 1h" not in seg or "STOCKS 1d" not in seg:
        return None
    f1, c1 = seg["STOCKS 1h"]; fd = seg["STOCKS 1d"][0].reset_index(drop=True)
    c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(c1)), c1) if len(c1) != len(f1) else c1
    dtr = SA.daily_trend(fd)
    # OI: 1-hour label series (time -> label) and daily OI change of each session
    lab = pd.Series(x1[1]["oi_lab"].values, index=pd.to_datetime(x1[1]["time"].values)).sort_index()
    f0 = S["f"]; doi = pd.Series(f0["doi"].values, index=pd.to_datetime(f0["time"]).dt.normalize().values)
    dday = pd.to_datetime(fd["time"]).dt.normalize().values
    sl, sh = swings(fd); dlo, dhi = fd["low"].values, fd["high"].values
    frames = {}
    if "STOCKS 3h" in seg:
        frames["3h"] = seg["STOCKS 3h"]
    for hrs, tf in ((2, "2h"), (4, "4h")):
        C, first = anchored(f1, hrs)
        frames[tf] = (C, c1[first[:len(C)]])
    rows = []
    for tf, (C, cost) in frames.items():
        rules = [r for r in LIVE if r[1] == tf]
        if not rules or len(C) < 300:
            continue
        f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
        sets = {(a, b, c): (x, y) for a, b, c, x, y in SV.signal_sets(f, dtr, tf)}
        sets.update({(a, b, c): (x, y) for a, b, c, x, y in SA.signal_sets(f, dtr)})
        t = pd.to_datetime(f["time"]).values; v = C["volume"].values.astype(float)
        vavg = pd.Series(v).rolling(20, min_periods=10).mean().shift(1).values
        atr = f["atr"].values if "atr" in f else H.features(C)["atr"].values
        cl = C["close"].values
        for rid, _, fam, par, flt, k, r, _ in rules:
            if (fam, par, flt) not in sets:
                continue
            s = sets[(fam, par, flt)][1]
            sig = np.where(np.nan_to_num(np.asarray(s, float)) > 0, -1, 0)
            for x in H.simulate(f, sig, -1, k, r, SV.MAXH[tf], 0, np.asarray(cost, float), start=210):
                if x["status"] != "trade":
                    continue
                i = x["i"]; ts = pd.Timestamp(t[i]); day = ts.normalize()
                j = np.searchsorted(dday, np.datetime64(day)) - 1            # last COMPLETED session before the signal day
                R = k * atr[i]
                if j < 5 or not R > 0:
                    continue
                cand = np.flatnonzero(sl[:j - 1][-120:]) + max(0, j - 1 - 120)  # swing lows confirmed by day j
                below = [dlo[q] for q in cand if dlo[q] < cl[i]]
                cand_h = np.flatnonzero(sh[:j - 1][-120:]) + max(0, j - 1 - 120)
                above = [dhi[q] for q in cand_h if dhi[q] > cl[i]]
                sup = max(below) if below else np.nan; res = min(above) if above else np.nan
                lb = lab[:ts]
                rows.append(dict(rule=rid, tf=tf, name=job[1], t_in=t[i], t_out=t[min(i + x["bars"], len(t) - 1)], r=x["r2"], exit=x["exit"],
                                 target_R=r, oi_lab=str(lb.iloc[-1]) if len(lb) and isinstance(lb.iloc[-1], str) else "none",
                                 doi_prev=float(doi.get(pd.Timestamp(dday[j]), np.nan)) * 100,
                                 volx=v[i] / vavg[i] if vavg[i] > 0 else np.nan,
                                 sup_R=(cl[i] - sup) / R if np.isfinite(sup) else np.nan, res_R=(res - cl[i]) / R if np.isfinite(res) else np.nan,
                                 pdl=bool(cl[i] < dlo[j])))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    with Pool(2) as p:
        T = pd.DataFrame([r for x in p.imap_unordered(one, J, chunksize=2) if x for r in x])
    tv = pd.to_datetime(T.t_in).values
    T["split"] = np.where(tv < SV.P1, "p1", np.where(tv < SV.P2, "p2", "p3"))
    T.to_csv(OUT / "stk_feat_trades.csv.gz", index=False)
    print("trades", len(T), "OI label known", round((T.oi_lab != "none").mean(), 3), flush=True)
    B = {"oi_lab": T.oi_lab,
         "doi_prev": pd.cut(T.doi_prev, [-1e9, -2, 0, 2, 5, 1e9], labels=["<-2%", "-2..0%", "0..2%", "2..5%", ">5%"]),
         "volx": pd.cut(T.volx, [0, 0.8, 1.2, 2, 3, 1e9], labels=["<0.8x", "0.8-1.2x", "1.2-2x", "2-3x", ">3x"]),
         "support room (R)": pd.cut(T.sup_R.fillna(99), [-1, 1, 2, 3, 98, 100], labels=["<1R", "1-2R", "2-3R", ">3R", "none in 120d"]),
         "support inside target": np.where(T.sup_R.fillna(99) < T.target_R, "support before target", "clear to target"),
         "resistance above (R)": pd.cut(T.res_R.fillna(99), [-1, 0.5, 1, 2, 98, 100], labels=["<0.5R", "0.5-1R", "1-2R", ">2R", "none"]),
         "closed below prev-day low": T.pdl.map({True: "yes", False: "no"})}
    rows = []
    for nm, b in B.items():
        for v, g in T.groupby(b, observed=True):
            row = dict(feature=nm, bucket=str(v), n=len(g), win=round(100 * (g.r > 0).mean(), 1), R=round(g.r.mean(), 3))
            for sp in ("p1", "p2", "p3"):
                x = g[g.split == sp].r; row[f"{sp}_n"] = len(x); row[f"{sp}_R"] = round(x.mean(), 3) if len(x) else None
            rows.append(row)
    L = pd.DataFrame(rows); L.to_csv(OUT / "stk_feat_summary.csv", index=False)
    base = dict(n=len(T), win=round(100 * (T.r > 0).mean(), 1), R=round(T.r.mean(), 3), **{f"{sp}_R": round(T[T.split == sp].r.mean(), 3) for sp in ("p1", "p2", "p3")})
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
    print("ALL:", base)
    print(L.to_string(index=False))


if __name__ == "__main__":
    main()
