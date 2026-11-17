"""ROUND 5 selection: every commodity's own strategy from rounds 4 + 5, chosen WITHOUT looking at OOS.
  1  candidates: TRAIN and VALID both positive, enough trades, >= 50 % of the other exits of the same entry also positive
  2  rank by robust score min(TRAIN_R*sqrt(n), VALID_R*sqrt(n)); take the top 8 distinct entries per commodity
  3  random check (same candle / side / filter condition / stop / target / signal rate, 200 draws) on TRAIN and VALID;
     the pick = best-scored candidate whose TRAIN and VALID both beat >= 80 % of random draws
  4  OOS (and OOS vs random) shown unchanged
Also: how each indicator family (trendline, divergence, Hull, DMO, breakouts) did pooled over the 7 commodities.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round5_pick -> reports/mcx_round5_pick.json"""
import json
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import data as D, runner as RN
from research.mcx_institutional_buy.stock_rules_on_mcx import round4 as R4, round5 as R5
from research.mcx_institutional_buy.stock_rules_on_mcx.round4_pick import score, neighbours, MIN, ENTRY

NAMES = {"TLB": "trendline breakout (whole candle)", "TLC": "trendline breakout (close)", "DIV1": "divergence (1+ indicators)",
         "DIV2": "divergence (2+ indicators)", "DIV3": "divergence (3+ indicators)", "HULL": "Hull trend cross",
         "DMOX": "DMO zero cross", "DMOR": "DMO oversold reversal", "BO10": "10-candle breakout", "BO20": "20-candle breakout",
         "BO55": "55-candle breakout", "MARU20": "strong-candle 20-candle breakout", "PMO": "previous-month high break",
         "PWK": "previous-week high break"}
SELLN = {"TLB": "trendline breakdown (whole candle)", "TLC": "trendline breakdown (close)", "BO10": "10-candle breakdown",
         "BO20": "20-candle breakdown", "BO55": "55-candle breakdown", "MARU20": "strong-candle 20-candle breakdown",
         "PMO": "previous-month low break", "PWK": "previous-week low break", "DMOR": "DMO overbought reversal"}
FILTN = {"VOL": "volume > 1.5x", "HT1": "higher-timeframe trend", "HT2": "2nd higher-timeframe trend", "HULLUP": "Hull trend",
         "DMOP": "DMO on our side", "DIVR": "recent divergence"}
TFN = {"3h": "3h", "4h": "4h", "1d": "Daily", "1w": "Weekly", "1M": "Monthly"}


def label(r):
    side = 1 if r["side"] == "BUY" else -1
    fam = (NAMES if side > 0 else {**NAMES, **SELLN})[r["fam"]]
    f = "" if r["filt"] == "none" else " · " + " + ".join(FILTN[x] for x in r["filt"].split("+"))
    ex = "trailing stop 3 ATR" if r["exit"].startswith("trail") else f"target {r['r']:g}R"
    return f"{TFN[r['tf']]} {fam} {r['side']}{f} · SL {r['k']:g} ATR · {ex}"


def main():
    L = pd.concat([pd.read_csv(RN.REPORTS / "mcx_round4.csv"), pd.read_csv(RN.REPORTS / "mcx_round5.csv")], ignore_index=True)
    L = L.drop_duplicates(["name"] + ENTRY + ["k", "r", "exit"])
    L["nb"] = neighbours(L, ["name"] + ENTRY); L["score"] = score(L)
    mn = L.tf.map(lambda t: MIN[t][0]); mv = L.tf.map(lambda t: MIN[t][1])
    C = L[(L.TRAIN_n >= mn) & (L.VAL_n >= mv) & (L.TRAIN_R > 0) & (L.VAL_R > 0) & (L.nb >= 0.5)].sort_values("score", ascending=False)

    # indicator family summary: share of (commodity, candle, side, filter, exit) cells positive in all 3 periods, pooled R
    fam = L.groupby("fam").apply(lambda g: pd.Series(dict(
        cells=len(g), all3_pos=round(100 * float(((g.TRAIN_R > 0) & (g.VAL_R > 0) & (g.OOS_R > 0)).mean()), 1),
        TRAIN_R=round(float(g.sum_TRAIN.sum() / max(g.TRAIN_n.sum(), 1)), 3), VAL_R=round(float(g.sum_VAL.sum() / max(g.VAL_n.sum(), 1)), 3),
        OOS_R=round(float(g.sum_OOS.sum() / max(g.OOS_n.sum(), 1)), 3)))).sort_values("all3_pos", ascending=False)
    print(fam.to_string())

    rng = np.random.default_rng(23); out = {"families": fam.reset_index().to_dict("records"), "commodities": {}}; trades = []
    cache = {}
    for name in D.INTRA:
        B = R4.build(name)
        cand = C[C.name == name].drop_duplicates(ENTRY).head(8)
        tried = []
        pick = None
        for _, r in cand.iterrows():
            side = 1 if r.side == "BUY" else -1
            key = (name, r.tf, side)
            if key not in cache:
                cache[key] = R5.parts(B[r.tf], side)
            P, cond, arr = cache[key]; d = B[r.tf]
            base = np.ones(len(arr["c"]), bool)
            for c_ in ([] if r.filt == "none" else r.filt.split("+")):
                base &= cond[c_]
            m = P[r.fam] & base
            kind = 2 if r.exit.startswith("trail") else 0
            si, ei, xi, g, nr, mfe, mae, why = R4.run(arr, d, m, side, r.k, r.r, kind, r.tf, name)
            pe = d["per"][ei]; st = R4.pstats(nr, pe)
            rate = m.sum() / max(base.sum(), 1); dr = {p: [] for p in ("TRAIN", "VAL", "OOS")}
            for _ in range(200):
                x = R4.run(arr, d, base & (rng.random(len(base)) < rate), side, r.k, r.r, kind, r.tf, name)
                xp = d["per"][x[1]]
                for p in dr:
                    y = x[4][xp == p]; dr[p].append(y.mean() if len(y) else np.nan)
            rec = dict(strategy=label(r), tf=r.tf, side=r.side, fam=r.fam, filt=r.filt, k=r.k, r=r.r, exit=r.exit, **st,
                       ALL_n=int(len(nr)), ALL_win=round(100 * float((nr > 0).mean()), 1), ALL_R=round(float(nr.mean()), 3))
            for p in dr:
                a = np.array(dr[p], float)
                rec[f"{p}_random_R"] = round(float(np.nanmean(a)), 3) if np.isfinite(a).any() else None
                rec[f"{p}_beats_pct"] = int(100 * np.nanmean(a < st[f"{p}_R"])) if (st[f"{p}_R"] == st[f"{p}_R"] and np.isfinite(a).any()) else None
            f = d["f"]; c = f["close"].values.astype(float); o = f["open"].values.astype(float); at = f["atr"].values.astype(float)
            fac = f["raw_close"].values / c; rk = side * (o[ei] - (c[si] - side * r.k * at[si])); rs = nr * rk * fac[ei] * R4.MULT[name]
            rec["rs"] = int(rs.sum())
            tried.append(rec)
            if pick is None and (rec["TRAIN_beats_pct"] or 0) >= 80 and (rec["VAL_beats_pct"] or 0) >= 80:
                pick = rec
                t = pd.to_datetime(f["time"])
                for i in range(len(nr)):
                    trades.append(dict(strategy=f"Round 5 · {name} own rule · {rec['strategy']}", commodity=name, side=r.side,
                                       entry=str(t.iloc[ei[i]])[:16], exit=str(t.iloc[xi[i]])[:16], entry_px=round(float(o[ei[i]] * fac[ei[i]]), 2),
                                       exit_px=round(float((o[ei[i]] + side * g[i] * rk[i]) * fac[ei[i]]), 2), R=round(float(nr[i]), 2),
                                       pnl_rs=int(round(rs[i])), best_rs=int(round(mfe[i] * rk[i] * fac[ei[i]] * R4.MULT[name])),
                                       worst_rs=int(round(mae[i] * rk[i] * fac[ei[i]] * R4.MULT[name])), period=str(pe[i]),
                                       result=R4.__dict__.get("REASON", {1: "stop-loss", 2: "target", 3: "time exit", 4: "contract roll", 5: "stop-loss"}).get(int(why[i]), "exit")))
        out["commodities"][name] = dict(pick=pick, tried=tried)
        if pick:
            print(f"\n{name}: PICK {pick['strategy']}\n   TRAIN {pick['TRAIN_n']} tr {pick['TRAIN_win']}% {pick['TRAIN_R']}R (rand {pick['TRAIN_random_R']}, beat {pick['TRAIN_beats_pct']}%)"
                  f" | VALID {pick['VAL_n']} tr {pick['VAL_win']}% {pick['VAL_R']}R (rand {pick['VAL_random_R']}, beat {pick['VAL_beats_pct']}%)"
                  f" | OOS {pick['OOS_n']} tr {pick['OOS_win']}% {pick['OOS_R']}R (rand {pick['OOS_random_R']}, beat {pick['OOS_beats_pct']}%) | Rs {pick['rs']:,}", flush=True)
        else:
            print(f"\n{name}: NO PICK (none of the top 8 beat random in both TRAIN and VALID)", flush=True)
        for x in tried:
            print(f"   - {x['strategy'][:95]:95s} T {x['TRAIN_R']:+.2f}/{x['TRAIN_beats_pct']}% V {x['VAL_R']:+.2f}/{x['VAL_beats_pct']}% O {x['OOS_R']}/{x['OOS_beats_pct']}% n={x['ALL_n']}")
    out["trades"] = trades
    (RN.REPORTS / "mcx_round5_pick.json").write_text(json.dumps(out, default=lambda v: None))


if __name__ == "__main__":
    main()
