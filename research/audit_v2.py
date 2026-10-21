"""Phase 1 audit of the v1 MCX_DAILY_REAL results (C and G). Does not modify v1 outputs.

  python -m research.audit_v2      -> research/output_v2/audit/
"""
from pathlib import Path
import glob
import numpy as np
import pandas as pd
from research import continuous as CO, engine_daily as ED, roll_adjust as RA, portfolio as PF1, portfolio_mtm as PM
from research.instruments import REGISTRY

ROOT = Path(__file__).resolve().parent
V1 = ROOT / "output"
OUT = ROOT / "output_v2" / "audit"
COMMOD = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]


def w(df, name):
    OUT.mkdir(parents=True, exist_ok=True); df.to_csv(OUT / name, index=False); return df


def data_defects():
    rows, rolls = [], []
    for n in COMMOD:
        raw, _ = RA.load_mcx(n, adjusted=False)
        adj, tab = RA.load_mcx(n, adjusted=True)
        g = raw["time"].diff().dt.days
        hole_list = [f"{raw.time[i - 1].date()} → {raw.time[i].date()} ({int(g[i])}d)" for i in np.where(g > RA.HOLE_DAYS)[0]]
        med = raw["volume"].median()
        rows.append(dict(instrument=n, first=raw.time.min().date(), last=raw.time.max().date(), bars=len(raw),
                         data_holes=len(hole_list), holes="; ".join(hole_list),
                         saturday_sundays=int((raw.time.dt.weekday >= 5).sum()),
                         note_weekend="MCX had Saturday sessions until 2013 + special sessions",
                         illiquid_days_vol_lt_1pct_median=int((raw["volume"] < 0.01 * med).sum()),
                         rolls_detected=len(tab), rolls_expected_per_year=len(RA.RULES[n][0]),
                         rolls_detected_per_year=round(len(tab) / max((raw.time.max() - raw.time.min()).days / 365.25, 1), 1),
                         est_roll_gap_mean_pct=round(tab.est_gap_pct.mean(), 3) if len(tab) else np.nan,
                         est_cum_roll_drift_pct=round(tab.est_gap_pct.sum(), 1) if len(tab) else np.nan))
        rolls.append(tab)
    w(pd.concat(rolls), "estimated_rolls.csv")
    return w(pd.DataFrame(rows), "data_defects.csv")


def roll_estimator_validation():
    v = pd.concat([RA.validate_on_index(None, CO.load_angel(n, "ONE_DAY"), n) for n in ("NIFTY", "BANKNIFTY")]).dropna()
    w(v, "roll_estimator_validation.csv")
    return dict(n=len(v), corr=round(v[["true_gap_pct", "est_gap_pct"]].corr().iloc[0, 1], 3),
                mean_true=round(v.true_gap_pct.mean(), 3), mean_est=round(v.est_gap_pct.mean(), 3),
                mae=round((v.true_gap_pct - v.est_gap_pct).abs().mean(), 3),
                cum_true=round(v.true_gap_pct.sum(), 1), cum_est=round(v.est_gap_pct.sum(), 1))


def trade_audit(strat):
    t = pd.concat([pd.read_csv(f, parse_dates=["signal_time", "entry_time", "exit_time"])
                   for f in glob.glob(str(V1 / "trades" / "MCX_DAILY_REAL" / strat / "*.csv"))], ignore_index=True)
    rows = []
    for _, x in t.iterrows():
        n = x.instrument
        raw, _ = RA.load_mcx(n, adjusted=False)
        adj, tab = RA.load_mcx(n, adjusted=True)
        d = ED.add_indicators(CO.load_angel(n, "ONE_DAY"))
        i = d.index[d.time == x.signal_time][0]; j = i + 1
        k = d.index[d.time == x.exit_time][0]
        s = 1 if x.side == "LONG" else -1
        R_check = 2.0 * d.at[i, "atr"]
        hold = raw.iloc[j:k + 1]
        holes = int((hold["time"].diff().dt.days > RA.HOLE_DAYS).sum())
        rs = tab[(tab.switch_day > x.entry_time) & (tab.switch_day <= x.exit_time)] if len(tab) else tab
        carry_pts = rs.est_gap_pts.sum() if len(rs) else 0.0          # price jumps that were contract switches
        # proxy consistency: MCX % move vs proxy x USD/INR % move over the holding period
        er = RA.expected_return(n, pd.DatetimeIndex(hold["time"].dt.normalize()),
                                None if n != "ZINC" else None)
        proxy_move = (np.nanprod(1 + er.fillna(0).values[1:]) - 1) * 100 if len(er) > 1 and er.notna().any() else np.nan
        mcx_move = (x.exit_px / x.entry_px - 1) * 100
        rows.append(dict(instrument=n, side=x.side, signal=x.signal_time.date(), entry=x.entry_time.date(),
                         exit=x.exit_time.date(), entry_px=x.entry_px, exit_px=x.exit_px, exit_reason=x.exit_reason,
                         R_pts=round(x.R_pts, 2), R_recomputed=round(R_check, 2), R_ok=abs(R_check - x.R_pts) < 1e-6,
                         entry_is_next_open=bool(np.isclose(d.at[j, "open"], x.entry_px)),
                         net_R=round(x.net_R, 2), mcx_move_pct=round(mcx_move, 1), proxy_fx_move_pct=round(proxy_move, 1),
                         contract_switches=len(rs), est_roll_jump_R=round(s * carry_pts / x.R_pts, 2),
                         net_R_ex_roll=round(x.net_R - s * carry_pts / x.R_pts, 2), data_holes_in_hold=holes,
                         rs_per_lot=round(x.pnl_rs_1lot), rs_check=round(x.net_R * x.R_pts * REGISTRY[n]["mult"]),
                         contract="Angel front-month stitched (actual contract & expiry not identifiable per day)",
                         lot=f"{REGISTRY[n]['lot']} (current spec; mult ₹{REGISTRY[n]['mult']}/pt)",
                         flag_gt10R=x.net_R > 10,
                         cause=("data hole" if holes else "roll jumps material" if abs(s * carry_pts / x.R_pts) > 0.5
                                else "genuine move (consistent with proxy)" if pd.notna(proxy_move) and np.sign(proxy_move) == np.sign(mcx_move)
                                and abs(proxy_move - mcx_move) < max(10, 0.25 * abs(mcx_move))
                                else "check: MCX and proxy disagree" if pd.notna(proxy_move) else "no proxy to cross-check")))
    a = pd.DataFrame(rows)
    w(a, f"trade_audit_MCX_DAILY_REAL_{strat}.csv")
    return a, t


def main():
    dd = data_defects()
    val = roll_estimator_validation()
    summary = {"roll_estimator_validation": val}
    for strat in ("C", "G"):
        a, t = trade_audit(strat)
        t["exit_time"] = pd.to_datetime(t["exit_time"])
        by_month = t.groupby(t.exit_time.dt.to_period("M"))["net_R"].sum()
        top = t.sort_values("net_R", ascending=False)
        summary[strat] = dict(trades=len(t), total_R=round(t.net_R.sum(), 1),
                              top5_share_pct=round(top.net_R.head(5).sum() / t.net_R.sum() * 100),
                              trades_gt10R=int((t.net_R > 10).sum()), R_from_2026=round(t[t.exit_time.dt.year == 2026].net_R.sum(), 1),
                              best_month=str(by_month.idxmax()), best_month_R=round(by_month.max(), 1),
                              trades_spanning_data_hole=int((a.data_holes_in_hold > 0).sum()),
                              R_of_trades_spanning_hole=round(a.loc[a.data_holes_in_hold > 0, "net_R"].sum(), 1),
                              est_roll_jump_R_total=round(a.est_roll_jump_R.sum(), 1),
                              R_ok_all=bool(a.R_ok.all()), entries_next_open_all=bool(a.entry_is_next_open.all()),
                              rupee_calc_ok=bool((a.rs_per_lot - a.rs_check).abs().max() <= 1))
        # portfolio reconciliation: v1 (fixed capital, closed-trade equity, no margin) vs v2 MTM
        frames = {n: RA.load_mcx(n, adjusted=False)[0] for n in COMMOD}
        oos = t[pd.to_datetime(t.entry_time) >= pd.Timestamp("2021-08-08")].copy()
        oos["valid"] = True
        tt = oos.copy(); tt["entry_adj"] = tt["entry_px"]          # raw series: adj == raw
        _, s1 = PF1.simulate(oos, 2_500_000, 0.02, 6, 0.08)
        _, eq2, s2 = PM.simulate(tt, frames, 2_500_000, risk_pct=0.02, max_pos=6, max_open_risk=0.08,
                                 group_risk=0.08, max_capital_use=10.0, daily_loss=1.0)
        _, _, s2b = PM.simulate(tt, frames, 2_500_000, risk_pct=0.02, max_pos=6, max_open_risk=0.08,
                                group_risk=0.08, max_capital_use=10.0, daily_loss=1.0, size_on_equity=False)
        _, eq3, s3 = PM.simulate(tt, frames, 2_500_000, risk_pct=0.02, max_pos=6, max_open_risk=0.08,
                                 group_risk=0.04, max_capital_use=0.5, daily_loss=0.03)
        summary[strat]["reconcile_oos"] = dict(
            v1_closed_trade_fixed_capital=dict(return_pct=s1.get("return_pct"), max_dd_pct=s1.get("max_dd_pct"), taken=s1.get("taken")),
            v2_mtm_fixed_capital_sizing=dict(return_pct=s2b.get("return_pct"), max_dd_pct=s2b.get("max_dd_pct"), taken=s2b.get("taken")),
            v2_mtm_same_limits=dict(return_pct=s2.get("return_pct"), max_dd_pct=s2.get("max_dd_pct"), taken=s2.get("taken")),
            v2_mtm_with_margin_group_daily_loss=dict(return_pct=s3.get("return_pct"), max_dd_pct=s3.get("max_dd_pct"),
                                                     taken=s3.get("taken"), skips={k: v for k, v in s3.items() if k.startswith("skip")}))
    import json
    (OUT / "audit_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    print(dd.to_string())


if __name__ == "__main__":
    main()
