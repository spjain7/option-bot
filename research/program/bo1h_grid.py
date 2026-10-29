"""BO1H-002 (29-Oct-2026, owner: "tighter screening – ADR/ADX, different EMA, volume 2×, 1:1, S/R-based target and risk").
Base event: 1h close beyond the 20-candle high/low with volume ≥ 1.5× (futures: MCX 7, index 2, stocks ~180; Jul-2022→Oct-2026).
Pre-declared grid (every combination tested, side-aware):
  EMA trend side   : 20 / 50 / 100 / 200 / none
  volume           : ≥1.5× / ≥2× / ≥2.5×
  ADX(14)          : any / ≥20 / ≥25 and rising (vs 3 bars ago)
  ADR room         : any / today's range so far ≤ 0.8 × ADR(14)  (move not exhausted for the day)
  OI (prev day)    : any / not against / confirms   (MCX: no OI – only "any")
  room to resistance: any / older level (bars 21-120) not before the target
Exits: A stop 2 ATR target 1R · B stop 1.5 ATR target 1R · C stop 2 ATR target 2R ·
       D S/R: stop beyond the 10-bar swing ±0.25 ATR, target = older level (≥1R, else 2R if none) ·
       E S/R stop (as D), target 1R.
Execution as harness.simulate (next-bar open, 0.5-ATR chase, stop first, gaps at the open, roll exit, max 40 bars,
stop cap 2.5 %), one trade at a time per instrument & combo, 2× costs. Selection on train (<2024-07) AND valid (<2025-07):
n ≥ 30 each, exp2 > 0 each, BH-FDR 10 % on the train+valid t-stat; then the untouched TEST year is reported.
python research/program/bo1h_grid.py"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
T1, T2 = pd.Timestamp("2024-07-01"), pd.Timestamp("2025-07-01")
EXITS = ("A_2atr_1R", "B_1.5atr_1R", "C_2atr_2R", "D_SR_SR", "E_SR_1R")


def trade(o, h, l, c, sw, i, side, st, tp, maxh=40):
    """Entry next open (already chase-checked). -> (exit_px, j)"""
    e0 = o[i + 1]; j = i + 1
    while j < len(c):
        if j > i + 1 and sw[j]:
            return c[j - 1], j - 1
        if j > i + 1 and side * (o[j] - st) <= 0:
            return o[j], j
        if j > i + 1 and side * (o[j] - tp) >= 0:
            return o[j], j
        if (l[j] <= st) if side > 0 else (h[j] >= st):
            return st, j
        if (h[j] >= tp) if side > 0 else (l[j] <= tp):
            return tp, j
        if j - (i + 1) >= maxh:
            return c[j], j
        j += 1
    return c[-1], len(c) - 1


def run(job):
    try:
        fr = EX.frames(job)
    except Exception as e:
        print("skip", job[:2], e); return []
    rows = []
    for seg, f0, od, cost in fr:
        if not seg.endswith("1h") or len(f0) < 400:
            continue
        mkt = seg.split()[0]
        f = H.features(f0.reset_index(drop=True)); f["switch"] = f0["switch"].values
        o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values
        emas = {n: I.ema(f["close"], n).values for n in (20, 50, 100, 200)}
        adx = f["adx"].values; adx3 = np.r_[np.full(3, np.nan), adx[:-3]]
        day = f["time"].dt.normalize()
        dhi, dlo = f.groupby(day)["high"].cummax().values, f.groupby(day)["low"].cummin().values
        dd = f.groupby(day).agg(hi=("high", "max"), lo=("low", "min"))
        adr = (dd["hi"] - dd["lo"]).rolling(14).mean().shift(1)
        adr_i = day.map(adr).values
        lo10, hi10 = f["low"].rolling(10).min().values, f["high"].rolling(10).max().values
        volx = f["volx"].values
        up = (c > f["hh"].values) & (volx >= 1.5); dn = (c < f["ll"].values) & (volx >= 1.5)
        for side, ev in ((1, up), (-1, dn)):
            for i in np.flatnonzero(ev):
                if i < 210 or i >= len(c) - 2 or sw[i] or sw[i + 1] or not a[i] > 0:
                    continue
                if abs(o[i + 1] - c[i]) / a[i] > H.CHASE:
                    continue
                e0 = o[i + 1]
                lvl = f["hi120"].iat[i] if side > 0 else f["lo120"].iat[i]
                room = side * (lvl - e0) if np.isfinite(lvl) else np.nan
                swst = (lo10[i] - 0.25 * a[i]) if side > 0 else (hi10[i] + 0.25 * a[i])
                plans = {"A_2atr_1R": (2.0 * a[i], 1.0), "B_1.5atr_1R": (1.5 * a[i], 1.0), "C_2atr_2R": (2.0 * a[i], 2.0)}
                Rs = side * (e0 - swst)
                if Rs > 0:
                    if np.isfinite(room) and room > 0:
                        plans["D_SR_SR"] = (Rs, room / Rs) if room >= Rs else None
                    else:
                        plans["D_SR_SR"] = (Rs, 2.0)
                    plans["E_SR_1R"] = (Rs, 1.0)
                feat = (mkt, job[1], "BUY" if side > 0 else "SELL", f["time"].iat[i],
                        *[int(side * (c[i] - emas[n][i]) > 0) for n in (20, 50, 100, 200)], float(volx[i]),
                        float(adx[i]), int(adx[i] > adx3[i]), float((dhi[i] - dlo[i]) / adr_i[i]) if adr_i[i] > 0 else np.nan,
                        int(od[i]) * side if mkt != "MCX" else 9)
                for ex in EXITS:
                    p = plans.get(ex)
                    if p is None:
                        continue
                    R, tr = p
                    if R / e0 * 100 > 2.5:
                        continue
                    st, tp = e0 - side * R, e0 + side * tr * R
                    px, j = trade(o, h, l, c, sw, i, side, st, tp)
                    rm = (room / R) if np.isfinite(room) else np.inf
                    rows.append((*feat, ex, float(rm), float(tr), int(j), int(i), (side * (px - e0) - cost[i]) / R,
                                 (side * (px - e0) - 2 * cost[i]) / R))
    return rows


COLS = ["market", "name", "side", "time", "e20", "e50", "e100", "e200", "volx", "adx", "adx_up", "adr_used", "oi",
        "exit", "room_r", "tgt_r", "j", "i", "r1", "r2"]


def nonoverlap(g):
    keep, busy = [], {}
    for idx, nm, i, j in zip(g.index, g["name"], g["i"], g["j"]):
        if i > busy.get(nm, -1):
            keep.append(idx); busy[nm] = j
    return g.loc[keep]


def tstat(r):
    return r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 2 and r.std() > 0 else 0.0


def main():
    J = [j for j in EX.jobs() if j[0] in ("mi", "stk")]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(run, J, chunksize=2) for r in x]
    T = pd.DataFrame(rows, columns=COLS)
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T = T.sort_values(["time", "name"]).reset_index(drop=True)
    T["split"] = np.where(T["time"] < T1, "train", np.where(T["time"] < T2, "valid", "test"))
    T.to_csv(OUT / "bo1h_grid_events.csv.gz", index=False)
    grid = list(itertools.product(("none", "e20", "e50", "e100", "e200"), (1.5, 2.0, 2.5), ("any", "adx20", "adx25up"),
                                  ("any", "adr0.8"), ("any", "oi_not_against", "oi_confirms"), ("any", "room")))
    res = []
    for (mkt, side, ex), G in T.groupby(["market", "side", "exit"]):
        for em, vx, ad, adr, oi, rm in grid:
            if mkt == "MCX" and oi != "any":
                continue
            m = G["volx"] >= vx
            if em != "none":
                m &= G[em] == 1
            if ad == "adx20":
                m &= G["adx"] >= 20
            elif ad == "adx25up":
                m &= (G["adx"] >= 25) & (G["adx_up"] == 1)
            if adr == "adr0.8":
                m &= G["adr_used"] <= 0.8
            if oi == "oi_not_against":
                m &= G["oi"] >= 0
            elif oi == "oi_confirms":
                m &= G["oi"] == 1
            if rm == "room":
                m &= (G["room_r"] >= G["tgt_r"]) | (G["room_r"] < 0)
            g = nonoverlap(G[m])
            if len(g) < 60:
                continue
            row = dict(market=mkt, side=side, exit=ex, ema=em, vol=vx, adx=ad, adr=adr, oi=oi, room=rm)
            for sp in ("train", "valid", "test"):
                x = g[g["split"] == sp]
                row.update({f"n_{sp}": len(x), f"exp2_{sp}": x["r2"].mean() if len(x) else np.nan,
                            f"win_{sp}": (x["r1"] > 0).mean() * 100 if len(x) else np.nan})
            tv = g[g["split"] != "test"]["r2"]
            row["t_tv"] = tstat(tv)
            res.append(row)
    S = pd.DataFrame(res)
    from scipy.stats import norm
    S["p"] = 1 - norm.cdf(S["t_tv"])
    S = S.sort_values("p").reset_index(drop=True)
    S["bh"] = S["p"] <= 0.10 * (np.arange(len(S)) + 1) / len(S)
    S["bh"] = S["bh"][::-1].cummax()[::-1]
    S["pass_tv"] = (S["n_train"] >= 30) & (S["n_valid"] >= 30) & (S["exp2_train"] > 0) & (S["exp2_valid"] > 0)
    S.to_csv(OUT / "bo1h_grid_summary.csv.gz", index=False)
    print("combos tested:", len(S), "| pass train+valid:", int(S["pass_tv"].sum()), "| pass + FDR:", int((S["pass_tv"] & S["bh"]).sum()))
    sel = S[S["pass_tv"] & S["bh"]]
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200)
    cols = ["market", "side", "exit", "ema", "vol", "adx", "adr", "oi", "room", "n_train", "exp2_train", "n_valid", "exp2_valid",
            "n_test", "exp2_test", "win_test"]
    print(sel[cols].round(3).head(60).to_string(index=False))
    print("\nselected combos positive in TEST:", int((sel["exp2_test"] > 0).sum()), "of", len(sel))
    for (mk, sd), g in sel.groupby(["market", "side"]):
        print(mk, sd, "selected", len(g), "test>0", int((g["exp2_test"] > 0).sum()), "median test exp2", round(g["exp2_test"].median(), 3))


if __name__ == "__main__":
    main()
