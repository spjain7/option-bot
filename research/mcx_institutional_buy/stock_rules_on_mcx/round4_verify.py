"""ROUND 4 verification: the pooled pick of each candle size and each commodity's own pick vs RANDOM entries
(same commodity, candle, side, same filter condition, same stop / target, same number of signals; 200 draws), plus Rs per lot,
double costs and every trade (for the dashboard).
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round4_verify -> reports/mcx_round4_verify.json"""
import json
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import data as D, runner as RN
from research.mcx_institutional_buy.stock_rules_on_mcx import round4 as R4

TFN = {"3h": "3h", "4h": "4h", "1d": "Daily", "1w": "Weekly", "1M": "Monthly"}
FAMN = {"BO10": "10-candle breakout", "BO20": "20-candle breakout", "BO55": "55-candle breakout", "PWK": "previous-week high break",
        "PMO": "previous-month high break", "MARU20": "strong candle 20-candle breakout"}
FAMN_S = {"BO10": "10-candle breakdown", "BO20": "20-candle breakdown", "BO55": "55-candle breakdown", "PWK": "previous-week low break",
          "PMO": "previous-month low break", "MARU20": "strong candle 20-candle breakdown"}
HTN = {"3h": ("daily trend", "weekly trend"), "4h": ("daily trend", "weekly trend"), "1d": ("weekly trend", "monthly trend"),
       "1w": ("monthly trend", "12-week EMA"), "1M": ("12-month EMA", "12-month EMA")}
# (tf, side, fam, filt, k, r, kind, commodities, group)
POOLED = [("3h", 1, "BO10", ("VOL", "HT1"), 1.5, 3.0, 0), ("4h", 1, "MARU20", ("VOL",), 1.5, 3.0, 0),
          ("1d", 1, "BO20", ("VOL",), 1.5, 3.0, 0), ("1d", 1, "BO55", (), 2.0, 0.0, 2), ("1w", 1, "PMO", ("HT2",), 2.0, 3.0, 0),
          ("1M", 1, "BO10", ("HT1",), 1.5, 3.0, 0), ("4h", -1, "BO10", ("VOL",), 1.5, 3.0, 0)]
OWN = {"GOLD": ("4h", 1, "BO10", (), 1.5, 3.0, 0), "SILVER": ("1d", 1, "BO20", ("VOL",), 2.0, 0.0, 2),
       "COPPER": ("1d", 1, "PMO", ("VOL",), 2.0, 3.0, 0), "ZINC": ("1w", 1, "PMO", ("HT2",), 2.0, 3.0, 0),
       "ALUMINIUM": ("4h", -1, "BO10", ("VOL",), 1.5, 3.0, 0), "CRUDEOIL": ("3h", 1, "BO10", ("VOL", "HT1"), 1.5, 3.0, 0),
       "NATURALGAS": ("4h", 1, "MARU20", ("VOL",), 1.5, 3.0, 0)}
REASON = {1: "stop-loss", 2: "target", 3: "time exit", 4: "contract roll", 5: "stop-loss"}


def label(tf, side, fam, filt, k, r, kind):
    parts = [f"{TFN[tf]} {(FAMN if side > 0 else FAMN_S)[fam]} {'BUY' if side > 0 else 'SELL'}"]
    for x in filt:
        parts.append("volume > 1.5x" if x == "VOL" else (HTN[tf][0] if x == "HT1" else HTN[tf][1]) + (" up" if side > 0 else " down"))
    parts.append(f"SL {k:g} ATR"); parts.append("trailing stop 3 ATR" if kind == 2 else f"target {r:g}R")
    return " · ".join(parts)


def main():
    B = {n: R4.build(n) for n in D.INTRA}
    rng = np.random.default_rng(17)
    res = []; trades = []

    def one(name, spec, group):
        tf, side, fam, filt, k, r, kind = spec
        d = B[name][tf]; P, cond, arr = R4.signals(d, side)
        if fam not in P:
            return None
        base = np.ones(len(arr["c"]), bool)
        for c_ in filt:
            base &= cond[c_]
        m = P[fam] & base
        si, ei, xi, g, nr, mfe, mae, why = R4.run(arr, d, m, side, k, r, kind, tf, name)
        f = d["f"]; c = f["close"].values.astype(float); o = f["open"].values.astype(float); a = f["atr"].values.astype(float)
        fac = f["raw_close"].values / c
        rk = side * (o[ei] - (c[si] - side * k * a[si]))
        rs = nr * rk * fac[ei] * R4.MULT[name]
        per = d["per"][ei]
        # double costs
        d2 = dict(d); f2 = f.copy()
        cm = R4.CMUL[tf]; R4.CMUL[tf] = cm * 2
        nr2 = R4.run(arr, d, m, side, k, r, kind, tf, name)[4]; R4.CMUL[tf] = cm
        # random
        rate = m.sum() / max(base.sum(), 1)
        dr = {p: [] for p in ("TRAIN", "VAL", "OOS")}
        for _ in range(200):
            rm = base & (rng.random(len(base)) < rate)
            x = R4.run(arr, d, rm, side, k, r, kind, tf, name)
            pe = d["per"][x[1]]
            for p in dr:
                y = x[4][pe == p]
                dr[p].append(y.mean() if len(y) else np.nan)
        lab = label(*spec)
        rec = dict(group=group, commodity=name, strategy=lab, **R4.pstats(nr, per), ALL_n=int(len(nr)),
                   ALL_win=round(100 * float((nr > 0).mean()), 1) if len(nr) else None,
                   ALL_R=round(float(nr.mean()), 3) if len(nr) else None, ALL_R_double_costs=round(float(nr2.mean()), 3) if len(nr2) else None,
                   rs=int(rs.sum()))
        for p in dr:
            arr_ = np.array(dr[p], float); v = rec[f"{p}_R"]
            rec[f"{p}_random_R"] = round(float(np.nanmean(arr_)), 3) if np.isfinite(arr_).any() else None
            rec[f"{p}_beats_pct"] = int(100 * np.nanmean(arr_ < v)) if (v == v and np.isfinite(arr_).any()) else None
        t = pd.to_datetime(f["time"])
        for i in range(len(nr)):
            trades.append(dict(strategy=lab, commodity=name, side="BUY" if side > 0 else "SELL", entry=str(t.iloc[ei[i]])[:16],
                               exit=str(t.iloc[xi[i]])[:16], entry_px=round(float(o[ei[i]] * fac[ei[i]]), 2),
                               exit_px=round(float((o[ei[i]] + side * g[i] * rk[i]) * fac[ei[i]]), 2), R=round(float(nr[i]), 2),
                               pnl_rs=int(round(rs[i])), best_rs=int(round(mfe[i] * rk[i] * fac[ei[i]] * R4.MULT[name])),
                               worst_rs=int(round(mae[i] * rk[i] * fac[ei[i]] * R4.MULT[name])),
                               period={"VAL": "VAL"}.get(str(per[i]), str(per[i])), result=REASON.get(int(why[i]), "exit"), group=group))
        return rec

    for spec in POOLED:
        recs = [x for x in (one(n, spec, "same rule all 7") for n in D.INTRA) if x]
        res.extend(recs)
        n_ = sum(x["ALL_n"] for x in recs)
        print(label(*spec), "| trades", n_, "| Rs", sum(x["rs"] for x in recs),
              "| per commodity OOS R vs random:", {x["commodity"]: (x["OOS_R"], x["OOS_random_R"]) for x in recs}, flush=True)
    for name, spec in OWN.items():
        x = one(name, spec, "own rule per commodity"); res.append(x)
        print("OWN", name, x["strategy"], {k: x[k] for k in ("TRAIN_n", "TRAIN_R", "TRAIN_random_R", "VAL_n", "VAL_R", "VAL_random_R",
                                                              "OOS_n", "OOS_win", "OOS_R", "OOS_random_R", "OOS_beats_pct", "ALL_R_double_costs", "rs")}, flush=True)
    (RN.REPORTS / "mcx_round4_verify.json").write_text(json.dumps(dict(results=res, trades=trades), default=lambda v: None))
    R = pd.DataFrame(res)
    # pooled summary per rule: trade-weighted R vs random per period
    for p in ("TRAIN", "VAL", "OOS"):
        R[f"{p}_w"] = R[f"{p}_R"].fillna(0) * R[f"{p}_n"]; R[f"{p}_wr"] = R[f"{p}_random_R"].fillna(0) * R[f"{p}_n"]
    G = R.groupby(["group", "strategy"]).agg(**{f"{p}_n": (f"{p}_n", "sum") for p in ("TRAIN", "VAL", "OOS")},
                                             **{f"{p}_w": (f"{p}_w", "sum") for p in ("TRAIN", "VAL", "OOS")},
                                             **{f"{p}_wr": (f"{p}_wr", "sum") for p in ("TRAIN", "VAL", "OOS")}, rs=("rs", "sum"))
    for p in ("TRAIN", "VAL", "OOS"):
        G[f"{p}_R"] = (G[f"{p}_w"] / G[f"{p}_n"]).round(3); G[f"{p}_rand"] = (G[f"{p}_wr"] / G[f"{p}_n"]).round(3)
    pd.set_option("display.width", 250)
    print(G[["TRAIN_n", "TRAIN_R", "TRAIN_rand", "VAL_n", "VAL_R", "VAL_rand", "OOS_n", "OOS_R", "OOS_rand", "rs"]].to_string())


if __name__ == "__main__":
    main()
