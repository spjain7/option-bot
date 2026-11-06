"""MCXD-004 – Gold/Silver day-trend continuation: audit-driven improvements with IDENTICAL entry signals.
Variants are chosen on DEV only; VALID and HIST are read, never used to choose.
  risk   R1 one position per commodity per day (skip 17:00 if the 13:00 trade is still open)
  delay  entry 0 / 5 / 10 / 15 minutes after the checkpoint (live scans run ~2-5 min after a candle closes)
  costs  realistic x1 / x2 / x4
  exits  E0 square-off 23:00 (base) · E1 trailing 1 x daily ATR · E2 VWAP failure (15m close back through VWAP) · E3 half
         at +1R then stop to entry, rest to 23:00 · E4 time exit after 2 h · E5 time exit after 4 h
  trend  T60 (base) · T30 (30m EMA20/50) · T60+D (60m and the daily EMA20/50 trend agree) · ADX (60m ADX >= 20)
  chase  skip if the move from the open already exceeds 1.5 x daily ATR
python research/program/mcx_dtc2.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.program import mcx_disc as MD  # noqa: E402
from crude import indicators as I  # noqa: E402

OUT = ROOT / "research/program/results"
CPS, K, M = (13 * 60, 17 * 60), 0.3, 0.5


def build(name):
    d5, f15, f30, f60, dd, sw = MD.prep(name)
    e20, e50 = f30.close.ewm(span=20, adjust=False).mean(), f30.close.ewm(span=50, adjust=False).mean()
    f30["tr"] = np.where((e20 > e50) & (f30.close > e50), 1, np.where((e20 < e50) & (f30.close < e50), -1, 0))
    i30 = np.searchsorted((f30.time + pd.Timedelta(minutes=30)).values, (f15.time + pd.Timedelta(minutes=15)).values, side="right") - 1
    f15["tr30"] = np.where(i30 >= 0, f30.tr.values[np.clip(i30, 0, None)], 0)
    f60["adx"] = I.adx(f60, 14)
    i60 = np.searchsorted((f60.time + pd.Timedelta(minutes=60)).values, (f15.time + pd.Timedelta(minutes=15)).values, side="right") - 1
    f15["adx60"] = np.where(i60 >= 0, f60.adx.values[np.clip(i60, 0, None)], np.nan)
    c = dd.c; de20, de50 = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    dd["dtr"] = pd.Series(np.where((de20 > de50) & (c > de50), 1, np.where((de20 < de50) & (c < de50), -1, 0)), index=dd.index).shift(1)
    return d5, f15, dd, sw


def walk_ex(d5, i0, s, e, st, ie, R, mode, atr_d, vw15):
    H, L, O, C, T = d5.high.values, d5.low.values, d5.open.values, d5.close.values, d5.time.values
    best, half_done, half_px = e, False, None
    t_end = ie
    if mode in ("E4", "E5"):
        t_end = min(ie, i0 + (24 if mode == "E4" else 48))
    for k in range(i0, t_end + 1):
        if k > i0 and ((s > 0 and O[k] <= st) or (s < 0 and O[k] >= st)):
            px = O[k]; break
        if (s > 0 and L[k] <= st) or (s < 0 and H[k] >= st):
            px = st; break
        if mode == "E3" and not half_done and ((s > 0 and H[k] >= e + R) or (s < 0 and L[k] <= e - R)):
            half_done, half_px, st = True, e + s * R, e
        if mode == "E1":
            best = max(best, H[k]) if s > 0 else min(best, L[k]); ns = best - s * atr_d
            if (s > 0 and ns > st) or (s < 0 and ns < st):
                st = ns
        if mode == "E2" and (k - i0) % 3 == 2:                          # 15m close (every third 5m bar) back through VWAP
            v = vw15.get(pd.Timestamp(T[k]) - pd.Timedelta(minutes=10))
            if v is not None and s * (C[k] - v) < 0:
                px = C[k]; break
    else:
        px = C[t_end]
    g = s * (px - e)
    if mode == "E3" and half_done:
        g = 0.5 * s * (half_px - e) + 0.5 * g
    return g


def trades(name, B, delay=0, trend="T60", chase=False, one_pos=False, mode="E0"):
    d5, f15, dd, sw = B
    t5 = d5.time.values
    eod = d5[d5.m <= 23 * 60].groupby("day").apply(lambda g: g.index[-1])
    vw15 = dict(zip(f15.time, f15.vwap))
    rows, busy = [], {}
    for cp in CPS:
        for _, r in f15[f15.m == cp - 15].iterrows():
            day = r.day
            if day in sw or day not in dd.index or day not in eod.index or not dd.at[day, "atr"] > 0:
                continue
            D = dd.loc[day]
            dayo = d5.open.values[np.searchsorted(t5, np.datetime64(day + pd.Timedelta(hours=9)))]
            for s in (1, -1):
                tr = {"T60": r.tr60, "T30": r.tr30, "T60+D": r.tr60 if D.dtr == r.tr60 else 0, "ADX": r.tr60 if r.adx60 >= 20 else 0}[trend]
                mv = s * (r.close - dayo)
                if not (tr == s and s * (r.close - r.vwap) > 0 and mv >= K * D.atr):
                    continue
                if chase and mv > 1.5 * D.atr:
                    continue
                i0 = np.searchsorted(t5, np.datetime64(r.time + pd.Timedelta(minutes=15 + delay)))
                if i0 >= len(d5) or d5.day.iat[i0] != day or i0 >= eod[day]:
                    continue
                if one_pos and busy.get((name, day), -1) >= i0:
                    continue
                e = d5.open.iat[i0]; R = M * D.atr; st = e - s * R
                g = walk_ex(d5, i0, s, e, st, int(eod[day]), R, mode, D.atr, vw15)
                c = MD.real_cost(name, e)
                rows.append(dict(name=name, day=day, cp=cp, side=s, gross=g / R, cost=c / R))
                if one_pos:                                                  # position open until its exit – approx: until EOD unless stopped
                    busy[(name, day)] = int(eod[day]) if g / R > -0.999 else i0
    return pd.DataFrame(rows)


def score(x, cost_x=1.0):
    x = x.assign(net=x.gross - cost_x * x.cost)
    p = np.where(x.day < MD.Y0, "hist", np.where(x.day < MD.DEV_END, "dev", "valid"))
    o = {q: round(x.net[p == q].mean(), 3) for q in ("dev", "valid", "hist")}
    yr = x.groupby(x.day.dt.year).net.mean()
    R = x.net.values
    return dict(n=len(x), net=round(R.mean(), 3), **o, years_pos=f"{int((yr > 0).sum())}/{len(yr)}",
                drop5=round(R[R < np.quantile(R, .95)].mean(), 3), PF=round(R[R > 0].sum() / -R[R <= 0].sum(), 2))


def main():
    B = {n: build(n) for n in ("GOLD", "SILVER")}
    run = lambda **kw: pd.concat([trades(n, B[n], **kw) for n in B])  # noqa: E731
    rows = []
    base = run()
    rows.append(dict(test="BASE (T60, E0, no delay)", **score(base)))
    for cx in (2.0, 4.0):
        rows.append(dict(test=f"costs x{cx:g}", **score(base, cx)))
    for dl in (5, 10, 15):
        rows.append(dict(test=f"entry delay +{dl} min", **score(run(delay=dl))))
    rows.append(dict(test="R1 one position per commodity per day", **score(run(one_pos=True))))
    for mo, lab in (("E1", "trail 1x daily ATR"), ("E2", "VWAP-failure exit"), ("E3", "half at 1R, stop to entry"), ("E4", "time exit 2h"), ("E5", "time exit 4h")):
        rows.append(dict(test=f"exit {lab}", **score(run(mode=mo))))
    for tr in ("T30", "T60+D", "ADX"):
        rows.append(dict(test=f"trend {tr}", **score(run(trend=tr))))
    rows.append(dict(test="skip if already > 1.5 daily ATR from open", **score(run(chase=True))))
    S = pd.DataFrame(rows); S.to_csv(OUT / "mcxdtc2_improve.csv", index=False)
    pd.set_option("display.width", 220); print(S.to_string(index=False))


if __name__ == "__main__":
    main()
