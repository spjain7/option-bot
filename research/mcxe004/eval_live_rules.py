"""MCXE-004 E1 – the LIVE / SHADOW rules that have research code, re-simulated ONLY inside the approved 1-year windows
(PROTOCOL.md). Nothing older than the window start is read; indicators warm up inside the window (the research simulator
starts signals at bar 210 of the clipped frame). Results are written to the execution register, one record per rule x
instrument and one per rule (pooled), with DEV / VALID / OOS separately.

Rules (copied unchanged from research/program/portfolio.py LIVE = the live rulebook + breakout rules with research parity):
  MCX:    RB 4h EMA13/48 BUY, 4h MACD-zero BUY, 2h momentum BUY, 2h EMA9/21 BUY, 1d retest BUY, 1h MACD BUY,
          BO 3h N10 BUY, FH 4h N10 BUY, BO 1d N20+ADX25 BUY
  STOCKS: RB 3h MACD-zero SELL, 3h EMA9/21 SELL, 1d RSI>80 BUY, FH 3h N5 vol2 SELL
  plus the MCX day-trend continuation SHADOW rule (alerts/mcx_dtc.py; research mcx_dtc.trades, GOLD + SILVER, 13:00 /
  17:00, k 0.3, stop 0.5 daily ATR).
Window per market: MCX (Angel front-month: 1h-based frames end 2026-10-21 – PROTOCOL deviation recorded, see notes);
STOCKS = NSE_FUT_INTRADAY (Angel 1-hour, today's list, 2025-10-23 -> 2026-10-22).
Selection overlap: every rule was chosen on 2022-26 data that INCLUDES this window -> the best possible status is
PAPER_ONLY (register.classify).
python research/mcxe004/eval_live_rules.py"""
import json
import sys
import time
import traceback
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe004 import register as RG, window as W  # noqa: E402

OUT = ROOT / "research/mcxe004/results"
SCRIPT = "MCXE004-E1"
MK_WIN = {"MCX": "MCX", "STOCKS": "NSE_FUT_INTRADAY"}
HORIZON = {"1h": "positional", "2h": "positional", "3h": "positional", "4h": "positional", "1d": "positional"}


def _clip(df, wkey):
    if df is None:
        return None
    w = W.get(wkey)
    col = "time" if "time" in df.columns else None
    if col is None:
        idx = pd.to_datetime(df.index)
        return df[(idx >= w["start"]) & (idx <= w["reference"] + pd.Timedelta(days=1))]
    t = pd.to_datetime(df[col])
    keep = (t >= w["start"]) & (t < w["reference"] + pd.Timedelta(days=1))
    return df[keep.values].reset_index(drop=True), keep.values


def one(job):
    from research.program import harness as H, search_all as SA, search_v2 as SV, portfolio as PF
    rows, sigs, errs = [], [], []
    try:
        frames = SV.frames_for(job)
    except Exception as e:                                       # noqa: BLE001
        return rows, sigs, [f"{job[1]}: frames_for {type(e).__name__}: {e}"]
    for mk, tf, f0, cost, fd in frames:
        rules = [r for r in PF.LIVE if r[1] == mk and r[2] == tf]
        if not rules:
            continue
        try:
            wk = MK_WIN[mk]
            f0c, keep = _clip(f0, wk)
            costc = np.asarray(cost, float)[keep] if len(np.asarray(cost)) == len(f0) else np.asarray(cost, float)[:len(f0c)]
            fdc = None
            if fd is not None:
                x = _clip(fd, wk)
                fdc = x[0] if isinstance(x, tuple) else x
            if len(f0c) < 260:
                for rid, *_ in rules:
                    sigs.append(dict(rule=rid, inst=job[1], tf=tf, bars=len(f0c), signals=0, note="fewer than 260 bars in the window"))
                continue
            f = H.features(f0c)
            f["switch"] = f0c["switch"].values if "switch" in f0c else np.zeros(len(f0c), bool)
            dtr = SA.daily_trend(fdc) if fdc is not None and len(fdc) else pd.Series(dtype=float)
            sets = {(a, b, c): (x, y) for a, b, c, x, y in SV.signal_sets(f, dtr, tf)}
            sets.update({(a, b, c): (x, y) for a, b, c, x, y in SA.signal_sets(f, dtr)})
            t = pd.to_datetime(f["time"]).values
            for rid, _, _, fam, par, flt, side, k, r in rules:
                b, s = sets[(fam, par, flt)]
                sig = np.where(np.nan_to_num(np.asarray(b if side > 0 else s, float)) > 0, side, 0)
                n_sig = int((sig[210:] != 0).sum())
                res = H.simulate(f, sig, side, k, r, SV.MAXH[tf], 0, costc, start=210)
                rej = {}
                for x in res:
                    if x["status"] == "trade":
                        j = min(x["i"] + x["bars"], len(t) - 1)
                        rows.append(dict(rule=rid, mkt=mk, tf=tf, inst=job[1], side=side, date=t[x["i"]], t_out=t[j],
                                         r1=x["r1"], r2=x["r2"], cost_r=x.get("cost_r"), exit=x["exit"]))
                    else:
                        rej[x["why"]] = rej.get(x["why"], 0) + 1
                n_tr = sum(1 for x in res if x["status"] == "trade")
                rej["skipped: position already open / switch day / warm-up edge"] = n_sig - len(res)
                sigs.append(dict(rule=rid, inst=job[1], tf=tf, bars=len(f0c), first=str(pd.Timestamp(t[0]).date()),
                                 last=str(pd.Timestamp(t[-1]).date()), signals=n_sig, trades=n_tr,
                                 rejected=sum(v for v in rej.values()), reasons=rej))
        except Exception as e:                                   # noqa: BLE001
            errs.append(f"{job[1]} {tf}: {type(e).__name__}: {e} | {traceback.format_exc(limit=2)[-300:]}")
    return rows, sigs, errs


def dtc_trades():
    """MCX day-trend continuation (shadow rule) inside the MCX window."""
    from research.program import mcx_disc as MD, mcx_dtc as DT, liqtl_mcx5 as LM
    out, info = [], {}
    orig = LM.load
    w = W.get("MCX")
    try:
        def clipped(name, iv):
            d = orig(name, iv)
            return d[(d.time >= w["start"]) & (d.time < w["reference"] + pd.Timedelta(days=1))].reset_index(drop=True)
        LM.load = clipped
        for nm in ("GOLD", "SILVER"):
            P = MD.prep(nm)
            X = DT.trades(nm, P, (13 * 60, 17 * 60), 0.3, 0.5)
            days = sorted(P[0].day.unique())
            warm = days[min(15, len(days) - 1)]                  # daily ATR(14) + 60m EMA50 warm-up inside the window
            X = X[X.day >= warm]
            info[nm] = dict(sessions=len(days), first=str(days[0].date()), last=str(days[-1].date()), warmup_until=str(warm.date()))
            out.append(X.assign(inst=nm))
    finally:
        LM.load = orig
    T = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    if len(T):
        T = T.rename(columns={"day": "date", "net": "r1", "stress": "r2"})
        T["rule"] = "SHADOW_MCX_DTC_GOLD_SILVER"; T["mkt"] = "MCX"; T["tf"] = "15m checkpoint"
    return T, info


def evaluate(T, rule, mkt, tf, insts, wkey, horizon, sig_info, overlap=True, extra_notes=""):
    """one register record for `rule` pooled over `insts` (T = trades of this rule)."""
    w = W.get(wkey)
    firsts = [s["first"] for s in sig_info if s.get("first")]; lasts = [s["last"] for s in sig_info if s.get("last")]
    meta = dict(script_id=SCRIPT, strategy_name=rule, market=mkt, instrument=",".join(sorted(insts)) if insts else None,
                timeframe=tf, data_start_date=min(firsts) if firsts else str(w["start"].date()),
                data_end_date=max(lasts) if lasts else str(w["reference"].date()))
    with RG.Execution(**meta) as ex:
        ex.stage("metrics")
        if len(T):
            T = T.copy(); T["period"] = W.period(T.date, wkey)
        per = {}
        for P in ("DEV", "VALID", "OOS"):
            x = T[T.period == P] if len(T) else T
            per[P] = dict(r1=RG.metrics(x, "r1"), r2=RG.metrics(x, "r2"))
        status, why = RG.classify(per["OOS"]["r1"], per["OOS"]["r2"], horizon, overlap, controls_run=False)
        n_sig = sum(s.get("signals", 0) for s in sig_info)
        rej = {}
        for s in sig_info:
            for k, v in (s.get("reasons") or {}).items():
                rej[k] = rej.get(k, 0) + v
        n_tr = int(len(T))
        allm = RG.metrics(T, "r1") if len(T) else RG.metrics(pd.DataFrame(columns=["r1", "date"]))
        o = per["OOS"]["r1"]
        ex.finish("INSUFFICIENT_DATA" if status == "INSUFFICIENT_DATA" else "COMPLETED",
                  total_signals=n_sig, eligible_signals=n_sig - rej.get("skipped: position already open / switch day / warm-up edge", 0),
                  executed_backtest_trades=n_tr, rejected_signals=int(sum(rej.values())), rejection_reasons=rej,
                  win_rate=o["win_rate"], net_expectancy_R=o["expectancy_R"], profit_factor=o["profit_factor"],
                  net_pnl={"unit": "R (rupee P&L not modelled: lot sizing is not part of the research rules)",
                           "OOS_net_R_1x": o["net_R"], "all_window_net_R_1x": allm["net_R"]},
                  max_drawdown={"OOS_R": o["max_drawdown_R"], "all_window_R": allm["max_drawdown_R"]},
                  costs={"model": "realistic 1x (r1) and 2x stress (r2), research cost model of the rule",
                         "median_cost_R": round(float(np.nanmedian(T.cost_r)), 4) if len(T) and "cost_r" in T and T.cost_r.notna().any() else None},
                  sample_dates={P: per[P]["r1"]["unique_dates"] for P in per},
                  confidence_interval={"OOS_1x_ci95_conservative": o["ci95"], "method": "day-block bootstrap + cluster t (widest)"},
                  validation_status=status, conclusion=why + (f" | {extra_notes}" if extra_notes else ""),
                  artifact_paths=[str((OUT / "e1_trades.csv.gz").relative_to(ROOT)), str((OUT / "e1_signals.csv").relative_to(ROOT))])
        ex.rec["periods"] = per                                 # full DEV / VALID / OOS detail (extra, not a required field)
        ex.rec["oos"] = per["OOS"]["r1"]
        ex.rec["horizon"] = horizon
        ex.rec["selection_overlaps_window"] = overlap
    return ex.rec


def main():
    from research.program import emax as EX
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    J = [j for j in EX.jobs() if (j[0] == "mi" and j[2] == "MCX") or j[0] == "stk"]
    rows, sigs, errs = [], [], []
    with Pool(2) as p:
        for r, s, e in p.imap_unordered(one, J, chunksize=2):
            rows += r; sigs += s; errs += e
    T = pd.DataFrame(rows)
    S = pd.DataFrame(sigs)
    if "reasons" in S:
        S["reasons"] = S.reasons.map(lambda d: json.dumps(d) if isinstance(d, dict) else None)
    try:
        D, dinfo = dtc_trades()
    except Exception as e:                                        # noqa: BLE001
        D, dinfo = pd.DataFrame(), {}
        errs.append(f"DTC: {type(e).__name__}: {e}")
    if len(D):
        T = pd.concat([T, D[["rule", "mkt", "tf", "inst", "side", "date", "r1", "r2"]]], ignore_index=True)
    T.to_csv(OUT / "e1_trades.csv.gz", index=False)
    S.to_csv(OUT / "e1_signals.csv", index=False)
    print(f"{len(J)} jobs · trades {len(T)} · errors {len(errs)} · {time.time() - t0:.0f}s", flush=True)
    from research.program import portfolio as PF
    recs = []
    for rid, mk, tf, *_ in PF.LIVE:
        x = T[T.rule == rid] if len(T) else T
        si = [s for s in sigs if s["rule"] == rid]
        wk = MK_WIN[mk]
        note = "MCX frames are built from Angel 1-hour files that end 2026-10-21 (2 weeks short of the MCX reference 2026-11-03)" if mk == "MCX" else \
            "stock universe = today's F&O list (survivorship)"
        recs.append(evaluate(x, rid, "MCX" if mk == "MCX" else "NSE_FUT", tf, set(x.inst) if len(x) else set(), wk,
                             HORIZON[tf], si, True, note))
    if len(D):
        x = T[T.rule == "SHADOW_MCX_DTC_GOLD_SILVER"]
        recs.append(evaluate(x, "SHADOW_MCX_DTC_GOLD_SILVER", "MCX", "15m checkpoints 13:00/17:00", {"GOLD", "SILVER"}, "MCX",
                             "intraday", [dict(signals=int(len(x)), reasons={})], True,
                             f"shadow rule (never sent); window info {json.dumps(dinfo)}; signal = trade (no entry filters in this rule)"))
    for e in errs:
        with RG.Execution(script_id=SCRIPT, strategy_name="job error") as ex:
            raise RuntimeError(e)
    (OUT / "e1_records.json").write_text(json.dumps([RG._clean(r) for r in recs], indent=1, default=str))
    for r in recs:
        o = r["oos"]
        print(f"{r['strategy_name']:28s} {r['validation_status']:18s} OOS n {o['trades']:4d} dates {o['unique_dates']:3d} "
              f"win {o['win_rate']} exp {o['expectancy_R']} PF {o['profit_factor']} CI {o['ci95']} | {r['conclusion'][:80]}")
    for e in errs:
        print("ERROR", e)


if __name__ == "__main__":
    main()
