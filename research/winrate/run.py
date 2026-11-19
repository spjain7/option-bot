"""WINRATE – owner 12-Nov: "with all combinations of weightage find a 70–80 % winning setup" (research only).
Instead of hand-picking combinations, every closed bar is scored on ALL features at once, and the WEIGHTS are learned
from data (logistic regression and gradient-boosted trees), with a strict time split:
  TRAIN   DEV period  (weights learned here only)
  TUNE    VALID period (the score threshold that gives >= 70 % wins is chosen here only)
  TEST    OOS period  (looked at once; nothing is changed after seeing it)
Features at the decision bar (known at its close): candlestick patterns (engulfing, hammer / shooting star, doji,
inside / outside bar, morning / evening star proxy, close position in range), trend (EMA20/50/200 stack and slopes,
ADX, 20-bar linear-regression slope = trendline), support / resistance (distance to the 20- and 50-bar high / low in
ATR, distance to the last confirmed swing high / low = supply / demand zone proxy), breakouts (20-bar), momentum (RSI,
RSI 75 / 25 flags, MACD histogram, stochastic, DMO, CCI, MFI), divergences (regular / hidden, RSI / MACD / OBV / MFI,
bull / bear, known 3 bars after the swing), volume (relative volume, OBV slope), OI (stock futures: 5-day OI change
and price x OI quadrant: long / short build-up, covering, unwinding), higher-timeframe trend, ATR percentile, time of day.
Label: a trade from the NEXT bar's open with stop 1 ATR and target k ATR (k = 0.5, 1.0, 1.5), max hold, the stop
counted first inside a bar; net of real costs. BUY and SELL are separate models.
Markets: MCX 1h and 3h (all 7 commodities, 2023 -> Nov-2026), NSE stock futures daily (2018 -> 2026, with OI).
Reported for the chosen threshold: VALID and OOS win rate, net R per trade, trades, and a one-trade-at-a-time portfolio
check. python -m research.winrate.run [mcx1h mcx3h stockfut]  ->  results/winrate.csv"""
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E  # noqa: E402
from research.rsirev import run as RR  # noqa: E402
from research.cycle2 import common as C  # noqa: E402
from research.hull_dmo import run as HD  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"; OUT.mkdir(parents=True, exist_ok=True)
KS = (0.5, 1.0, 1.5)


def features(b, tf, oi=None):
    o, h, l, c, v = (b[x].astype(float).reset_index(drop=True) for x in ("open", "high", "low", "close", "volume"))
    n = len(c); pc = c.shift(1)
    atr = pd.Series(E.wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14))
    F = {}
    body, rng = (c - o), (h - l).replace(0, np.nan)
    lw, uw = np.minimum(o, c) - l, h - np.maximum(o, c)
    F["body_pct"] = body / rng; F["close_pos"] = (c - l) / rng; F["lower_wick"] = lw / rng; F["upper_wick"] = uw / rng
    F["bull_engulf"] = ((c > o) & (c.shift(1) < o.shift(1)) & (c >= o.shift(1)) & (o <= c.shift(1))).astype(float)
    F["bear_engulf"] = ((c < o) & (c.shift(1) > o.shift(1)) & (c <= o.shift(1)) & (o >= c.shift(1))).astype(float)
    F["hammer"] = ((lw >= 2 * body.abs()) & (uw <= 0.3 * rng)).astype(float); F["star"] = ((uw >= 2 * body.abs()) & (lw <= 0.3 * rng)).astype(float)
    F["doji"] = (body.abs() <= 0.1 * rng).astype(float)
    F["inside"] = ((h < h.shift(1)) & (l > l.shift(1))).astype(float); F["outside"] = ((h > h.shift(1)) & (l < l.shift(1))).astype(float)
    F["ret1_atr"] = (c - pc) / atr; F["ret5_atr"] = (c - c.shift(5)) / atr; F["ret20_atr"] = (c - c.shift(20)) / atr
    e20, e50, e200 = (c.ewm(span=s, adjust=False).mean() for s in (20, 50, 200))
    F["c_e20"] = (c - e20) / atr; F["c_e50"] = (c - e50) / atr; F["c_e200"] = (c - e200) / atr
    F["e20_slope"] = (e20 - e20.shift(5)) / atr; F["e50_slope"] = (e50 - e50.shift(10)) / atr
    F["stack_up"] = ((c > e20) & (e20 > e50) & (e50 > e200)).astype(float); F["stack_dn"] = ((c < e20) & (e20 < e50) & (e50 < e200)).astype(float)
    ad, _ = RR.adx(h, l, c); F["adx"] = ad
    t = np.arange(20, dtype=float); tm = t.mean(); den = ((t - tm) ** 2).sum()
    F["linreg_slope20"] = c.rolling(20).apply(lambda z: ((t - tm) * (z - z.mean())).sum() / den, raw=True) / atr
    for w in (20, 50):
        hh, ll = h.shift(1).rolling(w).max(), l.shift(1).rolling(w).min()
        F[f"d_high{w}"] = (hh - c) / atr; F[f"d_low{w}"] = (c - ll) / atr
        F[f"brk_up{w}"] = (c > hh).astype(float); F[f"brk_dn{w}"] = (c < ll).astype(float)
    K = 3; wdw = 2 * K + 1
    ispl = (l == l.rolling(wdw, center=True).min()); isph = (h == h.rolling(wdw, center=True).max())
    last_pl = pd.Series(np.where(ispl, l, np.nan)).shift(K).ffill(); last_ph = pd.Series(np.where(isph, h, np.nan)).shift(K).ffill()
    F["d_demand"] = (c - last_pl) / atr; F["d_supply"] = (last_ph - c) / atr
    I = E.indicators(h, l, c, v); r = I["rsi"]
    F["rsi"] = r; F["rsi_ge75"] = (r >= 75).astype(float); F["rsi_le25"] = (r <= 25).astype(float)
    F["macd_hist"] = I["macd_hist"] / atr; F["stoch"] = I["stoch"]; F["cci"] = I["cci"]; F["mfi"] = I["mfi"]
    F["obv_slope"] = (I["obv"] - I["obv"].shift(10)) / (v.rolling(10).sum().replace(0, np.nan))
    F["dmo"] = HD.dmo(h.values, l.values, c.values, 14, False)
    a, bb = HD.hull(h.values, l.values, c.values, 30); F["hull_green"] = (bb > a).astype(float)
    D = E.divergences(h, l, {k: I[k] for k in ("rsi", "macd", "obv", "mfi")}, K)
    for k in ("rsi", "macd", "obv", "mfi"):
        for kind in ("regular", "hidden"):
            for sd, nm in ((1, "bull"), (-1, "bear")):
                x = pd.Series(D[k, kind, sd].astype(float)).rolling(3).max()
                F[f"div_{k}_{kind}_{nm}"] = x
    F["rvol"] = v / v.rolling(20).mean().shift(1)
    F["atr_pct_rank"] = (atr / c).rolling(250, min_periods=50).rank(pct=True)
    F["htf_up"] = C.htf_up(b, tf).astype(float)
    tt = pd.to_datetime(b["time"])
    if tf in ("1h", "3h"):
        F["hour"] = (tt.dt.hour + tt.dt.minute / 60).values
    if oi is not None:
        oi = pd.Series(np.asarray(oi, float)); oc = oi / oi.shift(5) - 1; pc5 = c / c.shift(5) - 1
        F["oi_chg5"] = oc
        F["long_buildup"] = ((pc5 > 0) & (oc > 0)).astype(float); F["short_buildup"] = ((pc5 < 0) & (oc > 0)).astype(float)
        F["short_cover"] = ((pc5 > 0) & (oc < 0)).astype(float); F["long_unwind"] = ((pc5 < 0) & (oc < 0)).astype(float)
    X = pd.DataFrame({k: np.asarray(val, float) for k, val in F.items()})
    return X.replace([np.inf, -np.inf], np.nan), atr.values


@njit(cache=True)
def labels(o, h, l, c, atr, side, k, hold, grp, costf):
    """every bar independently: entry next open, stop 1 ATR, target k ATR, stop first; -> (win flag, net R) per bar."""
    n = len(c); win = np.full(n, np.nan); net = np.full(n, np.nan)
    for t in range(n - 1):
        if not np.isfinite(atr[t]) or atr[t] <= 0 or grp[t + 1] != grp[t]:
            continue
        e = t + 1; px = o[e]; rk = atr[t]; st = px - side * rk; tp = px + side * k * rk
        x = np.nan; j = e
        while j < n and grp[j] == grp[e]:
            if j > e and ((side > 0 and o[j] <= st) or (side < 0 and o[j] >= st)):
                x = o[j]; break
            if j > e and ((side > 0 and o[j] >= tp) or (side < 0 and o[j] <= tp)):
                x = o[j]; break
            if (side > 0 and l[j] <= st) or (side < 0 and h[j] >= st):
                x = st; break
            if (side > 0 and h[j] >= tp) or (side < 0 and l[j] <= tp):
                x = tp; break
            if j - e + 1 >= hold or j == n - 1 or grp[j + 1] != grp[j]:
                x = c[j]; break
            j += 1
        if np.isnan(x):
            continue
        r = (side * (x - px) - costf[e] * px) / rk
        net[t] = r; win[t] = 1.0 if r > 0 else 0.0
    return win, net


def load(m):
    if m == "mcx1h":
        return RR.mcx("1h"), "1h", 45, [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")], False
    if m == "mcx3h":
        return RR.mcx("3h"), "3h", 40, [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")], False
    return RR.stockfut("1d"), "1d", 15, [("DEV", "2018-01-01"), ("VAL", "2022-01-01"), ("OOS", "2024-01-01")], True


def stockfut_oi(frames):
    """attach aggregate OI (sum over expiries / cumulative adjustment) to the stock-futures frames."""
    import pickle
    from research.rsidiv import stockfut as SF
    A = pickle.loads(SF.CM_PKL.read_bytes()); F = SF.fut_daily(SF.fut_rows("STK"))
    sk = pd.concat([pd.DataFrame(dict(date=a["time"], symbol=a["symbol"].astype(str), key=k)) for k, a in A.items()], ignore_index=True)
    F = F.merge(sk, on=["date", "symbol"]); oi_by = {}
    for key, f in F.groupby("key"):
        a = A[key]; fac = a["factor"].values.astype(float); cum = np.r_[np.cumprod(fac[::-1])[::-1][1:], 1.0]
        s = pd.Series(cum, index=pd.to_datetime(a["time"]))
        oi_by[str(a["symbol"].iloc[-1])] = (f.set_index("date")["oi_all"] / s.reindex(f.date).values)
    return oi_by


def run(m):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    frames, tf, hold, cuts, has_oi = load(m)
    oi_by = stockfut_oi(frames) if has_oi else {}
    Xs, metas = [], []
    for g, f in enumerate(frames):
        b = f["b"].reset_index(drop=True)
        oi = oi_by[f["name"]].reindex(pd.to_datetime(b["time"])).values if has_oi and f["name"] in oi_by else (np.full(len(b), np.nan) if has_oi else None)
        X, atr = features(b, tf, oi)
        meta = pd.DataFrame(dict(time=pd.to_datetime(b["time"]).values, name=f["name"], live=np.asarray(f["live"], bool), atr=atr,
                                 o=b.open.values.astype(float), h=b.high.values.astype(float), l=b.low.values.astype(float), c=b.close.values.astype(float),
                                 grp=np.asarray(f["grp"]) if np.ndim(f["grp"]) else np.full(len(b), f["grp"]), costf=f["costf"]))
        Xs.append(X); metas.append(meta)
    X = pd.concat(Xs, ignore_index=True); M = pd.concat(metas, ignore_index=True)
    M["grp"] = M.grp.astype(np.int64)
    per = E.periods(M.time.values, cuts)
    rows = []
    for side in (1, -1):
        for k in KS:
            win, net = labels(M.o.values, M.h.values, M.l.values, M.c.values, M.atr.values, side, k, hold, M.grp.values, M.costf.values.astype(float))
            ok = np.isfinite(win) & M.live.values & (X.notna().mean(axis=1).values > 0.8)
            base = {p: (np.nanmean(win[ok & (per == p)]), np.nanmean(net[ok & (per == p)])) for p, _ in cuts}
            tr = ok & (per == "DEV"); va = ok & (per == "VAL"); te = ok & (per == "OOS")
            for mname, model in (("logistic", make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=300, C=0.5))),
                                 ("boosted_trees", HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200, l2_regularization=1.0))):
                Xtr = X[tr]; ytr = win[tr]
                if len(Xtr) > 400000:                     # memory guard: random subsample of DEV for fitting
                    sel = np.random.default_rng(1).choice(len(Xtr), 400000, replace=False); Xtr, ytr = Xtr.iloc[sel], ytr[sel]
                model.fit(Xtr, ytr)
                pv, pt = model.predict_proba(X[va])[:, 1], model.predict_proba(X[te])[:, 1]
                nv, nt = net[va], net[te]; wv, wt = win[va], win[te]
                # thresholds chosen on VALID only: the lowest score giving >= 70 % and >= 80 % wins with >= 50 trades
                for goal in (0.70, 0.80):
                    thr = None
                    for q in np.linspace(0.5, 0.999, 120):
                        th = np.quantile(pv, q); s = pv >= th
                        if s.sum() >= 50 and wv[s].mean() >= goal:
                            thr = th; break
                    row = dict(market=m, tf=tf, side="BUY" if side > 0 else "SELL", target_atr=k, model=mname, goal_win=goal,
                               base_win_VAL=round(100 * base["VAL"][0], 1), base_R_VAL=round(base["VAL"][1], 3),
                               base_win_OOS=round(100 * base["OOS"][0], 1), base_R_OOS=round(base["OOS"][1], 3))
                    if thr is None:
                        row.update(found_on_VAL=False); rows.append(row); continue
                    sv, st_ = pv >= thr, pt >= thr
                    row.update(found_on_VAL=True, threshold=round(float(thr), 4), VAL_trades=int(sv.sum()), VAL_win=round(100 * wv[sv].mean(), 1),
                               VAL_R=round(float(nv[sv].mean()), 3), OOS_trades=int(st_.sum()),
                               OOS_win=round(100 * wt[st_].mean(), 1) if st_.any() else np.nan, OOS_R=round(float(nt[st_].mean()), 3) if st_.any() else np.nan)
                    # one trade at a time per instrument in OOS (what a real call list would be)
                    idx = np.where(te)[0][st_]
                    sig = np.zeros(len(M), np.bool_); sig[idx] = True
                    ei, xi, nr, gr, cr = E.sim(M.o.values, M.h.values, M.l.values, M.c.values, sig, side, M.atr.values.astype(float), k,
                                               M.grp.values, hold, M.costf.values.astype(float), np.zeros(len(M), np.int64))
                    row.update(OOS_calls_one_at_a_time=len(nr), OOS_calls_win=round(100 * float((nr > 0).mean()), 1) if len(nr) else np.nan,
                               OOS_calls_R=round(float(nr.mean()), 3) if len(nr) else np.nan,
                               OOS_calls_total_R=round(float(nr.sum()), 1) if len(nr) else np.nan)
                    rows.append(row)
                print(m, side, k, mname, "done", flush=True)
    return rows


def main(ms):
    rows = []
    for m in ms:
        t0 = time.time(); rows += run(m); print(m, f"{time.time() - t0:.0f}s", flush=True)
        pd.DataFrame(rows).to_csv(OUT / "winrate.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1:] or ["mcx1h", "mcx3h", "stockfut"])
