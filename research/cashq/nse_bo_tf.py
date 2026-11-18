"""NSE STOCK BREAKOUT / BREAKDOWN by timeframe (owner 18-Nov-2026: "we trade the Indian market – breakout / breakdown setups,
weekly, monthly, daily, 4 hours"). Official NSE bhavcopies 2005-26 (back-adjusted, delisted included), point-in-time liquid
universe (₹25 cr median turnover, ≥ ₹50, ≥ 250 sessions). Weekly / monthly candles built from the daily ones.
BUY = breakout (cash delivery or futures); SELL = breakdown (only through stock futures / intraday – cash prices used as the
proxy). Signal at the candle's close, entry at the next candle's open.
  setups  BO10 / BO20 / BO55 (close beyond the 10 / 20 / 55-candle high / low) · PREV (close beyond the previous candle's high /
          low, weekly / monthly) · HI52 (52-week closing high / low) · ATH (all-time closing high / low since 2005, weekly /
          monthly) · BOX (last 10 candles inside 2.5 ATR, then close beyond the box) · MARU (strong candle: body >= 70 %, range
          >= 1.5 ATR, beyond the 20-candle high / low)
  filters none · VOL (volume >= 1.5x its 20-candle average) · TREND (close above EMA50 and EMA50 rising; SELL mirror) ·
          MKT (top-100 EW index above its 200-day average; SELL below) · VOL+TREND · TREND+MKT
  exits   SL 1.5 / 2 / 3 ATR x target 2R / 3R, or SL 2 ATR + 3 ATR chandelier trail · max 60 daily / 26 weekly / 12 monthly candles
  costs   0.393 % per round trip (delivery); random entries with the same side / exit for comparison
Periods DEV 2005-14 · VALID 2015-19 · OOS 2020-26 (and 2024 / 2025 / 2026).
python -m research.cashq.nse_bo_tf -> results/nse_bo_tf.csv"""
import gc
import itertools
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.cashq import data as D, ind as I  # noqa: E402
import importlib.util as _iu  # noqa: E402
_sp = _iu.spec_from_file_location("mcx_sim", ROOT.parent / "mcxib/research/mcx_institutional_buy/backtesting/sim.py")
S = _iu.module_from_spec(_sp); _sp.loader.exec_module(S)     # the shared numba simulator (research/mcx-institutional-buy)

OUT = Path(__file__).resolve().parent / "results"
COST = 0.00393
MAXH = {"1d": 60, "1w": 26, "1M": 12}
HI52 = {"1d": 252, "1w": 52, "1M": 12}
EXITS = [(k, r, 0) for k in (1.5, 2.0, 3.0) for r in (2.0, 3.0)] + [(2.0, 0.0, 2)]
FILTS = [(), ("VOL",), ("TREND",), ("MKT",), ("VOL", "TREND"), ("TREND", "MKT")]


def monthly(W):
    g = W["close"].index.to_period("M")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "value": "sum"}
    out = {f: W[f].groupby(g).agg(agg[f]) for f in agg}
    last_day = pd.Series(W["close"].index, index=W["close"].index).groupby(g).last()
    for f in out:
        out[f].index = pd.DatetimeIndex(last_day.values)
    out["elig"] = W["elig"].groupby(g).last().set_axis(out["close"].index).astype(bool)
    return out


def per(t):
    y = t.year
    return np.where(y <= 2014, "DEV", np.where(y <= 2019, "VALID", "OOS"))


def run_tf(P, tf, mkt):
    o, h, l, c, v = (P[x].astype("float64") for x in ("open", "high", "low", "close", "volume")); e = P["elig"].reindex_like(c).fillna(False).astype(bool)
    keep = c.notna().values.T.ravel()
    flat = lambda df: np.asarray(df.values, float).T.ravel()[keep]
    flatb = lambda df: np.asarray(df.fillna(False).values, bool).T.ravel()[keep]
    seg = np.repeat(np.arange(c.shape[1]), c.shape[0])[keep].astype(np.int64)
    tix = np.tile(np.arange(c.shape[0]), c.shape[1])[keep]
    days = c.index
    atr = I.atr(h, l, c, 14); ema50 = c.ewm(span=50, adjust=False, min_periods=50).mean()
    vx = v / v.rolling(20).mean().shift(1)
    mk = mkt.reindex(days, method="ffill").fillna(False).values
    MK = pd.DataFrame(np.repeat(mk[:, None], c.shape[1], 1), index=days, columns=c.columns)
    rows = []
    A = flat(atr); cost_raw = COST
    rng = np.random.default_rng(11)
    for side in (1, -1):
        oo, hh, ll, cc = (o, h, l, c) if side > 0 else (-o, -l, -h, -c)
        em = ema50 if side > 0 else -ema50
        P_ = {}
        for N in (10, 20, 55):
            P_[f"BO{N}"] = cc > hh.shift(1).rolling(N).max()
        if tf != "1d":
            P_["PREV"] = (cc > hh.shift(1)) & (cc.shift(1) <= hh.shift(2))
            P_["ATH"] = (cc >= cc.cummax()) & (cc.notna().cumsum() >= 24 if tf == "1M" else cc.notna().cumsum() >= 104)
        P_["HI52"] = cc >= cc.rolling(HI52[tf], min_periods=int(HI52[tf] * 0.95)).max()
        bh, bl = hh.shift(1).rolling(10).max(), ll.shift(1).rolling(10).min()
        P_["BOX"] = ((bh - bl) / atr.shift(1) <= 2.5) & (cc > bh)
        rg = hh - ll; body = (cc - oo).abs()
        P_["MARU"] = (cc > oo) & (body >= 0.7 * rg) & (rg >= 1.5 * atr) & P_["BO20"]
        for k in list(P_):                                     # first signal in 3 candles
            x = P_[k].fillna(False)
            P_[k] = x & ~x.shift(1).rolling(3, min_periods=1).max().fillna(0).astype(bool)
        F_ = {"VOL": vx >= 1.5, "TREND": (cc > em) & (em > em.shift(5)), "MKT": MK if side > 0 else ~MK}
        O_, H_, L_, C_ = flat(oo), flat(hh), flat(ll), flat(cc)
        cf = np.full(len(C_), cost_raw) * np.sign(C_)            # costs as a fraction of the (mirrored) price
        E_ = flatb(e)
        nan = np.full(len(C_), np.nan)
        ed_all = days[tix]
        # random baseline per exit (2 % of eligible candles)
        base_rand = {}
        for k, r, kind in EXITS:
            rr = []
            for _ in range(5):
                sg = E_ & (rng.random(len(C_)) < 0.02)
                out = S.simulate(O_, H_, L_, C_, A, seg, cf, sg, C_ - k * A, nan, nan, kind, r, MAXH[tf], MAXH[tf], 3.0, 3, 0.25, 6.0, 1.0)
                pe = per(ed_all[out[1]]); rr.append({p: float(out[4][pe == p].mean()) for p in ("DEV", "VALID", "OOS")})
            base_rand[(k, r, kind)] = {p: np.mean([x[p] for x in rr]) for p in ("DEV", "VALID", "OOS")}
        for (fam, sig0), flt in itertools.product(P_.items(), FILTS):
            m = sig0
            for f in flt:
                m = m & F_[f]
            M = flatb(m) & E_
            if M.sum() < 30:
                continue
            for k, r, kind in EXITS:
                si, ei, xi, g, nr, mfe, mae, why, rej = S.simulate(O_, H_, L_, C_, A, seg, cf, M, C_ - k * A, nan, nan, kind, r, MAXH[tf], MAXH[tf],
                                                                   3.0, 3, 0.25, 6.0, 1.0)
                if len(nr) < 30:
                    continue
                ed = ed_all[ei]; p = per(ed)
                pct = side * (C_[xi] * 0 + 1)  # placeholder to keep shapes
                risk_pct = k * A[si] / np.abs(O_[ei])
                net_pct = nr * risk_pct * 100
                row = dict(tf=tf, side="BUY" if side > 0 else "SELL", setup=fam, filt="+".join(flt) or "none", sl_atr=k,
                           exit="trail 3 ATR" if kind == 2 else f"{r:g}R", trades=len(nr),
                           per_month_2025_26=round(float((ed >= "2025-01-01").sum() / 22.5), 1), win=round(100 * float((nr > 0).mean()), 1),
                           R=round(float(nr.mean()), 3), avg_pct=round(float(net_pct.mean()), 2), med_hold=int(np.median(xi - ei + 1)))
                for pp in ("DEV", "VALID", "OOS"):
                    x = nr[p == pp]; row[f"{pp}_n"] = len(x); row[f"{pp}_win"] = round(100 * float((x > 0).mean()), 1) if len(x) else None
                    row[f"{pp}_R"] = round(float(x.mean()), 3) if len(x) else None
                    row[f"{pp}_rand"] = round(base_rand[(k, r, kind)][pp], 3)
                for y in (2024, 2025, 2026):
                    x = nr[ed.year == y]; row[f"y{y}_n"] = len(x); row[f"y{y}_R"] = round(float(x.mean()), 3) if len(x) else None
                rows.append(row)
        print(tf, side, len(rows), flush=True)
    return rows


def main():
    W = D.daily_panel()
    mk = W["market"]["close"]; mkt = mk > mk.rolling(200).mean()
    rows = []
    rows += run_tf(W, "1d", mkt)
    Wk = D.weekly(W); rows += run_tf(Wk, "1w", mkt); del Wk; gc.collect()
    Mo = monthly(W); rows += run_tf(Mo, "1M", mkt); del Mo; gc.collect()
    L = pd.DataFrame(rows); OUT.mkdir(exist_ok=True); L.to_csv(OUT / "nse_bo_tf.csv", index=False)
    ok = L[(L.DEV_R > L.DEV_rand) & (L.VALID_R > L.VALID_rand) & (L.OOS_R > L.OOS_rand) & (L.DEV_R > 0) & (L.VALID_R > 0) & (L.OOS_R > 0)]
    pd.set_option("display.width", 280); pd.set_option("display.max_rows", 200)
    cols = ["tf", "side", "setup", "filt", "sl_atr", "exit", "trades", "per_month_2025_26", "win", "R", "avg_pct", "med_hold", "DEV_R", "VALID_R", "OOS_R",
            "OOS_rand", "y2024_R", "y2025_R", "y2026_R"]
    print("\nPOSITIVE AND BETTER THAN RANDOM IN ALL 3 PERIODS:", len(ok), "of", len(L))
    print(ok.groupby(["tf", "side"]).size())
    ok = ok.assign(score=np.minimum(np.minimum(ok.DEV_R - ok.DEV_rand, ok.VALID_R - ok.VALID_rand), ok.OOS_R - ok.OOS_rand))
    print(ok.sort_values("score", ascending=False).groupby(["tf", "side"]).head(5)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
