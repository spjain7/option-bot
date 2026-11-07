"""MCXE-011: 15-minute / 1-hour breakout-breakdown screen – only variants NOT tested in MCXE-005..010 (exploratory: DEV +
VALID only, OOS masked; VALID is not fresh). Hypothesis (from the one effect that held: H1.12L): breakouts work when held
across sessions with a wide trailing stop, not as same-day trades.
  MCX 15m  : Donchian N in {20, 40, 80} (80 x 15m ~ H1.12L's 20 hours), 2 ATR stop, 4 ATR trail, cap 960 bars (~16 sessions)
  STK 1h   : Donchian N in {20, 40}, 2 ATR stop, 4 ATR trail, cap 112 bars (~16 sessions), point-in-time stock futures
Long and short separately; same freeze bar as MCXE-007 (>= 30 trades / 20 dates per period, 2x > 0 in both, DEV+VALID CI
lower > 0, top-5 removal >= 0, no instrument > 50 %), then a random-entry control.
python research/mcxe011/intraday_bo.py -> research/mcxe011/RESULTS.csv"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe005 import frames as FR  # noqa: E402
from research.mcxe006 import engine as EN6  # noqa: E402
from research.mcxe007 import engine7 as E7, strat7 as S7  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402

OUT = ROOT / "research/mcxe011"


def mcx15():
    from research.program import mcx_disc as MD
    out = []
    for n in FR.MCX7:
        f = FR.mcx_positional(n, 15, FR.mcx_base(n))
        f.attrs.update(kind="MCX", wkey="MCX", mult=MD.REG[n]["mult"]); out.append(f)
    return out


def stk1h():
    fs = EN6.frames("NSE_FUT_I", 60)
    for f in fs:
        f.attrs.update(kind="STK", wkey="NSE_FUT_INTRADAY")
    return [f for f in fs if f is not None and len(f) > 300]


def summ(T):
    r = {}
    for P in ("DEV", "VALID"):
        x = T[T.period == P] if len(T) else T
        m1, m2 = E7.metrics(x, "r1", B=1000), E7.metrics(x, "r2", B=1000)
        r.update({f"{P}_n": m1.get("n", 0), f"{P}_dates": m1.get("dates", 0), f"{P}_win": m1.get("win"), f"{P}_exp2": m2.get("exp"),
                  f"{P}_pf": m1.get("pf"), f"{P}_cost": round(float(x.cost_R.mean()), 3) if len(x) else None})
    x = T[T.period.isin(["DEV", "VALID"])] if len(T) else T
    m = E7.metrics(x, "r1", B=1000); m2 = E7.metrics(x, "r2", B=1000)
    r.update(DV_ci_lo=m.get("ci_lo"), DV_ci_hi=m.get("ci_hi"), DV_wo_top5=m2.get("wo_top5"), **E7.concentration(x) if len(x) else {})
    r["eligible"] = bool(all((r[f"{P}_n"] or 0) >= 30 and (r[f"{P}_dates"] or 0) >= 20 and (r[f"{P}_exp2"] or -1) > 0 for P in ("DEV", "VALID"))
                         and (r["DV_ci_lo"] or -1) > 0 and (r["DV_wo_top5"] or -1) >= 0 and 0 <= (r.get("max_inst_share") or -1) <= 0.5)
    return r


def control(fs, T, exitp, side, seeds=20):
    want = T.groupby(["inst", "period"]).size().to_dict(); by = {f.attrs["name"]: f for f in fs}; res = []
    for s in range(seeds):
        rng = np.random.default_rng(300 + s)

        def fn(f, side, extra=None, **k):
            n = len(f); sig = np.zeros(n, bool); per = np.asarray(W.period(f.time, f.attrs["wkey"]))
            for P in ("DEV", "VALID"):
                kk = want.get((f.attrs["name"], P), 0); cand = np.flatnonzero((per == P) & f.sig_ok.values.astype(bool) & (np.arange(n) >= 100))
                if kk and len(cand):
                    sig[rng.choice(cand, min(kk, len(cand)), replace=False)] = True
            return dict(sig=sig, warm=100, entry="open")
        C = E7.run([by[x] for x in T.inst.unique()], fn, {}, exitp, side)
        res.append(C[C.period.isin(["DEV", "VALID"])].r2.mean())
    return round(float(np.nanmean(res)), 4), round(float(np.nanpercentile(res, 95)), 4)


def main():
    rows = []
    for mk, load, Ns, exitp in (("MCX_15m", mcx15, (20, 40, 80), dict(k=2.0, trail=4.0, maxbars=960)),
                                ("STK_1h", stk1h, (20, 40), dict(k=2.0, trail=4.0, maxbars=112))):
        fs = load()
        for N in Ns:
            for side in (1, -1):
                T = E7.run(fs, S7.dc, dict(n=N), exitp, side)
                r = dict(market=mk, rule=f"Donchian-{N} close {'breakout BUY' if side > 0 else 'breakdown SELL'}", N=N,
                         side="BUY" if side > 0 else "SELL", exit="2ATR stop, 4ATR trail", **summ(T))
                if r["eligible"]:
                    r["random_2x"], r["random_p95"] = control(fs, T, exitp, side)
                    r["beats_random_p95"] = (T[T.period.isin(["DEV", "VALID"])].r2.mean() > r["random_p95"])
                rows.append(r); print({k: r[k] for k in ("market", "rule", "DEV_n", "DEV_exp2", "VALID_n", "VALID_exp2", "VALID_win", "DV_ci_lo", "eligible")}, flush=True)
        pd.DataFrame(rows).to_csv(OUT / "RESULTS.csv", index=False)


if __name__ == "__main__":
    main()
