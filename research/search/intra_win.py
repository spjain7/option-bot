"""INTRA-WIN-001 – see REGISTRY_INTRA_WIN.md.  python -m research.search.intra_win"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research import instruments as INS  # noqa
from research.search import stock_check as SC, stock_search as SR, strategy_search as SS  # noqa
from research.search.intraday_search import prep, SPLIT  # noqa

STOPS, TGTS = (1.0, 1.5, 2.0, 3.0), (0.25, 0.5, 0.75, 1.0)
OUT = ROOT / "research" / "search" / "results_intra_win"


def entries(g, has_oi):
    """Yield (family, i, side) – first qualifying candle per family in this session."""
    n = len(g)
    t = g["trend"].iat[0]
    if n < 3 or pd.isna(t) or t == 0 or pd.isna(g["atr"].iat[0]):
        return
    C, H, L, V = g["close"].values, g["high"].values, g["low"].values, g["vwap"].values
    vx, atr, rsi = g["volx"].values, g["atr"].values, g["rsi"].values
    mins = (g["time"].dt.hour * 60 + g["time"].dt.minute).values
    fh_hi, fh_lo, fh_c, o, pc = g["fh_hi"].iat[0], g["fh_lo"].iat[0], g["fh_c"].iat[0], g["o"].iat[0], g["pc"].iat[0]
    ph, pl = g["ph"].iat[0], g["pl"].iat[0]
    got = set()

    def emit(f, i, s):
        if f not in got:
            got.add(f)
            out.append((f, i, s))
    out = []
    for i in range(1, n - 1):
        if t > 0 and C[i] > fh_hi and vx[i] > 1.5: emit("orb_trend", i, 1)
        if t < 0 and C[i] < fh_lo and vx[i] > 1.5: emit("orb_trend", i, -1)
        if has_oi and "orb_trend" in got and out[-1][0] == "orb_trend" and out[-1][1] == i:
            s = out[-1][2]
            if (g["lb_y"].iat[0] if s > 0 else g["sb_y"].iat[0]): emit("oi_orb", i, s)
        if t > 0 and C[i] > ph and vx[i] > 1.5: emit("pdh_break", i, 1)
        if t < 0 and C[i] < pl and vx[i] > 1.5: emit("pdh_break", i, -1)
        if mins[i] >= 675:
            if t > 0 and L[i] <= V[i] < C[i] and (C[:i] > V[:i]).all(): emit("vwap_pullback", i, 1)
            if t < 0 and H[i] >= V[i] > C[i] and (C[:i] < V[:i]).all(): emit("vwap_pullback", i, -1)
            if C[i] - V[i] > 2 * atr[i]: emit("vwap_stretch", i, -1)
            if V[i] - C[i] > 2 * atr[i]: emit("vwap_stretch", i, 1)
        if t > 0 and rsi[i] < 25: emit("rsi_snap", i, 1)
        if t < 0 and rsi[i] > 75: emit("rsi_snap", i, -1)
    if pd.notna(pc) and abs(o / pc - 1) >= 0.01:
        if o > pc and t < 0 and fh_c < o: out.append(("gap_fade", 1, -1))
        if o < pc and t > 0 and fh_c > o: out.append(("gap_fade", 1, 1))
    mid = (fh_hi + fh_lo) / 2
    if n > 3:
        if t > 0 and o - fh_lo > atr[0] and C[1] > mid: out.append(("fh_reversal", 1, 1))
        if t < 0 and fh_hi - o > atr[0] and C[1] < mid: out.append(("fh_reversal", 1, -1))
    for f, i, s in out:
        yield f, i, s


def simulate(g, i, s):
    """Returns gross P&L (points) for each (stop, target) combo, plus entry, atr."""
    e0, a = g["open"].iat[i + 1], g["atr"].iat[i]
    H, L, O = g["high"].values[i + 1:], g["low"].values[i + 1:], g["open"].values[i + 1:]
    last = g["close"].iat[-1]
    res = {}
    for sm in STOPS:
        st = e0 - s * sm * a
        hit_s = (L <= st) if s > 0 else (H >= st)
        for tm in TGTS:
            tp = e0 + s * tm * a
            hit_t = (H >= tp) if s > 0 else (L <= tp)
            ks = np.argmax(hit_s) if hit_s.any() else 10 ** 6
            kt = np.argmax(hit_t) if hit_t.any() else 10 ** 6
            if ks == kt == 10 ** 6:
                pnl = s * (last - e0)
            elif ks <= kt:
                px = min(O[ks], st) if s > 0 else max(O[ks], st)
                pnl = s * (px - e0)
            else:
                pnl = tm * a
            res[(sm, tm)] = pnl
    return e0, a, res


def run(items, kind):
    rows = []
    for name, h, lot, oi in items:
        hp = prep(h, oi)
        for day, g in hp.groupby("day"):
            g = g.reset_index(drop=True)
            for f, i, s in entries(g, oi is not None):
                if i + 1 >= len(g):
                    continue
                e0, a, res = simulate(g, i, s)
                cp = SC.cost_frac(e0, lot) if kind == "STOCKS" else INS.cost_points(name, e0)
                for (sm, tm), p in res.items():
                    R = sm * a
                    rows.append((name, f, sm, tm, g["time"].iat[i], (p - cp) / R, (p - 2 * cp) / R))
        print(kind, name, flush=True)
    return pd.DataFrame(rows, columns=["name", "fam", "stop", "tgt", "time", "r1", "r2"])


def evaluate(T, label):
    res = {}
    T["ho"] = T["time"] >= SPLIT
    for (f, sm, tm), g in T.groupby(["fam", "stop", "tgt"]):
        d, h = g[~g["ho"]], g[g["ho"]]
        sd = SR.stats(d["r1"])
        ok = (sd.get("trades", 0) >= 100 and sd["win"] >= 80 and sd["exp_r"] > 0.03 and (sd["pf"] or 0) >= 1.1
              and sd["p5"] > 0 and d["r2"].mean() > 0)
        row = dict(design=sd, design_2x=round(float(d["r2"].mean()), 3) if len(d) else None, shortlisted=bool(ok))
        if ok:
            sh = SR.stats(h["r1"])
            row.update(holdout=sh, holdout_2x=round(float(h["r2"].mean()), 3),
                       PASS=bool(sh.get("trades", 0) >= 60 and sh["win"] >= 75 and sh["exp_r"] > 0 and h["r2"].mean() > 0))
        res[f"{label}|{f}|S{sm}|T{tm}"] = row
    return res


def main():
    man = pd.read_csv(SR.DATA / "manifest_stocks.csv")
    stocks = []
    for r in man.itertuples():
        f, fo = SR.DATA / f"{r.name}_ONE_HOUR.csv", SR.DATA / f"{r.name}_OI_ONE_DAY.csv"
        if f.exists():
            h = pd.read_csv(f, parse_dates=["time"])[["time", "open", "high", "low", "close", "volume"]].iloc[:-1]
            stocks.append((r.name, h, r.lot, pd.read_csv(fo) if fo.exists() else None))
    idx = [(n, SS.load("NFO", n, "ONE_HOUR"), None, None) for n in ("NIFTY", "BANKNIFTY")]
    mcx = [(n, SS.load("MCX", n, "ONE_HOUR"), None, None) for n in ("CRUDEOIL", "NATURALGAS", "GOLD", "SILVER", "COPPER", "ZINC", "ALUMINIUM")]
    res = {}
    OUT.mkdir(parents=True, exist_ok=True)
    for label, items in (("INDEX", idx), ("MCX", mcx), ("STOCKS", stocks)):
        T = run([x for x in items if x[1] is not None], label)
        T.to_csv(OUT / f"trades_{label}.csv.gz", index=False)
        res.update(evaluate(T, label))
        (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))
    for k, v in res.items():
        if v["design"].get("win", 0) >= 75 or v.get("shortlisted"):
            print(k, v["design"], "2x", v["design_2x"], "| HO", v.get("holdout"), v.get("holdout_2x"), "PASS" if v.get("PASS") else "")


if __name__ == "__main__":
    main()
