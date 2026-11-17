"""ROUND 9 (owner 17-Nov-2026): (1) best WEIGHTED COMBINATION per script, (2) which setups give a good move BEFORE the stop.
(1) per commodity / candle / side: every round-8 setup is traded with the standard exit on TRAIN only; setups with a positive
    TRAIN average (>= 15 trades) get weight = that average R. Score of a candle = sum of the weights of the setups that fired on
    it or the 2 candles before (confluence). Trade when the score is in the TRAIN top 20 / 10 / 5 %, or when >= 2 / >= 3 of
    those setups agree. Exits: SL 2 ATR + 3R / 2R, SL 1.5 ATR + 3R, 3 ATR trailing, or half off at 1R + stop to break-even +
    rest at 3R (books the move before a reversal). Pick per commodity on TRAIN + VALID (score + random check), OOS unchanged.
(2) for every setup (standard exit): share of trades that went >= +1R and >= +2R in our favour before exit, average best move
    (R and Rs) of all trades and of the trades that ended at the stop.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round9 -> reports/mcx_round9_*.csv / .json"""
import itertools
import json
import warnings
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import data as D, costs as K, sim as S, runner as RN
from research.mcx_institutional_buy.stock_rules_on_mcx import round4 as R4, round8 as R8
from research.mcx_institutional_buy.stock_rules_on_mcx.run import frames
from research.mcx_institutional_buy.stock_rules_on_mcx.patterns import NAN as _N  # noqa: F401

warnings.filterwarnings("ignore")
TFS = ["1h", "2h", "3h", "4h", "1d"]
EXITS = [("SL 2 ATR · target 3R", 2.0, 0, 3.0), ("SL 2 ATR · target 2R", 2.0, 0, 2.0), ("SL 1.5 ATR · target 3R", 1.5, 0, 3.0),
         ("SL 2 ATR · 3 ATR trailing stop", 2.0, 2, 0.0), ("SL 2 ATR · half at 1R, rest 3R (stop to cost)", 2.0, 4, 3.0)]
NAN = {}


def run(f, arr, side, sig, name, tf, k, kind, r):
    o, h, l, c, a = arr["o"], arr["h"], arr["l"], arr["c"], arr["a"]; n = len(c); NAN.setdefault(n, np.full(n, np.nan))
    costf = K.cost_frac(name, f["raw_close"].values, pd.to_datetime(f["time"])) * side
    return S.simulate(o, h, l, c, a, f["seg"].values.astype(np.int64), costf, np.asarray(sig, bool), c - k * a, NAN[n], NAN[n],
                      kind, float(r), 40, 40, 3.0, 3, 0.25, 6.0, 1.0)[:8]


def st(nr, pe):
    o = {}
    for p in ("TRAIN", "VAL", "OOS"):
        x = nr[pe == p]; o[f"{p}_n"] = len(x)
        o[f"{p}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else np.nan
        o[f"{p}_R"] = round(float(x.mean()), 3) if len(x) else np.nan
    return o


def main():
    move = []; combos = []; ctr = {}
    rng = np.random.default_rng(41)
    for name in D.INTRA:
        B = R4.build(name, TFS); F, dd = frames(name)
        for tf in TFS:
            d = B[tf]; f = d["f"]; per = d["per"]
            fac = f["raw_close"].values / f["close"].values
            for side in (1, -1):
                SU, arr = R8.setups(name, d, dd, tf, side)
                # stop-order setups excluded from the combo (different entry); kept for the move table
                w = {}; masks = {}
                for lab, (sig, lvl, win) in SU.items():
                    sig = np.nan_to_num(np.asarray(sig, float)).astype(bool)
                    if sig.sum() < 5:
                        continue
                    if lvl is None:
                        si, ei, xi, g, nr, mfe, mae, why = run(f, arr, side, sig, name, tf, 2.0, 0, 3.0)
                    else:
                        (si, ei, xi, g, nr, mfe, mae, why), stop, el = R8.sim(f, arr, side, sig, name, tf, lvl, win)
                    if len(nr) < 5:
                        continue
                    risk = (arr["o"][ei] if lvl is None else np.maximum(arr["o"][ei], lvl[si])) - (arr["c"][si] - 2.0 * arr["a"][si] if lvl is None else lvl[si] - 2.0 * arr["a"][si])
                    M = R4.MULT[name] * fac[ei]; best_rs = mfe * risk * M
                    los = why == 1
                    move.append(dict(commodity=name, timeframe=R8.TFN[tf], side="BUY" if side > 0 else "SELL", setup=lab, trades=len(nr),
                                     reach_1R_pct=round(100 * float((mfe >= 1).mean()), 1), reach_2R_pct=round(100 * float((mfe >= 2).mean()), 1),
                                     avg_best_R=round(float(mfe.mean()), 2), avg_best_rs=int(best_rs.mean()),
                                     stop_trades=int(los.sum()), stopped_reached_1R_pct=round(100 * float((mfe[los] >= 1).mean()), 1) if los.any() else None,
                                     stopped_avg_best_R=round(float(mfe[los].mean()), 2) if los.any() else None,
                                     stopped_avg_best_rs=int(best_rs[los].mean()) if los.any() else None, win_pct=round(100 * float((nr > 0).mean()), 1),
                                     avg_R=round(float(nr.mean()), 3)))
                    if lvl is None:
                        tr = per[ei] == "TRAIN"
                        if tr.sum() >= 15 and nr[tr].mean() > 0:
                            w[lab] = float(nr[tr].mean()); masks[lab] = sig
                if len(w) < 2:
                    continue
                n = len(arr["c"])
                recent = {k_: pd.Series(m.astype(float)).rolling(3, min_periods=1).max().values > 0 for k_, m in masks.items()}
                score = sum(w[k_] * recent[k_] for k_ in w); cnt = sum(recent[k_].astype(int) for k_ in w)
                fire = sum(masks[k_].astype(int) for k_ in w) > 0          # at least one setup fires on this candle
                trs = (per == "TRAIN") & fire & (score > 0)
                rules = {}
                for q in (80, 90, 95):
                    thr = np.percentile(score[trs], q) if trs.any() else np.inf
                    rules[f"weighted score top {100 - q}%"] = fire & (score >= thr)
                rules["2+ setups agree"] = fire & (cnt >= 2); rules["3+ setups agree"] = fire & (cnt >= 3)
                for rl, m in rules.items():
                    if m.sum() < 15:
                        continue
                    for el, k, kind, r in EXITS:
                        si, ei, xi, g, nr, mfe, mae, why = run(f, arr, side, m, name, tf, k, kind, r)
                        if len(nr) < 15:
                            continue
                        row = dict(commodity=name, tf=tf, side="BUY" if side > 0 else "SELL", rule=rl, exit=el, weights=json.dumps({k_: round(v, 3) for k_, v in w.items()}),
                                   **st(nr, per[ei]))
                        combos.append(row); ctr[(name, tf, row["side"], rl, el)] = (m, k, kind, r)
            print(name, tf, len(move), len(combos), flush=True)
        ctr[name] = (B, F, dd)
    M_ = pd.DataFrame(move); M_.to_csv(RN.REPORTS / "mcx_round9_move.csv", index=False)
    C = pd.DataFrame(combos); C.to_csv(RN.REPORTS / "mcx_round9_combo.csv", index=False)
    # pick per commodity: TRAIN and VALID positive, >= 20 / 8 trades, robust score, random check
    C["score"] = np.minimum(C.TRAIN_R * np.sqrt(C.TRAIN_n), C.VAL_R * np.sqrt(C.VAL_n))
    Q = C[(C.TRAIN_R > 0) & (C.VAL_R > 0) & (C.TRAIN_n >= 20) & (C.VAL_n >= 8)].sort_values("score", ascending=False)
    out = {}; trades = []; summary = []
    for name in D.INTRA:
        B, F, dd = ctr[name]; pick = None; tried = []
        for _, x in Q[Q.commodity == name].drop_duplicates(["tf", "side", "rule"]).head(8).iterrows():
            m, k, kind, r = ctr[(name, x.tf, x.side, x.rule, x.exit)]
            side = 1 if x.side == "BUY" else -1; d = B[x.tf]; f = d["f"]; per = d["per"]
            SU, arr = R8.setups(name, d, dd, x.tf, side)
            si, ei, xi, g, nr, mfe, mae, why = run(f, arr, side, m, name, x.tf, k, kind, r)
            rate = m.sum() / len(m); dr = {p: [] for p in ("TRAIN", "VAL", "OOS")}
            for _ in range(200):
                y = run(f, arr, side, rng.random(len(m)) < rate, name, x.tf, k, kind, r); yp = per[y[1]]
                for p in dr:
                    z = y[4][yp == p]; dr[p].append(z.mean() if len(z) else np.nan)
            s_ = st(nr, per[ei])
            fac = f["raw_close"].values / f["close"].values; risk = arr["o"][ei] - (arr["c"][si] - k * arr["a"][si]); MM = R4.MULT[name] * fac[ei]
            rs = nr * risk * MM; best = mfe * risk * MM; worst = mae * risk * MM
            rec = dict(commodity=name, timeframe=R8.TFN[x.tf], side=x.side, setup=f"Weighted combo: {x.rule}", exit=x.exit, weights=json.loads(x.weights), **s_,
                       trades=len(nr), win_pct=round(100 * float((nr > 0).mean()), 1), avg_R=round(float(nr.mean()), 3), total_rs=int(rs.sum()),
                       avg_best_after_call_rs=int(best.mean()), avg_worst_after_call_rs=int(worst.mean()), biggest_win_rs=int(rs.max()),
                       biggest_loss_rs=int(rs.min()), reach_1R_pct=round(100 * float((mfe >= 1).mean()), 1))
            for p in dr:
                a = np.array(dr[p], float); rec[f"{p}_random_R"] = round(float(np.nanmean(a)), 3)
                rec[f"{p}_beats_pct"] = int(100 * np.nanmean(a < s_[f"{p}_R"])) if s_[f"{p}_R"] == s_[f"{p}_R"] else None
            tried.append(rec)
            if pick is None and (rec["TRAIN_beats_pct"] or 0) >= 80 and (rec["VAL_beats_pct"] or 0) >= 80:
                pick = rec
                t = pd.to_datetime(f["time"]); key = f"{name}|{rec['timeframe']}|{x.side}|{rec['setup']} · {x.exit}"
                rec["id"] = key
                for i in range(len(nr)):
                    trades.append(dict(id=f"{key}|{i}", key=key, commodity=name, timeframe=rec["timeframe"], side=x.side, setup=rec["setup"],
                                       entry=str(t.iloc[ei[i]])[:16], exit=str(t.iloc[xi[i]])[:16], entry_px=round(float(side * arr["o"][ei[i]] * fac[ei[i]]), 2),
                                       exit_px=round(float(side * (arr["o"][ei[i]] + g[i] * risk[i]) * fac[ei[i]]), 2), R=round(float(nr[i]), 2),
                                       pnl_rs=int(round(rs[i])), best_after_call_rs=int(round(best[i])), worst_after_call_rs=int(round(worst[i])),
                                       period={"VAL": "VALID"}.get(str(per[ei[i]]), str(per[ei[i]])),
                                       result={1: "stop-loss", 2: "target", 3: "time exit", 4: "contract roll", 5: "rest stopped at cost"}.get(int(why[i]), "exit")))
        out[name] = dict(pick=pick, tried=tried)
        print(f"\n{name}: " + (f"PICK {pick['timeframe']} {pick['side']} {pick['setup']} · {pick['exit']}" if pick else "NO PICK"))
        for z in tried:
            print(f"   {z['timeframe']:7s} {z['side']:4s} {z['setup'][16:]:26s} {z['exit'][:40]:40s} T {z['TRAIN_n']}/{z['TRAIN_win']}%/{z['TRAIN_R']:+.2f} b{z['TRAIN_beats_pct']}"
                  f" V {z['VAL_n']}/{z['VAL_win']}%/{z['VAL_R']:+.2f} b{z['VAL_beats_pct']} O {z['OOS_n']}/{z['OOS_win']}%/{z['OOS_R']} (rnd {z['OOS_random_R']} b{z['OOS_beats_pct']})"
                  f" Rs {z['total_rs']:,} reach1R {z['reach_1R_pct']}%", flush=True)
    (RN.REPORTS / "mcx_round9_pick.json").write_text(json.dumps(dict(picks=out, trades=trades), default=lambda v: None))
    # move-before-stop summary
    G = M_[M_.trades >= 30].sort_values("stopped_avg_best_R", ascending=False)
    print("\nBEST MOVE BEFORE STOP (stopped trades' average best move, R):")
    print(G.groupby("commodity").head(3)[["commodity", "timeframe", "side", "setup", "trades", "reach_1R_pct", "reach_2R_pct", "avg_best_R",
                                          "stopped_reached_1R_pct", "stopped_avg_best_R", "stopped_avg_best_rs", "win_pct", "avg_R"]].to_string(index=False))


if __name__ == "__main__":
    main()
