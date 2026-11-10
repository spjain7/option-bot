"""Robustness of the daily PASS candidates (positional trend family): year-by-year, regimes, parameter neighbourhood,
2x / 3x costs, and a capital-constrained portfolio (10 slots, equal weight, first-come by signal order, no re-entry while
held) vs the equal-weight eligible universe.  python -m research.cashq.robust"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from . import data as D, ind as I, engine as EN, validate as V
from .daily_run import features, first_in

OUT = Path(__file__).resolve().parent / "results"


def variants(F):
    c, h = F["close"], F["high"]
    hiN = lambda n: c >= c.rolling(n, min_periods=int(n * 0.95)).max()
    out = {}
    for n in (126, 189, 252, 378):
        for rv in (1.0, 1.5, 2.0):
            out[f"F1_hi{n}_rvol{rv}"] = first_in(hiN(n), 20) & (F["rvol"] >= rv)
    for q in (0.8, 0.9, 0.95):
        out[f"F2_RS{q}_BO50"] = first_in(F["hi50"], 5) & (F["rs_rank"] >= q)
    return {k: v.fillna(False).astype(bool) & F["elig"] for k, v in out.items()}


def portfolio(T, idx, slots=10):
    """daily mark-to-market of equal-weight slots; trades taken in entry order while a slot is free."""
    T = T.sort_values(["entry_time", "key"])
    held, taken = [], []
    for r in T.itertuples():
        held = [x for x in held if x > r.entry_time]
        if len(held) < slots:
            held.append(r.exit_time); taken.append(r)
    P = pd.DataFrame(taken)
    if P.empty:
        return None
    # per-trade return booked on exit day, sized 1/slots of equity (simple, conservative: no intra-trade MTM)
    ret = P.groupby("exit_time")["netpct"].sum() / slots
    eq = (1 + ret.reindex(idx).fillna(0)).cumprod()
    yrs = (idx[-1] - idx[0]).days / 365.25
    dd = float((eq / eq.cummax() - 1).min())
    return dict(trades=len(P), CAGR=round(100 * (eq.iloc[-1] ** (1 / yrs) - 1), 1), maxDD=round(100 * dd, 1),
                exposure=round(P["bars"].sum() / (len(idx) * slots) * 100, 1)), eq


def main():
    W = D.daily_panel()
    F = features(W)
    sym = W["symbol"]; mk = W["market"]["close"]
    trail = {"ema30": I.ema(F["close"], 30), "ema50": F["ema50"], "ema100": I.ema(F["close"], 100)}
    rows = []
    best = {}
    for nm, sig in variants(F).items():
        for tn, tr in trail.items():
            for cm in (1, 2, 3):
                T = EN.daily_trades(F, sig, 3.0 * F["atr"], 1, 0.0, 250, trail=tr, cost=EN.COST["delivery"] * cm)
                row = dict(variant=nm, trail=tn, cost_x=cm)
                for k, t in V.split(T, V.DAILY_SPLITS).items():
                    m = V.metrics(t)
                    row.update({f"{k}_{a}": m.get(a) for a in ("n", "avgR", "PF", "pct", "lo95", "hold")})
                yr = T.groupby(T["entry_time"].dt.year)["netR"].agg(["mean", "size"])
                row["years_pos"] = f"{int((yr['mean'] > 0).sum())}/{len(yr)}"
                rows.append(row)
                if cm == 1 and tn == "ema50" and nm in ("F1_hi252_rvol1.5", "F2_RS0.9_BO50"):
                    best[nm] = T
    R = pd.DataFrame(rows)
    R.to_csv(OUT / "robust_neighbourhood.csv", index=False)
    detail = {}
    idx = F["close"].index
    for nm, T in best.items():
        T = T.copy()
        T["mkt_on"] = F["mkt_on"].reindex(T["entry_time"]).values
        T["vol_hi"] = F["mkt_vol_hi"].reindex(T["entry_time"]).values
        by_year = T.groupby(T["entry_time"].dt.year)["netR"].agg(["size", "mean"]).round(3)
        reg = T.groupby(["mkt_on"])["netR"].agg(["size", "mean"]).round(3)
        vol = T.groupby(["vol_hi"])["netR"].agg(["size", "mean"]).round(3)
        pf, eq = portfolio(T[T["entry_time"] >= "2020-01-01"], idx[idx >= "2020-01-01"])
        pf_all, _ = portfolio(T, idx)
        ew = W["close"].pct_change().where(W["elig"].shift(1).fillna(False).astype(bool)).mean(axis=1)
        ew_eq = (1 + ew[idx >= "2020-01-01"].fillna(0)).cumprod()
        ewy = (ew_eq.iloc[-1] ** (1 / ((idx[-1] - pd.Timestamp('2020-01-01')).days / 365.25)) - 1) * 100
        mk_eq = mk[mk.index >= "2020-01-01"]
        detail[nm] = dict(by_year=by_year.reset_index().to_dict("records"), regime_mkt_on=reg.reset_index().to_dict("records"),
                          vol_regime=vol.reset_index().to_dict("records"), portfolio_2020_26=pf, portfolio_2005_26=pf_all,
                          ew_universe_CAGR_2020_26=round(float(ewy), 1),
                          ew_universe_maxDD_2020_26=round(float((ew_eq / ew_eq.cummax() - 1).min() * 100), 1),
                          top_symbols=T.groupby(T["key"].map(sym))["netR"].sum().sort_values(ascending=False).head(10).round(1).to_dict())
        T.assign(symbol=T["key"].map(sym)).to_csv(OUT / f"ledger_{nm}.csv", index=False)
    json.dump(detail, open(OUT / "robust_detail.json", "w"), indent=1, default=str)
    print(R[R.cost_x == 1].to_string(index=False))
    print(json.dumps({k: {a: v[a] for a in ("portfolio_2020_26", "portfolio_2005_26", "ew_universe_CAGR_2020_26", "ew_universe_maxDD_2020_26", "regime_mkt_on")} for k, v in detail.items()}, indent=1, default=str))


if __name__ == "__main__":
    main()
