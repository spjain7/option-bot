"""TRIAL AND ERROR on MCX (owner 17-Nov-2026): every combination of
  family    10-day / 20-day / 55-day breakout, EMA 9/21, 13/48, 20/50 cross, MACD zero / signal cross, RSI 70 / 80 momentum,
            Bollinger squeeze, momentum candle, Supertrend flip, breakout retest
  candles   2h, 3h, 4h (MCX day-anchored, Jul-2022 ->) and daily (2006 ->)
  side      BUY, SELL      filter  none / daily trend / EMA200 side      stop  1.5 / 2 / 3 ATR      target  2R / 3R
on each of the 7 commodities, with real MCX costs. The best combination per commodity is chosen on TRAIN only
(intraday 2022-07..2024-06, daily 2006-2016; >= 15 trades) and then shown, unchanged, on VALID and OOS.
Output: reports/mcx_search.csv (every combination), reports/mcx_search_best.json (chosen strategies + every trade, Rs per lot)
python -m research.mcx_institutional_buy.stock_rules_on_mcx.search"""
import itertools
import json
import warnings
import numpy as np
import pandas as pd
from alerts import rulebook as RB
from research.mcx_institutional_buy.backtesting import data as D, costs as K, sim as S, runner as RN, metrics as M
from research.mcx_institutional_buy.stock_rules_on_mcx.run import frames, dtrend

warnings.filterwarnings("ignore")
FAMS = [("BO", "N10 vol0"), ("BO", "N20 vol0"), ("BO", "N55 vol0"), ("EMAX", "9/21"), ("EMAX", "13/48"), ("EMAX", "20/50"),
        ("MACD", "zero"), ("MACD", "signal"), ("RSICONT", "70/30"), ("RSICONT", "80/20"), ("SQZ", "BB20"), ("MOMO", "1.5ATR"),
        ("ST", "10/3"), ("RETEST", "20/5")]
TFS = ["2h", "3h", "4h", "1d"]
FILTS = ["none", "DT", "EMA200"]
KS = [1.5, 2.0, 3.0]
RS = [2.0, 3.0]
MAXH = {"2h": 50, "3h": 40, "4h": 40, "1d": 20}
MULT = {k: v["mult"] for k, v in K.CFG["contracts"].items()}


def run_one(f, sig, side, k, r, maxh, name):
    s_ = 1 if side > 0 else -1
    o, h, l, c = (f[x].values.astype(float) for x in ("open", "high", "low", "close"))
    a = f["atr"].values.astype(float)
    if s_ < 0:
        o, h, l, c = -o, -l, -h, -c
    stop = c - k * a
    costf = K.cost_frac(name, f["raw_close"].values, pd.to_datetime(f["time"])) * s_
    si, ei, xi, g, nr, mfe, mae, why, rej = S.simulate(o, h, l, c, a, f["seg"].values.astype(np.int64), costf, np.asarray(sig, bool),
                                                       stop, np.full(len(c), np.nan), np.full(len(c), np.nan), 0, float(r),
                                                       int(maxh), int(maxh), 3.0, 3, 0.25, 6.0, 1.5)
    return si, ei, xi, g, nr, mfe, mae, why


def masks(f, dd):
    out = {}
    dt = dtrend(f, dd)
    e = f["ema200"].values; c = f["close"].values
    for fam, par in FAMS:
        try:
            b, s_ = RB.raw(f, fam, par)
        except Exception:
            continue
        for side, m in ((1, b), (-1, s_)):
            m = np.nan_to_num(np.asarray(m, float)).astype(bool)
            out[(fam, par, side, "none")] = m
            out[(fam, par, side, "DT")] = m & (dt == side)
            out[(fam, par, side, "EMA200")] = m & (side * (c - e) > 0)
    return out


def period(tf, t):
    return RN.period_of("1d" if tf == "1d" else "1h", t)


def main():
    rows = []; keep = {}
    for name in D.INTRA:
        F, dd = frames(name)
        for tf in TFS:
            f = F[tf]; t = pd.to_datetime(f["time"]).values; per_bar = period(tf, f["time"])
            for (fam, par, side, flt), m in masks(f, dd).items():
                if m.sum() < 10:
                    continue
                for k, r in itertools.product(KS, RS):
                    si, ei, xi, g, nr, mfe, mae, why = run_one(f, m, side, k, r, MAXH[tf], name)
                    if not len(nr):
                        continue
                    p = per_bar[ei]
                    row = dict(name=name, tf=tf, fam=fam, par=par, side="BUY" if side > 0 else "SELL", filt=flt, k=k, r=r)
                    for P in ("TRAIN", "VAL", "OOS"):
                        x = nr[p == P]
                        row[f"{P}_n"] = len(x); row[f"{P}_R"] = round(float(x.mean()), 3) if len(x) else np.nan
                        row[f"{P}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else np.nan
                        row[f"{P}_PF"] = round(float(x[x > 0].sum() / -x[x <= 0].sum()), 2) if len(x) and (x <= 0).any() else np.nan
                    rows.append(row)
                    keep[(name, tf, fam, par, side, flt, k, r)] = (si, ei, xi, g, nr, mfe, mae, why)
        print(name, "tested", sum(1 for x in rows if x["name"] == name), flush=True)
    L = pd.DataFrame(rows)
    L["id"] = L.tf + " " + L.fam + " " + L.par + " " + L.side + " " + L.filt + f" " + L.k.astype(str) + "ATR " + L.r.astype(str) + "R"
    L.to_csv(RN.REPORTS / "mcx_search.csv", index=False)
    # best per commodity, chosen on TRAIN only
    best = {}
    for name, g in L.groupby("name"):
        c = g[(g.TRAIN_n >= 15) & (g.VAL_n >= 5)].sort_values("TRAIN_R", ascending=False)
        best[name] = c.iloc[0].to_dict() if len(c) else None
    # pooled leaderboard: same combination on all 7 (TRAIN-ranked)
    P = L.groupby(["tf", "fam", "par", "side", "filt", "k", "r"]).apply(lambda g: pd.Series({
        **{f"{p}_n": g[f"{p}_n"].sum() for p in ("TRAIN", "VAL", "OOS")},
        **{f"{p}_R": (g[f"{p}_R"] * g[f"{p}_n"]).sum() / max(g[f"{p}_n"].sum(), 1) for p in ("TRAIN", "VAL", "OOS")},
        "commodities_pos": int((g.TRAIN_R > 0).sum())})).reset_index()
    P = P[P.TRAIN_n >= 60].sort_values("TRAIN_R", ascending=False)
    P["all3_positive"] = (P.TRAIN_R > 0) & (P.VAL_R > 0) & (P.OOS_R > 0)
    P.to_csv(RN.REPORTS / "mcx_search_pooled.csv", index=False)
    # trades of each commodity's chosen strategy (+ the pooled #1)
    out = dict(meta=dict(tested=int(len(L)), combos_per_commodity=int(len(L) / 7), periods=K.CFG["splits"],
                         note="Best per commodity chosen on TRAIN only; VALID / OOS shown unchanged. Rs per 1 lot after costs."),
               commodities={}, pooled=P.head(25).round(3).to_dict("records"), top_by_commodity={})
    for name, b in best.items():
        out["top_by_commodity"][name] = L[L.name == name].sort_values("TRAIN_R", ascending=False).head(10).round(3).to_dict("records")
        if b is None:
            continue
        F, dd = frames(name); f = F[b["tf"]]
        side = 1 if b["side"] == "BUY" else -1
        si, ei, xi, g, nr, mfe, mae, why = keep[(name, b["tf"], b["fam"], b["par"], side, b["filt"], b["k"], b["r"])]
        o = f["open"].values.astype(float); c = f["close"].values.astype(float); a = f["atr"].values.astype(float)
        fac = f["raw_close"].values / c                                      # adjusted -> raw price in the same contract
        stop = c[si] - side * b["k"] * a[si]
        rk = side * (o[ei] - stop)
        e_raw = o[ei] * fac[ei]; x_raw = (o[ei] + side * g * rk) * fac[ei]
        rs = nr * rk * fac[ei] * MULT[name]
        best_rs = mfe * rk * fac[ei] * MULT[name]; worst_rs = mae * rk * fac[ei] * MULT[name]
        t = pd.to_datetime(f["time"]); per = period(b["tf"], t.iloc[ei])
        reason = {1: "stop-loss", 2: "target", 3: "time exit", 4: "contract roll"}
        trades = [dict(entry=str(t.iloc[ei[i]])[:16], exit=str(t.iloc[xi[i]])[:16], side=b["side"], entry_px=round(float(e_raw[i]), 2),
                       exit_px=round(float(x_raw[i]), 2), R=round(float(nr[i]), 2), rs=int(round(rs[i])), best_rs=int(round(best_rs[i])),
                       worst_rs=int(round(worst_rs[i])), period=str(per[i]), exit_reason=reason.get(int(why[i]), "exit"))
                  for i in range(len(nr))]
        out["commodities"][name] = dict(strategy=b, lot_mult=MULT[name], trades=trades)
        print(name, b["id"], "TRAIN", b["TRAIN_R"], "VAL", b["VAL_R"], "OOS", b["OOS_R"], "trades", len(trades), flush=True)
    # trades of the top-3 shared rules (same rule on all 7; TRAIN-ranked, positive in all three periods)
    top = P[P.all3_positive & (P.TRAIN_n >= 60)].drop_duplicates(["fam", "par"]).head(4)          # best of each family
    out["shared"] = []
    for _, b in top.iterrows():
        rid = f"{b.tf} {b.fam} {b.par} {b.side} {b.filt} {b.k}ATR {b.r}R"
        rec = dict(id=rid, **{k_: (float(b[k_]) if isinstance(b[k_], (float, np.floating)) else b[k_]) for k_ in b.index}, trades={})
        side = 1 if b.side == "BUY" else -1
        for name in D.INTRA:
            key = (name, b.tf, b.fam, b.par, side, b.filt, b.k, b.r)
            if key not in keep:
                continue
            F, dd = frames(name); f = F[b.tf]
            si, ei, xi, g, nr, mfe, mae, why = keep[key]
            o = f["open"].values.astype(float); c = f["close"].values.astype(float); a = f["atr"].values.astype(float)
            fac = f["raw_close"].values / c; stop = c[si] - side * b.k * a[si]; rk = side * (o[ei] - stop)
            t = pd.to_datetime(f["time"]); per = period(b.tf, t.iloc[ei])
            rec["trades"][name] = [dict(entry=str(t.iloc[ei[i]])[:16], exit=str(t.iloc[xi[i]])[:16], side=b.side,
                                        entry_px=round(float(o[ei[i]] * fac[ei[i]]), 2),
                                        exit_px=round(float((o[ei[i]] + side * g[i] * rk[i]) * fac[ei[i]]), 2), R=round(float(nr[i]), 2),
                                        rs=int(round(nr[i] * rk[i] * fac[ei[i]] * MULT[name])),
                                        best_rs=int(round(mfe[i] * rk[i] * fac[ei[i]] * MULT[name])),
                                        worst_rs=int(round(mae[i] * rk[i] * fac[ei[i]] * MULT[name])), period=str(per[i]),
                                        exit_reason={1: "stop-loss", 2: "target", 3: "time exit", 4: "contract roll"}.get(int(why[i]), "exit"))
                                   for i in range(len(nr))]
        out["shared"].append(rec)
        print("shared", rid, {k_: len(v) for k_, v in rec["trades"].items()}, flush=True)
    (RN.REPORTS / "mcx_search_best.json").write_text(json.dumps(out, default=lambda x: None if x != x else (float(x) if isinstance(x, np.floating) else int(x) if isinstance(x, np.integer) else str(x))))
    print(P.head(15).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
