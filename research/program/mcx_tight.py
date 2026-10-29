"""MCX-TIGHT-001 (29-Oct-2026, owner: "no single commodity call – check each commodity, tighter filters").
Per commodity (CRUDEOIL, NATURALGAS, GOLD, SILVER, COPPER, ZINC, ALUMINIUM), Angel 1h futures Jul-2022→Oct-2026, on 1h / 3h / daily.
Base event: close beyond the 20-candle high/low with volume ≥ 1.5×. Pre-declared tight filters (all combinations):
  EMA side 20/50/100/200/none · volume ≥1.5/2/2.5× · ADX any/≥20/≥25 rising · ADR room (intraday only) any/≤0.8 ·
  room to the older level any/not before the target · exits A stop 2 ATR 1R · B 1.5 ATR 1R · C 2 ATR 2R · D S/R · E S/R 1R
Execution / costs / splits / one-trade-at-a-time exactly as bo1h_grid.py (2× costs). Selection per commodity & timeframe:
n ≥ 15 train and ≥ 10 valid, exp2 > 0 in both; BH-FDR 10 % over all combos; the untouched TEST year is then reported.
python research/program/mcx_tight.py"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, bo1h_grid as G  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
CAP = {"1h": 2.5, "3h": 2.5, "1d": 4.0}


def run(job):
    try:
        fr = EX.frames(job)
    except Exception as e:
        print("skip", job[:2], e); return []
    rows = []
    for seg, f0, od, cost in fr:
        tf = seg.split()[-1]
        if not seg.startswith("MCX") or tf not in CAP or len(f0) < 260:
            continue
        f = H.features(f0.reset_index(drop=True)); f["switch"] = f0["switch"].values
        o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values
        emas = {n: I.ema(f["close"], n).values for n in (20, 50, 100, 200)}
        adx = f["adx"].values; adx3 = np.r_[np.full(3, np.nan), adx[:-3]]
        if tf != "1d":
            day = f["time"].dt.normalize()
            dhi, dlo = f.groupby(day)["high"].cummax().values, f.groupby(day)["low"].cummin().values
            dd = f.groupby(day).agg(hi=("high", "max"), lo=("low", "min"))
            adr_i = day.map((dd["hi"] - dd["lo"]).rolling(14).mean().shift(1)).values
        lo10, hi10 = f["low"].rolling(10).min().values, f["high"].rolling(10).max().values
        volx = f["volx"].values
        up = (c > f["hh"].values) & (volx >= 1.5); dn = (c < f["ll"].values) & (volx >= 1.5)
        for side, ev in ((1, up), (-1, dn)):
            for i in np.flatnonzero(ev):
                if i < 210 or i >= len(c) - 2 or sw[i] or sw[i + 1] or not a[i] > 0 or abs(o[i + 1] - c[i]) / a[i] > H.CHASE:
                    continue
                e0 = o[i + 1]
                lvl = f["hi120"].iat[i] if side > 0 else f["lo120"].iat[i]
                room = side * (lvl - e0) if np.isfinite(lvl) else np.nan
                swst = (lo10[i] - 0.25 * a[i]) if side > 0 else (hi10[i] + 0.25 * a[i])
                plans = {"A_2atr_1R": (2.0 * a[i], 1.0), "B_1.5atr_1R": (1.5 * a[i], 1.0), "C_2atr_2R": (2.0 * a[i], 2.0)}
                Rs = side * (e0 - swst)
                if Rs > 0:
                    plans["D_SR_SR"] = ((Rs, room / Rs) if room >= Rs else None) if np.isfinite(room) and room > 0 else (Rs, 2.0)
                    plans["E_SR_1R"] = (Rs, 1.0)
                adr_used = float((dhi[i] - dlo[i]) / adr_i[i]) if tf != "1d" and adr_i[i] > 0 else np.nan
                for ex, p in plans.items():
                    if p is None or p[0] / e0 * 100 > CAP[tf]:
                        continue
                    R, tr = p
                    px, j = G.trade(o, h, l, c, sw, i, side, e0 - side * R, e0 + side * tr * R)
                    rows.append((job[1], tf, "BUY" if side > 0 else "SELL", f["time"].iat[i],
                                 *[int(side * (c[i] - emas[n][i]) > 0) for n in (20, 50, 100, 200)], float(volx[i]), float(adx[i]),
                                 int(adx[i] > adx3[i]), adr_used, ex, float(room / R) if np.isfinite(room) else np.inf, float(tr),
                                 int(j), int(i), (side * (px - e0) - cost[i]) / R, (side * (px - e0) - 2 * cost[i]) / R))
    return rows


COLS = ["name", "tf", "side", "time", "e20", "e50", "e100", "e200", "volx", "adx", "adx_up", "adr_used", "exit", "room_r", "tgt_r",
        "j", "i", "r1", "r2"]


def main():
    J = [j for j in EX.jobs() if j[0] == "mi" and j[2] == "MCX"]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(run, J) for r in x]
    T = pd.DataFrame(rows, columns=COLS)
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T = T.sort_values("time").reset_index(drop=True)
    T["split"] = np.where(T["time"] < G.T1, "train", np.where(T["time"] < G.T2, "valid", "test"))
    T.to_csv(OUT / "mcx_tight_events.csv.gz", index=False)
    grid = list(itertools.product(("none", "e20", "e50", "e100", "e200"), (1.5, 2.0, 2.5), ("any", "adx20", "adx25up"),
                                  ("any", "adr0.8"), ("any", "room")))
    res = []
    for (nm, tf, side, ex), Gx in T.groupby(["name", "tf", "side", "exit"]):
        for em, vx, ad, adr, rm in grid:
            if tf == "1d" and adr != "any":
                continue
            m = Gx["volx"] >= vx
            if em != "none":
                m &= Gx[em] == 1
            if ad == "adx20":
                m &= Gx["adx"] >= 20
            elif ad == "adx25up":
                m &= (Gx["adx"] >= 25) & (Gx["adx_up"] == 1)
            if adr == "adr0.8":
                m &= Gx["adr_used"] <= 0.8
            if rm == "room":
                m &= (Gx["room_r"] >= Gx["tgt_r"]) | (Gx["room_r"] < 0)
            g = G.nonoverlap(Gx[m])
            if len(g) < 30:
                continue
            row = dict(name=nm, tf=tf, side=side, exit=ex, ema=em, vol=vx, adx=ad, adr=adr, room=rm)
            for sp in ("train", "valid", "test"):
                x = g[g["split"] == sp]
                row.update({f"n_{sp}": len(x), f"exp2_{sp}": x["r2"].mean() if len(x) else np.nan,
                            f"win_{sp}": (x["r1"] > 0).mean() * 100 if len(x) else np.nan})
            row["t_tv"] = G.tstat(g[g["split"] != "test"]["r2"])
            res.append(row)
    S = pd.DataFrame(res)
    from scipy.stats import norm
    S["p"] = 1 - norm.cdf(S["t_tv"])
    S = S.sort_values("p").reset_index(drop=True)
    S["bh"] = (S["p"] <= 0.10 * (np.arange(len(S)) + 1) / len(S))[::-1].cummax()[::-1]
    S["pass_tv"] = (S["n_train"] >= 15) & (S["n_valid"] >= 10) & (S["exp2_train"] > 0) & (S["exp2_valid"] > 0)
    S.to_csv(OUT / "mcx_tight_summary.csv.gz", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 300)
    print("combos:", len(S), "| pass train+valid:", int(S["pass_tv"].sum()), "| + FDR:", int((S["pass_tv"] & S["bh"]).sum()))
    P = S[S["pass_tv"]]
    print("\npass train+valid, by commodity / timeframe / side: count, positive in TEST, median TEST exp2")
    print(P.groupby(["name", "tf", "side"]).agg(n=("exp2_test", "size"), test_pos=("exp2_test", lambda x: int((x > 0).sum())),
                                                med_test=("exp2_test", "median"), med_ntest=("n_test", "median")).round(3).to_string())
    cols = ["name", "tf", "side", "exit", "ema", "vol", "adx", "adr", "room", "n_train", "exp2_train", "n_valid", "exp2_valid",
            "n_test", "exp2_test", "win_test", "p", "bh"]
    print("\nstrongest 25 (by train+valid t-stat):")
    print(P[cols].head(25).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
