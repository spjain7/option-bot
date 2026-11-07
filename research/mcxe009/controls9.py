"""MCXE-009 controls for the two exploratory standouts (DEV + VALID only): random-entry control (same instruments, same
per-instrument/period counts, same side and exits, 30 seeds) and, for stocks, NIFTY futures on the same signal dates.
Also: combined DEV+VALID CI, concentration, month split.  python research/mcxe009/controls9.py"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe009 import weighted as WT  # noqa: E402
from research.mcxe007 import engine7 as E7, data7 as DA7  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402

CANDS = [("STK_1d", "data_driven", 1, 0.6), ("MCX_1h", "equal", 1, 0.6)]


def main():
    mk_all = WT.markets(); res = {}
    wts = json.loads((WT.OUT / "results_weights.json").read_text())
    for mk, model, side, th in CANDS:
        load, exitp, H = mk_all[mk]
        fs = [f for f in load() if f is not None and len(f) > 80]
        comps = [WT.components(f) for f in fs]
        w = wts[mk] if model == "data_driven" else WT.FAMILIES[model]
        T = WT.run_model(fs, comps, w, th, side, exitp)
        T.to_parquet(WT.OUT / f"cand_{mk}_{model}.parquet", index=False)
        want = T.groupby(["inst", "period"]).size().to_dict(); byname = {f.attrs["name"]: f for f in fs}
        rnd = []
        for s in range(30):
            rng = np.random.default_rng(500 + s)

            def fn(f, side, extra=None, **kw):
                n = len(f); sig = np.zeros(n, bool); per = np.asarray(W.period(f.time, f.attrs["wkey"]))
                for P in ("DEV", "VALID"):
                    k = want.get((f.attrs["name"], P), 0)
                    cand = np.flatnonzero((per == P) & f.sig_ok.values.astype(bool) & (np.arange(n) >= 60))
                    if k and len(cand):
                        sig[rng.choice(cand, min(k, len(cand)), replace=False)] = True
                return dict(sig=sig, warm=60, entry="open")
            C = E7.run([byname[x] for x in T.inst.unique()], fn, {}, exitp, side)
            rnd.append({P: C[C.period == P].r2.mean() for P in ("DEV", "VALID")})
        R = pd.DataFrame(rnd)
        out = {P: dict(strategy_2x=round(float(T[T.period == P].r2.mean()), 4), random_2x=round(float(R[P].mean()), 4),
                       random_p95=round(float(R[P].quantile(0.95)), 4)) for P in ("DEV", "VALID")}
        if mk == "STK_1d":
            N = [f for f in DA7.frames("IDX") if f.attrs["name"] == "NIFTY"][0]
            for P in ("DEV", "VALID"):
                dates = set(T[T.period == P].date.dt.normalize())
                M = E7.run([N], lambda f, side, extra=None, **k: dict(sig=f.time.dt.normalize().isin(dates).values, warm=0), {}, exitp, side)
                out[P]["nifty_same_dates_2x"] = round(float(M[M.period == P].r2.mean()), 4) if len(M) else None
        DV = T[T.period.isin(["DEV", "VALID"])]
        m = E7.metrics(DV, "r1")
        out["DV"] = dict(n=m["n"], dates=m["dates"], ci=[m["ci_lo"], m["ci_hi"]], **E7.concentration(DV),
                         months={str(k): round(float(v), 2) for k, v in DV.groupby(DV.date.dt.to_period("M")).r2.sum().items()},
                         trades_per_date_max=int(DV.groupby(DV.date.dt.normalize()).size().max()))
        res[f"{mk}|{model}|{'BUY' if side > 0 else 'SELL'}|{th}"] = out
        print(mk, model, json.dumps(out), flush=True)
    (WT.OUT / "controls.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
