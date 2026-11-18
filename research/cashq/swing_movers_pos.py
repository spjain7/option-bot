"""Follow-up (18-Nov): the swing_movers setups with the LIVE cash positional exit (stop 3 ATR, exit on a close below EMA50 at
the next open, max 250 sessions, delivery costs 0.393 %) – which setups add calls without hurting the result.
python -m research.cashq.swing_movers_pos -> results/swing_movers_pos.csv"""
import gc
import numpy as np
import pandas as pd
from research.cashq import swing_movers as SM
from research.cashq import data as D
from research.cashq.daily_run import features, first_in


def main():
    W = D.daily_panel(); F = features(W); del W; gc.collect()
    o, h, l, c, v = (F[x] for x in ("open", "high", "low", "close", "volume")); e = F["elig"].fillna(False)
    pc = c.shift(1); ret = c / pc - 1; rng = h - l; clv = (c - l) / rng.replace(0, np.nan); vx = v / v.rolling(20).mean().shift(1)
    S = {"MOMBURST": (ret >= 0.04) & (v > v.shift(1)) & (vx >= 1.5) & (clv >= 0.7) & (pc / c.shift(6) - 1 < 0.08) & (c > F["ema50"]),
         "VOLBO20": first_in(F["hi20"], 5) & (vx >= 2), "HI52VOL": first_in(F["hi252"] & (vx >= 1.5), 20),
         "TIGHTBO": (F["atr10_50"].shift(1) <= 0.8) & F["hi20"] & (vx >= 1.5), "GAPGO": (o >= pc * 1.03) & (c >= o) & (clv >= 0.6) & (vx >= 2)}
    import sys
    sys.path.insert(0, str(SM.ROOT.parent / "ob-main")); from cashstock import breakout as B
    BF = B.features(dict(open=o, high=h, low=l, close=c, volume=v, symbol=pd.Series(dict(zip(c.columns, c.columns)))))
    rsr, adx, tight, clv2, br = BF["rs126"], BF["adx"], BF["tight"], BF["clv"], BF["breadth50"]
    sc = (np.where(rsr >= .85, 35, np.where(rsr >= .70, 22, np.where(rsr >= .50, 10, 0))) + np.where(adx >= 30, 25, np.where(adx >= 22, 15, np.where(adx >= 16, 6, 0)))
          + np.where(tight <= .85, 20, np.where(tight <= 1.0, 10, 0)) + np.where(clv2 < .85, 10, 0)
          + np.where(br.values[:, None] >= .55, 10, np.where(br.values[:, None] >= .40, 5, 0)))
    sc = pd.DataFrame(sc, index=c.index, columns=c.columns)
    for th in (40, 50, 60, 70, 80):
        S[f"BO50 score>={th}"] = BF["signal"] & (sc >= th)
    for nm in ("MOMBURST", "VOLBO20", "TIGHTBO"):
        S[f"{nm} score>=60"] = S[nm] & (sc >= 60)
    S["MOMBURST RS>=.85"] = S["MOMBURST"] & (rsr >= .85)
    del BF; gc.collect()
    days = c.index; O, H, L, C, A, EM = (x.values for x in (o, h, l, c, F["atr"], F["ema50"])); E = e.values
    rows = []
    for sn, s0 in S.items():
        M = (s0 & e).fillna(False).values; res = []
        for j in np.where(M.any(0))[0]:
            rk = 3.0 * A[:, j]
            ei, xi, g, ep = SM.sim(O[:, j], H[:, j], L[:, j], C[:, j], M[:, j], rk, 2, 0.0, 250, EM[:, j])
            if len(ei):
                net = g - SM.COST * ep / rk[ei - 1]
                pct = net * rk[ei - 1] / ep * 100
                res.append(np.c_[ei, net, pct, xi - ei])
        X = np.vstack(res); ed = days[X[:, 0].astype(int)]; p = SM.per(ed); nr = X[:, 1]
        row = dict(setup=sn, trades=len(nr), per_month_2025_26=round(float((ed >= "2025-01-01").sum() / 22.5), 1), win=round(100 * float((nr > 0).mean()), 1),
                   R=round(float(nr.mean()), 3), avg_pct=round(float(X[:, 2].mean()), 2), med_hold=int(np.median(X[:, 3])),
                   big_win_pct=round(100 * float((X[:, 2] >= 15).mean()), 1))
        for pp in ("DEV", "VALID", "OOS"):
            x = nr[p == pp]; row[f"{pp}_n"] = len(x); row[f"{pp}_R"] = round(float(x.mean()), 3) if len(x) else None
        for y in (2024, 2025, 2026):
            x = nr[ed.year == y]; row[f"y{y}_n"] = len(x); row[f"y{y}_R"] = round(float(x.mean()), 3) if len(x) else None
        rows.append(row); print(sn, row["trades"], flush=True)
    L_ = pd.DataFrame(rows); L_.to_csv(SM.OUT / "swing_movers_pos.csv", index=False)
    pd.set_option("display.width", 260); print(L_.to_string(index=False))


if __name__ == "__main__":
    main()
