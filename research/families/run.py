"""FAMILIES – new strategy families beyond RSI / divergence (owner 11-Nov, cycle 3 · 9). Research only.
Every rule is pre-registered here (parameters are textbook values, not searched); BUY and SELL apart; realistic costs;
next-bar-open entries; stop = structure (the setup's own invalidation level +/- 0.1 ATR, kept 0.5–3 ATR); 2R and 3R
targets; intraday timeframes are flat by the session end. Markets: MCX 15-min (intraday) and 1-hour, NSE index futures
1-hour, NSE stock futures daily, NSE cash daily (BUY only). Logic behind each family in brackets.
  F1 ORB              close beyond the opening range (MCX: 09:00–09:30; index: first hour) before mid-session, first
                      break of the day [overnight information is resolved early; a clean break shows initiative flow]
  F2 ORB_FAIL         price trades beyond the opening range but closes back inside within 2 bars -> fade [trapped
                      breakout traders exit; stops above the range are cleared]
  F3 SWEEP_MSS        low below the previous session low (daily: 20-day low), then within 3 bars a close above the sweep
                      bar's high (market-structure shift) -> BUY; mirror SELL [stop-run liquidity, then reversal]
  F4 VWAP_RECLAIM     close crosses above VWAP after >= 4 bars below -> BUY; VWAP_REJECT: high reaches VWAP from below,
                      bearish close below it -> SELL (session VWAP intraday, 20-bar volume-weighted price daily)
                      [VWAP is the average price of the day's participants; reclaim = buyers back in control]
  F5 SQUEEZE_BREAK    20-bar Bollinger width the lowest of 120 bars within the last 5 bars, then a close beyond the
                      10-bar high / low [volatility clusters: contraction precedes expansion]
  F6 CLIMAX_ABSORB    volume >= 3x the 20-bar average, bar range >= 1.5 ATR, after a 5-bar fall, close in the top 40 % of
                      the bar -> BUY (mirror SELL) [selling exhausted into strong demand]
  F7 TREND_PULLBACK   EMA50 > EMA200 and close > EMA200; low touches EMA20 and the bar closes up above EMA20 -> BUY
                      (mirror SELL) [buy the dip in an established trend]
  F8 SR_RETEST        close above the prior 20-bar high, then within 5 bars a retest (low <= level + 0.25 ATR) that closes
                      above the level -> BUY (mirror SELL) [old resistance becomes support]
  F9 RS_ROTATION      (cash, monthly portfolio) top 2 sectors by 63-day return, the 5 strongest stocks (126-day return)
                      in them, equal weight, MA100 market filter, delivery costs [sector momentum]
Gate: profit and PF >= 1.2 in DEV, VALID and OOS, >= 30 trades each, >= 100 total; BH-FDR 10 % over every test.
python -m research.families.run [mcx15 mcx1h index stockfut cash rs]  ->  results/families.csv"""
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rsidiv import engine as E  # noqa: E402
from research.rsirev import run as RR  # noqa: E402
from research.cycle2 import common as C, cont_buy as CB  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"; OUT.mkdir(parents=True, exist_ok=True)


def session_or(b, tf):
    """opening-range high / low per day: MCX 15-min = first 2 bars, index 1h = first bar."""
    t = pd.to_datetime(b["time"]); day = t.dt.normalize().values
    k = pd.Series(np.arange(len(b))).groupby(day).cumcount().values
    nbar = 2 if tf == "15m" else 1
    h, l = b["high"].astype(float).values, b["low"].astype(float).values
    orh = pd.Series(np.where(k < nbar, h, np.nan)).groupby(day).transform("max").values
    orl = pd.Series(np.where(k < nbar, l, np.nan)).groupby(day).transform("min").values
    return orh, orl, k, nbar, day


def families(b, tf, intraday):
    o, h, l, c, v = (b[x].astype(float).reset_index(drop=True) for x in ("open", "high", "low", "close", "volume"))
    n = len(c); pc = c.shift(1)
    atr = pd.Series(E.wilder(np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs())).values, 14))
    S, lvl = {}, {}
    hm = (pd.to_datetime(b["time"]).dt.hour * 60 + pd.to_datetime(b["time"]).dt.minute).values
    if intraday:
        orh, orl, k, nbar, day = session_or(b, tf)
        late = hm >= (15 * 60 if tf == "15m" else 13 * 60)
        up = (c > orh) & (k >= nbar) & ~late; dn = (c < orl) & (k >= nbar) & ~late
        first_up = up & (pd.Series(up.values).groupby(day).cumsum().values == 1)
        first_dn = dn & (pd.Series(dn.values).groupby(day).cumsum().values == 1)
        S["F1_ORB", 1], S["F1_ORB", -1] = first_up.values, first_dn.values
        lvl["F1_ORB", 1], lvl["F1_ORB", -1] = orl, orh
        pierce_up = (h > orh) & (k >= nbar); pierce_dn = (l < orl) & (k >= nbar)
        back_dn = (c < orh) & (pierce_up.shift(1, fill_value=False) | pierce_up.shift(2, fill_value=False)) & ~late
        back_up = (c > orl) & (pierce_dn.shift(1, fill_value=False) | pierce_dn.shift(2, fill_value=False)) & ~late
        S["F2_ORB_FAIL", -1] = (back_dn & ~up).values; S["F2_ORB_FAIL", 1] = (back_up & ~dn).values
        lvl["F2_ORB_FAIL", -1] = h.rolling(3).max().values; lvl["F2_ORB_FAIL", 1] = l.rolling(3).min().values
        dser = pd.Series(l.values).groupby(day).transform("min"); dhig = pd.Series(h.values).groupby(day).transform("max")
        ud = pd.Series(day).drop_duplicates().values
        pdl = pd.Series(day).map(pd.Series(dser.groupby(day).first().values, index=ud).shift(1)).values
        pdh = pd.Series(day).map(pd.Series(dhig.groupby(day).first().values, index=ud).shift(1)).values
        ref_lo, ref_hi = pdl, pdh
        tp = (h + l + c) / 3; vw = (tp * v).groupby(day).cumsum() / v.groupby(day).cumsum().replace(0, np.nan)
    else:
        ref_lo, ref_hi = l.shift(1).rolling(20).min().values, h.shift(1).rolling(20).max().values
        tp = (h + l + c) / 3; vw = (tp * v).rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)
    # F3 sweep + structure shift
    for sd in (1, -1):
        sweep = (l.values < ref_lo) if sd > 0 else (h.values > ref_hi)
        z = np.zeros(n, bool); lv = np.full(n, np.nan)
        for i in np.where(sweep)[0]:
            for j in range(i + 1, min(i + 4, n)):
                if (sd > 0 and c.iloc[j] > h.iloc[i]) or (sd < 0 and c.iloc[j] < l.iloc[i]):
                    if not intraday or day[j] == day[i]:
                        z[j] = True; lv[j] = l.iloc[i: j + 1].min() if sd > 0 else h.iloc[i: j + 1].max()
                    break
        S["F3_SWEEP_MSS", sd] = z; lvl["F3_SWEEP_MSS", sd] = lv
    below = (c < vw)
    S["F4_VWAP_RECLAIM", 1] = ((c > vw) & (below.shift(1).rolling(4).sum() == 4)).fillna(False).values
    lvl["F4_VWAP_RECLAIM", 1] = l.rolling(4).min().values
    S["F4_VWAP_REJECT", -1] = ((h >= vw) & (c < vw) & (c < o) & (c.shift(1) < vw.shift(1))).fillna(False).values
    lvl["F4_VWAP_REJECT", -1] = h.rolling(2).max().values
    mid = c.rolling(20).mean(); wd = 4 * c.rolling(20).std() / mid
    sq = (wd <= wd.rolling(120).min() * 1.0001).rolling(5).max() > 0
    S["F5_SQUEEZE_BREAK", 1] = (sq & (c > h.shift(1).rolling(10).max())).fillna(False).values
    S["F5_SQUEEZE_BREAK", -1] = (sq & (c < l.shift(1).rolling(10).min())).fillna(False).values
    lvl["F5_SQUEEZE_BREAK", 1] = l.rolling(10).min().values; lvl["F5_SQUEEZE_BREAK", -1] = h.rolling(10).max().values
    rv = v / v.rolling(20).mean().shift(1); big = (h - l) >= 1.5 * atr; pos = (c - l) / (h - l).replace(0, np.nan)
    S["F6_CLIMAX_ABSORB", 1] = ((rv >= 3) & big & (c.shift(1) < c.shift(6)) & (pos >= 0.6)).fillna(False).values
    S["F6_CLIMAX_ABSORB", -1] = ((rv >= 3) & big & (c.shift(1) > c.shift(6)) & (pos <= 0.4)).fillna(False).values
    lvl["F6_CLIMAX_ABSORB", 1] = l.values; lvl["F6_CLIMAX_ABSORB", -1] = h.values
    e20, e50, e200 = (c.ewm(span=s_, adjust=False).mean() for s_ in (20, 50, 200))
    S["F7_TREND_PULLBACK", 1] = ((e50 > e200) & (c > e200) & (l <= e20) & (c > e20) & (c > o)).fillna(False).values
    S["F7_TREND_PULLBACK", -1] = ((e50 < e200) & (c < e200) & (h >= e20) & (c < e20) & (c < o)).fillna(False).values
    lvl["F7_TREND_PULLBACK", 1] = l.rolling(3).min().values; lvl["F7_TREND_PULLBACK", -1] = h.rolling(3).max().values
    for sd in (1, -1):
        br = (c > h.shift(1).rolling(20).max()) if sd > 0 else (c < l.shift(1).rolling(20).min())
        lev = (h.shift(1).rolling(20).max() if sd > 0 else l.shift(1).rolling(20).min()).values
        z = np.zeros(n, bool); lv = np.full(n, np.nan)
        for i in np.where(br.fillna(False).values)[0]:
            L_ = lev[i]
            for j in range(i + 1, min(i + 6, n)):
                if intraday and day[j] != day[i]:
                    break
                if sd > 0 and l.iloc[j] <= L_ + 0.25 * atr.iloc[j] and c.iloc[j] > L_:
                    z[j] = True; lv[j] = min(l.iloc[j], L_); break
                if sd < 0 and h.iloc[j] >= L_ - 0.25 * atr.iloc[j] and c.iloc[j] < L_:
                    z[j] = True; lv[j] = max(h.iloc[j], L_); break
        S["F8_SR_RETEST", sd] = z; lvl["F8_SR_RETEST", sd] = lv
    risk = {}
    for k, lv in lvl.items():
        sd = k[1]; lv = pd.Series(lv)
        d = (c - lv + 0.1 * atr) if sd > 0 else (lv - c + 0.1 * atr)
        risk[k] = d.clip(lower=0.5 * atr, upper=3 * atr).fillna(1.0 * atr).values
    return S, risk


def mcx15():
    from research.program import mcx_disc as MD
    from research.mcxhw.search import bars
    out = []
    for g, name in enumerate(MD.NAMES):
        d5 = MD.LM.load(name, "FIVE_MINUTE"); b = bars(d5, 15)
        hm = b["time"].dt.hour * 60 + b["time"].dt.minute
        b = b[(hm >= 9 * 60) & (hm <= 23 * 60 + 15)].reset_index(drop=True)
        cf = MD.real_cost(name, float(d5.close.iloc[-1])) / float(d5.close.iloc[-1])
        day = b["time"].dt.normalize().values.astype("datetime64[D]").astype(np.int64)
        out.append(dict(b=b, live=np.ones(len(b), bool), costf=np.full(len(b), cf), expid=np.zeros(len(b), np.int64), grp=g * 10 ** 6 + day, name=name))
    return out


SETS = {"mcx15": ("MCX", "15m", lambda: mcx15(), 400, True, (1, -1), [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")]),
        "mcx1h": ("MCX", "1h", lambda: RR.mcx("1h"), 45, False, (1, -1), [("DEV", "2022-01-01"), ("VAL", "2025-01-01"), ("OOS", "2026-01-01")]),
        "index": ("NSE_INDEX_FUT", "1h", lambda: RR.index("1h"), 21, True, (1, -1), [("DEV", "2022-07-01"), ("VAL", "2024-07-01"), ("OOS", "2025-07-01")]),
        "stockfut": ("NSE_STOCK_FUT", "1d", lambda: RR.stockfut("1d"), 15, False, (1, -1), [("DEV", "2018-01-01"), ("VAL", "2022-01-01"), ("OOS", "2024-01-01")]),
        "cash": ("NSE_CASH", "1d", None, 15, False, (1,), [("DEV", "2005-01-01"), ("VAL", "2015-01-01"), ("OOS", "2020-01-01")])}


class MultiPool(E.Pool):
    """one copy of the prices; a separate risk array and signal list per (family, side)."""

    def __init__(self):
        super().__init__(); self.rk2 = {}

    def add2(self, b, S, R, grp, costf, expid, name):
        for k in S:
            self.rk2.setdefault(k, []).append(R[k])
        n0 = self.n
        self.add(b, {(k[0], "x", "x", k[1]): x for k, x in S.items()}, {1: np.zeros(len(b)), -1: np.zeros(len(b))}, grp, costf, expid, name)
        for k in S:
            if len(self.rk2[k]) and len(self.rk2[k][-1]) != len(b):
                raise ValueError("risk length")

    def done(self):
        self.freeze(); self.rk2 = {k: np.concatenate(v).astype(float) for k, v in self.rk2.items()}
        return self

    def run2(self, k, R, hold):
        key = (k[0], "x", "x", k[1])
        if key not in self.idx:
            return pd.DataFrame(columns=["netR", "entry", "name"])
        sig = np.zeros(self.n, np.bool_); sig[self.idx[key]] = True
        rk = self.rk2[k]
        ei, xi, nr, gr, cr = E.sim(self.o, self.h, self.l, self.c, sig, k[1], rk, R, self.grp, hold, self.costf, self.expid)
        return pd.DataFrame(dict(i=ei, name=self.name[ei], entry=self.t[ei], exit=self.t[xi], bars=xi - ei + 1, netR=nr, grossR=gr, costR=cr,
                                 ret=nr * rk[ei - 1] / np.where(self.o[ei] > 0, self.o[ei], np.nan)))


def run_set(key):
    mk, tf, load, hold, intraday, sides, cuts = SETS[key]
    frames = CB.cash_frames("1d", C.cash_context()) if key == "cash" else load()
    P = MultiPool()
    for f in frames:
        b = f["b"].reset_index(drop=True)
        S, risk = families(b, tf, intraday)
        live = np.asarray(f["live"], bool)
        S = {k: x & live for k, x in S.items() if k[1] in sides}
        grp = f["grp"]
        if intraday and key == "index":                       # hourly index: flat by the session end
            grp = np.asarray(f["grp"]) * 10 ** 6 + pd.to_datetime(b["time"]).dt.normalize().values.astype("datetime64[D]").astype(np.int64) % 10 ** 6
        P.add2(b, S, risk, grp, f["costf"], f["expid"], f["name"])
    P.done(); rows = []
    for k in sorted(P.rk2):
        fam, sd = k
        for R in (2.0, 3.0):
            T = P.run2(k, R, hold)
            if len(T) < 10:
                rows.append(dict(market=mk, tf=tf, family=fam, side="BUY" if sd > 0 else "SELL", target_R=R, all_n=len(T), PASS=False)); continue
            rw = E.row((fam, "x", "x", sd), T, cuts); rw.update(market=mk, tf=tf, side="BUY" if sd > 0 else "SELL", target_R=R)
            rows.append(rw)
    every = np.zeros(P.n, np.bool_); every[::10] = True
    for sd in sides:
        for R in (2.0, 3.0):
            atr_like = np.nanmedian(np.vstack([P.rk2[k] for k in P.rk2 if k[1] == sd]), axis=0)
            ei, xi, nr, gr, cr = E.sim(P.o, P.h, P.l, P.c, every, sd, atr_like, R, P.grp, hold, P.costf, P.expid)
            T = pd.DataFrame(dict(name=P.name[ei], entry=P.t[ei], netR=nr, ret=0.0, costR=cr))
            rw = E.row(("BENCH_every_10th_bar", "x", "x", sd), T, cuts); rw.update(market=mk, tf=tf, side="BUY" if sd > 0 else "SELL", target_R=R, PASS=False)
            rows.append(rw)
    return rows


def rs_rotation():
    cs = C.cash_context(); W = cs["W"]; reg = cs["reg"]
    c, el = W["close"], W["elig"].astype(bool); o = W["open"]
    sec = W["symbol"].map(cs["sector_of"]).fillna("")
    S = pd.DataFrame({s: c[list(cols)].pct_change(fill_method=None).where(el[list(cols)]).mean(axis=1) for s, cols in sec.groupby(sec).groups.items() if s}).fillna(0).add(1).cumprod()
    days = c.index; month_ends = pd.Series(days, index=days).groupby(days.to_period("M")).last().values
    rows = []
    for a, b_ in zip(month_ends[:-1], month_ends[1:]):
        ia, ib = days.get_loc(a), days.get_loc(b_)
        if ia < 252 or ib + 1 >= len(days) or not bool(reg["mkt_ma100"].iloc[ia]):
            rows.append(dict(start=days[min(ia + 1, len(days) - 1)], ret=0.0, n=0)); continue
        top = (S.iloc[ia] / S.iloc[ia - 63] - 1).sort_values(ascending=False).index[:2]
        cand = [k for k in c.columns if sec[k] in set(top) and el.iloc[ia][k]]
        r126 = (c.iloc[ia][cand] / c.iloc[ia - 126][cand] - 1).dropna().sort_values(ascending=False)
        pick = list(r126.index[:5])
        if not pick:
            rows.append(dict(start=days[ia + 1], ret=0.0, n=0)); continue
        r = (o.iloc[ib + 1][pick] / o.iloc[ia + 1][pick] - 1).fillna(c.iloc[ib][pick] / o.iloc[ia + 1][pick] - 1)
        rows.append(dict(start=days[ia + 1], ret=float(r.mean()) - 0.00393, n=len(pick)))
    R = pd.DataFrame(rows)
    out = {}
    for lab, (x, y) in dict(DEV=("2006-01-01", "2015-01-01"), VAL=("2015-01-01", "2020-01-01"), OOS=("2020-01-01", "2027-01-01")).items():
        q = R[(R.start >= x) & (R.start < y)].ret
        eq = (1 + q).cumprod(); yrs = len(q) / 12
        out[lab] = dict(months=len(q), CAGR=round(100 * (eq.iloc[-1] ** (1 / yrs) - 1), 1) if len(q) else None,
                        sharpe=round(float(q.mean() / q.std() * np.sqrt(12)), 2) if q.std() > 0 else None,
                        maxDD=round(float(100 * (eq / eq.cummax() - 1).min()), 1))
    from research.cashq import mom_volume as MV
    d = MV.D(*MV.load()); MR, _ = MV.backtest(d, "B0", 10, "M")
    MR["start"] = pd.to_datetime(MR.start)
    for lab, (x, y) in dict(DEV=("2006-01-01", "2015-01-01"), VAL=("2015-01-01", "2020-01-01"), OOS=("2020-01-01", "2027-01-01")).items():
        q = MR[(MR.start >= x) & (MR.start < y)].ret; eq = (1 + q).cumprod(); yrs = len(q) / 12
        out[lab]["momentum_B0_CAGR"] = round(100 * (eq.iloc[-1] ** (1 / yrs) - 1), 1); out[lab]["momentum_B0_sharpe"] = round(float(q.mean() / q.std() * np.sqrt(12)), 2)
    j = R.assign(m=pd.to_datetime(R.start).dt.to_period("M")).set_index("m").ret.groupby(level=0).sum()
    mm = MR.assign(m=MR.start.dt.to_period("M")).set_index("m").ret.groupby(level=0).sum()
    out["corr_with_momentum"] = round(float(pd.concat([j, mm], axis=1).dropna().corr().iloc[0, 1]), 3)
    return out


def main(keys):
    import json
    rows, t0 = [], time.time()
    f = OUT / "families.csv"
    if f.exists():
        old = pd.read_csv(f); rows = [r for r in old.to_dict("records") if r["market"] + r["tf"] not in {SETS[k][0] + SETS[k][1] for k in keys if k in SETS}]
    for k in keys:
        if k == "rs":
            res = rs_rotation(); json.dump(res, open(OUT / "rs_rotation.json", "w"), indent=1); print("RS rotation", res, flush=True); continue
        rows += run_set(k); print(k, f"{time.time() - t0:.0f}s", flush=True)
        L = pd.DataFrame(rows); L.to_csv(f, index=False)
    L = pd.DataFrame(rows)
    if len(L) and "t_day" in L:
        ok = L.t_day.notna(); p = E.pvals(L.t_day.fillna(0).values)
        L["p"] = np.where(ok, p, np.nan); L["FDR10"] = C.bh(L.p.values); L["HOLM5"] = False
        L.loc[ok, "HOLM5"] = E.holm(L.loc[ok, "p"].values)
        L.to_csv(f, index=False)


if __name__ == "__main__":
    main(sys.argv[1:] or ["mcx15", "mcx1h", "index", "stockfut", "cash", "rs"])
