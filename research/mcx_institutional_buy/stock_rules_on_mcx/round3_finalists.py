"""Round 3 finalists (chosen on TRAIN + VALID only): per commodity, Rs per lot, double costs, 100 random draws, trades.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.round3_finalists -> reports/mcx_round3_finalists.json"""
import json
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import data as D, runner as RN, sim as S
from research.mcx_institutional_buy.stock_rules_on_mcx import patterns as PT

FIN = [("3h", 1, ("MARU", "BO20", "DT", "E200"), 3.0, 0.75,
        "3h Strong candle breaks 20-candle high BUY · daily trend up · above EMA200 · SL 3 ATR · target 0.75R"),
       ("4h", 1, ("MARU", "VOL", "DT", "E200"), 2.0, 0.75,
        "4h Strong candle on high volume BUY · daily trend up · above EMA200 · SL 2 ATR · target 0.75R"),
       ("3h", 1, ("PIN", "VOL", "DT", "E200"), 3.0, 0.5,
        "3h Hammer on high volume BUY · daily trend up · above EMA200 · SL 3 ATR · target 0.5R")]
REASON = {1: "stop-loss", 2: "target", 3: "time exit", 4: "contract roll"}


def main():
    data = PT.load()
    for d in data.values():
        PT.NAN.setdefault(len(d["c"]), np.full(len(d["c"]), np.nan))
    rng = np.random.default_rng(3); out = []; trades = []
    for tf, side, sg, k, r, label in FIN:
        per_c = {}; nrs = []; pes = []; nr2s = []
        for n in D.INTRA:
            d = data[(n, tf, side)]; m = np.ones(len(d["c"]), bool)
            for x in sg:
                m &= d["P"][x]
            si, ei, xi, g, nr, mfe, mae, why, _ = S.simulate(d["o"], d["h"], d["l"], d["c"], d["a"], d["seg"], d["costf"], m,
                                                             d["c"] - k * d["a"], PT.NAN[len(d["c"])], PT.NAN[len(d["c"])], 0, float(r),
                                                             PT.MAXH, PT.MAXH, 3.0, 3, 0.25, 6.0, 1.5)
            d2 = dict(d, costf=d["costf"] * 2)                      # double fees + slippage
            nr2 = PT.sim(d2, m, k, r)[3]
            c_, a_ = d["c"], d["a"]
            rk = d["o"][ei] - (c_[si] - k * a_[si])
            rs = nr * rk * d["fac"][ei] * PT.MULT[n]
            per = d["per"][ei]
            per_c[n] = dict(trades=int(len(nr)), win=round(100 * float((nr > 0).mean()), 1) if len(nr) else None,
                            avg_R=round(float(nr.mean()), 3) if len(nr) else None, rs=int(rs.sum()),
                            OOS_R=round(float(nr[per == "OOS"].mean()), 3) if (per == "OOS").any() else None)
            nrs.append(nr); pes.append(per); nr2s.append(nr2)
            t = pd.to_datetime(d["time"])
            for i in range(len(nr)):
                f_ = d["fac"][ei[i]]; M_ = PT.MULT[n]
                trades.append(dict(strategy=label, commodity=n, side="BUY", entry=str(t[ei[i]])[:16], exit=str(t[xi[i]])[:16],
                                   entry_px=round(float(d["o"][ei[i]] * f_), 2), exit_px=round(float((d["o"][ei[i]] + g[i] * rk[i]) * f_), 2),
                                   R=round(float(nr[i]), 2), pnl_rs=int(round(rs[i])), best_rs=int(round(mfe[i] * rk[i] * f_ * M_)),
                                   worst_rs=int(round(mae[i] * rk[i] * f_ * M_)), period=str(per[i]), result=REASON.get(int(why[i]), "exit")))
        nr = np.concatenate(nrs); pe = np.concatenate(pes); nr2 = np.concatenate(nr2s)
        # random: same side, daily trend + EMA200 bars, same rate, same exit; 100 draws
        rate = {n: sum(1 for _ in [0]) for n in D.INTRA}
        dr = {p: [] for p in ("TRAIN", "VAL", "OOS")}
        for _ in range(100):
            rr, rp = [], []
            for n in D.INTRA:
                d = data[(n, tf, side)]; m = np.ones(len(d["c"]), bool)
                for x in sg:
                    m &= d["P"][x]
                base = d["P"]["DT"] & d["P"]["E200"]
                msk = base & (rng.random(len(base)) < m.sum() / max(base.sum(), 1))
                s_ = PT.sim(d, msk, k, r); rr.append(s_[3]); rp.append(d["per"][s_[1]])
            rr = np.concatenate(rr); rp = np.concatenate(rp)
            for p in dr:
                dr[p].append(rr[rp == p].mean())
        st = PT.stats(nr, pe)
        rec = dict(strategy=label, tf=tf, signal="+".join(sg), k=k, r=r, **st, ALL_n=int(len(nr)),
                   ALL_win=round(100 * float((nr > 0).mean()), 1), ALL_R=round(float(nr.mean()), 3),
                   ALL_R_double_costs=round(float(nr2.mean()), 3), per_commodity=per_c,
                   **{f"{p}_random_R": round(float(np.nanmean(v)), 3) for p, v in dr.items()},
                   **{f"{p}_beats_random_pct": int(100 * np.mean(np.array(v) < st[f"{p}_R"])) for p, v in dr.items()})
        out.append(rec)
        print(json.dumps(rec, indent=0)[:1600], flush=True)
    (RN.REPORTS / "mcx_round3_finalists.json").write_text(json.dumps(dict(finalists=out, trades=trades)))


if __name__ == "__main__":
    main()
