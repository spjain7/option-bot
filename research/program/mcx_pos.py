"""MCX-POS-001 (24-Nov-2026, owner: "check which combo can work for us positionally" on MCX). Positional (multi-day) BUY and
SELL on MCX futures, daily candles from the MCX bhavcopy (Jul-2022 .. 23-Nov-2026, research-mcx-bhav branch).
Series: per day the contract with the most volume (never back to an earlier expiry), back-adjusted at each switch by the
measured price ratio of the day before (ratio back-adjusted); total OI = all contracts. Trades may run through a switch (extra cost per switch).
Commodities: GOLD, SILVER, CRUDEOIL, NATURALGAS, COPPER, ZINC, ALUMINIUM, LEAD, NICKEL.
Families (BUY wording; SELL = same on mirrored prices):
  own: Donchian 20 / 55 breakout, EMA 20/50 and 50/200 cross, SuperTrend(10,3) flip, MACD zero cross, pull-back to EMA20 in a
       trend, RSI(2) < 10 in a trend, NR7 / inside-day break, OI long build-up (close +1 %, total OI +2 %, trend)
  + the 14 TradingView trend scripts (tv_scripts.signals), 13 reversal indicators (rev_ind.tops on mirrored = bottoms),
    13 TradingView bottom scripts (tv_buy.bottoms)
Filters: none · TR (close on the EMA50 side of the call) · LT (EMA50 on the EMA200 side) · TR+LT.
Exits (entry next open, skipped if > 0.5 ATR away, stop first inside a day):
  F2x2_20  SL 2 ATR, target 2R, max 20 days       F2x3_40  SL 2 ATR, target 3R, max 40 days
  F3x2_40  SL 3 ATR, target 2R, max 40 days       CH3      SL 2.5 ATR, then 3-ATR chandelier trail from the best close, max 60
  EMA20    SL 2.5 ATR, exit at the first close on the wrong side of EMA20, max 60
Costs: 0.10 % of price per round trip + 0.05 % per contract switch crossed (about 2x real MCX costs + slippage).
PASS = R > 0 and above RANDOM (same side / filter / exit) in 2022-07..2023 / 2024 / 2025-26 with >= 15 trades each, and
positive in at least 5 of the 9 commodities.
python research/program/mcx_pos.py -> results/mcx_pos_summary.csv, results/mcx_pos_trades.parquet"""
import glob
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program.rev_ind import tops, mirror  # noqa: E402
from research.program.tv_scripts import signals as tv_sell  # noqa: E402
from research.program.tv_buy import bottoms  # noqa: E402

OUT = ROOT / "research/program/results"
BHAV = ROOT / "research/data/mcx_bhav/days"
COMS = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM", "LEAD", "NICKEL"]
EXITS = ["F2x2_20", "F2x3_40", "F3x2_40", "CH3", "EMA20"]
COST, ROLLC = 0.0010, 0.0005
P1, P2 = np.datetime64("2024-01-01"), np.datetime64("2025-01-01")


def load():
    fs = sorted(glob.glob(str(BHAV / "*.csv")))
    D = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    D = D[(D.instrument == "FUTCOM") & D.symbol.isin(COMS)].copy()
    D["date"] = pd.to_datetime(D["date"]); D["exp"] = pd.to_datetime(D["expiry"], format="%d%b%Y", errors="coerce")
    D = D[(D[["open", "high", "low", "close"]] > 0).all(axis=1) & (D.volume_lots > 0)]          # holidays / no-trade rows
    D = D[(D.low <= D[["open", "close"]].min(axis=1)) & (D.high >= D[["open", "close"]].max(axis=1))]
    return D


def series(D, sym):
    x = D[D.symbol == sym].sort_values(["date", "exp"])
    oi = x.groupby("date").oi_lots.sum()
    rows, cur_exp, adj_rows = [], None, []
    for d, g in x.groupby("date"):
        g = g[g.exp >= d]
        if cur_exp is not None:
            g = g[g.exp >= cur_exp]                                   # never back to an earlier expiry
        if g.empty:
            continue
        pick = g.loc[g.volume_lots.idxmax()]
        if cur_exp is not None and pick.exp != cur_exp and (g.exp == cur_exp).any():
            old = g[g.exp == cur_exp].iloc[0]
            if pick.volume_lots <= old.volume_lots:
                pick = old
        rows.append(dict(time=d, exp=pick.exp, open=pick.open, high=pick.high, low=pick.low, close=pick.close, prev_close=pick.prev_close,
                         volume=pick.volume_lots, oi=oi.get(d, np.nan)))
        cur_exp = pick.exp
    S = pd.DataFrame(rows)
    S["switch"] = S.exp != S.exp.shift(1); S.loc[0, "switch"] = False
    # back-adjust: at a switch, gap = new contract's previous close - old contract's previous close
    fac = np.ones(len(S))                                              # ratio back-adjustment (contango is a % of price)
    for i in np.flatnonzero(S.switch.values):
        if S.close.iat[i - 1] > 0 and S.prev_close.iat[i] > 0:
            fac[i] = S.prev_close.iat[i] / S.close.iat[i - 1]
    cum = np.cumprod(fac[::-1])[::-1]
    mult = np.r_[cum[1:], 1.0]                                          # product of the factors of every later switch
    for c in ("open", "high", "low", "close"):
        S[c] = S[c] * mult
    return S.reset_index(drop=True)


def ind(C):
    h, l, c = C.high.astype(float), C.low.astype(float), C.close.astype(float)
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / 14, adjust=False).mean().values, c.ewm(span=20, adjust=False).mean().values


def own(C):
    o, h, l, c, v = (C[x].astype(float) for x in ("open", "high", "low", "close", "volume"))
    e20, e50, e200 = (c.ewm(span=n, adjust=False).mean() for n in (20, 50, 200))
    up = (e20 > e50) & (c > e50)
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1); at = tr.ewm(alpha=1 / 10, adjust=False).mean()
    hl2 = (h + l) / 2; ub, lb = hl2 + 3 * at, hl2 - 3 * at
    U, L, Cc = ub.values.copy(), lb.values.copy(), c.values; d = np.ones(len(c))
    for i in range(1, len(c)):
        L[i] = max(L[i], L[i - 1]) if Cc[i - 1] > L[i - 1] else L[i]
        U[i] = min(U[i], U[i - 1]) if Cc[i - 1] < U[i - 1] else U[i]
        d[i] = 1 if Cc[i] > U[i - 1] else (-1 if Cc[i] < L[i - 1] else d[i - 1])
    st = pd.Series(d, index=c.index)
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    dd = c.diff(); r2 = 100 - 100 / (1 + dd.clip(lower=0).ewm(alpha=0.5, adjust=False).mean() / (-dd.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean().replace(0, np.nan))
    rg = h - l
    oi = C["oi"].astype(float)
    S = {"OWN Donchian 20 break": (c > h.shift(1).rolling(20).max()) & (c.shift(1) <= h.shift(2).rolling(20).max()),
         "OWN Donchian 55 break": (c > h.shift(1).rolling(55).max()) & (c.shift(1) <= h.shift(2).rolling(55).max()),
         "OWN EMA 20/50 cross": (e20 > e50) & (e20.shift(1) <= e50.shift(1)),
         "OWN EMA 50/200 cross": (e50 > e200) & (e50.shift(1) <= e200.shift(1)),
         "OWN SuperTrend flip": (st == 1) & (st.shift(1) == -1),
         "OWN MACD zero cross": (macd > 0) & (macd.shift(1) <= 0),
         "OWN pull-back to EMA20 in trend": up & (l <= e20) & (c > e20) & (c > o),
         "OWN RSI(2) < 10 in trend": up & (r2 < 10),
         "OWN NR7 break": (rg.shift(1) <= rg.shift(1).rolling(7).min()) & (c > h.shift(1)),
         "OWN inside-day break": (h.shift(1) <= h.shift(2)) & (l.shift(1) >= l.shift(2)) & (c > h.shift(1)),
         "OWN OI long build-up": up & (c >= c.shift(1) * 1.01) & (oi >= oi.shift(1) * 1.02)}
    return {k: x.fillna(False).astype(bool).values for k, x in S.items()}


def all_buy(C):
    S = own(C)
    for k, v in tops(mirror(C)).items():
        S["REV " + k] = v.values
    for k, v in bottoms(C).items():
        S["BOT " + k] = v.values
    for k, v in tv_sell(mirror(C), False).items():
        if k != "RANDOM":
            S["TV " + k] = np.asarray(v, bool)
    return S


def sim(C, sig, ex, at, e20, sw):
    o, h, l, c = (C[x].values.astype(float) for x in ("open", "high", "low", "close"))
    n = len(c); out = []; i = 0
    while i < n - 2:
        if not sig[i] or not np.isfinite(at[i]) or at[i] <= 0 or i < 200:
            i += 1; continue
        e = o[i + 1]
        if e > c[i] + 0.5 * at[i]:
            i += 1; continue
        k = {"F2x2_20": 2.0, "F2x3_40": 2.0, "F3x2_40": 3.0, "CH3": 2.5, "EMA20": 2.5}[ex]
        r = {"F2x2_20": 2.0, "F2x3_40": 3.0, "F3x2_40": 2.0}.get(ex)
        maxh = {"F2x2_20": 20, "F2x3_40": 40, "F3x2_40": 40}.get(ex, 60)
        R = k * at[i]; stop = e - R; tgt = e + r * R if r else None; best = c[i]
        px, why, j, rolls = None, 3, i + 1, 0
        for j in range(i + 1, min(n, i + 1 + maxh)):
            if j > i + 1 and sw[j]:
                rolls += 1
            if l[j] <= stop:
                px, why = (min(o[j], stop) if j > i + 1 else stop), 1; break
            if tgt is not None and h[j] >= tgt:
                px, why = (max(o[j], tgt) if j > i + 1 else tgt), 2; break
            if ex == "CH3":
                best = max(best, c[j]); stop = max(stop, best - 3 * at[j])
            if ex == "EMA20" and c[j] < e20[j]:
                px, why = c[j], 2; break
        if px is None:
            px = c[j]
        rr = (px - e) / R - (COST + ROLLC * rolls) * abs(e) / R
        out.append((i, j, rr, why))
        i = j + 1
    return out


def one(args):
    sym, S0 = args
    acc = {}; rows = []
    rng = np.random.default_rng(sum(map(ord, sym)))
    tt = pd.to_datetime(S0["time"]).values
    split = np.where(tt < P1, 0, np.where(tt < P2, 1, 2))
    sw = S0["switch"].values.astype(bool)
    for side, C in (("BUY", S0), ("SELL", mirror(S0))):
        C = C.copy(); C["oi"] = S0["oi"].values; C["switch"] = sw
        Sg = all_buy(C); Sg["RANDOM"] = rng.random(len(C)) < 0.05
        at, e20 = ind(C)
        c = C.close.astype(float); e50 = c.ewm(span=50, adjust=False).mean(); e200 = c.ewm(span=200, adjust=False).mean()
        trf = (c > e50).values; ltf = (e50 > e200).values
        for nm, s in Sg.items():
            s = np.asarray(s, bool)
            for flt, m in (("none", s), ("TR", s & trf), ("LT", s & ltf), ("TR+LT", s & trf & ltf)):
                if m.sum() < 1:
                    continue
                for ex in EXITS:
                    for i, j, rr, why in sim(C, m, ex, at, e20, sw):
                        a = acc.setdefault((nm, side, flt, ex, int(split[i])), [0, 0.0, 0, 0]); a[0] += 1; a[1] += rr; a[2] += rr > 0; a[3] += why == 1
                        rows.append((nm, side, flt, ex, sym, tt[i], rr, why, j - i))
    return acc, rows


def main():
    D = load()
    jobs = [(s, series(D, s)) for s in COMS]
    for s, S in jobs:
        print(s, len(S), S.time.min().date(), S.time.max().date(), int(S.switch.sum()), "switches")
    acc = {}; rows = []
    with Pool(2) as p:
        for a, r in p.imap_unordered(one, jobs):
            rows += r
            for k_, v in a.items():
                x = acc.setdefault(k_, [0, 0.0, 0, 0])
                for q in range(4):
                    x[q] += v[q]
    T = pd.DataFrame(rows, columns=["fam", "side", "flt", "exit", "sym", "t", "R", "why", "days"])
    T.to_parquet(OUT / "mcx_pos_trades.parquet")
    keys = ["fam", "side", "flt", "exit"]
    A = pd.DataFrame([(*k_, *v) for k_, v in acc.items()], columns=keys + ["split", "n", "sumR", "wins", "sl"])
    W = A.pivot_table(index=keys, columns="split", values=["n", "sumR", "wins", "sl"], aggfunc="sum").fillna(0)
    out = []
    for key, x in W.iterrows():
        n = [x.get(("n", s), 0) for s in (0, 1, 2)]; sR = [x.get(("sumR", s), 0) for s in (0, 1, 2)]; w = [x.get(("wins", s), 0) for s in (0, 1, 2)]
        N = sum(n)
        if N < 30:
            continue
        out.append(dict(zip(keys, key), n=int(N), win=round(100 * sum(w) / N, 1), sl=round(100 * sum(x.get(("sl", s), 0) for s in (0, 1, 2)) / N, 1),
                        R=round(sum(sR) / N, 3), **{f"p{s+1}_n": int(n[s]) for s in range(3)},
                        **{f"p{s+1}_R": round(sR[s] / n[s], 3) if n[s] else None for s in range(3)}))
    L = pd.DataFrame(out)
    base = L[L.fam == "RANDOM"].set_index(["side", "flt", "exit"])
    for s in (1, 2, 3):
        L[f"p{s}_rand"] = [base[f"p{s}_R"].get(kk, np.nan) for kk in zip(L.side, L.flt, L.exit)]
    pc = T.groupby(keys + ["sym"]).R.mean().gt(0).groupby(level=keys).sum().rename("coms_pos")
    L = L.merge(pc.reset_index(), on=keys, how="left")
    L["pass"] = np.all([(L[f"p{s}_R"] > 0) & (L[f"p{s}_R"] > L[f"p{s}_rand"].fillna(-9)) & (L[f"p{s}_n"] >= 15) for s in (1, 2, 3)], axis=0) \
        & (L.coms_pos >= 5) & (L.fam != "RANDOM")
    L["minR"] = L[["p1_R", "p2_R", "p3_R"]].min(axis=1)
    L.to_csv(OUT / "mcx_pos_summary.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 200); pd.set_option("display.max_colwidth", 52)
    c = ["fam", "side", "flt", "exit", "n", "win", "sl", "R", "p1_R", "p2_R", "p3_R", "p1_rand", "p2_rand", "p3_rand", "coms_pos"]
    print("PASSED:", int(L["pass"].sum()), "of", len(L))
    print(L[L["pass"]].sort_values("minR", ascending=False)[c].head(60).to_string(index=False))
    print(L[L.fam == "RANDOM"][c].to_string(index=False))


if __name__ == "__main__":
    main()
