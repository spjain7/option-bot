"""Experiment runner: features per commodity -> every trigger x exit -> trade lists -> period summaries."""
import hashlib
import json
import pickle
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from . import data as D, sim as S, metrics as M
from .costs import CFG
from ..feature_engineering import build as B

PKG = Path(__file__).resolve().parents[1]
REPORTS = PKG / "reports"; REPORTS.mkdir(exist_ok=True)
EXITS = {"2R": (0, 2.0, None), "3R": (0, 3.0, None), "STRUCT_SWING": (1, 0.0, "SWING"), "STRUCT_HTF": (1, 0.0, "HTF"),
         "TRAIL3ATR": (2, 0.0, None), "TIME": (3, 0.0, None), "PARTIAL_1R_3R": (4, 0.0, None)}
TFS = ["15m", "30m", "1h", "4h", "1d"]


def code_version():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=PKG, text=True).strip()
    except Exception:
        return "unknown"


def _fhash():
    h = hashlib.sha1()
    for p in sorted((PKG / "feature_engineering").glob("*.py")) + sorted((PKG / "backtesting").glob("*.py")):
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


def features(name, tf):
    fp = D.CACHE / f"F_{name}_{tf}_{_fhash()}.pkl"
    if fp.exists():
        return pickle.loads(fp.read_bytes())
    F = B.build(name, tf)
    D.CACHE.mkdir(parents=True, exist_ok=True); fp.write_bytes(pickle.dumps(F))
    return F


def universe(tf):
    return D.INTRA + (["LEAD"] if tf == "1d" else [])


def period_of(tf, t):
    sp = CFG["splits"]["daily" if tf == "1d" else "intraday"]
    t = pd.to_datetime(t); out = np.full(len(t), "PRE", object)
    for k, (a, b) in sp.items():
        out[(t >= pd.Timestamp(a)) & (t <= pd.Timestamp(b) + pd.Timedelta(days=1))] = k
    return out


def run_one(F, rule, sig, stop, elev, exit_name):
    kind, Rm, tg = EXITS[exit_name]; s = CFG["sim"]; tf = F["tf"]
    tgt = F["TGT"][tg] if tg else np.full(len(F["c"]), np.nan)
    si, ei, xi, g, nr, mfe, mae, why, rej = S.simulate(F["o"], F["h"], F["l"], F["c"], F["atr"], F["seg"], F["costf"], sig,
                                                       stop, elev, tgt, kind, Rm, s["max_hold_bars"][tf], s["time_exit_bars"][tf],
                                                       s["trail_atr"], s["stop_entry_window_bars"], s["min_risk_atr"],
                                                       s["max_risk_atr"], s["min_struct_rr"])
    t = F["time"]
    return pd.DataFrame(dict(rule=rule, exit=exit_name, tf=tf, name=F["name"], sig_i=si, sig_t=t[si], entry=t[ei], exit_t=t[xi],
                             grossR=g, netR=nr, mfeR=mfe, maeR=mae, bars=xi - ei + 1, reason=why)), rej


def run(tf, rules=None, exits=tuple(EXITS), cond=None, names=None, extra=None):
    """rules: list of trigger names (None = all); cond: optional fn(F) -> {new_rule: (sig, stop, elev)} for combinations."""
    out = []; rejected = {}
    for name in (names or universe(tf)):
        F = features(name, tf)
        if F is None:
            continue
        trig = {k: v[:3] for k, v in F["TRIG"].items() if rules is None or k in rules}
        if cond is not None:
            trig = cond(F)
        for rule, (sig, stop, elev) in trig.items():
            for ex in exits:
                T, rej = run_one(F, rule, sig, stop, elev, ex)
                rejected[(rule, ex)] = rejected.get((rule, ex), 0) + rej
                if len(T):
                    out.append(T)
    T = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    if len(T):
        T["period"] = period_of(tf, T.entry)
    return T, rejected


def table(T, by=("tf", "rule", "exit"), meta=None):
    rows = []
    for k, g in T.groupby(list(by)):
        r = dict(zip(by, k))
        for p in ("TRAIN", "VAL", "OOS"):
            s = M.summary(g[g.period == p])
            for a in ("n", "win", "R", "PF", "maxDD_R", "t_day"):
                r[f"{p}_{a}"] = s.get(a, np.nan)
        s = M.summary(g)
        for a in ("n", "win", "R", "PF", "avg_win", "avg_loss", "mfe", "mae", "hold", "max_consec_loss", "maxDD_R", "t_day"):
            r[f"ALL_{a}"] = s.get(a, np.nan)
        pc = g.groupby("name").netR.agg(["mean", "size"])
        r["per_commodity"] = "; ".join(f"{i}:{m_:+.2f}({n_})" for i, (m_, n_) in pc.iterrows())
        r["best_commodity_share"] = round(float(g.groupby("name").netR.sum().max() / g.netR.sum()), 2) if g.netR.sum() > 0 else np.nan
        rows.append(r)
    L = pd.DataFrame(rows)
    if len(L):
        g = CFG["gate"]
        L["p_train"] = [M.p_from_t(x) for x in L.TRAIN_t_day]
        L["TRAIN_PASS"] = (L.TRAIN_n >= g["min_trades_period"]) & (L.TRAIN_R > 0) & (L.TRAIN_PF >= g["min_pf"])
        L["VAL_PASS"] = L.TRAIN_PASS & (L.VAL_n >= g["min_trades_period"]) & (L.VAL_R > 0) & (L.VAL_PF >= g["min_pf"])
        L["OOS_PASS"] = L.VAL_PASS & (L.OOS_n >= g["min_trades_period"]) & (L.OOS_R > 0) & (L.OOS_PF >= g["min_pf"]) & \
            (L.ALL_n >= g["min_trades_total"])
    return L


def experiment_record(exp_id, module, tf, config, L, extra=None):
    rec = dict(id=exp_id, module=module, tf=tf, code_version=code_version(), feature_hash=_fhash(), data_version=CFG["data_version"],
               split=CFG["splits"]["daily" if tf == "1d" else "intraday"], config=config,
               tests=int(len(L)), train_pass=int(L.TRAIN_PASS.sum()) if len(L) else 0,
               val_pass=int(L.VAL_PASS.sum()) if len(L) else 0, oos_pass=int(L.OOS_PASS.sum()) if len(L) else 0,
               reproduce=f"python -m research.mcx_institutional_buy.{module}.run {tf}")
    if extra:
        rec.update(extra)
    p = REPORTS / "experiments.jsonl"
    with open(p, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return rec
