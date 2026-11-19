"""CASHQ-W – weekly-timeframe positional BUY tests (bars = weeks ending on the last session of the week; signal at the
week's close, entry next week's first open, stop 2 weekly ATR, exits 2R / 3R / weekly-EMA10 trail, max 26 weeks).
python -m research.cashq.weekly_run"""
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from . import data as D, ind as I, div as DV, engine as EN, validate as V
from .daily_run import summarise, first_in

OUT = Path(__file__).resolve().parent / "results"


def main():
    t0 = time.time()
    W = D.daily_panel()
    Wk = D.weekly(W)
    o, h, l, c, v = (Wk[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
    e = Wk["elig"]
    F = dict(open=o, high=h, low=l, close=c, atr=I.atr(h, l, c, 14))
    ema10, ema40 = I.ema(c, 10), I.ema(c, 40)
    r14 = I.rsi(c, 14)
    up = ema10 > ema40
    S = {
        "W1_donchian10_trend": first_in(c > h.shift(1).rolling(10).max(), 4) & up,
        "W2_RSI14x40_uptrend": (r14 > 40) & (r14.shift(1) <= 40) & up & (c > ema40),
        "W3_RSI14x30": (r14 > 30) & (r14.shift(1) <= 30),
        "W4_base26_BO_vol": (h.shift(1).rolling(26).max() / l.shift(1).rolling(26).min() - 1 < 0.35) & (c > h.shift(1).rolling(26).max()) & (I.rvol(v, 10) >= 1.5),
        "W5_pullback_EMA10": up & (l <= ema10) & (c > ema10) & (I.clv(h, l, c) >= 0.6),
    }
    D_ = pd.DataFrame(False, index=c.index, columns=c.columns)
    rs = r14.values
    for j, k in enumerate(c.columns):
        if c[k].notna().sum() < 80:
            continue
        D_[k] = DV.divergence(h[k].values, l[k].values, c[k].values, r14[k].values.astype(float), 1, False, 2, 26, 6)[0]
    S["W6_RSIdiv_struct"] = D_
    rows, led = [], []
    for nm, sig in S.items():
        sig = sig.fillna(False).astype(bool) & e
        for R, trail in ((2.0, None), (3.0, None), (0.0, ema10)):
            T = EN.daily_trades(F, sig, 2.0 * F["atr"], 1, R, 26, trail=trail)
            if not len(T):
                continue
            T["strategy"], T["R"] = nm, R
            rows.append(summarise(nm, "POSITIONAL", T, dict(params=f"weekly bars, stop 2 weekly ATR, {'target ' + format(R, 'g') + 'R' if R else 'trail weekly EMA10'}, max 26 weeks",
                                                             R=R, hold="weekly", side="LONG", tf="1w")))
            led.append(T)
    L = pd.DataFrame(rows)
    sel = L.apply(V.verdict, axis=1, min_oos=100) != "NOT_SELECTED"
    L["OOS_q"] = 1.0
    L.loc[sel, "OOS_q"] = V.bh(L.loc[sel, "OOS_p"].fillna(1).values)
    L["status"] = L.apply(V.verdict, axis=1)
    L["exp_id"] = L["exp_id"].str.replace("CQD-", "CQW-")
    L.to_csv(OUT / "weekly_leaderboard.csv", index=False)
    pd.concat(led, ignore_index=True).assign(symbol=lambda x: x["key"].map(W["symbol"])).to_csv(OUT / "weekly_trades.csv.gz", index=False)
    json.dump(dict(variants=len(L), trades=int(sum(len(x) for x in led)), seconds=round(time.time() - t0)), open(OUT / "weekly_run.json", "w"))
    print(L["status"].value_counts().to_dict())


if __name__ == "__main__":
    main()
