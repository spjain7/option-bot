"""MCXE-003 pre-registered STAGE 2 for the daily stage-1 survivors (MCX COPPER 20-day breakout BUY; NSE_FUT ZEEL NR7 breakdown SELL; both 5-session).
Execution menu (PREREGISTRATION.md): entry {next open, stop at trigger within 3 bars, cancelled if invalidation trades
first} x stop {invalidation +-0.1 ATR clamped 0.3-3 ATR, 1.5 ATR} x exit {2R, time stop 12 sessions, 2-ATR trail};
never across a contract roll (forced exit at the close before the roll day); costs 1x / 2x; one position at a time.
Choose on DEV+VALID (best mean net R at 2x cost, n >= 30), freeze, then OOS once. Matched control: random non-roll days
of the same commodity and period, market entry, stop distance = the event's median stop distance in ATR, same exit.
Day-block bootstrap CI of OOS net R. python research/mcxe003/stage2_daily.py"""
import json
import sys
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe003 import daily as D, execution as EX, cost_model as CM  # noqa: E402

OUT = ROOT / "research/mcxe003/results"
SURV = [("MCX", "COPPER", "NBAR_BRK", 1, "-"), ("NSE_FUT", "ZEEL", "NR7_BRK", -1, "-")]
EXECS = list(product((0, 1), ("inv", "atr"), ("2R", "time", "trail")))


def frames_for(market, inst):
    if market == "MCX":
        return {k: (d, e, b) for k, d, e, b in D.mcx_frames()}[inst]
    from research.adapters import nse_stkfut_pit as NF
    orig = NF.load
    NF.load = lambda kinds=("STK",): (lambda X: X[X.symbol == inst])(orig(kinds=kinds))
    try:
        return {k: (d, e, b) for k, d, e, b in D.fut_frames()}[inst]
    finally:
        NF.load = orig


def main(seed=20261107):
    rng = np.random.default_rng(seed)
    allout = {}
    for market, inst, name, side, sw in SURV:
        res, rows = {}, []
        d, elig, bad = frames_for(market, inst)
        f = D.finish(d.copy()); f.attrs.update(market=market, name=inst)
        E = D.events(f); E["i"] = E.i.astype(np.int64)
        E = E[(E.name == name) & (E.side == side) & (E.sw == sw)]
        E = E[elig[E.i.values]].drop_duplicates("i").sort_values("i")
        o, h, l, c, a = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close", "atr"))
        n = len(c); roll = np.where(bad)[0]
        def iend(i):                                               # noqa: E306
            nxt = roll[roll > i]
            lim = (nxt[0] - 1) if len(nxt) else n - 1
            return min(i + 12, lim)
        I_ = E.i.values; S = np.full(len(I_), side, np.int64); A = a[I_]
        IE = np.array([iend(i) for i in I_], np.int64)
        cpts = (lambda P: np.array([CM.cost_points("MCX", inst, p) for p in P])) if market == "MCX" else (lambda P: CM.cost_points(market, inst, P))
        cost = cpts(c[I_])
        inv = E.inv.values; trig = E.level.values
        per = np.where(f.time.values[I_] < np.datetime64(D.V0), "DEV", np.where(f.time.values[I_] < np.datetime64(D.O0), "VALID", "OOS"))
        perf = np.where(f.time.values < np.datetime64(D.V0), "DEV", np.where(f.time.values < np.datetime64(D.O0), "VALID", "OOS"))
        ok_ctl = np.where(elig & ~np.isnan(a))[0]
        for em, sm, xm in EXECS:
            dist = np.clip(np.abs(c[I_] - inv) + 0.1 * A, 0.3 * A, 3 * A) if sm == "inv" else 1.5 * A
            ref = o[np.minimum(I_ + 1, n - 1)] if em == 0 else trig
            stop = ref - S * dist
            tg = 2.0 if xm == "2R" else 0.0; tr = 2.0 if xm == "trail" else 0.0
            for cm in (1.0, 2.0):
                R = EX.run_stream(o, h, l, c, I_, S, stop, IE, cost, A, trig, inv, tg, tr, em, cm)
                # control: per event a random eligible day of the same period
                ci = np.sort(np.array([rng.choice(ok_ctl[perf[ok_ctl] == p]) for p in per], np.int64))
                dc = np.median(dist / A) * a[ci]
                sc = o[np.minimum(ci + 1, n - 1)] - side * dc
                cc = cpts(c[ci])
                Rc = EX.run_stream(o, h, l, c, ci, S, sc, np.array([iend(i) for i in ci], np.int64), cc, a[ci], trig, inv, tg, tr, 0, cm)
                perc = perf[ci]
                for P in ("DEV", "VALID", "OOS", "DV"):
                    m = ((per == P) if P != "DV" else (per != "OOS")) & ~np.isnan(R[:, 0])
                    mc = ((perc == P) if P != "DV" else (perc != "OOS")) & ~np.isnan(Rc[:, 0])
                    rows.append(dict(inst=inst, name=name, side=side, entry=em, stop=sm, exit=xm, cost=cm, period=P,
                                     n=int(m.sum()), R=float(np.nanmean(R[m, 0])) if m.any() else np.nan,
                                     n_ctl=int(mc.sum()), R_ctl=float(np.nanmean(Rc[mc, 0])) if mc.any() else np.nan))
                if cm == 1.0:
                    res[(em, sm, xm)] = (R, I_, per)
        T = pd.DataFrame(rows)
        T.to_csv(OUT / f"stage2_daily_{market}_{inst}.csv", index=False)
        sel = T[(T.period == "DV") & (T.cost == 2.0) & (T.n >= 30)].sort_values("R", ascending=False).iloc[0]
        key = (int(sel.entry), sel.stop, sel.exit)
        R, I_, per = res[key]
        o_ = (per == "OOS") & ~np.isnan(R[:, 0]); x = R[o_, 0]
        bs = [np.mean(np.random.default_rng(k).choice(x, len(x))) for k in range(5000)] if len(x) else [np.nan]
        pick = T[(T.entry == key[0]) & (T.stop == key[1]) & (T.exit == key[2])]
        out = dict(frozen_choice=dict(entry=["next open", "stop at trigger"][key[0]], stop=key[1], exit=key[2],
                                      DV_net_R_2x=round(float(sel.R), 3), DV_n=int(sel.n)),
                   OOS=pick[pick.period == "OOS"][["cost", "n", "R", "n_ctl", "R_ctl"]].round(3).to_dict("records"),
                   OOS_ci95_1x=[round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)],
                   all_periods=pick[pick.cost == 1.0][["period", "n", "R", "R_ctl"]].round(3).to_dict("records"))
        allout[f"{market} {inst} {name} {'BUY' if side > 0 else 'SELL'}"] = out
        print(json.dumps(out, indent=1))
        print(T[(T.cost == 1.0)].pivot_table(index=["entry", "stop", "exit"], columns="period", values="R").round(3).to_string())
    (OUT / "stage2_daily.json").write_text(json.dumps(allout, indent=1))


if __name__ == "__main__":
    main()
