"""CRSB-003 robustness of the FROZEN Crude 30m S/R breakout BUY (spec in crude_srbrk.SPEC; nothing re-tuned).
  A  by year / quarter (frozen rule over all history: NOT independent of selection for the 2024Q3-2026Q2 part)
  B  regimes: previous-day ADX(14) and daily ATR(14) percentile (trailing 250 days), computed from 5-min data
  C  costs x1 / x2 / x3; entry delay +1 / +2 five-minute bars; conservative stop fills +2 / +5 ticks per stop-out
  D  EXPLORATORY (labelled, not a replacement for the frozen spec): nearby S/R definitions via SR_LB / SR_TOL / SR_MIN
  E  comparison with the day-trend idea on Crude: DTC baseline, breakout alone, breakout with dayctx agreement,
     same-day overlap
Writes results/crsb_robust.json and results/crsb_robust_*.csv.
python research/program/crsb_robust.py"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import crude_srbrk as K, mcx_engine as E  # noqa: E402

OUT = ROOT / "research/program/results"
OOS0 = pd.Timestamp("2026-07-01")


def daily_regimes(d5):
    g = d5.groupby("day").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    h, l, c = g.high, g.low, g.close
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    up, dn = h.diff(), -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a14 = tr.ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, g.index).ewm(alpha=1 / 14, adjust=False).mean() / a14
    ndi = 100 * pd.Series(ndm, g.index).ewm(alpha=1 / 14, adjust=False).mean() / a14
    adx = (100 * (pdi - ndi).abs() / (pdi + ndi)).ewm(alpha=1 / 14, adjust=False).mean()
    pct = atr.rolling(250, min_periods=60).apply(lambda s: (s[:-1] < s[-1]).mean(), raw=True)
    R = pd.DataFrame(dict(adx_prev=adx.shift(), atrpct_prev=pct.shift(), trend20_prev=(c > c.rolling(20).mean()).shift()))
    return R


def summ(x):
    s = K.stats(x)
    if len(x) >= 5:
        lo, hi = K.boot(x, 5000); s.update(ci_lo=round(lo, 3), ci_hi=round(hi, 3))
    return s


def main():
    C = K.data(); d5 = C["d5"]
    X = K.frozen_trades(C)
    X["oos"] = X.day >= OOS0
    res = {}
    # A
    X["year"] = X.day.dt.year; X["q"] = pd.PeriodIndex(X.day, freq="Q").astype(str)
    byq = X.groupby("q").net.agg(["size", "mean", "sum"]).round(3)
    byq.to_csv(OUT / "crsb_robust_quarters.csv")
    res["by_year"] = {int(k): summ(v.net.values) for k, v in X.groupby("year")}
    res["quarters_positive"] = f"{int((byq['mean'] > 0).sum())}/{len(byq)}"
    # B
    Rg = daily_regimes(d5)
    X = X.join(Rg, on="day")
    reg = {}
    for col, bins, labels in (("adx_prev", [0, 20, 30, 200], ["ADX<20", "ADX20-30", "ADX>30"]),
                              ("atrpct_prev", [-.01, .33, .67, 1.01], ["ATR low third", "ATR mid", "ATR high third"])):
        X[col + "_b"] = pd.cut(X[col], bins, labels=labels)
        for lab, g in X.groupby(col + "_b", observed=True):
            reg[f"{lab} | all"] = summ(g.net.values)
            o = g[g.oos]
            if len(o):
                reg[f"{lab} | OOS"] = K.stats(o.net.values)
    for lab, g in X.groupby("trend20_prev"):
        reg[f"daily close>MA20 prev={lab} | all"] = summ(g.net.values)
    res["regimes"] = reg
    # C
    stress = {}
    for lab, kw in (("base", {}), ("costs x2", dict(cost_mult=2)), ("costs x3", dict(cost_mult=3)),
                    ("delay +1 bar", dict(delay=1)), ("delay +2 bars", dict(delay=2)),
                    ("stop fills +2 ticks", dict(extra_stop_ticks=2)), ("stop fills +5 ticks", dict(extra_stop_ticks=5)),
                    ("x2 costs + delay 1 + 2 ticks", dict(cost_mult=2, delay=1, extra_stop_ticks=2))):
        Y = K.frozen_trades(C, **kw)
        o = Y[Y.day >= OOS0]; a = Y[Y.day < OOS0]
        stress[lab] = dict(oos=summ(o.net.values), before_oos=K.stats(a.net.values))
    res["stress"] = stress
    # D exploratory S/R variants (each recomputes setups; labelled EXPLORATORY)
    base = (E.SR_LB, E.SR_TOL, E.SR_MIN)
    expl = {}
    for lb, tol, mn in [(60, 0.25, 2), (150, 0.25, 2), (100, 0.15, 2), (100, 0.35, 2), (100, 0.25, 3)]:
        E.SR_LB, E.SR_TOL, E.SR_MIN = lb, tol, mn
        try:
            D = E.setups_for("CRUDEOIL", C["P"])
            Y = K.frozen_trades(C, D=D)
            o = Y[Y.day >= OOS0]
            expl[f"lb{lb} tol{tol} min{mn}"] = dict(oos=K.stats(o.net.values), before_oos=K.stats(Y[Y.day < OOS0].net.values))
        finally:
            E.SR_LB, E.SR_TOL, E.SR_MIN = base
        print("variant", lb, tol, mn, expl[f"lb{lb} tol{tol} min{mn}"]["oos"].get("mean"), flush=True)
    res["exploratory_sr_variants"] = expl
    # E day-trend comparison
    cmp_ = {}
    for lab, g in (("breakout alone", X), ("breakout + dayctx agrees", X[X.dayctx == 1]),
                   ("breakout, dayctx not up", X[X.dayctx != 1])):
        cmp_[lab] = dict(oos=K.stats(g[g.oos].net.values), all=summ(g.net.values))
    from research.program import mcx_dtc as DT
    dtc = DT.trades("CRUDEOIL", C["P"], (13 * 60, 17 * 60), 0.3, 0.5)
    dtc["oos"] = dtc.day >= OOS0
    cmp_["DTC baseline on Crude (BUY+SELL)"] = dict(oos=K.stats(dtc[dtc.oos].net.values), all=summ(dtc.net.values))
    db = dtc[dtc.side == 1]
    cmp_["DTC baseline on Crude, BUY only"] = dict(oos=K.stats(db[db.oos].net.values), all=summ(db.net.values))
    bdays = set(X.day); ddays = set(db.day)
    ov = bdays & ddays
    o_b = X[X.oos]; o_d = db[db.oos]
    cmp_["overlap"] = dict(breakout_days=len(bdays), dtc_buy_days=len(ddays), shared_days=len(ov),
                           oos_breakout_days=int(o_b.day.nunique()), oos_dtc_buy_days=int(o_d.day.nunique()),
                           oos_shared_days=len(set(o_b.day) & set(o_d.day)),
                           breakout_on_shared_days=K.stats(X[X.day.isin(ov)].net.values),
                           breakout_on_other_days=K.stats(X[~X.day.isin(ov)].net.values),
                           corr_daily_R=round(float(pd.concat([X.groupby("day").net.sum().rename("b"),
                                                               db.groupby("day").net.sum().rename("d")], axis=1).fillna(0).corr().iat[0, 1]), 3))
    comb = pd.concat([X[["day", "net"]], db[["day", "net"]]])
    daily = comb.groupby("day").net.sum()
    cmp_["combined both (1R each), daily R"] = dict(oos=K.stats(daily[daily.index >= OOS0].values), all=K.stats(daily.values))
    res["daytrend_compare"] = cmp_
    (OUT / "crsb_robust.json").write_text(json.dumps(res, indent=1, default=str))
    X.to_csv(OUT / "crsb_robust_trades.csv", index=False)
    print(json.dumps({k: res[k] for k in ("by_year", "quarters_positive", "stress", "daytrend_compare")}, indent=1, default=str)[:6000])
    print(json.dumps(reg, indent=0, default=str)[:3000])


if __name__ == "__main__":
    main()
