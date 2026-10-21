"""Full-universe research backtest (research / paper mode only - touches nothing live).

  python -m research.adapters.nse_bhavcopy 2011-01-01     # REAL NSE index-futures data (one-time, ~25 min)
  python -m research.adapters.yahoo_proxy                 # PROXY data
  (optional) run GitHub workflow "Research data", then:
  git fetch origin research-data && git archive origin/research-data research/data/angel | tar -x
  python -m research.run_all                              # everything below -> research/output/

Plan, periods and pass/fail rules: research/CRITERIA.md (fixed before results).
"""
import json, itertools, subprocess, time
from pathlib import Path
import numpy as np
import pandas as pd
from research import continuous as CO, engine_daily as ED, engine_hourly as EH, metrics as MT, portfolio as PF
from research.instruments import REGISTRY, COSTS

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
CAPITAL, RISK, MAXPOS, MAXRISK = 2_500_000, 0.02, 6, 0.08
INDEX = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"]
COMMOD = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]
IDX_STRATS = ["B", "C", "D", "E", "F", "G", "H1", "H2", "H3", "H4", "I"]
COM_STRATS = ["B", "C", "D", "E", "G", "H1", "H2", "H4"]
# periods: fixed dates from CRITERIA.md, or "prop" = first 50% train / 25% validation / last 25% OOS of the data
GROUPS = {
    "INDEX_DAILY_REAL": dict(tf="1d", grade="REAL", clean=True, strats=IDX_STRATS,
                             periods=("2011-01-01", "2017-01-01", "2021-01-01"), wf_from=2017),
    "MCX_DAILY_PROXY": dict(tf="1d", grade="PROXY", clean=False, strats=COM_STRATS,
                            periods=("2005-01-01", "2013-01-01", "2018-01-01"), wf_from=2013),
    "MCX_DAILY_REAL": dict(tf="1d", grade="REAL-UNADJ", clean=False, strats=COM_STRATS, periods="prop"),
    "MCX_HOURLY_PROXY": dict(tf="1h", grade="PROXY", clean=False, strats=["A"], periods="prop"),
    "INDEX_HOURLY_PROXY": dict(tf="1h", grade="PROXY", clean=True, strats=["A"], periods="prop"),
    "MCX_HOURLY_REAL": dict(tf="1h", grade="REAL-UNADJ", clean=False, strats=["A"], periods="prop"),
    "INDEX_HOURLY_REAL": dict(tf="1h", grade="REAL-UNADJ", clean=True, strats=["A"], periods="prop"),
}
GRID_C = [dict(entry=a, exit=b, stop=s) for a, b, s in itertools.product((40, 55, 70), (15, 20, 25), (1.5, 2.0, 2.5))]
GRID_B = [dict(entry=a, exit=b) for a, b in itertools.product((15, 20, 25), (7, 10, 13))]
GRID_A = [dict(brk=a, min_adx=b) for a, b in itertools.product((3, 5, 8), (15, 20, 25))]
VARIANTS = {"count": 0}
KEEP = ("trades", "expectancy_R", "gross_expectancy_R", "pf", "total_R", "max_dd_R", "win_pct", "avg_days")


def w(df, *parts):
    f = OUT.joinpath(*parts); f.parent.mkdir(parents=True, exist_ok=True); df.to_csv(f, index=False); return f


# ───────────────────────── data ─────────────────────────
def load_data():
    D = {g: {} for g in GROUPS}
    cov = []
    t0 = time.time()
    nse = CO.load_nse(INDEX, roll_days=3)
    for n in INDEX:
        d = nse.get(n)
        if d is None or d.empty:
            cov.append(dict(group="INDEX_DAILY_REAL", instrument=n, source="NSE F&O bhavcopy", grade="MISSING", bars=0)); continue
        D["INDEX_DAILY_REAL"][n] = ED.add_indicators(d)
        cov.append(dict(group="INDEX_DAILY_REAL", instrument=n, source="NSE F&O bhavcopy (contract level, back-adjusted at our rolls)",
                        grade="REAL", start=d.time.min(), end=d.time.max(), bars=len(d), rolls=int(d.roll.sum()),
                        untraded_days=int((~d.traded).sum()), volume=True, oi=True))
    for n in COMMOD:
        r = REGISTRY[n]
        for tf, g in (("1d", "MCX_DAILY_PROXY"), ("1h", "MCX_HOURLY_PROXY")):
            d = CO.load_proxy(n, tf)
            if d is None:
                cov.append(dict(group=g, instrument=n, source="none", grade="MISSING", bars=0,
                                note="no free history (Yahoo lists no zinc future; MCX bhavcopy blocked here)")); continue
            D[g][n] = ED.add_indicators(d) if tf == "1d" else d
            cov.append(dict(group=g, instrument=n, source=f"Yahoo {r['proxy']} (international front month, unadjusted)",
                            grade="PROXY", start=d.time.min(), end=d.time.max(), bars=len(d), rolls="unknown", volume=True, oi=False))
    for n in INDEX:
        d = CO.load_proxy(n, "1h")
        if d is None:
            cov.append(dict(group="INDEX_HOURLY_PROXY", instrument=n, source="none", grade="MISSING", bars=0,
                            note="no free hourly history")); continue
        D["INDEX_HOURLY_PROXY"][n] = d
        cov.append(dict(group="INDEX_HOURLY_PROXY", instrument=n, source=f"Yahoo {REGISTRY[n]['hourly_proxy']} (cash index)",
                        grade="PROXY", start=d.time.min(), end=d.time.max(), bars=len(d), volume=False, oi=False))
    for names, iv, g in ((COMMOD, "ONE_DAY", "MCX_DAILY_REAL"), (COMMOD, "ONE_HOUR", "MCX_HOURLY_REAL"),
                         (INDEX, "ONE_HOUR", "INDEX_HOURLY_REAL")):
        for n in names:
            d = CO.load_angel(n, iv)
            if d is None or len(d) < 300:
                cov.append(dict(group=g, instrument=n, source="Angel One (front-month stitched by vendor)", grade="MISSING",
                                bars=0 if d is None else len(d), note="not downloaded or too short")); continue
            D[g][n] = ED.add_indicators(d) if iv == "ONE_DAY" else d
            cov.append(dict(group=g, instrument=n, source="Angel One (front-month stitched by vendor, NOT back-adjusted)",
                            grade="REAL-UNADJ", start=d.time.min(), end=d.time.max(), bars=len(d), rolls="at expiry (vendor)",
                            volume=True, oi=False, note="MCX OI history not served by Angel"))
    print(f"data loaded in {time.time() - t0:.0f}s")
    return D, pd.DataFrame(cov)


def resolve_periods(G, data):
    if G["periods"] != "prop":
        return G["periods"], G.get("wf_from")
    lo = min(d.time.min() for d in data.values()); hi = max(d.time.max() for d in data.values())
    span = hi - lo
    p = (str(lo.date()), str((lo + span * 0.5).date()), str((lo + span * 0.75).date()))
    return p, (pd.Timestamp(p[1]).year + 1 if G["tf"] == "1d" else None)


# ───────────────────────── helpers ─────────────────────────
def run_group(data, strat, over=None, cost_x=1.0):
    VARIANTS["count"] += 1
    if strat == "A":
        ts = [EH.run(n, d, over, cost_x) for n, d in data.items()]
    else:
        p = {**ED.STRATS[strat], **(over or {})}
        ts = [ED.run(n, d, p, cost_x) for n, d in data.items()]
    ts = [t for t in ts if not t.empty]
    return pd.concat(ts, ignore_index=True) if ts else pd.DataFrame()


def split(t, periods):
    tr, va, oos = periods
    return MT.period(t, tr, pd.Timestamp(va) - pd.Timedelta(days=1)), \
        MT.period(t, va, pd.Timestamp(oos) - pd.Timedelta(days=1)), MT.period(t, oos)


def walk_forward(runs, start_year, min_train=20):
    """runs: list of (params, trades). Anchored yearly: pick best train expectancy, apply to the next year."""
    if not runs or start_year is None:
        return pd.DataFrame(), []
    last = max(pd.to_datetime(t["entry_time"]).max().year for _, t in runs if not t.empty)
    picks, out = [], []
    for y in range(start_year, last + 1):
        best, bv = None, -9
        for p, t in runs:
            if t.empty:
                continue
            tr = t[pd.to_datetime(t["entry_time"]) < pd.Timestamp(f"{y}-01-01")]
            if len(tr) >= min_train and tr["net_R"].mean() > bv:
                best, bv = (p, t), tr["net_R"].mean()
        if best is None:
            continue
        p, t = best
        yy = t[pd.to_datetime(t["entry_time"]).dt.year == y]
        out.append(yy); picks.append(dict(year=y, params=json.dumps(p), train_exp_R=round(bv, 3), test_trades=len(yy),
                                          test_exp_R=round(yy["net_R"].mean(), 3) if len(yy) else np.nan))
    return (pd.concat(out) if out else pd.DataFrame()), picks


def breakdowns(t, key):
    if t.empty:
        return
    t = t.copy()
    t["year"] = pd.to_datetime(t["exit_time"]).dt.year
    t["month"] = pd.to_datetime(t["exit_time"]).dt.to_period("M").astype(str)
    t["adx_bucket"] = pd.cut(t["adx"], [-1, 20, 30, 200], labels=["ADX<20", "ADX20-30", "ADX>30"]).astype(str)
    if "atrp_pct" in t:
        t["vol_bucket"] = pd.cut(t["atrp_pct"], [-1, 33, 66, 101], labels=["low vol", "mid vol", "high vol"]).astype(str)
        t["trend"] = np.where(t["trend_up"], "above 200d", "below 200d")
    rows = []
    for dim in ("side", "instrument", "year", "month", "adx_bucket", "vol_bucket", "trend", "exit_reason"):
        if dim not in t:
            continue
        for v, g in t.groupby(dim):
            rows.append(dict(dimension=dim, value=v, trades=len(g), expectancy_R=round(g.net_R.mean(), 3),
                             gross_expectancy_R=round(g.gross_R.mean(), 3), total_R=round(g.net_R.sum(), 1),
                             win_pct=round((g.net_R > 0).mean() * 100, 1), rs_1lot=round(g.pnl_rs_1lot.sum())))
    w(pd.DataFrame(rows), "breakdowns", f"{key}.csv")


def equity_png(curves, title, fname):
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    for lab, (x, y) in curves.items():
        ax.plot(pd.to_datetime(x), y, label=lab, lw=1.2)
    ax.axhline(0, color="#888", lw=0.6); ax.set_title(title); ax.set_ylabel("Cumulative net R"); ax.legend(fontsize=7, ncol=4)
    fig.tight_layout(); (OUT / "equity").mkdir(parents=True, exist_ok=True); fig.savefig(OUT / "equity" / fname, dpi=110); plt.close(fig)


def grade(row, grade_data, clean):
    core = [row["oos_exp_R"] > 0.10, row["oos_boot_p5"] > 0, row["oos_trades"] >= 50, row["oos_pf"] >= 1.20,
            row["oos_exp_R_2x"] > 0]
    wf_ok = True if pd.isna(row["wf_exp_R"]) else row["wf_exp_R"] > 0
    sec = [row["val_exp_R"] > 0 and row["oos_years_pos"] >= 60, row["stability_pct"] >= 70, wf_ok,
           row["oos_max_dd_R"] >= -25]
    names_c = ["exp>0.10R", "boot p5>0", "≥50 trades", "PF≥1.2", "2x costs>0"]
    names_s = ["validation+years", "param stability", "walk-forward", "DD≤25R"]
    fails = [n for n, ok in zip(names_c, core) if not ok] + [n for n, ok in zip(names_s, sec) if not ok]
    if pd.isna(row["wf_exp_R"]):
        fails.append("(walk-forward n/a)")
    if not all(core):
        return "FAIL", fails
    if all(sec) and grade_data == "REAL" and clean and not pd.isna(row["wf_exp_R"]):
        return "PASS", fails
    if sum(not s for s in sec) <= 1:
        return "PAPER-CANDIDATE", fails + ([] if grade_data == "REAL" and clean else ["proxy/unadjusted or already-seen data"])
    return "FAIL", fails


# ───────────────────────── main ─────────────────────────
def main(only=None):
    OUT.mkdir(exist_ok=True)
    D, cov = load_data()
    w(cov, "data_coverage.csv")
    master, pf_rows, pf_summ, curves_all, comparable = [], [], [], {}, []
    used_periods = {}

    def master_rows(group, strat, t, periods, cost_tag):
        parts = dict(zip(("train", "validation", "oos"), split(t, periods))); parts["full"] = t
        for inst in ["ALL"] + sorted(t["instrument"].unique() if not t.empty else []):
            for per, tt in parts.items():
                x = tt if inst == "ALL" else tt[tt.instrument == inst]
                master.append(dict(group=group, strategy=strat, instrument=inst, period=per, costs=cost_tag,
                                   **MT.stats(x, capital=CAPITAL)))

    for g, G in GROUPS.items():
        data = D[g]
        if (only and g not in only) or not data:
            continue
        periods, wf_from = resolve_periods(G, data)
        used_periods[g] = dict(train=periods[0], validation=periods[1], oos=periods[2], walk_forward_from=wf_from)
        for strat in G["strats"]:
            if strat in ("F", "H3") and not all(d["oi"].notna().any() for d in data.values()):
                continue
            t = run_group(data, strat)
            if t.empty:
                continue
            for inst, ti in t.groupby("instrument"):
                w(ti, "trades", g, strat, f"{inst}.csv")
            master_rows(g, strat, t, periods, "1x")
            _, va, oos = split(t, periods)
            stress = {}
            for cx in (0, 2.0, 3.0):
                ts = run_group(data, strat, cost_x=cx)
                stress[cx] = MT.stats(split(ts, periods)[2]).get("expectancy_R", np.nan)
                master_rows(g, strat, ts, periods, f"{cx:g}x" if cx else "before costs")
            grid = GRID_A if strat == "A" else GRID_B if strat == "B" else GRID_C
            runs = [(p, run_group(data, strat, p)) for p in grid]
            oe = [MT.stats(split(tt, periods)[2]).get("expectancy_R", np.nan) for _, tt in runs]
            stab = np.nanmean([e > 0 for e in oe]) * 100
            w(pd.DataFrame([dict(**p, oos_expectancy_R=e) for (p, _), e in zip(runs, oe)]), "sensitivity", g, f"{strat}.csv")
            wf, picks = walk_forward(runs, wf_from)
            if picks:
                w(pd.DataFrame(picks), "walkforward", g, f"{strat}.csv")
            wfo = MT.period(wf, periods[2]) if not wf.empty else wf
            breakdowns(t, f"{g}_{strat}")
            p_all, s_all = PF.simulate(t, CAPITAL, RISK, MAXPOS, MAXRISK)
            p_oos, s_oos = PF.simulate(oos, CAPITAL, RISK, MAXPOS, MAXRISK)
            eq = t.sort_values("exit_time")[["exit_time", "instrument", "net_R", "pnl_rs_1lot"]].copy()
            eq["equity_R"] = eq["net_R"].cumsum()
            w(eq, "equity", "daily" if G["tf"] == "1d" else "hourly", g, f"{strat}_trades_R.csv")
            if not p_all.empty:
                w(p_all, "portfolio", g, f"{strat}_trades.csv")
                w(p_all[["exit_time", "instrument", "lots", "pnl_rs", "equity_rs"]], "equity",
                  "daily" if G["tf"] == "1d" else "hourly", g, f"{strat}_portfolio_rs.csv")
            curves_all.setdefault(g, {})[strat] = (eq["exit_time"], eq["equity_R"])
            pf_summ += [dict(group=g, strategy=strat, period="full", **s_all), dict(group=g, strategy=strat, period="oos", **s_oos)]
            so, sv = MT.stats(oos), MT.stats(va)
            row = dict(group=g, strategy=strat, data=G["grade"], holdout_clean=G["clean"], oos_from=periods[2],
                       oos_trades=so.get("trades", 0), oos_exp_R=so.get("expectancy_R", np.nan),
                       oos_gross_exp_R=so.get("gross_expectancy_R", np.nan), oos_pf=so.get("pf", np.nan),
                       oos_win_pct=so.get("win_pct", np.nan), oos_boot_p5=so.get("boot_p5_R", np.nan),
                       oos_max_dd_R=so.get("max_dd_R", np.nan), oos_years_pos=so.get("years_pos_pct", np.nan),
                       val_exp_R=sv.get("expectancy_R", np.nan), oos_exp_R_before_costs=stress[0],
                       oos_exp_R_2x=stress[2.0], oos_exp_R_3x=stress[3.0], stability_pct=round(stab),
                       wf_exp_R=round(wfo["net_R"].mean(), 3) if not wfo.empty else np.nan,
                       oos_long_exp_R=so.get("long_exp_R"), oos_short_exp_R=so.get("short_exp_R"),
                       oos_max_consec_losses=so.get("max_consec_losses"), oos_avg_days=so.get("avg_days"),
                       oos_portfolio_rs=s_oos.get("net_rs"), oos_portfolio_pct=s_oos.get("return_pct"),
                       oos_portfolio_dd_pct=s_oos.get("max_dd_pct"), oos_portfolio_skipped_size=s_oos.get("skip_size"))
            row["grade"], f = grade(row, G["grade"], G["clean"]); row["fails"] = "; ".join(f)
            pf_rows.append(row)
            print(g, strat, row["grade"], "OOS exp", row["oos_exp_R"], "trades", row["oos_trades"], flush=True)
            if strat == "A":                          # comparable window: hourly A vs daily B/C, same instruments
                lo, hi = min(d.time.min() for d in data.values()), max(d.time.max() for d in data.values())
                dg = {"MCX_HOURLY_PROXY": "MCX_DAILY_PROXY", "MCX_HOURLY_REAL": "MCX_DAILY_REAL",
                      "INDEX_HOURLY_PROXY": "INDEX_DAILY_REAL", "INDEX_HOURLY_REAL": "INDEX_DAILY_REAL"}[g]
                dd = {n: D[dg][n] for n in data if n in D[dg]}
                comparable.append(dict(hourly_group=g, window=f"{lo.date()} → {hi.date()}", strategy="A (hourly)",
                                       instruments=",".join(data), **{k: v for k, v in MT.stats(t).items() if k in KEEP}))
                for s2 in ("B", "C"):
                    td = MT.period(run_group(dd, s2), lo) if dd else pd.DataFrame()
                    comparable.append(dict(hourly_group=g, window=f"{lo.date()} → {hi.date()}", strategy=f"{s2} (daily, {dg})",
                                           instruments=",".join(dd), **{k: v for k, v in MT.stats(td).items() if k in KEEP}))

    # unadjusted-stitch bias check: same index, Angel-style unadjusted front series vs our back-adjusted bhavcopy series
    bias = []
    for n in ("NIFTY", "BANKNIFTY"):
        a = CO.load_angel(n, "ONE_DAY")
        if a is None or n not in D["INDEX_DAILY_REAL"]:
            continue
        a = ED.add_indicators(a); b = D["INDEX_DAILY_REAL"][n]
        lo = max(a.time.min(), b.time.min())
        for s in ("B", "C"):
            ta = MT.period(ED.run(n, a, ED.STRATS[s]), lo + pd.Timedelta(days=300))
            tb = MT.period(ED.run(n, b, ED.STRATS[s]), lo + pd.Timedelta(days=300))
            bias.append(dict(instrument=n, strategy=s, unadjusted_trades=len(ta), unadjusted_exp_R=round(ta.net_R.mean(), 3) if len(ta) else np.nan,
                             adjusted_trades=len(tb), adjusted_exp_R=round(tb.net_R.mean(), 3) if len(tb) else np.nan))
    if bias:
        w(pd.DataFrame(bias), "unadjusted_series_bias_check.csv")

    # ---------- outputs ----------
    w(pd.DataFrame(master), "master_comparison.csv")
    pfdf = pd.DataFrame(pf_rows); w(pfdf, "pass_fail.csv")
    w(pd.DataFrame(pf_summ), "portfolio_summary.csv")
    w(pd.DataFrame(comparable), "daily_vs_hourly_comparable.csv")
    for g, c in curves_all.items():
        equity_png(c, f"{g} – cumulative net R per trade, after costs", f"{g}.png")
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT.parent, text=True).strip()
    except Exception:
        commit = "?"
    cfg = dict(run_at=pd.Timestamp.now().isoformat(), git_commit=commit, capital_rs=CAPITAL, risk_per_trade=RISK,
               max_positions=MAXPOS, max_open_risk=MAXRISK, periods_used=used_periods,
               groups={k: {kk: vv for kk, vv in v.items()} for k, v in GROUPS.items()},
               daily_strategies=ED.STRATS, daily_base=ED.BASE, hourly_base=EH.BASE, hourly_sessions=EH.SESS,
               grids=dict(C=GRID_C, B=GRID_B, A=GRID_A), costs=COSTS,
               slippage_pts={k: v["slip_pts"] for k, v in REGISTRY.items()}, roll_days={k: v["roll_days"] for k, v in REGISTRY.items()},
               variants_run_this_project=VARIANTS["count"], variants_inspected_before_plan=30,
               bootstrap=dict(resamples=5000, seed=12345))
    (OUT / "run_config.json").write_text(json.dumps(cfg, indent=1, default=str))
    md = ["| Group | Strategy | Data | OOS from | OOS trades | Exp (R) after costs | Before costs | PF | Boot p5 | 2× costs | Stability | WF | Grade | Missed |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in pfdf.iterrows():
        md.append(f"| {r.group} | {r.strategy} | {r.data}{'' if r.holdout_clean else ' (seen)'} | {r.oos_from} | {r.oos_trades} | "
                  f"{r.oos_exp_R} | {r.oos_exp_R_before_costs} | {r.oos_pf} | {r.oos_boot_p5} | {r.oos_exp_R_2x} | "
                  f"{r.stability_pct}% | {r.wf_exp_R} | **{r.grade}** | {r.fails or '—'} |")
    (OUT / "PASS_FAIL.md").write_text("\n".join(md) + "\n")
    print("\n".join(md)); print(f"\nvariants run: {VARIANTS['count']}")


if __name__ == "__main__":
    import sys
    main(sys.argv[1:] or None)
