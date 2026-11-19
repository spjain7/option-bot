"""INST-CONFIRM – do volume, OI and indicator confirmations rescue the institutional MCX setups? (owner 12-Nov-2026)
Research only. Same 7 setups + benchmark as research/inst/run.py (identical triggers, stops, targets, costs, exits).
Every trade gets ~20 votes measured on the SIGNAL bar (known before the next-bar-open entry):
  volume : RVOL >= 1.5 / >= 2 (bar volume vs 20-bar mean), OBV 10-bar slope with the trade
  OI     : MCX daily bhavcopy, all expiries summed, PREVIOUS trading day only (no look-ahead):
           long build-up (price up + OI up) for BUY / short build-up for SELL; price direction with the trade;
           OI rising; 5-day price x OI build-up with the trade
  trend  : EMA20 > EMA50, EMA50 > EMA200, close vs session VWAP, previous-day close vs 20-day SMA (daily trend)
  momentum: RSI14 > 50, MACD histogram > 0, MACD histogram rising, Hull 30 trend, DMO(20) > 0, signal candle colour
  regime : ADX14 > 25, ATR above its 100-bar median
Weighting (all learned on DEV 2023–24 only, then FROZEN for VALID 2025 and OOS 2026):
  W1 per-indicator lift   weight = DEV mean-R lift (aligned minus not aligned), negative lifts set to 0
  W2 logistic regression  P(win) from all votes + setup dummies
  W3 equal weight         count of aligned directional votes (>= k of 15)
  each score keeps the top 30 % / 20 % / 10 % of trades (threshold set on DEV) -> win %, net R, PF per period.
python -m research.inst.confirm [15|60 pos]  ->  results/confirm_<tf>.csv, confirm_<tf>_indicators.csv"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD  # noqa: E402
from research.mcxhw.search import bars  # noqa: E402
from research.rsidiv import engine as E  # noqa: E402
from research.inst import run as I  # noqa: E402
from research.hull_dmo.run import hull, dmo  # noqa: E402

OUT = I.OUT
CUTS = I.CUTS


def daily_oi():
    """symbol -> DataFrame(date, oi, px): total futures OI (lots) and front-month close per trading day."""
    fs = sorted((ROOT / "research/data/mcx_bhav/days").glob("*.csv"))
    rows = []
    for f in fs:
        d = pd.read_csv(f, usecols=["date", "symbol", "instrument", "expiry", "close", "oi_lots"])
        d = d[d.instrument.astype(str).str.startswith("FUT") & d.symbol.isin(MD.NAMES)]
        if not len(d):
            continue
        d["exp"] = pd.to_datetime(d.expiry, format="%d%b%Y", errors="coerce")
        for s, g in d.groupby("symbol"):
            g = g.sort_values("exp")
            rows.append((pd.Timestamp(g.date.iloc[0]), s, float(g.oi_lots.sum()), float(g.close.iloc[0])))
    D = pd.DataFrame(rows, columns=["date", "symbol", "oi", "px"])
    return {s: g.sort_values("date").set_index("date") for s, g in D.groupby("symbol")}


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().values


def features(b, oi):
    """signed (+1 bull / -1 bear / 0) directional votes and unsigned (0/1) condition votes, one row per bar."""
    o, h, l, c, v = (b[x].astype(float).values for x in ("open", "high", "low", "close", "volume"))
    t = pd.to_datetime(b.time); day = t.dt.normalize()
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    atr = E.wilder(tr, 14)
    sgn = lambda x: np.sign(np.nan_to_num(x))
    D, U = {}, {}
    D["EMA20>50"] = sgn(ema(c, 20) - ema(c, 50))
    D["EMA50>200"] = sgn(ema(c, 50) - ema(c, 200))
    tp = (h + l + c) / 3; vs = pd.Series(v)
    vw = (pd.Series(tp * v).groupby(day.values).cumsum() / vs.groupby(day.values).cumsum().replace(0, np.nan)).values
    D["VWAP_side"] = sgn(c - vw)
    dlt = np.diff(c, prepend=np.nan); up = E.wilder(np.where(dlt > 0, dlt, 0.0), 14); dn = E.wilder(np.where(dlt < 0, -dlt, 0.0), 14)
    rsi = np.where(dn > 0, 100 - 100 / (1 + up / np.where(dn > 0, dn, 1)), 100.0)
    D["RSI>50"] = sgn(rsi - 50)
    macd = ema(c, 12) - ema(c, 26); hist = macd - ema(macd, 9)
    D["MACD_hist>0"] = sgn(hist); D["MACD_hist_rising"] = sgn(np.diff(hist, prepend=np.nan))
    ha, hb = hull(h, l, c, 30); D["HULL30"] = sgn(ha - hb)
    D["DMO>0"] = sgn(dmo(h, l, c, 20, False))
    obv = np.cumsum(np.sign(np.nan_to_num(dlt)) * v); D["OBV_slope10"] = sgn(obv - np.r_[np.full(10, np.nan), obv[:-10]])
    D["CANDLE"] = sgn(c - o)
    # daily trend: previous day's close vs its 20-day SMA
    dc = pd.Series(c).groupby(day.values).last(); dtr = np.sign(dc - dc.rolling(20).mean()).shift(1)
    D["DAILY_TREND"] = np.nan_to_num(day.map(dtr).values.astype(float))
    # OI: previous trading day's change (bhav published after the close -> usable from the next session)
    if oi is not None:
        g = oi.copy(); g["doi"] = g.oi.diff(); g["dpx"] = g.px.diff(); g["doi5"] = g.oi.diff(5); g["dpx5"] = g.px.diff(5)
        g = g.shift(1)                                  # value for date d = change measured at the close of d-1
        m = lambda col: day.map(g[col]).values.astype(float)
        doi, dpx, doi5, dpx5 = m("doi"), m("dpx"), m("doi5"), m("dpx5")
        D["OI_buildup"] = np.where(doi > 0, sgn(dpx), 0.0)           # +1 long build-up, -1 short build-up
        D["OI_price_dir"] = sgn(dpx)                                # previous day's price direction
        D["OI_buildup5"] = np.where(doi5 > 0, sgn(dpx5), 0.0)
        D["OI_cover_unwind"] = np.where(doi < 0, sgn(dpx), 0.0)     # +1 short covering, -1 long unwinding
        U["OI_rising"] = (doi > 0).astype(float)
        U["OI_have"] = np.isfinite(doi).astype(float)
    rv = v / pd.Series(v).rolling(20).mean().shift(1).values
    U["RVOL>=1.5"] = (rv >= 1.5).astype(float); U["RVOL>=2"] = (rv >= 2).astype(float)
    pdm = np.r_[np.nan, np.diff(h)]; ndm = -np.r_[np.nan, np.diff(l)]
    pdi = E.wilder(np.where((pdm > ndm) & (pdm > 0), pdm, 0.0), 14) / atr; ndi = E.wilder(np.where((ndm > pdm) & (ndm > 0), ndm, 0.0), 14) / atr
    dx = 100 * np.abs(pdi - ndi) / np.where(pdi + ndi > 0, pdi + ndi, np.nan); adx = E.wilder(np.nan_to_num(dx), 14)
    U["ADX>25"] = (adx > 25).astype(float)
    U["ATR_high"] = (atr > pd.Series(atr).rolling(100).median().values).astype(float)
    return D, U


def trades(tf, positional):
    OI = daily_oi()
    parts = []
    for g, name in enumerate(MD.NAMES):
        d5 = MD.LM.load(name, "FIVE_MINUTE")
        b = bars(d5, tf); hm = b.time.dt.hour * 60 + b.time.dt.minute
        b = b[(hm >= 9 * 60) & (hm < 23 * 60 + 30)].reset_index(drop=True)
        d5s = d5[(d5.time.dt.hour * 60 + d5.time.dt.minute >= 540) & (d5.time.dt.hour * 60 + d5.time.dt.minute < 1410)]
        S = I.setups(b, d5s); Dv, Uv = features(b, OI.get(name))
        day = b.time.dt.normalize().values
        last = np.r_[day[1:] != day[:-1], True]
        if positional:
            last = np.zeros(len(b), bool); last[-1] = True
        grp = g * 10 ** 7 + np.cumsum(b["sw"].fillna(False).astype(bool).values) * 10 ** 4 + pd.factorize(day)[0] % 10 ** 4
        cf = MD.real_cost(name, float(d5.close.iloc[-1])) / float(d5.close.iloc[-1])
        parts.append((name, b, S, last, grp.astype(np.int64), np.full(len(b), cf), pd.DataFrame(Dv), pd.DataFrame(Uv)))
        print(name, "built", flush=True)
    keys = sorted({k for p in parts for k in p[2]})
    cat = lambda f: np.concatenate([f(p) for p in parts])
    o, h, l, c = (cat(lambda p, x=x: p[1][x].astype(float).values) for x in ("open", "high", "low", "close"))
    last, grp, cf = cat(lambda p: p[3]), cat(lambda p: p[4]), cat(lambda p: p[5])
    tt, nm = cat(lambda p: p[1]["time"].values), cat(lambda p: np.full(len(p[1]), p[0]))
    Dall = pd.concat([p[6] for p in parts], ignore_index=True); Uall = pd.concat([p[7] for p in parts], ignore_index=True)
    out = []
    for k in keys:
        sig = cat(lambda p: p[2][k][0]); st = cat(lambda p: p[2][k][1].astype(float)); tg = cat(lambda p: np.asarray(p[2][k][2], float))
        ei, nr = I.sim_lv(o, h, l, c, sig, k[1], st, tg, grp, last, cf)
        si = ei - 1                                                 # the signal bar
        T = pd.DataFrame(dict(setup=k[0], side=k[1], exit=k[2], name=nm[ei], entry=tt[ei], netR=nr))
        A = (Dall.iloc[si].reset_index(drop=True).mul(k[1]) > 0).astype(float)   # aligned with the trade
        T = pd.concat([T, A.add_prefix("d_"), Uall.iloc[si].reset_index(drop=True).add_prefix("u_")], axis=1)
        out.append(T)
    T = pd.concat(out, ignore_index=True)
    T["period"] = E.periods(T.entry.values, CUTS)
    return T


def st(r):
    r = np.asarray(r, float)
    if len(r) == 0:
        return (0, np.nan, np.nan, np.nan)
    w = r > 0
    return (len(r), round(100 * w.mean(), 1), round(r.mean(), 3), round(r[w].sum() / -r[~w].sum(), 2) if (~w).any() else np.nan)


def main(tf=15, positional=False):
    from sklearn.linear_model import LogisticRegression
    tag = f"{tf}m{'_pos' if positional else ''}"
    cache = OUT / f".cache_confirm_{tag}.pkl"
    T = pd.read_pickle(cache) if cache.exists() else trades(tf, positional)
    T.to_pickle(cache)
    T = T[T.get("u_OI_have", 1) == 1].reset_index(drop=True)           # OI known for every trade kept
    F = [x for x in T.columns if x.startswith(("d_", "u_")) and x != "u_OI_have"]
    Dd = [x for x in F if x.startswith("d_")]
    # 1. each indicator alone (pooled real setups, benchmark apart)
    ind = []
    for bench in (False, True):
        S = T[(T.setup == "BENCH_every10") == bench]
        for f in F:
            r = dict(pool="BENCHMARK" if bench else "ALL_SETUPS", indicator=f[2:])
            for p, _ in CUTS:
                a, z = S[(S.period == p) & (S[f] == 1)].netR, S[(S.period == p) & (S[f] == 0)].netR
                na, wa, ra, _ = st(a); nz, wz, rz, _ = st(z)
                r[f"{p}_n_conf"] = na; r[f"{p}_win_conf"] = wa; r[f"{p}_R_conf"] = ra; r[f"{p}_win_not"] = wz; r[f"{p}_R_not"] = rz
                r[f"{p}_lift"] = round(ra - rz, 3) if na and nz else np.nan
            r["lift_same_sign_all3"] = bool(all(np.sign(r[f"{p}_lift"]) == np.sign(r["DEV_lift"]) != 0 for p, _ in CUTS))
            ind.append(r)
    IND = pd.DataFrame(ind); IND.to_csv(OUT / f"confirm_{tag}_indicators.csv", index=False)
    # 2. weighted scores, learned on DEV, frozen after
    dev = T.period == "DEV"; real = T.setup != "BENCH_every10"
    lift = {f: T.loc[dev & real & (T[f] == 1), "netR"].mean() - T.loc[dev & real & (T[f] == 0), "netR"].mean() for f in F}
    w1 = pd.Series({f: max(v, 0) if np.isfinite(v) else 0 for f, v in lift.items()})
    T["S_W1_lift"] = T[F].values @ w1[F].values
    X = pd.get_dummies(T.setup.astype(str) + "|" + T.side.astype(str) + "|" + T.exit.astype(str)).astype(float)
    Xf = pd.concat([T[F], X], axis=1).values
    lr = LogisticRegression(C=0.5, max_iter=2000).fit(Xf[(dev & real).values], (T.netR[dev & real] > 0).values)
    T["S_W2_logit"] = lr.predict_proba(Xf)[:, 1]
    T["S_W3_equal"] = T[Dd].sum(axis=1)
    rows = []
    groups = [("ALL_SETUPS", real)] + [(f"{s}|{'BUY' if sd > 0 else 'SELL'}|{ex}", (T.setup == s) & (T.side == sd) & (T.exit == ex))
                                       for (s, sd, ex), _ in T.groupby(["setup", "side", "exit"])]
    for gname, gm in groups:
        for sc in ("NONE", "S_W1_lift", "S_W2_logit", "S_W3_equal"):
            for keep in ((1.0,) if sc == "NONE" else (0.3, 0.2, 0.1)):
                G = T[gm]
                if sc == "NONE":
                    sel = np.ones(len(G), bool)
                else:
                    thr = np.quantile(G.loc[G.period == "DEV", sc], 1 - keep) if (G.period == "DEV").any() else np.inf
                    sel = (G[sc] >= thr).values
                r = dict(group=gname, score=sc, keep_top=keep)
                for p, _ in CUTS:
                    n, w, R, pf = st(G.netR.values[sel & (G.period == p).values])
                    r.update({f"{p}_n": n, f"{p}_win": w, f"{p}_R": R, f"{p}_PF": pf})
                r["PASS"] = bool(all(r[f"{p}_n"] >= 30 and r[f"{p}_R"] > 0 and (r[f"{p}_PF"] or 0) >= 1.2 for p, _ in CUTS))
                r["WIN60_all3"] = bool(all(r[f"{p}_n"] >= 30 and r[f"{p}_win"] >= 60 and r[f"{p}_R"] > 0 for p, _ in CUTS))
                rows.append(r)
    R = pd.DataFrame(rows); R.to_csv(OUT / f"confirm_{tag}.csv", index=False)
    (OUT / f"confirm_{tag}_weights.json").write_text(pd.Series({**{f"W1:{k}": round(v, 4) for k, v in w1.items()},
                                                                  **{f"W2:{k}": round(float(c_), 4) for k, c_ in zip(F, lr.coef_[0][:len(F)])}}).to_json(indent=1))
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
    print(IND[IND.pool == "ALL_SETUPS"][["indicator", "DEV_win_conf", "DEV_lift", "VAL_win_conf", "VAL_lift", "OOS_win_conf", "OOS_lift", "lift_same_sign_all3"]].to_string(index=False))
    print(R[R.group == "ALL_SETUPS"].to_string(index=False))
    print("PASS:", int(R.PASS.sum()), "of", len(R[R.score != "NONE"]), "| WIN60:", int(R.WIN60_all3.sum()))
    print(R[R.score != "NONE"].sort_values("OOS_R", ascending=False).head(15).to_string(index=False))


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]) if a else 15, len(a) > 1 and a[1] == "pos")
