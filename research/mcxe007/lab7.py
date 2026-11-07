"""MCXE-007 lab (development mode – OOS masked). Experiments in exp7.py; each is run for BUY (/L) and SELL (/S) separately.
  python research/mcxe007/lab7.py run A0 A1 ...        python research/mcxe007/lab7.py fam A B
  python research/mcxe007/lab7.py controls A0/L ...    random-entry + market-direction controls (DEV+VALID)
Register: research/mcxe007/EXPERIMENT_REGISTER.csv; trades: results/trades_<id>.parquet (git-ignored)."""
import json
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe007 import engine7 as EN, strat7 as ST, data7 as DA  # noqa: E402
from research.mcxe007.exp7 import EXPS  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402

D = ROOT / "research/mcxe007"
REGF = D / "EXPERIMENT_REGISTER.csv"
_EX = {}


def extra():
    if "x" not in _EX:
        _EX["x"] = dict(nifty=DA.nifty())
    return _EX["x"]


def commit():
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "?"


def run_exp(e, side, oos=False, log=False):
    fs = DA.frames(e["market"])
    if e.get("insts"):
        fs = [f for f in fs if f.attrs["name"] in e["insts"]]
    out = EN.run(fs, ST.REG[e["fn"]], e.get("params", {}), e.get("exit", {}), side, oos=oos, extra=extra(), log_signals=log)
    if e.get("hedge"):
        T = out[0] if log else out
        T = hedge(T)
        out = (T, out[1]) if log else T
    return out


def hedge(T):
    """beta-1 NIFTY futures hedge: equal notional opposite position in NIFTY from the stock's entry (open) to its exit
    date (close; a stop inside the day is approximated by that day's NIFTY close). Hedge P&L in R = -side x NIFTY
    return / risk_pct; hedge costs = NIFTY round-trip cost fraction / risk_pct (and 2x for r2)."""
    if not len(T):
        return T
    from research import instruments as INS
    N = [f for f in DA.frames("IDX") if f.attrs["name"] == "NIFTY"][0]
    o = pd.Series(N.open.values, index=N.time.dt.normalize()); c = pd.Series(N.close.values, index=N.time.dt.normalize())
    ne = T.entry_date.dt.normalize().map(o).values.astype(float); nx = T.exit_date.dt.normalize().map(c).values.astype(float)
    ret = nx / ne - 1
    cf = INS.cost_points("NIFTY", float(np.nanmedian(ne))) / float(np.nanmedian(ne))
    h = -T.side.values * ret / T.risk_pct.values
    hc = cf / T.risk_pct.values
    T = T.copy()
    ok = np.isfinite(h)
    T["hedge_R"] = h
    T["r1"] = T.r1 + h - hc; T["r2"] = T.r2 + h - 2 * hc; T["gross"] = T.gross + h; T["cost_R"] = T.cost_R + hc
    T["rs_net_1x"] = T.r1 * T.rs_per_R
    return T[ok].reset_index(drop=True)


def summ(T):
    out = {}
    for P in ("DEV", "VALID"):
        x = T[T.period == P] if len(T) else T
        m1, m2 = EN.metrics(x, "r1"), EN.metrics(x, "r2")
        days = W.get(DA.WKEY[T.market.iat[0]] if len(T) else "MCX")
        out[P] = dict(m1, exp2=m2.get("exp"), cost_R=round(float(x.cost_R.mean()), 3) if len(x) else np.nan,
                      gross=round(float(x.gross.mean()), 3) if len(x) else np.nan,
                      stop_pct=round(100 * x.etype.isin(["stop", "gap", "stop_fillbar"]).mean(), 1) if len(x) else np.nan,
                      tgt_pct=round(100 * (x.etype == "target").mean(), 1) if len(x) else np.nan,
                      rs_per_trade=round(float(x.rs_net_1x.mean()), 0) if len(x) else np.nan,
                      hold=round(float(x.hold.mean()), 1) if len(x) else np.nan)
    x = T[T.period.isin(["DEV", "VALID"])] if len(T) else T
    m = EN.metrics(x, "r1"); m2 = EN.metrics(x, "r2")
    out["DV"] = dict(n=m.get("n", 0), exp=m.get("exp"), exp2=m2.get("exp"), ci_lo=m.get("ci_lo"), ci_hi=m.get("ci_hi"),
                     wo_top1=m2.get("wo_top1"), wo_top3=m2.get("wo_top3"), wo_top5=m2.get("wo_top5"), insts=int(x.inst.nunique()) if len(x) else 0,
                     **EN.concentration(x))
    return out


def decide(row, reg):
    par = row["parent"]
    if not par:
        return "BASELINE", "family baseline"
    p = reg[reg.id == par]
    if not len(p):
        return "COMPARE?", f"parent {par} not run"
    p = p.iloc[-1]
    f = lambda v: -9 if (v is None or (isinstance(v, float) and np.isnan(v))) else v  # noqa: E731
    d_dev = f(row["DEV_exp2"]) - f(p["DEV_exp2"]); d_val = f(row["VALID_exp2"]) - f(p["VALID_exp2"])
    tag = "KEEP" if (d_dev > 0 and d_val >= -0.005) else "DROP"
    return tag, f"DEV 2x {d_dev:+.3f}R, VALID 2x {d_val:+.3f}R vs {par}"


def eligible(r):
    """pre-registered freeze bar except the control tests (run separately by `controls`)."""
    g = lambda k: r.get(k) if r.get(k) is not None and not (isinstance(r.get(k), float) and np.isnan(r.get(k))) else -9  # noqa: E731
    ok = all(g(f"{P}_n") >= 20 and g(f"{P}_dates") >= 15 and g(f"{P}_exp2") > 0 for P in ("DEV", "VALID"))
    return bool(ok and g("DV_ci_lo") > 0 and g("DV_wo_top5") >= 0 and 0 <= g("DV_max_inst_share") <= 0.5)


def main(ids):
    cm = commit()
    for i in ids:
        e = EXPS[i]
        for side, sfx in ((1, "L"), (-1, "S")):
            if e.get("side") and e["side"] != side:
                continue
            rid = f"{i}/{sfx}"
            t0 = time.time()
            T = run_exp(e, side)
            if len(T):
                T.to_parquet(D / "results" / f"trades_{rid.replace('/', '_')}.parquet", index=False)
            S = summ(T) if len(T) else {"DEV": {}, "VALID": {}, "DV": {}}
            row = dict(id=rid, parent=(f"{e['parent']}/{sfx}" if e.get("parent") else ""), family=e["fam"], hypothesis=e["hyp"],
                       market=e["market"], side="BUY" if side > 0 else "SELL", entry=f"{e['fn']}({json.dumps(e.get('params', {}))})",
                       exit=json.dumps(e.get("exit", {})), change=e.get("change", ""),
                       costs="MCX: fees+1.5 tick/side; STK: fees+0.05%/side; IDX: fees+index slip pts; also 2x",
                       boundaries="MCX DEV 2025-11-04–2026-05-04, VALID –08-04 | NSE DEV 2025-11-07–2026-05-07, VALID –08-07 | OOS masked")
            for P in ("DEV", "VALID"):
                for k in ("n", "dates", "win", "avg_win", "avg_loss", "exp", "exp2", "pf", "dd", "ci_lo", "ci_hi", "cost_R", "gross", "stop_pct",
                          "tgt_pct", "rs_per_trade", "hold"):
                    row[f"{P}_{k}"] = S[P].get(k)
            for k, v in S["DV"].items():
                row[f"DV_{k}"] = v
            cur = pd.read_csv(REGF) if REGF.exists() else pd.DataFrame(columns=["id"])
            row["decision"], row["reason"] = decide(row, cur)
            row["freeze_eligible_pre_controls"] = eligible(row)
            row["commit"] = cm; row["secs"] = round(time.time() - t0)
            reg = pd.concat([cur[cur.id != rid], pd.DataFrame([row])], ignore_index=True)
            reg.to_csv(REGF, index=False)
            print(f"{rid:9s} {row['decision']:8s} DEV n={row['DEV_n']} d={row['DEV_dates']} win={row['DEV_win']} 2x={row['DEV_exp2']} g={row['DEV_gross']} "
                  f"c={row['DEV_cost_R']} | VALID n={row['VALID_n']} d={row['VALID_dates']} win={row['VALID_win']} 2x={row['VALID_exp2']} pf={row['VALID_pf']} "
                  f"| DV ci [{row.get('DV_ci_lo')},{row.get('DV_ci_hi')}] wo5={row.get('DV_wo_top5')} inst%={row.get('DV_max_inst_share')} "
                  f"elig={row['freeze_eligible_pre_controls']}", flush=True)


def controls(rid, seeds=30):
    """random-entry (same instruments, side, per-instrument counts, periods, exits) and, for NSE, market-direction
    (same signal dates and side, traded on NIFTY futures) – DEV + VALID only."""
    i, sfx = rid.split("/"); e = EXPS[i]; side = 1 if sfx == "L" else -1
    T = pd.read_parquet(D / "results" / f"trades_{rid.replace('/', '_')}.parquet")
    fs = {f.attrs["name"]: f for f in DA.frames(e["market"])}
    want = T.groupby(["inst", "period"]).size().to_dict()
    res = []
    for s in range(seeds):
        rng = np.random.default_rng(7000 + s)

        def rnd(f, side, extra=None, **kw):
            n = len(f); sig = np.zeros(n, bool)
            per = np.asarray(W.period(f.time, f.attrs["wkey"]))
            for P in ("DEV", "VALID"):
                k = want.get((f.attrs["name"], P), 0)
                cand = np.flatnonzero((per == P) & f.sig_ok.values.astype(bool) & (np.arange(n) >= 30))
                if k and len(cand):
                    sig[rng.choice(cand, size=min(k, len(cand)), replace=False)] = True
            return dict(sig=sig, warm=30, entry="open")
        C = EN.run([fs[x] for x in T.inst.unique()], rnd, {}, e.get("exit", {}), side, extra=extra())
        if e.get("hedge"):
            C = hedge(C)
        res.append(C.r2.mean() if len(C) else np.nan)
    out = dict(random_entry_exp2=round(float(np.nanmean(res)), 4), random_entry_p95=round(float(np.nanpercentile(res, 95)), 4))
    if e["market"] in ("STK", "IDX"):
        N = [f for f in DA.frames("IDX") if f.attrs["name"] == "NIFTY"][0]
        dates = set(pd.to_datetime(T.date).dt.normalize())

        def mk(f, side, extra=None, **kw):
            return dict(sig=f.time.dt.normalize().isin(dates).values, warm=0, entry="open")
        M = EN.run([N], mk, {}, e.get("exit", {}), side, extra=extra())
        out["market_direction_exp2"] = round(float(M.r2.mean()), 4) if len(M) else None
        out["market_direction_n"] = len(M)
    out["strategy_exp2"] = round(float(T[T.period.isin(["DEV", "VALID"])].r2.mean()), 4)
    out["beats_random"] = out["strategy_exp2"] > out["random_entry_exp2"]
    out["beats_market"] = (out.get("market_direction_exp2") is None) or (out["strategy_exp2"] > out["market_direction_exp2"])
    reg = pd.read_csv(REGF)
    for k, v in out.items():
        if k not in reg.columns:
            reg[k] = None
        reg[k] = reg[k].astype(object)
        reg.loc[reg.id == rid, k] = v
    reg.loc[reg.id == rid, "freeze_eligible"] = bool(reg.loc[reg.id == rid, "freeze_eligible_pre_controls"].iat[0]) and out["beats_random"] and out["beats_market"]
    reg.to_csv(REGF, index=False)
    print(rid, out, flush=True)
    return out


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    if cmd == "run":
        main(args)
    elif cmd == "fam":
        main([k for k, v in EXPS.items() if v["fam"] in args])
    elif cmd == "controls":
        for a in args:
            controls(a)
