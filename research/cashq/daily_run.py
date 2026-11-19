"""CASHQ-D – daily / weekly positional experiments (BUY only: cash delivery cannot be shorted overnight; intraday shorts
are in intra_run). Every variant is pre-registered below; nothing is added after looking at the OOS.
python -m research.cashq.daily_run   -> research/cashq/results/{daily_leaderboard.csv, daily_trades.csv.gz, ...}"""
import json
import pickle
import time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from . import data as D, ind as I, div as DV, engine as EN, validate as V

OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)
RS_SWING = (0.5, 1.0, 1.5, 2.0, 3.0)


def features(W):
    P = {f: W[f].astype("float64") for f in ("open", "high", "low", "close", "volume")}
    o, h, l, c, v = P["open"], P["high"], P["low"], P["close"], P["volume"]
    F = dict(P)
    F["elig"] = W["elig"]
    F["atr"] = I.atr(h, l, c, 14)
    F["rsi14"], F["rsi5"], F["rsi2"], F["rsi3"] = I.rsi(c, 14), I.rsi(c, 5), I.rsi(c, 2), I.rsi(c, 3)
    F["adx"] = I.adx(h, l, c, 14)
    F["ema20"], F["ema50"], F["ema200"] = I.ema(c, 20), I.ema(c, 50), I.ema(c, 200)
    F["rvol"] = I.rvol(v, 20)
    F["clv"] = I.clv(h, l, c)
    F["hammer"], F["engulf"] = I.hammer(o, h, l, c), I.bull_engulf(o, h, l, c)
    F["hi20"], F["hi50"], F["hi55"] = (c > h.shift(1).rolling(n).max() for n in (20, 50, 55))
    F["lo20p"] = l.shift(1).rolling(20).min()
    F["hi252"] = c >= c.rolling(252, min_periods=240).max()
    F["r126"] = (c / c.shift(126) - 1).where(F["elig"])
    F["rs_rank"] = F["r126"].rank(axis=1, pct=True)
    F["obv"] = I.obv(c, v)
    F["cmf"] = I.cmf(h, l, c, v, 20)
    F["vol10_50"] = v.rolling(10).mean() / v.rolling(50).mean()
    F["atr10_50"] = I.atr(h, l, c, 10) / I.atr(h, l, c, 50)
    mk = W["market"]["close"]
    F["mkt_on"] = (mk > mk.rolling(100).mean()).reindex(c.index).fillna(False)
    F["mkt_w"] = pd.DataFrame(np.repeat(F["mkt_on"].values[:, None], c.shape[1], 1), index=c.index, columns=c.columns)  # row-wise (not column-aligned)
    mret = mk.pct_change()
    F["mkt_vol_hi"] = (mret.rolling(20).std() > mret.rolling(20).std().rolling(500, min_periods=100).median()).reindex(c.index).fillna(False)
    F["wk_hi_prev"] = _prev_week_high(h)
    return F


def _prev_week_high(h):
    g = h.index.to_period("W-FRI")
    wk = h.groupby(g).max()
    prev = wk.shift(1)
    return prev.reindex(g).set_axis(h.index)


def first_in(x, n):
    return x & ~x.shift(1).rolling(n, min_periods=1).max().fillna(0).astype(bool)


def div_signals(F, name, hidden=False):
    grp, fn = I.OSC[name]
    o, h, l, c, v = (F[x] for x in ("open", "high", "low", "close", "volume"))
    osc = fn(o, h, l, c, v)
    S = pd.DataFrame(False, index=c.index, columns=c.columns)
    LV = pd.DataFrame(np.nan, index=c.index, columns=c.columns)
    for k in c.columns:
        hk, lk, ck = h[k].values, l[k].values, c[k].values
        m = ~np.isnan(ck)
        if m.sum() < 300:
            continue
        s, lv = DV.divergence(np.nan_to_num(hk, nan=np.nan), lk, ck, osc[k].values.astype(float), 1, hidden, 3, 40, 10)
        S[k] = s
    return S


def signals(F):
    e = F["elig"]
    c, o, h, l = F["close"], F["open"], F["high"], F["low"]
    up = c > F["ema200"]
    rx = lambda r, lv: (r > lv) & (r.shift(1) <= lv)
    S = {}
    # A – RSI / reversal
    S["A1_RSI14x25"] = rx(F["rsi14"], 25)
    S["A2_RSI14x30"] = rx(F["rsi14"], 30)
    S["A3_RSI5x20"] = rx(F["rsi5"], 20)
    S["A4_RSI2x10_up"] = rx(F["rsi2"], 10) & up
    S["A5_RSI14_below25_3d_x"] = rx(F["rsi14"], 25) & (F["rsi14"].shift(1).rolling(3).max() < 25)
    S["A6_RSI14x30_candle"] = rx(F["rsi14"], 30) & (F["hammer"] | F["engulf"] | (F["clv"] >= 0.7))
    S["A7_RSI14x30_rvol_break"] = rx(F["rsi14"], 30) & (F["rvol"] >= 1.5) & (c > h.shift(1).rolling(3).max())
    S["A8_RSI14x30_range"] = rx(F["rsi14"], 30) & (F["adx"] < 20)
    S["A9_RSI14x40_trend"] = rx(F["rsi14"], 40) & (F["adx"] > 25) & up & (F["ema50"] > F["ema200"])
    S["A10_RSI14x70_mom"] = rx(F["rsi14"], 70) & (F["adx"] > 20) & up
    # C – volume / participation
    S["C1_BO20_rvol2"] = first_in(F["hi20"], 5) & (F["rvol"] >= 2)
    S["C2_BO20_novol"] = first_in(F["hi20"], 5) & (F["rvol"] < 1.0)
    S["C3_contract_then_BO"] = first_in(F["hi20"], 5) & (F["vol10_50"].shift(1) < 0.7) & (F["rvol"] >= 1.5)
    S["C4_climax_reversal"] = (c / c.shift(1) - 1 <= -0.03) & (F["rvol"] >= 3) & (F["clv"] >= 0.5)
    S["C5_OBV_high_BO"] = first_in(F["hi20"], 5) & (F["obv"] >= F["obv"].rolling(50).max())
    S["C6_CMF_BO50"] = first_in(F["hi50"], 5) & (F["cmf"] > 0.15)
    # E – price action
    S["E1_prev_week_high"] = first_in(c > F["wk_hi_prev"], 5)
    S["E2_donchian20"] = first_in(F["hi20"], 5)
    S["E3_donchian55"] = first_in(F["hi55"], 10)
    rng40 = h.shift(1).rolling(40).max() / l.shift(1).rolling(40).min() - 1
    S["E4_base_BO"] = (rng40 < 0.20) & (c > h.shift(1).rolling(40).max()) & (F["rvol"] >= 1.5)
    S["E5_trend_pullback"] = (c > F["ema50"]) & (F["ema50"] > F["ema200"]) & (l <= F["ema20"]) & (c > F["ema20"]) & (F["clv"] >= 0.6)
    gap = o / c.shift(1) - 1
    S["E6_gap_up_cont"] = (o >= h.shift(1)) & (gap >= 0.02) & (c > o) & (F["rvol"] >= 1.5)
    S["E7_gap_down_rev"] = (gap <= -0.02) & (c > o) & (F["clv"] >= 0.7)
    S["E8_sweep_20dlow"] = (l < F["lo20p"]) & (c > F["lo20p"]) & (F["clv"] >= 0.6)
    S["E9_hammer_20dlow_vol"] = F["hammer"] & (l <= F["lo20p"] * 1.01) & (F["rvol"] >= 1.5)
    dn3 = (c < c.shift(1)).shift(1) & (c < c.shift(1)).shift(2) & (c < c.shift(1)).shift(3)
    S["E10_engulf_after3dn_up"] = F["engulf"] & dn3.fillna(False).astype(bool) & up
    # B – divergence (+ structure break inside the detector)
    for nm in I.OSC:
        S[f"B_{nm}_regular"] = div_signals(F, nm, False)
    for nm in ("RSI", "MACDH", "OBV"):
        S[f"B_{nm}_hidden_up"] = div_signals(F, nm, True) & up
    grp = {}
    for nm, (g, _) in I.OSC.items():
        x = S[f"B_{nm}_regular"].rolling(3, min_periods=1).max().fillna(0).astype(bool)
        grp[g] = grp.get(g, False) | x
    ng = sum(v.astype(int) for v in grp.values())
    S["B_GROUPS2"] = (ng >= 2) & (S["B_RSI_regular"] | S["B_MACDH_regular"] | S["B_OBV_regular"])
    # combinations (section 4)
    S["X1_RSI_candle_rvol_break"] = rx(F["rsi14"], 30) & (F["hammer"] | F["engulf"]) & (F["rvol"] >= 1.5)
    S["X2_RSIdiv_rvol"] = S["B_RSI_regular"] & (F["rvol"] >= 1.5)
    S["X3_MACDdiv_volexp"] = S["B_MACDH_regular"] & (F["rvol"] >= 1.5)
    S["X4_STOCHdiv_RSIlow"] = S["B_STOCH_regular"] & (F["rsi14"].shift(3).rolling(10).min() < 35)
    S["X5_sweep_rvol"] = S["E8_sweep_20dlow"] & (F["rvol"] >= 1.5)
    S["X6_RS_BO_mkt"] = first_in(F["hi50"], 5) & (F["rs_rank"] >= 0.8) & F["mkt_w"]
    S["X7_lowATR_trend_BO"] = (F["atr10_50"] < 0.75) & up & first_in(F["hi20"], 5)
    full = dict(trend=up, mkt=F["mkt_w"], rvol=F["rvol"] >= 1.5, bo=first_in(F["hi20"], 5), adx=F["adx"] > 20, rs=F["rs_rank"] >= 0.7)
    S["X8_FULL"] = _all(full)
    for drop in full:
        S[f"X8_FULL_minus_{drop}"] = _all({k: v for k, v in full.items() if k != drop})
    return {k: (v.fillna(False).astype(bool) & e) for k, v in S.items()}


def _all(d):
    out = None
    for v in d.values():
        out = v if out is None else out & v
    return out


POSITIONAL = {   # trend families: trailing exit, long hold
    "F1_52wHigh_trail50": dict(sig=lambda F: first_in(F["hi252"], 20) & (F["rvol"] >= 1.5), trail="ema50"),
    "F2_RS_BO50_trail50": dict(sig=lambda F: first_in(F["hi50"], 5) & (F["rs_rank"] >= 0.9), trail="ema50"),
    "F3_VCP_BO_trail50": dict(sig=lambda F: (F["atr10_50"].shift(1) < 0.6) & first_in(F["hi20"], 5) & (F["rvol"] >= 1.5), trail="ema50"),
    "F4_MA_pullback_RSI3_trail50": dict(sig=lambda F: (F["ema50"] > F["ema200"]) & (F["rsi3"].shift(1) < 15) & (F["close"] > F["high"].shift(1)), trail="ema50"),
    "F1m_52wHigh_trail50_mkt": dict(sig=lambda F: first_in(F["hi252"], 20) & (F["rvol"] >= 1.5) & F["mkt_w"], trail="ema50"),
}


def rdist_atr(F, mult=1.5):
    return (mult * F["atr"]).shift(0)


def rdist_struct(F, look=5):
    a = F["atr"]
    d = F["close"] - F["low"].rolling(look).min() + 0.1 * a
    return d.clip(lower=0.75 * a, upper=3.0 * a)


def summarise(name, family, T, extra, splits=None):
    row = dict(exp_id=f"CQD-{family}-{name}-{extra.get('R', 0):g}R", strategy=name, family=family, **extra)
    parts = V.split(T, splits or V.DAILY_SPLITS)
    oos0 = (splits or V.DAILY_SPLITS)["OOS"][0]
    for k, t in parts.items():
        m = V.metrics(t)
        for a, b in m.items():
            row[f"{k}_{a}"] = b
    o = parts["OOS"]
    row["OOS_t"], row["OOS_p"] = np.nan, 1.0
    if len(o) > 2:
        dd = o.groupby(o["entry_time"].dt.normalize())["netR"].mean()
        tt = dd.mean() / (dd.std(ddof=1) / np.sqrt(len(dd))) if dd.std(ddof=1) > 0 else 0
        row["OOS_t"], row["OOS_p"] = round(float(tt), 2), float(stats.t.sf(tt, len(dd) - 1))
    yrs = T.groupby(T["entry_time"].dt.year)["netR"].mean()
    row["years_pos"] = f"{int((yrs > 0).sum())}/{len(yrs)}"
    return row


def main():
    t0 = time.time()
    W = D.daily_panel()
    F = features(W)
    sym = W["symbol"]; W.clear(); import gc; gc.collect()
    print(f"features {time.time() - t0:.0f}s, {F['close'].shape}", flush=True)
    S = signals(F)
    print(f"signals {time.time() - t0:.0f}s: {len(S)} swing signals", flush=True)
    rows, ledgers = [], []
    reg = F["mkt_on"]; vreg = F["mkt_vol_hi"]
    for name, sig in S.items():
        fam = name.split("_")[0][0]
        stop = rdist_struct(F) if fam in ("B", "E") and ("sweep" in name or fam == "B" or "hammer" in name) else rdist_atr(F)
        for R in RS_SWING:
            T = EN.daily_trades(F, sig, stop, 1, R, 20)
            if not len(T):
                continue
            T["mkt_on"] = reg.reindex(T["entry_time"]).values; T["vol_hi"] = vreg.reindex(T["entry_time"]).values
            T["strategy"] = name; T["R"] = R
            rows.append(summarise(name, {"A": "RSI", "B": "DIVERGENCE", "C": "VOLUME", "E": "PRICE_ACTION", "X": "COMBINED"}[fam],
                                  T, dict(params=f"target {R}R, stop {'structure' if stop is not None else 'ATR'}, max 20 sessions, entry next open",
                                          R=R, hold="swing", side="LONG")))
            ledgers.append(T)
        print(f"  {name}: done ({time.time() - t0:.0f}s)", flush=True)
    for name, spec in POSITIONAL.items():
        sig = spec["sig"](F).fillna(False).astype(bool) & F["elig"]
        for R, mb in ((0.0, 250), (3.0, 120)):
            T = EN.daily_trades(F, sig, (3.0 * F["atr"]), 1, R, mb, trail=F[spec["trail"]])
            T["mkt_on"] = reg.reindex(T["entry_time"]).values; T["vol_hi"] = vreg.reindex(T["entry_time"]).values
            T["strategy"] = name; T["R"] = R
            rows.append(summarise(name, "POSITIONAL", T, dict(params=f"stop 3 ATR, trail close<EMA50, {'target 3R' if R else 'no target'}, max {mb}",
                                                                R=R, hold="positional", side="LONG")))
            ledgers.append(T)
        print(f"  {name}: done ({time.time() - t0:.0f}s)", flush=True)
    L = pd.DataFrame(rows)
    sel = L.apply(V.verdict, axis=1) != "NOT_SELECTED"
    L["OOS_q"] = 1.0
    L.loc[sel, "OOS_q"] = V.bh(L.loc[sel, "OOS_p"].fillna(1).values)
    L["status"] = L.apply(V.verdict, axis=1)
    L.to_csv(OUT / "daily_leaderboard.csv", index=False)
    pd.concat(ledgers, ignore_index=True).assign(symbol=lambda x: x["key"].map(sym)).to_csv(OUT / "daily_trades.csv.gz", index=False)
    json.dump(dict(variants=len(L), signals=len(S) + len(POSITIONAL), trades=int(sum(len(x) for x in ledgers)), seconds=round(time.time() - t0)),
              open(OUT / "daily_run.json", "w"))
    print(L["status"].value_counts().to_dict(), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
