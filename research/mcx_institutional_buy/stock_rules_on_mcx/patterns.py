"""ROUND 3 (owner 17-Nov-2026): candlestick / breakout / breakdown / support-resistance / liquidity-sweep / volume / OI
strategies on MCX, single and combined, plus a weighted score; goal: 70-80 % win rate WITH positive expectancy after costs.
  triggers   ENGULF (engulfing), PIN (hammer / shooting star), MARU (marubozu >= 1.2 ATR), INSIDE (inside-bar breakout),
             BO20 (20-candle breakout / breakdown), RES (close through the last confirmed swing high / low, pivots 5/5),
             SR (bounce off the last swing low / high, within 0.3 ATR), SWEEP (wick through the last swing low / high and close
             back inside = liquidity grab)
  conditions VOL (volume > 1.5x 20-bar avg), OI (previous day: price and open interest both moved our way = long / short
             build-up), DT (daily trend EMA20/50), E200 (EMA200 side)
  signals    every trigger, every pair of triggers on the same candle, each with every subset of the 4 conditions;
             WSCORE = weighted sum of all 12 parts, weights = each part's TRAIN lift in average R (TRAIN only), top 10/20/30 %
  candles    1h, 2h, 3h, 4h (Jul-2022 ->), daily (2006 ->)      side  BUY and SELL
  exits      stop 1 / 1.5 / 2 / 3 ATR  x  target 0.5 / 0.75 / 1 / 1.5 / 2 / 3 R      (time exit 40 candles)
  costs      real MCX fees + live spread.  Same rule on all 7 commodities (pooled) -- no per-commodity tuning.
  pick       TRAIN only: win >= 70 %, avg R > 0, >= 40 trades. Then VALID and OOS shown unchanged, plus random entries
             (same side, same daily-trend filter, same stop / target) for the same periods: a high win rate is cheap with a
             small target and a wide stop, so the random column is the real test.
python -m research.mcx_institutional_buy.stock_rules_on_mcx.patterns -> reports/mcx_patterns*.csv / .json"""
import itertools
import json
import time
import warnings
import numpy as np
import pandas as pd
from research.mcx_institutional_buy.backtesting import data as D, costs as K, sim as S, runner as RN
from research.mcx_institutional_buy.feature_engineering import ind as I
from research.mcx_institutional_buy.stock_rules_on_mcx.run import frames, dtrend

warnings.filterwarnings("ignore")
TRIG = ["ENGULF", "PIN", "MARU", "INSIDE", "BO20", "RES", "SR", "SWEEP"]
COND = ["VOL", "OI", "DT", "E200"]
TFS = ["1h", "2h", "3h", "4h", "1d"]
KS = [1.0, 1.5, 2.0, 3.0]
RS = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
MAXH = 40
MULT = {k: v["mult"] for k, v in K.CFG["contracts"].items()}


def parts(o, h, l, c, atr, volx, e200, dts, oiok):
    """BUY-side parts on (possibly mirrored) prices; every value known at the candle's close."""
    rng_ = h - l; body = np.abs(c - o)
    po, pc, ph, pl = (np.r_[np.nan, x[:-1]] for x in (o, c, h, l))
    pph, ppl = np.r_[np.nan, ph[:-1]], np.r_[np.nan, pl[:-1]]
    up = c > o
    P = {}
    P["ENGULF"] = up & (pc < po) & (c >= po) & (o <= pc)
    lw = np.minimum(o, c) - l
    P["PIN"] = (lw >= 2 * body) & (lw >= 0.6 * rng_) & (c >= l + 0.66 * rng_) & (rng_ > 0.5 * atr)
    P["MARU"] = up & (body >= 0.8 * rng_) & (rng_ >= 1.2 * atr)
    P["INSIDE"] = (ph < pph) & (pl > ppl) & (c > ph)
    hh = pd.Series(h).shift(1).rolling(20).max().values
    P["BO20"] = c > hh
    plo, phi = I.pivots(l, h, 5, 5)
    rh, _ = I.known_levels(phi, h, 5, 1); rl, _ = I.known_levels(plo, l, 5, 1)
    rh, rl = rh[:, 0], rl[:, 0]
    P["RES"] = (c > rh) & (pc <= rh)
    P["SR"] = (l <= rl + 0.3 * atr) & (l >= rl - 0.3 * atr) & (c > rl) & up & (c > o + 0.3 * rng_ * 0)
    P["SWEEP"] = (l < rl) & (c > rl) & (c >= l + 0.5 * rng_)
    P["VOL"] = volx > 1.5
    P["OI"] = oiok
    P["DT"] = dts
    P["E200"] = c > e200
    return {k: np.nan_to_num(np.asarray(v, float)).astype(bool) for k, v in P.items()}


def signals():
    out = []
    for t in TRIG:
        out.append((t,))
    for a, b in itertools.combinations(TRIG, 2):
        out.append((a, b))
    full = []
    for tr in out:
        for n in range(len(COND) + 1):
            for cs in itertools.combinations(COND, n):
                full.append(tr + cs)
    return full


def load():
    data = {}
    for name in D.INTRA:
        F, dd = frames(name)
        oi = D.daily_oi(name)
        dclose = dd.set_index(pd.to_datetime(dd.time).dt.normalize())["raw_close"]
        dclose = dclose[~dclose.index.duplicated(keep="last")]
        for tf in TFS:
            f = F[tf].reset_index(drop=True)
            t = pd.to_datetime(f["time"]); day = t.dt.normalize()
            per = RN.period_of("1d" if tf == "1d" else "1h", t)
            dt = dtrend(f, dd)
            if oi is not None and len(oi):
                s = oi.oi.astype(float); s.index = pd.to_datetime(s.index)
                px = dclose.reindex(s.index)
                d_oi, d_px = (s / s.shift(1) - 1), (px / px.shift(1) - 1)
                # previous completed day only (shift 1 day onto the next trading day): no look-ahead
                lb = ((d_oi > 0) & (d_px > 0)).shift(1); sb = ((d_oi > 0) & (d_px < 0)).shift(1)
                if tf == "1d":                     # a daily candle's own day is complete at its close: use same-day
                    lb, sb = ((d_oi > 0) & (d_px > 0)), ((d_oi > 0) & (d_px < 0))
                oib = day.map(lb).fillna(False).values.astype(bool); ois = day.map(sb).fillna(False).values.astype(bool)
            else:
                oib = ois = np.zeros(len(f), bool)
            o, h, l, c, a = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
            costf = K.cost_frac(name, f["raw_close"].values, t)
            seg = f["seg"].values.astype(np.int64)
            fac = f["raw_close"].values / c
            for side in (1, -1):
                if side > 0:
                    oo, hh_, ll, cc, e = o, h, l, c, f["ema200"].values
                else:
                    oo, hh_, ll, cc, e = -o, -l, -h, -c, -f["ema200"].values
                P = parts(oo, hh_, ll, cc, a, f["volx"].values, e, dt == side, oib if side > 0 else ois)
                data[(name, tf, side)] = dict(o=oo, h=hh_, l=ll, c=cc, a=a, seg=seg, costf=costf * side, P=P, per=np.asarray(per),
                                              fac=fac, time=t.values, raw_o=o)
        print(name, "loaded", flush=True)
    return data


def sim(d, sig, k, r):
    si, ei, xi, g, nr, mfe, mae, why, rej = S.simulate(d["o"], d["h"], d["l"], d["c"], d["a"], d["seg"], d["costf"], sig,
                                                       d["c"] - k * d["a"], NAN[len(d["c"])], NAN[len(d["c"])], 0, float(r),
                                                       MAXH, MAXH, 3.0, 3, 0.25, 6.0, 1.5)
    return si, ei, xi, nr, why


NAN = {}


def stats(nr, per):
    out = {}
    for p in ("TRAIN", "VAL", "OOS"):
        x = nr[per == p]
        out[f"{p}_n"] = int(len(x))
        out[f"{p}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else np.nan
        out[f"{p}_R"] = round(float(x.mean()), 3) if len(x) else np.nan
    return out


def main():
    t0 = time.time()
    data = load()
    for d in data.values():
        NAN.setdefault(len(d["c"]), np.full(len(d["c"]), np.nan))
    SIG = signals()
    names = list(D.INTRA)
    rows = []
    rng = np.random.default_rng(5)
    # random baseline per tf / side / exit: daily-trend bars, 5 % of them, 20 draws pooled over the 7 commodities
    RB_ = {}
    for tf in TFS:
        for side in (1, -1):
            for k, r in itertools.product(KS, RS):
                acc = {p: [] for p in ("TRAIN", "VAL", "OOS")}
                for _ in range(10):
                    nrs, pers = [], []
                    for n in names:
                        d = data[(n, tf, side)]
                        m = d["P"]["DT"] & (rng.random(len(d["c"])) < 0.05)
                        si, ei, xi, nr, why = sim(d, m, k, r)
                        nrs.append(nr); pers.append(d["per"][ei])
                    nr = np.concatenate(nrs); pe = np.concatenate(pers)
                    for p in acc:
                        x = nr[pe == p]
                        acc[p].append(((x > 0).mean() * 100, x.mean()) if len(x) else (np.nan, np.nan))
                RB_[(tf, side, k, r)] = {f"{p}_rand_win": round(float(np.nanmean([a[0] for a in v])), 1) for p, v in acc.items()} | \
                                        {f"{p}_rand_R": round(float(np.nanmean([a[1] for a in v])), 3) for p, v in acc.items()}
    print("random done", round(time.time() - t0), "s", flush=True)

    for tf in TFS:
        for side in (1, -1):
            # combined masks per signal, pooled over commodities
            for sg in SIG:
                masks = []
                ok = True
                for n in names:
                    P = data[(n, tf, side)]["P"]
                    m = np.ones(len(P["DT"]), bool)
                    for x in sg:
                        m &= P[x]
                    masks.append(m)
                if sum(int(m.sum()) for m in masks) < 40:
                    continue
                for k, r in itertools.product(KS, RS):
                    nrs, pers = [], []
                    for n, m in zip(names, masks):
                        d = data[(n, tf, side)]
                        si, ei, xi, nr, why = sim(d, m, k, r)
                        nrs.append(nr); pers.append(d["per"][ei])
                    nr = np.concatenate(nrs); pe = np.concatenate(pers)
                    if (pe == "TRAIN").sum() < 20:
                        continue
                    row = dict(tf=tf, side="BUY" if side > 0 else "SELL", signal="+".join(sg), k=k, r=r, **stats(nr, pe))
                    row.update(RB_[(tf, side, k, r)])
                    rows.append(row)
            print(tf, side, "done", len(rows), round(time.time() - t0), "s", flush=True)
    L = pd.DataFrame(rows)
    L.to_csv(RN.REPORTS / "mcx_patterns.csv", index=False)
    print("tested", len(L), "combinations", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
