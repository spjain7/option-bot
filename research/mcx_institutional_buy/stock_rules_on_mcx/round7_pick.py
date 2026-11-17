"""ROUND 7 pick: each commodity's best BREAKOUT (BUY) and best BREAKDOWN (SELL), chosen on TRAIN + VALID only.
candidates  TRAIN and VALID positive, >= 20 / 8 trades, >= 50 % of the other exits of the same entry also positive
rank        robust score min(TRAIN_R*sqrt(n), VALID_R*sqrt(n)); top 8 distinct entries
check       random entries (same candle, filter, side, stop size in ATR, target / trail, holding; 200 draws) on TRAIN and
            VALID; the pick is the best-ranked that beats >= 80 % of random draws in both. OOS shown unchanged; Rs per 1 lot.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round7_pick -> reports/mcx_round7_pick.json"""
import json
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import data as D, runner as RN
from research.mcx_institutional_buy.stock_rules_on_mcx import round4 as R4, round7 as R7
from research.mcx_institutional_buy.stock_rules_on_mcx.run import frames, dtrend

FAMN = {"ORB1": "first-hour range", "ORB2": "first-2-hour range", "ORBE": "17:00 evening-hour range", "PDH": "previous-day high",
        "NR7": "NR7 day (narrowest of 7)", "IDNR7": "inside + NR7 day", "PWH": "previous-week high"}
FAMS = {"PDH": "previous-day low", "PWH": "previous-week low"}
ENT = ["tf", "side", "fam", "filt", "stop", "hold"]


def fam_label(fam, side):
    if fam.startswith("BOX"):
        N, w = fam[3:].split("_"); return f"{N}-candle box (≤ {w} ATR tall)"
    return (FAMS.get(fam) if side < 0 else None) or FAMN[fam]


def label(r):
    side = 1 if r["side"] == "BUY" else -1
    tf = "1h" if r["tf"] == "1h" else "Daily"
    what = "breakout BUY (buy-stop above" if side > 0 else "breakdown SELL (sell-stop below"
    st = "stop at the other side of the range" if r["stop"] == "STRUCT" else f"SL {float(r['stop']):g} ATR"
    ex = "trailing stop 3 ATR" if r["exit"].startswith("trail") else f"target {r['exit']}"
    hold = "exit by day end" if r["hold"] == "EOD" else ("hold up to 40 hours" if tf == "1h" else "hold up to 20 days")
    flt = " · daily trend on our side" if r["filt"] == "DT" else ""
    return f"{tf} {fam_label(r['fam'], side)} {what} it){flt} · {st} · {ex} · {hold}"


def main():
    L = pd.read_csv(RN.REPORTS / "mcx_round7.csv")
    L["nb"] = L.assign(ok=(L.TRAIN_R > 0) & (L.VAL_R > 0)).groupby(["name"] + ENT).ok.transform("mean")
    L["score"] = np.minimum(L.TRAIN_R * np.sqrt(L.TRAIN_n), L.VAL_R * np.sqrt(L.VAL_n))
    C = L[(L.TRAIN_R > 0) & (L.VAL_R > 0) & (L.TRAIN_n >= 20) & (L.VAL_n >= 8) & (L.nb >= 0.5)].sort_values("score", ascending=False)
    print("candidates:", C.groupby(["name", "side"]).size().to_dict())
    rng = np.random.default_rng(31); out = {}; trades = []
    for name in D.INTRA:
        F, dd = frames(name)
        f1 = F["1h"].reset_index(drop=True); t1 = pd.to_datetime(f1["time"]); per1 = RN.period_of("1h", t1)
        dayid = pd.factorize(t1.dt.normalize())[0]
        seg_eod = (f1["seg"].values.astype(np.int64) * 100000 + dayid).astype(np.int64); seg_sw = f1["seg"].values.astype(np.int64)
        fd = R4.feats(dd); perd = RN.period_of("1d", pd.to_datetime(fd["time"]))
        out[name] = {}
        for sd in ("BUY", "SELL"):
            side = 1 if sd == "BUY" else -1
            cand = C[(C.name == name) & (C.side == sd)].drop_duplicates(ENT).head(8); tried = []; pick = None
            for _, r in cand.iterrows():
                f, per = (f1, per1) if r.tf == "1h" else (fd, perd)
                dt = dtrend(f, dd)
                S_ = R7.setups_1h(f, dd, side) if r.tf == "1h" else R7.setups_1d(f, side)
                fam, sig, lvl, st, win = [x for x in S_ if x[0] == r.fam][0]
                base = (dt == side) if r.filt == "DT" else np.ones(len(sig), bool)
                s = sig & base
                stop = st if r.stop == "STRUCT" else lvl - float(r.stop) * f["atr"].values
                seg = seg_eod if r.hold == "EOD" else (seg_sw if r.tf == "1h" else fd["seg"].values.astype(np.int64))
                mh = 15 if r.hold == "EOD" else (40 if r.tf == "1h" else 20)
                kind, rr = (2, 0.0) if r.exit.startswith("trail") else (0, float(r.exit[:-1]))
                si, ei, xi, g, nr, mfe, mae, why = R7.sim(f, side, s, lvl, stop, win, kind, rr, mh, seg, name)
                pe = per[ei]; stt = R7.pst(nr, pe)
                o, h, l, c = R7.mirror(f, side); a = f["atr"].values.astype(float)
                px = np.maximum(o[ei], lvl[si]); risk = px - stop[si]; fac = f["raw_close"].values / f["close"].values
                rs = nr * risk * fac[ei] * R7.MULT[name]
                # random: next-open entries on base bars, same stop size in ATR (median), same exit / holding
                kk = float(np.median(risk / a[si])); rate = len(nr) / max(base.sum(), 1) * 1.5
                dr = {p: [] for p in ("TRAIN", "VAL", "OOS")}
                for _ in range(200):
                    rm = base & (rng.random(len(base)) < rate)
                    y = R7.sim(f, side, rm, np.full(len(c), np.nan), c - kk * a, 1, kind, rr, mh, seg, name)
                    yp = per[y[1]]
                    for p in dr:
                        z = y[4][yp == p]; dr[p].append(z.mean() if len(z) else np.nan)
                rec = dict(strategy=label(r), **{k: str(r[k]) for k in ENT}, exit=r.exit, **stt, ALL_n=len(nr),
                           ALL_win=round(100 * float((nr > 0).mean()), 1), ALL_R=round(float(nr.mean()), 3), rs=int(rs.sum()),
                           avg_win_rs=int(rs[rs > 0].mean()) if (rs > 0).any() else 0, avg_loss_rs=int(rs[rs <= 0].mean()) if (rs <= 0).any() else 0,
                           rs_OOS=int(rs[pe == "OOS"].sum()))
                for p in dr:
                    arr = np.array(dr[p], float)
                    rec[f"{p}_random_R"] = round(float(np.nanmean(arr)), 3) if np.isfinite(arr).any() else None
                    rec[f"{p}_beats_pct"] = int(100 * np.nanmean(arr < stt[f"{p}_R"])) if (stt[f"{p}_R"] == stt[f"{p}_R"] and np.isfinite(arr).any()) else None
                tried.append(rec)
                if pick is None and (rec["TRAIN_beats_pct"] or 0) >= 80 and (rec["VAL_beats_pct"] or 0) >= 80:
                    pick = rec
                    t = pd.to_datetime(f["time"])
                    for i in range(len(nr)):
                        trades.append(dict(strategy=f"Round 7 · {name} {sd} · {rec['strategy']}", commodity=name, side=sd,
                                           entry=str(t.iloc[ei[i]])[:16], exit=str(t.iloc[xi[i]])[:16],
                                           entry_px=round(float(side * px[i] * fac[ei[i]]), 2),
                                           exit_px=round(float(side * (px[i] + g[i] * risk[i]) * fac[ei[i]]), 2), R=round(float(nr[i]), 2),
                                           pnl_rs=int(round(rs[i])), best_rs=int(round(mfe[i] * risk[i] * fac[ei[i]] * R7.MULT[name])),
                                           worst_rs=int(round(mae[i] * risk[i] * fac[ei[i]] * R7.MULT[name])), period=str(pe[i]),
                                           result={1: "stop-loss", 2: "target", 3: "time exit", 4: "day end / roll"}.get(int(why[i]), "exit")))
            out[name][sd] = dict(pick=pick, tried=tried)
            print(f"\n{name} {sd}: " + (f"PICK {pick['strategy']}" if pick else "NO PICK"))
            for x in tried:
                print(f"   {x['strategy'][:110]:110s} T {x['TRAIN_n']}/{x['TRAIN_win']}%/{x['TRAIN_R']:+.2f} b{x['TRAIN_beats_pct']}"
                      f" V {x['VAL_n']}/{x['VAL_win']}%/{x['VAL_R']:+.2f} b{x['VAL_beats_pct']} O {x['OOS_n']}/{x['OOS_win']}%/{x['OOS_R']} (rnd {x['OOS_random_R']} b{x['OOS_beats_pct']})"
                      f" Rs {x['rs']:,} OOS Rs {x['rs_OOS']:,}", flush=True)
    (RN.REPORTS / "mcx_round7_pick.json").write_text(json.dumps(dict(picks=out, trades=trades), default=lambda v: None))


if __name__ == "__main__":
    main()
