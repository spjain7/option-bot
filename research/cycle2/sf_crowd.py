"""Cycle 2 · 2 – stock-futures CONTINUATION SELL (SF-CONT-SELL-v1, unchanged in shadow): 2026 deterioration, the real
futures execution gap and crowded-signal days. Any filtered rule here is a SEPARATE research version (SF-CONT-SELL-v2x),
never a change to v1.
  crowding    number of qualifying v1 signals across the whole universe on the signal day (known at that close)
  v2a-N       v1, but no entry on days with >= N signals (N = 3, 5, 8; N = 5 pre-registered, 3 / 8 = sensitivity)
  v2b-cap4    v1, at most 4 entries per day, the 4 most liquid (60-session median cash turnover) – pre-registered
Each version is replayed with the exact v1 trade rules (one open trade per stock), on the research basis (adjusted cash,
research costs) AND on real futures prices through the shadow engine (contract choice, rolls, F&O ban, slippage).
2026: is the year unusual? bootstrap of yearly averages from 2018–2025 trades at the 2026 sample size; mix-adjusted
expectation from the 2018–2025 R by market-move bucket applied to the 2026 bucket mix.
python -m research.cycle2.sf_crowd  ->  results/sf_crowd.json, results/sf_crowd_trades.csv.gz"""
import glob
import json
import pickle
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd

from research.cycle2 import common as C
from research.rsidiv import sf_check as SC, stockfut as SF
from research.shadow import rules as RU, engine as EN, data as DA, parity as PA

CUTS = SF.CUTS
RNG = np.random.default_rng(21)


def st(r):
    r = pd.Series(r, dtype=float).dropna()
    if len(r) < 3:
        return dict(n=len(r))
    w = r > 0; gl = -r[~w].sum()
    dm = r.groupby(np.arange(len(r))).mean()
    return dict(n=len(r), win=round(100 * w.mean(), 1), R=round(r.mean(), 3), PF=round(r[w].sum() / gl, 2) if gl > 0 else None)


def periods(T, col="netR", tcol="entry"):
    lab = C.E.periods(pd.to_datetime(T[tcol]).values, CUTS)
    return {p: st(T[col].values[lab == p]) for p, _ in CUTS}


def replay_masked(stocks, allow):
    """v1 rules, but a signal is allowed only if allow(name, signal_time) -> trades incl. overlap statuses."""
    p = RU.RULES["SF-CONT-SELL-v1"]

    def sig_fn(b):
        sig, risk, r, a = RU.sf_signal(b)
        t = b["time"].values; nm = b["name"].iloc[0]
        m = np.array([allow(nm, x) for x in t]) if sig.any() else np.zeros(len(t), bool)
        return sig & m, risk, r, a

    def expid(b):
        e = pd.Series(b["exp"]).astype("datetime64[ns]")
        return np.where(e.notna(), e.values.astype("datetime64[D]").astype(np.int64), -1)
    return PA.replay(stocks, sig_fn, p, lambda t: float(SF.fut_cost(np.array([t]))[0]), expid)


def futures_exec(T, A, fo, days, reg, bans, cands):
    """research trades T (status trade/open/overlap) -> shadow-engine lifecycle on real futures prices."""
    L = []
    for r in T[T.status.isin(["trade", "open", "overlap"])].itertuples():
        hit = [(k, np.where(A[k]["time"].values == np.datetime64(r.signal))[0]) for k in cands.get(r.name, [])]
        hit = [(k, i) for k, i in hit if len(i)]
        if not hit:
            continue
        k, i = hit[0]; a = A[k]; i = int(i[0]); sub = a.iloc[: i + 1]
        h, l, cc = sub.high.values.astype(float), sub.low.values.astype(float), sub.close.values.astype(float)
        at = RU.atr(h, l, cc)[-1]; risk = min(max(h[-5:].max() - cc[-1] + 0.1 * at, 0.5 * at), 3 * at)
        L.append(dict(strategy="SF", signal_date=r.signal, symbol=str(a.symbol.iloc[i]), key=k, close=float(cc[-1]), risk=risk,
                      risk_pct=risk / cc[-1], detected_on=r.signal, signal_id=f"{r.name}|{pd.Timestamp(r.signal):%Y-%m-%d}"))
    L = pd.DataFrame(L)
    return EN.lifecycle_sf(L, A, fo, days, reg, {}, days[-1], bans)


def done(X):
    return X[X.status.astype(str).str.startswith(("TARGET", "STOP", "TIME"))]


def main():
    stocks = SC.load()
    v1 = pd.read_csv(C.ROOT / "research/shadow/results/parity_SF-CONT-SELL-v1.csv.gz", parse_dates=["signal", "entry", "exit"])
    cnt = v1.groupby("signal").size()
    # liquidity rank per signal day for the cap rule
    to = {}
    for b in stocks:
        v = (b["close"] * b["volume"]).rolling(60, min_periods=40).median().shift(1)
        to.update({(b["name"].iloc[0], t): x for t, x in zip(b["time"].values, v.values)})
    v1["turn"] = [to.get((n, np.datetime64(s)), np.nan) for n, s in zip(v1.name, v1.signal)]
    v1["rank_liq"] = v1.groupby("signal").turn.rank(ascending=False, method="first")
    capset = set(zip(v1.name[v1.rank_liq <= 4], v1.signal[v1.rank_liq <= 4].values))
    versions = {"v1 (shadow, unchanged)": None}
    for N in (3, 5, 8):
        versions[f"v2a-{N}: skip days with >= {N} signals"] = (lambda N: (lambda nm, t: cnt.get(pd.Timestamp(t), 0) < N))(N)
    versions["v2b-cap4: max 4 per day, most liquid"] = lambda nm, t: (nm, np.datetime64(t)) in capset
    A = pickle.loads((C.ROOT / "research/data/nse_cm/_adjusted.pkl").read_bytes())
    cands = {}
    for k, a in A.items():
        cands.setdefault(str(a["symbol"].iloc[-1]), []).append(k)
    fs = sorted(glob.glob(str(C.ROOT / "research/data/nse_fut_pit/days/*.csv.gz")))
    fo = pd.concat((pd.read_csv(f, usecols=["date", "symbol", "kind", "expiry", "open", "high", "low", "close", "contracts", "oi"]) for f in fs), ignore_index=True)
    fo = fo[(fo.kind == "STK") & fo.symbol.isin(set(v1.name))]; fo["date"], fo["expiry"] = pd.to_datetime(fo.date), pd.to_datetime(fo.expiry)
    fo["token"] = fo.symbol + "|" + fo.expiry.dt.strftime("%Y%m%d"); fo["lot"] = 1; fo["value"] = np.nan; fo["settle"] = fo.close
    days = pd.DatetimeIndex(sorted(fo.date.unique())); reg = EN.market_regime(A)
    res, keep = {}, []
    for name, allow in versions.items():
        T = v1.copy() if allow is None else replay_masked(stocks, allow)
        tr = T[T.status.isin(["trade", "open"])]
        ent = sorted({d for d in (EN._next_session(days, s) for s in T.signal) if d is not None})
        with ThreadPoolExecutor(6) as ex:
            bans = dict(zip(ent, ex.map(DA.ban, ent)))
        X = futures_exec(T, A, fo, days, reg, bans, cands)
        Xd = done(X)
        res[name] = dict(research_basis=dict(all=st(tr.netR), **periods(tr), y2026=st(tr.netR[tr.entry.dt.year == 2026])),
                         futures_basis=dict(all=st(Xd.exec_R), **periods(Xd, "exec_R", "entry_date"),
                                            y2026=st(Xd.exec_R[pd.to_datetime(Xd.entry_date).dt.year == 2026])),
                         not_executable=int(X.status.astype(str).str.startswith("NOT EXEC").sum()),
                         by_year_futures={int(y): st(g.exec_R) for y, g in Xd.groupby(pd.to_datetime(Xd.entry_date).dt.year)})
        keep.append(X.assign(version=name))
        print(name, res[name]["research_basis"]["all"], res[name]["futures_basis"]["all"], flush=True)
    # crowded vs isolated, every period, both bases (v1 trades)
    X1 = done(keep[0]).copy(); X1["crowd"] = pd.to_datetime(X1.signal_date).map(cnt).fillna(0)
    tr1 = v1[v1.status.isin(["trade", "open"])].copy(); tr1["crowd"] = tr1.signal.map(cnt)
    buckets = [(1, 2, "1-2"), (3, 4, "3-4"), (5, 7, "5-7"), (8, 999, "8+")]
    res["crowding_v1"] = {lab: dict(research=dict(all=st(tr1.netR[(tr1.crowd >= a) & (tr1.crowd <= b)]),
                                                  **periods(tr1[(tr1.crowd >= a) & (tr1.crowd <= b)])),
                                     futures=dict(all=st(X1.exec_R[(X1.crowd >= a) & (X1.crowd <= b)]),
                                                  **periods(X1[(X1.crowd >= a) & (X1.crowd <= b)], "exec_R", "entry_date")))
                          for a, b, lab in buckets}
    res["crowding_v1_by_year"] = {int(y): {lab: st(g.netR[(g.crowd >= a) & (g.crowd <= b)]) for a, b, lab in ((1, 4, "1-4"), (5, 999, "5+"))}
                                  for y, g in tr1.groupby(tr1.entry.dt.year)}
    # execution gap decomposition (v1)
    X1["kfrac"] = X1.risk_pct
    X1["fee_R"] = [EN.fut_cost(e, 0.0) * (1 + r) / k for e, r, k in zip(X1.entry_date, X1.rolls, X1.kfrac)]
    X1["slip_R"] = 2 * 0.0003 / X1.kfrac
    X1["same_exit"] = pd.to_datetime(X1.exit_date) == pd.to_datetime(X1.research_exit)
    gap = X1.exec_R - X1.research_R
    res["execution_gap_v1"] = dict(trades=len(X1), mean_gap_R=round(float(gap.mean()), 3), median_gap_R=round(float(gap.median()), 3),
                                   share_same_exit_day=round(100 * float(X1.same_exit.mean()), 1),
                                   gap_when_same_exit=round(float(gap[X1.same_exit].mean()), 3), gap_when_exit_differs=round(float(gap[~X1.same_exit].mean()), 3),
                                   avg_fee_R=round(float(X1.fee_R.mean()), 3), avg_slip_R=round(float(X1.slip_R.mean()), 3),
                                   gap_by_rolls={int(k): round(float(g.mean()), 3) for k, g in gap.groupby(X1.rolls)},
                                   gap_by_year={int(k): round(float(g.mean()), 3) for k, g in gap.groupby(pd.to_datetime(X1.entry_date).dt.year)},
                                   note="research cost already includes 0.03 % slippage per side and fees; the gap is therefore mostly the futures price "
                                        "path (basis change, different highs / lows) and roll / contract timing")
    # 2026: unusual? bootstrap + mix-adjusted expectation (research basis)
    tr1["mkt_r20"] = tr1.signal.map(reg["r20"])
    tr1["bucket"] = pd.cut(tr1.mkt_r20, [-1, -0.05, -0.02, 0.0, 0.02, 0.05, 1]).astype(str)
    hist, y26 = tr1[tr1.entry.dt.year < 2026], tr1[tr1.entry.dt.year == 2026]
    bs = np.array([hist.netR.values[RNG.integers(0, len(hist), len(y26))].mean() for _ in range(5000)])
    exp = hist.groupby("bucket").netR.mean(); mix = y26.bucket.value_counts(normalize=True)
    res["y2026"] = dict(n=len(y26), R=round(float(y26.netR.mean()), 3), share_bootstrap_years_at_or_below=round(float((bs <= y26.netR.mean()).mean()), 4),
                        mix_adjusted_expectation_R=round(float((mix * exp.reindex(mix.index)).sum()), 3), bucket_mix=mix.round(3).to_dict(),
                        hist_R_by_bucket=exp.round(3).to_dict(), crowded_share_2026=round(float((y26.crowd >= 5).mean()), 3),
                        crowded_share_hist=round(float((hist.crowd >= 5).mean()), 3))
    pd.concat(keep).to_csv(C.OUT / "sf_crowd_trades.csv.gz", index=False, compression="gzip")
    json.dump(res, open(C.OUT / "sf_crowd.json", "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in res.items() if k not in ("crowding_v1_by_year",)}, default=str)[:9000])


if __name__ == "__main__":
    main()
