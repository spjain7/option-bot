"""TV-SCRIPTS-001 (19-Nov-2026, owner: "search Chartink and TradingView scripts, find what works best"). The most-liked
TradingView community scripts and the most common Chartink scan types, written from their published logic, tested as SELL
signals on the 181 F&O stock futures (research data 2022-26, front month, never through a roll, 2x costs, next-open entry,
0.5-ATR chase limit, stop first – the same harness as the live rules; sell_exits.run).
TradingView (likes per pickmytrade.io): Squeeze Momentum (LazyBear, 97k) · SMC break of structure (LuxAlgo, 78k) ·
  MACD cross (ChrisMoody, 70k) · SuperTrend 10/3 (KivancOzbilgic, 55k) · WaveTrend 10/21 (LazyBear, 52k) · ADX/DI 14
  (BeikabuOyaJi, 42k) · Bollinger + RSI (ChartArt, 38k) · MA cross EMA 20/50 (ChrisMoody, 36k) · S/R breaks with volume
  (LuxAlgo, 34k) · UT Bot (key 1, ATR 10) · QQE MOD (6/5/3, BB 50/0.35) · HalfTrend (2/2) · Chandelier Exit (22/3) ·
  SSL channel (10)
Chartink-style scans: Supertrend 7/3 · first-hour (opening range) low break · NR7 breakdown · close below VWAP-of-day after
  being above · RSI(14) crossing below 40
Exits: stop 1.5 / 2 ATR x target 1.5 / 2 / 3R (max 20 / 40 candles intraday, 10 daily). Filter: none / DT (stock's daily
trend down, as the live rules). PASS = R > 0 and > RANDOM sells in p1, p2 and p3 (>= 40 trades each).
python research/program/tv_scripts.py -> results/tv_scripts_summary.csv"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, search_all as SA, search_v2 as SV  # noqa: E402
from research.program.stk_anchor import anchored  # noqa: E402
from research.program.sell_exits import run  # noqa: E402

OUT = ROOT / "research/program/results"
EXITS = [(k, r) for k in (1.5, 2.0) for r in (1.5, 2.0, 3.0)]


def rma(x, n):
    return x.ewm(alpha=1 / n, adjust=False).mean()


def atr_(h, l, c, n):
    pc = c.shift(1)
    return rma(pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1), n)


def supertrend(h, l, c, n, m):
    a = atr_(h, l, c, n).values; hl2 = ((h + l) / 2).values; C = c.values
    up = hl2 - m * a; dn = hl2 + m * a; tr = np.ones(len(C)); fu = up.copy(); fd = dn.copy()
    for i in range(1, len(C)):
        fu[i] = max(up[i], fu[i - 1]) if C[i - 1] > fu[i - 1] else up[i]
        fd[i] = min(dn[i], fd[i - 1]) if C[i - 1] < fd[i - 1] else dn[i]
        tr[i] = 1 if C[i] > fd[i - 1] else (-1 if C[i] < fu[i - 1] else tr[i - 1])
    return pd.Series(tr, index=c.index)


def utbot(c, h, l, key=1.0, n=10):
    a = atr_(h, l, c, n).values * key; C = c.values; st = np.zeros(len(C))
    for i in range(1, len(C)):
        p = st[i - 1]
        if C[i] > p and C[i - 1] > p:
            st[i] = max(p, C[i] - a[i])
        elif C[i] < p and C[i - 1] < p:
            st[i] = min(p, C[i] + a[i])
        else:
            st[i] = C[i] - a[i] if C[i] > p else C[i] + a[i]
    st = pd.Series(st, index=c.index)
    return (c < st) & (c.shift(1) >= st.shift(1))


def qqe_line(c, rl=6, sf=5, qf=3.0):
    d = c.diff(); rsi = 100 - 100 / (1 + rma(d.clip(lower=0), rl) / rma(-d.clip(upper=0), rl).replace(0, np.nan))
    r = rsi.ewm(span=sf, adjust=False).mean()
    dar = r.diff().abs().ewm(span=2 * rl - 1, adjust=False).mean().ewm(span=2 * rl - 1, adjust=False).mean() * qf
    R, D = r.values, dar.values; lb = np.zeros(len(R)); sb = np.zeros(len(R)); tr = np.ones(len(R)); fl = np.zeros(len(R))
    for i in range(1, len(R)):
        nl, ns = R[i] - D[i], R[i] + D[i]
        lb[i] = max(lb[i - 1], nl) if (R[i - 1] > lb[i - 1] and R[i] > lb[i - 1]) else nl
        sb[i] = min(sb[i - 1], ns) if (R[i - 1] < sb[i - 1] and R[i] < sb[i - 1]) else ns
        tr[i] = 1 if (R[i] > sb[i - 1] >= R[i - 1]) else (-1 if (R[i] < lb[i - 1] <= R[i - 1]) else tr[i - 1])
        fl[i] = lb[i] if tr[i] == 1 else sb[i]
    return r, pd.Series(fl, index=c.index)


def halftrend(h, l, c, amp=2):
    hp = h.rolling(amp).max().values; lp = l.rolling(amp).min().values
    hma = h.rolling(amp).mean().values; lma = l.rolling(amp).mean().values; C, Hh, L = c.values, h.values, l.values
    n = len(C); tr = np.zeros(n); nt = 0; maxl = L[0]; minh = Hh[0]
    for i in range(1, n):
        tr[i] = tr[i - 1]
        if nt == 1:
            maxl = max(lp[i], maxl)
            if hma[i] < maxl and C[i] < L[i - 1]:
                tr[i] = 1; nt = 0; minh = hp[i]
        else:
            minh = min(hp[i], minh)
            if lma[i] > minh and C[i] > Hh[i - 1]:
                tr[i] = 0; nt = 1; maxl = lp[i]
    t = pd.Series(tr, index=c.index)
    return (t == 1) & (t.shift(1) == 0)


def pivots_low(l, n=5):
    lo = l.values; out = np.full(len(lo), np.nan)
    for i in range(2 * n, len(lo)):
        j = i - n
        if lo[j] == lo[j - n:j + n + 1].min():
            out[i] = lo[j]                                             # known n candles later
    return pd.Series(out, index=l.index).ffill()


def signals(C, intraday):
    o, h, l, c, v = (C[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
    S = {}
    bb_m, bb_s = c.rolling(20).mean(), c.rolling(20).std()
    tr = atr_(h, l, c, 20)
    kc_u, kc_l = c.rolling(20).mean() + 1.5 * tr, c.rolling(20).mean() - 1.5 * tr
    sqz_on = (bb_m - 2 * bb_s > kc_l) & (bb_m + 2 * bb_s < kc_u)
    mid = (h.rolling(20).max() + l.rolling(20).min()) / 2
    x = c - (mid + c.rolling(20).mean()) / 2
    mom = x.rolling(20).apply(lambda y: np.polyfit(np.arange(20), y, 1)[0] * 19 + np.polyfit(np.arange(20), y, 1)[1], raw=True)
    S["TV Squeeze release down (LazyBear)"] = sqz_on.shift(1).fillna(False) & ~sqz_on & (mom < 0) & (mom < mom.shift(1))
    pl = pivots_low(l, 5)
    S["TV SMC break of structure down (LuxAlgo-style)"] = (c < pl) & (c.shift(1) >= pl.shift(1))
    e12, e26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean(); mac = e12 - e26; sig = mac.ewm(span=9, adjust=False).mean()
    S["TV MACD cross below signal (ChrisMoody)"] = (mac < sig) & (mac.shift(1) >= sig.shift(1))
    st = supertrend(h, l, c, 10, 3.0)
    S["TV SuperTrend 10/3 turns red (Kivanc)"] = (st == -1) & (st.shift(1) == 1)
    ap = (h + l + c) / 3; esa = ap.ewm(span=10, adjust=False).mean(); dd = (ap - esa).abs().ewm(span=10, adjust=False).mean()
    wt1 = ((ap - esa) / (0.015 * dd)).ewm(span=21, adjust=False).mean(); wt2 = wt1.rolling(4).mean()
    S["TV WaveTrend cross down above +53 (LazyBear)"] = (wt1 < wt2) & (wt1.shift(1) >= wt2.shift(1)) & (wt1 > 53)
    up, dn = h.diff(), -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0); mdm = dn.where((dn > up) & (dn > 0), 0.0); a14 = atr_(h, l, c, 14)
    pdi, mdi = 100 * rma(pdm, 14) / a14, 100 * rma(mdm, 14) / a14
    adx = rma(100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan), 14)
    S["TV -DI crosses above +DI, ADX > 25"] = (mdi > pdi) & (mdi.shift(1) <= pdi.shift(1)) & (adx > 25)
    d = c.diff(); rsi14 = 100 - 100 / (1 + rma(d.clip(lower=0), 14) / rma(-d.clip(upper=0), 14).replace(0, np.nan))
    ub = bb_m + 2 * bb_s
    S["TV Bollinger + RSI: back below upper band, RSI > 70 (ChartArt)"] = (c < ub) & (c.shift(1) >= ub.shift(1)) & (rsi14.shift(1) > 70)
    e20, e50 = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    S["TV EMA 20 crosses below EMA 50"] = (e20 < e50) & (e20.shift(1) >= e50.shift(1))
    pl15 = pivots_low(l, 15); vo = (v.ewm(span=5).mean() - v.ewm(span=10).mean()) / v.ewm(span=10).mean() * 100
    S["TV S/R break with volume (LuxAlgo, pivot 15, vol osc > 20)"] = (c < pl15) & (c.shift(1) >= pl15.shift(1)) & (vo > 20)
    S["TV UT Bot sell (key 1, ATR 10)"] = utbot(c, h, l, 1.0, 10)
    r1, q1 = qqe_line(c, 6, 5, 3.0); r2, _ = qqe_line(c, 6, 5, 1.61)
    b = (q1 - 50).rolling(50).mean(); bs = (q1 - 50).rolling(50).std(); lower = b - 0.35 * bs
    qd = ((r2 - 50) < -3) & ((r1 - 50) < lower)
    S["TV QQE MOD turns down (Mihkel00)"] = qd & ~qd.shift(1).fillna(False)
    S["TV HalfTrend sell (everget, amp 2)"] = halftrend(h, l, c, 2)
    a22 = atr_(h, l, c, 22) * 3; ce_l = h.rolling(22).max() - a22; ce_s = l.rolling(22).min() + a22
    dirn = pd.Series(np.where(c > ce_s.shift(1), 1, np.where(c < ce_l.shift(1), -1, np.nan)), index=c.index).ffill()
    S["TV Chandelier Exit sell (22/3)"] = (dirn == -1) & (dirn.shift(1) == 1)
    sh, sl_ = h.rolling(10).mean(), l.rolling(10).mean()
    hlv = pd.Series(np.where(c > sh, 1, np.where(c < sl_, -1, np.nan)), index=c.index).ffill()
    S["TV SSL channel turns down (10)"] = (hlv == -1) & (hlv.shift(1) == 1)
    st7 = supertrend(h, l, c, 7, 3.0)
    S["Chartink Supertrend 7/3 turns red"] = (st7 == -1) & (st7.shift(1) == 1)
    r7 = h - l
    S["Chartink NR7 breakdown"] = (r7.shift(1) <= r7.shift(1).rolling(7).min()) & (c < l.shift(1))
    S["Chartink RSI(14) crosses below 40"] = (rsi14 < 40) & (rsi14.shift(1) >= 40)
    if intraday:
        day = pd.to_datetime(C["time"]).dt.normalize()
        fl = l.groupby(day).transform("first")                                # first candle of the day's low
        first = day != day.shift(1)
        below = c < fl
        prev_below = below.shift(1, fill_value=False) & ~first           # was already below earlier the same day
        S["Chartink opening-range (first candle) low break"] = (~first) & below & ~prev_below
        tp = (h + l + c) / 3; vw = (tp * v).groupby(day).cumsum() / v.groupby(day).cumsum()
        S["Chartink close crosses below day VWAP"] = (c < vw) & (c.shift(1) >= vw.shift(1)) & ~first
    S = {k: x.fillna(False).astype(bool) for k, x in S.items()}
    rng = np.random.default_rng(len(c))
    S["RANDOM"] = pd.Series(rng.random(len(c)) < 0.03, index=c.index)
    return S


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return None
    seg = {s: (f.reset_index(drop=True), np.asarray(c, float)) for s, f, od, c in fr}
    if "STOCKS 1h" not in seg or "STOCKS 1d" not in seg:
        return None
    f1, c1 = seg["STOCKS 1h"]; fd, cd = seg["STOCKS 1d"]
    c1 = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(c1)), c1) if len(c1) != len(f1) else c1
    dtr = SA.daily_trend(fd)
    frames = {"1d": (fd, cd), "1h": (f1, c1)}
    for hrs, tf in ((2, "2h"), (4, "4h")):
        C, first = anchored(f1, hrs); frames[tf] = (C, c1[first[:len(C)]])
    rows = []
    for tf, (C, cost) in frames.items():
        if len(C) < 300:
            continue
        f = H.features(C); f["switch"] = C["switch"].values if "switch" in C else np.zeros(len(C), bool)
        o, h, l, c, at = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "atr"))
        sw = f["switch"].values.astype(np.bool_); t = pd.to_datetime(f["time"]).values
        cost = np.asarray(cost, float)
        if len(cost) != len(c):
            cost = np.interp(np.arange(len(c)), np.linspace(0, len(c) - 1, len(cost)), cost)
        # the stock's own daily trend from the PREVIOUS completed day (SA.daily_trend is already shifted), as the live "DT"
        down = (pd.to_datetime(f["time"]).dt.normalize().map(dtr) < 0).values
        maxh = 10 if tf == "1d" else SV.MAXH.get(tf, 40)
        split = np.where(t < SV.P1, 0, np.where(t < SV.P2, 1, 2))
        for name, s in signals(C, tf != "1d").items():
            s = s.values
            for flt, m in (("none", s), ("DT", s & down)):
                if m.sum() < 3:
                    continue
                for k, r in EXITS:
                    for i, j, rr, why, mfe, booked in run(o, h, l, c, at, sw, m, k, r, maxh, cost, 0.0, 0.0, 0.0, H.CHASE):
                        rows.append((tf, name, flt, k, r, int(split[i]), rr))
    return rows


def main():
    J = [j for j in EX.jobs() if j[0] == "stk"]
    acc = {}
    with Pool(2) as p:
        for rows in p.imap_unordered(one, J, chunksize=2):
            if not rows:
                continue
            for tf, nm, fl, k, r, sp, rr in rows:
                a = acc.setdefault((tf, nm, fl, k, r, sp), [0, 0.0, 0])
                a[0] += 1; a[1] += rr; a[2] += rr > 0
    A = pd.DataFrame([(*k, *v) for k, v in acc.items()], columns=["tf", "script", "filt", "k", "r", "split", "n", "sumR", "wins"])
    W = A.pivot_table(index=["tf", "script", "filt", "k", "r"], columns="split", values=["n", "sumR", "wins"], aggfunc="sum").fillna(0)
    rows = []
    for key, x in W.iterrows():
        n = [x[("n", s)] for s in (0, 1, 2)]; sR = [x[("sumR", s)] for s in (0, 1, 2)]; w = [x[("wins", s)] for s in (0, 1, 2)]
        N = sum(n)
        if N < 60:
            continue
        rows.append(dict(zip(["tf", "script", "filt", "k", "r"], key), n=int(N), win=round(100 * sum(w) / N, 1), R=round(sum(sR) / N, 3),
                         **{f"p{s+1}_n": int(n[s]) for s in range(3)}, **{f"p{s+1}_R": round(sR[s] / n[s], 3) if n[s] else None for s in range(3)},
                         **{f"p{s+1}_win": round(100 * w[s] / n[s], 1) if n[s] else None for s in range(3)}))
    L = pd.DataFrame(rows)
    base = L[L.script == "RANDOM"].set_index(["tf", "filt", "k", "r"])
    for s in (1, 2, 3):
        L[f"p{s}_rand"] = [base[f"p{s}_R"].get((a, b, c_, d), np.nan) for a, b, c_, d in zip(L.tf, L.filt, L.k, L.r)]
    L["pass"] = np.all([(L[f"p{s}_n"] >= 40) & (L[f"p{s}_R"] > 0) & (L[f"p{s}_R"] > L[f"p{s}_rand"]) for s in (1, 2, 3)], axis=0) & (L.script != "RANDOM")
    L["minR"] = L[["p1_R", "p2_R", "p3_R"]].min(axis=1)
    L.to_csv(OUT / "tv_scripts_summary.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200); pd.set_option("display.max_colwidth", 60)
    c = ["tf", "script", "filt", "k", "r", "n", "win", "R", "p1_win", "p2_win", "p3_win", "p1_R", "p2_R", "p3_R", "p1_rand", "p2_rand", "p3_rand"]
    print(f"combos {len(L)} · PASS {int(L['pass'].sum())}")
    print(L[L["pass"]].sort_values("minR", ascending=False).head(40)[c].to_string(index=False))
    print("\nbest per script (by worst-period R):")
    B = L[L.script != "RANDOM"].sort_values("minR", ascending=False).groupby("script").head(1)
    print(B[c + ["pass"]].to_string(index=False))


if __name__ == "__main__":
    main()
