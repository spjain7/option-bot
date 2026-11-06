"""EQ-001 – NSE cash-equity DELIVERY (swing) strategy research. Intraday ORB is separate (eq_orb.py); results never mixed.

Pre-registered (before seeing results):
  Strategies (BUY only – cash delivery cannot be shorted overnight):
    A1 PDH   strong close (top 30 % of range, volume >= 1.5x, close > EMA50) -> buy-stop above that day's high (next session)
    A2 BO20  close > 20-day high, volume >= 1.5x          A3 BO55  close > 55-day high, volume >= 1.5x
    B  RET   within 10 sessions of a 20-day breakout, low back to the level (<= +0.3 ATR), close above it, bullish close
    D  PB    EMA20 > EMA50 > EMA200, low touches EMA20 (+0.2 ATR), close > EMA20, close in top 40 % of range
    E  MOMO  63-day relative strength (vs NIFTY) in the top 20 % of the universe, close > EMA50 & EMA200, 10-day range
             <= 3 ATR (consolidation), then close > 10-day high with volume >= 1.5x and close in top 25 %
    F  REV   RSI(7) touched 30 in 3 sessions, bullish reversal candle, close > EMA200 (no weak stocks)
    G  RS    RS top 10 % AND its industry's median RS top 30 %, close > 20-day high, volume >= 1.2x
  Grid: entry {next open, buy-stop above signal high (1 session for A1, 3 otherwise; cancelled if signal low breaks)}
        x stop {2 ATR, structure = signal low - 0.1 ATR (0.3-3 ATR)} x exit {2R, 3R, 3-ATR trail} x max 20 sessions
        x market regime filter {all, NIFTY bull (close > EMA200 & EMA50 > EMA200), not bear}.
  Costs: delivery round trip (eq_data.cost_frac) incl. 0.05 % slippage per side; gaps through the stop fill at the open.
  Validation: 4 chronological blocks; PASS = positive in every block, BH q < 0.10 over all combinations, n >= 300,
  >= 55 % of stocks with trades positive. Universe point-in-time by trailing turnover (eq_data.universe_mask).
python research/program/eq_research.py [bhav|eq|fut]   (bhav = NSE cash bhavcopy 2005-26, the final source)   (fut = smoke test on the 2022-26 stock-futures daily data)"""
import sys
import time
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit
from scipy import stats
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import eq_data as ED  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
STRATS = ("A1_PDH", "A2_BO20", "A3_BO55", "B_RET", "D_PB", "E_MOMO", "F_REV", "G_RS")
ENTRIES = ("OPEN", "STOP"); STOPS = ("ATR2", "STRUCT"); EXITS = {"2R": 2, "3R": 3, "TR": 0}; REGIMES = ("all", "bull", "notbear")


# ── data ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def load_all(source="eq"):
    """-> dict sym -> daily frame (adjusted), industry map, NIFTY frame, split log"""
    log, D = [], {}
    if source == "bhav":                          # NSE cash bhavcopy: exact corporate actions, point-in-time incl. delisted
        from research.program import eq_bhav as EB
        P = EB.panel(); A = EB.adjusted(P)
        rep = EB.verify(P, A); print("data check:", rep)
        uf = ED.EQ / "universe.csv"
        imap = dict(zip(*pd.read_csv(uf)[["symbol", "industry"]].fillna("").values.T)) if uf.exists() else {}
        D = {}
        for k, d in A.items():
            sym = d.symbol.iat[-1]
            D[sym] = d[["time", "open", "high", "low", "close", "volume"]].copy()
        ind = {s: imap.get(s, "") for s in D}
        nifty = ED.load("NIFTY") if (ED.EQ / "NIFTY_ONE_DAY.csv.gz").exists() else EB.market(A)
        return D, ind, nifty, log
    if source == "eq":
        u = pd.read_csv(ED.EQ / "universe.csv")
        ind = dict(zip(u.symbol, u.industry.fillna("")))
        for s in u.symbol:
            d = ED.load(s)
            if d is not None and len(d) > 300:
                D[s] = ED.adjust_splits(d, log, s)
        nifty = ED.load("NIFTY")
    else:
        from research.program import emax as EX, search_all as SA, harness as H
        ED.MIN_TURNOVER = 0.0                     # futures volume is in contracts – turnover filter not meaningful here
        ind = {}
        for job in [j for j in EX.jobs() if j[0] == "stk"]:
            try:
                for mk, tf, f, c_, fd in SA.frames_for(job):
                    if tf == "1d" and len(f) > 300:
                        D[job[1]] = ED.adjust_splits(ED.clean(f[["time", "open", "high", "low", "close", "volume"]].copy()), log, job[1])
            except Exception:
                pass
        nifty = ED.clean(H.nseidx("NIFTY")[["time", "open", "high", "low", "close", "volume"]].copy())
    return D, ind, nifty, log


def regime(nifty):
    c = nifty.close
    e50, e200 = c.ewm(span=50, adjust=False).mean(), c.ewm(span=200, adjust=False).mean()
    bull = (c > e200) & (e50 > e200); bear = (c < e200) & (e50 < e200)
    atrp = I.atr(nifty, 14) / c; hv = atrp > atrp.rolling(250, min_periods=100).median()
    r = pd.DataFrame(dict(time=nifty.time, bull=bull.shift(1), bear=bear.shift(1), hivol=hv.shift(1), ret63=c.pct_change(63)))
    return r.set_index("time")


def cross_section(D, ind, R):
    """63-day return relative to NIFTY, percentile among the eligible universe each day; industry median percentile."""
    rows = []
    for s, d in D.items():
        x = pd.DataFrame(dict(time=d.time, rs=d.close.pct_change(63).values, elig=ED.universe_mask(d)))
        x["sym"] = s; rows.append(x)
    X = pd.concat(rows)
    X = X.merge(R[["ret63"]], left_on="time", right_index=True, how="left")
    X["rs"] = X.rs - X.ret63
    X.loc[~X.elig, "rs"] = np.nan
    X["rs_pct"] = X.groupby("time").rs.rank(pct=True)
    X["ind"] = X.sym.map(ind).fillna("")
    im = X[X.ind != ""].groupby(["time", "ind"]).rs_pct.median().rename("ind_pct")
    X = X.merge(im, left_on=["time", "ind"], right_index=True, how="left")
    return {s: g.set_index("time")[["rs_pct", "ind_pct"]] for s, g in X.groupby("sym")}


def setups(d, cs):
    o, h, l, c = (d[x].values.astype(float) for x in ("open", "high", "low", "close"))
    v = d.volume.values.astype(float); n = len(c)
    a = I.atr(d, 14).values
    cs_ = cs.reindex(d.time.values)
    rs, ip = cs_.rs_pct.values, cs_.ind_pct.values
    rng = np.where(h - l > 0, h - l, np.nan); pos = (c - l) / rng
    volx = v / pd.Series(v).rolling(20).mean().shift(1).values
    S = pd.Series(c)
    e20, e50, e200 = (S.ewm(span=k, adjust=False).mean().values for k in (20, 50, 200))
    hh = lambda k: pd.Series(h).shift(1).rolling(k).max().values  # noqa: E731
    hh10, hh20, hh55 = hh(10), hh(20), hh(55)
    rsi7 = I.rsi(S, 7).values
    out = {}
    vx = np.nan_to_num(volx)
    out["A1_PDH"] = (pos >= 0.7) & (vx >= 1.5) & (c > e50)
    out["A2_BO20"] = (c > hh20) & (vx >= 1.5)
    out["A3_BO55"] = (c > hh55) & (vx >= 1.5)
    bo = c > hh20
    lvl = pd.Series(np.where(bo, hh20, np.nan)).ffill().values
    recent = pd.Series(bo).rolling(10).max().shift(1).fillna(0).values.astype(bool)
    out["B_RET"] = recent & ~bo & (l <= lvl + 0.3 * a) & (c > lvl) & (pos >= 0.5)
    out["D_PB"] = (e20 > e50) & (e50 > e200) & (l <= e20 + 0.2 * a) & (c > e20) & (pos >= 0.6)
    rng10 = pd.Series(h).rolling(10).max().shift(1).values - pd.Series(l).rolling(10).min().shift(1).values
    out["E_MOMO"] = (np.nan_to_num(rs) >= 0.8) & (c > e50) & (c > e200) & (rng10 <= 3 * a) & (c > hh10) & (vx >= 1.5) & (pos >= 0.75)
    out["F_REV"] = (pd.Series(rsi7).rolling(3).min().values <= 30) & (c > o) & (pos >= 0.5) & (c > e200)
    ipc = np.where(np.isnan(ip), 1.0, ip)                       # sector unknown (no map / delisted) -> RS condition only
    out["G_RS"] = (np.nan_to_num(rs) >= 0.9) & (ipc >= 0.7) & (c > hh20) & (vx >= 1.2)
    el = ED.universe_mask(d)
    return {k: np.nan_to_num(m.astype(float)).astype(bool) & el for k, m in out.items()}, a


@njit(cache=True)
def sim(o, h, l, c, atr, idx, entry, win, stop, exitc, maxh, costf):
    n = len(c); oi = np.empty(len(idx), np.int64); ox = np.empty(len(idx), np.int64); orr = np.empty(len(idx)); k = 0; busy = -1
    for q in range(len(idx)):
        i = idx[q]
        if i <= busy or i + 2 >= n or not atr[i] > 0:
            continue
        a = atr[i]; L = h[i]; V = l[i]; j = -1; e = 0.0
        if entry == 0:
            j = i + 1; e = o[j]
        else:
            for t in range(i + 1, min(i + 1 + win, n)):
                if o[t] < V or (l[t] < V and not h[t] > L):
                    break
                if h[t] > L:
                    j = t; e = max(L, o[t]); break
            if j < 0 or e - L > 0.5 * a:
                continue
        st = e - 2.0 * a if stop == 0 else V - 0.1 * a
        R = e - st
        if not (R > 0.3 * a and R < 3.0 * a):
            continue
        tgt = e + exitc * R if exitc > 0 else 1e18
        best = e; px = 0.0; t = j; got = False
        while t < n:
            if t > j and o[t] <= st:
                px = o[t]; got = True; break
            if l[t] <= st:
                px = st; got = True; break
            if exitc > 0 and (t > j or entry == 0) and h[t] >= tgt:
                px = o[t] if (t > j and o[t] >= tgt) else tgt; got = True; break
            if exitc == 0:
                best = max(best, h[t]); ns = best - 3.0 * atr[t]
                if ns > st:
                    st = ns
            if t - j >= maxh:
                px = c[t]; got = True; break
            t += 1
        if not got:
            px = c[n - 1]; t = n - 1
        oi[k] = i; ox[k] = t; orr[k] = (px - e - costf * e) / R; k += 1
        busy = t
    return oi[:k], orr[:k], ox[:k]


def blocks(t, src):
    cuts = {"eq": [np.datetime64("2013-01-01"), np.datetime64("2018-01-01"), np.datetime64("2022-01-01")],
            "bhav": [np.datetime64("2011-01-01"), np.datetime64("2016-01-01"), np.datetime64("2021-01-01")]}.get(
        src, [np.datetime64("2023-07-01"), np.datetime64("2024-07-01"), np.datetime64("2025-07-01")])
    return np.searchsorted(np.array(cuts), t, side="right")


def run(src="eq"):
    t0 = time.time()
    D, ind, nifty, log = load_all(src)
    R = regime(nifty)
    CS = cross_section(D, ind, R)
    cf = ED.cost_frac("delivery")
    rows, trades = [], []
    for s, d in D.items():
        d = d.reset_index(drop=True)
        M, a = setups(d, CS[s])
        rsv = CS[s].reindex(d.time.values).rs_pct.values
        vv = d.volume.values.astype(float); vxx = vv / pd.Series(vv).rolling(20).mean().shift(1).values
        to60 = (d.close * d.volume).rolling(60, min_periods=20).median().shift(1).values
        ret = d.close.pct_change().values
        o, h, l, c = (d[x].values.astype(np.float64) for x in ("open", "high", "low", "close"))
        a = np.nan_to_num(a).astype(np.float64)
        t = d.time.values
        rg = R.reindex(d.time.values)
        bull = rg.bull.fillna(False).values.astype(bool); bear = rg.bear.fillna(False).values.astype(bool)
        for st_, m in M.items():
            for rf in REGIMES:
                mm = m & (bull if rf == "bull" else (~bear if rf == "notbear" else True))
                idx = np.flatnonzero(mm).astype(np.int64)
                if len(idx) < 3:
                    continue
                for en, sp, ex in product(range(2), range(2), EXITS):
                    oi, rr, xx = sim(o, h, l, c, a, idx, en, 1 if st_ == "A1_PDH" else 3, sp, EXITS[ex], 20, cf)
                    if not len(oi):
                        continue
                    b = blocks(t[oi], src)
                    for k in range(4):
                        x = rr[b == k]
                        if len(x):
                            rows.append((s, st_, rf, ENTRIES[en], STOPS[sp], ex, k, len(x), x.sum(), (x ** 2).sum(), (x > 0).sum(), x[x > 0].sum(), -x[x <= 0].sum()))
                    if rf == "all":                     # regime filters are re-applied by date in eq_top5.py
                        trades += [(s, st_, rf, ENTRIES[en], STOPS[sp], ex, t[i], t[x_], r, rsv[i], vxx[i], to60[i], a[i] / c[i])
                                   for i, r, x_ in zip(oi, rr, xx)]
    A = pd.DataFrame(rows, columns=["sym", "strat", "regime", "entry", "stop", "exit", "block", "n", "s", "ss", "w", "gw", "gl"])
    T = pd.DataFrame(trades, columns=["sym", "strat", "regime", "entry", "stop", "exit", "time", "exit_time", "R", "rs", "volx", "turnover", "atr_pct"])
    tag = {"eq": "eq", "bhav": "eqbhav"}.get(src, "eqfut")
    T.to_parquet(OUT / f"{tag}_trades.parquet") if False else T.to_csv(OUT / f"{tag}_trades.csv.gz", index=False)
    S = summarise(A)
    S.to_csv(OUT / f"{tag}_summary.csv", index=False)
    pd.DataFrame(log, columns=["sym", "date", "ratio"]).to_csv(OUT / f"{tag}_splits.csv", index=False)
    print(f"[{(time.time() - t0) / 60:.1f} min] stocks {len(D)} · splits adjusted {len(log)} · combinations {len(S)} · PASS {int(S.PASS.sum())}")
    return S, T


def summarise(A):
    K = ["strat", "regime", "entry", "stop", "exit"]
    g = A.groupby(K + ["block"])[["n", "s", "ss", "w", "gw", "gl"]].sum()
    tot = g.groupby(level=list(range(len(K)))).sum()
    S = pd.DataFrame(dict(n=tot.n, win=100 * tot.w / tot.n, R=tot.s / tot.n, PF=tot.gw / tot.gl.replace(0, np.nan)))
    sd = np.sqrt(np.maximum(tot.ss / tot.n - S.R ** 2, 1e-9))
    S["t"] = (S.R / (sd / np.sqrt(tot.n))).astype(float); S["p"] = stats.t.sf(S.t.values, np.maximum(tot.n.values.astype(float) - 1, 1))
    for k in range(4):
        x = g.xs(k, level="block") if k in g.index.get_level_values("block") else None
        S[f"b{k}_n"] = x.n if x is not None else 0
        S[f"b{k}_R"] = (x.s / x.n) if x is not None else np.nan
    S = S.reset_index()
    nm = A.groupby(K + ["sym"])[["s"]].sum().reset_index()
    nm = nm.assign(pos=nm.s > 0).groupby(K).pos.mean().rename("stocks_pos").reset_index()
    S = S.merge(nm, on=K, how="left").sort_values("p").reset_index(drop=True)
    m = len(S); S["q"] = (S.p * m / (np.arange(m) + 1))[::-1].cummin()[::-1].clip(upper=1)
    S["all_blocks"] = (S[[f"b{k}_R" for k in range(4)]] > 0).all(axis=1)
    S["PASS"] = S.all_blocks & (S.q < 0.10) & (S.n >= 300) & (S.stocks_pos >= 0.55)
    return S


if __name__ == "__main__":
    run((sys.argv[1:] or ["eq"])[0])
