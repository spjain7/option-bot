"""MCXE-012: SL / target design for the 1-hour OI-breakout rule (research only, DEV + VALID; OOS masked; VALID not fresh).
Historical intraday OI is not in the research store (Angel getOIData needs credentials), so the OI condition is left out
here – this test only decides HOW to place SL and target, on the same breakout + volume + wick signals.
Signal (causal, the breakout level excludes the signal candle): first 1h close beyond the prior 20-candle high (BUY) / low
(SELL); volume >= VX x 20-candle average; rejection wick <= 50 % of the candle. Entry next candle open.
Plans:
  ATR      : SL 1 ATR, target 3R (= the live rule today); call only if no swing level inside the target
  SWING    : SL beyond the 5-candle swing low/high - 0.25 ATR buffer; target = nearest 1h/daily swing level beyond entry
             (minus 0.1 ATR) capped at entry + 3 ATR; call only if 0.75 ATR <= SL distance <= 2.5 ATR and reward/risk >= RR
  BRKLVL   : as SWING but SL = breakout level -/+ 0.5 ATR
Costs: MCX cost model / index cost points, also 2x. Time exit 40 candles; forced exit before the contract switch.
python research/mcxe012/sl_target.py -> research/mcxe012/RESULTS.csv"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crude import indicators as I  # noqa: E402
from research.mcxe006 import engine as EN6  # noqa: E402
from research.mcxe007 import engine7 as E7  # noqa: E402
from research.mcxe004 import window as W  # noqa: E402

OUT = ROOT / "research/mcxe012"


def levels(h, l, c_daily_h, c_daily_l, i, side):
    """confirmed swing levels before candle i: 1h pivots (k=2, last 200 candles) + daily pivots / previous-day extreme."""
    lo = max(0, i - 200)
    out = []
    H, L = h[lo:i - 2], l[lo:i - 2]
    for j in range(2, len(H) - 2):
        if side > 0 and H[j] == max(H[j - 2:j + 3]):
            out.append(H[j])
        if side < 0 and L[j] == min(L[j - 2:j + 3]):
            out.append(L[j])
    out += list(c_daily_h if side > 0 else c_daily_l)
    return np.array(out)


def run(f, side, plan, vx, rr, cost_fn):
    o, h, l, c, v = (f[x].values.astype(float) for x in ("open", "high", "low", "close", "volume"))
    a = f.atr.values.astype(float); n = len(f)
    per = np.asarray(W.period(f.time, f.attrs["wkey"]))
    IE = EN6.iend_positional(f, 40)
    lv = pd.Series(h).shift(1).rolling(20).max().values if side > 0 else pd.Series(l).shift(1).rolling(20).min().values
    vol_x = v / pd.Series(v).rolling(20).mean().shift(1).values
    day = f.time.dt.normalize()
    dh = f.groupby(day).high.max(); dl = f.groupby(day).low.min()
    dpos = {d: k for k, d in enumerate(dh.index)}
    rows, busy = [], -1
    for i in range(60, n - 1):
        if per[i] == "OOS" or not f.sig_ok.iat[i] or i <= busy or not (a[i] > 0):
            continue
        if not (side * (c[i] - lv[i]) > 0 and side * (c[i - 1] - lv[i - 1]) <= 0 and vol_x[i] >= vx):
            continue
        rng = h[i] - l[i]
        wick = (h[i] - max(o[i], c[i])) if side > 0 else (min(o[i], c[i]) - l[i])
        if rng > 0 and wick > 0.5 * rng:
            continue
        k = dpos[day.iat[i]]
        dd_h = dh.values[max(0, k - 60):k]; dd_l = dl.values[max(0, k - 60):k]    # completed days only
        L_ = levels(h, l, dd_h, dd_l, i, side)
        beyond = L_[side * (L_ - c[i]) > 0]
        nearest = (beyond.min() if side > 0 else beyond.max()) if len(beyond) else np.nan
        e_ref = c[i]
        if plan == "ATR":
            sl = e_ref - side * 1.0 * a[i]; tg = e_ref + side * 3.0 * (1.0 * a[i])
            if np.isfinite(nearest) and side * (nearest - e_ref) < 3.0 * a[i]:
                continue
        elif plan in ("S2", "S3", "ATR15", "ATRS"):
            sw = (l[i - 4:i + 1].min() - 0.25 * a[i]) if side > 0 else (h[i - 4:i + 1].max() + 0.25 * a[i])
            if plan == "S2":
                sl = sw
            elif plan == "S3":                                    # never inside noise: at least 1.5 ATR away
                sl = min(sw, e_ref - 1.5 * a[i]) if side > 0 else max(sw, e_ref + 1.5 * a[i])
            elif plan == "ATRS":                                  # beyond the breakout candle (structure), at least 1.5 ATR
                cs = (l[i] - 0.25 * a[i]) if side > 0 else (h[i] + 0.25 * a[i])
                sl = min(cs, e_ref - 1.5 * a[i]) if side > 0 else max(cs, e_ref + 1.5 * a[i])
            else:
                sl = e_ref - side * 1.5 * a[i]
            d = side * (e_ref - sl)
            if not (0.75 * a[i] <= d <= (2.5 if plan == "ATRS" else 3.0) * a[i]):
                continue
            ref = e_ref + side * max(3.0 * a[i], 2.0 * d)               # 3 ATR reference (at least 2R) when no level is in the way
            tg = ref if not np.isfinite(nearest) else ((min(ref, nearest - 0.1 * a[i])) if side > 0 else max(ref, nearest + 0.1 * a[i]))
            if side * (tg - e_ref) / d < (rr or 1.2):
                continue
        else:
            if plan == "SWING":
                sl = (l[i - 4:i + 1].min() - 0.25 * a[i]) if side > 0 else (h[i - 4:i + 1].max() + 0.25 * a[i])
            else:
                sl = lv[i] - side * 0.5 * a[i]
            d = side * (e_ref - sl)
            if not (0.75 * a[i] <= d <= 2.5 * a[i]):
                continue
            cap = e_ref + side * 3.0 * a[i]
            tg = cap if not np.isfinite(nearest) else (min(cap, nearest - 0.1 * a[i]) if side > 0 else max(cap, nearest + 0.1 * a[i]))
            if side * (tg - e_ref) / d < rr:
                continue
        # simulate from next open
        k0 = i + 1; e = o[k0]
        R = side * (e - sl)
        if not R > 0 or side * (tg - e) <= 0:
            continue
        px, kx, why = np.nan, IE[i], "time"
        for kk in range(k0, IE[i] + 1):
            if kk > k0 and side * (o[kk] - sl) <= 0:
                px, kx, why = o[kk], kk, "stop"; break
            if side * (l[kk] - sl) <= 0 if side > 0 else side * (h[kk] - sl) <= 0:
                px, kx, why = sl, kk, "stop"; break
            if (side > 0 and h[kk] >= tg) or (side < 0 and l[kk] <= tg):
                px, kx, why = (max(tg, o[kk]) if side > 0 else min(tg, o[kk])) if kk > k0 else tg, kk, "target"; break
        if not np.isfinite(px):
            px = c[IE[i]]
        cost = cost_fn(f, np.array([c[i]]))[0]
        g = side * (px - e) / R
        rows.append(dict(inst=f.attrs["name"], date=f.time.iat[i], period=per[i], r1=g - cost / R, r2=g - 2 * cost / R, why=why,
                         sl_atr=R / a[i], tg_R=side * (tg - e) / R, hold=kx - k0))
        busy = kx
    return rows


def main():
    from research.program import mcx_disc as MD
    from research.mcxe008 import lab8 as L8
    mcx = EN6.frames("MCX", 60)
    for f in mcx:
        f.attrs.update(kind="MCX", wkey="MCX", mult=MD.REG[f.attrs["name"]]["mult"])
    idx = L8.idx1h()
    res = []
    for mk, fs in (("MCX_1h", mcx), ("IDX_1h", idx)) if "--all" in sys.argv else (("MCX_1h", mcx),):
        for side in (1, -1):
            for plan, vx, rr in (("ATR", 2.5, 0), ("ATR15", 2.5, 1.2), ("ATR15", 2.5, 1.5), ("ATRS", 2.5, 1.2), ("ATRS", 2.5, 1.5)):
                T = pd.DataFrame([r for f in fs for r in run(f, side, plan, vx, rr, E7.costs)])
                rec = dict(market=mk, side="BUY" if side > 0 else "SELL", plan=plan, vol_x=vx, min_rr=rr)
                for P in ("DEV", "VALID"):
                    x = T[T.period == P] if len(T) else T
                    m1 = E7.metrics(x, "r1", B=500) if len(x) else {}; m2 = E7.metrics(x, "r2", B=500) if len(x) else {}
                    rec.update({f"{P}_n": m1.get("n", 0), f"{P}_win": m1.get("win"), f"{P}_exp2": m2.get("exp"), f"{P}_pf": m1.get("pf"),
                                f"{P}_dd": m1.get("dd"), f"{P}_stop%": round(100 * (x.why == "stop").mean(), 1) if len(x) else None,
                                f"{P}_tgt%": round(100 * (x.why == "target").mean(), 1) if len(x) else None,
                                f"{P}_maxloss_streak": int(max((len(list(g)) for k_, g in __import__('itertools').groupby(x.r1 <= 0) if k_), default=0)) if len(x) else 0})
                res.append(rec); print(rec, flush=True)
    pd.DataFrame(res).to_csv(OUT / ("RESULTS.csv" if "--all" in sys.argv else "RESULTS_mcx_structure.csv"), index=False)


if __name__ == "__main__":
    main()
