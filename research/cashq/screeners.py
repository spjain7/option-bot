"""CASHQ-SCR – popular Chartink / TradingView style screeners ported and tested on NSE cash daily data (owner 10-Nov:
"check Chartink / TradingView – does any filter or screener help?"). BUY side, point-in-time liquid universe, entry next
open, delivery costs 0.393 %, DEV 2005-14 / VALID 2015-19 / OOS 2020-26 (same gate as the other CASHQ runs).
Scans (rules as published; sources in BUY_ENGINE.md):
  S1 Connors RSI(2)      RSI2 < 10, close > SMA200, close < previous close · exit RSI2 > 70 (native) · stop 3 ATR
  S2 Turtle Soup         low < yesterday's low, yesterday's low <= 20-day low (2 days ago), close > yesterday's low · exit 5 bars
  S3 Pocket pivot        up day, volume > every down-day volume of the last 10 sessions, close > EMA50 > EMA200, within 5 % of EMA10
  S4 Bollinger squeeze   bandwidth(20,2) at a 120-session low (yesterday), close > upper band
  S5 VCP (Kell, simple)  5-day high < its value 20 days ago, 5-day low > its value 20 days ago (yesterday), close > 10-day high, vol > 1.5x
  S6 Minervini template  close > SMA50 > SMA150 > SMA200, SMA200 rising 21 sessions, close >= 1.3 x 52-week low, close >= 0.75 x
                         52-week high, RS percentile >= 70 – tested (a) as a signal on the day it first becomes true, (b) + 50-day
                         breakout, (c) as a FILTER on the scored breakout calls
  S7 TradingView style   "strong technicals + relative volume": close > SMA20 > SMA50 > SMA200, RSI14 55-70, ADX > 25, RVOL >= 2
  S8 Strict (>= 2 scans true on the same candle among S1-S5, S7)
Exits tested per scan: native where one exists, 2R/20 sessions (stop 1.5 ATR), and EMA50 trail (stop 3 ATR).
python -m research.cashq.screeners"""
import gc
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from . import data as D, ind as I, engine as EN, validate as V
from .daily_run import summarise, first_in

OUT = Path(__file__).resolve().parent / "results"


def main():
    t0 = time.time()
    W = D.daily_panel()
    o, h, l, c, v = (W[x].astype("float64") for x in ("open", "high", "low", "close", "volume"))
    e = W["elig"]; sym = W["symbol"]
    W.clear(); gc.collect()
    sma = lambda n: c.rolling(n, min_periods=n).mean()
    s20, s50, s150, s200 = sma(20), sma(50), sma(150), sma(200)
    e10, e50, e200 = I.ema(c, 10), I.ema(c, 50), I.ema(c, 200)
    atr = I.atr(h, l, c, 14)
    rsi2, rsi14, adx = I.rsi(c, 2), I.rsi(c, 14), I.adx(h, l, c, 14)
    rvol50 = v / v.rolling(50, min_periods=25).mean().shift(1)
    rvol20 = I.rvol(v, 20)
    F = dict(open=o, high=h, low=l, close=c, atr=atr)
    S = {}
    S["S1_connors_rsi2"] = (rsi2 < 10) & (c > s200) & (c < c.shift(1))
    S["S2_turtle_soup"] = (l < l.shift(1)) & (l.shift(1) <= l.shift(2).rolling(20).min()) & (c > l.shift(1))
    dnv = v.where(c < c.shift(1), 0.0)
    S["S3_pocket_pivot"] = (c > c.shift(1)) & (v > dnv.shift(1).rolling(10).max()) & (c > e50) & (e50 > e200) & (c / e10 - 1 < 0.05)
    sd = c.rolling(20).std(ddof=0)
    bw = 4 * sd / s20
    S["S4_bb_squeeze"] = (bw.shift(1) <= bw.shift(1).rolling(120, min_periods=100).min()) & (c > s20 + 2 * sd)
    hh5, ll5 = h.rolling(5).max(), l.rolling(5).min()
    S["S5_vcp_kell"] = (hh5.shift(1) < hh5.shift(21)) & (ll5.shift(1) > ll5.shift(21)) & (c > h.shift(1).rolling(10).max()) & (rvol50 >= 1.5)
    rs = (c / c.shift(126) - 1).where(e).rank(axis=1, pct=True)
    tt = ((c > s50) & (s50 > s150) & (s150 > s200) & (s200 > s200.shift(21)) & (c >= 1.3 * l.rolling(252, min_periods=200).min())
          & (c >= 0.75 * h.rolling(252, min_periods=200).max()) & (rs >= 0.70))
    S["S6a_minervini_first"] = first_in(tt, 20)
    bo50 = first_in(c > h.shift(1).rolling(50).max(), 5)
    S["S6b_minervini_bo50"] = tt & bo50
    S["S7_tv_strong_rvol"] = (c > s20) & (s20 > s50) & (s50 > s200) & (rsi14 >= 55) & (rsi14 <= 70) & (adx > 25) & (rvol20 >= 2)
    flags = sum(S[k].fillna(False).astype(int) for k in ("S1_connors_rsi2", "S2_turtle_soup", "S3_pocket_pivot", "S4_bb_squeeze", "S5_vcp_kell", "S7_tv_strong_rvol"))
    S["S8_strict_2of6"] = flags >= 2
    nan = pd.DataFrame(np.nan, index=c.index, columns=c.columns)
    native = {"S1_connors_rsi2": dict(k=3.0, R=0.0, mb=15, trail=nan.where(~(rsi2 > 70), np.inf)),
              "S2_turtle_soup": dict(k=1.0, R=0.0, mb=5, trail=None)}
    rows, led = [], []
    for nm, sig in S.items():
        sig = sig.fillna(False).astype(bool) & e
        exits = [("2R_20d", dict(k=1.5, R=2.0, mb=20, trail=None)), ("trail50", dict(k=3.0, R=0.0, mb=250, trail=e50))]
        if nm in native:
            exits.insert(0, ("native", native[nm]))
        for xn, x in exits:
            T = EN.daily_trades(F, sig, x["k"] * atr, 1, x["R"], x["mb"], trail=x["trail"])
            if not len(T):
                continue
            T["strategy"], T["R"] = f"{nm}_{xn}", x["R"]
            rows.append(summarise(f"{nm}_{xn}", "SCREENER", T, dict(params=f"{nm}, exit {xn}", R=x["R"], hold=xn, side="LONG")))
            led.append(T)
        print(f"  {nm} ({time.time() - t0:.0f}s)", flush=True)
    L = pd.DataFrame(rows)
    L["exp_id"] = "CQS-" + L["strategy"]
    sel = L.apply(V.verdict, axis=1) != "NOT_SELECTED"
    L["OOS_q"] = 1.0
    L.loc[sel, "OOS_q"] = V.bh(L.loc[sel, "OOS_p"].fillna(1).values)
    L["status"] = L.apply(V.verdict, axis=1)
    L.to_csv(OUT / "screeners_leaderboard.csv", index=False)
    pd.concat(led, ignore_index=True).assign(symbol=lambda x: x["key"].map(sym)).to_csv(OUT / "screeners_trades.csv.gz", index=False)
    # (c) as filters on the scored 50-day breakout calls
    ev = pd.read_csv(OUT / "buy_events_scored.csv.gz", parse_dates=["signal_time", "entry_time"])
    pos = c.index.get_indexer(ev["signal_time"]); ci = c.columns.get_indexer(ev["key"])
    ev["minervini"] = tt.values[pos, ci]
    ev["pocket10"] = S["S3_pocket_pivot"].fillna(False).rolling(10, min_periods=1).max().values[pos, ci].astype(bool)
    ev["squeeze"] = (bw.shift(1) <= bw.shift(1).rolling(120, min_periods=100).min()).rolling(10, min_periods=1).max().values[pos, ci].astype(bool)
    ev["rvol50"] = rvol50.values[pos, ci]
    ev = ev[~ev["open_trade"]]
    out = []
    for lab, (a, b) in V.DAILY_SPLITS.items():
        d = ev[(ev.entry_time >= a) & (ev.entry_time <= b)]
        for f in ("minervini", "pocket10", "squeeze"):
            for val, g in d.groupby(f):
                out.append(dict(period=lab, filter=f, value=bool(val), n=len(g), win=round(100 * (g.netR > 0).mean(), 1), avgR=round(g.netR.mean(), 3)))
        for nm, g in (("score>=70 & minervini", d[(d.score >= 70) & d.minervini]), ("score>=70 only", d[d.score >= 70]),
                      ("score>=55 & minervini & rvol50>=1.5", d[(d.score >= 55) & d.minervini & (d.rvol50 >= 1.5)])):
            out.append(dict(period=lab, filter=nm, value=True, n=len(g), win=round(100 * (g.netR > 0).mean(), 1), avgR=round(g.netR.mean(), 3)))
    pd.DataFrame(out).to_csv(OUT / "screeners_as_filters.csv", index=False)
    json.dump(dict(variants=len(L), seconds=round(time.time() - t0)), open(OUT / "screeners_run.json", "w"))
    c_ = ["strategy", "status", "DEV_n", "DEV_avgR", "VALID_n", "VALID_avgR", "OOS_n", "OOS_win", "OOS_avgR", "OOS_PF", "OOS_lo95", "years_pos"]
    print(L[c_].to_string(index=False)); print(pd.DataFrame(out).to_string(index=False))


if __name__ == "__main__":
    main()
