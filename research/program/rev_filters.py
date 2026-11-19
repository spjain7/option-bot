"""REV-FILT-001 (19-Nov-2026, owner: "what further filter can we add so stop-losses drop and targets / winning calls rise").
Base = the reversal SELL setups at 1:1 (stop 2 ATR, target 1R) from rev_ind.py, same harness (next open, 0.5-ATR chase
limit, 2x costs, stop first, never through a roll). For every trade the state at the SIGNAL candle (or the entry open) is
recorded, then each candidate filter is scored per period (2022-24 / 2024-25 / 2025-26). Filter thresholds are fixed
round numbers, not fitted. A filter is ROBUST when it raises R per call in all three periods and keeps >= 25 % of trades.
Also tested: stop management (stop to cost at 0.5R / 0.75R) on the same signals.
python research/program/rev_filters.py -> results/rev_filters_trades.parquet, results/rev_filters_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.sell_exits import run  # noqa: E402
from research.program.rev_ind import tops  # noqa: E402

OUT = ROOT / "research/program/results"
# setup: (indicator, tf, context)
BASE = {"TD9P 4h DT": ("TD9P", "4h", "DT"), "VOLCLIMAX 4h UP": ("VOL_CLIMAX", "4h", "UP"), "CCI200 4h DT": ("CCI200", "4h", "DT"),
        "MACDDIV 4h DT": ("MACD_DIV", "4h", "DT"), "FISHER 4h DT": ("FISHER", "4h", "DT"), "STOCH80 4h DT": ("STOCH80", "4h", "DT"),
        "WPR20 4h DT": ("WPR20", "4h", "DT"), "STOCH80 1d DT": ("STOCH80", "1d", "DT"), "WPR20 1d DT": ("WPR20", "1d", "DT")}
# exit variant: (half_at, be_at)
EXV = {"1:1": (0.0, 0.0), "1:1 BE0.5": (0.0, 0.5), "1:1 BE0.75": (0.0, 0.75)}


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in fr}
    if "STOCKS 1h" not in seg or "STOCKS 1d" not in seg:
        return None
    f1, c1 = seg["STOCKS 1h"]; fd, cd = seg["STOCKS 1d"]
    c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(c1)), c1) if len(c1) != len(f1) else c1
    dtr = SA.daily_trend(fd)
    # daily context known at the previous day's close
    D = H.features(fd)
    dc = D["close"].astype(float)
    dctx = pd.DataFrame({"d_rsi": D["rsi"].values, "d_adx": D["adx"].values, "d_roc20": D["roc20"].values,
                         "d_e20slope": (dc.ewm(span=20, adjust=False).mean().pct_change(5) * 100).values,
                         "d_below200": (dc < D["ema200"]).astype(float).values,
                         "d_dist20lo": ((dc - D["low"].rolling(20).min()) / D["atr"]).values},
                        index=pd.to_datetime(fd["time"]).dt.normalize().values).shift(1)
    dctx = dctx[~dctx.index.duplicated(keep="last")]
    frames = {"1d": (fd, cd)}
    C4, first = anchored(f1, 4); frames["4h"] = (C4, c1[first[:len(C4)]])
    rows = []
    for tf, (C, cost) in frames.items():
        if len(C) < 300:
            continue
        cost = np.asarray(cost, float)
        if len(cost) != len(C):
            cost = np.interp(np.arange(len(C)), np.linspace(0, len(C) - 1, len(cost)), cost)
        f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
        o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values.astype(np.bool_)
        tt = pd.to_datetime(f["time"]); day = tt.dt.normalize()
        e20 = pd.Series(c).ewm(span=20, adjust=False).mean().values; e50 = pd.Series(c).ewm(span=50, adjust=False).mean().values
        up = c > e50 + at; dt = (day.map(dtr) < 0).values
        sw_idx = np.flatnonzero(sw)
        dc_ = dctx.reindex(day.values)
        S = tops(C)
        rng = np.random.default_rng(sum(map(ord, job[1])) + len(tf))
        S["RANDOM"] = pd.Series(rng.random(len(c)) < 0.03)
        todo = [(k, v[0], v[2]) for k, v in BASE.items() if v[1] == tf] + [(f"RANDOM {tf} DT", "RANDOM", "DT")]
        for setup, ind, ctx in todo:
            m = S[ind].values & (dt if ctx == "DT" else up)
            if m.sum() < 1:
                continue
            for ev, (half, be) in EXV.items():
                for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, m, 2.0, 1.0, 10 if tf == "1d" else SV.MAXH.get(tf, 40), cost, half, be, 0.0, H.CHASE):
                    nxt = sw_idx[sw_idx > i]
                    a = at[i]
                    rec = dict(setup=setup, exitv=ev, sym=job[1], tf=tf, t=tt.iat[i], R=rr, why=int(why), mfe=mfe,
                               rsi=f["rsi"].iat[i], adx=f["adx"].iat[i], volx=f["volx"].iat[i], clv=f["clv"].iat[i], body=f["body"].iat[i],
                               red=float(c[i] < o[i]), atrp_rel=f["atrp"].iat[i] / f["atrp_med"].iat[i] if f["atrp_med"].iat[i] else np.nan,
                               ext20=(c[i] - e20[i]) / a, ext50=(c[i] - e50[i]) / a, roc20=f["roc20"].iat[i],
                               room_lo20=(c[i] - f["ll"].iat[i]) / a, res_hh20=(f["hh"].iat[i] - c[i]) / a,
                               wick=(h[i] - max(o[i], c[i])) / a, gap=(o[i + 1] - c[i]) / a,
                               bars_to_roll=(nxt[0] - i) if len(nxt) else 999, hour=tt.iat[i].hour, dow=tt.iat[i].dayofweek)
                    rec.update({k: dc_[k].iat[i] for k in dctx.columns})
                    rows.append(rec)
    return rows, dtr.rename(job[1])


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    rows, trends = [], []
    with Pool(2) as p:
        for x in p.imap_unordered(one, J, chunksize=2):
            if x:
                rows += x[0]; trends.append(x[1])
    T = pd.DataFrame(rows)
    # market breadth: share of F&O stocks whose daily trend is down (previous day)
    B = pd.concat(trends, axis=1)
    breadth = (B < 0).sum(axis=1) / B.notna().sum(axis=1)
    T["day"] = pd.to_datetime(T.t).dt.normalize()
    T["breadth_dn"] = T.day.map(breadth)
    T["period"] = np.where(T.t < SV.P1, "p1", np.where(T.t < SV.P2, "p2", "p3"))
    T.to_parquet(OUT / "rev_filters_trades.parquet")
    F = {"RSI > 60": T.rsi > 60, "RSI < 60": T.rsi <= 60, "ADX > 25": T.adx > 25, "ADX < 25": T.adx <= 25,
         "Vol > 1.5x": T.volx > 1.5, "Vol < 1x": T.volx < 1.0, "Close in lower half of candle": T.clv < 0.5, "Red signal candle": T.red > 0,
         "Upper wick > 0.5 ATR": T.wick > 0.5, "Volatility above normal": T.atrp_rel > 1.1, "Volatility below normal": T.atrp_rel < 0.9,
         "Above EMA20 by > 1 ATR": T.ext20 > 1, "Below / near EMA20": T.ext20 <= 0.5, "Room to 20-bar low > 2 ATR": T.room_lo20 > 2,
         "Room to 20-bar low < 1 ATR": T.room_lo20 < 1, "Near 20-bar high (< 1 ATR)": T.res_hh20 < 1, "Opens lower (gap < 0)": T.gap < 0,
         "Opens higher (gap >= 0)": T.gap >= 0, ">= 5 candles before expiry roll": T.bars_to_roll >= 5,
         "Daily RSI < 45": T.d_rsi < 45, "Daily RSI > 45": T.d_rsi >= 45, "Daily ADX > 25": T.d_adx > 25, "Daily EMA20 falling > 1%/wk": T.d_e20slope < -1,
         "Below daily EMA200": T.d_below200 > 0, "Above daily EMA200": T.d_below200 == 0,
         "Breadth: > 50% stocks falling": T.breadth_dn > 0.5, "Breadth: < 30% stocks falling": T.breadth_dn < 0.3,
         "Breadth: > 40% stocks falling": T.breadth_dn > 0.4,
         "Morning signal (09:15 candle)": T.hour == 9, "Afternoon signal (13:15 candle)": T.hour == 13,
         "Not Monday": T.dow != 0, "Daily room to 20d low > 3 ATR": T.d_dist20lo > 3}
    out = []
    for (s, ev), G in T.groupby(["setup", "exitv"]):
        def st(g):
            return dict(n=len(g), win=100 * (g.R > 0).mean() if len(g) else np.nan, sl=100 * (g.why == 1).mean() if len(g) else np.nan,
                        R=g.R.mean() if len(g) else np.nan)
        base = {p: st(G[G.period == p]) for p in ("p1", "p2", "p3")}
        b = st(G)
        out.append(dict(setup=s, exitv=ev, filter="(none)", keep=100.0, **b, **{f"{p}_R": base[p]["R"] for p in base}, **{f"{p}_win": base[p]["win"] for p in base},
                        robust=False))
        for fn, mask in F.items():
            g = G[mask.loc[G.index].fillna(False).values]
            if len(g) < 60:
                continue
            per = {p: st(g[g.period == p]) for p in ("p1", "p2", "p3")}
            ok = all(per[p]["n"] >= 15 and per[p]["R"] > base[p]["R"] for p in per) and len(g) >= 0.25 * len(G)
            out.append(dict(setup=s, exitv=ev, filter=fn, keep=round(100 * len(g) / len(G), 1), **st(g), **{f"{p}_R": per[p]["R"] for p in per},
                            **{f"{p}_win": per[p]["win"] for p in per}, robust=ok))
    L = pd.DataFrame(out).round(3)
    L.to_csv(OUT / "rev_filters_summary.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 400)
    x = L[L.exitv == "1:1"]
    print(x[(x["filter"] == "(none)")].to_string(index=False))
    print(x[x.robust].sort_values(["setup", "R"], ascending=[True, False]).to_string(index=False))
    # how often each filter is robust across the real setups
    y = x[x.robust & ~x.setup.str.startswith("RANDOM")]
    print(y.groupby("filter").setup.count().sort_values(ascending=False).to_string())
    print(L[L["filter"] == "(none)"].sort_values(["setup", "exitv"]).to_string(index=False))


if __name__ == "__main__":
    main()
