"""IDX-BASKET-001 (19-Nov-2026): the cluster that passed IDX-SEARCH-001 – NIFTY / BANKNIFTY SELL when an overbought
oscillator turns down on 3-hour / 4-hour candles (no trend filter). Members (SELL-side wording):
  LAG   Laguerre RSI (0.5) crosses below 0.8          CCI   CCI(20) crosses below +100       WPR   Williams %R crosses below -20
  SQZ   Squeeze momentum turns down above zero         SSL   SSL channel (10) turns down       SFP   swing failure above a 20-candle high
Basket = any member, one open call per instrument (first signal wins), exits 1.5x1.5, 1.5x2, 2x1, 2x2 ATR/R.
Reported per year, per instrument, per timeframe, and per member, plus the RANDOM-SELL benchmark.
python research/program/idx_basket.py -> results/idx_basket_trades.parquet"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.sell_exits import run  # noqa: E402
from research.program.rev_ind import tops, mirror  # noqa: E402
from research.program.tv_scripts import signals as tv_sell  # noqa: E402
from research.program.tv_buy import bottoms  # noqa: E402

OUT = ROOT / "research/program/results"
EXITS = [(1.5, 1.5), (1.5, 2.0), (2.0, 1.0), (2.0, 2.0)]


def members(C):
    B = bottoms(mirror(C))                       # bottom scripts on mirrored candles = top scripts on C
    T = tops(C); V = tv_sell(C, False)
    return {"LAG": B["Laguerre RSI cross above 0.2 (Ehlers)"].values, "CCI": B["CCI(20) cross above -100"].values,
            "WPR": B["Williams %R cross above -80"].values, "SQZ": B["Squeeze Momentum turns up below zero (LazyBear)"].values,
            "SSL": np.asarray(V["TV SSL channel turns down (10)"], bool), "SFP": T["SFP"].values}


def main():
    rows = []
    for name in ("NIFTY", "BANKNIFTY"):
        job = [j for j in EX.jobs() if j[0] == "mi" and j[1] == name][0]
        seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in EX.frames(job)}
        k1 = [s for s in seg if s.endswith("1h")][0]; f1, c1 = seg[k1]
        c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(c1)), c1) if len(c1) != len(f1) else c1
        frames = {"3h": seg[[s for s in seg if s.endswith("3h")][0]]}
        f1s = f1.copy(); f1s["switch"] = f1s.get("switch", False)
        C4, first = anchored(f1s, 4); frames["4h"] = (C4, c1[first[:len(C4)]])
        rng = np.random.default_rng(sum(map(ord, name)))
        for tf, (C, cost) in frames.items():
            cost = np.asarray(cost, float)
            if len(cost) != len(C):
                cost = np.interp(np.arange(len(C)), np.linspace(0, len(C) - 1, len(cost)), cost)
            f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
            o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
            sw = f["switch"].values.astype(np.bool_); tt = pd.to_datetime(C["time"])
            M = members(C)
            basket = np.zeros(len(C), bool)
            for v in M.values():
                basket |= v
            sets = dict(M); sets["BASKET"] = basket; sets["RANDOM"] = rng.random(len(C)) < 0.05
            for nm, s in sets.items():
                for k, r in EXITS:
                    for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, s, k, r, SV.MAXH.get(tf, 40), cost, 0.0, 0.0, 0.0, H.CHASE):
                        fired = ",".join(m for m, v in M.items() if v[i]) if nm == "BASKET" else nm
                        rows.append(dict(set=nm, name=name, tf=tf, exit=f"{k:g}x{r:g}", t=tt.iat[i], t_out=tt.iat[j], R=rr, why=int(why), fired=fired,
                                         entry=o[i + 1], sl=o[i + 1] + k * at[i], tgt=o[i + 1] - r * k * at[i],
                                         hi=h[i + 1:j + 1].max(), lo=l[i + 1:j + 1].min()))
    T = pd.DataFrame(rows)
    T["year"] = pd.to_datetime(T.t).dt.year
    T["period"] = np.where(T.t < SV.P1, "2022-24", np.where(T.t < SV.P2, "2024-25", "2025-26"))
    T.to_parquet(OUT / "idx_basket_trades.parquet")
    st = lambda g: pd.Series(dict(n=len(g), win=round(100 * (g.R > 0).mean(), 1), sl=round(100 * (g.why == 1).mean(), 1), R=round(g.R.mean(), 3)))
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 300)
    B = T[T.set.isin(["BASKET", "RANDOM"])]
    print(B.groupby(["set", "exit", "period"]).apply(st).unstack("period").to_string())
    print(T[T.set == "BASKET"].groupby(["exit", "name", "tf"]).apply(st).to_string())
    print(T[(T.set == "BASKET")].groupby(["exit", "year"]).apply(st).unstack("year").to_string())
    print(T[~T.set.isin(["BASKET", "RANDOM"]) & (T.exit == "1.5x2")].groupby(["set", "period"]).apply(st).unstack("period").to_string())


if __name__ == "__main__":
    main()
