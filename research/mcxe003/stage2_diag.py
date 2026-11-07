"""MCXE-003 – DIAGNOSTIC execution test (not the pre-registered stage 2, which runs only on stage-1 survivors; there were
none intraday). Purpose: answer "are stops / entries / exits the problem?" for the families with the strongest DEV
information, by running the pre-registered execution menu on them and on MATCHED CONTROL entries with the same execution.
Nothing here can produce an accepted candidate (selection was made on DEV t across hundreds of families).

For each (market, fam, name, side, tf): pooled over instruments and swing methods of that row.
  execution menu: entry {next open, stop at trigger (3 bars)} x stop {invalidation +-0.1 ATR clamped 0.3-3 ATR, 1.5 ATR}
                  x exit {2R, session end, 2-ATR trail}  (12 executions); costs 1x and 2x
  control: for every event, one random bar of the same instrument, same bar time-of-day, same period, same side,
           market entry, stop at the event's stop distance (ATR) – same exit rule
Output: results/stage2_diag_<market>.csv (net R per period for every execution and its control).
python research/mcxe003/stage2_diag.py mcx|nse_fut|nse_eq [top]
"""
import sys
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe003 import (bars as B, swing_detection as SWD, run_discovery as RD, execution as EX,  # noqa: E402
                              cost_model as CM)

OUT = ROOT / "research/mcxe003/results"
EXECS = list(product((0, 1), ("inv", "atr"), ("2R", "eod", "trail")))


def frame(market, inst, tf):
    return B.mcx_intraday(inst, tf) if market == "MCX" else (B.nse_eq_intraday(inst, tf) if market == "NSE_EQ" else B.nse_fut_hourly(inst))


def run_rows(market, rows, insts, seed=20261107):
    rng = np.random.default_rng(seed)
    out = []
    for inst in insts:
        for tf in sorted({r["tf"] for r in rows}):
            try:
                f = frame(market, inst, tf)
            except Exception:                                   # noqa: BLE001
                continue
            methods = ("f2", "f3", "f5", "z15", "z3") if market == "MCX" else ("f3", "z3")
            E = RD.all_events(f, tuple(methods))
            E = E[f.sig_ok.values[E.i.values]]
            o, h, l, c, a = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close", "atr"))
            dl = f.dlast.values.astype(np.int64)
            v0_, o0_ = RD.PERIODS[market]
            q = np.where(f.day < pd.Timestamp(v0_), "DEV", np.where(f.day < pd.Timestamp(o0_), "VALID", "OOS"))
            key = pd.Series(q).str.cat(f.m.astype(str).values, sep="|").values
            pool = pd.Series(np.arange(len(f))[f.sig_ok.values]).groupby(key[f.sig_ok.values]).apply(np.array).to_dict()
            day = f.day.values
            v0, o0 = RD.PERIODS[market]
            for r in [r for r in rows if r["tf"] == tf]:
                x = E[(E.name == r["name"]) & (E.side == r["side"]) & ((E.sw == r["sw"]) | (r["sw"] == "*"))]
                x = x.drop_duplicates("i").sort_values("i")
                if len(x) < 5:
                    continue
                I_ = x.i.values.astype(np.int64); S = x.side.values.astype(np.int64)
                A = a[I_]; px = c[I_]
                cost = np.asarray(np.array([CM.cost_points(market, inst, p) for p in px]) if market == "MCX" else CM.cost_points(market, inst, px), np.float64)
                inv = x.inv.values.astype(np.float64); trig = x.level.values.astype(np.float64)
                dist_inv = np.clip(np.abs(px - inv) + 0.1 * A, 0.3 * A, 3 * A)
                # control bars
                ci = np.array([rng.choice(pool[key[i]]) if key[i] in pool else i for i in I_], np.int64)
                ci = np.sort(ci)
                pxc = c[ci]
                costc = np.asarray(np.array([CM.cost_points(market, inst, p) for p in pxc]) if market == "MCX" else CM.cost_points(market, inst, pxc), np.float64)
                per = np.where(day[I_] < np.datetime64(v0), "DEV", np.where(day[I_] < np.datetime64(o0), "VALID", "OOS"))
                perc = np.where(day[ci] < np.datetime64(v0), "DEV", np.where(day[ci] < np.datetime64(o0), "VALID", "OOS"))
                for em, sm, xm in EXECS:
                    d = dist_inv if sm == "inv" else 1.5 * A
                    ent_ref = np.where(em == 0, o[np.minimum(I_ + 1, len(o) - 1)], trig)
                    stop = ent_ref - S * d
                    tg = 2.0 if xm == "2R" else 0.0; tr = 2.0 if xm == "trail" else 0.0
                    for cm in (1.0, 2.0):
                        res = EX.run_stream(o, h, l, c, I_, S, stop, dl[I_], cost, A, trig, inv, tg, tr, em, cm)
                        dc = np.median(d / A) * a[ci]
                        sc = o[np.minimum(ci + 1, len(o) - 1)] - S[:len(ci)] * dc
                        resc = EX.run_stream(o, h, l, c, ci, S[:len(ci)], sc, dl[ci], costc, a[ci], trig, inv, tg, tr, 0, cm)
                        for P in ("DEV", "VALID", "OOS"):
                            m = (per == P) & ~np.isnan(res[:, 0]); mc = (perc == P) & ~np.isnan(resc[:, 0])
                            out.append(dict(market=market, inst=inst, tf=tf, fam=r["fam"], name=r["name"], side=r["side"],
                                            sw=r["sw"], entry=em, stop=sm, exit=xm, cost=cm, period=P,
                                            n=int(m.sum()), sumR=float(res[m, 0].sum()), n_ctl=int(mc.sum()),
                                            sumR_ctl=float(resc[mc, 0].sum())))
    return pd.DataFrame(out)


def main(which, top=6):
    mk = {"mcx": "MCX", "nse_fut": "NSE_FUT", "nse_eq": "NSE_EQ"}[which]
    F = pd.read_csv(OUT / f"stage1_families_{which}.csv")
    F = F[F.nd_DEV >= 100].sort_values("t_DEV", ascending=False).head(top)
    rows = [dict(fam=r.fam, name=r.name, side=int(r.side), tf=int(r.tf), sw="*") for r in F.itertuples()]
    print("diagnostic rows:", rows, flush=True)
    insts = B.MCX7 if mk == "MCX" else (B.nse_eq_symbols() if mk == "NSE_EQ" else
                                         sorted(p.name.split("_ONE_HOUR")[0] for p in (ROOT / "research/data/angel/NFO_STK").glob("*_ONE_HOUR.csv")))
    R = run_rows(mk, rows, insts)
    R.to_csv(OUT / f"stage2_diag_{which}.csv", index=False)
    g = R.groupby(["name", "side", "tf", "entry", "stop", "exit", "cost", "period"])[["n", "sumR", "n_ctl", "sumR_ctl"]].sum()
    g["R"] = g.sumR / g.n; g["R_ctl"] = g.sumR_ctl / g.n_ctl
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    x = g.reset_index()
    x = x[x.cost == 1.0].pivot_table(index=["name", "side", "tf", "entry", "stop", "exit"], columns="period", values=["R", "R_ctl", "n"])
    print(x.round(3).to_string())


if __name__ == "__main__":
    main((sys.argv[1:] or ["mcx"])[0], int((sys.argv[2:] or [6])[0]))
