"""MCXE-002 matched controls for walk-forward survivors (owner 6-Nov: "matched controls: same instrument, timeframe, signal
timestamps / session, trade count, execution and risk; multiple permutations and block shuffles; distributions,
percentile rank and confidence intervals").

For a stream and its walk-forward choices (results/mcxe2_wf_quarters.csv), per test quarter:
  ACTUAL   the chosen filter / entry / stop / exit applied to the stream's real signals (one position at a time)
  PERM     every real signal moved to a random OTHER trading day of the same quarter at the SAME time-of-day candle, same
           side, same risk in ATR units (invalidation = trigger -/+ risk_atr x ATR at the new candle), same execution
  BLOCK    all signals of the quarter shifted together by one random number of trading days (circular inside the quarter)
           -> keeps the clustering of signals, breaks their link to the market
N_PERM permutations each (stable seed per stream). Reported: actual mean net R, control mean / 5th / 95th percentile,
percentile rank of the actual (share of controls below it), bootstrap 95 % CI of the actual mean, for the walk-forward
test quarters and for the untouched OOS separately.
python research/program/mcx_controls.py"""
import json
import sys
import zlib
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_engine as E, mcx_disc as MD  # noqa: E402

OUT = ROOT / "research/program/results"
N_PERM = 200
SEED = E.SEED


def frames(P):
    d5, f15, f30, f60, dd, sw = P
    return {"15m": f15.reset_index(drop=True), "30m": f30.reset_index(drop=True), "60m": f60.reset_index(drop=True)}


def shifted(F, fr, tf, d5, eod_day, rng, mode, q_days):
    """build control setups from real setups F (same quarter) on timeframe frame fr."""
    if F.empty:
        return F
    t5 = d5.time.values
    day_of = fr.day.values; m_of = fr.m.values
    key = {}
    for idx, (dy, mm) in enumerate(zip(day_of, m_of)):
        key[(dy, mm)] = idx
    days = list(q_days)
    rows = []
    off = rng.integers(1, max(2, len(days))) if mode == "BLOCK" else None
    for r in F.itertuples():
        mm = m_of[r.i]
        if mode == "PERM":
            cand = [d for d in days if d != r.day and (d, mm) in key]
            if not cand:
                continue
            nd = cand[rng.integers(len(cand))]
        else:
            k = days.index(r.day) if r.day in days else 0
            nd = days[(k + off) % len(days)]
            if (nd, mm) not in key:
                continue
        j = key[(nd, mm)]
        a = fr.atr.values[j]
        if not a > 0:
            continue
        trig = fr.high.values[j] if r.side > 0 else fr.low.values[j]
        end = fr.time.values[j] + np.timedelta64(E.TFS[tf], "m")
        act = np.searchsorted(t5, end)
        if act >= len(d5) or d5.day.values[act] != nd or nd not in eod_day.index:
            continue
        eod = int(eod_day[nd])
        if act >= eod:
            continue
        rows.append(dict(act=act, side=r.side, trig=trig, inv=trig - r.side * r.risk_atr * a, atr=a, eod=eod,
                         last_entry=min(act + 3 * E.TFS[tf] // 5 - 1, eod - 1), day=nd))
    return pd.DataFrame(rows).sort_values("act", kind="stable") if rows else pd.DataFrame()


def boot_ci(x, rng, n=2000):
    if len(x) < 5:
        return (np.nan, np.nan)
    m = [rng.choice(x, len(x)).mean() for _ in range(n)]
    return (float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)))


def run_stream(stream, choices, cache):
    name, tf, fam, sub, side = stream
    if name not in cache:
        P = MD.prep(name)
        d5 = P[0]
        cache[name] = dict(P=P, d5=d5, D=E.setups_for(name, P), fr=frames(P),
                           eod=d5[d5.m <= 23 * 60].groupby("day").apply(lambda g: g.index[-1]),
                           arr=tuple(d5[x].values.astype(np.float64) for x in ("open", "high", "low", "close")),
                           cost=np.array([MD.real_cost(name, p) for p in d5.close.values]))
    C = cache[name]
    sd = 1 if side == "BUY" else -1
    S = C["D"][(C["D"].tf == tf) & (C["D"].fam == fam) & (C["D"]["sub"] == sub) & (C["D"].side == sd)]
    S = S.assign(qq=pd.PeriodIndex(S.day, freq="Q").astype(str))
    rng = np.random.default_rng((SEED + zlib.crc32("|".join(stream).encode())) % (2 ** 32))
    out = {}
    for part, qs in (("WF", [c for c in choices if c[0] != "OOS"]), ("OOS", [c for c in choices if c[0] == "OOS"])):
        actual, perm, block = [], np.zeros(N_PERM), np.zeros(N_PERM)
        pn, bn = np.zeros(N_PERM), np.zeros(N_PERM)
        for tq, ch in qs:
            if not ch:
                continue
            flt, en, sp, ex = ch.split("|")
            enc, spc = ("NXT", "STP").index(en), ("STR", "ATR").index(sp)
            exc = {"2R": 2.0, "3R": 3.0, "EOD": 0.0, "TRL": -1.0}[ex]
            qlist = ["2026Q3", "2026Q4"] if tq == "OOS" else [tq]
            Fq = E.apply_filter(S[S.qq.isin(qlist)], flt)
            if Fq.empty:
                continue
            X = E.simulate(Fq, C["arr"], C["cost"], enc, spc, exc)
            actual += list(X.gross - X.costR)
            qd = sorted(set(C["d5"].day[pd.PeriodIndex(C["d5"].day, freq="Q").astype(str).isin(qlist)]))
            for p in range(N_PERM):
                for mode, acc, cnt in (("PERM", perm, pn), ("BLOCK", block, bn)):
                    Ctl = shifted(Fq, C["fr"][tf], tf, C["d5"], C["eod"], rng, mode, qd)
                    if Ctl.empty:
                        continue
                    Y = E.simulate(Ctl, C["arr"], C["cost"], enc, spc, exc)
                    acc[p] += (Y.gross - Y.costR).sum(); cnt[p] += len(Y)
        x = np.array(actual)
        if not len(x):
            continue
        pm, bm = perm / np.maximum(pn, 1), block / np.maximum(bn, 1)
        lo, hi = boot_ci(x, rng)
        out[part] = dict(n=len(x), actual=float(x.mean()), ci_lo=lo, ci_hi=hi,
                         perm_mean=float(pm.mean()), perm_p5=float(np.percentile(pm, 5)), perm_p95=float(np.percentile(pm, 95)),
                         perm_rank=float((pm < x.mean()).mean()), block_mean=float(bm.mean()), block_p95=float(np.percentile(bm, 95)),
                         block_rank=float((bm < x.mean()).mean()), ctl_trades_per_perm=float(pn.mean()))
    return out


def main(top=None):
    A = pd.read_csv(OUT / "mcxe2_wf.csv")
    C = pd.read_csv(OUT / "mcxe2_wf_quarters.csv")
    good = A[(A.wf_n >= 60) & (A.wf_R > 0) & (A.wf_stress > 0) & (A.wf_quarters_pos >= 0.6 * A.wf_quarters_traded)].sort_values("wf_R", ascending=False)
    if top:
        good = good.head(top)
    cache, rows = {}, []
    for r in good.itertuples():
        st = (r.name, r.tf, r.fam, r.sub, r.side)
        ch = C[(C.name == r.name) & (C.tf == r.tf) & (C.fam == r.fam) & (C["sub"] == r.sub) & (C.side == r.side)]
        res = run_stream(st, list(zip(ch.test, ch.chosen.where(ch.chosen.notna(), None))), cache)
        for part, v in res.items():
            rows.append(dict(name=r.name, tf=r.tf, fam=r.fam, sub=r.sub, side=r.side, part=part, **v))
        print(st, {k: (round(v["actual"], 3), round(v["perm_rank"], 3), round(v["block_rank"], 3), v["n"]) for k, v in res.items()}, flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(OUT / "mcxe2_controls.csv", index=False)
    (OUT / "mcxe2_controls_meta.json").write_text(json.dumps(dict(n_perm=N_PERM, seed=SEED, streams=len(good)), indent=1))
    return R


if __name__ == "__main__":
    main()
