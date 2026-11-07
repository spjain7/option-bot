"""MCXE-003 stage 2 for the daily stage-1 survivors – CORRECTED version (Addendum D, 7-Nov-2026).
Same pre-registered execution menu and selection rule as stage2_daily.py (v1, kept unchanged for the audit trail);
corrections:
  1. CI: day-block bootstrap (bootstrap.block_ci: trading-date clusters, circular moving blocks) instead of the IID
     trade bootstrap v1 used; n, n_dates, n_eff, t-interval cross-check and block-length sensitivity reported.
  2. Controls: ONE fixed set of control dates per survivor (seed 20261107), reused for every execution and both cost
     levels (v1 re-drew controls inside every loop, so 1x vs 2x control results were different samples); drawn WITHOUT
     replacement from eligible days of the same period, excluding the survivor's own signal days; controls whose trade is
     skipped (overlap / roll) are counted.
  3. Costs for MCX: computed at the RAW contract price and scaled by the back-adjustment ratio (v1 computed them at the
     back-adjusted price, which mis-scales the fixed tick slippage by up to 1/1.78 for COPPER; NSE futures costs are
     proportional, unaffected).
  4. Per-trade files (events and controls) for the frozen execution; skipped / overlapping events counted.
python research/mcxe003/stage2_daily_v2.py"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.mcxe003 import daily as D, execution as EX, cost_model as CM, bootstrap as BT  # noqa: E402
from research.mcxe003.stage2_daily import SURV, EXECS, frames_for  # noqa: E402

OUT = ROOT / "research/mcxe003/results"


def raw_ratio(market, inst, f):
    if market != "MCX":
        return np.ones(len(f))
    from research.program import liqtl_mcx5 as LM
    raw = LM.load(inst, "ONE_DAY").set_index("time").close
    return f.close.values / raw.reindex(f.time.values).values


def main(seed=20261107):
    allout = {}
    for market, inst, name, side, sw in SURV:
        rng = np.random.default_rng(seed)
        d, elig, bad = frames_for(market, inst)
        f = D.finish(d.copy()); f.attrs.update(market=market, name=inst)
        E = D.events(f); E["i"] = E.i.astype(np.int64)
        E0 = E[(E.name == name) & (E.side == side) & (E.sw == sw)]
        n_raw = len(E0)
        E = E0[elig[E0.i.values]]
        n_elig = len(E)
        E = E.drop_duplicates("i").sort_values("i")
        o, h, l, c, a = (f[x].values.astype(np.float64) for x in ("open", "high", "low", "close", "atr"))
        t = f.time.values
        n = len(c); roll = np.where(bad)[0]
        ratio = raw_ratio(market, inst, f)

        def iend(i):
            nxt = roll[roll > i]
            return min(i + 12, (nxt[0] - 1) if len(nxt) else n - 1)

        def cpts(idx):
            if market == "MCX":
                return np.array([CM.cost_points("MCX", inst, c[k] / ratio[k]) * ratio[k] for k in idx])
            return np.asarray(CM.cost_points(market, inst, c[idx]), float)
        I_ = E.i.values.astype(np.int64); S = np.full(len(I_), side, np.int64); A = a[I_]
        IE = np.array([iend(i) for i in I_], np.int64)
        cost = cpts(I_); cost_v1 = (np.array([CM.cost_points("MCX", inst, p) for p in c[I_]]) if market == "MCX" else cost)
        inv = E.inv.values.astype(float); trig = E.level.values.astype(float)
        P_ = lambda ix: np.where(t[ix] < np.datetime64(D.V0), "DEV", np.where(t[ix] < np.datetime64(D.O0), "VALID", "OOS"))  # noqa: E731
        per = P_(I_); perf = P_(np.arange(n))
        # fixed control set: same period, eligible, not a signal day, a valid next-day entry inside the contract
        sig = set(I_.tolist())
        pool = np.array([k for k in np.where(elig & ~np.isnan(a))[0] if k not in sig and iend(k) > k], np.int64)
        ci = []
        for P in ("DEV", "VALID", "OOS"):
            need = int((per == P).sum()); cand = pool[perf[pool] == P]
            if need:
                ci.append(rng.choice(cand, size=need, replace=need > len(cand)))
        ci = np.sort(np.concatenate(ci)) if ci else np.array([], np.int64)
        reuse = int(len(ci) - len(np.unique(ci)))
        cc = cpts(ci); perc = perf[ci]; Sc = np.full(len(ci), side, np.int64)
        rows, keep = [], {}
        for em, sm, xm in EXECS:
            dist = np.clip(np.abs(c[I_] - inv) + 0.1 * A, 0.3 * A, 3 * A) if sm == "inv" else 1.5 * A
            ref = o[np.minimum(I_ + 1, n - 1)] if em == 0 else trig
            stop = ref - S * dist
            tg = 2.0 if xm == "2R" else 0.0; tr = 2.0 if xm == "trail" else 0.0
            dc = np.median(dist / A) * a[ci]
            sc = o[np.minimum(ci + 1, n - 1)] - side * dc
            for cm in (1.0, 2.0):
                R = EX.run_stream(o, h, l, c, I_, S, stop, IE, cost, A, trig, inv, tg, tr, em, cm)
                Rc = EX.run_stream(o, h, l, c, ci, Sc, sc, np.array([iend(i) for i in ci], np.int64), cc, a[ci],
                                   np.full(len(ci), np.nan), np.full(len(ci), np.nan), tg, tr, 0, cm)
                keep[(em, sm, xm, cm)] = (R, Rc)
                for P in ("DEV", "VALID", "OOS", "DV"):
                    m = ((per == P) if P != "DV" else (per != "OOS")) & ~np.isnan(R[:, 0])
                    mc = ((perc == P) if P != "DV" else (perc != "OOS")) & ~np.isnan(Rc[:, 0])
                    rows.append(dict(entry=em, stop=sm, exit=xm, cost=cm, period=P, n=int(m.sum()),
                                     R=float(R[m, 0].mean()) if m.any() else np.nan, n_ctl=int(mc.sum()),
                                     R_ctl=float(Rc[mc, 0].mean()) if mc.any() else np.nan))
        T = pd.DataFrame(rows)
        T.to_csv(OUT / f"stage2_daily_v2_{market}_{inst}.csv", index=False)
        cand_sel = T[(T.period == "DV") & (T.cost == 2.0) & (T.n >= 30)].sort_values("R", ascending=False)
        sel = cand_sel.iloc[0]
        key = (int(sel.entry), sel.stop, sel.exit)
        res = dict(events=dict(raw=n_raw, eligible_days=n_elig, unique_signal_bars=int(len(I_))),
                   control=dict(n=int(len(ci)), reused_dates=reuse, pool_size=int(len(pool))),
                   frozen_choice=dict(entry=["next open", "stop at trigger"][key[0]], stop=key[1], exit=key[2],
                                      DV_net_R_2x=round(float(sel.R), 3), DV_n=int(sel.n),
                                      same_as_v1=None))
        tr_rows = []
        for cm in (1.0, 2.0):
            R, Rc = keep[key + (cm,)]
            traded = ~np.isnan(R[:, 0])
            res.setdefault("skipped_events", {})[f"{cm:g}x"] = dict(no_fill_or_overlap=int((~traded).sum()))
            for P in ("DEV", "VALID", "OOS"):
                m = (per == P) & traded; mc = (perc == P) & ~np.isnan(Rc[:, 0])
                ev_dates = t[R[m, 3].astype(np.int64)] if m.any() else []
                ctl_dates = t[Rc[mc, 3].astype(np.int64)] if mc.any() else []
                bl = BT.block_ci(ev_dates, R[m, 0])
                blc = BT.block_ci(ctl_dates, Rc[mc, 0])
                diff = None
                if m.any() and mc.any():
                    diff = round(float(R[m, 0].mean() - Rc[mc, 0].mean()), 3)
                iid = None
                if m.sum() > 1:
                    x = R[m, 0]
                    b = [np.mean(np.random.default_rng(k).choice(x, len(x))) for k in range(5000)]
                    iid = [round(float(np.percentile(b, 2.5)), 3), round(float(np.percentile(b, 97.5)), 3)]
                res.setdefault("by_period", {}).setdefault(P, {})[f"{cm:g}x"] = dict(event=bl, control=blc,
                                                                                    event_minus_control=diff,
                                                                                    iid_trade_bootstrap_v1_method=iid)
                if cm == 1.0:
                    for k in np.where(m)[0]:
                        tr_rows.append(dict(kind="event", period=P, signal=t[I_[k]], entry=t[int(R[k, 3])], exit=t[int(R[k, 2])],
                                            netR_1x=R[k, 0], grossR=R[k, 1], cost_R_v2=R[k, 1] - R[k, 0]))
                    for k in np.where(mc)[0]:
                        tr_rows.append(dict(kind="control", period=P, signal=t[ci[k]], entry=t[int(Rc[k, 3])],
                                            exit=t[int(Rc[k, 2])], netR_1x=Rc[k, 0], grossR=Rc[k, 1], cost_R_v2=Rc[k, 1] - Rc[k, 0]))
        pd.DataFrame(tr_rows).to_csv(OUT / f"stage2_daily_v2_trades_{market}_{inst}.csv", index=False)
        res["cost_check"] = dict(median_cost_points_v2=round(float(np.median(cost)), 4),
                                 median_cost_points_v1=round(float(np.median(cost_v1)), 4))
        oos = res["by_period"]["OOS"]["1x"]["event"]
        lo = (oos.get("ci95_conservative") or [np.nan])[0]
        res["verdict"] = ("ACCEPT as potentially promising" if (oos.get("n", 0) and lo == lo and lo > 0
                          and res["by_period"]["OOS"]["2x"]["event"]["mean"] > 0
                          and (res["by_period"]["OOS"]["1x"]["event_minus_control"] or 0) > 0)
                          else "REJECT (pre-registered acceptance not met)")
        allout[f"{market} {inst} {name} {'BUY' if side > 0 else 'SELL'}"] = res
    v1 = json.loads((OUT / "stage2_daily.json").read_text()) if (OUT / "stage2_daily.json").exists() else {}
    for k, r in allout.items():
        if k in v1:
            fc = v1[k]["frozen_choice"]
            r["frozen_choice"]["same_as_v1"] = (fc["entry"], fc["stop"], fc["exit"]) == (r["frozen_choice"]["entry"],
                                                                                       r["frozen_choice"]["stop"], r["frozen_choice"]["exit"])
    (OUT / "stage2_daily_v2.json").write_text(json.dumps(allout, indent=1, default=str))
    print(json.dumps(allout, indent=1, default=str))


if __name__ == "__main__":
    main()
