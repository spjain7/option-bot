"""CRSB-004 independent pre-history test of the FROZEN Crude 30m S/R breakout BUY.
All selection (MCXE-002 walk-forward, candidate pick) used 5-minute data from 2023-09-27. The stitched front-month
15-minute series starts 2020-10-12, so 2020-10 .. 2023-09 was never seen by any selection step.
The engine executes on 5-minute bars, so each 15-minute bar is split into three pseudo 5-minute bars:
  bar 1 = the full 15m O/H/L/C (whole range in the first sub-bar), bars 2-3 = flat at the 15m close.
This is coarse: stop-entry and stop-out inside one 15m bar collapse into one sub-bar, and the engine's conservative rule
(trigger and invalidation in the same bar -> no trade) then skips the trade. VALIDATION: the same construction is applied
to the 15m bars resampled from real 5m data (2023-09 .. 2026-11) and compared with the real 5m result.
Roll handling: stitched front month, not back-adjusted; roll ('switch') days are excluded from signals by the engine; we
also report trades within 5 sessions after a roll (S/R levels may straddle the roll gap).
python research/program/crsb_prehist.py"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import crude_srbrk as K, mcx_engine as E, mcx_disc as MD  # noqa: E402

OUT = ROOT / "research/program/results"


def pseudo5(f15):
    f = f15[["time", "open", "high", "low", "close", "volume", "switch"]].reset_index(drop=True)
    parts = []
    for k in range(3):
        g = f.copy()
        g["time"] = g.time + pd.Timedelta(minutes=5 * k)
        if k:
            g["open"] = g["high"] = g["low"] = f.close
            g["volume"] = 0
        else:
            g["volume"] = f.volume
        parts.append(g)
    return pd.concat(parts).sort_values("time", kind="stable").drop_duplicates("time").reset_index(drop=True)


def run_on(base5, lo, hi):
    """patch the 5m loader, run MD.prep + engine on base5 restricted to [lo, hi)."""
    orig_load, orig_ge = MD.LM.load, None
    b = base5[(base5.time >= lo) & (base5.time < hi)].reset_index(drop=True)

    def fake(name, iv):
        return b.copy() if iv == "FIVE_MINUTE" else orig_load(name, iv)
    MD.LM.load = fake
    try:
        src = MD.prep.__code__
        P = prep_any(b)
    finally:
        MD.LM.load = orig_load
    d5 = P[0]
    C = dict(P=P, d5=d5, D=E.setups_for("CRUDEOIL", P),
             arr=tuple(d5[x].values.astype(np.float64) for x in ("open", "high", "low", "close")),
             cost=np.array([MD.real_cost("CRUDEOIL", p) for p in d5.close.values]))
    X = K.frozen_trades(C)
    return X, P


def prep_any(d):
    """MD.prep without its hard-coded >= 2023 cut (identical otherwise)."""
    orig = MD.LM.load
    MD.LM.load = lambda name, iv: d.copy()
    src_cut = pd.Timestamp("1900-01-01")
    try:
        import inspect
        code = inspect.getsource(MD.prep).replace('d = d[d.time >= "2023-01-01"].reset_index(drop=True)', "d = d.reset_index(drop=True)")
        ns = dict(MD.__dict__)
        exec(code, ns)
        return ns["prep"]("CRUDEOIL")
    finally:
        MD.LM.load = orig


def after_roll(X, P, k=5):
    d5, sw = P[0], P[5]
    days = sorted(d5.day.unique()); pos = {d: i for i, d in enumerate(days)}
    swi = sorted(pos[s] for s in sw if s in pos)
    out = []
    for dy in X.day:
        i = pos[dy]; prev = [s for s in swi if s <= i]
        out.append(bool(prev) and i - prev[-1] <= k)
    return np.array(out, bool)


def main():
    f15 = MD.LM.load("CRUDEOIL", "FIFTEEN_MINUTE")
    real5 = MD.LM.load("CRUDEOIL", "FIVE_MINUTE")
    res = {}
    # validation on the overlap: real 5m vs pseudo-5m from 15m resampled from that same real 5m
    lo_v, hi_v = pd.Timestamp("2023-09-27"), pd.Timestamp("2026-11-04")
    Xr, Pr = run_on(real5, lo_v, hi_v)
    r15 = MD.LM.resample(real5[(real5.time >= lo_v) & (real5.time < hi_v)], 15).reset_index(drop=True)
    r15["time"] = r15.time.dt.floor("15min")
    Xp, _ = run_on(pseudo5(r15), lo_v, hi_v)
    res["validation_real5m"] = K.stats(Xr.net.values)
    res["validation_pseudo5m"] = K.stats(Xp.net.values)
    m = pd.merge(Xr[["day", "end", "net"]], Xp[["day", "end", "net"]], on=["day", "end"], suffixes=("_real", "_pseudo"))
    res["validation_matched_signals"] = dict(n=len(m), corr=round(float(m.net_real.corr(m.net_pseudo)), 3),
                                             mean_real=round(m.net_real.mean(), 3), mean_pseudo=round(m.net_pseudo.mean(), 3))
    print("validation", json.dumps({k: res[k] for k in res}, default=str), flush=True)
    # independent pre-history 2020-10-12 .. 2023-09-26 (warm-up: first 3 months used for indicators only)
    lo, hi = pd.Timestamp("2020-10-12"), pd.Timestamp("2023-09-27")
    Xh, Ph = run_on(pseudo5(f15), lo, hi)
    Xh = Xh[Xh.day >= pd.Timestamp("2021-01-01")]
    ar = after_roll(Xh, Ph)
    res["prehist_2021_to_2023-09"] = dict(all=K.stats(Xh.net.values), ci=K.boot(Xh.net.values) if len(Xh) > 5 else None,
                                         stress_costs_x2=K.stats(K.frozen_trades(dict(P=Ph, d5=Ph[0], D=E.setups_for("CRUDEOIL", Ph),
                                             arr=tuple(Ph[0][x].values.astype(np.float64) for x in ("open", "high", "low", "close")),
                                             cost=np.array([MD.real_cost("CRUDEOIL", p) for p in Ph[0].close.values])), cost_mult=2)
                                             .query("day >= '2021-01-01'").net.values),
                                         by_year={int(y): K.stats(g.net.values) for y, g in Xh.groupby(Xh.day.dt.year)},
                                         within_5_sessions_after_roll=K.stats(Xh.net.values[ar]),
                                         other=K.stats(Xh.net.values[~ar]))
    Xh[["day", "end", "trig", "inv", "atr", "gross", "costR", "net"]].to_csv(OUT / "crsb_prehist_trades.csv", index=False)
    (OUT / "crsb_prehist.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
