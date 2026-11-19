"""Owner 11-Nov requirements 7 and 8 – historical investigation of the two shadow candidates (research only).
SF-CONT-SELL-v1: why 2026 is negative · weakness in falling markets · what real FUTURES prices (not the cash proxy),
                 the F&O ban list and rolls do to the result.
CM-CONT-BUY-v1:  low-liquidity execution (order size vs the day's turnover) · circuit locks on entry / exit days · gap
                 risk · incremental value vs the live monthly momentum portfolio.
python -m research.shadow.investigate  ->  research/shadow/results/investigate_sf.json, investigate_cm.json (+ trades)"""
import glob
import json
import pickle
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.shadow import engine as EN, data as DA, rules as RU  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"


def st(r):
    r = pd.Series(r, dtype=float).dropna()
    if len(r) < 3:
        return dict(n=len(r))
    w = r > 0; gl = -r[~w].sum()
    return dict(n=len(r), win=round(100 * w.mean(), 1), R=round(r.mean(), 3), PF=round(r[w].sum() / gl, 2) if gl > 0 else None)


def grp(df, col, val="netR"):
    return {str(k): st(g[val]) for k, g in df.groupby(col)}


# ───────────────────────── SF ─────────────────────────
def sf():
    A = pickle.loads((ROOT / "research/data/nse_cm/_adjusted.pkl").read_bytes())
    T = pd.read_csv(OUT / "parity_SF-CONT-SELL-v1.csv.gz", parse_dates=["signal", "entry", "exit"])
    allsig = T.copy(); T = T[T.status.isin(["trade", "open"])].copy()
    reg = EN.market_regime(A)
    T["market_up"] = T.signal.map(reg["up"]); T["mkt_r20"] = T.signal.map(reg["r20"])
    T["year"] = T.entry.dt.year; T["month"] = T.entry.dt.to_period("M").astype(str)
    T["era"] = np.where(T.entry < "2024-10-01", "STT 0.0125%", np.where(T.entry < "2026-04-01", "STT 0.02%", "STT 0.05%"))
    cnt = allsig.groupby("signal").size(); T["signals_that_day"] = T.signal.map(cnt)
    T["cluster"] = np.where(T.signals_that_day >= 5, "5+ signals that day", "1-4 signals that day")
    T["mkt_r20_bucket"] = pd.cut(T.mkt_r20, [-1, -0.05, -0.02, 0.0, 0.02, 0.05, 1], labels=["<-5%", "-5..-2%", "-2..0%", "0..2%", "2..5%", ">5%"]).astype(str)
    T["reason_grp"] = T.reason.str.split(" ").str[0]
    out = dict(
        all=st(T.netR), by_year={int(k): dict(st(g.netR), gross=round(g.grossR.mean(), 3), cost=round(g.costR.mean(), 3),
                                              stop_pct=round(100 * g.reason.str.startswith("stop").mean(), 1),
                                              target_pct=round(100 * g.reason.str.startswith("target").mean(), 1),
                                              mfe=round(g.mfe_R.mean(), 2), market_up_share=round(100 * g.market_up.mean(), 0))
                                 for k, g in T.groupby("year")},
        y2026_by_month={k: dict(st(g.netR), gross=round(g.grossR.mean(), 3)) for k, g in T[T.year == 2026].groupby("month")},
        by_cost_era={k: dict(st(g.netR), gross=round(g.grossR.mean(), 3), cost=round(g.costR.mean(), 3)) for k, g in T.groupby("era")},
        by_market=grp(T, "market_up"), by_market_20d_return=grp(T, "mkt_r20_bucket"), by_cluster=grp(T, "cluster"),
        y2026_by_market=grp(T[T.year == 2026], "market_up"), y2026_by_cluster=grp(T[T.year == 2026], "cluster"),
        y2026_gross_without_cost=st(T[T.year == 2026].grossR),
        signals_not_taken_overlap=int((allsig.status == "overlap").sum()))
    # real futures prices + F&O ban + rolls through the shadow engine (same code as the forward test)
    fs = sorted(glob.glob(str(ROOT / "research/data/nse_fut_pit/days/*.csv.gz")))
    fo = pd.concat((pd.read_csv(f, usecols=["date", "symbol", "kind", "expiry", "open", "high", "low", "close", "contracts", "oi"]) for f in fs), ignore_index=True)
    fo = fo[fo.kind == "STK"]; fo["date"], fo["expiry"] = pd.to_datetime(fo.date), pd.to_datetime(fo.expiry)
    fo = fo[fo.symbol.isin(set(T.name))]
    fo["token"] = fo.symbol + "|" + fo.expiry.dt.strftime("%Y%m%d"); fo["lot"] = 1; fo["value"] = np.nan; fo["settle"] = fo.close
    cands = {}
    for k, a in A.items():
        cands.setdefault(str(a["symbol"].iloc[-1]), []).append(k)
    sym_on = {}; L = []; unmapped = 0
    for r in allsig[allsig.status.isin(["trade", "open", "overlap"])].itertuples():
        hit = [(k, np.where(A[k]["time"].values == np.datetime64(r.signal))[0]) for k in cands.get(r.name, [])]
        hit = [(k, i) for k, i in hit if len(i)]
        if not hit:
            unmapped += 1; continue
        k, i = hit[0]; a = A[k]
        i = int(i[0]); c = float(a.close.iloc[i])
        sub = a.iloc[: i + 1]
        h, l, cc = sub.high.values.astype(float), sub.low.values.astype(float), sub.close.values.astype(float)
        at = RU.atr(h, l, cc)[-1]; risk = min(max(h[-5:].max() - cc[-1] + 0.1 * at, 0.5 * at), 3 * at)
        L.append(dict(strategy="SF-CONT-SELL-v1", signal_date=r.signal, symbol=str(a.symbol.iloc[i]), key=k, close=c, risk=risk, risk_pct=risk / c,
                      detected_on=r.signal, signal_id=f"{r.name}|{r.signal:%Y-%m-%d}"))
        sym_on[(str(a.symbol.iloc[i]), r.signal)] = r.name
    L = pd.DataFrame(L)
    fo = fo[fo.symbol.isin(set(L.symbol))]
    days = pd.DatetimeIndex(sorted(fo.date.unique()))
    entry_days = sorted({d for d in (EN._next_session(days, s) for s in L.signal_date) if d is not None})
    with ThreadPoolExecutor(6) as ex:
        bl = dict(zip(entry_days, ex.map(DA.ban, entry_days)))
    X = EN.lifecycle_sf(L, A, fo, days, reg, {}, days[-1], bl)
    X.to_csv(OUT / "investigate_sf_futures.csv.gz", index=False, compression="gzip")
    ex_ = X[X.get("exec_R").notna()] if "exec_R" in X else X.iloc[0:0]
    done = ex_[ex_.status.astype(str).str.startswith(("TARGET", "STOP", "TIME"))]
    out["futures_execution"] = dict(
        signals=len(X), signals_unmapped=unmapped, executed=len(ex_), closed=len(done),
        not_executable={k: int(v) for k, v in X.status.astype(str)[X.status.astype(str).str.startswith("NOT EXEC")].value_counts().items()},
        overlap=int(X.status.astype(str).str.startswith("OVERLAP").sum()), ban_lists_found=sum(v is not None for v in bl.values()), ban_lists_needed=len(bl),
        exec_on_futures=st(done.exec_R), research_basis_same_trades=st(done.research_R),
        exec_minus_research_R=round(float((done.exec_R - done.research_R).mean()), 3) if len(done) else None,
        exec_by_year={int(k): st(g.exec_R) for k, g in done.groupby(pd.to_datetime(done.entry_date).dt.year)},
        rolls_share=round(100 * (done.rolls > 0).mean(), 1) if len(done) else None)
    json.dump(out, open(OUT / "investigate_sf.json", "w"), indent=1, default=str)
    return out


# ───────────────────────── CM ─────────────────────────
def cm():
    p = RU.RULES["CM-CONT-BUY-v1"]
    T = pd.read_csv(OUT / "parity_CM-CONT-BUY-v1.csv.gz", parse_dates=["signal", "entry", "exit"])
    T = T[T.status.isin(["trade", "open"])].copy()
    raw = pd.concat([pd.read_csv(f, parse_dates=["date"], usecols=["date", "symbol", "series", "open", "high", "low", "close", "prevclose", "value"])
                     for f in sorted((ROOT / "research/data/nse_cm").glob("20*.csv.gz"))], ignore_index=True)
    raw = raw[raw.series.isin(["EQ", "BE"])].sort_values(["date", "symbol", "series"]).drop_duplicates(["date", "symbol"], keep="last")
    R = raw.set_index(["date", "symbol"])
    days = pd.DatetimeIndex(sorted(raw.date.unique()))
    # the weekly bar label is the last session of the week; entry = first session after it
    T["entry_day"] = [EN._next_session(days, s) for s in T.signal]
    rows = []
    for r in T.itertuples():
        x = R.loc[(r.entry_day, r.name)] if (r.entry_day, r.name) in R.index else None
        if x is None:
            rows.append(dict(entry_raw="missing")); continue
        rows.append(dict(entry_gap_pct=100 * (x.open / x.prevclose - 1), entry_value_cr=x.value / 1e7, participation_pct=100 * p["order_value"] / max(x.value, 1),
                         entry_locked_up=bool(x.open == x.high == x.low and x.open > x.prevclose), series=x.series))
    T = pd.concat([T.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    # daily order of events inside each week is tracked by the forward shadow test (lifecycle_cm); not re-derived here
    T["exit_day_locked_down"] = [bool((R.loc[(d, n)].open == R.loc[(d, n)].high == R.loc[(d, n)].low) and R.loc[(d, n)].open < R.loc[(d, n)].prevclose)
                                 if (d, n) in R.index else False for d, n in zip(T.exit, T.name)]
    T["gap_stop"] = T.reason.eq("stop (gap)")
    # incremental vs the live monthly momentum rule (B0, monthly, 10 stocks, MA100 market filter)
    from research.cashq import mom_volume as MV
    d = MV.D(*MV.load()); MR, MP = MV.backtest(d, "B0", 10, "M")
    MP["start"] = pd.to_datetime(MP.start); MR["start"], MR["end"] = pd.to_datetime(MR.start), pd.to_datetime(MR.end)
    per = MR[["start", "end"]].reset_index(drop=True)
    held = {}
    for r in MP.itertuples():
        held.setdefault(r.start, set()).add(r.sym)

    def in_mom(sym, day):
        k = per[(per.start <= day) & (per.end > day)]
        return bool(len(k)) and sym in held.get(k.start.iloc[0], set())
    T["in_momentum"] = [in_mom(n, d_) for n, d_ in zip(T.name, T.entry_day)]
    T["mom_invested"] = [bool(len(per[(per.start <= d_) & (per.end > d_)]) and len(held.get(per[(per.start <= d_) & (per.end > d_)].start.iloc[0], ())) > 0)
                         for d_ in T.entry_day]
    T["month"] = T.entry_day.dt.to_period("M")
    cmm = T.groupby("month").apply(lambda g: (g.netR * 0.01).sum())          # 1 % risk per trade -> monthly return proxy
    mm = MR.assign(month=MR.start.dt.to_period("M")).set_index("month").ret
    j = pd.concat([cmm.rename("cm"), mm.rename("mom")], axis=1).dropna()
    T["participation_bucket"] = pd.cut(T.participation_pct, [0, 0.5, 1, 2, 5, 1000], labels=["<0.5%", "0.5-1%", "1-2%", "2-5%", ">5%"]).astype(str)
    T["gap_bucket"] = pd.cut(T.entry_gap_pct, [-100, -2, 0, 2, 5, 100], labels=["<-2%", "-2..0%", "0..2%", "2..5%", ">5%"]).astype(str)
    out = dict(all=st(T.netR), entry_locked_up_circuit=int(T.entry_locked_up.fillna(False).sum()),
               exit_day_locked_lower_circuit=int(T.exit_day_locked_down.sum()), BE_series_entries=int((T.series == "BE").sum()),
               by_participation=grp(T, "participation_bucket"), participation_median_pct=round(float(T.participation_pct.median()), 3),
               share_participation_over_2pct=round(100 * float((T.participation_pct > 2).mean()), 1),
               by_entry_gap=grp(T, "gap_bucket"), gap_through_stop=dict(n=int(T.gap_stop.sum()), avg_R=round(float(T[T.gap_stop].netR.mean()), 3) if T.gap_stop.any() else None),
               worst_trades=T.nsmallest(5, "netR")[["name", "entry_day", "netR", "reason"]].astype(str).to_dict("records"),
               momentum=dict(overlap_share_pct=round(100 * T.in_momentum.mean(), 1), in_momentum=st(T[T.in_momentum].netR),
                             not_in_momentum=st(T[~T.in_momentum].netR), when_momentum_invested=st(T[T.mom_invested].netR),
                             when_momentum_in_cash=st(T[~T.mom_invested].netR),
                             monthly_correlation=round(float(j.cm.corr(j.mom)), 3) if len(j) > 10 else None, months=len(j)))
    T.drop(columns=["month"]).to_csv(OUT / "investigate_cm_trades.csv.gz", index=False, compression="gzip")
    json.dump(out, open(OUT / "investigate_cm.json", "w"), indent=1, default=str)
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("sf", "both"):
        print(json.dumps(sf(), indent=1, default=str)[:6000], flush=True)
    if which in ("cm", "both"):
        print(json.dumps(cm(), indent=1, default=str)[:6000], flush=True)
