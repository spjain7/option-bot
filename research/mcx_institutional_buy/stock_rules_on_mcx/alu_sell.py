"""Aluminium weekly / monthly BREAKDOWN SELL with volume + indicator support (owner 17-Nov-2026). Daily data 2006-2026,
periods 2006-16 / 2017-21 / 2022-26. Breakdowns: 10 / 20-candle low, previous-month low (weekly), strong-candle breakdown.
Filters (any combination of up to 2): VOL (volume > 1.5x), MT (monthly trend down / 12-candle EMA for monthly), E (close below
20-candle EMA), RSI<45, MACD<0 (and falling), DMO<0, HULL (Hull trend down). Exits: SL 1.5 / 2 ATR x T 1R / 1.5R / 3R.
Also run on COPPER and ZINC (same base-metal family) as a robustness check. Research only.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.alu_sell"""
import itertools
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import runner as RN
from research.mcx_institutional_buy.stock_rules_on_mcx import round4 as R4, round5 as R5

R4.CMUL["1w"] = 2; R4.CMUL["1M"] = 3


def filters(d, side, arr):
    f = d["f"]; o, h, l, c = arr["o"], arr["h"], arr["l"], arr["c"]
    e20 = R5.ema(c, 20); r = R5.rsi(c, 14)
    m = R5.ema(c, 12) - R5.ema(c, 26)
    mom = c - np.r_[np.full(14, np.nan), c[:-14]]
    rg = pd.Series(h).rolling(14).max().values - pd.Series(l).rolling(14).min().values
    hl2 = (h + l) / 2
    a_ = R5.wma(2 * R5.wma(hl2, 12) - R5.wma(hl2, 24), 5); b_ = R5.wma(R5.wma(c, 4) * 3 - R5.wma(c, 6) - R5.wma(c, 12), 12)
    F = {"VOL": f["volx"].values > 1.5, "MT": d["ht"]["HT1"] == side, "E": c > e20, "RSI": r > 55,
         "MACD": (m > 0) & (m > np.r_[np.nan, m[:-1]]), "DMO": mom / rg > 0, "HULL": b_ > a_}
    return {k: np.nan_to_num(np.asarray(v, float)).astype(bool) for k, v in F.items()}


def main():
    rows = []
    for name in ("ALUMINIUM", "COPPER", "ZINC"):
        B = R4.build(name, ["1w", "1M"])
        for tf in ("1w", "1M"):
            d = B[tf]; side = -1
            P, cond, arr = R4.signals(d, side)
            F = filters(d, side, arr)
            trig = {k: P[k] for k in ("BO10", "BO20", "PMO", "MARU20") if k in P}
            combos = [()] + [(x,) for x in F] + list(itertools.combinations(F, 2))
            for tg, m0 in trig.items():
                for cb in combos:
                    m = m0.copy()
                    for x in cb:
                        m &= F[x]
                    if m.sum() < 5:
                        continue
                    for k, r in ((1.5, 1.0), (1.5, 1.5), (2.0, 1.0), (2.0, 1.5), (2.0, 3.0)):
                        si, ei, xi, g, nr, mfe, mae, why = R4.run(arr, d, m, side, k, r, 0, tf, name)
                        if len(nr) < 4:
                            continue
                        pe = d["per"][ei]; row = dict(name=name, tf=tf, trig=tg, filt="+".join(cb) or "none", k=k, r=r, n=len(nr),
                                                       win=round(100 * float((nr > 0).mean()), 1), R=round(float(nr.mean()), 3))
                        for p in ("TRAIN", "VAL", "OOS"):
                            x = nr[pe == p]; row[f"{p}_n"] = len(x); row[f"{p}_R"] = round(float(x.mean()), 3) if len(x) else None
                            row[f"{p}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else None
                        rows.append(row)
    L = pd.DataFrame(rows); L.to_csv(RN.REPORTS / "mcx_alu_sell.csv", index=False)
    A = L[(L.name == "ALUMINIUM")]
    q = A[(A.TRAIN_R > 0) & (A.VAL_R > 0) & (A.TRAIN_n >= 5) & (A.VAL_n >= 3)].copy()
    q["score"] = np.minimum(q.TRAIN_R * np.sqrt(q.TRAIN_n), q.VAL_R * np.sqrt(q.VAL_n))
    q = q.sort_values("score", ascending=False)
    # same rule on copper and zinc (robustness)
    key = ["tf", "trig", "filt", "k", "r"]
    other = L[L.name != "ALUMINIUM"].groupby(key).apply(lambda g: pd.Series(dict(other_n=g.n.sum(), other_R=round(float((g.R * g.n).sum() / g.n.sum()), 3)))).reset_index()
    q = q.merge(other, on=key, how="left")
    pd.set_option("display.width", 250)
    print("ALUMINIUM SELL candidates (TRAIN and VALID positive):", len(q), "of", len(A))
    print(q.head(15)[key + ["n", "win", "R", "TRAIN_n", "TRAIN_R", "VAL_n", "VAL_R", "OOS_n", "OOS_win", "OOS_R", "other_n", "other_R"]].to_string(index=False))
    base = A[(A.filt == "none")]
    print("\nno filter:"); print(base[key + ["n", "win", "R", "OOS_n", "OOS_R"]].to_string(index=False))


if __name__ == "__main__":
    main()
