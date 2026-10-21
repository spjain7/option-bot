"""Full-universe research backtest (research / paper mode only - touches nothing live).

  python -m research.adapters.nse_bhavcopy 2011-01-01     # REAL NSE index-futures data (one-time, ~25 min)
  python -m research.adapters.yahoo_proxy                 # PROXY data
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
GROUPS = {
    "INDEX_DAILY_REAL": dict(names=INDEX, grade="REAL", clean=True,
                             periods=("2011-01-01", "2017-01-01", "2021-01-01"), wf_from=2017),
    "MCX_DAILY_PROXY": dict(names=COMMOD, grade="PROXY", clean=False,
                            periods=("2005-01-01", "2013-01-01", "2018-01-01"), wf_from=2013),
}
DAILY_STRATS = {"INDEX_DAILY_REAL": ["B", "C", "D", "E", "F", "G", "H1", "H2", "H3", "H4", "I"],
                "MCX_DAILY_PROXY": ["B", "C", "D", "E", "G", "H1", "H2", "H4"]}
GRID_C = [dict(entry=a, exit=b, stop=s) for a, b, s in itertools.product((40, 55, 70), (15, 20, 25), (1.5, 2.0, 2.5))]
GRID_B = [dict(entry=a, exit=b) for a, b in itertools.product((15, 20, 25), (7, 10, 13))]
GRID_A = [dict(brk=a, min_adx=b) for a, b in itertools.product((3, 5, 8), (15, 20, 25))]
VARIANTS = {"count": 0}


def w(df, *parts):
    f = OUT.joinpath(*parts); f.parent.mkdir(parents=True, exist_ok=True); df.to_csv(f, index=False); return f


# ───────────────────────── data ─────────────────────────
def load_data():
    daily, cov = {}, []
    t0 = time.time()
    nse = CO.load_nse(INDEX, roll_days=3)
    for n in INDEX:
        d = nse.get(n)
        if d is None or d.empty:
            cov.append(dict(instrument=n, dataset="daily", source="NSE bhavcopy", grade="REAL", bars=0,
                            note="no futures rows in downloaded bhavcopies")); continue
        daily[n] = ED.add_indicators(d)
        cov.append(dict(instrument=n, dataset="daily", source="NSE F&O bhavcopy (contract level)", grade="REAL",
                        start=d.time.min().date(), end=d.time.max().date(), bars=len(d), rolls=int(d.roll.sum()),
                        untraded_days=int((~d.traded).sum()), volume=True, oi=True))
    for n in COMMOD:
        d = CO.load_proxy(n, "1d")
        r = REGISTRY[n]
        if d is None:
            cov.append(dict(instrument=n, dataset="daily", source="none", grade="MISSING", bars=0,
                            note="no free daily history found (Yahoo has no zinc future); MCX bhavcopy blocked here")); continue
        daily[n] = ED.add_indicators(d)
        cov.append(dict(instrument=n, dataset="daily", source=f"Yahoo {r['proxy']} (international, unadjusted)", grade="PROXY",
                        start=d.time.min().date(), end=d.time.max().date(), bars=len(d), rolls="unknown",
                        volume="exchange volume of proxy", oi=False))
    hourly = {}
    for n, r in REGISTRY.items():
        d = CO.load_proxy(n, "1h")
        if d is None:
            cov.append(dict(instrument=n, dataset="hourly", source="none", grade="MISSING", bars=0,
                            note="no free hourly history")); continue
        hourly[n] = d
        src = r.get("hourly_proxy") or r.get("proxy")
        cov.append(dict(instrument=n, dataset="hourly", source=f"Yahoo {src} ({'cash index' if r['kind'] == 'index' else 'international future'})",
                        grade="PROXY", start=d.time.min(), end=d.time.max(), bars=len(d),
                        volume=bool((d.volume > 0).mean() > 0.5), oi=False))
    ang = ROOT / "data" / "angel" / "manifest.csv"
    if ang.exists():
        m = pd.read_csv(ang)
        for (ex, n), g in m.groupby(["exch", "name"]):
            for iv, gg in g.groupby("interval"):
                cov.append(dict(instrument=n, dataset=f"angel_{iv}", source="Angel One SmartAPI (listed contracts only)",
                                grade="REAL", start=gg["first"].min(), end=gg["last"].max(), bars=int(gg.bars.sum()),
                                contracts=len(gg), note="expired contracts not served; MCX OI history not served"))
    else:
        cov.append(dict(instrument="MCX (all)", dataset="angel", source="Angel One SmartAPI", grade="MISSING",
                        note="run the 'Research data' workflow, then fetch branch research-data"))
    print(f"data loaded in {time.time() - t0:.0f}s")
    return daily, hourly, pd.DataFrame(cov)


# ───────────────────────── helpers ─────────────────────────
def run_daily_group(daily, names, strat, over=None, cost_x=1.0):
    VARIANTS["count"] += 1
    p = {**ED.STRATS[strat], **(over or {})}
    ts = [ED.run(n, daily[n], p, cost_x) for n in names if n in daily]
    ts = [t for t in ts if not t.empty]
    return pd.concat(ts, ignore_index=True) if ts else pd.DataFrame()


def split(t, periods):
    tr, va, oos = periods
    return MT.period(t, tr, pd.Timestamp(va) - pd.Timedelta(days=1)), \
        MT.period(t, va, pd.Timestamp(oos) - pd.Timedelta(days=1)), MT.period(t, oos)


def walk_forward(runs, start_year, min_train=20):
    """runs: list of (params, trades). Anchored yearly: pick best train expectancy, apply to next year."""
    if not runs:
        return pd.DataFrame(), []
    last = max(pd.to_datetime(t["entry_time"]).max().year for _, t in runs if not t.empty)
    picks, out = [], []
    for y in range(start_year, last + 1):
        best, bv = None, -9
        for p, t in runs:
            tr = t[pd.to_datetime(t["entry_time"]) < pd.Timestamp(f"{y}-01-01")] if not t.empty else t
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
    for dim in ("side", "year", "month", "adx_bucket", "vol_bucket", "trend"):
        if dim not in t:
            continue
        for v, g in t.groupby(dim):
            rows.append(dict(dimension=dim, value=v, trades=len(g), expectancy_R=round(g.net_R.mean(), 3),
                             total_R=round(g.net_R.sum(), 1), win_pct=round((g.net_R > 0).mean() * 100, 1),
                             rs_1lot=round(g.pnl_rs_1lot.sum())))
    w(pd.DataFrame(rows), "breakdowns", f"{key}.csv")


def equity_png(curves, title, fname):
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    for lab, (x, y) in curves.items():
        ax.plot(pd.to_datetime(x), y, label=lab, lw=1.2)
    ax.axhline(0, color="#888", lw=0.6); ax.set_title(title); ax.set_ylabel("Cumulative net R"); ax.legend(fontsize=7, ncol=3)
    fig.tight_layout(); (OUT / "equity").mkdir(parents=True, exist_ok=True); fig.savefig(OUT / "equity" / fname, dpi=110); plt.close(fig)


def grade(row, grade_data, clean):
    core = [row["oos_exp_R"] > 0.10, row["oos_boot_p5"] > 0, row["oos_trades"] >= 50, row["oos_pf"] >= 1.20,
            row["oos_exp_R_2x"] > 0]
    sec = [row["val_exp_R"] > 0 and row["oos_years_pos"] >= 60, row["stability_pct"] >= 70, row["wf_exp_R"] > 0,
           row["oos_max_dd_R"] >= -25]
    names_c = ["exp>0.10R", "boot p5>0", "≥50 trades", "PF≥1.2", "2x costs>0"]
    names_s = ["validation+years", "param stability", "walk-forward", "DD≤25R"]
    fails = [n for n, ok in zip(names_c, core) if not ok] + [n for n, ok in zip(names_s, sec) if not ok]
    if not all(core):
        return "FAIL", fails
    if all(sec) and grade_data == "REAL" and clean:
        return "PASS", fails
    if sum(not s for s in sec) <= 1:
        return "PAPER-CANDIDATE", fails + ([] if grade_data == "REAL" and clean else ["proxy or already-seen data"])
    return "FAIL", fails


# ───────────────────────── main ─────────────────────────
def main():
    OUT.mkdir(exist_ok=True)
    daily, hourly, cov = load_data()
    w(cov, "data_coverage.csv")
    master, pf_rows, pf_summ, curves_all = [], [], [], {}

    def master_rows(group, strat, label, t, periods, cost_tag="1x"):
        parts = dict(zip(("train", "validation", "oos"), split(t, periods))) if periods else {"all": t}
        parts["full"] = t
        for inst in ["ALL"] + sorted(t["instrument"].unique() if not t.empty else []):
            for per, tt in parts.items():
                x = tt if inst == "ALL" else tt[tt.instrument == inst]
                st = MT.stats(x, capital=CAPITAL)
                master.append(dict(group=group, strategy=strat, variant=label, instrument=inst, period=per, costs=cost_tag, **st))

    # ---------- daily groups ----------
    for g, G in GROUPS.items():
        names = [n for n in G["names"] if n in daily]
        for strat in DAILY_STRATS[g]:
            t = run_daily_group(daily, names, strat)
            if t.empty:
                continue
            for inst, ti in t.groupby("instrument"):
                w(ti, "trades", g, strat, f"{inst}.csv")
            master_rows(g, strat, "base", t, G["periods"])
            tr, va, oos = split(t, G["periods"])
            stress = {}
            for cx in (0, 2.0, 3.0):
                ts = run_daily_group(daily, names, strat, cost_x=cx)
                _, _, o = split(ts, G["periods"])
                stress[cx] = MT.stats(o).get("expectancy_R", np.nan)
                master_rows(g, strat, "base", ts, G["periods"], cost_tag=f"{cx:g}x")
            grid = GRID_B if strat == "B" else GRID_C
            runs = [(p, run_daily_group(daily, names, strat, p)) for p in grid]
            oos_exps = [MT.stats(split(tt, G["periods"])[2]).get("expectancy_R", np.nan) for _, tt in runs]
            stab = np.nanmean([e > 0 for e in oos_exps]) * 100
            w(pd.DataFrame([dict(**p, oos_expectancy_R=e) for (p, _), e in zip(runs, oos_exps)]), "sensitivity", g, f"{strat}.csv")
            wf, picks = walk_forward(runs, G["wf_from"])
            w(pd.DataFrame(picks), "walkforward", g, f"{strat}.csv")
            wfo = MT.period(wf, G["periods"][2]) if not wf.empty else wf
            breakdowns(t, f"{g}_{strat}")
            p_all, s_all = PF.simulate(t, CAPITAL, RISK, MAXPOS, MAXRISK)
            p_oos, s_oos = PF.simulate(oos, CAPITAL, RISK, MAXPOS, MAXRISK)
            if not p_all.empty:
                w(p_all, "portfolio", g, f"{strat}_trades.csv")
                eq = p_all[["exit_time", "equity_rs", "pnl_rs"]].copy(); eq["equity_R"] = p_all["net_R"].cumsum().values
                w(eq, "equity", "daily", g, f"{strat}.csv")
                curves_all.setdefault(g, {})[strat] = (eq["exit_time"], eq["equity_R"])
            pf_summ.append(dict(group=g, strategy=strat, period="full", **s_all)); pf_summ.append(dict(group=g, strategy=strat, period="oos", **s_oos))
            so, sv = MT.stats(oos), MT.stats(va)
            row = dict(group=g, strategy=strat, data=G["grade"], holdout_clean=G["clean"],
                       oos_trades=so.get("trades", 0), oos_exp_R=so.get("expectancy_R", np.nan),
                       oos_gross_exp_R=so.get("gross_expectancy_R", np.nan), oos_pf=so.get("pf", np.nan),
                       oos_boot_p5=so.get("boot_p5_R", np.nan), oos_max_dd_R=so.get("max_dd_R", np.nan),
                       oos_years_pos=so.get("years_pos_pct", np.nan), val_exp_R=sv.get("expectancy_R", np.nan),
                       oos_exp_R_2x=stress[2.0], oos_exp_R_3x=stress[3.0], stability_pct=round(stab),
                       wf_exp_R=round(wfo["net_R"].mean(), 3) if not wfo.empty else np.nan,
                       oos_long_exp_R=so.get("long_exp_R"), oos_short_exp_R=so.get("short_exp_R"),
                       oos_portfolio_rs=s_oos.get("net_rs"), oos_portfolio_dd_pct=s_oos.get("max_dd_pct"))
            row["grade"], row["fails"] = grade(row, G["grade"], G["clean"])
            row["fails"] = "; ".join(row["fails"])
            pf_rows.append(row)
            print(g, strat, row["grade"], "OOS exp", row["oos_exp_R"], "trades", row["oos_trades"], flush=True)

    # ---------- hourly A (PROXY) ----------
    hgroups = {"MCX_HOURLY_PROXY": [n for n in COMMOD if n in hourly], "INDEX_HOURLY_PROXY": [n for n in INDEX if n in hourly]}
    comparable = []
    for g, names in hgroups.items():
        if not names:
            continue
        def runA(over=None, cx=1.0):
            VARIANTS["count"] += 1
            ts = [EH.run(n, hourly[n], over, cx) for n in names]
            ts = [t for t in ts if not t.empty]
            return pd.concat(ts, ignore_index=True) if ts else pd.DataFrame()
        t = runA()
        lo, hi = min(hourly[n].time.min() for n in names), max(hourly[n].time.max() for n in names)
        span = hi - lo
        periods = (str(lo.date()), str((lo + span * 0.5).date()), str((lo + span * 0.75).date()))
        for inst, ti in t.groupby("instrument"):
            w(ti, "trades", g, "A", f"{inst}.csv")
        master_rows(g, "A", "base", t, periods)
        _, va, oos = split(t, periods)
        stress = {cx: MT.stats(split(runA(None, cx), periods)[2]).get("expectancy_R", np.nan) for cx in (0, 2.0, 3.0)}
        runs = [(p, runA(p)) for p in GRID_A]
        oe = [MT.stats(split(tt, periods)[2]).get("expectancy_R", np.nan) for _, tt in runs]
        w(pd.DataFrame([dict(**p, oos_expectancy_R=e) for (p, _), e in zip(runs, oe)]), "sensitivity", g, "A.csv")
        breakdowns(t, f"{g}_A")
        eq = t.sort_values("exit_time")[["exit_time", "net_R", "pnl_rs_1lot"]].copy(); eq["equity_R"] = eq["net_R"].cumsum()
        w(eq, "equity", "hourly", f"{g}_A.csv"); curves_all.setdefault(g, {})["A"] = (eq["exit_time"], eq["equity_R"])
        p_oos, s_oos = PF.simulate(oos, CAPITAL, RISK, MAXPOS, MAXRISK)
        pf_summ.append(dict(group=g, strategy="A", period="oos", **s_oos))
        so, sv = MT.stats(oos), MT.stats(va)
        row = dict(group=g, strategy="A", data="PROXY", holdout_clean=g.startswith("INDEX"),
                   oos_trades=so.get("trades", 0), oos_exp_R=so.get("expectancy_R", np.nan),
                   oos_gross_exp_R=so.get("gross_expectancy_R", np.nan), oos_pf=so.get("pf", np.nan),
                   oos_boot_p5=so.get("boot_p5_R", np.nan), oos_max_dd_R=so.get("max_dd_R", np.nan),
                   oos_years_pos=so.get("years_pos_pct", np.nan), val_exp_R=sv.get("expectancy_R", np.nan),
                   oos_exp_R_2x=stress[2.0], oos_exp_R_3x=stress[3.0], stability_pct=round(np.nanmean([e > 0 for e in oe]) * 100),
                   wf_exp_R=np.nan, oos_long_exp_R=so.get("long_exp_R"), oos_short_exp_R=so.get("short_exp_R"),
                   oos_portfolio_rs=s_oos.get("net_rs"), oos_portfolio_dd_pct=s_oos.get("max_dd_pct"))
        row["grade"], fails = grade({**row, "wf_exp_R": 1}, "PROXY", False)
        row["fails"] = "; ".join(fails + ["walk-forward n/a (2-year window)"])
        pf_rows.append(row)
        print(g, "A", row["grade"], "OOS exp", row["oos_exp_R"], flush=True)
        # comparable period: hourly A vs daily B/C on the same window and instruments
        dg = "INDEX_DAILY_REAL" if g.startswith("INDEX") else "MCX_DAILY_PROXY"
        for strat in ("B", "C"):
            td = run_daily_group(daily, [n for n in names if n in daily], strat)
            td = MT.period(td, lo)
            comparable.append(dict(window=f"{lo.date()} → {hi.date()}", instruments=",".join(names), strategy=f"{strat} (daily, {dg.split('_')[-1]})",
                                   **{k: v for k, v in MT.stats(td).items() if k in ("trades", "expectancy_R", "gross_expectancy_R", "pf", "total_R", "max_dd_R", "win_pct", "avg_days")}))
        comparable.append(dict(window=f"{lo.date()} → {hi.date()}", instruments=",".join(names), strategy="A (hourly, PROXY)",
                               **{k: v for k, v in MT.stats(t).items() if k in ("trades", "expectancy_R", "gross_expectancy_R", "pf", "total_R", "max_dd_R", "win_pct", "avg_days")}))

    # ---------- outputs ----------
    w(pd.DataFrame(master), "master_comparison.csv")
    pfdf = pd.DataFrame(pf_rows); w(pfdf, "pass_fail.csv")
    w(pd.DataFrame(pf_summ), "portfolio_summary.csv")
    w(pd.DataFrame(comparable), "daily_vs_hourly_comparable.csv")
    for g, c in curves_all.items():
        equity_png(c, f"{g} – cumulative net R (after costs)", f"{g}.png")
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT.parent, text=True).strip()
    except Exception:
        commit = "?"
    cfg = dict(run_at=pd.Timestamp.now().isoformat(), git_commit=commit, capital_rs=CAPITAL, risk_per_trade=RISK,
               max_positions=MAXPOS, max_open_risk=MAXRISK, groups=GROUPS, daily_strategies={k: ED.STRATS[k] for k in ED.STRATS},
               daily_base=ED.BASE, hourly_base=EH.BASE, hourly_sessions=EH.SESS, costs=COSTS,
               slippage_pts={k: v["slip_pts"] for k, v in REGISTRY.items()}, roll_days={k: v["roll_days"] for k, v in REGISTRY.items()},
               variants_run_this_project=VARIANTS["count"], variants_inspected_before_plan=30,
               bootstrap=dict(resamples=5000, seed=12345))
    (OUT / "run_config.json").write_text(json.dumps(cfg, indent=1, default=str))
    md = ["| Group | Strategy | Data | OOS trades | OOS exp (R) | PF | Boot p5 | 2× cost exp | Stability | WF exp | Grade | Why |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in pfdf.iterrows():
        md.append(f"| {r.group} | {r.strategy} | {r.data}{'' if r.holdout_clean else ' (seen)'} | {r.oos_trades} | {r.oos_exp_R} | {r.oos_pf} | "
                  f"{r.oos_boot_p5} | {r.oos_exp_R_2x} | {r.stability_pct}% | {r.wf_exp_R} | **{r.grade}** | {r.fails or 'all criteria met'} |")
    (OUT / "PASS_FAIL.md").write_text("\n".join(md) + "\n")
    print("\n".join(md)); print(f"\nvariants run: {VARIANTS['count']}")


if __name__ == "__main__":
    main()
