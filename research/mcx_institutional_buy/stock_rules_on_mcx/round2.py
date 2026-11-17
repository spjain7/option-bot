"""ROUND 2 trial and error on the 4 shared MCX rules that held in all three periods (owner 17-Nov-2026: "what works best and
what more trial and error"). Research only.
  A  better than random?   same filter (daily trend up), same stop / target, random entry bars at the same rate (100 draws)
  B  neighbours            stop 1.0-3.0 ATR x target 1.5-4R: does the edge survive nearby settings (no knife-edge optimum)
  C  extra filters         volume > 1.5x, ADX > 20 / 25, above EMA200, day session only (entry before 17:00), previous-day OI up
  D  exits                 fixed 3R (base) / 2R / 4R, trailing stop 2 / 3 ATR, half at 1R + rest at 3R, time exit 10 candles
  E  per year + all 4 together (1 lot each): yearly Rs, worst drawdown
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round2 -> reports/mcx_round2_*.csv"""
import warnings
import numpy as np
import pandas as pd
from alerts import rulebook as RB
from research.mcx_institutional_buy.backtesting import data as D, costs as K, sim as S, runner as RN
from research.mcx_institutional_buy.stock_rules_on_mcx.run import frames, dtrend

warnings.filterwarnings("ignore")
MULT = {k: v["mult"] for k, v in K.CFG["contracts"].items()}
RULES = [("MOMO 1.5ATR", "MOMO", "1.5ATR", 1.5), ("RSI 70", "RSICONT", "70/30", 2.0), ("BO 20", "BO", "N20 vol0", 1.5),
         ("RETEST 20/5", "RETEST", "20/5", 2.0)]
P3 = ("TRAIN", "VAL", "OOS")


def sim(f, sig, k, r=3.0, kind=0, trail=3.0, ntime=40, name="GOLD"):
    o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
    costf = K.cost_frac(name, f["raw_close"].values, pd.to_datetime(f["time"]))
    si, ei, xi, g, nr, mfe, mae, why, rej = S.simulate(o, h, l, c, a, f["seg"].values.astype(np.int64), costf, np.asarray(sig, bool),
                                                       c - k * a, np.full(len(c), np.nan), np.full(len(c), np.nan), kind, float(r),
                                                       40, int(ntime), float(trail), 3, 0.25, 6.0, 1.5)
    fac = f["raw_close"].values / c
    rk = o[ei] - (c[si] - k * a[si])
    rs = nr * rk * fac[ei] * MULT[name]
    t = pd.to_datetime(f["time"])
    return pd.DataFrame(dict(name=name, entry=t.values[ei], exit=t.values[xi], R=nr, rs=rs,
                             period=RN.period_of("1h", t.iloc[ei]) if len(ei) else []))


def pooled(T):
    out = {}
    for p in P3:
        x = T[T.period == p].R
        out[f"{p}_n"] = len(x); out[f"{p}_R"] = round(float(x.mean()), 3) if len(x) else np.nan
    x = T.R; out["ALL_n"] = len(x); out["ALL_R"] = round(float(x.mean()), 3) if len(x) else np.nan
    out["ALL_rs"] = int(T.rs.sum()) if len(T) else 0
    out["all3_pos"] = all((out[f"{p}_R"] or -1) > 0 for p in P3)
    return out


def main():
    data = {}
    for name in D.INTRA:
        F, dd = frames(name); f = F["4h"].reset_index(drop=True)
        dt = dtrend(f, dd) == 1
        oi = D.daily_oi(name)
        day = pd.to_datetime(f["time"]).dt.normalize()
        if oi is not None and len(oi):
            s = oi.oi.astype(float); up = (s / s.shift(1) - 1 > 0).shift(1)        # previous completed day's OI change
            oiup = day.map(up).fillna(False).values.astype(bool)
        else:
            oiup = np.zeros(len(f), bool)
        sigs = {}
        for lab, fam, par, k in RULES:
            b, _ = RB.raw(f, fam, par)
            sigs[lab] = np.nan_to_num(np.asarray(b, float)).astype(bool) & dt
        data[name] = dict(f=f, dt=dt, oiup=oiup, sigs=sigs)
        print(name, "loaded", flush=True)

    def run(lab, k, maskf=None, **kw):
        T = []
        for name, d in data.items():
            m = d["sigs"][lab] if maskf is None else maskf(d, d["sigs"][lab])
            T.append(sim(d["f"], m, k, name=name, **kw))
        return pd.concat(T, ignore_index=True)

    base = {lab: run(lab, k) for lab, _, _, k in RULES}

    # A: random
    A = []
    rng = np.random.default_rng(7)
    for lab, _, _, k in RULES:
        rate = {n: d["sigs"][lab].sum() / max(d["dt"].sum(), 1) for n, d in data.items()}
        draws = {p: [] for p in P3 + ("ALL",)}
        for _ in range(100):
            T = pd.concat([sim(d["f"], d["dt"] & (rng.random(len(d["dt"])) < rate[n]), k, name=n) for n, d in data.items()])
            for p in P3:
                draws[p].append(T[T.period == p].R.mean())
            draws["ALL"].append(T.R.mean())
        b = pooled(base[lab]); row = dict(rule=lab)
        for p in P3 + ("ALL",):
            arr = np.array(draws[p]); row[f"{p}_rule"] = b[f"{p}_R"]; row[f"{p}_random"] = round(float(np.nanmean(arr)), 3)
            row[f"{p}_beats_pct"] = round(100 * float((arr < b[f"{p}_R"]).mean()), 0)
        A.append(row); print("A", row, flush=True)
    A = pd.DataFrame(A); A.to_csv(RN.REPORTS / "mcx_round2_random.csv", index=False)

    # B: neighbours
    B = []
    for lab, _, _, k0 in RULES:
        for k in (1.0, 1.5, 2.0, 2.5, 3.0):
            for r in (1.5, 2.0, 2.5, 3.0, 4.0):
                B.append(dict(rule=lab, k=k, r=r, **pooled(run(lab, k, r=r))))
    B = pd.DataFrame(B); B.to_csv(RN.REPORTS / "mcx_round2_neighbours.csv", index=False)
    print(B.groupby("rule").agg(cells=("all3_pos", "size"), all3_pos=("all3_pos", "sum"), OOS_pos=("OOS_R", lambda x: int((x > 0).sum()))))

    # C: filters
    FL = {"base": None,
          "volume>1.5x": lambda d, m: m & (d["f"]["volx"].values > 1.5),
          "ADX>20": lambda d, m: m & (d["f"]["adx"].values > 20),
          "ADX>25": lambda d, m: m & (d["f"]["adx"].values > 25),
          "above EMA200": lambda d, m: m & (d["f"]["close"].values > d["f"]["ema200"].values),
          "day session": lambda d, m: m & (pd.to_datetime(d["f"]["time"]).dt.hour.values < 13),     # 4h block 09:00 -> entry 13:00
          "OI up yesterday": lambda d, m: m & d["oiup"]}
    C = [dict(rule=lab, filter=fn, **pooled(run(lab, k, fx))) for lab, _, _, k in RULES for fn, fx in FL.items()]
    C = pd.DataFrame(C); C.to_csv(RN.REPORTS / "mcx_round2_filters.csv", index=False)

    # D: exits
    EX = {"target 3R (base)": dict(kind=0, r=3.0), "target 2R": dict(kind=0, r=2.0), "target 4R": dict(kind=0, r=4.0),
          "trail 2 ATR": dict(kind=2, trail=2.0), "trail 3 ATR": dict(kind=2, trail=3.0),
          "half at 1R, rest 3R": dict(kind=4), "time exit 10 candles": dict(kind=3, ntime=10)}
    E = [dict(rule=lab, exit=en, **pooled(run(lab, k, **kw))) for lab, _, _, k in RULES for en, kw in EX.items()]
    E = pd.DataFrame(E); E.to_csv(RN.REPORTS / "mcx_round2_exits.csv", index=False)

    # E: years + all four together
    Y = []
    for lab, T in base.items():
        T = T.assign(year=pd.to_datetime(T.exit).dt.year)
        for y, g in T.groupby("year"):
            Y.append(dict(rule=lab, year=int(y), trades=len(g), avg_R=round(float(g.R.mean()), 3), rs=int(g.rs.sum())))
    AL = pd.concat([T.assign(rule=lab) for lab, T in base.items()]).sort_values("exit")
    AL["year"] = pd.to_datetime(AL.exit).dt.year
    for y, g in AL.groupby("year"):
        Y.append(dict(rule="ALL 4 together", year=int(y), trades=len(g), avg_R=round(float(g.R.mean()), 3), rs=int(g.rs.sum())))
    Y = pd.DataFrame(Y); Y.to_csv(RN.REPORTS / "mcx_round2_years.csv", index=False)
    eq = AL.rs.cumsum(); dd = (eq - eq.cummax()).min()
    eqR = AL.R.cumsum(); ddR = (eqR - eqR.cummax()).min()
    print(f"ALL 4 together: trades {len(AL)}  Rs {int(AL.rs.sum()):,}  worst drawdown Rs {int(dd):,}  ({ddR:.1f}R)")
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(A.to_string(index=False)); print(C.to_string(index=False)); print(E.to_string(index=False))
    print(Y.pivot(index="year", columns="rule", values="rs").to_string())
    # per-commodity drawdown of all four together
    for n, g in AL.groupby("name"):
        e = g.rs.cumsum(); print(n, "Rs", int(g.rs.sum()), "worst DD", int((e - e.cummax()).min()))


if __name__ == "__main__":
    main()
