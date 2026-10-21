"""EXP-001 – does a pre-entry regime filter improve the crude INTRADAY engine?  (research only; never touches the
live paper ledger – outputs go to crude/research/results/EXP-001/)

Pre-registered (frozen in crude/research/REGISTRY.md BEFORE the run):
  A  baseline       – current intraday strategy unchanged
  B  regime filter  – new entries only when the pre-entry regime is uptrend/high-vol (existing definition, no tuning)
  C  long-only      – BUY entries only (control for the long bias inside B)
Same data, fills, stops, targets, sizing, costs. Positional engine untouched.
All results on 2020-10 → 2026-10 are EXPLORATORY: this history was already examined when the subgroup was found.

  python -m crude.research.exp001
"""
import hashlib, json, subprocess, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import config as K, data as D, indicators as I, backtest as B  # noqa: E402

EXP = "EXP-001"
OUT = ROOT / "crude" / "research" / "results" / EXP
SEED = 7
FROZEN = dict(regime="uptrend/high-vol", sma_n=100, sma_min=60, atr_n=20, med_n=250, med_min=100,
              costs=(1.0, 2.0, 3.0), slip_ticks=(0, 2, 4, 6), miss_rate=0.10, miss_seeds=(1, 2, 3),
              neighbours=[(80, 250), (120, 250), (100, 200), (100, 300)], bootstrap=5000)


# ─────────────── regime ───────────────
def daily(a):
    g = a.groupby(a["time"].dt.normalize())
    dd = g.agg(high=("high", "max"), low=("low", "min"), close=("close", "last"), offset=("offset", "last"))
    dd["raw_close"] = dd["close"] - dd["offset"]
    return dd


def regime_labels(a, sma_n=100, atr_n=20, med_n=250, raw_denominator=True):
    """Label for session d uses ONLY sessions ≤ d−1 (shift by one session):
       trend  = adjusted close > SMA(sma_n) of adjusted closes   -> uptrend / downtrend
       vol    = ATR(atr_n, Wilder, adjusted daily bars) / close  > rolling median of the same over med_n sessions
       raw_denominator=True divides by the REAL close (the corrected version). The original backtest divided by the
       back-adjusted close, whose level depends on roll gaps estimated LATER – a look-ahead distortion."""
    dd = daily(a)
    sma = dd["close"].rolling(sma_n, min_periods=FROZEN["sma_min"] if sma_n == 100 else int(sma_n * 0.6)).mean()
    atr = I.atr(dd.reset_index(drop=True)[["high", "low", "close"]], atr_n).values
    den = dd["raw_close"].values if raw_denominator else dd["close"].values
    atrp = pd.Series(atr / den, index=dd.index)
    med = atrp.rolling(med_n, min_periods=FROZEN["med_min"] if med_n == 250 else int(med_n * 0.4)).median()
    tr = np.where(dd["close"] > sma, "uptrend", "downtrend")
    vo = np.where(atrp > med, "high-vol", "low-vol")
    lab = pd.Series([f"{x}/{y}" for x, y in zip(tr, vo)], index=dd.index)
    lab[sma.isna() | med.isna()] = "warm-up"
    return lab.shift(1).fillna("warm-up")


# ─────────────── statistics ───────────────
def boot(r, n=FROZEN["bootstrap"], seed=SEED):
    if len(r) == 0:
        return dict(p2_5=None, p5=None, p97_5=None)
    rng = np.random.default_rng(seed)
    m = rng.choice(r, (n, len(r))).mean(axis=1)
    return dict(p2_5=round(float(np.percentile(m, 2.5)), 3), p5=round(float(np.percentile(m, 5)), 3),
                p97_5=round(float(np.percentile(m, 97.5)), 3))


def stats(t, cnt=None):
    if t is None or not len(t):
        return dict(trades=0)
    p, r = t["pnl"].values, t["r"].values
    w, l = p[p > 0], p[p <= 0]
    eq = K.CAPITAL + np.cumsum(p)
    dd = (eq - np.maximum.accumulate(eq)).min()
    cr = np.cumsum(r)
    ddr = (cr - np.maximum.accumulate(np.r_[0, cr])[1:]).min()
    streak = mx = 0
    for x in p:
        streak = streak + 1 if x <= 0 else 0
        mx = max(mx, streak)
    out = dict(trades=int(len(t)), win_rate=round(float((p > 0).mean() * 100), 1),
               avg_win_rs=round(float(w.mean()), 0) if len(w) else 0, avg_loss_rs=round(float(l.mean()), 0) if len(l) else 0,
               avg_win_r=round(float(r[p > 0].mean()), 3) if len(w) else 0, avg_loss_r=round(float(r[p <= 0].mean()), 3) if len(l) else 0,
               expectancy_r=round(float(r.mean()), 3), expectancy_rs=round(float(p.mean()), 0),
               profit_factor=round(float(w.sum() / -l.sum()), 2) if len(l) and l.sum() < 0 else None,
               net_rs=round(float(p.sum()), 0), charges_rs=round(float(t["charges"].sum()), 0),
               charges_r_per_trade=round(float((t["charges"] / (t["risk_pts"] * t["units"])).mean()), 3),
               max_dd_rs=round(float(dd), 0), max_dd_pct=round(float(dd / K.CAPITAL * 100), 2), max_dd_r=round(float(ddr), 2),
               worst_losing_streak=int(mx), bootstrap=boot(r))
    if cnt is not None:
        out["exposure_pct_of_bars"] = cnt.get("exposure_pct")
    return out


def by(t, key):
    return {str(k): stats(g) for k, g in t.groupby(key)} if len(t) else {}


def anchored(t):
    """Parameters are frozen (nothing re-fitted), so each calendar year after the first is scored as an
    out-of-sample step of an anchored walk-forward; pooled = all steps together."""
    if not len(t):
        return {}
    y = pd.to_datetime(t["entry_time"]).dt.year
    first = y.min()
    steps = {str(k): dict(trades=int(len(g)), expectancy_r=round(float(g["r"].mean()), 3)) for k, g in t.groupby(y) if k > first}
    pooled = t[y > first]
    return dict(steps=steps, pooled_expectancy_r=round(float(pooled["r"].mean()), 3) if len(pooled) else None,
                positive_steps=f"{sum(v['expectancy_r'] > 0 for v in steps.values())}/{len(steps)}")


def rolling12(t):
    if not len(t):
        return {}
    et = pd.to_datetime(t["entry_time"])
    s, out = pd.Timestamp(et.min().year, 1, 1), {}
    while s < et.max():
        e = s + pd.DateOffset(months=12)
        g = t[(et >= s) & (et < e)]
        out[f"{s:%Y-%m}"] = dict(trades=int(len(g)), expectancy_r=round(float(g["r"].mean()), 3) if len(g) else None)
        s += pd.DateOffset(months=6)
    return out


def criteria(m1, m2, wf, independent=False, post_hoc=False):
    c = {"trades ≥ 50": m1.get("trades", 0) >= 50, "expectancy > +0.10R": m1.get("expectancy_r", -9) > 0.10,
         "bootstrap p5 > 0": (m1.get("bootstrap", {}).get("p5") or -9) > 0, "profit factor ≥ 1.20": (m1.get("profit_factor") or 0) >= 1.2,
         "positive at 2× costs": m2.get("expectancy_r", -9) > 0, "anchored walk-forward > 0": (wf.get("pooled_expectancy_r") or -9) > 0}
    all_ok = all(c.values())
    if not all_ok:
        verdict = "FAIL"
    elif post_hoc or not independent:
        verdict = "PAPER-CANDIDATE (exploratory – not independent evidence)"
    else:
        verdict = "PASS"
    return dict(checks=c, verdict=verdict)


# ─────────────── manifest ───────────────
def _git(*a):
    try:
        return subprocess.check_output(["git", *a], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def main():
    t0 = time.time()
    d, row = B.load_15m()
    rolls = B.roll_table(d)
    a = B.adjust(d, rolls)
    h1 = B.hourly(a)
    h3 = D.three_hour(h1[["time", "open", "high", "low", "close", "volume", "offset"]])
    days = a["time"].dt.normalize()
    lab_new = regime_labels(a)
    lab_old = regime_labels(a, raw_denominator=False)
    day_lab = days.map(lab_new).values

    def f_B(labels):
        dl = days.map(labels).values
        return lambda i, side: None if dl[i] == FROZEN["regime"] else f"regime {dl[i]}"
    f_C = lambda i, side: None if side == "BUY" else "SELL (long-only control)"
    variants = {"A": None, "B": f_B(lab_new), "C": f_C}

    def sim(flt, **o):
        opts = dict(o)
        if flt:
            opts["entry_filter"] = flt
        cx = opts.pop("cost_x", 1.0)
        return B.simulate("intraday", a, h1, h3, rolls, cost_x=cx, opts=opts)

    res, trades = {}, {}
    # reproduction of the original backtest (EXP-000) – must match crude/reports/backtest.json
    t_orig, c_orig = sim(None)
    ref = json.loads((ROOT / "crude" / "reports" / "backtest.json").read_text())["results"]["intraday"]["cost"]["1.0"]
    repro = dict(reference=dict(trades=ref["trades"], expectancy_r=ref["expectancy_r"], net_rs=ref["net_rs"]),
                 reproduced=dict(trades=int(len(t_orig)), expectancy_r=round(float(t_orig["r"].mean()), 3), net_rs=round(float(t_orig["pnl"].sum()), 0)))
    repro["within_tolerance"] = (repro["reproduced"]["trades"] == ref["trades"] and abs(repro["reproduced"]["expectancy_r"] - ref["expectancy_r"]) <= 0.001
                                 and abs(repro["reproduced"]["net_rs"] - ref["net_rs"]) <= 1)
    print("reproduction", repro, flush=True)
    # leakage audit: switch-day entries (roll gap known only at that day's close) and the regime denominator
    t_nsw, c_nsw = sim(None, no_switch_day=True)
    leak = dict(switch_day_entries=dict(trades_removed=int(len(t_orig) - len(t_nsw)), baseline_without=stats(t_nsw, c_nsw)),
                regime_denominator=dict(days_relabelled=int((lab_new != lab_old).sum()), days=int(len(lab_new)),
                                        uptrend_highvol_days_old=int((lab_old == FROZEN["regime"]).sum()),
                                        uptrend_highvol_days_new=int((lab_new == FROZEN["regime"]).sum())))
    t_Bold, c_Bold = sim(f_B(lab_old), no_switch_day=True)
    leak["regime_denominator"]["B_with_original_labels"] = stats(t_Bold, c_Bold)
    print("leakage", json.dumps(leak)[:300], flush=True)
    # main grid (corrected research implementation: no switch-day entries, raw-close ATR%)
    for v, flt in variants.items():
        r = dict(cost={}, slippage={}, missed_fills={})
        for cx in FROZEN["costs"]:
            t, c = sim(flt, cost_x=cx, no_switch_day=True)
            r["cost"][f"{cx:g}x"] = stats(t, c)
            if cx == 1.0:
                trades[v], r["counts"] = t, {k: v_ for k, v_ in c.items() if k != "reasons"}
                r["reasons"] = dict(sorted(c["reasons"].items(), key=lambda x: -x[1])[:15])
        for tk in FROZEN["slip_ticks"]:
            t, c = sim(flt, slip_ticks=tk, no_switch_day=True)
            r["slippage"][f"{tk} ticks"] = stats(t, c)
        ms = []
        for sd in FROZEN["miss_seeds"]:
            t, c = sim(flt, miss_rate=FROZEN["miss_rate"], seed=sd, no_switch_day=True)
            ms.append(stats(t, c))
        r["missed_fills"] = dict(rate=FROZEN["miss_rate"], runs=ms,
                                 mean_expectancy_r=round(float(np.mean([m["expectancy_r"] for m in ms if m["trades"]])), 3))
        t = trades[v]
        if len(t):
            t["regime_at_signal"] = [day_lab[i] for i in t["signal_i"]]
            t["year"] = pd.to_datetime(t["entry_time"]).dt.year
        r["by_year"], r["by_regime"], r["by_side"] = by(t, "year"), by(t, "regime_at_signal"), by(t, "side")
        r["anchored_walk_forward"], r["rolling_12m"] = anchored(t), rolling12(t)
        r["criteria"] = criteria(r["cost"]["1x"], r["cost"]["2x"], r["anchored_walk_forward"], independent=False, post_hoc=(v == "B"))
        res[v] = r
        print(v, r["cost"]["1x"].get("trades"), r["cost"]["1x"].get("expectancy_r"), r["criteria"]["verdict"], flush=True)
    # where does B's difference come from?
    tA, tB, tC = trades["A"], trades["B"], trades["C"]
    rng = np.random.default_rng(SEED)
    sub = [rng.choice(tA["r"].values, len(tB), replace=False).mean() for _ in range(5000)] if len(tB) and len(tA) >= len(tB) else []
    attrib = dict(
        B_vs_random_subsets_of_A=dict(B_mean_r=round(float(tB["r"].mean()), 3) if len(tB) else None,
                                      pct_of_random_A_subsets_below_B=round(float(np.mean(np.array(sub) < tB["r"].mean()) * 100), 1) if sub else None),
        B_by_side=by(tB, "side"),
        B_without_best_year=None, B_without_2026=None,
        A_trades_in_uptrend_highvol=stats(tA[tA["regime_at_signal"] == FROZEN["regime"]]) if len(tA) else {},
        C_trades_in_uptrend_highvol=stats(tC[tC["regime_at_signal"] == FROZEN["regime"]]) if len(tC) else {},
        charges_r_per_trade={v: res[v]["cost"]["1x"].get("charges_r_per_trade") for v in res})
    if len(tB):
        yb = pd.to_datetime(tB["entry_time"]).dt.year
        best = tB.groupby(yb)["r"].sum().idxmax()
        attrib["B_without_best_year"] = dict(best_year=int(best), **stats(tB[yb != best]))
        attrib["B_without_2026"] = stats(tB[yb != 2026])
    # neighbouring regime definitions (stability only – never used to choose)
    neigh = {}
    for sn, mn in FROZEN["neighbours"]:
        t, c = sim(f_B(regime_labels(a, sma_n=sn, med_n=mn)), no_switch_day=True)
        neigh[f"SMA{sn}/median{mn}"] = stats(t, c)
    res["B"]["neighbour_stability"] = neigh
    manifest = dict(
        experiment=EXP, run_id=f"{EXP}-{_git('rev-parse', '--short', 'HEAD')}-{sha(B.SRC / (row['symbol'] + '_FIFTEEN_MINUTE.csv'))[:8]}",
        created=pd.Timestamp.now(tz="Asia/Kolkata").isoformat(), code_revision=_git("rev-parse", "HEAD"),
        working_tree_clean=_git("status", "--porcelain", "crude") == "",
        data=dict(file=f"research/data/angel/MCX/{row['symbol']}_FIFTEEN_MINUTE.csv", sha256_16=sha(B.SRC / (row['symbol'] + '_FIFTEEN_MINUTE.csv')),
                  first=str(d["time"].min()), last=str(d["time"].max()), bars=int(len(d)), source="Angel One getCandleData (vendor-stitched front month)",
                  holes=["09-Apr-2021 → 16-Apr-2021", "17-Dec-2021 → 02-May-2022"], oi="none (Angel AB1012) – every variant ran without an OI filter"),
        config=dict(version=K.VERSION, INTRA=K.INTRA, risk_pct=K.RISK_PCT, capital=K.CAPITAL, min_rr=K.MIN_RR,
                    roll_trading_days=K.ROLL_TRADING_DAYS, cooldown=K.COOLDOWN_BARS, daily_loss_pct=K.DAILY_LOSS_PCT),
        costs=dict(brokerage_per_order=K.BROKERAGE_PER_ORDER, ctt_sell=K.CTT_SELL, exch_txn=K.EXCH_TXN, sebi=K.SEBI_FEE,
                   stamp_buy=K.STAMP_BUY, gst=K.GST, slippage_ticks=K.SLIPPAGE_TICKS, tick=1.0, rs_per_point=K.RS_PER_POINT[K.TRADE_NAME]),
        frozen=FROZEN, deterministic_seed=SEED, runtime_sec=round(time.time() - t0))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    (OUT / "results.json").write_text(json.dumps(dict(reproduction=repro, leakage_audit=leak, variants=res, attribution=attrib),
                                                 indent=1, default=str))
    for v, t in trades.items():
        t.to_csv(OUT / f"trades_{v}.csv", index=False)
    print("done", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
