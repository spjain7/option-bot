"""MCXE-006 experiment lab. Experiments are declared in experiments.py (id, parent, family, hypothesis, universe, tf,
horizon, signal function + params, exit params, the one component changed). Development mode only (OOS masked).
  python research/mcxe006/lab.py run H1.0 H1.1 ...      run experiments, append/replace rows in EXPERIMENT_REGISTER.csv
  python research/mcxe006/lab.py fam H1                 run every experiment of a family
Trades per experiment -> results/trades_<id>.parquet (git-ignored, reproducible)."""
import json
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe006 import engine as EN, strategies as ST  # noqa: E402
from research.mcxe006.experiments import EXPS  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402

D = ROOT / "research/mcxe006"
REGF = D / "EXPERIMENT_REGISTER.csv"
_EXTRA = {}


def extra_for(universe):
    if universe in _EXTRA:
        return _EXTRA[universe]
    ex = None
    if universe in ("NSE_FUT_D", "NSE_FUT_I"):
        fs = EN.frames("NSE_FUT_D", 1440)
        ex = dict(breadth=EN.breadth(fs))
        ex.update(xs_panel(fs))
    elif universe in ("NSE_EQ_D", "NSE_EQ_I"):
        ex = dict(breadth=EN.breadth(EN.frames("NSE_EQ_D", 1440)))
    _EXTRA[universe] = ex
    return ex


def xs_panel(fs):
    """cross-sectional ranks of past returns (known at the close), only for instruments eligible that day."""
    C = {}; OK = {}
    for f in fs:
        idx = f.time.dt.normalize().values
        C[f.attrs["name"]] = pd.Series(f.close.values.astype(float), index=idx)
        OK[f.attrs["name"]] = pd.Series(f.sig_ok.values.astype(bool), index=idx)
    C = pd.DataFrame(C).sort_index(); OK = pd.DataFrame(OK).reindex(C.index).fillna(False).astype(bool)
    out = {}
    for lb in (5, 20, 60):
        r = C / C.shift(lb) - 1
        r = r.where(OK & r.notna())
        out[lb] = r.rank(axis=1, ascending=False)
    fri = pd.Series(C.index, index=C.index)
    wk = fri.groupby(pd.Index(C.index).to_period("W-FRI")).max().values     # last trading day of each week
    return dict(xs=out, xs_dates=set(pd.to_datetime(wk)))


def commit():
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "?"


def run_exp(e, oos=False):
    fs = []
    for tf in (e["tf"] if isinstance(e["tf"], (list, tuple)) else [e["tf"]]):
        fs += EN.frames(e["universe"], tf)
    if e.get("insts"):
        fs = [f for f in fs if f.attrs["name"] in e["insts"]]
    fn = ST.REG[e["fn"]]
    T = EN.run(fs, fn, e.get("params", {}), e.get("exit", {}), e["horizon"], oos=oos, extra=extra_for(e["universe"]))
    if len(T) and e.get("side_only"):
        T = T[T.side == e["side_only"]]
    return T


def flat(S, P):
    m = S.get(P, {})
    keys = ["n", "dates", "win", "avg_win", "avg_loss", "exp", "exp2", "pf", "dd", "ci_lo", "ci_hi", "cost_R", "gross", "stop_pct",
            "tgt_pct", "n_buy", "n_sell", "buy_exp2", "sell_exp2"]
    return {f"{P}_{k}": m.get(k) for k in keys}


def bounds(universe):
    w = W.get(EN.WKEY[universe])
    return f"DEV {w['start'].date()}–{w['valid_from'].date()}; VALID –{w['oos_from'].date()}; OOS {w['oos_from'].date()}–{w['reference'].date()} (masked in dev)"


def decide(row, reg):
    par = row["parent"]
    if not par:
        return "BASELINE", "family baseline"
    p = reg[reg.id == par]
    if not len(p):
        return "COMPARE?", f"parent {par} not run"
    p = p.iloc[-1]
    d_dev = (row["DEV_exp2"] or -9) - (p["DEV_exp2"] if pd.notna(p["DEV_exp2"]) else -9)
    d_val = (row["VALID_exp2"] or -9) - (p["VALID_exp2"] if pd.notna(p["VALID_exp2"]) else -9)
    if d_dev > 0 and d_val >= -0.005:
        return "KEEP", f"DEV 2x {d_dev:+.3f}R, VALID 2x {d_val:+.3f}R vs {par}"
    return "DROP", f"DEV 2x {d_dev:+.3f}R, VALID 2x {d_val:+.3f}R vs {par}"


def eligible(row, horizon):
    nmin, dmin = (20, 15) if horizon == "positional" else (30, 20)
    ok = all((row.get(f"{P}_n") or 0) >= nmin and (row.get(f"{P}_dates") or 0) >= dmin and (row.get(f"{P}_exp2") or -1) > 0
             for P in ("DEV", "VALID"))
    return bool(ok and (row.get("DV_ci_lo") or -1) > 0)


def main(ids):
    reg = pd.read_csv(REGF) if REGF.exists() else pd.DataFrame(columns=["id"])
    cm = commit()
    for i in ids:
        e = EXPS[i]
        t0 = time.time()
        T = run_exp(e)
        T.to_parquet(D / "results" / f"trades_{i.replace('/', '_')}.parquet", index=False)
        S = EN.summary(T)
        row = dict(id=i, parent=e.get("parent", ""), family=e["fam"], hypothesis=e["hyp"], market=e["universe"],
                   tf=json.dumps(e["tf"]), horizon=e["horizon"], entry=f"{e['fn']}({json.dumps(e.get('params', {}))})",
                   exit=json.dumps(e.get("exit", {})), side=("BUY" if e.get("side_only") == 1 else "SELL" if e.get("side_only") == -1 else "both"),
                   change=e.get("change", ""), costs="1x realistic (MCXE-003 cost_model) and 2x", boundaries=bounds(e["universe"]),
                   **flat(S, "DEV"), **flat(S, "VALID"),
                   DV_n=S["DV"]["n"], DV_exp=S["DV"]["exp"], DV_ci_lo=S["DV"]["ci_lo"], DV_ci_hi=S["DV"]["ci_hi"])
        reg = pd.read_csv(REGF) if REGF.exists() else reg
        row["decision"], row["reason"] = decide(row, reg)
        row["freeze_eligible"] = eligible(row, e["horizon"])
        row["commit"] = cm; row["secs"] = round(time.time() - t0)
        cur = pd.read_csv(REGF) if REGF.exists() else pd.DataFrame(columns=["id"])   # re-read: other runs may have written
        reg = pd.concat([cur[cur.id != i], pd.DataFrame([row])], ignore_index=True)
        reg.to_csv(REGF, index=False)
        print(f"{i:8s} {row['decision']:8s} DEV n={row['DEV_n']} d={row['DEV_dates']} win={row['DEV_win']} exp={row['DEV_exp']} 2x={row['DEV_exp2']} "
              f"g={row['DEV_gross']} c={row['DEV_cost_R']} pf={row['DEV_pf']} | VALID n={row['VALID_n']} win={row['VALID_win']} exp={row['VALID_exp']} "
              f"2x={row['VALID_exp2']} pf={row['VALID_pf']} | B/S dev {row['DEV_buy_exp2']}/{row['DEV_sell_exp2']} val {row['VALID_buy_exp2']}/{row['VALID_sell_exp2']} "
              f"| DVci [{row['DV_ci_lo']},{row['DV_ci_hi']}] elig={row['freeze_eligible']} {row['secs']}s", flush=True)


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    if cmd == "run":
        main(args)
    elif cmd == "fam":
        main([k for k, v in EXPS.items() if v["fam"] in args])
