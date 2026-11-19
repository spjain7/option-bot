"""EARLY-REV CHECK – are the best MCX early-reversal BUYs real, or the 2023–26 metals up-move?
For the period-gate passes (fixed, nothing re-tuned):
  * benchmark: entries every 10th bar with the SAME tight stop (3-bar low - 0.1 ATR, 0.3–2 ATR) and the same exit
  * untouched window: Angel hourly bars Jul-2022 -> the start of the 5-minute files (never used by any study)
  * SELL mirror, metals vs energy, per commodity, per year
python -m research.early_rev.check  ->  results/early_rev_check.json"""
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
from research.cycle2 import common as C  # noqa: E402
from research.early_rev import run as ER  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
CANDS = [("3h", "T2_SWEEP_MSS", "all", "8R"), ("1h", "T8_DOUBLE_BOTTOM", "with", "8R"), ("1h", "T7_RSI_RECLAIM", "with", "8R"),
         ("1h", "T2_SWEEP_MSS", "with", "8R"), ("1d", "T2_SWEEP_MSS", "all", "8R"), ("1h", "T3_FAILED_BREAK", "all", "5R")]
MIN = {"1h": 60, "3h": 180, "1d": 1440}
HOLD = {"1h": 90, "3h": 80, "1d": 40}
CUTS = [("UNTOUCHED", "2000-01-01"), ("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")]


def pool(tf, src):
    P = __import__("research.families.run", fromlist=["MultiPool"]).MultiPool()
    for g, name in enumerate(MD.NAMES):
        d5 = MD.LM.load(name, "FIVE_MINUTE")
        if src == "h1":
            if tf == "1d":
                continue
            d = MD.LM.load(name, "ONE_HOUR"); d = d[d.time < d5.time.iloc[0].normalize()].reset_index(drop=True)
            if len(d) < 300:
                continue
        else:
            d = d5
        b = bars(d, MIN[tf]).reset_index(drop=True)
        S, risk, up = ER.triggers(b)
        c = b.close.astype(float); l, h = b.low.astype(float), b.high.astype(float); pc = c.shift(1)
        atr = pd.Series(E.wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14))
        every = np.zeros(len(b), bool); every[::10] = True
        S2, R2 = {}, {}
        for (tg, sd), x in S.items():
            for cx, m in (("all", np.ones(len(b), bool)), ("with", up if sd > 0 else ~up), ("counter", ~up if sd > 0 else up)):
                S2[(f"{tg}|{cx}", sd)] = x & m; R2[(f"{tg}|{cx}", sd)] = risk[(tg, sd)]
        for sd in (1, -1):
            lv = l.rolling(3).min() if sd > 0 else h.rolling(3).max()
            rk = ((c - lv + 0.1 * atr) if sd > 0 else (lv - c + 0.1 * atr)).clip(lower=0.3 * atr, upper=2 * atr).values
            for cx, m in (("all", np.ones(len(b), bool)), ("with", up if sd > 0 else ~up), ("counter", ~up if sd > 0 else up)):
                S2[(f"BENCH_every10|{cx}", sd)] = every & m; R2[(f"BENCH_every10|{cx}", sd)] = rk
        cf = MD.real_cost(name, float(d5.close.iloc[-1])) / float(d5.close.iloc[-1])
        P.add2(b, S2, R2, g * 10000 + np.cumsum(b["sw"].fillna(False).astype(bool).values), np.full(len(b), cf), np.zeros(len(b), np.int64), name)
    return P.done()


def st(r):
    r = np.asarray(r, float)
    if not len(r):
        return dict(n=0)
    w = r > 0
    return dict(n=int(len(r)), win=round(100 * float(w.mean()), 1), R=round(float(r.mean()), 3),
                PF=round(float(r[w].sum() / -r[~w].sum()), 2) if (~w).any() else None)


def run(P, tg, cx, sd, ex, hold):
    k = (f"{tg}|{cx}", sd)
    if (f"{tg}|{cx}", "x", "x", sd) not in P.idx:
        return pd.DataFrame(columns=["name", "entry", "netR"])
    if ex == "TRAIL":
        sig = np.zeros(P.n, np.bool_); sig[P.idx[(f"{tg}|{cx}", "x", "x", sd)]] = True
        ei, nr = ER.sim_trail(P.o, P.h, P.l, P.c, sig, sd, P.rk2[k], P.grp, hold, P.costf)
        return pd.DataFrame(dict(name=P.name[ei], entry=P.t[ei], netR=nr))
    return P.run2(k, float(ex[:-1]), hold)


def main():
    res = {}
    for tf in ("1h", "3h", "1d"):
        P5, PH = pool(tf, "m5"), (pool(tf, "h1") if tf != "1d" else None)
        for (ctf, tg, cx, ex) in CANDS:
            if ctf != tf:
                continue
            out = {}
            for sd in (1, -1):
                for lab, trig in (("rule", tg), ("benchmark_every10_same_stop", "BENCH_every10")):
                    T = run(P5, trig, cx, sd, ex, HOLD[tf]); U = run(PH, trig, cx, sd, ex, HOLD[tf]) if PH is not None else pd.DataFrame(columns=["netR", "entry", "name"])
                    per = E.periods(T.entry.values, CUTS[1:]) if len(T) else np.array([])
                    o = {p: st(T.netR.values[per == p]) for p, _ in CUTS[1:]}
                    o["UNTOUCHED_2022_23"] = st(U.netR.values) if len(U) else dict(n=0)
                    o["metals"] = st(T.netR[T.name.isin(C.METALS)].values); o["energy"] = st(T.netR[~T.name.isin(C.METALS)].values)
                    o["per_commodity"] = {n: st(g.netR.values)["R"] for n, g in T.groupby("name")}
                    o["per_year"] = {int(y): st(g.netR.values)["R"] for y, g in T.groupby(pd.to_datetime(T.entry).dt.year)}
                    out[f"{'BUY' if sd > 0 else 'SELL'} {lab}"] = o
            res[f"{tf} {tg} {cx} {ex}"] = out
            b, bb = out["BUY rule"], out["BUY benchmark_every10_same_stop"]
            print(f"{tf} {tg} {cx} {ex}: rule DEV/VAL/OOS {b['DEV'].get('R')}/{b['VAL'].get('R')}/{b['OOS'].get('R')} untouched {b['UNTOUCHED_2022_23']} | "
                  f"bench {bb['DEV'].get('R')}/{bb['VAL'].get('R')}/{bb['OOS'].get('R')} untouched {bb['UNTOUCHED_2022_23'].get('R')} | "
                  f"SELL rule {out['SELL rule']['DEV'].get('R')}/{out['SELL rule']['VAL'].get('R')}/{out['SELL rule']['OOS'].get('R')} | metals {b['metals'].get('R')} energy {b['energy'].get('R')}", flush=True)
    json.dump(res, open(OUT / "early_rev_check.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
