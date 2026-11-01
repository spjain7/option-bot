"""IMPROVE-001 (1-Nov-2026, owner "yes all"): three ways to make the core breakout calls more accurate, tested on 4 years.
Core rules (live settings, candle-close entry at the next candle's open, 2x costs, one trade at a time, 1-hour bar exits):
  MCX 3h BUY  N=10 vol 1.5x 2ATR/2R · MCX 4h BUY  N=10 vol 2x 1.5ATR/3R · STK 4h SELL N=5 vol 2x 2ATR/2R
 1. CONFLUENCE  D  daily trend agrees (previous day: daily EMA20 vs EMA50 and close vs EMA50 on the side of the call)
                OI stocks only: OI label of the signal hour supports the side (SB / LU for SELL) – daily-based label in this data
                IX stocks only: NIFTY daily trend agrees (previous day close below EMA50 for SELL)
 2. MANAGEMENT  BE   at +1R move the stop to entry
                HALF at +1R book half, stop to entry on the rest (rest runs to the target)
 3. REGIME      ADX daily ADX(14) ≥ 20 the previous day (trending, not choppy)
                VOL daily ATR % above its 100-day median (moving market)
python research/program/improve4.py"""
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from research.program import harness as H, emax as EX, touch as TC  # noqa: E402
from research.program.tf5h import T1, T2  # noqa: E402
from crude import indicators as I  # noqa: E402

RULES = {"MCX 3h BUY": ("MCX", 3), "MCX 4h BUY": ("MCX", 4), "STK 4h SELL": ("STOCKS", 4)}
OUT = ROOT / "research/program/results"
_NIFTY = None


def daily_ctx(f1):
    d = f1.assign(day=f1["time"].dt.normalize()).groupby("day").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                                                    close=("close", "last"))
    e20, e50 = I.ema(d["close"], 20), I.ema(d["close"], 50)
    adx = I.adx(d.reset_index(drop=True)).values
    atr = I.atr(d.reset_index(drop=True), 14).values
    atrp = pd.Series(atr / d["close"].values, index=d.index)
    x = pd.DataFrame(dict(up=((e20 > e50) & (d["close"] > e50)).values, dn=((e20 < e50) & (d["close"] < e50)).values,
                          adx=adx, volhi=(atrp > atrp.rolling(100, min_periods=40).median()).values), index=d.index)
    return x.shift(1)                                              # previous day's values only


def nifty():
    global _NIFTY
    if _NIFTY is None:
        d = H.nseidx("NIFTY").set_index("time")
        e50 = I.ema(d["close"], 50)
        _NIFTY = pd.DataFrame(dict(up=d["close"] > e50, dn=d["close"] < e50)).shift(1)
        _NIFTY.index = pd.to_datetime(_NIFTY.index).normalize()
    return _NIFTY


def sim(f1, cid_first, cid_last, C, F, rule, cost1, oi_lab, ctx, nf, market, n):
    side, N, vx, k, r = rule["side"], rule["N"], rule["vx"], rule["k"], rule["r"]
    cap = 2.5 if market == "MCX" else 4.0
    lvl = (F.high.shift(1).rolling(N).max() if side > 0 else F.low.shift(1).rolling(N).min()).values
    cl, ema, atr, va, vol = F.close.values, F.ema200.values, F.atr.values, F.va.values, F.volume.values.astype(float)
    o1, h1, l1, c1, sw1 = (f1[x].values.astype(float) for x in ("open", "high", "low", "close", "switch"))
    out = []
    for mgmt in ("base", "BE", "HALF"):
        busy = -1
        for i in range(210, len(C) - 1):
            if not atr[i] > 0 or F["switch"].iat[i] or F["switch"].iat[i + 1]:
                continue
            if not (side * (cl[i] - lvl[i]) > 0 and vol[i] > vx * va[i] and side * (cl[i] - ema[i]) > 0):
                continue
            j0 = cid_first[i + 1]
            if j0 <= busy:
                continue
            e0, R = o1[j0], k * atr[i]
            if R / e0 * 100 > cap:
                continue
            st, tp, one = e0 - side * R, e0 + side * r * R, e0 + side * R
            px = why = None; half = None; j = j0
            while j < len(f1):
                if j > j0 and sw1[j]:
                    px, why, j = c1[j - 1], "roll", j - 1; break
                if j > j0 and side * (o1[j] - st) <= 0:
                    px, why = o1[j], "stop-gap"; break
                if j > j0 and side * (o1[j] - tp) >= 0:
                    px, why = o1[j], "target-gap"; break
                if (l1[j] <= st) if side > 0 else (h1[j] >= st):
                    px, why = st, "stop"; break
                if (h1[j] >= tp) if side > 0 else (l1[j] <= tp):
                    px, why = tp, "target"; break
                if mgmt != "base" and half is None and ((h1[j] >= one) if side > 0 else (l1[j] <= one)):
                    half = one; st = e0                         # from the NEXT bar the stop sits at entry
                if j - j0 >= TC.MAXC * n:
                    px, why = c1[j], "time"; break
                j += 1
            if px is None:
                px, why, j = c1[-1], "end", len(f1) - 1
            g = side * (px - e0)
            if mgmt == "HALF" and half is not None:
                g = 0.5 * side * (half - e0) + 0.5 * g
            cst = cost1[min(j0, len(cost1) - 1)]
            day = pd.Timestamp(C["time"].iat[i]).normalize()
            last_h = cid_last[i]
            cx = ctx.loc[day] if day in ctx.index else None
            lab = oi_lab[last_h] if oi_lab is not None else None
            nfx = nf.loc[day] if (nf is not None and day in nf.index) else None
            out.append(dict(mgmt=mgmt, time=C["time"].iat[i], r2=(g - 2 * cst) / R,
                            D=bool(cx is not None and (cx["up"] if side > 0 else cx["dn"]) == True),  # noqa: E712
                            ADX=bool(cx is not None and cx["adx"] >= 20), VOL=bool(cx is not None and cx["volhi"] == True),  # noqa: E712
                            OI=(lab in (("LB", "SC") if side > 0 else ("SB", "LU"))) if lab is not None else None,
                            IX=bool(nfx is not None and (nfx["up"] if side > 0 else nfx["dn"]) == True) if nf is not None else None))  # noqa: E712
            busy = j
    return out


def one(job):
    try:
        fr = EX.frames(job)
    except Exception:
        return []
    rows = []
    for seg, f0, od, cost in fr:
        market, tf0 = seg.split()[0], seg.split()[-1]
        if tf0 != "1h" or market not in ("MCX", "STOCKS"):
            continue
        f1 = f0.reset_index(drop=True)
        c_ = np.interp(np.arange(len(f1)), np.linspace(0, len(f1) - 1, len(cost)), cost)
        oi_lab = None
        if market == "STOCKS":
            x = EX.RV.stock_1h(job[1], job[2])
            if x is not None and len(x[1]) == len(f1):
                oi_lab = x[1]["oi_lab"].values
        ctx = daily_ctx(f1)
        nf = nifty() if market == "STOCKS" else None
        for name_, (mk, n) in RULES.items():
            if mk != market:
                continue
            C, cid = TC.blocks(f1, market, n)
            if len(C) < 260:
                continue
            F = H.features(C); F["switch"] = C["switch"].values
            first = np.r_[0, np.flatnonzero(np.diff(cid)) + 1]
            last = np.r_[first[1:] - 1, len(f1) - 1]
            for t in sim(f1, first, last, C, F, TC.RULES[(market, n)], c_, oi_lab, ctx, nf, market, n):
                t.update(rule=name_, name=job[1]); rows.append(t)
    return rows


def stats(x):
    s = dict(n=len(x), win=(x.r2 > 0).mean(), R=x.r2.mean(), totalR=x.r2.sum())
    for sp, a, b in (("p1_train", None, T1), ("p2_valid", T1, T2), ("p3_test", T2, None)):
        m = np.ones(len(x), bool)
        if a is not None:
            m &= x.time >= a
        if b is not None:
            m &= x.time < b
        s[sp] = x.r2[m].mean() if m.any() else np.nan
    s["all3"] = all(s[k] > 0 for k in ("p1_train", "p2_valid", "p3_test"))
    return pd.Series(s)


def main():
    J = [j for j in EX.jobs() if (j[0] == "mi" and j[2] == "MCX") or j[0] == "stk"]
    with Pool(3) as p:
        rows = [r for x in p.imap_unordered(one, J, chunksize=2) for r in x]
    cache = OUT / "improve4_trades.csv.gz"
    if not rows and cache.exists():
        pass
    T = pd.DataFrame(rows)
    T["time"] = pd.to_datetime(T["time"], format="mixed")
    T.to_csv(OUT / "improve4_trades.csv.gz", index=False)
    res = []
    for rule, g in T.groupby("rule"):
        b = g[g.mgmt == "base"]
        filters = {"BASE": b, "D daily trend": b[b.D], "ADX ≥ 20": b[b.ADX], "VOL high": b[b.VOL], "D + ADX": b[b.D & b.ADX]}
        if rule.startswith("STK"):
            filters.update({"OI supports": b[b.OI == True], "NIFTY trend": b[b.IX == True],  # noqa: E712
                            "D + NIFTY": b[b.D & (b.IX == True)]})  # noqa: E712
        for k, x in filters.items():
            res.append(dict(rule=rule, test=k, **stats(x)))
        for m in ("BE", "HALF"):
            res.append(dict(rule=rule, test=f"mgmt {m}", **stats(g[g.mgmt == m])))
            x = g[(g.mgmt == m) & g.D]
            res.append(dict(rule=rule, test=f"mgmt {m} + D", **stats(x)))
    S = pd.DataFrame(res)
    S.to_csv(OUT / "improve4_summary.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
    print(S.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
