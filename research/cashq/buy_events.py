"""CASHQ-BUY stage 1 – positional BUY candidate events with point-in-time features and realised outcomes.
Candidate (discovery): first close above the 50-session high in 5 sessions, in the point-in-time liquid universe.
Trade (same as the PASS benchmarks F1 / F2): entry next session's open, stop 3 x ATR(14), exit on a close below EMA50
(next open) or after 250 sessions, delivery costs 0.393 %. One position per stock at a time.
Features (all known at the signal day's close):
  market   mkt_on (EW top-100 index > its 100-session average), breadth50 (share of eligible stocks above their EMA50),
           nhnl (252-day new highs minus new lows, share of eligible), mkt_vol_hi
  rs       rs126 (percentile of 126-day return), rs_acc (change of that percentile over 21 sessions), rs63
  trend    above200 (close / EMA200 − 1), ema_stack (EMA20 > EMA50 > EMA200), adx, hi252 (also a 252-day closing high),
           from_low (close / 252-day low − 1)  -> early vs extended
  base     tight (ATR10 / ATR50 before the breakout), range40 (40-session range before), ext50 (close / EMA50 − 1),
           ext_atr ((close − prior 50-day high) / ATR)
  volume   rvol, udvol (up-day / down-day volume, 50 sessions), obv_hi (OBV at a 50-session high), cmf
  entry    clv (close position in the day's range), day_ret
  risk     stop_pct (3 ATR / close), turnover (60-session median, ₹ cr)
Outcomes: netR, net %, bars held, T1 (+1R) and T2 (+2R) reached while the trade was open, exit code.
python -m research.cashq.buy_events -> results/buy_events.csv.gz"""
import gc
from pathlib import Path
import numpy as np
import pandas as pd
from . import data as D, ind as I, engine as EN
from .daily_run import features, first_in

OUT = Path(__file__).resolve().parent / "results"


def market_features(F):
    e = F["elig"]
    n = e.sum(axis=1).replace(0, np.nan)
    c = F["close"]
    out = pd.DataFrame(index=c.index)
    out["mkt_on"] = F["mkt_on"].astype(float)
    out["mkt_vol_hi"] = F["mkt_vol_hi"].astype(float)
    out["breadth50"] = ((c > F["ema50"]) & e).sum(axis=1) / n
    hi = (c >= c.rolling(252, min_periods=240).max()) & e
    lo = (c <= c.rolling(252, min_periods=240).min()) & e
    out["nhnl"] = (hi.sum(axis=1) - lo.sum(axis=1)) / n
    out["n_elig"] = n
    return out


def stock_features(F):
    c, h, l, v = F["close"], F["high"], F["low"], F["volume"]
    e = F["elig"]
    X = {}
    X["rs126"] = F["rs_rank"]
    X["rs_acc"] = F["rs_rank"] - F["rs_rank"].shift(21)
    X["rs63"] = (c / c.shift(63) - 1).where(e).rank(axis=1, pct=True)
    X["above200"] = c / F["ema200"] - 1
    X["ema_stack"] = ((F["ema20"] > F["ema50"]) & (F["ema50"] > F["ema200"])).astype(float)
    X["adx"] = F["adx"]
    X["hi252"] = F["hi252"].astype(float)
    X["from_low"] = c / l.rolling(252, min_periods=200).min() - 1
    X["tight"] = F["atr10_50"].shift(1)
    X["range40"] = h.shift(1).rolling(40).max() / l.shift(1).rolling(40).min() - 1
    X["ext50"] = c / F["ema50"] - 1
    X["ext_atr"] = (c - h.shift(1).rolling(50).max()) / F["atr"]
    X["rvol"] = F["rvol"]
    up = v.where(c > c.shift(1), 0.0).rolling(50).sum()
    dn = v.where(c < c.shift(1), 0.0).rolling(50).sum()
    X["udvol"] = up / dn.replace(0, np.nan)
    X["obv_hi"] = (F["obv"] >= F["obv"].rolling(50).max()).astype(float)
    X["cmf"] = F["cmf"]
    X["clv"] = F["clv"]
    X["day_ret"] = c / c.shift(1) - 1
    X["stop_pct"] = 3 * F["atr"] / c
    return X


def main():
    W = D.daily_panel()
    F = features(W)
    sym = W["symbol"]
    turn = (W["value"].rolling(60, min_periods=40).median().shift(1) / 1e7)
    W.clear(); gc.collect()
    sig = (first_in(F["hi50"], 5)).fillna(False).astype(bool) & F["elig"]
    T = EN.daily_trades(F, sig, 3.0 * F["atr"], 1, 0.0, 250, trail=F["ema50"])
    idx = F["close"].index
    pos = idx.get_indexer(T["entry_time"])
    T["signal_time"] = idx[pos - 1]
    M = market_features(F)
    for k in M.columns:
        T[k] = M[k].reindex(T["signal_time"]).values
    X = stock_features(F)
    X["turnover_cr"] = turn
    cols = {k: i for i, k in enumerate(F["close"].columns)}
    ci = T["key"].map(cols).values
    for k, df in X.items():
        T[k] = df.values[pos - 1, ci]
    # T1 / T2 reached while open (exit day excluded when the exit was the stop)
    H = F["high"].values
    xpos = idx.get_indexer(T["exit_time"])
    t1 = np.zeros(len(T), bool); t2 = np.zeros(len(T), bool)
    ent, rk, code = T["entry"].values, T["risk"].values, T["code"].values
    for i in range(len(T)):
        a, b = pos[i], xpos[i] + (0 if code[i] == 1 else 1)
        if b > a:
            mx = np.nanmax(H[a:b, ci[i]])
            t1[i] = mx >= ent[i] + rk[i]; t2[i] = mx >= ent[i] + 2 * rk[i]
    T["T1"], T["T2"] = t1, t2
    T["symbol"] = T["key"].map(sym)
    T.to_csv(OUT / "buy_events.csv.gz", index=False)
    print(len(T), T["entry_time"].min().date(), T["entry_time"].max().date(), "avg netR", round(T["netR"].mean(), 3))


if __name__ == "__main__":
    main()
