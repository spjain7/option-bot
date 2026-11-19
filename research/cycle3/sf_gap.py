"""Cycle 3 · 2 – where the 0.085R real-futures shortfall of SF-CONT-SELL-v1 comes from (v1 itself unchanged).
For every executed v1 trade (research/cycle2/results/sf_crowd_trades.csv.gz, version v1) the cash path (adjusted AND raw
bhavcopy prices) and the futures path of the contract actually used (NSE F&O bhavcopy) are rebuilt day by day with the
same stop distance in % of the entry open. Then, for trades whose futures exit differs from the research (cash) exit:
  basis      futures / raw cash - 1 at the entry open, at the close of each day, and at the HIGH of the futures stop day
  causes     (a) corporate action inside the trade (adjusted cash != raw cash; futures follow raw prices, NSE adjusts
                 futures only for bonus / split, not for ordinary dividends)
             (b) expiry inside the trade (roll) or entry in the next month on expiry day
             (c) basis move: the futures stop-day high is above the stop only because the premium widened (the raw cash
                 high stayed below the same % stop)
             (d) futures-only spike: futures high > stop while the futures CLOSE basis that day is normal (thin contract
                 print; intraday futures history is not stored, so this is identified from daily high vs close)
             (e) entry difference: futures open vs cash open gap (the trade starts at a different point)
Daily bars only (no intraday futures history); Best-5 depth does not exist for these dates.
python -m research.cycle3.sf_gap  ->  results/sf_gap.json, results/sf_gap_trades.csv.gz"""
import glob
import json
import pickle
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent / "results"; OUT.mkdir(parents=True, exist_ok=True)


def main():
    X = pd.read_csv(ROOT / "research/cycle2/results/sf_crowd_trades.csv.gz", low_memory=False, parse_dates=["signal_date", "entry_date", "exit_date", "research_exit"])
    X = X[X.version.str.startswith("v1") & X.status.astype(str).str.startswith(("TARGET", "STOP", "TIME"))].copy()
    A = pickle.loads((ROOT / "research/data/nse_cm/_adjusted.pkl").read_bytes())
    fs = sorted(glob.glob(str(ROOT / "research/data/nse_fut_pit/days/*.csv.gz")))
    fo = pd.concat((pd.read_csv(f, usecols=["date", "symbol", "kind", "expiry", "open", "high", "low", "close", "contracts"]) for f in fs), ignore_index=True)
    fo = fo[(fo.kind == "STK") & fo.symbol.isin(set(X.symbol))]
    fo["date"], fo["expiry"] = pd.to_datetime(fo.date), pd.to_datetime(fo.expiry)
    fo = fo.set_index(["symbol", "expiry", "date"]).sort_index()
    rows = []
    for r in X.itertuples():
        a = A[r.key].copy(); a["time"] = pd.to_datetime(a["time"])
        f = a["factor"].values.astype(float); cum = np.r_[np.cumprod(f[::-1])[::-1][1:], 1.0]
        a["raw_o"], a["raw_h"], a["raw_c"] = a.open / cum, a.high / cum, a.close / cum
        a = a.set_index("time")
        exp = pd.Timestamp(r.contract.split(" ", 1)[1])
        try:
            fp = fo.loc[(r.symbol, exp)]
        except KeyError:
            continue
        end = max(r.exit_date, r.research_exit)
        days = a.index[(a.index >= r.entry_date) & (a.index <= end)]
        if not len(days) or r.entry_date not in fp.index:
            continue
        oc, of = a.at[r.entry_date, "open"], fp.at[r.entry_date, "open"]
        k = r.risk / oc                                           # stop distance in % of the entry open (research)
        st_c, st_f = oc * (1 + k), of * (1 + k)
        ca = any(a.loc[days, "factor"].values != 1.0)
        first_c = next((d for d in days if a.at[d, "high"] >= st_c or (d > r.entry_date and a.at[d, "open"] >= st_c)), None)
        first_f = next((d for d in days if d in fp.index and (fp.at[d, "high"] >= st_f or (d > r.entry_date and fp.at[d, "open"] >= st_f))), None)
        b_e = of / a.at[r.entry_date, "raw_o"] - 1
        row = dict(signal_id=r.signal_id, symbol=r.symbol, entry=r.entry_date, exec_R=r.exec_R, research_R=r.research_R, gap_R=r.exec_R - r.research_R,
                   same_exit=r.exit_date == r.research_exit, exec_reason=r.status, research_reason=r.research_reason, stop_pct=round(100 * k, 3),
                   basis_entry_pct=round(100 * b_e, 3), entry_gap_vs_signal_pct=round(100 * (of / r.close - 1), 3), corp_action_in_trade=bool(ca),
                   expiry_in_trade=bool(exp <= end) or bool(r.rolls), next_month_entry=isinstance(r.contract_note, str),
                   contracts_entry=float(fp.at[r.entry_date, "contracts"]), fut_stop_day=first_f, cash_stop_day=first_c)
        if first_f is not None:
            d = first_f
            b_h = fp.at[d, "high"] / a.at[d, "raw_h"] - 1; b_c = fp.at[d, "close"] / a.at[d, "raw_c"] - 1
            row.update(basis_at_stopday_high_pct=round(100 * b_h, 3), basis_at_stopday_close_pct=round(100 * b_c, 3),
                       basis_change_to_high_pct=round(100 * (b_h - b_e), 3), cash_high_vs_stop_pct=round(100 * (a.at[d, "high"] / st_c - 1), 3),
                       contracts_stopday=float(fp.at[d, "contracts"]))
        rows.append(row)
    T = pd.DataFrame(rows)
    D = T[~T.same_exit].copy()
    fut_only = D[D.fut_stop_day.notna() & (D.cash_stop_day.isna() | (pd.to_datetime(D.fut_stop_day) < pd.to_datetime(D.cash_stop_day)))].copy()

    def cause(x):
        if x.corp_action_in_trade:
            return "a corporate action inside the trade"
        if x.next_month_entry or (x.expiry_in_trade and pd.notna(x.fut_stop_day) and pd.Timestamp(x.fut_stop_day) >= pd.Timestamp(x.entry)):
            if x.expiry_in_trade:
                return "b expiry / roll inside the trade"
        if pd.notna(x.get("basis_change_to_high_pct")) and x.basis_change_to_high_pct >= 0.15 and \
                pd.notna(x.basis_at_stopday_close_pct) and (x.basis_at_stopday_close_pct - x.basis_entry_pct) >= 0.1:
            return "c premium widened (close basis also up)"
        if pd.notna(x.get("basis_change_to_high_pct")) and x.basis_change_to_high_pct >= 0.15:
            return "d futures-only intraday spike (close basis normal)"
        return "e small basis noise (< 0.15 %) – stop sat right at the high"
    fut_only["cause"] = fut_only.apply(cause, axis=1)
    rev = D[D.cash_stop_day.notna() & (D.fut_stop_day.isna() | (pd.to_datetime(D.cash_stop_day) < pd.to_datetime(D.fut_stop_day)))]
    res = dict(executed_trades=len(T), same_exit=int(T.same_exit.sum()), exit_differs=len(D),
               mean_gap_all_R=round(float(T.gap_R.mean()), 3), mean_gap_same_exit_R=round(float(T[T.same_exit].gap_R.mean()), 3),
               mean_gap_exit_differs_R=round(float(D.gap_R.mean()), 3), gap_total_R=round(float(T.gap_R.sum()), 1),
               futures_stopped_first=dict(n=len(fut_only), gap_sum_R=round(float(fut_only.gap_R.sum()), 1), gap_mean_R=round(float(fut_only.gap_R.mean()), 3),
                                          by_cause={c: dict(n=int(len(g)), gap_sum_R=round(float(g.gap_R.sum()), 1), gap_mean_R=round(float(g.gap_R.mean()), 3),
                                                            basis_change_to_high_median_pct=round(float(g.basis_change_to_high_pct.median()), 3) if g.basis_change_to_high_pct.notna().any() else None)
                                                    for c, g in fut_only.groupby("cause")},
                                          cash_high_vs_stop_median_pct=round(float(fut_only.cash_high_vs_stop_pct.median()), 3),
                                          stop_pct_median=round(float(fut_only.stop_pct.median()), 3),
                                          basis_change_to_high_median_pct=round(float(fut_only.basis_change_to_high_pct.median()), 3)),
               cash_stopped_first=dict(n=len(rev), gap_sum_R=round(float(rev.gap_R.sum()), 1), gap_mean_R=round(float(rev.gap_R.mean()), 3)),
               other_exit_differences=dict(n=len(D) - len(fut_only) - len(rev), gap_sum_R=round(float(D.drop(fut_only.index.union(rev.index)).gap_R.sum()), 1)),
               entry_basis=dict(median_pct=round(float(T.basis_entry_pct.median()), 3), p10=round(float(T.basis_entry_pct.quantile(0.1)), 3),
                                p90=round(float(T.basis_entry_pct.quantile(0.9)), 3)),
               gap_by_entry_basis={str(k): round(float(g.gap_R.mean()), 3) for k, g in T.groupby(pd.cut(T.basis_entry_pct, [-50, -0.5, 0, 0.5, 1, 50]))},
               gap_by_stop_pct={str(k): round(float(g.gap_R.mean()), 3) for k, g in T.groupby(pd.cut(T.stop_pct, [0, 1.5, 2.5, 4, 100]))},
               gap_by_contract_liquidity={str(k): round(float(g.gap_R.mean()), 3) for k, g in T.groupby(pd.qcut(T.contracts_entry, 4, duplicates="drop"))})
    T.to_csv(OUT / "sf_gap_trades.csv.gz", index=False, compression="gzip")
    json.dump(res, open(OUT / "sf_gap.json", "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
